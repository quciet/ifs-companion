import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('scenario_optional',Path(__file__).resolve().parents[1]/'scenario-tool/service.py')
optional=importlib.util.module_from_spec(spec)
spec.loader.exec_module(optional)


class OptionalScenarioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.shared=self.root/'settings.json'
        self.ai=self.root/'companion/ai-settings.json'
        self.server=optional.create_server(self.root/'tool-data', 'test-token', self.ai, self.shared)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def request(self,path,data=None,token='test-token'):
        request=urllib.request.Request(self.url+path,data=None if data is None else json.dumps(data).encode(),
            headers={'X-IFs-Tool-Token':token,'Content-Type':'application/json'})
        return urllib.request.urlopen(request,timeout=5)

    def test_assets_and_all_routes_are_authenticated(self):
        for path in ('/','/bridge/status','/api/scenario/download?id=test'):
            with self.assertRaises(urllib.error.HTTPError) as error:self.request(path,token='wrong')
            self.assertEqual(error.exception.code,403);error.exception.close()
        with self.request('/') as response:
            text=response.read().decode();self.assertIn('scenarioInspector',text);self.assertIn('bridge.js',text)
        with self.request('/bridge.js') as response:
            self.assertIn(b'companionSession',response.read())
        with self.request('/bridge/status') as response:self.assertFalse(json.load(response)['running'])

    def test_shared_settings_are_live_and_separate_from_tool_data(self):
        self.assertEqual(self.server.service.settings_file,self.ai)
        self.shared.write_text(json.dumps({'installation':'D:/First'}))
        self.assertEqual(self.server.service.installation(),Path('D:/First'))
        self.shared.write_text(json.dumps({'installation':'D:/Second'}))
        self.assertEqual(self.server.service.installation(),Path('D:/Second'))
        self.assertFalse((self.root/'tool-data/companion/ai-settings.json').exists())

    def test_chat_and_stop_bridge(self):
        with patch.object(self.server.service,'chat',return_value={'session':'test','reply':'Clarify.','draft':None}):
            with self.request('/api/scenario/chat',{'message':'Help'}) as response:
                self.assertEqual(json.load(response)['reply'],'Clarify.')
        with self.request('/bridge/stop',{}) as response:self.assertTrue(json.load(response)['stopped'])


if __name__=='__main__':unittest.main()
