import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]

class DesktopLifecycleTests(unittest.TestCase):
    def test_engine_stops_when_desktop_pipe_closes(self):
        with tempfile.TemporaryDirectory() as folder:
            env = dict(os.environ, IFS_VETTING_DATA_DIR=folder)
            process = subprocess.Popen([sys.executable, str(ROOT/'desktop_launcher.py')],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            try:
                ready = json.loads(process.stdout.readline())
                with urllib.request.urlopen(ready['url']+'/api/status', timeout=5) as response:
                    self.assertEqual(json.load(response), {'running': False})
                process.stdin.close()
                self.assertEqual(process.wait(timeout=10), 0)
                with self.assertRaises(OSError):
                    urllib.request.urlopen(ready['url']+'/api/status', timeout=2)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                process.stdout.close()
                process.stderr.close()

if __name__ == '__main__':
    unittest.main()
