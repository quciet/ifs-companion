"""One installation-wide execution reservation, shared across Companion processes."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import threading
import time


def external_run(installation):
    if os.name != 'nt': return False
    script = "$ErrorActionPreference='Stop'; Get-CimInstance Win32_Process -Filter \"Name='ifs.exe'\" | Select-Object ProcessId,ExecutablePath | ConvertTo-Json -Compress"
    try:
        result = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],
            capture_output=True,text=True,timeout=15,creationflags=subprocess.CREATE_NO_WINDOW)
    except subprocess.SubprocessError:
        raise ValueError('Could not check whether IFs is already running.') from None
    if result.returncode: raise ValueError('Could not check whether IFs is already running.')
    processes=json.loads(result.stdout.strip() or '[]')
    if isinstance(processes,dict): processes=[processes]
    if not isinstance(processes,list) or any(not isinstance(item,dict) for item in processes):
        raise ValueError('Could not inspect the IFs process list.')
    root=Path(installation).resolve()
    return any(not item.get('ExecutablePath') or Path(item['ExecutablePath']).resolve().is_relative_to(root) for item in processes)


class Execution:
    def __init__(self, installation, detector=external_run):
        self.installation=installation
        self.detector=detector
        self.lock=threading.RLock()
        self.reservation=None
        self.file=None

    def acquire(self, owner, recovery=False):
        with self.lock:
            if self.reservation: raise ValueError('The IFs installation is reserved by '+self.reservation['owner']+'.')
            root=self.installation()
            if not root: raise ValueError('Select an IFs installation first.')
            if not recovery and (Path(root)/'.companion-recovery.json').exists():
                raise ValueError('A previous IFs run requires working-file recovery before another run can start.')
            path=Path(root).resolve()/'.companion-execution.lock'
            if path.is_symlink():raise ValueError('The IFs reservation path must not be a link.')
            stream=open(path,'a+b')
            try:
                stream.seek(0,2)
                if stream.tell()==0:stream.write(b'\0');stream.flush()
                stream.seek(0)
                if stream.read(1)!=b'\0':raise OSError('Unrecognized reservation file')
                stream.seek(0)
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError:
                stream.close()
                raise ValueError('This IFs installation is reserved by another Companion process.') from None
            try:
                if self.detector(root): raise ValueError('IFs is already running for this installation. Wait for it to finish.')
                record={'lease':secrets.token_hex(24),'owner':owner,'installation':str(root),'created':time.time()}
                stream.seek(1);stream.truncate();stream.write(json.dumps({**record,'pid':os.getpid()}).encode());stream.flush()
                self.file=stream;self.reservation=record
                return dict(record)
            except Exception:
                stream.close()
                raise

    def release(self, lease):
        with self.lock:
            if not self.reservation or not secrets.compare_digest(str(lease),self.reservation['lease']):
                raise ValueError('Unknown IFs execution reservation.')
            self.file.close();self.file=None;self.reservation=None
            return {'released':True}

    def status(self):
        with self.lock:
            return {'running':bool(self.reservation),'owner':self.reservation['owner'] if self.reservation else None}

    def close(self):
        with self.lock:
            if self.file:self.file.close()
            self.file=None;self.reservation=None
