import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import storage


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.app = self.root / 'app'
        self.app.mkdir()
        self.environment = patch.dict(os.environ, {'IFS_COMPANION_APP_DIR': str(self.app),
                                                   'LOCALAPPDATA': str(self.root / 'local')})
        self.environment.start()
        os.environ.pop('IFS_VETTING_DATA_DIR', None)
        self.old_temp = tempfile.tempdir
        self.lease = patch.object(storage, 'acquire')
        self.lease.start()

    def tearDown(self):
        tempfile.tempdir = self.old_temp
        self.lease.stop()
        self.environment.stop()
        self.temp.cleanup()

    def test_new_default_and_temporary_files_stay_beside_app(self):
        current = storage.initialize()
        self.assertEqual(current, self.app / 'data')
        self.assertEqual(Path(tempfile.gettempdir()), current / 'temp')
        self.assertEqual(os.environ['TEMP'], str(current / 'temp'))
        self.assertFalse((self.root / 'local').exists())

    def test_legacy_data_is_verified_and_original_removed(self):
        old = self.root / 'local' / 'IFsModelVetting'
        (old / 'results').mkdir(parents=True)
        (old / 'results' / 'report.json').write_text('saved')
        (old / 'WebView2').mkdir()
        (old / 'WebView2' / 'cache').write_text('cache')
        current = storage.initialize()
        self.assertEqual((current / 'results' / 'report.json').read_text(), 'saved')
        self.assertFalse(old.exists())
        self.assertFalse((current / 'WebView2').exists())
        self.assertFalse(storage.status(current)['cleanup_pending'])

    def test_pending_change_copies_latest_data_only_on_restart(self):
        current = storage.initialize()
        destination = self.root / 'custom'
        storage.schedule(current, str(destination))
        (current / 'settings.json').write_text('latest')
        self.assertFalse((destination / 'settings.json').exists())
        self.assertEqual(storage.initialize(), destination)
        self.assertEqual((destination / 'settings.json').read_text(), 'latest')
        self.assertFalse(current.exists())
        self.assertIsNone(storage.status(destination)['pending'])

    def test_conflicts_and_nested_locations_leave_configuration_unchanged(self):
        current = storage.initialize()
        before = storage.config_path().read_bytes()
        occupied = self.root / 'occupied'
        occupied.mkdir()
        (occupied / 'keep').write_text('do not replace')
        for destination in (current / 'nested', self.app, occupied):
            with self.assertRaises(ValueError):
                storage.schedule(current, str(destination))
        self.assertEqual(storage.config_path().read_bytes(), before)
        self.assertEqual((occupied / 'keep').read_text(), 'do not replace')

    def test_verification_failure_keeps_source_and_pending_configuration(self):
        current = storage.initialize()
        (current / 'results.json').write_text('original')
        destination = self.root / 'custom'
        storage.schedule(current, str(destination))
        with patch.object(storage, 'digest', side_effect=[b'a', b'b']):
            self.assertEqual(storage.initialize(), current)
        self.assertIn('still using the original', storage.status(current)['migration_error'])
        self.assertEqual((current / 'results.json').read_text(), 'original')
        self.assertEqual(list(destination.iterdir()), [])
        self.assertEqual(storage.read_config()['location'], 'data')
        self.assertEqual(storage.read_config()['pending'], str(destination))

    def test_environment_override_and_cancel(self):
        current = storage.initialize()
        storage.schedule(current, str(self.root / 'custom'))
        self.assertIsNone(storage.schedule(current, str(current))['pending'])
        with patch.dict(os.environ, {'IFS_VETTING_DATA_DIR': str(self.root / 'override')}):
            self.assertEqual(storage.initialize(), self.root / 'override')
            with self.assertRaises(ValueError):
                storage.schedule(current, str(self.root / 'custom'))

    def test_missing_source_does_not_switch_to_empty_storage(self):
        storage.write_config({'location': str(self.root / 'missing'), 'pending': str(self.root / 'target')})
        with self.assertRaises(ValueError):
            storage.initialize()
        self.assertEqual(storage.read_config()['location'], str(self.root / 'missing'))

    def test_portable_default_remains_relative(self):
        storage.initialize()
        self.assertEqual(storage.read_config()['location'], 'data')

    def test_failed_cleanup_keeps_new_location_and_retries_next_launch(self):
        current = storage.initialize()
        (current / 'saved.txt').write_text('saved')
        destination = self.root / 'custom'
        storage.schedule(current, str(destination))
        unlink = Path.unlink
        def fail_original(path, *args, **kwargs):
            if path == current / 'saved.txt':
                raise PermissionError('File is locked')
            return unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', fail_original):
            self.assertEqual(storage.initialize(), destination)
        self.assertTrue(storage.status(destination)['cleanup_pending'])
        self.assertIn('new storage folder', storage.status(destination)['cleanup_error'])
        self.assertEqual((destination / 'saved.txt').read_text(), 'saved')
        self.assertEqual(storage.initialize(), destination)
        self.assertFalse(current.exists())
        self.assertFalse(storage.status(destination)['cleanup_pending'])

    def test_configuration_failure_never_deletes_original(self):
        current = storage.initialize()
        (current / 'saved.txt').write_text('saved')
        storage.schedule(current, str(self.root / 'custom'))
        with patch.object(storage, 'write_config', side_effect=OSError('Cannot commit location')):
            self.assertEqual(storage.initialize(), current)
        self.assertEqual((current / 'saved.txt').read_text(), 'saved')
        self.assertEqual(storage.read_config()['location'], 'data')

    def prepare_cleanup(self):
        source = self.root / 'original'
        source.mkdir()
        (source / 'saved.txt').write_text('saved')
        target = self.root / 'target'
        record = storage.migrate(source, target)
        config = {'location': str(target), 'cleanup': record}
        storage.write_config(config)
        return source, target, config

    def test_changed_original_is_preserved(self):
        source, target, config = self.prepare_cleanup()
        (source / 'saved.txt').write_text('new work')
        storage.cleanup_original(config, target)
        self.assertEqual((source / 'saved.txt').read_text(), 'new work')
        self.assertEqual((target / 'saved.txt').read_text(), 'saved')
        self.assertIn('cleanup', storage.read_config())

    def test_uninventoried_files_are_not_deleted(self):
        source, target, config = self.prepare_cleanup()
        (source / 'new.txt').write_text('new work')
        storage.cleanup_original(config, target)
        self.assertEqual((source / 'new.txt').read_text(), 'new work')
        self.assertIn('cleanup', storage.read_config())

    def test_missing_destination_file_preserves_original(self):
        source, target, config = self.prepare_cleanup()
        (target / 'saved.txt').unlink()
        storage.cleanup_original(config, target)
        self.assertEqual((source / 'saved.txt').read_text(), 'saved')

    def test_cleanup_refuses_source_containing_application(self):
        source, target, config = self.prepare_cleanup()
        config['cleanup']['source'] = str(self.root)
        storage.cleanup_original(config, target)
        self.assertTrue((source / 'saved.txt').exists())

    def test_cleanup_after_source_removed_finishes_journal(self):
        source, target, config = self.prepare_cleanup()
        (source / 'saved.txt').unlink()
        source.rmdir()
        storage.cleanup_original(config, target)
        self.assertNotIn('cleanup', storage.read_config())


if __name__ == '__main__':
    unittest.main()
