import re
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET
from official_tools import COMPANION_VERSION


class VersionConsistencyTests(unittest.TestCase):
    def test_engine_desktop_installer_agree(self):
        root = Path(__file__).resolve().parents[1]
        version = '.'.join(map(str, COMPANION_VERSION))
        desktop = ET.parse(root / 'desktop/IFsCompanion.csproj').findtext('.//Version')
        installer = re.search(r'^#define AppVersion "([^"]+)"', (root / 'packaging/installer.iss').read_text(), re.M)[1]
        self.assertEqual(version, desktop)
        self.assertEqual(version, installer)

    def test_header_has_no_fixed_version(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / 'shell.html').read_text(encoding='utf-8')
        self.assertIn('id="companionVersion"', html)
        self.assertNotRegex(html, r'<small>v\d+\.\d+\.\d+</small>')
