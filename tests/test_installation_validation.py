from contextlib import closing
import json
import pathlib
import sqlite3
import tempfile
import unittest
import urllib.error
from unittest.mock import patch
from installation_validation import REQUIRED_DIRECTORIES, REQUIRED_FILES, validate_installation
import test_shell
import app


def make_installation(root):
    root.mkdir(exist_ok=True)
    for name in REQUIRED_DIRECTORIES:
        (root/name).mkdir(exist_ok=True)
    for name in REQUIRED_FILES:
        path=root/name
        path.parent.mkdir(parents=True,exist_ok=True)
        if name != 'IFsInit.db': path.touch()
    with closing(sqlite3.connect(root/'IFsInit.db', isolation_level=None)) as db:
        db.execute('CREATE TABLE IFsInit (Variable TEXT, Value TEXT)')
        db.executemany('INSERT INTO IFsInit VALUES (?,?)', [('LastYearHistory','2020'),('FirstYearForecast','2021')])
        db.execute('CREATE TABLE LoadFull (Variable TEXT, Value TEXT)')
        db.execute('INSERT INTO LoadFull VALUES (?,?)', ('ModelVersion$','8.72'))
    return root


class InstallationValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=make_installation(pathlib.Path(self.temp.name))

    def test_metadata_and_no_database_changes(self):
        original=(self.root/'IFsInit.db').read_bytes()
        self.assertEqual(validate_installation(self.root), {'base_year':2020,'version':'8.72'})
        self.assertEqual((self.root/'IFsInit.db').read_bytes(),original)

    def test_each_required_file_is_enforced(self):
        for name in REQUIRED_FILES:
            with self.subTest(name=name):
                path=self.root/name
                backup=path.with_suffix('.backup')
                path.rename(backup)
                try:
                    with self.assertRaisesRegex(ValueError,name): validate_installation(self.root)
                finally: backup.rename(path)

    def test_missing_directories_reported_together(self):
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises(ValueError) as error: validate_installation(empty)
            self.assertIn('DATA/',str(error.exception))
            self.assertIn('RUNFILES/',str(error.exception))

    def test_forecast_fallback_and_invalid_metadata(self):
        with closing(sqlite3.connect(self.root/'IFsInit.db', isolation_level=None)) as db:
            db.execute("DELETE FROM IFsInit WHERE Variable='LastYearHistory'")
        self.assertEqual(validate_installation(self.root)['base_year'],2021)
        with closing(sqlite3.connect(self.root/'IFsInit.db', isolation_level=None)) as db: db.execute("UPDATE IFsInit SET Value='invalid'")
        with self.assertRaisesRegex(ValueError,'base year'): validate_installation(self.root)

    def test_missing_version_and_corrupt_database_rejected(self):
        with closing(sqlite3.connect(self.root/'IFsInit.db', isolation_level=None)) as db: db.execute('DELETE FROM LoadFull')
        with self.assertRaisesRegex(ValueError,'ModelVersion'): validate_installation(self.root)
        (self.root/'IFsInit.db').write_bytes(b'not sqlite')
        with self.assertRaisesRegex(ValueError,'Cannot read'): validate_installation(self.root)


class InstallationRouteTests(test_shell.ShellTests):
    def test_save_and_reload_with_comparison_running_and_failed_save_preserves_settings(self):
        root=make_installation(self.data/'ifs')
        self.request('/')
        import urllib.request
        def save():
            request=urllib.request.Request(self.base+'/api/installation',data=json.dumps({'installation':str(root)}).encode(),headers={'Content-Type':'application/json','X-Companion-Token':self.server.tool_token})
            with urllib.request.urlopen(request,timeout=5) as response:return json.load(response)
        with patch.object(app,'SETTINGS',self.data/'settings.json'), patch.object(self.server.RequestHandlerClass,'comparison_running',return_value=True), patch.object(self.server.RequestHandlerClass,'comparison_proxy',side_effect=AssertionError('Settings must stay in Companion')):
            self.assertEqual(save()['version'],'8.72')
            self.assertEqual(json.loads(self.request('/api/installation'))['base_year'],2020)
            original=app.SETTINGS.read_bytes()
            (root/'DATA/SAMBase.db').unlink()
            with self.assertRaises(urllib.error.HTTPError) as error: save()
            with error.exception as response:
                self.assertIn('DATA/SAMBase.db',response.read().decode())
            self.assertEqual(app.SETTINGS.read_bytes(),original)
