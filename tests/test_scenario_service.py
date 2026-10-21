import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scenario_compiler import Compiler, References, ValidationError
from scenario_service import ScenarioService, expand_country_targets


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

    def chat(self, request):
        result = self.service.chat(request)
        if result.get('confirmation'):
            result = self.service.chat({'session': result['session'], 'confirmation': result['confirmation']['id']})
        return result

    def test_confirmation_required_before_preview_export_and_no_ai_on_confirm(self):
        self.answer(proposal())
        result = self.service.chat({'message': 'Double yield.'})
        self.assertIsNone(result['draft'])
        token = result['confirmation']['id']
        self.assertEqual(result['confirmation']['geographies'][0]['countries'], ['Iraq'])
        request = {'session': result['session'], 'draft': token, 'filename': 'Iraq.sce'}
        with self.assertRaises(ValidationError): self.service.preview(request)
        with self.assertRaises(ValidationError): self.service.export(request)
        with self.assertRaises(ValidationError): self.service.chat({'session': result['session'], 'confirmation': 'wrong'})
        confirmed = self.service.chat({'session': result['session'], 'confirmation': token})
        self.assertIsNotNone(confirmed['draft'])
        self.assertEqual(len(self.seen), 1)
        with self.assertRaises(ValidationError): self.service.chat({'session': result['session'], 'confirmation': token})

    def test_revision_and_installation_change_invalidate_confirmation(self):
        self.answer(proposal())
        result = self.service.chat({'message': 'Double yield.'})
        request = {'session': result['session'], 'confirmation': result['confirmation']['id']}
        with patch.object(self.service, 'context', return_value=(self.refs, {}, self.context, 'changed')):
            with self.assertRaises(ValidationError): self.service.chat(request)
        self.answer({'reply': 'What should change?', 'proposal': None})
        self.service.chat({'session': result['session'], 'message': 'Revise this.'})
        with self.assertRaises(ValidationError): self.service.chat(request)

    def test_preset_lookup_and_server_expansion(self):
        self.refs.countries.add('Jordan')
        self.refs.country_groups['42'] = {'id': '42', 'name': 'Example preset', 'long_name': '',
            'alias': 'Middle East', 'countries': ['Iraq', 'Jordan'], 'invalid_members': []}
        for name, args in [('search_country_groups', {'query': 'Middle East'}), ('country_group_details', {'id': '42'})]:
            self.replies.append({'role': 'assistant', 'content': None, 'tool_calls': [
                {'id': name, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}]})
        plan = proposal(); plan['proposal']['entries'][0]['targets'] = [{'country_group': '42'}]
        self.answer(plan)
        pending = self.service.chat({'message': 'Use Middle East.'})
        self.assertEqual(pending['confirmation']['geographies'][0]['countries'], ['Iraq', 'Jordan'])
        result = self.service.chat({'session': pending['session'], 'confirmation': pending['confirmation']['id']})
        self.assertEqual([r['targets'] for r in result['draft']['rows']], [['Iraq'], ['Jordan']])
        self.assertEqual(json.loads(self.seen[1][1][-1]['content'])['matches'][0]['id'], '42')

    def test_custom_country_validation_and_subgroup_preservation(self):
        self.refs.parameters['sector'] = (1, 2, 0)
        item = {'parameter': 'sector', 'targets': [{'countries': ['Iraq'], 'label': 'Custom scope'}, 7], 'values': [1]}
        expanded, scopes = expand_country_targets([item], self.refs)
        self.assertEqual(expanded[0]['targets'], ['Iraq', 7])
        self.assertIn('Custom', scopes[0]['kind'])
        for countries in (['Atlantis'], ['iraq'], ['Iraq', 'Iraq'], []):
            with self.assertRaises(ValidationError):
                expand_country_targets([{**item, 'targets': [{'countries': countries, 'label': 'Custom'}]}], self.refs)
        with self.assertRaises(ValidationError):
            expand_country_targets([{**item, 'parameter': 'globalp'}], self.refs)
        with self.assertRaises(ValidationError):
            expand_country_targets([{**item, 'targets': [{'country_group': 'invented'}]}], self.refs)

    def test_draft_review_export_and_comments(self):
        self.answer(proposal())
        reply = self.chat({'message': 'Double Iraq baseline yield by 2100.'})
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
        result = self.chat({'message': 'Double yield.'})
        self.assertIsNone(result['draft'])
        self.assertEqual(json.loads(self.seen[-1][1][-1]['content'])['dimensions'], [1, 0, 0])

    def test_many_parameter_lookups_in_one_response(self):
        names = ['democm', 'democpolyarchym', 'govcorruptm', 'ginidomm', 'goveffectm',
                 'tradeexportdvadm', 'gdsm', 'migrateoutm', 'migrateinm', 'govnucwepadd']
        self.refs.parameters.update({name: (1, 0, 0) for name in names})
        self.replies.append({'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': str(i), 'type': 'function', 'function': {'name': 'parameter_details',
                'arguments': json.dumps({'parameter': name})}} for i, name in enumerate(names)]})
        self.answer({'reply': 'What years and adjustment magnitudes should these changes use?', 'proposal': None})
        result = self.service.chat({'message': 'Create a Divided World scenario with these parameters.'})
        self.assertIsNone(result['draft'])
        results = [m for m in self.seen[-1][1] if m['role'] == 'tool']
        self.assertEqual(len(results), 10)
        self.assertTrue(all('error' not in json.loads(m['content']) for m in results))

    def metadata(self, calls):
        self.replies.append({'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': str(i), 'type': 'function', 'function': {'name': name,
                'arguments': json.dumps(args)}} for i, (name, args) in enumerate(calls)]})

    def test_large_batch_has_no_old_call_limit_and_duplicate_lookups_are_cached(self):
        names = ['parameter'+str(i) for i in range(150)]
        self.refs.parameters.update({name: (1, 0, 0) for name in names})
        self.metadata([('parameter_details', {'parameter': name}) for name in names] * 2)
        self.answer({'reply': 'Which years?', 'proposal': None})
        with patch.object(self.service, 'lookup', wraps=self.service.lookup) as lookup:
            result = self.service.chat({'message': 'Inspect many parameters.'})
            self.assertEqual(lookup.call_count, 150)
        self.assertIsNone(result['draft'])
        tools = [m for m in self.seen[-1][1] if m['role'] == 'tool']
        self.assertEqual(len(tools), 300)
        self.assertFalse(any('error' in json.loads(m['content']) for m in tools))

    def repeated_pause(self):
        for _ in range(4): self.metadata([('parameter_details', {'parameter': 'ylm'})])
        return self.service.chat({'message': 'Double baseline yield for Iraq by 2100.'})

    def test_repeated_cycles_pause_then_continue_preserves_progress(self):
        with patch.object(self.service, 'lookup', wraps=self.service.lookup) as lookup:
            paused = self.repeated_pause()
            self.assertEqual(lookup.call_count, 1)
        self.assertEqual(paused['research']['reason'], 'repeated')
        self.assertEqual(paused['research']['cache_hits'], 3)
        self.assertIsNone(paused['draft'])
        self.assertFalse((self.root/'scenarios').exists())
        self.answer(proposal())
        request = {'session': paused['session'], 'continue_research': paused['research']['id']}
        result = self.service.chat(request)
        self.assertIsNotNone(result['confirmation'])
        messages = self.seen[-1][1]
        self.assertTrue(any('Double baseline yield' in (m.get('content') or '') for m in messages))
        self.assertEqual(sum(m['role'] == 'tool' for m in messages), 4)
        with self.assertRaises(ValidationError): self.service.chat(request)

    def test_round_checkpoint_is_resumable_and_can_be_revised(self):
        for query in ('yield', 'agriculture'): self.metadata([('search_parameters', {'query': query})])
        with patch('scenario_service.MAX_METADATA_ROUNDS', 2):
            paused = self.service.chat({'message': 'Research yield changes.'})
        self.assertEqual(paused['research']['reason'], 'rounds')
        self.answer({'reply': 'Which years should I use?', 'proposal': None})
        self.service.chat({'session': paused['session'], 'message': 'Use 2100 and only Iraq.'})
        messages = self.seen[-1][1]
        self.assertTrue(any(m.get('content') == 'Research yield changes.' for m in messages))
        self.assertEqual(messages[-1]['content'], 'Use 2100 and only Iraq.')
        self.assertEqual(sum(m['role'] == 'tool' for m in messages), 2)
        with self.assertRaises(ValidationError):
            self.service.chat({'session': paused['session'], 'continue_research': paused['research']['id']})

    def test_provider_failure_and_stop_keep_research(self):
        self.metadata([('parameter_details', {'parameter': 'ylm'})])
        original = self.service.requester
        count = 0
        def failing(settings, messages):
            nonlocal count
            count += 1
            if count == 2: raise ValidationError('AI request timed out.')
            return original(settings, messages)
        self.service.requester = failing
        paused = self.service.chat({'message': 'Inspect Iraq yield.'})
        self.assertEqual(paused['research']['reason'], 'provider')
        self.assertEqual(paused['research']['lookups'], 1)
        def stopping(settings, messages):
            self.service.cancel()
            return {'role': 'assistant', 'content': json.dumps(proposal())}
        self.service.requester = stopping
        stopped = self.service.chat({'session': paused['session'], 'continue_research': paused['research']['id']})
        self.assertEqual(stopped['research']['reason'], 'stopped')
        self.service.requester = original
        self.answer(proposal())
        resumed = self.service.chat({'session': stopped['session'], 'continue_research': stopped['research']['id']})
        self.assertIsNotNone(resumed['confirmation'])
        self.assertTrue(any(m['role'] == 'tool' for m in self.seen[-1][1]))

    def test_changed_installation_blocks_research_resume(self):
        paused = self.repeated_pause()
        with patch.object(self.service, 'context', return_value=(self.refs, {}, self.context, 'changed')):
            with self.assertRaises(ValidationError):
                self.service.chat({'session': paused['session'], 'continue_research': paused['research']['id']})

    def test_attachment_and_lookup_results_survive_pause(self):
        for _ in range(4): self.metadata([('source_rows', {'parameter': 'ylm'})])
        source = {'name': 'Original.sce', 'text': 'CUSTOM,ylm,Iraq,1,1,1\n'}
        paused = self.service.chat({'message': 'Inspect this attachment.', 'source': source})
        self.answer({'reply': 'The original values are unchanged. Which adjustment do you want?', 'proposal': None})
        result = self.service.chat({'session': paused['session'], 'continue_research': paused['research']['id']})
        self.assertIsNone(result['draft'])
        rows = [json.loads(m['content'])['rows'] for m in self.seen[-1][1] if m['role'] == 'tool']
        self.assertEqual(rows[0], [['CUSTOM', 'ylm', 'Iraq', '1', '1', '1']])
        self.assertEqual(self.service.sessions[result['session']]['source'].source, 'Original.sce')

    def test_context_compaction_preserves_full_local_transcript(self):
        messages = [{'role': 'system', 'content': 'Instructions'}, {'role': 'user', 'content': 'Inspect the scenario.'},
                    {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'huge'}]},
                    {'role': 'tool', 'tool_call_id': 'huge', 'content': 'x'*300001}]
        compact = self.service.compact_metadata(messages)
        self.assertLess(len(json.dumps(compact)), 240000)
        self.assertEqual(len(messages[-1]['content']), 300001)
        self.assertIn('Inspect the scenario.', json.dumps(compact))

    def test_inspector_metadata_and_file_preview_do_not_export(self):
        plan = proposal()
        plan['proposal']['entries'].append({'parameter': 'globalp', 'targets': [], 'values': [1, 1.2, 1.4]})
        self.answer(plan)
        reply = self.chat({'message': 'Include a global input.'})
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
        reply = self.chat({'message': 'Double ylm in 2023–24.', 'source': {'name': 'Original.sce', 'text': source}})
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
        with self.assertRaises(ValidationError): self.chat({'message': 'Do something.'})
        with patch('scenario_service.ai_settings.load', return_value={'configured': False}):
            with self.assertRaises(ValidationError): self.chat({'message': 'Do something.'})
        self.assertFalse((self.root/'scenarios').exists())

    def test_old_draft_and_changed_installation_cannot_export(self):
        self.answer(proposal()); reply = self.chat({'message': 'Double yield.'})
        with self.assertRaises(ValidationError):
            self.service.export({'session': reply['session'], 'draft': 'stale', 'filename': 'Iraq.sce'})
        with patch.object(self.service, 'context', return_value=(self.refs, {}, self.context, 'new-digest')):
            with self.assertRaises(ValidationError):
                self.service.export({'session': reply['session'], 'draft': reply['draft']['id'], 'filename': 'Iraq.sce'})
        self.answer({'reply': 'Please clarify.', 'proposal': None})
        self.chat({'session': reply['session'], 'message': 'Actually change something else.'})
        with self.assertRaises(ValidationError):
            self.service.export({'session': reply['session'], 'draft': reply['draft']['id'], 'filename': 'Iraq.sce'})

    def test_set_linear_and_path_rejection(self):
        plan = proposal(); plan['proposal'].pop('entries')
        plan['proposal']['changes'] = [{'parameter': 'ylm', 'targets': ['Iraq'], 'start_year': 2022,
            'end_year': 2024, 'operation': 'set_linear', 'start_value': 1, 'end_value': 2}]
        self.answer(plan)
        reply = self.chat({'message': 'Ramp.', 'source': {'name': 'Original.sce', 'text': 'CUSTOM,ylm,Iraq,1,1,1\n'}})
        self.assertEqual(reply['draft']['rows'][0]['after'], ['1', '1.5', '2'])
        for name in ('../escape.sce', 'CON.sce', 'file.exe'):
            with self.assertRaises(ValidationError):
                self.service.export({'session': reply['session'], 'draft': reply['draft']['id'], 'filename': name})


if __name__ == '__main__':
    unittest.main()
