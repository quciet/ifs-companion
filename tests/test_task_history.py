import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from conversations import Conversations
from jobs import Jobs
from task_history import sync_reports, delete_task, checked_tree


class TaskHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.chats=Conversations(self.root/'companion',lambda:'installation',None)
        self.jobs=Jobs(self.root/'companion')
        self.tools=SimpleNamespace(data=self.root/'companion/tool-data',stop=Mock())
        self.app=SimpleNamespace(DATA_ROOT=self.root,JOBS={},LOCK=threading.RLock())
        self.handler=SimpleNamespace(conversations=lambda:self.chats,jobs=lambda:self.jobs,tools=lambda:self.tools,task_app=self.app)

    def report(self,identity='old'):
        folder=self.root/'results'/identity;folder.mkdir(parents=True)
        (folder/'report.json').write_text('{}')
        self.app.JOBS[identity]={'status':'complete'}
        return {'id':identity,'title':'Saved comparison','created':100}

    def test_adopts_legacy_report_once_and_preserves_dates(self):
        report=self.report()
        first=sync_reports(self.chats,[report])['chats']
        second=sync_reports(self.chats,[report])['chats']
        self.assertEqual(first,second)
        self.assertEqual(len(first),1)
        self.assertEqual(first[0]['updated'],100)
        self.assertEqual(self.chats.read(first[0]['id'])['messages'][0]['links'][0]['id'],'old')

    def test_report_attached_to_chat_is_not_duplicated(self):
        chat=self.chats.create()
        self.chats.append(chat['id'],'assistant','Report',[{'kind':'report','id':'old'}])
        self.assertEqual(len(sync_reports(self.chats,[self.report()])['chats']),1)

    def test_later_chat_attachment_replaces_imported_placeholder(self):
        report=self.report()
        imported=sync_reports(self.chats,[report])['chats'][0]['id']
        real=self.chats.create()['id']
        self.chats.append(real,'user','Compare these runs')
        self.chats.append(real,'assistant','Report',[{'kind':'report','id':'old'}])
        self.assertEqual([c['id'] for c in sync_reports(self.chats,[report])['chats']],[real])
        with self.assertRaises(ValueError):self.chats.read(imported)

    def test_delete_removes_history_reports_runs_sessions_and_job_events(self):
        chat=sync_reports(self.chats,[self.report()])['chats'][0]
        identity=chat['id']
        job=self.jobs.create('scenario_run',identity)
        self.jobs.update(job['id'],'complete')
        run=self.root/'runs'/job['id'];run.mkdir(parents=True)
        (run/'result.run.db').write_text('generated')
        backend=self.jobs.create('comparison',identity,{'backend_id':'old'})
        self.jobs.update(backend['id'],'complete')
        self.chats.state(identity,'scenario-session','session1')
        scenario=self.tools.data/'ifs-scenario-builder';scenario.mkdir(parents=True)
        export=scenario/'scenarios/task.sce';export.parent.mkdir();export.write_text('scenario')
        (scenario/'sessions.json').write_text(json.dumps({'session1':{'export':{'path':{'__path__':str(export)}}},'other':{'history':['keep']}}))
        untouched=self.root/'results/other';untouched.mkdir();(untouched/'report.json').write_text('keep')
        delete_task(self.handler,identity)
        self.assertFalse((self.root/'results/old').exists())
        self.assertFalse(run.exists());self.assertFalse(export.exists())
        self.assertTrue(untouched.exists());self.assertEqual(self.jobs.list(),[])
        self.assertEqual(self.jobs.events(),[])
        self.assertEqual(json.loads((scenario/'sessions.json').read_text()),{'other':{'history':['keep']}})
        self.assertEqual(self.chats.list()['chats'],[])
        with self.assertRaisesRegex(ValueError,'Unknown chat'): self.chats.read(identity)

    def test_running_or_recovery_jobs_block_before_deleting_data(self):
        identity=sync_reports(self.chats,[self.report()])['chats'][0]['id']
        job=self.jobs.create('scenario_run',identity)
        for status,recovery in [('running',False),('failed',True)]:
            if status!='running':self.jobs.update(job['id'],status,recovery_required=recovery)
            with self.assertRaisesRegex(ValueError,'Finish or recover'):delete_task(self.handler,identity)
            self.assertTrue((self.root/'results/old/report.json').exists())
            self.assertTrue(self.chats.read(identity))
        self.tools.stop.assert_not_called()

    def test_shared_reports_are_protected(self):
        identity=sync_reports(self.chats,[self.report()])['chats'][0]['id']
        other=self.chats.create()['id']
        self.chats.append(other,'assistant','Shared',[{'kind':'report','id':'old'}])
        delete_task(self.handler,identity)
        self.assertTrue((self.root/'results/old/report.json').exists())
        self.assertTrue(self.chats.read(other))
        delete_task(self.handler,other)
        self.assertFalse((self.root/'results/old').exists())

    def test_running_tasks_include_responses_owned_work_and_legacy_comparisons(self):
        chat=self.chats.create()['id'];self.chats.append(chat,'user','Work on this')
        self.chats.active[chat]=threading.Event()
        report={**self.report(),'status':'running'}
        state=sync_reports(self.chats,[report])
        imported=next(c['id'] for c in state['chats'] if c['id']!=chat)
        self.assertEqual(set(state['running']),{chat,imported})
        self.chats.active.clear()
        work=self.jobs.create('scenario_run',chat)
        state=sync_reports(self.chats,[{**report,'status':'complete'}],self.jobs.list())
        self.assertEqual(state['running'],[chat])
        self.jobs.update(work['id'],'complete')
        self.assertEqual(sync_reports(self.chats,[{**report,'status':'complete'}],self.jobs.list())['running'],[])

    def test_paths_cannot_escape_storage(self):
        with self.assertRaises(ValueError):checked_tree(self.root,'../outside')
        with self.assertRaises(ValueError):checked_tree(self.root,'.')
