import pathlib
import tempfile
import threading
import unittest
from unittest.mock import patch, MagicMock
import companion_server
import app

class StopComparisonTests(unittest.TestCase):
    def test_stop_during_metadata_prevents_variable_work_and_report(self):
        started=threading.Event();release=threading.Event()
        def metadata(path):
            started.set();release.wait(3);return {}
        with tempfile.TemporaryDirectory() as directory, patch.object(app,'DATA_ROOT',pathlib.Path(directory)), patch.object(app,'JOBS',{'test':{'status':'running'}}), patch.object(app,'metadata',side_effect=metadata), patch.object(app,'connect',return_value=MagicMock()), patch.object(app,'decode') as decode:
            worker=threading.Thread(target=app.compare,args=('test',{'a':'a','b':'b','variables':['GDP']}))
            worker.start();self.assertTrue(started.wait(2))
            app.JOBS['test']['stop_requested']=True;release.set();worker.join(3)
            self.assertFalse(worker.is_alive())
            self.assertEqual(app.JOBS['test']['status'],'stopped')
            decode.assert_not_called()
            self.assertFalse((pathlib.Path(directory)/'results/test/report.json').exists())
