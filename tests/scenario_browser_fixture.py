"""Isolated manual browser fixture. Uses installed IFs metadata and a local fake AI."""
import json
from pathlib import Path
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import companion_server
import ai_settings


class Provider(BaseHTTPRequestHandler):
    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        attached = not payload['messages'][0]['content'].endswith('Attached source summary: null')
        plan = {'purpose': 'Increase Iraq baseline yield to twofold through ylm with a linear increase.',
                'regeneration_prompt': 'Use ylm for Iraq and increase linearly from the model base year to twice baseline in 2100.',
                'filename': 'Iraq_BrowserTest.sce'}
        if attached:
            plan['filename'] = 'Iraq_BrowserFlavor.sce'
            plan['changes'] = [{'parameter': 'ylm', 'targets': ['Iraq'], 'start_year': 2023,
                                'end_year': 2024, 'operation': 'multiply', 'value': 2}]
        else:
            plan['entries'] = [{'parameter': 'ylm', 'targets': ['Iraq'],
                               'ramp': {'start_value': 1, 'end_value': 2, 'end_year': 2100}},
                               {'parameter': 'ylm', 'targets': ['Kenya'], 'values': [1, 1.1, 1.2]},
                               {'parameter': 'actreaon', 'targets': [], 'values': [1, 0, 0]},
                               {'parameter': 'inputagrim', 'targets': ['Iraq', 1], 'values': [1, 1.2, 1.4]}]
        body = json.dumps({'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant',
            'content': json.dumps({'reply': 'Local test provider: review the proposed ylm change for Iraq.', 'proposal': plan})}}]}).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]/'output/scenario-browser-check'
    root.mkdir(parents=True, exist_ok=True)
    companion_server.app.DATA_ROOT = root
    companion_server.app.SETTINGS = root/'settings.json'
    companion_server.app.SETTINGS.write_text(json.dumps({'installation': 'D:/IFs'}), encoding='utf-8')
    provider = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    threading.Thread(target=provider.serve_forever, daemon=True).start()
    ai_settings.save(root/'companion/ai-settings.json', {'endpoint': f'http://127.0.0.1:{provider.server_port}/v1', 'model': 'local-test-provider'})
    server = ThreadingHTTPServer(('127.0.0.1', 0), companion_server.Handler)
    from tool_manager import ToolManager
    import secrets
    server.tools = ToolManager(root/'companion')
    server.tool_token = secrets.token_urlsafe(32)
    package = Path(__file__).resolve().parents[1]/'scenario-tool/release/ifs-scenario-builder-0.1.0-win-x64.ifstool'
    server.tools.install(package)
    server.tools.start('ifs-scenario-builder', Path('D:/IFs'))
    print(f'Browser fixture: http://127.0.0.1:{server.server_port}', flush=True)
    try: server.serve_forever()
    finally: server.tools.close(); server.server_close(); provider.shutdown(); provider.server_close()
