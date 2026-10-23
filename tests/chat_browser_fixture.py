"""Isolated browser fixture: subprocess simulator and real comparisons; no native IFs or provider calls."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import hashlib
import sqlite3
import subprocess
from contextlib import closing
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import companion_server
import app
from conversations import Conversations
from execution import Execution
from scenario_runner import ScenarioRunner, fingerprint
from installation_validation import REQUIRED_FILES,validate_installation


class FixtureHandler(companion_server.Handler):
    def do_GET(self):
        if self.path=='/fixture/activity/start':
            owner=self.conversations().list()['chats'][0]['id']
            self.server.fixture_activity=self.jobs().create('scenario_run',owner)['id']
            return self.send({'running':owner})
        if self.path=='/fixture/activity/finish':
            self.jobs().update(self.server.fixture_activity,'complete')
            return self.send({'complete':True})
        if self.path=='/fixture/stop':
            self.send({'stopped':True})
            threading.Thread(target=self.server.shutdown,daemon=True).start()
            return
        return super().do_GET()


def main():
    with tempfile.TemporaryDirectory(prefix='companion-chat-ui-') as temporary:
        app.DATA_ROOT=Path(temporary)
        app.SETTINGS=app.DATA_ROOT/'settings.json'
        server=companion_server.create_server()
        server.RequestHandlerClass=FixtureHandler
        # Real subprocess and comparison paths, with a tiny simulator replacing IFs.
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'ifs-model-vetting/tests'))
        from test_multi_run import run_file,fixture_decode
        installation=app.DATA_ROOT/'fixture-ifs'
        for name in ('DATA','RUNFILES','Scenario','net8'):(installation/name).mkdir(parents=True)
        for name in REQUIRED_FILES:
            target=installation/name
            if name.endswith('.db'):
                with closing(sqlite3.connect(target)) as db:db.execute('CREATE TABLE fixture(value)');db.commit()
            else:target.write_bytes(b'simulator')
        with closing(sqlite3.connect(installation/'IFsInit.db')) as db:
            db.executescript("CREATE TABLE IFsInit(Variable,Value);INSERT INTO IFsInit VALUES('LastYearHistory',2022);CREATE TABLE LoadFull(Variable,Value);INSERT INTO LoadFull VALUES('ModelVersion$','browser fixture');");db.commit()
        base=installation/'RUNFILES/IFsBase.run.db';base.unlink();run_file(base,list(range(2022,2031)))
        app.SETTINGS.write_text(json.dumps({'installation':str(installation.resolve())}))
        app.decode=fixture_decode
        root=app.DATA_ROOT/'companion'
        (root/'ai-settings.json').write_text(json.dumps({'endpoint':'http://localhost/v1','model':'fixture'}))
        service=Conversations(root,app.saved_installation,lambda *args:({},None),
            requester=lambda *args:{'role':'assistant','content':'Fixture answer. Independent chat history is working.'})
        server.conversations=service
        from jobs import Jobs
        server.jobs=Jobs(root)
        server.execution=Execution(app.saved_installation,lambda root:False)
        server.execution_token='fixture-execution-token'
        script="""import sys,time,sqlite3,io
from pathlib import Path
import numpy as np
root=Path(sys.argv[1]);time.sleep(1)
with sqlite3.connect(root/'RUNFILES/Working.run.db') as db:
 data=np.load(io.BytesIO(db.execute("SELECT Data FROM ifs_var_blob WHERE VariableName='GDP'").fetchone()[0]));data['value']*=1.1
 stream=io.BytesIO();np.save(stream,data);db.execute("UPDATE ifs_var_blob SET Data=? WHERE VariableName='GDP'",(stream.getvalue(),));db.commit()
(root/'RUNFILES/progress.txt').write_text(sys.argv[2]+',1.0')
"""
        def popen(command,**kwargs):return subprocess.Popen([sys.executable,'-c',script,str(installation),command[2]],**kwargs)
        server.runner=ScenarioRunner(app.DATA_ROOT,server.jobs,server.execution,app.saved_installation,validate_installation,popen)
        app.JOBS['fixture']={'status':'complete','report':{'run1':'Baseline.run.db','run2':'Education.run.db',
            'summaries':[],'audits':[],'buckets':{},'atol':0.000001,'rtol':0.00001}}
        example=service.create()
        service.append(example['id'],'user','Show the completed comparison.')
        service.append(example['id'],'assistant','Open this existing comparison in the reused Model Vetting interface.',
            [{'kind':'report','id':'fixture','title':'Review comparison results'}])
        text='CUSTOM,ylm,Kenya,1,2\n'
        approval={'id':'fixture-approval','owner':example['id'],'installation':str(installation.resolve()),'fingerprint':fingerprint(installation),
            'end_year':2030,'sha256':hashlib.sha256(text.encode()).hexdigest(),'text':text,'filename':'Fixture.sce','session':None,'draft':None}
        service.state(example['id'],'run-approval',approval)
        service.append(example['id'],'assistant','Review and run the isolated simulator. This never launches an actual IFs installation.',
            [{'kind':'run-review','id':approval['id'],'title':'Review simulator run'}])
        print(f'http://127.0.0.1:{server.server_port}',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:server.server_close()


if __name__=='__main__':main()
