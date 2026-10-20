import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scenario_compiler import Compiler, References, ValidationError
from scenario_service import ScenarioService


def proposal():
    return {'reply': 'Review this linear increase in ylm for Iraq.', 'proposal': {
        'purpose': 'Increase Iraq baseline yield to twofold through ylm with a linear increase.',
        'regeneration_prompt': 'Use ylm for Iraq and increase linearly from the model base year to twice baseline in 2100.',
        'filename': 'Iraq.sce', 'entries': [{'parameter': 'ylm', 'targets': ['Iraq'],
            'ramp': {'start_value': 1, 'end_value': 2, 'end_year': 2100}}]}}


class ScenarioServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.refs = References({'ylm': (1, 0, 0), 'globalp': (0, 0, 0)}, {}, {'Iraq'})
        self.context = {'installation': 'fixture', 'version': 'test', 'base_year': 2022}
        self.replies = []
        self.seen = []
        def requester(settings, messages):
            self.seen.append((settings, list(messages)))
            return self.replies.pop(0)
        self.service = ScenarioService(self.root, lambda: 'fixture', requester)
        self.context_patch = patch.object(self.service, 'context', return_value=(self.refs, {'ylm': 'Agricultural yields multiplier'}, self.context, 'digest'))
        self.context_patch.start(); self.addCleanup(self.context_patch.stop)
        self.ai_patch = patch('scenario_service.ai_settings.load', return_value={
            'configured': True, 'endpoint': 'https://provider.example/v1', 'model': 'shared-model', 'api_key': 'test-key'})
        self.ai_patch.start(); self.addCleanup(self.ai_patch.stop)

    def answer(self, value):
        self.replies.append({'role': 'assistant', 'content': json.dumps(value)})

    def test_draft_review_export_and_comments(self):
        self.answer(proposal())
        reply = self.service.chat({'message': 'Double Iraq baseline yield by 2100.'})
        self.assertFalse((self.root/'scenarios').exists())
        row = reply['draft']['rows'][0]
        self.assertEqual((row['after'][0], row['after'][-1], len(row['after'])), ('1', '2', 79))
        self.assertEqual(self.seen[0][0]['model'], 'shared-model')
        saved = self.service.export({'session': reply['session'], 'draft': reply['draft']['id'], 'filename': 'Iraq.sce'})
        text = Path(saved['path']).read_text(encoding='utf-8')
        self.assertIn('COMMENT,START', text)
        self.assertIn('Parameters used: ylm.', text)
        self.assertNotIn('Structured specification', text)
        self.assertEqual(self.service.download(saved['download'].split('=')[1]), Path(saved['path']).read_bytes())
        with self.assertRaises(ValidationError):
            self.service.export({'session': reply['session'], 'draft': reply['draft']['id'], 'filename': 'Iraq.sce'})

    def test_metadata_tools_and_clarification(self):
        self.replies.append({'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': 'lookup', 'type': 'function', 'function': {'name': 'parameter_details', 'arguments': '{"parameter":"ylm"}'}}]})
        self.answer({'reply': 'Do you mean baseline yield or absolute yield?', 'proposal': None})
        result = self.service.chat({'message': 'Double yield.'})
        self.assertIsNone(result['draft'])
        self.assertEqual(json.loads(self.seen[-1][1][-1]['content'])['dimensions'], [1, 0, 0])

    def test_inspector_metadata_and_file_preview_do_not_export(self):
        plan = proposal()
        plan['proposal']['entries'].append({'parameter': 'globalp', 'targets': [], 'values': [1, 1.2, 1.4]})
        self.answer(plan)
        reply = self.service.chat({'message': 'Include a global input.'})
        self.assertEqual(reply['draft']['dimensions']['globalp'], (0, 0, 0))
        self.assertEqual(reply['draft']['rows'][1]['target_labels'], [])
        request = {'session': reply['session'], 'draft': reply['draft']['id']}
        preview = self.service.preview(request)
        self.assertIn('COMMENT,START', preview['text'])
        self.assertFalse((self.root/'scenarios').exists())
        with self.assertRaises(ValidationError): self.service.preview({**request, 'draft': 'stale'})

    def test_inspector_subgroup_labels_and_many_country_rows(self):
        countries = {f'Country {i}' for i in range(188)}
        refs = References({'first': (1, 2, 0), 'second': (1, 0, 0)}, {2: {1: 'Agriculture'}}, countries)
        entries = [{'parameter': name, 'targets': [country, 1] if name == 'first' else [country], 'values': [1, 2]}
                   for name in ('first', 'second') for country in sorted(countries)]
        plan = {**proposal()['proposal'], 'entries': entries}
        draft = self.service.prepare(Compiler(refs), None, plan, self.context)
        self.assertEqual(len(draft['review']['rows']), 376)
        self.assertEqual(draft['review']['dimensions']['first'], (1, 2, 0))
        self.assertEqual(draft['review']['rows'][0]['target_labels'][1], 'Agriculture')

    def test_attachment_modification_preserves_notes_and_other_rows(self):
        source = 'CUSTOM,ylm,Iraq,1,1,1\nCUSTOM,globalp,3,3,3\nCOMMENT,START\nOriginal "notes, verbatim.\n'
        plan = proposal()
        plan['proposal'].pop('entries')
        plan['proposal']['changes'] = [{'parameter': 'ylm', 'targets': ['Iraq'], 'start_year': 2023,
                                       'end_year': 2024, 'operation': 'multiply', 'value': 2}]
        self.answer(plan)
        reply = self.service.chat({'message': 'Double ylm in 2023–24.', 'source': {'name': 'Original.sce', 'text': source}})
        review = reply['draft']['rows']
        self.assertEqual(len(review), 1)
        self.assertEqual(review[0]['before'], ['1', '1', '1'])
        self.assertEqual(review[0]['after'], ['1', '2', '2'])
        saved = self.service.export({'session': reply['session'], 'draft': reply['draft']['id'], 'filename': 'Flavor.sce'})
        compiler = Compiler(self.refs)
        rows = compiler.read(saved['path'])
        self.assertEqual(rows[1], ['CUSTOM', 'globalp', '3', '3', '3'])
        self.assertIn('Original "notes, verbatim.', rows.comments)

    def test_invalid_parameter_and_missing_ai_fail_closed(self):
        plan = proposal(); plan['proposal']['entries'][0]['parameter'] = 'invented'
        self.answer(plan)
        with self.assertRaises(ValidationError): self.service.chat({'message': 'Do something.'})
        with patch('scenario_service.ai_settings.load', return_value={'configured': False}):
            with self.assertRaises(ValidationError): self.service.chat({'message': 'Do something.'})
        self.assertFalse((self.root/'scenarios').exists())

    def test_old_draft_and_changed_installation_cannot_export(self):
        self.answer(proposal()); reply = self.service.chat({'message': 'Double yield.'})
        with self.assertRaises(ValidationError):
            self.service.export({'session': reply['session'], 'draft': 'stale', 'filename': 'Iraq.sce'})
        with patch.object(self.service, 'context', return_value=(self.refs, {}, self.context, 'new-digest')):
            with self.assertRaises(ValidationError):
                self.service.export({'session': reply['session'], 'draft': reply['draft']['id'], 'filename': 'Iraq.sce'})
        self.answer({'reply': 'Please clarify.', 'proposal': None})
        self.service.chat({'session': reply['session'], 'message': 'Actually change something else.'})
        with self.assertRaises(ValidationError):
            self.service.export({'session': reply['session'], 'draft': reply['draft']['id'], 'filename': 'Iraq.sce'})

    def test_set_linear_and_path_rejection(self):
        plan = proposal(); plan['proposal'].pop('entries')
        plan['proposal']['changes'] = [{'parameter': 'ylm', 'targets': ['Iraq'], 'start_year': 2022,
            'end_year': 2024, 'operation': 'set_linear', 'start_value': 1, 'end_value': 2}]
        self.answer(plan)
        reply = self.service.chat({'message': 'Ramp.', 'source': {'name': 'Original.sce', 'text': 'CUSTOM,ylm,Iraq,1,1,1\n'}})
        self.assertEqual(reply['draft']['rows'][0]['after'], ['1', '1.5', '2'])
        for name in ('../escape.sce', 'CON.sce', 'file.exe'):
            with self.assertRaises(ValidationError):
                self.service.export({'session': reply['session'], 'draft': reply['draft']['id'], 'filename': name})


if __name__ == '__main__':
    unittest.main()
