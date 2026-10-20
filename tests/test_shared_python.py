import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from shared_python import SharedPython, PROFILE
from tool_manager import ToolManager, manifest


class SharedPythonTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.manager=ToolManager(self.tmp.name)
        self.lock={'core':['numpy'],'tools':{
            'ifs-model-vetting':['numpy','common'],
            'ifs-autotune':['numpy','common','exclusive'],
            'ifs-code-reader':['common']},
            'packages':{name:{'version':'1.0','sha256':'a'*64,'url':'https://example.invalid/'+name+'.whl'}
                        for name in ('numpy','common','exclusive')}}
        runtime=Path(self.tmp.name)/'python.exe';runtime.touch()
        self.manager.python=SharedPython(self.tmp.name,runtime=runtime,lock=self.lock)

    def package(self,identity,version='1.0.0'):
        buffer=io.BytesIO()
        meta={'id':identity,'name':'Fixture','version':version,'api_version':1,'platform':'win-x64',
              'kind':'web-service','entrypoint':'service.py','python_profile':PROFILE}
        with zipfile.ZipFile(buffer,'w') as archive:
            archive.writestr('tool.json',json.dumps(meta));archive.writestr('service.py','')
        buffer.seek(0)
        return buffer

    def fake_pip(self,command,**kwargs):
        stage=Path(command[command.index('--target')+1]);stage.mkdir()
        (stage/'payload').write_text('installed')
        return Mock(returncode=0)

    def test_shared_library_survives_uninstall_and_no_duplicate_install(self):
        with patch('shared_python.subprocess.run',side_effect=self.fake_pip) as pip:
            self.manager.install(self.package('ifs-model-vetting'))
            self.manager.install(self.package('ifs-autotune'))
            self.assertEqual(pip.call_count,2) # common once; exclusive once; core never copied
        # Another tool can continue running while unreferenced libraries are removed.
        self.manager.processes['ifs-model-vetting']={'process':Mock(poll=Mock(return_value=None))}
        saved=self.manager.data/'ifs-autotune';saved.mkdir();(saved/'work').write_text('keep')
        self.manager.uninstall('ifs-autotune')
        self.assertTrue(self.manager.python.folder('common').is_dir())
        self.assertFalse(self.manager.python.folder('exclusive').exists())
        self.assertTrue((saved/'work').exists())
        self.manager.processes.clear()
        self.manager.uninstall('ifs-model-vetting')
        self.assertFalse(self.manager.python.folder('common').exists())

    def test_failed_dependency_install_keeps_old_tool_and_other_libraries(self):
        with patch('shared_python.subprocess.run',side_effect=self.fake_pip):
            self.manager.install(self.package('ifs-model-vetting'))
        with patch('shared_python.subprocess.run',return_value=Mock(returncode=1)):
            with self.assertRaisesRegex(ValueError,'shared library'):
                self.manager.install(self.package('ifs-autotune'))
        self.assertEqual(self.manager.read('ifs-model-vetting')['version'],'1.0.0')
        self.assertFalse(self.manager._folder('ifs-autotune').exists())
        self.assertTrue(self.manager.python.folder('common').exists())
        self.assertFalse(self.manager.python.folder('exclusive').exists())

    def test_unknown_profile_or_unofficial_identity_cannot_select_dependencies(self):
        for identity in ['third-party','ifs-autotune']:
            data={'id':identity,'name':'Fixture','version':'1.0.0','api_version':1,'platform':'win-x64',
                  'kind':'web-service','entrypoint':'service.py','python_profile':PROFILE if identity=='third-party' else 'future-profile'}
            with self.assertRaises(ValueError):manifest(data)

    def test_corrupt_other_manifest_prevents_cleanup(self):
        with patch('shared_python.subprocess.run',side_effect=self.fake_pip):
            self.manager.install(self.package('ifs-autotune'))
            self.manager.install(self.package('ifs-model-vetting'))
        (self.manager._folder('ifs-model-vetting')/'tool.json').write_text('{broken')
        self.manager.uninstall('ifs-autotune')
        self.assertTrue(self.manager.python.folder('common').exists())

    def test_failed_tool_swap_keeps_existing_dependencies(self):
        with patch('shared_python.subprocess.run',side_effect=self.fake_pip):
            self.manager.install(self.package('ifs-autotune'))
        rename=Path.rename
        def fail(source,target):
            if source.name=='new':raise OSError('locked')
            return rename(source,target)
        with patch.object(Path,'rename',fail):
            with self.assertRaises(OSError):self.manager.install(self.package('ifs-autotune','2.0.0'))
        self.assertEqual(self.manager.read('ifs-autotune')['version'],'1.0.0')
        self.assertTrue(self.manager.python.folder('exclusive').exists())


if __name__=='__main__':unittest.main()
