"""Thin desktop adapter for the sibling model-vetting tool; no plugin framework."""
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
if not getattr(sys, 'frozen', False):
    tool = Path(os.environ.get('IFS_MODEL_VETTING_PATH', ROOT.parent/'ifs-model-vetting')).resolve()
    if not (tool/'app.py').is_file():
        raise RuntimeError('Model-vetting source is missing. Clone ifs-model-vetting beside ifs-companion or set IFS_MODEL_VETTING_PATH.')
    sys.path.insert(0, str(tool))
import app

class Handler(app.Handler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path in ('/', '/shell.js', '/shell.css'):
            filename = 'shell.html' if path == '/' else path[1:]
            content = {'shell.html':'text/html', 'shell.js':'text/javascript', 'shell.css':'text/css'}[filename]
            return self.send((ROOT/filename).read_bytes(), content+'; charset=utf-8')
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
        if self.path != '/api/ui-preferences':
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
    return server

if __name__ == '__main__':
    server=create_server(8766)
    print('IFsCompanion: http://127.0.0.1:8766',flush=True)
    server.serve_forever()
