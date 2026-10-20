import json
from pathlib import Path
import sqlite3
from contextlib import closing
import tempfile
import unittest
from unittest.mock import patch

from scenario_compiler import References, ValidationError
from companion_server import Handler
import app


class InstallationReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for folder in ('DATA', 'RUNFILES'):
            (self.root / folder).mkdir()
        with closing(sqlite3.connect(self.root / 'RUNFILES/IFsVar.db')) as db, db:
            db.execute('CREATE TABLE IFsVar (NAME, DIMENSION1, DIMENSION2, DIMENSION3)')
            db.execute("INSERT INTO IFsVar VALUES ('labcoeffsm',1,2,3)")
        with closing(sqlite3.connect(self.root / 'DATA/IFs.db')) as db, db:
            db.execute('CREATE TABLE RegionIDNewFull (RegionName, RegionNum)')
            db.execute("INSERT INTO RegionIDNewFull VALUES ('Exact Country', 7)")
        (self.root / 'DATA/IFS.grp').write_text('3\n2, Agriculture, ALL\n2, Skilled, ALL\n')

    def test_settings_and_native_sources(self):
        settings = self.root / 'settings.json'
        settings.write_text(json.dumps({'installation': str(self.root)}))
        refs = References.from_companion_settings(settings)
        self.assertEqual(refs.dimensions('labcoeffsm'), (1, 2, 3))
        self.assertEqual(refs.targets('labcoeffsm', ['Exact Country', 'Agriculture', 'Skilled']),
                         ['Exact Country', '1', '1'])
        refs.parameters['bilateral'] = (1, 1, 0)
        self.assertEqual(refs.targets('bilateral', ['Exact Country', 'Exact Country']), ['Exact Country', '7'])

    def test_handler_reloads_selected_installation(self):
        handler = object.__new__(Handler)
        with patch.object(app, 'saved_installation', return_value=self.root):
            self.assertEqual(handler.scenario_references().dimensions('labcoeffsm'), (1, 2, 3))
            with closing(sqlite3.connect(self.root / 'RUNFILES/IFsVar.db')) as db, db:
                db.execute('UPDATE IFsVar SET DIMENSION3=0')
            self.assertEqual(handler.scenario_references().dimensions('labcoeffsm'), (1, 2, 0))
        with patch.object(app, 'saved_installation', return_value=None):
            with self.assertRaises(ValidationError):
                handler.scenario_references()

    def test_missing_database_is_not_created(self):
        path = self.root / 'RUNFILES/IFsVar.db'
        path.unlink()
        with self.assertRaises(ValidationError):
            References.from_installation(self.root)
        self.assertFalse(path.exists())

    def test_invalid_schema_halts(self):
        with closing(sqlite3.connect(self.root / 'DATA/IFs.db')) as db, db:
            db.execute('DROP TABLE RegionIDNewFull')
        with self.assertRaises(ValidationError):
            References.from_installation(self.root)
