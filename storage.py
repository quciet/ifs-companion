"""Companion-owned storage, selected before the engine or browser starts."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import uuid

LOCK = threading.RLock()
_leases = []
_migration_error = None
_cleanup_error = None


def acquire(path):
    """Hold a cross-process lease for the lifetime of this engine."""
    path.mkdir(parents=True, exist_ok=True)
    handle = (path / '.storage.lock').open('a+b')
    try:
        if os.name == 'nt':
            import msvcrt
            handle.seek(0)
            if not handle.read(1):
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise ValueError('This storage folder is in use. Close other Companion windows before reopening: ' + str(path))
    _leases.append(handle)
    return handle


def release(handle):
    handle.close()
    if handle in _leases:
        _leases.remove(handle)


def app_directory():
    if os.environ.get('IFS_COMPANION_APP_DIR'):
        return Path(os.environ['IFS_COMPANION_APP_DIR']).resolve()
    return Path(sys.executable).resolve().parent.parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent


def config_path():
    return app_directory() / 'storage.json'


def read_config():
    try:
        value = json.loads(config_path().read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}
    if not isinstance(value, dict):
        raise ValueError('Invalid storage.json beside Companion. Restore this file before starting.')
    return value


def write_config(value):
    path = config_path()
    temporary = path.with_name('storage-' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def resolve_location(value=None):
    return (app_directory() / (value or 'data')).resolve()


def writable(path):
    path.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=path):
        pass


def validate_destination(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination:
        return
    if source.is_relative_to(destination) or destination.is_relative_to(source):
        raise ValueError('Choose a folder separate from the current storage folder, not inside it or above it.')
    if destination == app_directory() or app_directory().is_relative_to(destination):
        raise ValueError('Choose a dedicated data folder, not the application folder itself.')
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Choose an empty folder so existing files cannot be overwritten.')
    writable(destination)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').digest()


def migrate(source, destination):
    """Stage a verified copy and return an exact inventory for post-commit cleanup."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    validate_destination(source, destination)
    if source == destination:
        raise ValueError('The new storage folder must differ from the current folder.')
    if not source.is_dir():
        raise ValueError('The original storage folder is unavailable: ' + str(source))
    inventory = {'source': str(source), 'destination': str(destination), 'files': {}, 'directories': []}
    with tempfile.TemporaryDirectory(prefix='.companion-migration-', dir=destination.parent) as temporary:
        stage = Path(temporary) / 'data'
        stage.mkdir()
        def unreadable(error):
            raise error
        for current, directories, files in os.walk(source, followlinks=False, onerror=unreadable):
            parent = Path(current)
            relative = parent.relative_to(source)
            for name in directories + files:
                item = parent / name
                if item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()):
                    raise ValueError('Storage contains a link or junction; move that data separately: ' + str(item))
            inventory['directories'].append(relative.as_posix())
            disposable = bool(relative.parts and relative.parts[0] in ('WebView2', 'temp'))
            if not disposable:
                (stage / relative).mkdir(parents=True, exist_ok=True)
            for name in files:
                if relative == Path('.') and name == '.storage.lock':
                    continue
                original, copied = parent / name, stage / relative / name
                checksum = digest(original)
                if not disposable:
                    shutil.copy2(original, copied)
                    if checksum != digest(copied) or checksum != digest(original):
                        raise OSError('Storage verification failed: ' + str(original))
                inventory['files'][(relative / name).as_posix()] = {'sha256': checksum.hex(), 'disposable': disposable}
        # Refuse a destination changed by another process while copying.
        destination.rmdir()
        stage.rename(destination)
    return inventory


def cleanup_original(config, current):
    """Delete only unchanged files inventoried by the committed migration.

    Persist the inventory until cleanup completes so interrupted cleanup is resumable.
    Never recursively delete a user-selected directory.
    """
    global _cleanup_error
    record = config.get('cleanup')
    if not record:
        return config
    try:
        source = Path(record['source'])
        destination = Path(record['destination']).resolve()
        # Validate absolute targets before deleting anything, including on recovery.
        if not source.is_absolute() or source.resolve() != source or source == Path(source.anchor):
            raise ValueError('The original storage path has changed; cleanup was stopped.')
        if destination != Path(current).resolve() or not destination.is_dir():
            raise ValueError('The new storage folder is unavailable; cleanup was stopped.')
        if source == destination or source.is_relative_to(destination) or destination.is_relative_to(source):
            raise ValueError('Storage folders overlap; cleanup was stopped.')
        if app_directory().is_relative_to(source):
            raise ValueError('The original folder contains the application; cleanup was stopped.')
        if source.exists():
            lease = acquire(source)
            try:
                for relative, item in record['files'].items():
                    original = source / relative
                    if original.resolve() != original or not original.is_relative_to(source):
                        raise ValueError('An original file path has changed; cleanup was stopped.')
                    if not original.exists():
                        continue  # Already removed before an interrupted cleanup.
                    if digest(original).hex() != item['sha256']:
                        raise ValueError('A file changed in the original folder; it was preserved: ' + str(original))
                    if not item['disposable'] and not (destination / relative).is_file():
                        raise ValueError('A migrated file is missing; the original was preserved: ' + relative)
                    original.unlink()
            finally:
                release(lease)
            for relative in sorted(record['directories'], key=lambda value: len(Path(value).parts), reverse=True):
                directory = source / relative
                if directory == source:
                    continue
                if directory.resolve() != directory or not directory.is_relative_to(source):
                    raise ValueError('An original directory path has changed; cleanup was stopped.')
                if directory.exists():
                    directory.rmdir()  # Refuses unexpected/new files instead of deleting them.
            (source / '.storage.lock').unlink(missing_ok=True)
            source.rmdir()
        updated = dict(config)
        updated.pop('cleanup')
        write_config(updated)
        return updated
    except (OSError, ValueError) as error:
        _cleanup_error = 'Using the new storage folder, but some original files could not be removed. ' + str(error)
        return config


def status(current):
    config = read_config()
    override = bool(os.environ.get('IFS_VETTING_DATA_DIR'))
    return {'current': str(current), 'default': str(resolve_location()),
            'pending': str(resolve_location(config['pending'])) if config.get('pending') else None,
            'backup': config.get('backup'), 'environment_override': override, 'migration_error': _migration_error,
            'cleanup_pending': bool(config.get('cleanup')), 'cleanup_error': _cleanup_error}


def schedule(current, value):
    global _migration_error
    with LOCK:
        if os.environ.get('IFS_VETTING_DATA_DIR'):
            raise ValueError('Storage is controlled by IFS_VETTING_DATA_DIR. Remove that environment override before changing it here.')
        if not isinstance(value, str) or not value.strip():
            raise ValueError('Choose a storage folder.')
        destination = Path(value.strip()).expanduser()
        if not destination.is_absolute():
            raise ValueError('Enter an absolute storage folder path.')
        destination = destination.resolve()
        validate_destination(current, destination)
        config = read_config()
        if config.get('cleanup'):
            raise ValueError('Restart Companion to finish the previous storage cleanup before moving storage again.')
        if destination == Path(current).resolve():
            config.pop('pending', None)
        else:
            config['pending'] = 'data' if destination == resolve_location() else str(destination)
        # Explicit source permits safe migration even after a portable app is relocated.
        config['location'] = 'data' if Path(current).resolve() == resolve_location() else str(current)
        write_config(config)
        _migration_error = None
        return status(current)


def initialize():
    global _migration_error, _cleanup_error
    with LOCK:
        _migration_error = None
        _cleanup_error = None
        override = os.environ.get('IFS_VETTING_DATA_DIR')
        config = read_config() if not override else {}
        current = Path(override).resolve() if override else resolve_location(config.get('location'))
        if not override:
            if config.get('pending'):
                if not current.is_dir():
                    raise ValueError('The original storage folder is unavailable: ' + str(current))
                source_lease = acquire(current)
                try:
                    destination = resolve_location(config['pending'])
                    inventory = migrate(current, destination)
                    updated = {**config, 'location': config['pending'], 'cleanup': inventory}
                    updated.pop('pending')
                    write_config(updated)
                    config = updated
                    current = destination
                except (ValueError, OSError) as error:
                    _migration_error = 'Storage change failed; still using the original folder. ' + str(error)
                finally:
                    release(source_lease)
            elif not config and not current.exists():
                legacy = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'IFsModelVetting'
                if legacy.exists() and legacy.resolve() != current:
                    source_lease = acquire(legacy)
                    try:
                        inventory = migrate(legacy, current)
                    finally:
                        release(source_lease)
                    config['cleanup'] = inventory
                config['location'] = 'data'
                write_config(config)
        acquire(current)
        writable(current)
        if not override:
            cleanup_original(config, current)
        temporary = current / 'temp'
        writable(temporary)
        # Python and subprocesses (including installed tools) share this temp root.
        os.environ['TEMP'] = os.environ['TMP'] = os.environ['TMPDIR'] = str(temporary)
        tempfile.tempdir = str(temporary)
        return current
