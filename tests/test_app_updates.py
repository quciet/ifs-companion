import hashlib
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from app_updates import AppUpdates, select_release


def release(version='0.2.3', payload=b'installer-test', **extra):
    names=[f'IFsCompanion-Setup-{version}-win-x64.exe',f'IFsCompanion-Portable-{version}-win-x64.zip',f'SHA256SUMS-{version}.txt']
    digest=hashlib.sha256(payload).hexdigest()
    manifest=''.join(digest+'  '+name+'\n' for name in names[:2]).encode()
    assets=[{'name':name,'size':len(manifest) if i==2 else len(payload),
             'browser_download_url':f'https://github.com/quciet/ifs-companion/releases/download/v{version}/{name}'} for i,name in enumerate(names)]
    return {'tag_name':'v'+version,'draft':False,'prerelease':False,'assets':assets,'body':'Release notes',**extra},manifest


class AppUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.app=self.root/'app';self.app.mkdir()
        (self.app/'unins000.exe').write_bytes(b'fixture')
        self.payload=b'verified-update';self.record,self.manifest=release(payload=self.payload)
        self.download=self.payload
        def opener(url):
            if '/releases?' in url:return io.BytesIO(json.dumps([self.record]).encode())
            return io.BytesIO(self.manifest if url.endswith('.txt') else self.download)
        self.updater=AppUpdates(self.root/'data',self.app,current=(0,2,2),frozen=True,opener=opener)

    def wait(self):
        deadline=time.monotonic()+3
        while self.updater.active() and time.monotonic()<deadline:time.sleep(.01)
        self.assertFalse(self.updater.active());return self.updater.progress()

    def test_filters_tool_releases_prereleases_and_drafts(self):
        stable,_=release('0.2.3');tool={**stable,'tag_name':'scenario-builder-v99.0.0'}
        prerelease,_=release('99.0.0',prerelease=True);draft,_=release('98.0.0',draft=True)
        self.assertEqual(select_release([tool,prerelease,draft,stable])['version'],'0.2.3')
        broken={**stable,'assets':[dict(a) for a in stable['assets']]};broken['assets'][0]['browser_download_url']='https://other.example/setup.exe'
        with self.assertRaises(ValueError):select_release([broken])

    def test_verified_download_and_tamper_detection(self):
        self.updater.check();self.assertEqual(self.wait()['status'],'available')
        self.updater.download('installer');self.assertEqual(self.wait()['status'],'ready')
        record=self.updater.prepare_install();self.assertEqual(Path(record['path']).read_bytes(),self.payload)
        Path(record['path']).write_bytes(b'changed')
        with self.assertRaises(ValueError):self.updater.prepare_install()

    def test_mismatch_never_replaces_previous_verified_file(self):
        self.updater.check();self.wait();self.updater.download('installer');self.wait()
        previous=Path(self.updater.verified_file()['path']);self.download=b'bad'
        self.updater.download('installer');self.assertEqual(self.wait()['status'],'error')
        self.assertEqual(previous.read_bytes(),self.payload)
        self.assertFalse(list(self.updater.folder.rglob('*.partial')))
        with self.assertRaises(ValueError):self.updater.prepare_install()

    def test_portable_download_cannot_launch_installer(self):
        self.updater.mode='portable';self.updater.check();self.wait();self.updater.download('portable')
        self.assertFalse(self.wait()['can_install'])
        with self.assertRaises(ValueError):self.updater.prepare_install()

    def test_offline_is_not_reported_up_to_date(self):
        def offline(url):raise OSError('offline')
        self.updater.opener=offline;self.updater.check();self.assertEqual(self.wait()['status'],'error')
        self.assertIsNone(self.updater.progress()['release'])

    def test_current_version_is_not_downgraded(self):
        self.updater.current=(1,0,0);self.updater.check();self.assertEqual(self.wait()['status'],'up_to_date')
        with self.assertRaises(ValueError):self.updater.download('installer')


if __name__=='__main__':unittest.main()
