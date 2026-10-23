"""Package a single relocatable Python runtime and the Companion engine sources."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def build(destination, model):
    destination=Path(destination).resolve()
    destination.mkdir(parents=True,exist_ok=True)
    runtime=destination/'python'
    if runtime.exists(): raise ValueError('Build into a fresh directory.')
    runtime.mkdir()
    base=Path(sys.base_prefix)
    lock=json.loads((ROOT/'shared-python-lock.json').read_text(encoding='utf-8'))
    if '.'.join(map(str,sys.version_info[:2])) != lock['python']:
        raise ValueError('Build with Python '+lock['python'])
    for source in base.iterdir():
        if source.is_file() and (source.suffix in ('.exe','.dll') or source.name.startswith('LICENSE')):
            shutil.copy2(source,runtime/source.name)
    for name in ('Lib','DLLs','tcl'):
        shutil.copytree(base/name,runtime/name,ignore=shutil.ignore_patterns('site-packages','__pycache__','test','tests','idlelib','*.pyc'))
    python=runtime/'python.exe'
    subprocess.run([str(python),'-I','-m','ensurepip'],check=True)
    with tempfile.TemporaryDirectory() as temporary:
        requirements=Path(temporary)/'core.txt'
        requirements.write_text(''.join(f"{name} @ {lock['packages'][name]['url']} --hash=sha256:{lock['packages'][name]['sha256']}\n" for name in lock['core']),encoding='utf-8')
        subprocess.run([str(python),'-I','-m','pip','--isolated','install','--no-deps','--no-cache-dir','--no-compile',
                        '--only-binary=:all:','--require-hashes','-r',str(requirements)],check=True)
    subprocess.run([str(python),'-I','-c','import numpy,sqlite3,tkinter,ssl; print("Shared Python core verified")'],check=True)
    engine=destination/'engine';engine.mkdir()
    for name in ('desktop_launcher.py','companion_server.py','tool_manager.py','official_tools.py','shared_python.py',
                 'shared-python-lock.json','ai_settings.py','ai_usage.py','storage.py','update_cleanup.py','app_updates.py','installation_validation.py',
                 'shell.html','shell.js','shell.css','chat-workspace.js','task_history.py','conversations.py','execution.py','agent_workflows.py','jobs.py','scenario_runner.py','job-view.html','job-view.js'):
        shutil.copy2(ROOT/name,engine/name)
    for source in model.glob('*.py'):shutil.copy2(source,engine/source.name)
    for name in ('index.html','audit.js'):shutil.copy2(model/name,engine/name)
    for name in ('assets','python-bootstrap','decoder-runtime'):
        shutil.copytree(ROOT/name,engine/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    return runtime


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--destination',type=Path,required=True)
    parser.add_argument('--model',type=Path,default=ROOT.parent/'ifs-model-vetting')
    args=parser.parse_args()
    build(args.destination,args.model)
