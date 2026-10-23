"""Durable jobs and events shared by chat, comparison and scenario execution."""
from contextlib import contextmanager
import json
from pathlib import Path
import secrets
import sqlite3
import time
import os

TERMINAL = {'complete','failed','cancelled','interrupted'}


def process_alive(pid, created=None):
    """Inspect a process without sending signals on Windows; tolerate denied access."""
    if not isinstance(pid,int) or pid<=0:return False
    if os.name=='nt':
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
        kernel.GetProcessTimes.argtypes=[wintypes.HANDLE,*[ctypes.POINTER(wintypes.FILETIME)]*4]
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        handle=kernel.OpenProcess(0x1000,False,pid)
        if not handle:return ctypes.get_last_error()!=87
        try:
            code=wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle,ctypes.byref(code)):return True
            if code.value!=259:return False
            if created is not None:
                times=[wintypes.FILETIME() for _ in range(4)]
                if kernel.GetProcessTimes(handle,*[ctypes.byref(t) for t in times]):
                    born=((times[0].dwHighDateTime<<32)|times[0].dwLowDateTime)/10_000_000-11644473600
                    if born>created+1:return False
            return True
        finally:kernel.CloseHandle(handle)
    try:os.kill(pid,0);return True
    except ProcessLookupError:return False
    except PermissionError:return True



class Jobs:
    def __init__(self, root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.path=self.root/'jobs.sqlite3'
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,kind TEXT,owner TEXT,status TEXT,created REAL,updated REAL,data TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY,job TEXT,created REAL,data TEXT)')

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=20)
        try:
            with db:yield db
        finally:db.close()

    def create(self, kind, owner=None, data=None, identity=None):
        identity=identity or secrets.token_hex(16);now=time.time()
        data={'manager_pid':os.getpid(),**(data or {})}
        with self.db() as db:
            db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?)',(identity,kind,owner,'running',now,now,json.dumps(data)))
            db.execute('INSERT INTO events(job,created,data) VALUES(?,?,?)',(identity,now,json.dumps({'status':'running'})))
        return self.get(identity)

    def get(self, identity):
        with self.db() as db:row=db.execute('SELECT * FROM jobs WHERE id=?',(identity,)).fetchone()
        if not row:raise ValueError('Unknown job.')
        return {**dict(zip(('id','kind','owner','status','created','updated'),row[:6])), 'data':json.loads(row[6])}

    def update(self, identity, status=None, **changes):
        with self.db() as db:
            # Reserve the write transaction before reading to avoid lost progress updates.
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT status,data FROM jobs WHERE id=?',(identity,)).fetchone()
            if not row:raise ValueError('Unknown job.')
            old,data=row[0],json.loads(row[1]);data.update(changes)
            if old in TERMINAL and changes.get('stage')=='stopping':return self.get(identity)
            if old in TERMINAL and status and status!=old:raise ValueError('A finished job cannot be restarted.')
            now=time.time();status=status or old
            db.execute('UPDATE jobs SET status=?,updated=?,data=? WHERE id=?',(status,now,json.dumps(data),identity))
            db.execute('INSERT INTO events(job,created,data) VALUES(?,?,?)',(identity,now,json.dumps({'status':status,**changes})))
        return self.get(identity)

    def list(self, owner=None):
        with self.db() as db:
            rows=db.execute('SELECT id FROM jobs'+(' WHERE owner=?' if owner else '')+' ORDER BY created DESC', (owner,) if owner else ()).fetchall()
        return [self.get(row[0]) for row in rows]

    def delete(self, identity):
        with self.db() as db:
            row=db.execute('SELECT status,data FROM jobs WHERE id=?',(identity,)).fetchone()
            if not row: return
            if row[0]=='running' or json.loads(row[1]).get('recovery_required'):
                raise ValueError('Finish or recover this task before deleting it.')
            db.execute('DELETE FROM events WHERE job=?',(identity,))
            db.execute('DELETE FROM jobs WHERE id=?',(identity,))

    def events(self, after=0):
        with self.db() as db:rows=db.execute('SELECT seq,job,created,data FROM events WHERE seq>? ORDER BY seq LIMIT 500',(int(after),)).fetchall()
        return [{'seq':r[0],'job':r[1],'created':r[2],**json.loads(r[3])} for r in rows]

    def claim(self, identity, owner):
        with self.db() as db:
            row=db.execute('SELECT owner FROM jobs WHERE id=?',(identity,)).fetchone()
            if not row:raise ValueError('Unknown job.')
            if row[0] and row[0]!=owner:raise ValueError('This job belongs to another chat.')
            db.execute('UPDATE jobs SET owner=? WHERE id=?',(owner,identity))

    def interrupt(self, kinds):
        for job in self.list():
            if job['status']=='running' and job['kind'] in kinds:
                pid=job['data'].get('manager_pid')
                if pid and process_alive(pid,job['created']):continue
                recovery=bool(job['data'].get('recovery_required'))
                message='Companion stopped before this job finished.'+(' Restore the backed-up IFs working files before continuing.' if recovery else ' No active worker remains.')
                self.update(job['id'],'interrupted',stage='recovery_required' if recovery else 'finished',
                            recovery_status='required' if recovery else job['data'].get('recovery_status','not_needed'),message=message,error=message)
