import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError

import ai_settings


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'settings.json'
        self.draft = {'endpoint': 'https://example.test/v1', 'model': 'chat', 'api_key': 'draft-key'}

    def response(self, value):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = json.dumps(value).encode()
        return opener

    def test_models_without_model_and_without_saving(self):
        opener = self.response({'data': [{'id': 'z'}, {'id': 'a'}, {'id': 'a'}]})
        with patch.object(ai_settings, 'build_opener', return_value=opener):
            result = ai_settings.probe(self.path, {**self.draft, 'model': ''}, models=True)
        self.assertEqual(result['models'], ['a', 'z'])
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'https://example.test/v1/models')
        self.assertEqual(request.get_header('Authorization'), 'Bearer draft-key')
        self.assertFalse(self.path.exists())

    def test_connection_never_generates_or_requires_model(self):
        opener = self.response({'data': []})
        with patch.object(ai_settings, 'build_opener', return_value=opener):
            self.assertIn('verified', ai_settings.probe(self.path, {**self.draft, 'model': ''})['message'])
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'https://example.test/v1/models')
        self.assertEqual(request.get_method(), 'GET')
        self.assertIsNone(request.data)
        opener.open.assert_called_once()

    def test_connection_returns_models_without_key(self):
        opener = self.response({'data': [{'id': 'local-chat'}]})
        with patch.object(ai_settings, 'build_opener', return_value=opener):
            result = ai_settings.probe(self.path, {**self.draft, 'api_key': '', 'model': ''})
        self.assertEqual(result['models'], ['local-chat'])
        self.assertIsNone(opener.open.call_args.args[0].get_header('Authorization'))
        self.assertFalse(self.path.exists())
        opener.open.assert_called_once()

    def test_named_connections_migrate_switch_and_delete(self):
        self.path.write_text(json.dumps({'endpoint': self.draft['endpoint'], 'model': 'old', 'protected_key': 'eA=='}))
        migrated = ai_settings.load(self.path)
        self.assertEqual(migrated['name'], 'Default connection')
        self.assertNotIn('protected_key', json.dumps(migrated))
        saved = ai_settings.save(self.path, {**self.draft, 'id': '', 'name': 'Second', 'api_key': ''})
        second_id = saved['id']
        self.assertEqual(len(saved['connections']), 2)
        self.assertFalse(saved['has_key'])
        switched = ai_settings.save(self.path, {'action': 'activate', 'id': 'default'})
        self.assertEqual(switched['model'], 'old')
        self.assertTrue(switched['has_key'])
        deleted = ai_settings.save(self.path, {'action': 'delete', 'id': 'default'})
        self.assertEqual(deleted['active_id'], second_id)
        self.assertEqual(len(deleted['connections']), 1)

    def test_probe_uses_selected_connection_not_active_key(self):
        self.path.write_text(json.dumps({'active_id': 'a', 'connections': [
            {'id': 'a', 'name': 'A', 'endpoint': self.draft['endpoint'], 'model': 'chat', 'protected_key': 'YQ=='},
            {'id': 'b', 'name': 'B', 'endpoint': self.draft['endpoint'], 'model': 'chat', 'protected_key': 'Yg=='}]}))
        opener = self.response({'data': []})
        with patch.object(ai_settings, 'build_opener', return_value=opener), patch.object(ai_settings, 'protect', side_effect=lambda value, decrypt=False: value):
            ai_settings.probe(self.path, {**self.draft, 'id': 'b', 'api_key': ''})
        self.assertEqual(opener.open.call_args.args[0].get_header('Authorization'), 'Bearer b')

    def test_save_preserves_key_but_endpoint_change_clears_it(self):
        self.path.write_text(json.dumps({'endpoint': self.draft['endpoint'], 'model': 'old', 'protected_key': 'eA=='}))
        draft = {**self.draft, 'id': 'default', 'name': 'Renamed', 'api_key': ''}
        self.assertTrue(ai_settings.save(self.path, draft)['has_key'])
        self.assertFalse(ai_settings.save(self.path, {**draft, 'endpoint': 'https://different.test/v1'})['has_key'])

    def test_saved_key_never_transferred_to_other_endpoint(self):
        self.path.write_text(json.dumps({'endpoint': 'https://old.test/v1', 'protected_key': 'secret'}))
        opener = self.response({'data': []})
        with patch.object(ai_settings, 'build_opener', return_value=opener), patch.object(ai_settings, 'protect') as decrypt:
            ai_settings.probe(self.path, {**self.draft, 'api_key': ''}, models=True)
        decrypt.assert_not_called()
        self.assertIsNone(opener.open.call_args.args[0].get_header('Authorization'))

    def test_saved_key_and_clear_key(self):
        self.path.write_text(json.dumps({'endpoint': self.draft['endpoint'], 'protected_key': 'eA=='}))
        for clear, expected in [(False, 'Bearer saved'), (True, None)]:
            opener = self.response({'data': []})
            with patch.object(ai_settings, 'build_opener', return_value=opener), patch.object(ai_settings, 'protect', return_value=b'saved'):
                ai_settings.probe(self.path, {**self.draft, 'api_key': '', 'clear_key': clear}, models=True)
            self.assertEqual(opener.open.call_args.args[0].get_header('Authorization'), expected)

    def test_provider_errors_do_not_expose_response_or_key(self):
        opener = MagicMock()
        opener.open.side_effect = HTTPError(self.draft['endpoint'], 401, 'draft-key', {}, None)
        with patch.object(ai_settings, 'build_opener', return_value=opener):
            with self.assertRaisesRegex(ValueError, 'HTTP 401') as error:
                ai_settings.probe(self.path, self.draft)
        self.assertNotIn('draft-key', str(error.exception))

    def test_invalid_response_and_remote_http(self):
        with patch.object(ai_settings, 'build_opener', return_value=self.response({'choices': []})):
            with self.assertRaisesRegex(ValueError, 'unexpected response'):
                ai_settings.probe(self.path, self.draft)
        with self.assertRaisesRegex(ValueError, 'HTTPS'):
            ai_settings.probe(self.path, {**self.draft, 'endpoint': 'http://example.test'})


if __name__ == '__main__':
    unittest.main()
