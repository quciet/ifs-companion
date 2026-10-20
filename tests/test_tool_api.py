import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from pathlib import Path
from companion_server import Handler
import app

class ToolApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patch=patch.object(app,'DATA_ROOT',Path(self.temp.name));self.patch.start()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'
        with urllib.request.urlopen(self.url) as response:response.read()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.patch.stop();self.temp.cleanup()
    def post(self,path,data,token=True,origin=None):
        headers={'Content-Type':'application/octet-stream'}
        if token:headers['X-Companion-Token']=self.server.tool_token
        if origin:headers['Origin']=origin
        request=urllib.request.Request(self.url+path,data=data,headers=headers)
        with urllib.request.urlopen(request) as response:return json.load(response)
    def test_upload_list_remove_and_persist(self):
        manifest={'id':'sample-tool','name':'Sample','version':'1.0.0','api_version':1,'platform':'win-x64','kind':'web-service','entrypoint':'sample.exe'}
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as z:z.writestr('tool.json',json.dumps(manifest));z.writestr('sample.exe',b'fixture')
        installed=self.post('/api/tools/install',data.getvalue())
        self.assertEqual(installed['id'],'sample-tool')
        with urllib.request.urlopen(self.url+'/api/tools') as response:self.assertEqual(len(json.load(response)['tools']),1)
        saved=self.server.tools.data/'sample-tool';saved.mkdir();(saved/'result.txt').write_text('result')
        self.post('/api/tools/uninstall',b'{"id":"sample-tool"}')
        self.assertTrue((saved/'result.txt').exists())
    def test_rejects_missing_token_and_foreign_origin(self):
        for kwargs in [{'token':False},{'origin':'https://example.invalid'}]:
            with self.assertRaises(urllib.error.HTTPError) as error:self.post('/api/tools/uninstall',b'{"id":"sample-tool"}',**kwargs)
            self.assertEqual(error.exception.code,400)
            error.exception.close()

    def test_shared_ai_settings_are_authenticated_and_do_not_echo_key(self):
        request=json.dumps({'endpoint':'http://127.0.0.1:12345/v1','model':'local-fixture'}).encode()
        with self.assertRaises(urllib.error.HTTPError) as error:self.post('/api/ai-settings',request,token=False)
        error.exception.close()
        result=self.post('/api/ai-settings',request)
        self.assertTrue(result['configured'])
        self.assertNotIn('api_key',result)
        with urllib.request.urlopen(self.url+'/api/ai-settings') as response:
            self.assertEqual(json.load(response)['model'],'local-fixture')

    def test_scenario_builder_is_not_bundled(self):
        with urllib.request.urlopen(self.url) as response: html=response.read().decode()
        self.assertNotIn('id="scenarioView"', html)
        self.assertNotIn('href="/scenario.css"', html)
        self.assertNotIn('data-view="scenario"', html)
        for path in ('/scenario.js','/api/scenario/references'):
            with self.assertRaises(urllib.error.HTTPError) as error: urllib.request.urlopen(self.url+path)
            self.assertEqual(error.exception.code,404);error.exception.close()
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post('/api/scenario/chat',b'{"message":"test"}')
        self.assertEqual(error.exception.code,404);error.exception.close()

    def test_app_update_mutations_are_authenticated_and_install_waits_for_work(self):
        for path in ('/api/app-update/check','/api/app-update/download','/api/app-update/install'):
            with self.assertRaises(urllib.error.HTTPError) as error:self.post(path,b'{}',token=False)
            self.assertEqual(error.exception.code,400);error.exception.close()
        with urllib.request.urlopen(self.url+'/api/app-update') as response:
            self.assertEqual(json.load(response)['status'],'idle')
        from unittest.mock import Mock
        updater=Mock();updater.check.return_value={'status':'checking'}
        with patch.object(Handler,'updater',return_value=updater):
            self.assertEqual(self.post('/api/app-update/check',b'{}')['status'],'checking')
            with patch.object(self.server.tools,'busy',return_value=True):
                with self.assertRaises(urllib.error.HTTPError) as error:self.post('/api/app-update/install',b'{}')
                self.assertEqual(error.exception.code,400);error.exception.close()
            updater.prepare_install.assert_not_called()

    def test_storage_change_is_authenticated_and_stays_in_companion(self):
        import os
        import storage
        with tempfile.TemporaryDirectory() as appdir, tempfile.TemporaryDirectory() as destination, patch.object(storage, 'app_directory', return_value=Path(appdir)), patch.dict(os.environ, {'IFS_VETTING_DATA_DIR': ''}):
            request=json.dumps({'location':destination}).encode()
            with self.assertRaises(urllib.error.HTTPError) as error:self.post('/api/storage',request,token=False)
            error.exception.close()
            result=self.post('/api/storage',request)
            self.assertEqual(Path(result['pending']),Path(destination).resolve())
            with patch.object(Handler,'comparison_running',return_value=True), patch.object(Handler,'comparison_proxy',side_effect=AssertionError('Storage belongs to Companion')):
                with urllib.request.urlopen(self.url+'/api/storage') as response:
                    self.assertEqual(json.load(response)['current'],str(app.DATA_ROOT))

if __name__=='__main__':unittest.main()
