import json
import pathlib
import tempfile
import threading
import unittest
import urllib.request
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import companion_server
import app

class ShellTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.data=pathlib.Path(self.folder.name)
        self.patches=[patch.object(app,'DATA_ROOT',self.data),patch.object(app,'JOBS',{})]
        for item in self.patches:item.start()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),companion_server.Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        for item in reversed(self.patches):item.stop()
        self.folder.cleanup()
    def request(self,path,data=None):
        req=urllib.request.Request(self.base+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=5) as response:return response.read()
    def test_shell_and_comparison_are_separate_live_routes(self):
        self.assertIn(b'id="comparison"',self.request('/'))
        self.assertIn(b'id="variables"',self.request('/compare'))
        self.assertIn(b'openRecent',self.request('/shell.js'))
        self.assertIn(b'.sub',self.request('/shell.css'))
    def test_preferences_persist_outside_random_port(self):
        self.assertEqual(json.loads(self.request('/api/ui-preferences')), {})
        expected={'toolsGroup':True,'recentGroup':False}
        self.request('/api/ui-preferences',expected)
        self.assertEqual(json.loads(self.request('/api/ui-preferences')),expected)
        self.assertEqual(json.loads((self.data/'ui-preferences.json').read_text()),expected)
    def test_recent_running_failed_and_restored_reports(self):
        folder=self.data/'results'/'old';folder.mkdir(parents=True)
        (folder/'report.json').write_text(json.dumps({'run1':'base.run.db','run2':'test.run.db','buckets':{},'summaries':[]}))
        app.restore_jobs()
        app.JOBS['running']={'status':'running','created':9999999999,'run1':'a.run.db','run2':'b.run.db'}
        app.JOBS['failed']={'status':'failed','created':1,'error':'Example failure'}
        data=json.loads(self.request('/api/recent'))['jobs']
        self.assertEqual(data[0]['id'],'running')
        self.assertEqual({x['status'] for x in data},{'running','complete','failed'})
        self.assertEqual(next(x for x in data if x['id']=='old')['title'],'base.run.db vs test.run.db')
        self.assertNotIn('report',data[0])
