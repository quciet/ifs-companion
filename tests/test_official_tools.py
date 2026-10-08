import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from official_tools import OfficialTools, validate_catalog
from tool_manager import ToolManager

class OfficialToolTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.manager=ToolManager(self.temp.name);self.official=OfficialTools(self.manager)
        buffer=io.BytesIO()
        self.meta={'id':'sample-tool','name':'Example','version':'1.2.0','api_version':1,'platform':'win-x64','kind':'web-service','entrypoint':'tool.exe'}
        with zipfile.ZipFile(buffer,'w') as z:z.writestr('tool.json',json.dumps(self.meta));z.writestr('tool.exe',b'fixture')
        self.package=buffer.getvalue()
        self.row={**self.meta,'description':'Example tool','min_companion_version':'0.1.0','url':'https://github.com/quciet/ifs-companion/releases/download/test-v1.2.0/sample.ifstool','sha256':hashlib.sha256(self.package).hexdigest(),'size':len(self.package)}
    def tearDown(self):self.temp.cleanup()
    def download(self,row=None,content=None):
        catalog={'schema_version':1,'tools':[row or self.row]}
        with patch('official_tools.open_url',side_effect=[io.BytesIO(json.dumps(catalog).encode()),io.BytesIO(self.package if content is None else content)]):
            self.official._install('sample-tool')
        return self.official.progress()
    def test_verified_download_and_provenance(self):
        self.assertEqual(self.download()['status'],'complete')
        self.assertEqual(self.manager.read('sample-tool')['official_sha256'],self.row['sha256'])
        self.manager.install(io.BytesIO(self.package))
        self.assertNotIn('official_sha256',self.manager.read('sample-tool'))
    def test_checksum_mismatch_preserves_installed_version(self):
        self.manager.install(io.BytesIO(self.package))
        result=self.download(content=self.package[:-1]+b'x')
        self.assertEqual(result['status'],'error');self.assertIn('verification failed',result['message'])
        self.assertEqual(self.manager.read('sample-tool')['version'],'1.2.0')
    def test_wrong_manifest_version_and_truncated_download_rejected(self):
        self.assertEqual(self.download(row={**self.row,'version':'1.3.0'})['status'],'error')
        self.assertEqual(self.download(content=self.package[:-5])['status'],'error')
        self.assertEqual(self.manager.list(),[])
    def test_incompatible_and_unapproved_urls(self):
        self.assertEqual(self.download(row={**self.row,'min_companion_version':'9.0.0'})['status'],'error')
        for url in ['http://github.com/quciet/ifs-companion/releases/download/v1/a.ifstool','https://github.com/other/repo/releases/download/v1/a.ifstool','https://github.com/quciet/ifs-companion/releases/download/../a.ifstool']:
            with self.assertRaises(ValueError):validate_catalog({'schema_version':1,'tools':[{**self.row,'url':url}]})
    def test_offline_failure_does_not_affect_local_install(self):
        with patch('official_tools.open_url',side_effect=OSError('offline')):
            with self.assertRaisesRegex(ValueError,'Install from file still works'):self.official.catalog()
        self.manager.install(io.BytesIO(self.package));self.assertEqual(len(self.manager.list()),1)
    def test_update_guard_prevents_change_while_comparison_runs(self):
        def busy(identity):raise ValueError('Comparison is still running')
        self.manager.before_change=busy
        with self.assertRaisesRegex(ValueError,'still running'):self.manager.install(io.BytesIO(self.package))
        self.assertEqual(self.manager.list(),[])

if __name__=='__main__':unittest.main()
