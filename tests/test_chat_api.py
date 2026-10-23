import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch
import companion_server
import app
import io
import hashlib
import sqlite3
from contextlib import closing
from types import SimpleNamespace
from scenario_runner import fingerprint
from execution import Execution
from jobs import Jobs


class ChatApiTests(unittest.TestCase):
    def test_inline_review_requires_owned_session_and_persists_confirmed_result(self):
        chat=self.post('/api/chats/create',{})
        from conversations import Conversations
        service=self.server.conversations
        service.state(chat['id'],'scenario-session','owned-session')
        request={'id':chat['id'],'session':'owned-session','confirmation':'review-token'}
        with self.assertRaises(HTTPError) as error:self.post('/api/chats/scenario',request,False)
        error.exception.close()
        with self.assertRaises(HTTPError) as error:self.post('/api/chats/scenario',{**request,'session':'other-chat'})
        error.exception.close()
        result={'session':'owned-session','reply':'Confirmed draft.','draft':{'id':'draft-token'}}
        with patch.object(self.server.tools,'start'),patch.object(self.server.tools,'request',return_value=io.BytesIO(json.dumps(result).encode())):
            self.assertEqual(self.post('/api/chats/scenario',request),result)
        restored=Conversations(service.root,service.installation,None).read(chat['id'])
        self.assertEqual(restored['messages'][-1]['links'][0]['context'],result)
        self.assertEqual(service.state(chat['id'],'scenario-review'),result)
        self.assertFalse(service.busy())

    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.patch=patch.object(app,'DATA_ROOT',Path(self.folder.name));self.patch.start()
        self.server=companion_server.create_server()
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.patch.stop();self.folder.cleanup()

    def post(self,path,body,token=True):
        headers={'Content-Type':'application/json'}
        if token:headers['X-Companion-Token']=self.server.tool_token
        with urlopen(Request(self.base+path,data=json.dumps(body).encode(),headers=headers),timeout=5) as response:
            return json.load(response)

    def test_save_to_ifs_requires_authentication_and_routes_name(self):
        from unittest.mock import Mock
        runner=Mock();runner.save_to_ifs.return_value={'saved':True}
        self.server.runner=runner
        with self.assertRaises(HTTPError) as error:self.post('/api/runs/save',{'id':'run'},False)
        error.exception.close();runner.save_to_ifs.assert_not_called()
        self.assertEqual(self.post('/api/runs/save',{'id':'run','name':'DiwWorld'}),{'saved':True})
        runner.save_to_ifs.assert_called_once_with('run','DiwWorld')

    def test_chat_create_requires_authentication_and_persists(self):
        with self.assertRaises(HTTPError) as error:self.post('/api/chats/create',{},False)
        error.exception.close()
        chat=self.post('/api/chats/create',{})
        with urlopen(self.base+'/api/chats?id='+chat['id']) as response:
            self.assertEqual(json.load(response)['messages'],[])
        with urlopen(self.base+'/api/chats') as response:
            self.assertEqual(json.load(response)['chats'],[])
        opened=self.post('/api/chats/touch',{'id':chat['id']})
        self.assertEqual(opened['id'],chat['id'])
        self.assertEqual(opened['updated'],chat['updated'])

    def test_saved_tasks_migrate_reports_and_delete_requires_authentication(self):
        with patch.dict(app.JOBS,{},clear=True):
            app.JOBS['legacy']={'status':'complete','created':100,'report':{'run1':'Base.run.db','run2':'Policy.run.db'}}
            folder=app.DATA_ROOT/'results/legacy';folder.mkdir(parents=True)
            (folder/'report.json').write_text('{}')
            recents=self.post('/api/tasks/recent',{})['chats']
            self.assertEqual(len(recents),1)
            self.assertEqual(recents[0]['title'],'Base.run.db vs Policy.run.db')
            self.assertEqual(self.post('/api/tasks/recent',{})['chats'],recents)
            with self.assertRaises(HTTPError) as error:
                self.post('/api/tasks/delete',{'id':recents[0]['id']},False)
            error.exception.close()
            self.assertTrue(folder.exists())
            self.post('/api/tasks/delete',{'id':recents[0]['id']})
            self.assertFalse(folder.exists())
            self.assertEqual(self.post('/api/tasks/recent',{})['chats'],[])

    def test_invalid_comparison_event_does_not_add_history(self):
        chat=self.post('/api/chats/create',{})
        with self.assertRaises(HTTPError) as error:self.post('/api/chats/event',{'id':chat['id'],'kind':'comparison','job':'missing'})
        error.exception.close()
        with urlopen(self.base+'/api/chats?id='+chat['id']) as response:
            self.assertEqual(json.load(response)['messages'],[])

    def test_run_requires_exact_approval_and_duplicate_start_is_idempotent(self):
        root=Path(self.folder.name)/'ifs'
        for name in ('DATA','RUNFILES','net8'):(root/name).mkdir(parents=True)
        for name in ('IFsInit.db','RUNFILES/IFsBase.run.db','DATA/SAMBase.db','RUNFILES/IFsVar.db'):
            with closing(sqlite3.connect(root/name)) as db:db.execute('CREATE TABLE fixture(value)');db.commit()
        (root/'net8/ifs.exe').write_bytes(b'fixture')
        text='CUSTOM,ylm,Kenya,1,2\n'
        calls=[]
        def request(identity,path,*args):
            if path=='bridge/capabilities':return io.BytesIO(b'{"approved_execution":1}')
            return io.BytesIO(json.dumps({'text':text,'filename':'Fixture.sce'}).encode())
        def start(approval):
            calls.append(approval)
            return self.server.jobs.create('scenario_run',approval['owner'],{'approval_id':approval['id'],'stage':'running'})
        self.server.runner=SimpleNamespace(start=start,close=lambda:None)
        with patch.object(app,'saved_installation',return_value=root),patch('companion_server.validate_installation',return_value={'base_year':2022,'version':'fixture'}),patch.object(self.server.tools,'start'),patch.object(self.server.tools,'request',side_effect=request):
            chat=self.post('/api/chats/create',{})
            approval=self.post('/api/runs/prepare',{'chat':chat['id'],'source':{'name':'Fixture.sce','text':text},'end_year':2030})
            self.assertEqual(approval['sha256'],hashlib.sha256(text.encode()).hexdigest());self.assertEqual(calls,[])
            with self.assertRaises(HTTPError) as error:self.post('/api/runs/start',{'chat':chat['id'],'approval':approval['id'],'sha256':'wrong'})
            error.exception.close();self.assertEqual(calls,[])
            body={'chat':chat['id'],'approval':approval['id'],'sha256':approval['sha256']}
            first=self.post('/api/runs/start',body);second=self.post('/api/runs/start',body)
            self.assertEqual(first['id'],second['id']);self.assertEqual(len(calls),1)
            with urlopen(self.base+'/api/jobs?chat='+chat['id']) as response:
                self.assertEqual(json.load(response)['jobs'][0]['id'],first['id'])

    def test_recents_release_abandoned_run_but_require_working_file_recovery(self):
        chat=self.post('/api/chats/create',{})
        with urlopen(self.base+'/api/jobs') as response:json.load(response)
        job=self.server.jobs.create('scenario_run',chat['id'],{'manager_pid':2147483647,'stage':'stopping','recovery_required':True})
        recent=self.post('/api/tasks/recent',{})
        self.assertNotIn(chat['id'],recent['running'])
        repaired=self.server.jobs.get(job['id'])
        self.assertEqual(repaired['status'],'interrupted')
        self.assertTrue(repaired['data']['recovery_required'])
        with self.assertRaises(HTTPError) as error:self.post('/api/tasks/delete',{'id':chat['id']})
        error.exception.close()
        self.server.jobs.update(job['id'],recovery_required=False)
        self.post('/api/tasks/delete',{'id':chat['id']})

    def test_jobs_cancel_is_targeted_and_events_survive_polling(self):
        with urlopen(self.base+'/api/jobs') as response:json.load(response)
        first=self.server.jobs.create('comparison',data={'backend_id':'one'})
        second=self.server.jobs.create('comparison',data={'backend_id':'two'})
        with patch.object(app,'JOBS',{'one':{'status':'running'},'two':{'status':'running'}}):
            self.post('/api/jobs/cancel',{'id':first['id']})
            self.assertTrue(app.JOBS['one']['stop_requested']);self.assertNotIn('stop_requested',app.JOBS['two'])
        with urlopen(self.base+'/api/jobs/events?after=0') as response:
            self.assertTrue(json.load(response)['events'])

    def test_run_completion_notifies_chat_and_links_saved_output(self):
        chat=self.post('/api/chats/create',{})
        with urlopen(self.base+'/api/jobs') as response:json.load(response)
        job=self.server.jobs.create('scenario_run',chat['id'],{'installation':'fixture','end_year':2030,'output':'fixture/result.run.db'})
        job=self.server.jobs.update(job['id'],'complete')
        handler=object.__new__(companion_server.Handler);handler.server=self.server
        handler.publish_run_result(job)
        with urlopen(self.base+'/api/chats?id='+chat['id']) as response:
            message=json.load(response)['messages'][-1]
        self.assertIn('2030',message['content'])
        self.assertEqual(message['links'][1]['context']['comparisons'],['fixture/result.run.db'])
        self.assertTrue(self.server.jobs.get(job['id'])['data']['notification_sent'])

    def test_comparison_cannot_read_working_database_during_model_execution(self):
        root=Path(self.folder.name)/'ifs';root.mkdir()
        controller=Execution(lambda:root,lambda root:False);self.server.execution=controller
        self.server.execution_token='fixture'
        with patch.object(app,'saved_installation',return_value=root),patch.object(app,'JOBS',{}):
            lease=controller.acquire('Scenario run')['lease']
            try:
                with self.assertRaises(HTTPError) as error:
                    self.post('/api/compare',{'a':str(root/'RUNFILES/Working.run.db'),'comparisons':[str(root/'RUNFILES/IFsBase.run.db')],'variables':['GDP']})
                self.assertEqual(error.exception.code,400);error.exception.close();self.assertEqual(app.JOBS,{})
            finally:controller.release(lease)

    def test_storage_relocation_rebases_run_catalog_references(self):
        data=Path(self.folder.name);store=Jobs(data/'companion')
        old=str(data/'old-location/result.run.db');output=data/'runs/relocated/result.run.db';output.parent.mkdir(parents=True);output.write_bytes(b'fixture')
        store.create('scenario_run',data={'output':old},identity='relocated');store.update('relocated','complete')
        chat=self.post('/api/chats/create',{})
        self.server.conversations.append(chat['id'],'assistant','Comparison',
            [{'kind':'comparison','context':{'a':'baseline.run.db','comparisons':[old],'variables':['GDP']}}])
        with urlopen(self.base+'/api/chats?id='+chat['id']) as response:
            context=json.load(response)['messages'][-1]['links'][0]['context']
        self.assertEqual(context['comparisons'],[str(output.resolve())])
        self.assertEqual(self.server.jobs.get('relocated')['data']['output'],str(output.resolve()))
