"""Run approved scenario bytes using IFs' established future-mode CLI contract."""
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import sqlite3
import subprocess
import threading
import time
import tempfile
from contextlib import closing

WORKING=('Scenario/Working.sce','RUNFILES/Working.run.db','RUNFILES/SAMWorking.db',
         'RUNFILES/IFsPopWork.db','RUNFILES/ifsForDyadicWork.db','RUNFILES/progress.txt')
MARKER='.companion-recovery.json'


def fingerprint(root):
    """Bind approval to the model identity and baseline, not mutable working files."""
    root=Path(root).resolve()
    required=('IFsInit.db','net8/ifs.exe','RUNFILES/IFsBase.run.db','DATA/SAMBase.db','RUNFILES/IFsVar.db')
    result=[[name,(root/name).stat().st_size,(root/name).stat().st_mtime_ns] for name in required]
    for name in ('DATA/IFS.grp','DATA/IFs.db','DATA/DataDict.db','RUNFILES/IFs.db','DATA/IFsForDyadic.db'):
        stat=(root/name).stat() if (root/name).exists() else None
        result.append([name,stat.st_size if stat else None,stat.st_mtime_ns if stat else None])
    return result


def checked(root, relative):
    path=root/relative
    if path.is_symlink() or not path.resolve().is_relative_to(root):raise ValueError('IFs working paths must remain inside the selected installation.')
    return path


def database_copy(source, destination):
    destination=Path(destination)
    with tempfile.TemporaryDirectory(prefix='.companion-db-',dir=destination.parent) as temporary:
        staged=Path(temporary)/'copy.db'
        with closing(sqlite3.connect(Path(source).resolve().as_uri()+'?mode=ro',uri=True)) as origin:
            with closing(sqlite3.connect(staged)) as target:origin.backup(target)
        os.replace(staged,destination)


def scenario_name(filename):
    name=str(filename).replace('\\','/').rsplit('/',1)[-1]
    stem=name[:-4] if name.lower().endswith('.sce') else name
    if (not stem or stem!=stem.strip() or stem.endswith('.') or
        re.search(r'[<>:"/\\|?*\x00-\x1f]',stem) or
        stem.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}):
        raise ValueError('Choose a valid scenario name.')
    return stem


def log_tail(folder):
    parts=[]
    for name in ('console.log','ifs.log'):
        path=folder/name
        if path.exists():
            try:
                with path.open('rb') as stream:
                    stream.seek(max(0,path.stat().st_size-8192))
                    parts.append(name+':\n'+stream.read(8192).decode('utf-8',errors='replace'))
            except OSError:pass
    return '\n'.join(parts)


class ScenarioRunner:
    def __init__(self, root, jobs, execution, installation, validate, popen=subprocess.Popen, on_complete=None):
        self.root=(Path(root)/'runs').resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.jobs=jobs;self.execution=execution;self.installation=installation;self.validate=validate;self.popen=popen
        self.lock=threading.RLock();self.workers={}
        self.on_complete=on_complete
        self.closing=False

    def start(self, approval):
        with self.lock:
            if self.closing:raise ValueError('Companion is closing; no new IFs runs can start.')
            root=Path(self.installation() or '').resolve()
            if str(root)!=approval['installation'] or fingerprint(root)!=approval['fingerprint']:
                raise ValueError('The IFs installation changed. Review and approve the scenario again.')
            if hashlib.sha256(approval['text'].encode()).hexdigest()!=approval['sha256']:raise ValueError('Scenario approval is invalid.')
            name=scenario_name(approval.get('filename','Scenario.sce'))
            metadata=self.validate(root)
            if not (root/'Scenario').is_dir():raise ValueError('The IFs installation is missing its Scenario folder.')
            end=approval['end_year']
            if type(end)!=int or not metadata['base_year']<=end<=2100:raise ValueError('Select a run end year between the base year and 2100.')
            with self.execution.lock:
                mutable={str((root/name).resolve()).casefold() for name in WORKING}
                for active in self.jobs.list():
                    if active['kind']=='comparison' and active['status']=='running' and any(str(Path(path).resolve()).casefold() in mutable for path in active['data'].get('inputs',[])):
                        raise ValueError('A comparison is reading IFs working files. Wait for it to finish before running the model.')
                lease=self.execution.acquire('Scenario run')
            job=None
            try:
                job=self.jobs.create('scenario_run',approval['owner'],{'installation':str(root),'end_year':end,'sha256':approval['sha256'],'filename':approval.get('filename','Scenario.sce'),'approval_id':approval['id'],'stage':'preparing','base_year':metadata['base_year'],'scenario_name':name,'save_status':'pending','recovery_status':'not_needed'})
                folder=self.root/job['id'];folder.mkdir()
                (folder/(name+'.sce')).write_bytes(approval['text'].encode())
                (folder/'approval.json').write_text(json.dumps(approval),encoding='utf-8')
                stop=threading.Event()
                thread=threading.Thread(target=self.run,args=(job['id'],root,folder,end,lease['lease'],stop),daemon=True)
                self.workers[job['id']]={'stop':stop,'thread':thread,'process':None}
                thread.start();return job
            except Exception as exc:
                try:
                    if job:self.jobs.update(job['id'],'failed',error=str(exc),stage='finished')
                finally:self.execution.release(lease['lease'])
                raise

    def report_progress(self, identity, path, last):
        try:
            with path.open('rb') as stream:
                stream.seek(max(0,path.stat().st_size-2048))
                value=stream.read(2048).decode('utf-8',errors='replace').strip().splitlines()[-1]
            if value!=last:
                changes={'progress':value,'last_progress_at':time.time()}
                try:changes['current_year']=int(value.split(',')[0].strip())
                except ValueError:pass
                self.jobs.update(identity,**changes)
            return value
        except (OSError,IndexError):return last

    def restore(self, root, folder):
        manifest=json.loads((folder/'recovery.json').read_text(encoding='utf-8'))
        for relative,existed in manifest.items():
            if relative not in WORKING:raise ValueError('Invalid recovery manifest.')
            target=checked(root,relative)
            if relative.endswith('.db'):
                for suffix in ('-wal','-shm','-journal'):checked(root,relative+suffix).unlink(missing_ok=True)
            if existed:
                source=folder/'backup'/relative
                if source.is_symlink() or not source.resolve().is_relative_to(folder.resolve()):raise ValueError('Invalid backup path.')
                shutil.copy2(source,target)
            elif target.exists():target.unlink()
        marker=checked(root,MARKER)
        marker.unlink(missing_ok=True)
        try:
            self.remove_backup(folder)
            (folder/'recovery.json').unlink()
        except OSError:return 'Working files restored; backup cleanup remains at '+str(folder/'backup')

    @staticmethod
    def remove_backup(folder):
        backup=folder/'backup'
        if backup.is_symlink() or backup.resolve().parent!=folder.resolve():raise ValueError('Invalid backup cleanup path.')
        if backup.exists():shutil.rmtree(backup)

    def run(self, identity, root, folder, end, lease, stop):
        status='failed';error=None;process=None;marked=False;restored=True;run_error=None
        try:
            manifest={}
            for relative in WORKING:
                path=checked(root,relative);manifest[relative]=path.exists()
                if relative.endswith('.db') and any(Path(str(path)+suffix).exists() for suffix in ('-wal','-shm','-journal')):
                    raise ValueError('Close database users and checkpoint working database journals before running IFs.')
                if path.exists():
                    backup=folder/'backup'/relative;backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,backup)
            (folder/'recovery.json').write_text(json.dumps(manifest),encoding='utf-8')
            marker=checked(root,MARKER)
            with marker.open('x',encoding='utf-8') as stream:json.dump({'job':identity,'folder':str(folder)},stream)
            marked=True
            self.jobs.update(identity,recovery_required=True,recovery_status='backup_ready')
            if stop.is_set():raise InterruptedError('Run cancelled before execution.')
            database_copy(root/'RUNFILES/IFsBase.run.db',checked(root,'RUNFILES/Working.run.db'))
            database_copy(root/'DATA/SAMBase.db',checked(root,'RUNFILES/SAMWorking.db'))
            dyadic=root/'DATA/IFsForDyadic.db'
            if dyadic.exists():database_copy(dyadic,checked(root,'RUNFILES/ifsForDyadicWork.db'))
            name=self.jobs.get(identity)['data']['scenario_name']
            shutil.copy2(folder/(name+'.sce'),checked(root,'Scenario/Working.sce'))
            progress=checked(root,'RUNFILES/progress.txt');progress.unlink(missing_ok=True)
            command=[str(root/'net8/ifs.exe'),'5',str(end),'-1','true','true','1','false',
                     '--log',str(folder/'ifs.log'),'--websessionid',identity]
            with (folder/'console.log').open('wb') as log:
                process=self.popen(command,cwd=root/'net8',stdout=log,stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                with self.lock:self.workers[identity]['process']=process
                self.jobs.update(identity,stage='running',pid=process.pid,started_at=time.time())
                last=''
                while process.poll() is None:
                    if stop.wait(.3):self.terminate(process);raise InterruptedError('Run cancelled.')
                    last=self.report_progress(identity,progress,last)
                self.report_progress(identity,progress,last)
                if stop.is_set():raise InterruptedError('Run cancelled.')
                if process.returncode:
                    diagnostics=log_tail(folder)
                    errors=[line for line in diagnostics.splitlines() if re.search(r'error|exception|fatal|failed',line,re.I)]
                    raise ValueError(f'IFs exited with code {process.returncode}.'+(' '+ '\n'.join(errors[-5:]) if errors else ' See the model log for details.'))
            lines=progress.read_text(encoding='utf-8').strip().splitlines()
            if not lines:raise ValueError('IFs did not report the requested final year.')
            final_year=int(lines[-1].split(',')[0].strip())
            self.jobs.update(identity,current_year=final_year,last_progress_at=time.time())
            if final_year!=end:raise ValueError('IFs did not report the requested final year.')
            self.jobs.update(identity,stage='saving',save_status='saving',current_year=end)
            output=folder/(name+'.run.db');database_copy(root/'RUNFILES/Working.run.db',output)
            with closing(sqlite3.connect(output)) as db:
                if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('The completed run database is invalid.')
            self.jobs.update(identity,stage='restoring',output=str(output),save_status='saved')
            status='complete'
        except InterruptedError as exc:status='cancelled';error=str(exc)
        except Exception as exc:
            error=str(exc)
            if self.jobs.get(identity)['data'].get('save_status')=='saving':self.jobs.update(identity,save_status='failed')
        finally:
            run_error=error
            if process and process.poll() is None:
                try:self.terminate(process)
                except Exception as exc:error='Could not stop the owned IFs process: '+str(exc)
            alive=process is not None and process.poll() is None
            if marked and not alive:
                try:
                    self.jobs.update(identity,stage='restoring',recovery_status='restoring')
                    if self.execution.detector(root):raise ValueError('An external IFs process is using this installation.')
                    warning=self.restore(root,folder)
                    if warning:self.jobs.update(identity,cleanup_warning=warning)
                except Exception as exc:restored=False;error=(run_error+' ' if run_error else '')+'Working-file recovery is required: '+str(exc)
            elif marked:restored=False
            elif (folder/'backup').exists():
                try:self.remove_backup(folder)
                except OSError as exc:error='Backup cleanup remains: '+str(exc);status='failed'
            if not restored:status='failed'
            try:self.jobs.update(identity,status,stage='finished' if restored else 'recovery_required',error=error,recovery_required=not restored,recovery_status='restored' if marked and restored else ('required' if not restored else 'not_needed'),finished_at=time.time(),run_error=run_error,log_tail=log_tail(folder))
            finally:
                # Never release the reservation while the owned process is still alive.
                if not alive:
                    self.execution.release(lease)
            if self.on_complete:
                try:self.on_complete(self.jobs.get(identity))
                except (OSError,ValueError):pass
            if not alive:
                with self.lock:self.workers.pop(identity,None)

    @staticmethod
    def terminate(process):
        if process.poll() is not None:return
        if os.name=='nt':
            result=subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=5,creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode and process.poll() is None:process.terminate()
        else:process.terminate()
        process.wait(timeout=15)

    def cancel(self, identity):
        with self.lock:
            if identity not in self.workers:raise ValueError('This run is no longer active.')
            self.workers[identity]['stop'].set()
        return self.jobs.update(identity,stage='stopping')

    def recover(self, identity):
        job=self.jobs.get(identity);folder=(self.root/identity).resolve()
        if job['kind']!='scenario_run' or folder.parent!=self.root.resolve():raise ValueError('Invalid recovery job.')
        root=Path(job['data']['installation']).resolve()
        if root!=Path(self.installation() or '').resolve():raise ValueError('Select the original IFs installation before recovery.')
        marker=json.loads(checked(root,MARKER).read_text(encoding='utf-8'))
        if marker!={'job':identity,'folder':str(folder)}:raise ValueError('Recovery marker does not match this job.')
        lease=self.execution.acquire('Working-file recovery',recovery=True)
        try:
            warning=self.restore(root,folder)
            return self.jobs.update(identity,recovery_required=False,recovery_status='restored',stage='recovered',cleanup_warning=warning,error=job['data'].get('run_error'))
        finally:self.execution.release(lease['lease'])

    def save_to_ifs(self, identity, name=None):
        job=self.jobs.get(identity)
        if job['kind']!='scenario_run' or (job['status']!='complete' and job['data'].get('save_status')!='saved') or job['status']=='running' or job['data'].get('recovery_required'):
            raise ValueError('Only a completed, recovered run can be saved to IFs.')
        root=Path(self.installation() or '').resolve()
        if root!=Path(job['data']['installation']).resolve():
            raise ValueError('Select the original IFs installation before saving.')
        folder=(self.root/identity).resolve()
        if folder.parent!=self.root or folder.is_symlink():raise ValueError('Invalid run folder.')
        if name is not None and (not isinstance(name,str) or '/' in name or '\\' in name or not name):raise ValueError('Choose a scenario name without a folder path.')
        stem=scenario_name(name or job['data'].get('scenario_name') or job['data']['filename'])
        if stem.casefold() in {'working','ifsbase'}:raise ValueError('Choose a name other than Working or IFsBase when saving to IFs.')
        source=Path(job['data']['output'])
        scenario=folder/(job['data'].get('scenario_name','approved')+'.sce')
        if source.is_symlink() or source.resolve().parent!=folder or scenario.is_symlink() or scenario.resolve().parent!=folder:raise ValueError('Invalid run artifact.')
        targets=[checked(root,'Scenario/'+stem+'.sce'),checked(root,'RUNFILES/'+stem+'.run.db')]
        lease=self.execution.acquire('Save scenario to IFs')
        created=[]
        try:
            if any(target.exists() for target in targets):
                raise ValueError('A scenario or run with this name already exists in IFs. Choose another name.')
            for origin,target in zip((scenario,source),targets):
                with origin.open('rb') as incoming, target.open('xb') as outgoing:
                    created.append(target)
                    shutil.copyfileobj(incoming,outgoing)
            return self.jobs.update(identity,saved_to_ifs={'scenario':str(targets[0]),'run':str(targets[1]),'saved_at':time.time()})
        except Exception:
            for target in created:target.unlink(missing_ok=True)
            raise
        finally:self.execution.release(lease['lease'])

    def close(self):
        with self.lock:self.closing=True;workers=list(self.workers.values())
        for worker in workers:worker['stop'].set()
        for worker in workers:worker['thread'].join(timeout=35)
        if any(w['thread'].is_alive() or (w['process'] and w['process'].poll() is None) for w in workers):raise ValueError('IFs is still stopping; keep Companion open until working files are restored.')
