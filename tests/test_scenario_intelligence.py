import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from scenario_compiler import References, Compiler, ValidationError
from scenario_intelligence import Baseline, preset_entry, details, semantic_entries, compact_groups, expand_native_source
from scenario_intelligence import decoder_path
from scenario_service import ScenarioService, ScenarioConflict, expand_country_targets, TOOLS


class IntelligenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root/'RUNFILES').mkdir()
        (self.root/'RUNFILES/IFsBase.run.db').touch()
        self.refs = References({'govcorruptm': (1,0,0), 'gdsm': (1,9,0), 'govnucwpadd': (1,0,0)},
            {1: {1:'Iraq',2:'Jordan'}, 9:{1:'Military'}}, {'Iraq','Jordan'},
            {'42': {'id':'42','name':'World','countries':['Iraq','Jordan'],'invalid_members':[]}},
            {'gdsm': {'MINIMUM':0.01,'MAXIMUM':2,'SHIFT UP':0.2,'SHIFT DOWN':-0.2,'SHIFT YEARS':10,'AGGREGATION':'AVG'},
             'govcorruptm': {'AGGREGATION':'POP','MINIMUM':0.01,'MAXIMUM':5},
             'GOVCORRUPT': {'DEFINITION':'Higher is less corrupt'},
             'govnucwpadd': {'AGGREGATION':'SUM','MINIMUM':-10000,'MAXIMUM':10000}}, str(self.root))
        self.compiler = Compiler(self.refs)
        self.context = {'version':'fixture','base_year':2022,'installation':str(self.root)}
        self.service = ScenarioService(self.root, lambda:self.root)
        self.frames = {'gdsm': ([0,1,9], {(y,i,1):float(i)/2 for y in range(2022,2051) for i in (1,2)}),
                       'govcorruptm': ([0,1], {(y,i):1.0 for y in range(2022,2051) for i in (1,2)})}
        self.decode = patch('scenario_intelligence.decoded', side_effect=lambda p,s,n,d:self.frames[n])
        self.decode.start();self.addCleanup(self.decode.stop)
        self.decoder = patch('scenario_intelligence.decoder_path', return_value=Path('test-decoder'))
        self.decoder.start();self.addCleanup(self.decoder.stop)

    def effect(self, direction, quantity='parameter_input', outcome=''):
        return {'direction':direction,'quantity':quantity,'outcome':outcome}

    def test_defaults_use_country_baseline_instead_of_assuming_one(self):
        baseline = Baseline(self.refs,2022)
        results = [preset_entry({'parameter':'gdsm','targets':[c,1],
            'preset':{'level':'high','hold_until':2050}},self.refs,baseline)[0] for c in ('Iraq','Jordan')]
        self.assertEqual([Decimal(r['values'][0]) for r in results], [Decimal('.5'),Decimal('1')])
        self.assertEqual([Decimal(r['values'][-1]) for r in results], [Decimal('.7'),Decimal('1.2')])
        self.assertEqual(Decimal(results[0]['values'][10]),Decimal('.7'))
        low,_ = preset_entry({'parameter':'gdsm','targets':['Iraq',1],'preset':{'level':'low'}},self.refs,baseline)
        self.assertEqual(Decimal(low['values'][-1]),Decimal('.3'))

    def test_defaults_clip_bounds_and_missing_settings_do_not_get_invented(self):
        self.refs.metadata['gdsm']['SHIFT UP'] = 20
        result,_ = preset_entry({'parameter':'gdsm','targets':['Iraq',1],'preset':{'level':'high'}},self.refs,Baseline(self.refs,2022))
        self.assertEqual(Decimal(result['values'][-1]),2)
        with self.assertRaisesRegex(ValidationError,'does not supply'):
            preset_entry({'parameter':'govcorruptm','targets':['Iraq'],'preset':{'level':'high'}},self.refs,Baseline(self.refs,2022))
        self.refs.metadata['gdsm']['SHIFT YEARS'] = ''
        with self.assertRaisesRegex(ValidationError,'duration'):
            preset_entry({'parameter':'gdsm','targets':['Iraq',1],'preset':{'level':'high'}},self.refs,Baseline(self.refs,2022))

    def test_base_preserves_varying_baseline_not_flat_first_value(self):
        self.frames['gdsm'][1][(2023,1,1)] = .6
        result,_ = preset_entry({'parameter':'gdsm','targets':['Iraq',1],
            'preset':{'level':'base','hold_until':2023}},self.refs,Baseline(self.refs,2022))
        self.assertEqual(list(map(Decimal,result['values'])), [Decimal('.5'),Decimal('.6')])

    def test_world_at_war_corruption_inverse_is_blocked_even_if_ai_mislabels_it(self):
        entry = {'parameter':'govcorruptm','targets':['Iraq'],'values':[1,1.25], 'effect':self.effect('decrease')}
        with self.assertRaisesRegex(ValidationError,'Direction conflict'):
            semantic_entries([entry],self.refs,'The world has more corruption.')
        entry['values'] = [1,.9];entry['effect'] = self.effect('increase')
        result,receipt = semantic_entries([entry],self.refs,'The world has more corruption.')
        self.assertTrue(receipt[0]['verified'])
        self.assertEqual(details(self.refs,'govcorruptm')['semantic_rule']['affected_definition'],'Higher is less corrupt')

    def test_world_at_war_nuclear_cumulative_stock_stops_annual_additions(self):
        entry = {'parameter':'govnucwpadd','targets':['Iraq'],'values':[0,5,10,20,20,20],
                 'effect':self.effect('increase','cumulative_addition')}
        results,_ = semantic_entries([entry],self.refs)
        self.assertEqual(list(map(Decimal,results[0]['values'])),[0,5,5,10,0,0])
        self.assertEqual(sum(map(Decimal,results[0]['values'])),20)
        entry['effect'] = self.effect('increase')
        with self.assertRaisesRegex(ValidationError,'annual addition'):semantic_entries([entry],self.refs)

    def test_common_group_writes_one_record_and_reopens_as_country_rows(self):
        rows = self.compiler.build([{'parameter':'govcorruptm','targets':[c],'values':[1,.9]} for c in ('Iraq','Jordan')])
        exported,receipt = compact_groups(rows,self.refs,Baseline(self.refs,2022),[{'id':'42'}])
        self.assertEqual(len(exported),1)
        self.assertEqual(exported[0][2],'World')
        self.assertTrue(receipt[0]['native_group'])
        expanded = expand_native_source(exported,self.refs,Baseline(self.refs,2022))
        self.assertEqual(expanded,rows)

    def test_different_country_baselines_do_not_get_native_group_allocation(self):
        rows = self.compiler.build([{'parameter':'gdsm','targets':[c,1],'values':[1,1.2]} for c in ('Iraq','Jordan')])
        exported,receipt = compact_groups(rows,self.refs,Baseline(self.refs,2022),[{'id':'42'}])
        self.assertEqual(len(exported),2)
        self.assertIn('baselines differ',receipt[0]['reason'])

    def test_country_specific_values_common_targets_and_sum_controls_stay_explicit(self):
        rows = self.compiler.build([{'parameter':'govcorruptm','targets':['Iraq'],'values':[1,.9]},
                                    {'parameter':'govcorruptm','targets':['Jordan'],'values':[1,.8]}])
        self.assertEqual(len(compact_groups(rows,self.refs,Baseline(self.refs,2022),[{'id':'42'}])[0]),2)
        rows[1][-1] = '.9';self.refs.metadata['govcorruptm']['COMMONTARGET'] = 1
        self.assertEqual(len(compact_groups(rows,self.refs,Baseline(self.refs,2022),[{'id':'42'}])[0]),2)
        rows = self.compiler.build([{'parameter':'govnucwpadd','targets':[c],'values':[0,20]} for c in ('Iraq','Jordan')])
        self.assertEqual(len(compact_groups(rows,self.refs,Baseline(self.refs,2022),[{'id':'42'}])[0]),2)

    def test_literal_native_group_is_expanded_for_validation(self):
        entries,scopes = expand_country_targets([{'parameter':'govcorruptm','targets':['World'],'values':[1,.9]}],self.refs)
        self.assertEqual([r['targets'] for r in entries],[['Iraq'],['Jordan']])
        self.assertEqual(scopes[0]['id'],'42')

    def test_combined_presets_semantics_and_group_writing(self):
        # This baseline is deliberately different by country: IFs high must retain that difference.
        proposal = {'purpose':'Increase military spending using IFs high and increase corruption.',
            'regeneration_prompt':'Use IFs high military spending and a lower corruption-perception multiplier for World.',
            'entries':[{'parameter':'gdsm','targets':[{'country_group':'42'},1],
                        'preset':{'level':'high','hold_until':2035},'effect':self.effect('increase')},
                       {'parameter':'govcorruptm','targets':[{'country_group':'42'}],
                        'ramp':{'start_value':1,'end_value':.9,'end_year':2035},'effect':self.effect('increase')}]}
        draft = self.service.prepare(self.compiler,None,proposal,self.context,'More corruption and higher military spending.')
        self.assertEqual(len(draft['review']['rows']),4)
        self.assertEqual(len(draft['rows']),3)
        self.assertEqual(len(draft['review']['presets']),2)
        self.assertTrue(any(r[2]=='World' for r in draft['rows']))
        proposal['entries'][1]['ramp']['end_value'] = 1.25
        with self.assertRaisesRegex(ScenarioConflict,'Semantic check'):
            self.service.prepare(self.compiler,None,proposal,self.context,'More corruption.')

    def test_missing_effect_and_military_headcount_proxy_are_not_silently_accepted(self):
        with self.assertRaisesRegex(ValidationError,'intended outcome'):
            semantic_entries([{'parameter':'govcorruptm','values':[1,.9]}],self.refs)
        with self.assertRaisesRegex(ValidationError,'not nuclear'):
            semantic_entries([{'parameter':'cpowf','values':[1,1.2],
                'effect':self.effect('increase',outcome='military personnel')}],self.refs)

    def test_baseline_dimension_and_missing_coordinates_fail_closed(self):
        with self.assertRaisesRegex(ValidationError,'no saved value'):
            Baseline(self.refs,2022).value('gdsm',['Iraq',1],2100)
        self.frames['gdsm'] = ([0,1], {})
        with self.assertRaisesRegex(ValidationError,'dimensions differ'):
            Baseline(self.refs,2022).value('gdsm',['Iraq',1])

    def test_packaged_core_decoder_location(self):
        core = self.root/'packaged-core'
        decoder = core/'engine/decoder-runtime/Decoder.exe'
        decoder.parent.mkdir(parents=True)
        decoder.touch()
        # Use the original implementation, not the fixture decoder override.
        self.decoder.stop()
        with patch.dict('os.environ', {'IFS_COMPANION_APP_DIR':str(core)}):
            self.assertEqual(decoder_path(),decoder)
        self.decoder.start()

    def test_all_sector_selector_expands_before_baseline_lookup(self):
        self.refs.groups[9][2] = 'Health';self.refs.groups[9][3] = 'ALL'
        entries,_ = expand_country_targets([{'parameter':'gdsm','targets':[{'country_group':'42'},3],
                                             'preset':{'level':'high'}}],self.refs)
        self.assertEqual({tuple(e['targets']) for e in entries},
                         {('Iraq',1),('Iraq',2),('Jordan',1),('Jordan',2)})

    def test_ai_cannot_spoof_an_internal_baseline_reference(self):
        with self.assertRaisesRegex(ValidationError,'Direction conflict'):
            semantic_entries([{'parameter':'govcorruptm','values':[1,1.25], '_reference':[1.5,1.5],
                'effect':self.effect('increase')}],self.refs,'More corruption.')

    def test_direction_uses_actual_baseline_not_a_misleading_start_value(self):
        plan = {'purpose':'Increase corruption through the perception index.',
                'regeneration_prompt':'More corruption through govcorruptm.',
                'entries':[{'parameter':'govcorruptm','targets':['Iraq'],'values':[1.5,1.25],
                            'effect':self.effect('increase')}]}
        with self.assertRaisesRegex(ScenarioConflict,'Direction conflict'):
            self.service.prepare(self.compiler,None,plan,self.context,'More corruption.')

    def test_group_with_missing_baseline_cannot_be_silently_flattened(self):
        rows = self.compiler.build([{'parameter':'govcorruptm','targets':['World'],'values':[1,.9]}])
        self.frames['govcorruptm'][1].pop((2023,2))
        with self.assertRaisesRegex(ValidationError,'no saved value'):
            expand_native_source(rows,self.refs,Baseline(self.refs,2022))

    def test_narrative_direction_overrides_wrong_declared_effect(self):
        for parameter, phrase in [('goveffectm','Less government effectiveness.'),
                                  ('democm','Democratic regression.'),
                                  ('ginidomm','Less income inequality.'),
                                  ('xsm','Reduced global exports.')]:
            with self.subTest(parameter=parameter):
                with self.assertRaisesRegex(ValidationError,'Direction conflict'):
                    semantic_entries([{'parameter':parameter,'values':[1,1.2],
                                       'effect':self.effect('increase')}],self.refs,phrase)

    def test_provider_tool_arrays_have_item_schemas(self):
        def check(node):
            if isinstance(node,dict):
                if node.get('type') == 'array':self.assertIn('items',node)
                for value in node.values():check(value)
            elif isinstance(node,list):
                for value in node:check(value)
        check(TOOLS)
