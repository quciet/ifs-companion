import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from update_cleanup import cleanup, write_manifest, digest, MANIFEST, STATE


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'app'; self.root.mkdir()
        self.data = self.root/'my-work'; self.data.mkdir()
        (self.root/'engine').mkdir()
        (self.root/'engine/old.py').write_text('old code')
        (self.root/'engine/changed.py').write_text('original code')
        write_manifest(self.root, '1.0.0')
        cleanup(self.root, self.data, '1.0.0')
        (self.root/'engine/new.py').write_text('new code')
        # New package no longer contains old/changed files, but overlay leaves them on disk.
        manifest = {'version':'1.1.0','files':{'engine/new.py':digest(self.root/'engine/new.py')}}
        (self.root/MANIFEST).write_text(json.dumps(manifest))
        (self.root/'engine/changed.py').write_text('user edit')
        (self.root/'engine/unknown.txt').write_text('keep')
        (self.root/'storage.json').write_text('settings')
        (self.data/'scenario.sce').write_text('saved scenario')
        for version in ('1.0.0','1.1.0','1.2.0'):
            folder = self.data/'updates'/version; folder.mkdir(parents=True)
            (folder/f'IFsCompanion-Setup-{version}-win-x64.exe').write_text('download')
            (folder/'notes.txt').write_text('user notes')
            (folder/('a'*32+'.partial')).write_text('interrupted download')

    def test_success_removes_only_obsolete_owned_files_and_completed_downloads(self):
        cleanup(self.root,self.data,'1.1.0')
        self.assertFalse((self.root/'engine/old.py').exists())
        for name in ('engine/new.py','engine/changed.py','engine/unknown.txt','storage.json','my-work/scenario.sce'):
            self.assertTrue((self.root/name).exists(),name)
        self.assertFalse(list((self.data/'updates/1.0.0').glob('*.exe')))
        self.assertFalse(list((self.data/'updates/1.0.0').glob('*.partial')))
        self.assertTrue(list((self.data/'updates/1.2.0').glob('*.partial')))
        self.assertFalse(list((self.data/'updates/1.1.0').glob('*.exe')))
        self.assertTrue(list((self.data/'updates/1.2.0').glob('*.exe')))
        self.assertTrue((self.data/'updates/1.0.0/notes.txt').exists())

    def test_incomplete_update_preserves_previous_files_and_downloads(self):
        (self.root/'engine/new.py').write_text('partial copy')
        with self.assertRaises(ValueError): cleanup(self.root,self.data,'1.1.0')
        self.assertTrue((self.root/'engine/old.py').exists())
        self.assertTrue(list((self.data/'updates/1.0.0').glob('*.exe')))

    def test_wrong_version_does_not_clean(self):
        with self.assertRaises(ValueError): cleanup(self.root,self.data,'1.0.0')
        self.assertTrue((self.root/'engine/old.py').exists())

    def test_first_manifest_does_not_guess_old_file_ownership(self):
        (self.root/STATE).unlink()
        cleanup(self.root,self.data,'1.1.0')
        self.assertTrue((self.root/'engine/old.py').exists())

    def test_protected_storage_and_traversal_in_previous_manifest(self):
        state = self.root/STATE
        value = json.loads(state.read_text())
        for name in ('storage.json','my-work/scenario.sce'):
            value['files'][name] = digest(self.root/name)
        state.write_text(json.dumps(value))
        cleanup(self.root,self.data,'1.1.0')
        self.assertTrue((self.data/'scenario.sce').exists())
        self.assertTrue((self.root/'storage.json').exists())
        value['files']['../outside'] = '0'*64; state.write_text(json.dumps(value))
        with self.assertRaises(ValueError): cleanup(self.root,self.data,'1.1.0')

    def test_locked_file_retried_after_next_successful_launch(self):
        original = Path.unlink
        def locked(path, *args, **kwargs):
            if path.name == 'old.py': raise PermissionError('locked')
            return original(path,*args,**kwargs)
        with patch.object(Path,'unlink',locked):
            self.assertEqual(cleanup(self.root,self.data,'1.1.0')['pending'],1)
        cleanup(self.root,self.data,'1.1.0')
        self.assertFalse((self.root/'engine/old.py').exists())

    def test_links_never_followed(self):
        with patch('update_cleanup.linked', side_effect=lambda p: p.name=='engine'):
            with self.assertRaises(ValueError): cleanup(self.root,self.data,'1.1.0')
        self.assertTrue((self.root/'engine/old.py').exists())
