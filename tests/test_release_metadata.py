import io,json,tempfile,unittest,zipfile
from tool_manager import ToolManager,manifest,release_metadata
from official_tools import validate_catalog

class ReleaseMetadataTests(unittest.TestCase):
    def package(self,**extra):
        data={'id':'sample-release','name':'Sample','version':'1.0.0','api_version':1,'platform':'win-x64','kind':'web-service','entrypoint':'sample.exe',**extra}
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:z.writestr('tool.json',json.dumps(data));z.writestr('sample.exe',b'fixture')
        stream.seek(0);return stream
    def test_file_install_preserves_details_and_measures_sizes(self):
        with tempfile.TemporaryDirectory() as root:
            manager=ToolManager(root);package=self.package(released_at='2026-10-10',release_notes='First release',installed_size=999999,size=999999,min_companion_version='0.1.2')
            with zipfile.ZipFile(package) as z:expected=sum(i.file_size for i in z.infolist())
            package.seek(0);manager.install(package)
            stored=manager.read('sample-release')
            self.assertEqual(stored['release_notes'],'First release');self.assertEqual(stored['installed_size'],expected)
            self.assertEqual(stored['size'],len(package.getvalue()))
            manager.install(self.package())
            self.assertNotIn('release_notes',manager.read('sample-release'))
    def test_invalid_metadata_and_incompatible_package(self):
        for data in [{'size':True},{'installed_size':-1},{'released_at':'2026-02-30'},{'release_notes':'x'*8001},{'min_companion_version':'latest'}]:
            with self.assertRaises(ValueError):release_metadata(data)
        with tempfile.TemporaryDirectory() as root:
            manager=ToolManager(root)
            with self.assertRaisesRegex(ValueError,'requires Companion'):manager.install(self.package(min_companion_version='99.0.0'))
            self.assertEqual(manager.list(),[])
    def test_catalog_metadata_and_online_install_persistence(self):
        row={'id':'sample-release','name':'Sample','description':'Example','version':'1.0.0','min_companion_version':'0.1.2','api_version':1,'platform':'win-x64','url':'https://github.com/quciet/ifs-companion/releases/download/v1/example.ifstool','sha256':'a'*64,'size':100,'installed_size':500,'released_at':'2026-10-10','release_notes':'Catalog notes'}
        validated=validate_catalog({'schema_version':1,'tools':[row]})[0]
        self.assertEqual(validated['release_notes'],'Catalog notes')
        with tempfile.TemporaryDirectory() as root:
            manager=ToolManager(root);manager.install(self.package(),release_info=validated,official_sha256=row['sha256'])
            self.assertEqual(manager.read('sample-release')['released_at'],'2026-10-10')

if __name__=='__main__':unittest.main()
