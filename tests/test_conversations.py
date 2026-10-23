import tempfile
import json
import threading
import unittest
from unittest.mock import patch
from conversations import Conversations


class ConversationTests(unittest.TestCase):
    @staticmethod
    def lookup(index, query=None):
        return {'role':'assistant','content':None,'tool_calls':[{'id':'lookup-'+str(index),'type':'function',
            'function':{'name':'knowledge','arguments':json.dumps({'query':query or str(index)})}}]}

    def test_scenario_after_64_rounds_returns_without_outer_reinterpretation(self):
        replies=[self.lookup(i) for i in range(64)]
        replies.append({'role':'assistant','content':None,'tool_calls':[{'id':'build','type':'function','function':{'name':'scenario','arguments':'{"message":"Build the agreed scenario"}'}}]})
        iterator=iter(replies);self.service.requester=lambda *args:next(iterator)
        self.service.operation=lambda name,args,owner:({'reply':'Review the validated scope.'},{'kind':'scenario','id':'ifs-scenario-builder'}) if name=='scenario' else ({'evidence':args['query']},None)
        chat=self.service.send(self.service.create()['id'],'Build a complex scenario')
        self.assertEqual(chat['messages'][-1]['content'],'Review the validated scope.')
        self.assertEqual(chat['messages'][-1]['links'][0]['kind'],'scenario')
        self.assertIsNone(chat['research'])

    def test_checkpoint_survives_restart_and_continues_original_tool_context(self):
        owner=self.service.create()['id'];index=iter(range(3))
        def request(*args):
            i=next(index)
            if i==2:raise ValueError('Provider disconnected')
            return self.lookup(i)
        self.service.requester=request
        self.service.operation=lambda name,args,owner:({'evidence':args['query']},None)
        paused=self.service.send(owner,'Original request')
        self.assertEqual(paused['research']['reason'],'connection')
        restored=Conversations(self.folder.name,lambda:self.installation,self.service.operation)
        def resume(settings,messages,tools):
            self.assertEqual(messages[-1]['role'],'tool')
            self.assertEqual(json.loads(messages[-1]['content']),{'evidence':'1'})
            self.assertIn('Original request',[m.get('content') for m in messages])
            return {'role':'assistant','content':'Completed with prior research'}
        restored.requester=resume
        result=restored.send(owner,continue_research=paused['research']['id'])
        self.assertIsNone(result['research'])
        self.assertEqual(result['messages'][-1]['content'],'Completed with prior research')
        self.assertEqual(sum(m['role']=='user' for m in result['messages']),1)
        with self.assertRaisesRegex(ValueError,'expired'):restored.send(owner,continue_research=paused['research']['id'])

    def test_repeated_lookups_are_cached_and_pause_without_losing_results(self):
        calls=[];self.service.operation=lambda name,args,owner:(calls.append(args) or ({'evidence':'saved'},None))
        self.service.requester=lambda *args:self.lookup(1,'same query')
        paused=self.service.send(self.service.create()['id'],'Research')
        self.assertEqual(calls,[{'query':'same query'}])
        self.assertEqual(paused['research']['reason'],'repeated')
        self.assertEqual(paused['research']['rounds'],4)
        self.service.requester=lambda *args:{'role':'assistant','content':'Done'}
        self.service.send(paused['id'],continue_research=paused['research']['id'])
        self.assertEqual(len(calls),1)

    def test_different_queries_with_identical_results_are_not_progress(self):
        queries=iter(range(10));self.service.requester=lambda *args:self.lookup(next(queries))
        calls=[];self.service.operation=lambda *args:(calls.append(args) or ({'matches':[]},None))
        paused=self.service.send(self.service.create()['id'],'Research')
        self.assertEqual(paused['research']['reason'],'repeated')
        self.assertEqual(len(calls),4)

    def test_stop_can_resume_without_reexecuting_completed_lookups(self):
        owner=self.service.create()['id'];count=0
        def request(*args):
            nonlocal count
            count+=1
            if count==2:self.service.stop(owner)
            return self.lookup(count)
        self.service.requester=request;calls=[]
        self.service.operation=lambda *args:(calls.append(args) or ({'evidence':'saved'},None))
        paused=self.service.send(owner,'Research')
        self.assertEqual(paused['research']['reason'],'stopped')
        self.service.requester=lambda *args:{'role':'assistant','content':'Done'}
        result=self.service.send(owner,continue_research=paused['research']['id'])
        self.assertEqual(len(calls),1);self.assertIsNone(result['research'])

    def test_large_lookup_batch_is_accepted(self):
        batch={'role':'assistant','content':None,'tool_calls':[self.lookup(i)['tool_calls'][0] for i in range(20)]}
        replies=iter([batch,{'role':'assistant','content':'Done'}]);self.service.requester=lambda *args:next(replies)
        calls=[];self.service.operation=lambda name,args,owner:(calls.append(args) or ({'evidence':args['query']},None))
        chat=self.service.send(self.service.create()['id'],'Many lookups')
        self.assertEqual(len(calls),20);self.assertIsNone(chat['research'])

    def test_provider_failure_keeps_completed_tools_and_resumes(self):
        responses=iter([self.lookup(1),None]);calls=[]
        def request(*args):
            response=next(responses)
            if response is None:raise ValueError('Provider timed out')
            return response
        self.service.requester=request;self.service.operation=lambda *args:(calls.append(args) or ({'evidence':'known'},None))
        paused=self.service.send(self.service.create()['id'],'Question')
        self.assertEqual(paused['research']['reason'],'connection')
        self.service.requester=lambda *args:{'role':'assistant','content':'Recovered'}
        result=self.service.send(paused['id'],continue_research=paused['research']['id'])
        self.assertEqual(len(calls),1);self.assertIsNone(result['research'])

    def test_checkpoint_is_chat_scoped_and_revision_invalidates_it(self):
        self.service.requester=lambda *args:self.lookup(1)
        paused=self.service.send(self.service.create()['id'],'Question')
        other=self.service.create()['id']
        with self.assertRaisesRegex(ValueError,'expired'):self.service.send(other,continue_research=paused['research']['id'])
        self.service.requester=lambda *args:{'role':'assistant','content':'Revised answer'}
        self.service.send(paused['id'],'Revised request')
        with self.assertRaisesRegex(ValueError,'expired'):self.service.send(paused['id'],continue_research=paused['research']['id'])

    def test_changed_connection_rejects_continue_but_keeps_checkpoint(self):
        self.service.requester=lambda *args:self.lookup(1)
        paused=self.service.send(self.service.create()['id'],'Question')
        with patch('conversations.ai_settings.load',return_value={'configured':True,'model':'different'}):
            with self.assertRaisesRegex(ValueError,'connection changed'):self.service.send(paused['id'],continue_research=paused['research']['id'])
        self.assertEqual(self.service.read(paused['id'])['research'],paused['research'])

    def test_attachment_uses_scenario_backend_and_keeps_main_chat_history(self):
        calls=[]
        self.service.operation=lambda name,args,owner:(calls.append((name,args,owner)) or ({'reply':'Reviewed attachment.'},{'kind':'scenario','id':'ifs-scenario-builder','context':{'session':'owned'}}))
        self.service.requester=lambda *args:self.fail('Attachment must go directly to the validated scenario backend')
        owner=self.service.create()['id'];source={'name':'Policy.sce','text':'CUSTOM,ylm,Kenya,1,2\n'}
        chat=self.service.send(owner,'Explain this file',source=source)
        self.assertEqual(calls,[('scenario',{'message':'Explain this file','source':source},owner)])
        self.assertIn('Policy.sce',chat['messages'][0]['content'])
        self.assertEqual(chat['messages'][-1]['content'],'Reviewed attachment.')
        self.assertEqual(chat['messages'][-1]['links'][0]['kind'],'scenario')
        self.assertFalse(self.service.busy())

    def test_invalid_attachment_is_rejected_without_history_or_backend_calls(self):
        owner=self.service.create()['id']
        self.service.operation=lambda *args:self.fail('Invalid attachment reached backend')
        for source in ({'name':'bad.txt','text':'x'},{'name':'big.sce','text':'x'*1_000_001}):
            with self.assertRaises(ValueError):self.service.send(owner,'Inspect',source=source)
        self.assertEqual(self.service.read(owner)['messages'],[])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.installation = 'test-installation'
        self.service = Conversations(self.folder.name, lambda:self.installation, lambda name,args,identity:({'ok':True},None),
                                     requester=lambda *args:{'role':'assistant','content':'Answer'})
        self.settings = patch('conversations.ai_settings.load', return_value={'configured':True})
        self.settings.start()

    def tearDown(self):
        self.settings.stop()
        self.folder.cleanup()

    def test_history_survives_restart_and_does_not_mix_chats(self):
        a=self.service.create()['id'];b=self.service.create()['id']
        self.service.send(a,'Question A')
        restored=Conversations(self.folder.name,lambda:self.installation,None)
        self.assertEqual([m['content'] for m in restored.read(a)['messages']],['Question A','Answer'])
        self.assertEqual(restored.read(b)['messages'],[])
        self.assertFalse(self.service.busy())

    def test_recents_rank_continued_tasks_but_not_opened_tasks(self):
        a=self.service.create()['id'];b=self.service.create()['id']
        self.assertEqual(self.service.list()['chats'],[])
        self.service.send(a,'First task')
        self.service.send(b,'Second task')
        self.assertEqual([c['id'] for c in self.service.list()['chats']],[b,a])
        before=self.service.read(a)['updated']
        self.service.read(a)
        self.service.touch(a)
        self.assertEqual(self.service.read(a)['updated'],before)
        self.assertEqual([c['id'] for c in self.service.list()['chats']],[b,a])
        self.service.send(a,'Continue the first task')
        self.assertEqual([c['id'] for c in self.service.list()['chats']],[a,b])

    def test_installation_change_rejects_existing_chat(self):
        identity=self.service.create()['id'];self.installation='different'
        with self.assertRaisesRegex(ValueError,'installation changed'):self.service.send(identity,'Question')
        self.assertEqual(self.service.read(identity)['messages'],[])

    def test_cancel_is_isolated_and_other_chat_can_respond(self):
        entered=threading.Event();release=threading.Event()
        def request(settings,messages,tools):
            if messages[-1]['content']=='slow':entered.set();release.wait(4)
            return {'role':'assistant','content':'Answer'}
        self.service.requester=request
        a=self.service.create()['id'];b=self.service.create()['id']
        thread=threading.Thread(target=self.service.send,args=(a,'slow'))
        thread.start()
        try:
            self.assertTrue(entered.wait(2));self.service.stop(a)
            self.service.send(b,'fast')
        finally:release.set();thread.join(5)
        self.assertEqual(self.service.read(a)['messages'][-1]['content'],'Stopped.')
        self.assertEqual(self.service.read(b)['messages'][-1]['content'],'Answer')

    def test_unlisted_operation_is_not_executed(self):
        replies=iter([{'role':'assistant','content':None,'tool_calls':[{'id':'x','type':'function','function':{'name':'shell','arguments':'{}'}}]},
                      {'role':'assistant','content':'No action'}])
        self.service.requester=lambda *args:next(replies)
        self.service.operation=lambda *args:self.fail('Unlisted operation executed')
        self.service.send(self.service.create()['id'],'Question')
