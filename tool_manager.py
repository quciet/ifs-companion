"""Local, self-contained IFs tool packages. User data lives outside program files."""
import ctypes
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import stat
import subprocess
import tempfile
import threading
import time
import urllib.request
import zipfile

MAX_UPLOAD = 4 * 1024**3
MAX_EXPANDED = 12 * 1024**3
RESERVED = {'compare', 'companion', 'code', 'scenario', 'settings'}

def safe_relative(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value:
        raise ValueError('Package contains an invalid file path.')
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ('', '.', '..') for part in value.split('/')):
        raise ValueError('Package paths must stay inside the tool folder.')
    for part in path.parts:
        if part.endswith((' ', '.')) or re.match(r'(?i)^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)', part):
            raise ValueError('Package contains a reserved Windows filename.')
    return path

def manifest(data):
    if not isinstance(data, dict): raise ValueError('tool.json must contain an object.')
    identity = data.get('id', '')
    if not isinstance(identity, str) or not re.fullmatch(r'[a-z][a-z0-9-]{2,63}', identity) or identity in RESERVED:
        raise ValueError('Invalid or reserved tool ID.')
    if data.get('api_version') != 1 or data.get('platform') != 'win-x64' or data.get('kind') != 'web-service':
        raise ValueError('This package requires a different Companion version or platform.')
    if not isinstance(data.get('name'), str) or not 1 <= len(data['name']) <= 80:
        raise ValueError('A tool name is required.')
    if not isinstance(data.get('version'), str) or not re.fullmatch(r'\d+\.\d+\.\d+', data['version']):
        raise ValueError('Tool version must use major.minor.patch.')
    entry = safe_relative(data.get('entrypoint'))
    if entry.suffix.lower() != '.exe': raise ValueError('A self-contained Windows executable is required.')
    # Do not accept arbitrary commands, shell strings, or environment overrides.
    return {key: data[key] for key in ('id', 'name', 'version', 'api_version', 'platform', 'kind', 'entrypoint')}

class ToolManager:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.programs = self.root / 'tools'
        self.data = self.root / 'tool-data'
        self.programs.mkdir(parents=True, exist_ok=True)
        self.data.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.processes = {}
        self.before_change = lambda identity: None

    def _folder(self, identity):
        if not isinstance(identity, str) or not re.fullmatch(r'[a-z][a-z0-9-]{2,63}', identity) or identity in RESERVED:
            raise ValueError('Invalid tool ID.')
        target = (self.programs / identity).resolve()
        if target.parent != self.programs.resolve(): raise ValueError('Invalid tool folder.')
        return target

    def read(self, identity):
        folder = self._folder(identity)
        stored = json.loads((folder / 'tool.json').read_text(encoding='utf-8'))
        result = manifest(stored)
        if isinstance(stored.get('official_sha256'),str) and re.fullmatch('[a-f0-9]{64}',stored['official_sha256']):
            result['official_sha256'] = stored['official_sha256']
        if result['id'] != identity: raise ValueError('Tool ID does not match its folder.')
        return result

    def list(self):
        with self.lock:
            result = []
            for folder in sorted(self.programs.iterdir()):
                if not folder.is_dir() or folder.name.startswith('.'): continue
                try:
                    item = self.read(folder.name)
                    state = self.processes.get(folder.name)
                    item['running'] = bool(state and state['process'].poll() is None)
                    result.append(item)
                except (ValueError, OSError): continue
            return result

    def install(self, archive, expected_id=None, official_sha256=None):
        with self.lock, zipfile.ZipFile(archive) as package:
            infos = package.infolist()
            if len(infos) > 100000 or sum(i.file_size for i in infos) > MAX_EXPANDED:
                raise ValueError('The tool package is too large.')
            names = set()
            for info in infos:
                name = info.filename.rstrip('/')
                safe_relative(name)
                if name.casefold() in names: raise ValueError('Duplicate file in tool package.')
                names.add(name.casefold())
                if stat.S_ISLNK(info.external_attr >> 16): raise ValueError('Links are not allowed in tool packages.')
            info = package.getinfo('tool.json')
            if info.file_size > 16384: raise ValueError('Invalid tool manifest.')
            meta = manifest(json.loads(package.read(info)))
            identity = meta['id']
            self.before_change(identity)
            if official_sha256: meta['official_sha256'] = official_sha256
            if expected_id and expected_id != identity: raise ValueError('Choose an update package for this tool.')
            folder = self._folder(identity)
            if meta['entrypoint'] not in package.namelist(): raise ValueError('The tool executable is missing.')
            if folder.exists():
                self._require_stopped(identity)
                previous = self.read(identity)
                if tuple(map(int, meta['version'].split('.'))) < tuple(map(int, previous['version'].split('.'))):
                    raise ValueError('An older version cannot replace an installed tool.')
            with tempfile.TemporaryDirectory(prefix='.install-', dir=self.programs) as temp:
                stage = Path(temp) / 'new'
                stage.mkdir()
                for info in infos:
                    target = stage.joinpath(*PurePosixPath(info.filename).parts)
                    if info.is_dir(): target.mkdir(parents=True, exist_ok=True); continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with package.open(info) as source, target.open('wb') as output:
                        shutil.copyfileobj(source, output, 1024 * 1024)
                (stage / 'tool.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
                backup = Path(temp) / 'previous'
                if folder.exists(): folder.rename(backup)
                try: stage.rename(folder)
                except Exception:
                    if backup.exists(): backup.rename(folder)
                    raise
            return meta

    def _require_stopped(self, identity):
        state = self.processes.get(identity)
        if state and state['process'].poll() is None:
            raise ValueError('Close this tool before updating or uninstalling it.')
        # A tool from a previous Companion session may still be shutting down.
        if os.name == 'nt':
            exe = self._folder(identity) / self.read(identity)['entrypoint']
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CreateFileW.restype = ctypes.c_void_p
            handle = kernel.CreateFileW(str(exe), 0x80000000, 0, None, 3, 0, None)
            if handle == ctypes.c_void_p(-1).value: raise ValueError('The tool is in use. Close it and try again.')
            kernel.CloseHandle(ctypes.c_void_p(handle))

    def uninstall(self, identity):
        with self.lock:
            self.before_change(identity)
            folder = self._folder(identity)
            self.read(identity)
            self._require_stopped(identity)
            shutil.rmtree(folder)
            return {'removed': identity, 'data_preserved': True}

    def start(self, identity, installation=''):
        with self.lock:
            state = self.processes.get(identity)
            if state and state['process'].poll() is None: return {'url': f'/tools/{identity}/'}
            meta = self.read(identity)
            data = self.data / identity
            data.mkdir(parents=True, exist_ok=True)
            ready = data / ('ready-' + secrets.token_hex(12) + '.json')
            token = secrets.token_urlsafe(32)
            env = dict(os.environ, IFS_COMPANION_MODE='1', IFS_COMPANION_PID=str(os.getpid()), IFS_TOOL_DATA_DIR=str(data),
                       IFS_TOOL_READY_FILE=str(ready), IFS_TOOL_TOKEN=token, IFS_INSTALLATION=str(installation) if installation else '')
            if identity == 'ifs-model-vetting':
                env['IFS_VETTING_DATA_DIR'] = str(self.root.parent)
            with (data / 'tool.log').open('ab') as log:
                process = subprocess.Popen([str(self._folder(identity) / meta['entrypoint'])],
                    cwd=self._folder(identity), env=env, stdin=subprocess.PIPE, stdout=log, stderr=log,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            try:
                for _ in range(600):
                    if process.poll() is not None: raise ValueError('The tool could not start. See its tool.log for details.')
                    if ready.exists():
                        endpoint = json.loads(ready.read_text(encoding='utf-8'))
                        port = endpoint.get('port')
                        if not isinstance(port, int) or not 1 <= port <= 65535: raise ValueError('Invalid tool startup response.')
                        self.processes[identity] = {'process': process, 'port': port, 'token': token}
                        return {'url': f'/tools/{identity}/'}
                    time.sleep(.1)
                raise ValueError('The tool took too long to start. See its tool.log for details.')
            except Exception:
                process.stdin.close()
                if process.poll() is None: process.terminate()
                raise
            finally: ready.unlink(missing_ok=True)

    def request(self, identity, path, method='GET', data=None):
        state = self.processes.get(identity)
        if not state or state['process'].poll() is not None: raise ValueError('This tool is closed. Open it again from Tools.')
        request = urllib.request.Request(f'http://127.0.0.1:{state["port"]}/' + path.lstrip('/'),
            data=data, method=method, headers={'X-IFs-Tool-Token':state['token'], 'Content-Type':'application/json'})
        return urllib.request.urlopen(request, timeout=3 if path in ('bridge/status', 'bridge/shutdown') else None)

    def stop(self, identity, force=False):
        with self.lock:
            state = self.processes.get(identity)
            if not state or state['process'].poll() is not None: return {'closed':identity}
            if not force:
                with self.request(identity, 'bridge/status') as response:
                    if json.load(response).get('running'): raise ValueError('This tool is busy. Stop its work before closing it.')
            try:
                with self.request(identity, 'bridge/shutdown', 'POST', b'{}') as response: response.read()
            except Exception: pass
            state['process'].stdin.close()
            try: state['process'].wait(timeout=10)
            except subprocess.TimeoutExpired: state['process'].terminate()
            return {'closed':identity}

    def busy(self):
        for identity, state in list(self.processes.items()):
            if state['process'].poll() is not None: continue
            try:
                with self.request(identity, 'bridge/status') as response:
                    if json.load(response).get('running'): return True
            except Exception: return True
        return False

    def close(self):
        for identity in list(self.processes): self.stop(identity, force=True)
