"""Optional Scenario Builder web-service package; no dependency on Companion's engine."""
import ctypes
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from scenario_service import ScenarioService

ROOT = Path(__file__).resolve().parent


def saved_installation(settings_file):
    try:
        value = json.loads(Path(settings_file).read_text(encoding='utf-8')).get('installation')
        return Path(value) if value else None
    except FileNotFoundError:
        return None


class Handler(BaseHTTPRequestHandler):
    def send(self, value, status=200, content='application/json'):
        data = value if isinstance(value, bytes) else json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', content)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        try: self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError): pass

    def authorized(self):
        return secrets.compare_digest(self.headers.get('X-IFs-Tool-Token', ''), self.server.token)

    def do_GET(self):
        if not self.authorized(): return self.send({'error':'Unauthorized'}, 403)
        path = urlsplit(self.path).path
        try:
            if path == '/bridge/status': return self.send({'running': self.server.service.busy()})
            if path == '/bridge/capabilities':return self.send({'chat_review':1,'session_cancel':1,'persistent_sessions':1,'approved_execution':1})
            if path == '/api/scenario/download':
                identity = parse_qs(urlsplit(self.path).query).get('id', [''])[0]
                return self.send(self.server.service.download(identity), content='application/octet-stream')
            files = {'/':'index.html', '/base.css':'base.css', '/bridge.js':'bridge.js',
                     '/scenario.css':'scenario.css', '/scenario.js':'scenario.js'}
            if path in files:
                name = files[path]
                folder = ROOT if getattr(sys, 'frozen', False) or name not in ('scenario.css','scenario.js') else ROOT.parent
                content = 'text/html' if name.endswith('.html') else 'text/css' if name.endswith('.css') else 'text/javascript'
                return self.send((folder/name).read_bytes(), content=content+'; charset=utf-8')
            return self.send({'error':'Not found'}, 404)
        except (ValueError, OSError, TypeError) as error:
            return self.send({'error': str(error)}, 400)

    def do_POST(self):
        if not self.authorized(): return self.send({'error':'Unauthorized'}, 403)
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 1_200_000: raise ValueError('Request exceeds the attachment size limit.')
            request = json.loads(self.rfile.read(size))
            if not isinstance(request, dict): raise ValueError('Invalid request.')
            if self.path == '/bridge/shutdown':
                self.server.service.cancel()
                self.send({'ok':True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if self.path == '/bridge/stop':
                identity = request.get('session')
                self.server.service.cancel(identity)
                deadline = time.monotonic()+70
                while self.server.service.busy(identity) and time.monotonic() < deadline: time.sleep(.1)
                if self.server.service.busy(identity): raise ValueError('AI request is still stopping. Try again shortly.')
                self.server.service.persist_sessions()
                return self.send({'stopped':True})
            if self.path in ('/api/scenario/new','/api/scenario/chat','/api/scenario/export','/api/scenario/preview','/api/scenario/validate_file'):
                result = getattr(self.server.service, self.path.rsplit('/',1)[-1])(request)
                self.server.service.persist_sessions()
                return self.send(result)
            return self.send({'error':'Not found'}, 404)
        except (ValueError, OSError, KeyError, TypeError, ArithmeticError) as error:
            return self.send({'error':str(error)}, 400)


def create_server(data, token, ai_settings_file, shared_settings_file):
    if not token: raise ValueError('A tool authentication token is required.')
    server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
    server.token = token
    server.service = ScenarioService(data, lambda:saved_installation(shared_settings_file), settings_file=ai_settings_file)
    return server


def parent_alive(pid):
    if os.name == 'nt':
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p,ctypes.c_ulong]
        handle = kernel.OpenProcess(0x100000,False,pid)
        if not handle: return False
        try: return kernel.WaitForSingleObject(handle,0) == 0x102
        finally: kernel.CloseHandle(handle)
    try: os.kill(pid,0); return True
    except OSError: return False


def main():
    settings = os.environ['IFS_AI_SETTINGS_FILE']
    shared = os.environ.get('IFS_SETTINGS_FILE') or str(Path(settings).parent.parent/'settings.json')
    server = create_server(os.environ['IFS_TOOL_DATA_DIR'], os.environ['IFS_TOOL_TOKEN'], settings, shared)
    ready = Path(os.environ['IFS_TOOL_READY_FILE'])
    pending = ready.with_suffix('.tmp')
    pending.write_text(json.dumps({'port':server.server_port}), encoding='utf-8'); pending.replace(ready)
    def stop(): server.service.cancel(); server.shutdown()
    def watch_parent():
        while parent_alive(int(os.environ['IFS_COMPANION_PID'])): time.sleep(1)
        stop()
    def watch_stdin():
        if sys.stdin is not None: sys.stdin.read(); stop()
    threading.Thread(target=watch_parent,daemon=True).start()
    threading.Thread(target=watch_stdin,daemon=True).start()
    try: server.serve_forever()
    finally: server.service.cancel(); server.server_close()


if __name__ == '__main__': main()
