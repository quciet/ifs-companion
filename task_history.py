"""Saved task history and deletion of task-owned artifacts."""
import json
from pathlib import Path
import re
import shutil


def checked_tree(root, relative):
    root=Path(root).resolve()
    path=root/relative
    if not path.resolve().is_relative_to(root) or path.resolve()==root:
        raise ValueError('Task data path is outside its storage folder.')
    for part in (path, *path.parents):
        if part==root: break
        if part.is_symlink() or part.is_junction(): raise ValueError('Task data contains a filesystem link.')
    if path.is_dir():
        for child in path.rglob('*'):
            if child.is_symlink() or child.is_junction(): raise ValueError('Task data contains a filesystem link.')
    return path


def report_ids(chat):
    return {link['id'] for message in chat['messages'] for link in message.get('links',[])
            if link.get('kind')=='report' and isinstance(link.get('id'),str)}


def sync_reports(conversations, reports, jobs=()):
    """Adopt old standalone reports once; existing chat links retain ownership."""
    with conversations.lock:
        chats=[conversations.read(c['id']) for c in conversations.list()['chats']]
        # A comparison may first appear while running directly in a tool, then
        # become attached to its originating chat. Keep only the real task.
        attached=set().union(*(report_ids(c) for c in chats if not conversations.state(c['id'],'legacy-report'))) if chats else set()
        for chat in list(chats):
            imported=conversations.state(chat['id'],'legacy-report')
            if imported in attached and len(chat['messages'])==1:
                conversations.delete(chat['id']);chats.remove(chat)
        known=set().union(*(report_ids(chat) for chat in chats)) if chats else set()
        for report in reports:
            identity=report['id']
            if identity in known: continue
            chat=conversations.create()
            conversations.append(chat['id'],'assistant','Saved comparison report.',
                                 [{'kind':'report','id':identity,'title':'Open comparison results'}])
            conversations.state(chat['id'],'legacy-report',identity)
            created=report.get('created') or chat['created']
            with conversations.connect() as db:
                db.execute('UPDATE chats SET title=?,created=?,updated=? WHERE id=?',
                           (report['title'],created,created,chat['id']))
            known.add(identity)
    result=conversations.list()
    report_owners={report:chat['id'] for chat in result['chats'] for report in report_ids(conversations.read(chat['id']))}
    running=set(result['busy'])
    running.update(job['owner'] for job in jobs if job['status']=='running' and job.get('owner'))
    running.update(report_owners[r['id']] for r in reports if r.get('status')=='running' and r['id'] in report_owners)
    result['running']=sorted(running)
    return result


def delete_task(handler, identity):
    service=handler.conversations()
    jobs=handler.jobs()
    # Keep a provider response from starting while deletion is in progress.
    with service.lock:
        chat=service.read(identity)
        if identity in service.active: raise ValueError('Stop this task before deleting it.')
        owned=jobs.list(identity)
        if any(j['status']=='running' or j['data'].get('recovery_required') for j in owned):
            raise ValueError('Finish or recover this task before deleting it.')
        reports=report_ids(chat)|{j['data']['backend_id'] for j in owned if j['kind']=='comparison'}
        others=[service.read(c['id']) for c in service.list()['chats'] if c['id']!=identity]
        shared=set().union(*(report_ids(c) for c in others)) if others else set()
        shared_reports=reports & shared
        reports-=shared_reports
        retained=[j for j in owned if j['kind']=='comparison' and j['data'].get('backend_id') in shared_reports]
        owned=[j for j in owned if j not in retained]
        related=[j for j in jobs.list() if j['kind']=='comparison' and j['data'].get('backend_id') in reports]
        if any(j['status']=='running' or j['data'].get('recovery_required') for j in related):
            raise ValueError('Finish or recover the comparison before deleting this task.')
        folders=[]
        for report in reports:
            if not re.fullmatch(r'[A-Za-z0-9_-]+',report): raise ValueError('Invalid saved report ID.')
            state=handler.task_app.JOBS.get(report,{})
            if state.get('status')=='running': raise ValueError('Finish the comparison before deleting this task.')
            folders.append(checked_tree(handler.task_app.DATA_ROOT,Path('results')/report))
        for job in owned:
            if job['kind']=='scenario_run':
                if not re.fullmatch(r'[A-Za-z0-9_-]+',job['id']): raise ValueError('Invalid saved run ID.')
                output=job['data'].get('output')
                other_reports=[v for k,v in handler.task_app.JOBS.items() if k not in reports]
                if output and (any(output in json.dumps(c) for c in others) or any(output in json.dumps(r) for r in other_reports)):
                    raise ValueError('A generated run is also used by another task.')
                folders.append(checked_tree(handler.task_app.DATA_ROOT,Path('runs')/job['id']))
        session=service.state(identity,'scenario-session')
        session_path=checked_tree(handler.tools().data,Path('ifs-scenario-builder')/'sessions.json')
        sessions=None
        # Idle tool processes cache saved data. Close them before changing that data.
        # stop() checks bridge/status and refuses to interrupt active work.
        if reports: handler.tools().stop('ifs-model-vetting')
        if session:
            handler.tools().stop('ifs-scenario-builder')
            if session_path.exists():
                sessions=json.loads(session_path.read_text(encoding='utf-8'))
                saved=sessions.pop(session,None)
                exported=(saved or {}).get('export',{}).get('path')
                if isinstance(exported,dict): exported=exported.get('__path__')
                if exported:
                    target=Path(exported)
                    base=handler.tools().data/'ifs-scenario-builder'
                    if not target.resolve().is_relative_to(base.resolve()): raise ValueError('Scenario file is outside task storage.')
                    # Do not remove an export still used by a different scenario session.
                    if not any(exported in json.dumps(s) for s in sessions.values()):
                        folders.append(checked_tree(base,target.resolve().relative_to(base.resolve())))
        for folder in folders:
            if folder.is_dir(): shutil.rmtree(folder)
            elif folder.exists(): folder.unlink()
        if sessions is not None:
            temporary=session_path.with_suffix('.delete.tmp')
            temporary.write_text(json.dumps(sessions),encoding='utf-8');temporary.replace(session_path)
        with handler.task_app.LOCK:
            for report in reports: handler.task_app.JOBS.pop(report,None)
        for job in owned: jobs.delete(job['id'])
        # Legacy comparison jobs may predate chat ownership.
        for job in jobs.list():
            if job['kind']=='comparison' and job['data'].get('backend_id') in reports:
                jobs.delete(job['id'])
        for job in retained:
            with jobs.db() as db: db.execute('UPDATE jobs SET owner=NULL WHERE id=?',(job['id'],))
        service.delete(identity)
    return {'deleted':identity}
