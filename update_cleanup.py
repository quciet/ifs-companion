"""Conservative cleanup after a packaged desktop successfully opens."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat

MANIFEST = 'app-files.json'
STATE = '.installed-files.json'
PROTECTED = {'data', 'output', 'updates', 'release', 'scenarios', 'tool-data', 'companion',
             'settings.json', 'storage.json', MANIFEST, STATE}


def linked(path):
    return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def safe_file(root, relative):
    parts = PurePosixPath(relative).parts
    if not parts or '\\' in relative or ':' in relative or relative.startswith('/') or any(p in ('.', '..') for p in relative.split('/')):
        raise ValueError('Invalid manifest path')
    target = root
    for part in parts:
        target = target/part
        if target.exists() or target.is_symlink():
            if linked(target): raise ValueError('Linked cleanup path')
    return target


def digest(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_manifest(path):
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict) or not isinstance(value.get('version'), str) or not re.fullmatch(r'\d+\.\d+\.\d+', value['version']): raise ValueError('Invalid manifest version')
    files = value.get('files')
    if not isinstance(files, dict): raise ValueError('Invalid manifest files')
    for name, checksum in files.items():
        if not isinstance(name, str) or not isinstance(checksum, str) or not re.fullmatch('[a-f0-9]{64}', checksum): raise ValueError('Invalid manifest entry')
    return value


def write_manifest(root, version):
    root = Path(root)
    files = {}
    for path in root.rglob('*'):
        if linked(path): raise ValueError('Cannot package links')
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            if relative.split('/')[0].lower() in PROTECTED: continue
            files[relative] = digest(path)
    (root/MANIFEST).write_text(json.dumps({'version':version, 'files':files}, indent=2), encoding='utf-8')


def cleanup(app_root, data_root, version):
    root, data = Path(app_root).absolute(), Path(data_root).absolute()
    # Reject links even in ancestors; never follow a redirected installation/data root.
    for base in (root, data):
        for path in (base, *base.parents):
            if linked(path): raise ValueError('Linked installation or storage root')
    current = read_manifest(safe_file(root, MANIFEST))
    if current['version'] != version: raise ValueError('Running version does not match package')
    protected = set(PROTECTED)
    if data.is_relative_to(root):
        if data == root: raise ValueError('Storage overlaps application root')
        protected.add(data.relative_to(root).parts[0].lower())
    def owned(name): return name.split('/')[0].lower() not in protected
    # Validate every new file before deleting anything (partial updates fail closed).
    for name, checksum in current['files'].items():
        path = safe_file(root, name)
        if not owned(name) or not path.is_file() or digest(path) != checksum:
            raise ValueError('Installed package is incomplete or modified')
    state = safe_file(root, STATE)
    previous = read_manifest(state) if state.exists() else {'files':{}}
    # Validate all previous paths before any deletion.
    for name in previous['files']: safe_file(root, name)
    retained = {}
    removed = 0
    current_names = {name.lower() for name in current['files']}
    for name, checksum in previous['files'].items():
        if name.lower() in current_names or not owned(name): continue
        path = safe_file(root, name)
        if not path.is_file(): continue
        if digest(path) != checksum: continue  # A locally modified file now belongs to the user.
        try:
            path.unlink(); removed += 1
            parent = path.parent
            while parent != root:
                try: parent.rmdir()
                except OSError: break
                parent = parent.parent
        except OSError: retained[name] = checksum  # Retry locked files on the next successful launch.
    pending = safe_file(root, STATE+'.tmp')
    pending.write_text(json.dumps({'version':version, 'files':{**retained, **current['files']}}, indent=2), encoding='utf-8')
    pending.replace(state)
    updates = safe_file(data, 'updates')
    if updates.is_dir():
        for directory in updates.iterdir():
            if linked(directory) or not directory.is_dir() or not re.fullmatch(r'\d+\.\d+\.\d+', directory.name): continue
            if tuple(map(int,directory.name.split('.'))) > tuple(map(int,version.split('.'))): continue
            names = {f'IFsCompanion-Setup-{directory.name}-win-x64.exe',
                     f'IFsCompanion-Portable-{directory.name}-win-x64.zip', f'SHA256SUMS-{directory.name}.txt'}
            for file in directory.iterdir():
                if linked(file) or not file.is_file() or (file.name not in names and not re.fullmatch(r'[a-f0-9]{32}\.partial', file.name)): continue
                try: file.unlink(); removed += 1
                except OSError: pass  # The installer may still be running; retry next launch.
            try: directory.rmdir()
            except OSError: pass
    return {'removed':removed, 'pending':len(retained)}
