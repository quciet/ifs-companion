"""Thin desktop adapter for the sibling model-vetting tool; no plugin framework."""
import json
import os
from pathlib import Path
import sys
import secrets
import tempfile
import urllib.error
from tool_manager import ToolManager, MAX_UPLOAD
from official_tools import OfficialTools
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent
if not getattr(sys, 'frozen', False):
    tool = Path(os.environ.get('IFS_MODEL_VETTING_PATH', ROOT.parent/'ifs-model-vetting')).resolve()
    if not (tool/'app.py').is_file():
        raise RuntimeError('Model-vetting source is missing. Clone ifs-model-vetting beside ifs-companion or set IFS_MODEL_VETTING_PATH.')
    sys.path.insert(0, str(tool))
import app

class Handler(app.Handler):
    def tools(self):
        if not hasattr(self.server, 'tools'):
            self.server.tools = ToolManager(app.DATA_ROOT / 'companion')
            self.server.tool_token = secrets.token_urlsafe(32)
        self.server.tools.before_change = self.comparison_guard
        return self.server.tools

    def comparison_guard(self, identity):
        if identity == 'ifs-model-vetting':
            with app.LOCK:
                if any(j['status'] == 'running' for j in app.JOBS.values()):
                    raise ValueError('Wait for the current comparison to finish before changing this tool.')

    def official(self):
        if not hasattr(self.server, 'official_tools'):
            self.server.official_tools = OfficialTools(self.tools())
        return self.server.official_tools

    def comparison_running(self):
        state = self.tools().processes.get('ifs-model-vetting')
        return bool(state and state['process'].poll() is None)

    def comparison_proxy(self, method, path=None):
        size = int(self.headers.get('Content-Length', 0))
        if size < 0 or size > 8 * 1024**2: raise ValueError('Comparison request is too large.')
        data = self.rfile.read(size) if method == 'POST' else None
        try: response = self.tools().request('ifs-model-vetting', path or self.path, method, data)
        except urllib.error.HTTPError as error: response = error
        with response:
            return self.send(response.read(), response.headers.get('Content-Type', 'application/octet-stream'), status=response.status)

    def tool_access(self, mutate=False):
        self.tools()
        origin = f'http://127.0.0.1:{self.server.server_port}'
        if self.headers.get('Host') != origin.removeprefix('http://'):
            raise ValueError('Open Companion using its local address.')
        if self.headers.get('Origin') not in (None, origin):
            raise ValueError('Requests must come from Companion.')
        if mutate and not secrets.compare_digest(self.headers.get('X-Companion-Token', ''), self.server.tool_token):
            raise ValueError('Reload Companion before managing tools.')

    def proxy_tool(self, method):
        self.tool_access(mutate=method != 'GET')
        _, _, identity, path = self.path.split('/', 3)
        size = int(self.headers.get('Content-Length', 0))
        if size < 0 or size > 8 * 1024**2: raise ValueError('Request too large.')
        data = self.rfile.read(size) if method == 'POST' else None
        try:
            response = self.tools().request(identity, path, method, data)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return self.send(response.read(), response.headers.get('Content-Type', 'application/octet-stream'), status=response.status)

    def tool_post(self):
        self.tool_access(mutate=True)
        if self.path.startswith('/api/tools/install'):
            size = int(self.headers.get('Content-Length', 0))
            if not 0 < size <= MAX_UPLOAD: raise ValueError('Choose a tool package smaller than 4 GB.')
            expected = parse_qs(urlparse(self.path).query).get('id', [None])[0]
            with tempfile.TemporaryFile() as upload:
                remaining = size
                while remaining:
                    chunk = self.rfile.read(min(remaining, 1024 * 1024))
                    if not chunk: raise ValueError('Upload interrupted. The previous tool is unchanged.')
                    upload.write(chunk); remaining -= len(chunk)
                upload.seek(0)
                return self.send(self.tools().install(upload, expected))
        size = int(self.headers.get('Content-Length', 0))
        if not 0 < size < 16384: raise ValueError('Invalid tool request.')
        request = json.loads(self.rfile.read(size))
        identity = request.get('id')
        if self.path == '/api/tools/official-install': return self.send(self.official().begin(identity))
        if self.path == '/api/tools/open': return self.send(self.tools().start(identity, app.saved_installation()))
        if self.path == '/api/tools/close':
            result = self.tools().stop(identity)
            if identity == 'ifs-model-vetting': app.restore_jobs()
            return self.send(result)
        if self.path == '/api/tools/uninstall':
            result = self.tools().uninstall(identity)
            if identity == 'ifs-model-vetting': app.restore_jobs()
            return self.send(result)
        raise ValueError('Unknown tool action.')

    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith('/tools/') or path.startswith('/api/tools'):
            try:
                self.tool_access()
                if path == '/api/tools/catalog': return self.send(self.official().catalog())
                if path == '/api/tools/download': return self.send(self.official().progress())
                if path == '/api/tools': return self.send({'tools': self.tools().list()})
                return self.proxy_tool('GET')
            except Exception as error: return self.send({'error': str(error)}, status=400)
        if path == '/api/status':
            return self.send({'running': any(j['status'] == 'running' for j in app.JOBS.values()) or self.tools().busy() or self.official().progress()['status'] in ('checking','downloading','verifying','installing')})
        if path in ('/', '/shell.js', '/shell.css'):
            filename = 'shell.html' if path == '/' else path[1:]
            content = {'shell.html':'text/html', 'shell.js':'text/javascript', 'shell.css':'text/css'}[filename]
            body = (ROOT/filename).read_bytes()
            if filename == 'shell.html':
                self.tools()
                body = body.replace(b'__COMPANION_TOKEN__', self.server.tool_token.encode())
            return self.send(body, content+'; charset=utf-8')
        if path == '/compare' and (self.tools().programs / 'ifs-model-vetting/tool.json').is_file():
            try:
                self.comparison_guard('ifs-model-vetting')
                self.tools().start('ifs-model-vetting', app.saved_installation())
                return self.comparison_proxy('GET', '/')
            except Exception as error: return self.send({'error': str(error)}, status=400)
        if self.comparison_running() and (path.startswith('/api/') and path != '/api/ui-preferences' or path == '/audit.js'):
            return self.comparison_proxy('GET')
        if path == '/compare':
            html = (app.ROOT/'index.html').read_text(encoding='utf-8')
            style = '<style>body{background:white}main{padding:8px 4px;max-width:none}#installation,#browse,#scan,#installationPaths{display:none}section:first-of-type>label:first-child,section:first-of-type>p:first-of-type{display:none}#openSettings{display:inline-block}</style>'
            return self.send(html.replace('<main>',style+'<main>',1).encode(), 'text/html; charset=utf-8')
        if path == '/api/ui-preferences':
            try:
                with app.LOCK:
                    data=json.loads((app.DATA_ROOT/'ui-preferences.json').read_text(encoding='utf-8'))
            except (OSError,ValueError):
                data={}
            return self.send(data)
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith(('/api/tools/', '/tools/')):
            try:
                if self.path.startswith('/tools/'): return self.proxy_tool('POST')
                return self.tool_post()
            except Exception as error: return self.send({'error': str(error)}, status=400)
        if self.path != '/api/ui-preferences':
            if self.comparison_running():
                try: return self.comparison_proxy('POST')
                except Exception as error: return self.send({'error': str(error)}, status=400)
            return super().do_POST()
        try:
            request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            preferences={key:bool(request.get(key,False)) for key in ('toolsGroup','recentGroup')}
            app.DATA_ROOT.mkdir(parents=True,exist_ok=True)
            with app.LOCK:
                (app.DATA_ROOT/'ui-preferences.json').write_text(json.dumps(preferences),encoding='utf-8')
            return self.send(preferences)
        except (ValueError,TypeError,KeyError,OSError) as exc:
            return self.send({'error':str(exc)},status=400)

def create_server(port=0):
    server=app.create_server(port)
    server.RequestHandlerClass=Handler
    server.tools = ToolManager(app.DATA_ROOT / 'companion')
    server.tool_token = secrets.token_urlsafe(32)
    original_close = server.server_close
    def close():
        server.tools.close()
        original_close()
    server.server_close = close
    return server

if __name__ == '__main__':
    server=create_server(8766)
    print('IFsCompanion: http://127.0.0.1:8766',flush=True)
    try: server.serve_forever()
    finally: server.server_close()
