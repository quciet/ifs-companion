"""Explicit, checksum-verified updates from the official Companion releases."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import threading
import uuid
import json

from official_tools import COMPANION_VERSION, open_url

REPOSITORY = 'https://github.com/quciet/ifs-companion'
RELEASES_API = 'https://api.github.com/repos/quciet/ifs-companion/releases?per_page=100'
MAX_PACKAGE = 2 * 1024**3


def select_release(releases):
    if not isinstance(releases, list): raise ValueError('Invalid release information.')
    stable = []
    for release in releases:
        if not isinstance(release, dict) or release.get('draft') or release.get('prerelease'): continue
        match = re.fullmatch(r'v(\d+)\.(\d+)\.(\d+)', str(release.get('tag_name', '')))
        if match: stable.append((tuple(map(int, match.groups())), release))
    if not stable: raise ValueError('No stable Companion release is available.')
    version, release = max(stable, key=lambda item:item[0])
    text = '.'.join(map(str, version))
    files = {}
    for kind, name in [('installer', f'IFsCompanion-Setup-{text}-win-x64.exe'),
                       ('portable', f'IFsCompanion-Portable-{text}-win-x64.zip'),
                       ('checksums', f'SHA256SUMS-{text}.txt')]:
        matches = [asset for asset in release.get('assets', []) if asset.get('name') == name]
        if len(matches) != 1: raise ValueError('The latest Companion release is missing a required download.')
        asset = matches[0]
        url = f'{REPOSITORY}/releases/download/v{text}/{name}'
        if asset.get('browser_download_url') != url or type(asset.get('size')) is not int or not 0 < asset['size'] <= MAX_PACKAGE:
            raise ValueError('The release download information is invalid.')
        files[kind] = {'name':name, 'url':url, 'size':asset['size']}
    return {'version':text, 'url':f'{REPOSITORY}/releases/tag/v{text}',
            'notes':str(release.get('body') or '')[:16000], 'files':files}


class AppUpdates:
    def __init__(self, data_root, app_directory, current=COMPANION_VERSION, frozen=False, opener=open_url):
        self.folder = Path(data_root)/'updates'
        self.app_directory = Path(app_directory)
        self.current = tuple(current)
        self.mode = 'source' if not frozen else 'installer' if (self.app_directory/'unins000.exe').is_file() else 'portable'
        self.opener = opener
        self.lock = threading.RLock()
        self.release = None
        self.ready = None
        self.state = {'status':'idle', 'message':'Check the official source for a newer Companion release.', 'received':0, 'total':0}

    def progress(self):
        with self.lock:
            return {**self.state, 'current_version':'.'.join(map(str,self.current)), 'distribution':self.mode,
                    'release':self.release, 'can_install':self.mode == 'installer' and self.state['status'] == 'ready' and bool(self.ready and self.ready['kind']=='installer')}

    def active(self):
        with self.lock: return self.state['status'] in ('checking','downloading','verifying')

    def _state(self, **values):
        with self.lock: self.state.update(values)

    def check(self):
        with self.lock:
            if self.active(): raise ValueError('Wait for the current update operation.')
            self.release = None; self.ready = None
            self.state = {'status':'checking','message':'Checking official Companion releases…','received':0,'total':0}
        threading.Thread(target=self._check, daemon=True).start()
        return self.progress()

    def _check(self):
        try:
            with self.opener(RELEASES_API) as response: raw = response.read(2_000_001)
            if len(raw) > 2_000_000: raise ValueError('Release information exceeded its size limit.')
            release = select_release(json.loads(raw))
            newer = tuple(map(int, release['version'].split('.'))) > self.current
            with self.lock:
                self.release = release
                self.state.update(status='available' if newer else 'up_to_date',
                    message=f'Companion {release["version"]} is available.' if newer else 'You are up to date.',
                    checked_at=datetime.now(timezone.utc).isoformat(timespec='seconds'))
        except Exception:
            self._state(status='error', message='Could not check for updates. Check your connection and try again.')

    def download(self, kind):
        with self.lock:
            if self.active(): raise ValueError('Wait for the current update operation.')
            if kind not in ('installer','portable'): raise ValueError('Choose the installer or portable ZIP.')
            if not self.release or tuple(map(int,self.release['version'].split('.'))) <= self.current:
                raise ValueError('Check for a newer Companion release first.')
            release = self.release
            self.ready = None
            self.state.update(status='downloading',kind=kind,received=0,total=release['files'][kind]['size'],message='Downloading from the official release…')
        threading.Thread(target=self._download,args=(release,kind),daemon=True).start()
        return self.progress()

    def _download(self, release, kind):
        pending = None
        try:
            checksum = release['files']['checksums']
            if checksum['size'] > 16384: raise ValueError('Checksum manifest is too large.')
            with self.opener(checksum['url']) as response: raw = response.read(16385)
            if len(raw) > 16384 or len(raw) != checksum['size']: raise ValueError('Invalid checksum manifest.')
            asset = release['files'][kind]
            matches = []
            for line in raw.decode('ascii').splitlines():
                match = re.fullmatch(r'([a-fA-F0-9]{64})\s+\*?(.+)', line)
                if match and match.group(2) == asset['name']: matches.append(match.group(1).lower())
            if len(matches) != 1: raise ValueError('The checksum manifest does not identify this download.')
            expected = matches[0]
            directory = self.folder/release['version']; directory.mkdir(parents=True,exist_ok=True)
            destination = directory/asset['name']
            pending = directory/(uuid.uuid4().hex+'.partial')
            digest=hashlib.sha256();received=0
            with self.opener(asset['url']) as response, pending.open('xb') as stream:
                while True:
                    chunk = response.read(1024*1024)
                    if not chunk: break
                    received += len(chunk)
                    if received > asset['size']: raise ValueError('Download exceeded its expected size.')
                    stream.write(chunk);digest.update(chunk)
                    self._state(received=received)
            self._state(status='verifying',message='Verifying SHA256 checksum…')
            if received != asset['size'] or digest.hexdigest() != expected: raise ValueError('Download verification failed.')
            pending.replace(destination)
            with self.lock:
                self.ready = {'path':str(destination.resolve()),'sha256':expected,'kind':kind}
                self.state.update(status='ready',path=str(destination.resolve()),message='Download verified and ready.')
        except Exception:
            self._state(status='error', message='Update download or checksum verification failed. The app was not changed; retry the download.')
        finally:
            if pending: pending.unlink(missing_ok=True)

    def verified_file(self):
        with self.lock:
            if self.state['status'] != 'ready' or not self.ready: raise ValueError('Download and verify an update first.')
            record = dict(self.ready)
        path = Path(record['path'])
        if not path.is_relative_to(self.folder.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != record['sha256']:
            raise ValueError('The downloaded update changed. Download it again.')
        return record

    def complete_startup(self):
        with self.lock:
            if self.mode == 'source' or self.active(): return {'skipped':True}
            from update_cleanup import cleanup
            return cleanup(self.app_directory, self.folder.parent, '.'.join(map(str,self.current)))

    def prepare_install(self):
        record = self.verified_file()
        if self.mode != 'installer' or record['kind'] != 'installer':
            raise ValueError('Portable and source copies must be updated manually from the downloaded package.')
        return record
