import tempfile
import threading
import unittest
from unittest.mock import patch
from conversations import Conversations


class ConversationTests(unittest.TestCase):
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
