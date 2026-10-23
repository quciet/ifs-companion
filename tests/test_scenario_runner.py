from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from execution import Execution
from jobs import Jobs
from scenario_runner import ScenarioRunner, WORKING, fingerprint, MARKER


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.ifs=self.root/'ifs';self.data=self.root/'data'
        for name in ('DATA','RUNFILES','Scenario','net8'):(self.ifs/name).mkdir(parents=True)
        for name in ('IFsInit.db','RUNFILES/IFsBase.run.db','DATA/SAMBase.db','RUNFILES/IFsVar.db'):
            with closing(sqlite3.connect(self.ifs/name)) as db:db.execute('CREATE TABLE fixture(value TEXT)');db.commit()
        (self.ifs/'net8/ifs.exe').write_bytes(b'fixture')
        for name in WORKING:(self.ifs/name).write_bytes(b'original '+name.encode())
        self.originals={name:(self.ifs/name).read_bytes() for name in WORKING}
        self.store=Jobs(self.data);self.execution=Execution(lambda:self.ifs,lambda root:False)
        self.delay=0;self.exitcode=0;self.reported=2030;self.commands=[]
        def popen(command,**kwargs):
            self.commands.append(command)
            script='import time,sys;from pathlib import Path;time.sleep(float(sys.argv[2]));Path(sys.argv[1]).write_text(sys.argv[3]+",1.0");print("Fatal model error: fixture" if int(sys.argv[4]) else "Model finished",flush=True);sys.exit(int(sys.argv[4]))'
            return subprocess.Popen([sys.executable,'-c',script,str(self.ifs/'RUNFILES/progress.txt'),str(self.delay),str(self.reported),str(self.exitcode)],**kwargs)
        self.runner=ScenarioRunner(self.data,self.store,self.execution,lambda:self.ifs,lambda root:{'base_year':2022},popen)

    def tearDown(self):
        self.runner.close();self.execution.close();self.temp.cleanup()

    def approval(self):
        text='CUSTOM,ylm,Kenya,1,2\n'
        return {'id':'approval','owner':'chat','installation':str(self.ifs.resolve()),'fingerprint':fingerprint(self.ifs),
            'text':text,'sha256':hashlib.sha256(text.encode()).hexdigest(),'end_year':2030}

    def wait(self, identity):
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            result=self.store.get(identity)
            if result['status']!='running' and not self.execution.status()['running']:return result
            time.sleep(.03)
        self.fail('Run did not finish')

    def assert_restored(self):
        for name,content in self.originals.items():self.assertEqual((self.ifs/name).read_bytes(),content,name)
        self.assertFalse((self.ifs/MARKER).exists())

    def test_success_preserves_inputs_captures_run_and_restores_working_files(self):
        approval=self.approval();job=self.runner.start(approval);result=self.wait(job['id'])
        self.assertEqual(result['status'],'complete',result)
        self.assertEqual(self.commands[0][1:8],['5','2030','-1','true','true','1','false'])
        folder=self.runner.root/job['id']
        self.assertEqual((folder/'Scenario.sce').read_text(),approval['text'])
        self.assertTrue(Path(result['data']['output']).is_file())
        self.assertFalse((folder/'backup').exists());self.assert_restored()

    def test_named_artifacts_and_explicit_save_are_independent(self):
        approval=self.approval();approval['filename']='DiwWorld.sce'
        result=self.wait(self.runner.start(approval)['id'])
        folder=self.runner.root/result['id']
        self.assertEqual(Path(result['data']['output']).name,'DiwWorld.run.db')
        self.assertFalse((self.ifs/'RUNFILES/DiwWorld.run.db').exists())
        self.assertEqual(result['data']['current_year'],2030)
        self.assertEqual(result['data']['save_status'],'saved')
        self.assertEqual(result['data']['recovery_status'],'restored')
        saved=self.runner.save_to_ifs(result['id'])
        self.assertEqual((self.ifs/'Scenario/DiwWorld.sce').read_text(),approval['text'])
        self.assertEqual((self.ifs/'RUNFILES/DiwWorld.run.db').read_bytes(),Path(result['data']['output']).read_bytes())
        with self.assertRaisesRegex(ValueError,'already exists'):self.runner.save_to_ifs(result['id'])
        for protected in ('Working','IFsBase','../escape'):
            with self.assertRaises(ValueError):self.runner.save_to_ifs(result['id'],protected)
        self.runner.save_to_ifs(result['id'],'Another name')
        self.assertTrue((self.ifs/'RUNFILES/Another name.run.db').is_file())
        import shutil
        shutil.rmtree(folder)
        self.assertTrue(Path(saved['data']['saved_to_ifs']['run']).is_file())

    def test_export_conflicts_and_partial_failure_preserve_existing_files(self):
        result=self.wait(self.runner.start(self.approval())['id'])
        existing=self.ifs/'RUNFILES/Scenario.run.db';existing.write_bytes(b'keep')
        with self.assertRaises(ValueError):self.runner.save_to_ifs(result['id'])
        self.assertEqual(existing.read_bytes(),b'keep')
        self.assertFalse((self.ifs/'Scenario/Scenario.sce').exists())
        existing.unlink()
        with patch('scenario_runner.shutil.copyfileobj',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.runner.save_to_ifs(result['id'])
        self.assertFalse((self.ifs/'Scenario/Scenario.sce').exists())
        self.assertFalse(existing.exists())
        self.assertFalse(self.execution.status()['running'])

    def test_fresh_installation_without_working_files_restores_without_warning(self):
        for name in WORKING:(self.ifs/name).unlink()
        result=self.wait(self.runner.start(self.approval())['id'])
        self.assertEqual(result['status'],'complete',result)
        self.assertNotIn('cleanup_warning',result['data'])
        for name in WORKING:self.assertFalse((self.ifs/name).exists())

    def test_live_year_updates_and_bounded_logs(self):
        from scenario_runner import log_tail
        job=self.store.create('scenario_run')
        progress=self.root/'progress.txt';progress.write_text('2025,1.0\n2026,1.1')
        self.runner.report_progress(job['id'],progress,'')
        self.assertEqual(self.store.get(job['id'])['data']['current_year'],2026)
        progress.write_text('partial')
        self.runner.report_progress(job['id'],progress,'2026,1.1')
        self.assertEqual(self.store.get(job['id'])['data']['current_year'],2026)
        (self.root/'console.log').write_text('x'*20000+'Fatal error: fixture')
        tail=log_tail(self.root)
        self.assertLess(len(tail),8300);self.assertIn('Fatal error: fixture',tail)

    def test_unsafe_export_names_rejected(self):
        from scenario_runner import scenario_name
        for name in ('CON','bad:name','trailing.',''):
            with self.assertRaises(ValueError):scenario_name(name)

    def test_zero_exit_without_requested_year_fails_and_restores(self):
        self.reported=2029;result=self.wait(self.runner.start(self.approval())['id'])
        self.assertEqual(result['status'],'failed');self.assertIn('final year',result['data']['error']);self.assert_restored()

    def test_cancel_stops_owned_process_and_restores(self):
        self.delay=20;job=self.runner.start(self.approval())
        deadline=time.monotonic()+5
        while self.store.get(job['id'])['data'].get('stage')!='running' and time.monotonic()<deadline:time.sleep(.02)
        self.runner.cancel(job['id']);result=self.wait(job['id'])
        self.assertEqual(result['status'],'cancelled');self.assert_restored()

    def test_changed_installation_or_bytes_rejects_before_mutation(self):
        approval=self.approval();approval['text']+='changed'
        with self.assertRaises(ValueError):self.runner.start(approval)
        approval=self.approval();(self.ifs/'net8/ifs.exe').write_bytes(b'changed')
        with self.assertRaises(ValueError):self.runner.start(approval)
        self.assert_restored();self.assertEqual(self.store.list(),[])

    def test_failed_restoration_blocks_execution_until_explicit_recovery(self):
        original=self.runner.restore
        with patch.object(self.runner,'restore',side_effect=OSError('fixture locked')):
            job=self.runner.start(self.approval());result=self.wait(job['id'])
        self.assertTrue(result['data']['recovery_required']);self.assertTrue((self.ifs/MARKER).exists())
        with self.assertRaisesRegex(ValueError,'recovery'):self.execution.acquire('Other run')
        recovered=self.runner.recover(job['id']);self.assertFalse(recovered['data']['recovery_required']);self.assert_restored()
        self.assertEqual(recovered['data']['save_status'],'saved')
        self.runner.save_to_ifs(job['id'])
        self.assertTrue((self.ifs/'RUNFILES/Scenario.run.db').exists())

    def test_other_run_cannot_start_while_reserved(self):
        self.delay=20;job=self.runner.start(self.approval())
        with self.assertRaises(ValueError):self.runner.start(self.approval())
        self.runner.cancel(job['id']);self.wait(job['id'])

    def test_comparison_reading_working_files_blocks_model_preparation(self):
        comparison=self.store.create('comparison',data={'inputs':[str(self.ifs/'RUNFILES/Working.run.db')]})
        with self.assertRaisesRegex(ValueError,'comparison'):self.runner.start(self.approval())
        self.assert_restored()
        self.store.update(comparison['id'],'complete')
        self.assertEqual(self.wait(self.runner.start(self.approval())['id'])['status'],'complete')

    def test_nonzero_exit_restores_and_never_publishes_output(self):
        self.exitcode=3;result=self.wait(self.runner.start(self.approval())['id'])
        self.assertEqual(result['status'],'failed');self.assertNotIn('output',result['data']);self.assertIn('Fatal model error: fixture',result['data']['error']);self.assertEqual(result['data']['current_year'],2030);self.assert_restored()

    def test_working_database_journals_block_before_mutation(self):
        journal=self.ifs/'RUNFILES/Working.run.db-wal';journal.write_bytes(b'external database journal')
        result=self.wait(self.runner.start(self.approval())['id'])
        self.assertEqual(result['status'],'failed');self.assertEqual(journal.read_bytes(),b'external database journal');self.assert_restored()


class JobTests(unittest.TestCase):
    def test_restart_interrupts_dead_owner_but_preserves_live_owner(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Jobs(folder);dead=store.create('scenario_run',data={'manager_pid':123456789});live=store.create('chat')
            with patch('jobs.process_alive',side_effect=lambda pid,created=None:pid!=123456789):
                store.interrupt({'scenario_run','chat'})
            self.assertEqual(store.get(dead['id'])['status'],'interrupted');self.assertEqual(store.get(live['id'])['status'],'running')
    def test_windows_process_probe_is_non_destructive_and_rejects_reused_pid(self):
        import os
        from jobs import process_alive
        self.assertTrue(process_alive(os.getpid()))
        self.assertFalse(process_alive(2147483647))
        if os.name=='nt':self.assertFalse(process_alive(os.getpid(),0))

    def test_interrupted_run_keeps_recovery_required_and_can_be_deleted_after_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Jobs(folder)
            job=store.create('scenario_run',data={'manager_pid':123456789,'recovery_required':True,'stage':'stopping'})
            with patch('jobs.process_alive',return_value=False):store.interrupt({'scenario_run'})
            result=store.get(job['id'])
            self.assertEqual(result['status'],'interrupted')
            self.assertEqual(result['data']['stage'],'recovery_required')
            with self.assertRaises(ValueError):store.delete(job['id'])
            store.update(job['id'],recovery_required=False,stage='recovered')
            store.delete(job['id']);self.assertEqual(store.list(),[])

    def test_persist_events_owner_and_terminal_state(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Jobs(folder);job=store.create('comparison',data={'backend_id':'abc'})
            store.claim(job['id'],'chat')
            with self.assertRaises(ValueError):store.claim(job['id'],'other')
            store.update(job['id'],progress='halfway');store.update(job['id'],'complete')
            restored=Jobs(folder);self.assertEqual(restored.list('chat')[0]['status'],'complete')
            self.assertEqual(restored.events()[-1]['status'],'complete')
            with self.assertRaises(ValueError):restored.update(job['id'],'running')
