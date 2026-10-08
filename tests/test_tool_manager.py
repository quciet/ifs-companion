import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
import zipfile
from tool_manager import ToolManager

class ToolPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.manager=ToolManager(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def package(self,version='1.0.0',extra=None,identity='sample-tool'):
        buffer=io.BytesIO()
        meta={'id':identity,'name':'Sample tool','version':version,'api_version':1,'platform':'win-x64','kind':'web-service','entrypoint':'app/tool.exe'}
        with zipfile.ZipFile(buffer,'w') as z:
            z.writestr('tool.json',json.dumps(meta));z.writestr('app/tool.exe',b'fixture')
            for name,data in (extra or {}).items():z.writestr(name,data)
        buffer.seek(0);return buffer
    def test_install_update_remove_preserves_data(self):
        self.manager.install(self.package(extra={'old.txt':'old'}))
        data=self.manager.data/'sample-tool/results';data.mkdir(parents=True)
        result=data/'result.txt';result.write_text('saved work')
        self.manager.install(self.package('1.1.0'))
        self.assertFalse((self.manager.programs/'sample-tool/old.txt').exists())
        self.assertEqual(self.manager.list()[0]['version'],'1.1.0')
        self.manager.uninstall('sample-tool')
        self.assertEqual(result.read_text(),'saved work')
        self.assertEqual(self.manager.list(),[])
    def test_explicit_older_and_prerelease_install(self):
        self.manager.install(self.package('2.0.0'))
        with self.assertRaises(ValueError):self.manager.install(self.package('1.0.0-beta.1'))
        self.manager.install(self.package('1.0.0-beta.1'),allow_older=True)
        self.assertEqual(self.manager.read('sample-tool')['version'],'1.0.0-beta.1')
        self.manager.install(self.package('1.0.0'))
        with self.assertRaises(ValueError):self.manager.install(self.package('1.0.0-beta.2'))

    def test_uninstall_closes_idle_tool_but_preserves_busy_tool(self):
        self.manager.install(self.package())
        with patch.object(self.manager,'stop',side_effect=ValueError('This tool is busy')):
            with self.assertRaisesRegex(ValueError,'busy'):self.manager.uninstall('sample-tool',close_idle=True)
        self.assertTrue(self.manager._folder('sample-tool').exists())
        with patch.object(self.manager,'stop') as stop:
            self.manager.uninstall('sample-tool',close_idle=True)
            stop.assert_called_once_with('sample-tool')
        self.assertEqual(self.manager.list(),[])

    def test_bad_update_does_not_replace_working_tool(self):
        self.manager.install(self.package())
        for package in [self.package('0.9.0'), self.package('2.0.0',{'../escape':'bad'}),self.package('2.0.0',{'app/TOOL.EXE':'duplicate'})]:
            with self.assertRaises(ValueError):self.manager.install(package)
        self.assertEqual(self.manager.read('sample-tool')['version'],'1.0.0')
        self.assertFalse((Path(self.temp.name)/'escape').exists())
    def test_reserved_and_wrong_update_ids_are_rejected(self):
        with self.assertRaises(ValueError):self.manager.install(self.package(identity='compare'))
        with self.assertRaises(ValueError):self.manager.install(self.package(),expected_id='another-tool')
        with self.assertRaises(ValueError):self.manager.uninstall('../outside')
    def test_running_tool_cannot_be_removed_or_updated(self):
        self.manager.install(self.package())
        self.manager.processes['sample-tool']={'process':Mock(poll=Mock(return_value=None))}
        with self.assertRaises(ValueError):self.manager.uninstall('sample-tool')
        with self.assertRaises(ValueError):self.manager.install(self.package('1.1.0'))
    def test_failed_swap_restores_previous_version(self):
        self.manager.install(self.package())
        original=Path.rename
        def fail(source,target):
            if source.name=='new':raise OSError('Simulated file lock')
            return original(source,target)
        with patch.object(Path,'rename',fail):
            with self.assertRaises(OSError):self.manager.install(self.package('1.1.0'))
        self.assertEqual(self.manager.read('sample-tool')['version'],'1.0.0')

    def test_launch_converts_shared_path_and_closes_owned_process(self):
        self.manager.install(self.package())
        process=Mock(poll=Mock(return_value=None))
        def launch(*args,**kwargs):
            env=kwargs['env']
            self.assertTrue(all(isinstance(value,str) for value in env.values()))
            self.assertEqual(env['IFS_INSTALLATION'],str(Path(self.temp.name)/'installation'))
            Path(env['IFS_TOOL_READY_FILE']).write_text('{"port":12345}')
            return process
        with patch('tool_manager.subprocess.Popen',side_effect=launch):
            result=self.manager.start('sample-tool',Path(self.temp.name)/'installation')
        self.assertEqual(result['url'],'/tools/sample-tool/')
        self.manager.close()
        process.stdin.close.assert_called_once()

    def test_long_jobs_have_no_artificial_one_hour_timeout(self):
        self.manager.processes['sample-tool']={'process':Mock(poll=Mock(return_value=None)), 'port':12345, 'token':'test'}
        with patch('tool_manager.urllib.request.urlopen') as open_url:
            self.manager.request('sample-tool','bridge/invoke','POST',b'{}')
            self.assertIsNone(open_url.call_args.kwargs['timeout'])
            self.manager.request('sample-tool','bridge/status')
            self.assertEqual(open_url.call_args.kwargs['timeout'],3)

if __name__=='__main__':unittest.main()
