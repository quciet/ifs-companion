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

if __name__=='__main__':unittest.main()
