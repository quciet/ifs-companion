from pathlib import Path
import tempfile
import unittest
from execution import Execution


class ExecutionTests(unittest.TestCase):
    def test_reservation_is_exclusive_across_controllers_and_release_requires_token(self):
        with tempfile.TemporaryDirectory() as folder:
            a=Execution(lambda:Path(folder),lambda root:False)
            b=Execution(lambda:Path(folder),lambda root:False)
            try:
                lease=a.acquire('Autotune')['lease']
                with self.assertRaises(ValueError):b.acquire('Chat')
                with self.assertRaises(ValueError):a.release('wrong')
                a.release(lease)
                b.release(b.acquire('Chat')['lease'])
            finally:a.close();b.close()

    def test_external_run_blocks_and_does_not_leak_reservation(self):
        with tempfile.TemporaryDirectory() as folder:
            controller=Execution(lambda:folder,lambda root:True)
            try:
                with self.assertRaisesRegex(ValueError,'already running'):controller.acquire('Chat')
                self.assertFalse(controller.status()['running'])
                controller.detector=lambda root:False
                controller.release(controller.acquire('Chat')['lease'])
            finally:controller.close()
