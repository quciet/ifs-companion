"""Thin desktop adapter for the sibling model-vetting tool; no plugin framework."""
import json
import os
from pathlib import Path
import sys
import secrets
import threading
import hashlib
import io
from jobs import Jobs, TERMINAL
from scenario_runner import ScenarioRunner, fingerprint, WORKING, log_tail
import tempfile
import urllib.error
from tool_manager import ToolManager, MAX_UPLOAD
from official_tools import OfficialTools
import ai_settings
from conversations import Conversations
from task_history import sync_reports, delete_task
from execution import Execution
import storage
from app_updates import AppUpdates
from installation_validation import validate_installation
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent
if not getattr(sys, 'frozen', False) and not os.environ.get('IFS_COMPANION_PACKAGED'):
    tool = Path(os.environ.get('IFS_MODEL_VETTING_PATH', ROOT.parent/'ifs-model-vetting')).resolve()
    if not (tool/'app.py').is_file():
        raise RuntimeError('Model-vetting source is missing. Clone ifs-model-vetting beside ifs-companion or set IFS_MODEL_VETTING_PATH.')
    sys.path.insert(0, str(tool))
import app

class Handler(app.Handler):
    task_app = app
    def service_lock(self):
        with app.LOCK:
            if not hasattr(self.server,'service_lock'):self.server.service_lock=threading.RLock()
        return self.server.service_lock

    def approval_lock(self):
        with self.service_lock():
            if not hasattr(self.server,'approval_lock'):self.server.approval_lock=threading.Lock()
        return self.server.approval_lock

    def jobs(self):
        with self.service_lock():
            if not hasattr(self.server,'jobs'):
                self.server.jobs=Jobs(app.DATA_ROOT/'companion')
                self.server.jobs.interrupt({'chat','scenario_run'})
                for job in self.server.jobs.list():
                    if job['kind']=='scenario_run' and job['data'].get('output'):
                        candidate=(app.DATA_ROOT/'runs'/job['id']/Path(job['data']['output']).name).resolve()
                        if candidate.is_relative_to((app.DATA_ROOT/'runs').resolve()) and candidate.is_file() and str(candidate)!=job['data']['output']:
                            previous=job['data'].get('previous_outputs',[])
                            self.server.jobs.update(job['id'],output=str(candidate),previous_outputs=[*previous,job['data']['output']])
            return self.server.jobs

    def runner(self):
        with self.service_lock():
            if not hasattr(self.server,'runner'):
                self.server.runner=ScenarioRunner(app.DATA_ROOT,self.jobs(),self.execution(),app.saved_installation,validate_installation,on_complete=self.publish_run_result)
            return self.server.runner

    def publish_run_result(self, job):
        owner=job['owner']
        if not owner:return
        links=[{'kind':'job','id':job['id'],'title':'View scenario run'}]
        if job['status']=='complete':
            root=Path(job['data']['installation'])
            links.append({'kind':'comparison','title':'Choose comparison indicators','context':{'a':str(root/'RUNFILES/IFsBase.run.db'),'comparisons':[job['data']['output']],'variables':[]}})
            text='The scenario run finished through '+str(job['data']['end_year'])+'. Its saved output is ready to compare with the baseline. Choose indicators in Model Vetting, or ask me to use the selection discussed earlier.'
        else:text='Scenario run '+job['status']+'. '+str(job['data'].get('error') or 'Open the job for details.')
        self.conversations().append(owner,'assistant',text,links)
        self.jobs().update(job['id'],notification_sent=True)

    def installation_layout(self):
        installation=app.saved_installation()
        layout=app.installation_layout(installation) if installation else app.empty_installation()
        if installation:
            for job in self.jobs().list():
                output=job['data'].get('output')
                if job['kind']=='scenario_run' and job['status']=='complete' and job['data'].get('installation')==str(Path(installation).resolve()) and output and Path(output).is_file():
                    if output not in layout['runs']:layout['runs'].append(output)
                    layout['labels'][output]='Scenario '+job['id'][:8]+' · '+str(job['data']['end_year'])
        return layout

    def reconcile_jobs(self):
        self.jobs().interrupt({'chat','scenario_run'})
        with app.LOCK:existing=[(key,dict(value)) for key,value in app.JOBS.items() if not value.get('_parent')]
        for backend,state in existing:
            identity='comparison-'+backend
            try:self.jobs().get(identity)
            except ValueError:
                self.jobs().create('comparison',data={'backend_id':backend},identity=identity)
                if state['status']!='running':self.jobs().update(identity,{'stopped':'cancelled'}.get(state['status'],state['status']),progress=state.get('progress',''))
        for job in self.jobs().list():
            if job['kind']=='knowledge' and job['status']=='running':
                try:
                    with self.tools().request('ifs-code-reader','api/state') as response:state=json.load(response)['job']
                    status={'idle':'cancelled'}.get(state['status'],state['status']);progress=state.get('message','')
                    if status!='running' or progress!=job['data'].get('progress'):
                        self.jobs().update(job['id'],status,progress=progress,answer_id=state.get('answer_id'))
                except (ValueError,OSError):self.jobs().update(job['id'],'interrupted',message='Knowledge backend is unavailable.')
                continue
            if job['kind']!='comparison' or job['status']!='running':continue
            backend=job['data']['backend_id']
            try:
                if self.comparison_running():
                    with self.tools().request('ifs-model-vetting','api/job?job='+backend) as response:state=json.load(response)
                else:
                    state=app.JOBS.get(backend)
                    if state is None:
                        app.restore_jobs();state=app.JOBS.get(backend)
                if state is None:
                    self.jobs().update(job['id'],'interrupted',message='Comparison backend is unavailable. Reopen its saved report if present.');continue
                status={'stopped':'cancelled'}.get(state['status'],state['status'])
                progress=state.get('progress',state.get('error',''))
                if status!='running' or progress!=job['data'].get('progress'):
                    self.jobs().update(job['id'],status,progress=progress)
            except (ValueError,OSError):pass

    def send(self, data, content='application/json', status=200):
        if isinstance(data,dict) and isinstance(data.get('messages'),list):
            relocated={old:job['data']['output'] for job in self.jobs().list() if job['kind']=='scenario_run' and job['data'].get('output') for old in job['data'].get('previous_outputs',[])}
            for message in data['messages']:
                for link in message.get('links',[]):
                    if link.get('kind')=='comparison':
                        context=link.get('context',{})
                        context['a']=relocated.get(context.get('a'),context.get('a'))
                        context['comparisons']=[relocated.get(path,path) for path in context.get('comparisons',[])]
        if self.path in ('/tools/ifs-code-reader/api/index','/tools/ifs-code-reader/api/semantic','/tools/ifs-code-reader/api/ask','/tools/ifs-code-reader/api/search') and status==200:
            parsed=json.loads(data) if isinstance(data,bytes) else data
            if isinstance(parsed,dict) and parsed.get('status')=='running':
                self.jobs().create('knowledge',data={'action':self.path.rsplit('/',1)[-1],'progress':parsed.get('message','')})
        # Observe existing comparison submissions without changing their engine/API.
        if self.path=='/api/compare' and status==200:
            parsed=json.loads(data) if isinstance(data,bytes) else data
            if isinstance(parsed,dict) and parsed.get('job'):
                identity='comparison-'+parsed['job']
                try:self.jobs().get(identity)
                except ValueError:self.jobs().create('comparison',data={'backend_id':parsed['job'],'inputs':getattr(self,'comparison_inputs',[])},identity=identity)
        try:return super().send(data,content,status)
        except (BrokenPipeError,ConnectionResetError):return None

    def prepare_run(self, request):
        owner=request.get('chat');chat=self.conversations().read(owner)
        root=app.saved_installation()
        if not root or str(root)!=chat['installation']:raise ValueError('The installation changed. Start a new chat.')
        metadata=validate_installation(root);end=request.get('end_year')
        if type(end)!=int or not metadata['base_year']<=end<=2100:raise ValueError('Choose an end year between the base year and 2100.')
        self.tools().start('ifs-scenario-builder',root)
        try:
            with self.tools().request('ifs-scenario-builder','bridge/capabilities') as response:
                if not json.load(response).get('approved_execution'):raise ValueError('Update Scenario Builder before reviewing model execution.')
        except urllib.error.HTTPError:raise ValueError('Update Scenario Builder before reviewing model execution.') from None
        source=request.get('source')
        if source is not None:
            operation='validate_file';body={'source':source}
        else:
            session=self.conversations().state(owner,'scenario-session')
            if not session or session!=request.get('session'):raise ValueError('This scenario does not belong to the selected chat.')
            operation='preview';body={'session':session,'draft':request.get('draft')}
        with self.tools().request('ifs-scenario-builder','api/scenario/'+operation,'POST',json.dumps(body).encode()) as response:
            preview=json.load(response)
        text=preview['text'];identity=secrets.token_hex(24)
        approval={'id':identity,'owner':owner,'installation':str(Path(root).resolve()),'fingerprint':fingerprint(root),
            'end_year':end,'sha256':hashlib.sha256(text.encode()).hexdigest(),'text':text,'filename':preview['filename'],
            'session':body.get('session'),'draft':body.get('draft')}
        self.conversations().state(owner,'run-approval',approval)
        return approval
    def execution(self):
        with self.service_lock():
            if not hasattr(self.server,'execution'):
                self.server.execution=Execution(app.saved_installation)
                self.server.execution_token=secrets.token_urlsafe(32)
            controller=self.server.execution
        if controller.reservation and controller.reservation['owner']=='Autotune':
            state=getattr(getattr(self.server,'tools',None),'processes',{}).get('ifs-autotune')
            if state and state['process'].poll() is not None:
                with controller.lock:
                    if controller.reservation and controller.reservation['owner']=='Autotune':controller.release(controller.reservation['lease'])
        return controller

    def conversations(self):
        with self.service_lock():
            if not hasattr(self.server, 'conversations'):
                self.server.conversations = Conversations(app.DATA_ROOT / 'companion', app.saved_installation, self.chat_operation)
        return self.server.conversations

    def stop_chat(self, identity):
        service=self.conversations();result=service.stop(identity)
        if service.state(identity,'scenario-active'):
            session=service.state(identity,'scenario-session')
            def stop_scenario():
                try:
                    with self.tools().request('ifs-scenario-builder','bridge/stop','POST',json.dumps({'session':session}).encode()) as response:response.read()
                except (OSError,ValueError):pass
            threading.Thread(target=stop_scenario,daemon=True).start()
        return result

    def chat_operation(self, name, args, conversation):
        installation = app.saved_installation()
        layout = self.installation_layout()
        if name=='jobs':return {'jobs':self.jobs().list(conversation)},None
        if name=='job':return self.jobs().get(args['id']),None
        if name=='run_scenario':
            review=self.conversations().state(conversation,'scenario-review') or {}
            draft=review.get('draft') or review.get('confirmation') or {}
            approval=self.prepare_run({'chat':conversation,'session':self.conversations().state(conversation,'scenario-session'),
                'draft':draft.get('id'),'end_year':args['end_year']})
            return {'status':'execution approval required','sha256':approval['sha256'],'end_year':approval['end_year']}, {'kind':'run-review','id':approval['id'],'title':'Review and approve IFs execution'}
        if name == 'installation': return layout, None
        if name == 'indicators':
            if args['path'] not in layout['runs']: raise ValueError('Choose a run in the selected installation.')
            metadata=app.metadata(args['path'])
            query=str(args.get('query','')).casefold()
            items=[(key,value) for key,value in metadata['variables'].items() if query in key.casefold() or query in str(value.get('display','')).casefold()]
            return {'variables':dict(items[:200]),'matching':len(items),'shown':min(200,len(items))}, None
        if name in ('reports','report'):
            if name=='report':
                identity=args['id']
                if not isinstance(identity,str) or not identity.isalnum():raise ValueError('Invalid comparison ID.')
            if self.comparison_running():
                with self.tools().request('ifs-model-vetting','api/recent' if name=='reports' else 'api/job?job='+identity) as response:
                    result=json.load(response)
            elif name=='reports':
                result={'jobs':[{'id':key,'status':value['status'],'baseline':value.get('report',{}).get('run1',value.get('run1')),
                    'comparison':value.get('report',{}).get('run2',value.get('run2'))} for key,value in app.JOBS.items() if not value.get('_parent')]}
            else:
                if identity not in app.JOBS:raise ValueError('Unknown comparison.')
                result=dict(app.JOBS[identity])
            if name=='report' and result.get('report'):
                report=result['report'];variable=args.get('variable')
                summaries=[row for row in report.get('summaries',[]) if not variable or row.get('variable')==variable]
                audits=[row for row in report.get('audits',[]) if not variable or row.get('base_variable')==variable]
                result={'status':result['status'],'baseline':report['run1'],'comparison':report['run2'],
                    'summaries':summaries[:100],'summary_count':len(summaries),'audits':audits[:30],'audit_count':len(audits),
                    'note':'Numerical differences are descriptive evidence, not causal attribution.'}
            return result, None
        if name == 'comparison':
            runs = args['comparisons']
            if not isinstance(runs, list) or not runs or not isinstance(args['variables'], list) or not args['variables']:
                raise ValueError('Select comparison runs and indicators.')
            if any(p not in layout['runs'] for p in [args['a'], *runs]): raise ValueError('Run is not in the selected installation.')
            return {'status':'selection ready for user review; not started'}, {'kind':'comparison', 'title':'Review comparison setup', 'context':args}
        if name in ('knowledge','knowledge_read'):
            self.tools().start('ifs-code-reader', installation)
            try:
                with self.tools().request('ifs-code-reader','bridge/capabilities') as response:
                    if not json.load(response).get('shared_evidence'):raise ValueError('Update Code Interpreter to enable shared chat knowledge.')
            except urllib.error.HTTPError:raise ValueError('Update Code Interpreter to enable shared chat knowledge.') from None
            endpoint='api/evidence' if name=='knowledge' else 'api/research'
            with self.tools().request('ifs-code-reader', endpoint, 'POST', json.dumps(args).encode()) as response:
                return json.load(response), None
        if name == 'scenario':
            self.tools().start('ifs-scenario-builder', installation)
            try:
                with self.tools().request('ifs-scenario-builder','bridge/capabilities') as response:
                    if not json.load(response).get('chat_review'):raise ValueError('Update Scenario Builder to enable main-chat reviews.')
            except urllib.error.HTTPError:raise ValueError('Update Scenario Builder to enable main-chat reviews.') from None
            body = {'message':args['message']}
            session = self.conversations().state(conversation, 'scenario-session')
            if not session:
                with self.tools().request('ifs-scenario-builder','api/scenario/new','POST',b'{}') as response:
                    session=json.load(response)['session']
                self.conversations().state(conversation,'scenario-session',session)
            body['session'] = session
            self.conversations().state(conversation,'scenario-active',True)
            try:
                with self.tools().request('ifs-scenario-builder', 'api/scenario/chat', 'POST', json.dumps(body).encode()) as response:
                    result = json.load(response)
            finally:self.conversations().state(conversation,'scenario-active',False)
            self.conversations().state(conversation, 'scenario-session', result['session'])
            self.conversations().state(conversation, 'scenario-review', result)
            return result, {'kind':'scenario','id':'ifs-scenario-builder','title':'Review scenario', 'context':result}
        if name == 'open_tool':
            identity = args['id']
            if identity not in ('ifs-autotune','ifs-scenario-builder','ifs-code-reader'): raise ValueError('Unsupported capability.')
            self.tools().read(identity)
            return {'status':'workspace link ready'}, {'kind':'tool','id':identity,'title':{'ifs-autotune':'Open Autotune','ifs-scenario-builder':'Build and review scenario','ifs-code-reader':'Inspect IFs knowledge'}[identity]}
        raise ValueError('Unknown operation.')

    def updater(self):
        with app.LOCK:
            if not hasattr(self.server, 'updater'):
                self.server.updater = AppUpdates(app.DATA_ROOT, storage.app_directory(), frozen=bool(getattr(sys,'frozen',False) or os.environ.get('IFS_COMPANION_PACKAGED')))
        return self.server.updater

    def tools(self):
        if not hasattr(self.server, 'tools'):
            self.server.tools = ToolManager(app.DATA_ROOT / 'companion')
            self.server.tool_token = secrets.token_urlsafe(32)
        self.server.tools.before_change = self.comparison_guard
        self.execution()
        self.server.tools.execution_url=f'http://127.0.0.1:{self.server.server_port}/api/execution'
        self.server.tools.execution_token=self.server.execution_token
        return self.server.tools

    def comparison_guard(self, identity):
        if identity == 'ifs-model-vetting':
            with app.LOCK:
                if any(j['status'] == 'running' for j in app.JOBS.values()):
                    raise ValueError('Wait for the current comparison to finish before changing this tool.')

    def official(self):
        if not hasattr(self.server, 'official_tools'):
            self.server.official_tools = OfficialTools(self.tools())
        return self.server.official_tools

    def comparison_running(self):
        state = self.tools().processes.get('ifs-model-vetting')
        return bool(state and state['process'].poll() is None)

    def comparison_proxy(self, method, path=None):
        size = int(self.headers.get('Content-Length', 0))
        if size < 0 or size > 8 * 1024**2: raise ValueError('Comparison request is too large.')
        data = self.rfile.read(size) if method == 'POST' else None
        try: response = self.tools().request('ifs-model-vetting', path or self.path, method, data)
        except urllib.error.HTTPError as error: response = error
        with response:
            return self.send(response.read(), response.headers.get('Content-Type', 'application/octet-stream'), status=response.status)

    def tool_access(self, mutate=False):
        self.tools()
        origin = f'http://127.0.0.1:{self.server.server_port}'
        if self.headers.get('Host') != origin.removeprefix('http://'):
            raise ValueError('Open Companion using its local address.')
        if self.headers.get('Origin') not in (None, origin):
            raise ValueError('Requests must come from Companion.')
        if mutate and not secrets.compare_digest(self.headers.get('X-Companion-Token', ''), self.server.tool_token):
            raise ValueError('Reload Companion before managing tools.')

    def proxy_tool(self, method):
        self.tool_access(mutate=method != 'GET')
        if method=='POST' and self.path in ('/tools/ifs-code-reader/api/index','/tools/ifs-code-reader/api/semantic','/tools/ifs-code-reader/api/ask','/tools/ifs-code-reader/api/search'):
            self.reconcile_jobs()
        _, _, identity, path = self.path.split('/', 3)
        size = int(self.headers.get('Content-Length', 0))
        if size < 0 or size > 8 * 1024**2: raise ValueError('Request too large.')
        data = self.rfile.read(size) if method == 'POST' else None
        try:
            response = self.tools().request(identity, path, method, data)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return self.send(response.read(), response.headers.get('Content-Type', 'application/octet-stream'), status=response.status)

    def tool_post(self):
        self.tool_access(mutate=True)
        if self.path.startswith('/api/tools/install'):
            size = int(self.headers.get('Content-Length', 0))
            if not 0 < size <= MAX_UPLOAD: raise ValueError('Choose a tool package smaller than 4 GB.')
            expected = parse_qs(urlparse(self.path).query).get('id', [None])[0]
            with tempfile.TemporaryFile() as upload:
                remaining = size
                while remaining:
                    chunk = self.rfile.read(min(remaining, 1024 * 1024))
                    if not chunk: raise ValueError('Upload interrupted. The previous tool is unchanged.')
                    upload.write(chunk); remaining -= len(chunk)
                upload.seek(0)
                result = self.tools().install(upload, expected, allow_older=parse_qs(urlparse(self.path).query).get('allow_older') == ['1'])
                if result['id'] == 'ifs-model-vetting': (self.tools().root / 'comparison-removed').unlink(missing_ok=True)
                return self.send(result)
        size = int(self.headers.get('Content-Length', 0))
        if not 0 < size < 16384: raise ValueError('Invalid tool request.')
        request = json.loads(self.rfile.read(size))
        identity = request.get('id')
        if self.path == '/api/tools/official-install': return self.send(self.official().begin(identity))
        if self.path == '/api/tools/open': return self.send(self.tools().start(identity, app.saved_installation()))
        if self.path == '/api/tools/close':
            result = self.tools().stop(identity)
            if identity == 'ifs-model-vetting': app.restore_jobs()
            return self.send(result)
        if self.path == '/api/tools/uninstall':
            if identity == 'ifs-model-vetting' and not self.tools()._folder(identity).exists():
                self.comparison_guard(identity)
                result = {'removed': identity, 'data_preserved': True}
            else:
                result = self.tools().uninstall(identity, close_idle=True)
            if identity == 'ifs-model-vetting': (self.tools().root / 'comparison-removed').touch()
            if identity == 'ifs-model-vetting': app.restore_jobs()
            return self.send(result)
        raise ValueError('Unknown tool action.')

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ('/job-view','/run-review','/job-view.js'):
            self.tool_access()
            filename='job-view.js' if path.endswith('.js') else 'job-view.html'
            return self.send((ROOT/filename).read_bytes(),'text/javascript' if filename.endswith('.js') else 'text/html; charset=utf-8')
        if path == '/api/runs/approval':
            try:
                self.tool_access();query=parse_qs(urlparse(self.path).query)
                approval=self.conversations().state(query.get('chat',[''])[0],'run-approval')
                if not approval or approval['id']!=query.get('id',[''])[0]:raise ValueError('This approval expired. Review the latest scenario.')
                return self.send(approval)
            except (ValueError,OSError) as error:return self.send({'error':str(error)},status=400)
        if path in ('/api/jobs','/api/jobs/events'):
            try:
                self.tool_access();self.reconcile_jobs()
                query=parse_qs(urlparse(self.path).query)
                if path.endswith('/events'):return self.send({'events':self.jobs().events(query.get('after',[0])[0])})
                identity=query.get('id',[''])[0]
                if identity:
                    job=self.jobs().get(identity)
                    if job['kind']=='scenario_run':job['data']['log_tail']=log_tail(app.DATA_ROOT/'runs'/identity)
                    return self.send(job)
                return self.send({'jobs':self.jobs().list(query.get('chat',[None])[0])})
            except (ValueError,OSError) as error:return self.send({'error':str(error)},status=400)
        if path == '/api/execution':
            self.tool_access()
            return self.send(self.execution().status())
        if path == '/api/chats':
            try:
                self.tool_access()
                identity = parse_qs(urlparse(self.path).query).get('id', [''])[0]
                return self.send(self.conversations().read(identity) if identity else self.conversations().list())
            except (ValueError, OSError) as error: return self.send({'error':str(error)}, status=400)
        if path in ('/api/app-update', '/api/app-update/file'):
            try:
                self.tool_access()
                if path.endswith('/file'):
                    return self.send(Path(self.updater().verified_file()['path']).read_bytes(), 'application/octet-stream')
                return self.send(self.updater().progress())
            except (ValueError, OSError) as error:
                return self.send({'error':str(error)},status=400)
        if path.startswith('/api/scenario/') or path in ('/scenario.js', '/scenario.css'):
            return self.send({'error': 'Install Scenario Builder from Manage tools.'}, status=404)
        if path == '/api/storage':
            try:
                self.tool_access()
                return self.send(storage.status(app.DATA_ROOT))
            except (ValueError, OSError) as error:
                return self.send({'error': str(error)}, status=400)
        if path == '/api/ai-settings':
            try:
                self.tool_access()
                with app.LOCK:
                    return self.send(ai_settings.load(app.DATA_ROOT / 'companion' / 'ai-settings.json'))
            except (ValueError, OSError):
                return self.send({'error': 'Cannot read shared AI settings.'}, status=400)
        if path.startswith('/tools/') or path.startswith('/api/tools'):
            try:
                self.tool_access()
                if path == '/api/tools/catalog': return self.send(self.official().catalog())
                if path == '/api/tools/download': return self.send(self.official().progress())
                if path == '/api/tools': return self.send({'tools': self.tools().list(), 'comparison_enabled': not (self.tools().root / 'comparison-removed').exists()})
                return self.proxy_tool('GET')
            except Exception as error: return self.send({'error': str(error)}, status=400)
        if path == '/api/installation':
            try:
                installation = app.saved_installation()
                if installation is None:
                    return self.send(app.empty_installation())
                metadata = validate_installation(installation)
                return self.send({**self.installation_layout(), **metadata})
            except (ValueError, OSError) as error:
                return self.send({'error': str(error)}, status=400)
        if path == '/api/status':
            self.reconcile_jobs()
            return self.send({'running': any(j['status'] == 'running' for j in app.JOBS.values()) or (hasattr(self.server,'conversations') and self.server.conversations.busy()) or self.execution().status()['running'] or self.tools().busy() or self.official().progress()['status'] in ('checking','downloading','verifying','installing') or (hasattr(self.server,'updater') and self.server.updater.active())})
        if path == '/assets/app-icon.png':
            return self.send((ROOT/'assets/app-icon.png').read_bytes(), 'image/png')
        if path in ('/', '/shell.js', '/shell.css', '/chat-workspace.js'):
            filename = 'shell.html' if path == '/' else path[1:]
            content = {'shell.html':'text/html', 'shell.js':'text/javascript', 'chat-workspace.js':'text/javascript', 'shell.css':'text/css'}[filename]
            body = (ROOT/filename).read_bytes()
            if filename == 'shell.html':
                self.tools()
                body = body.replace(b'__COMPANION_TOKEN__', self.server.tool_token.encode())
            return self.send(body, content+'; charset=utf-8')
        if path == '/compare' and (self.tools().programs / 'ifs-model-vetting/tool.json').is_file():
            try:
                self.comparison_guard('ifs-model-vetting')
                self.tools().start('ifs-model-vetting', app.saved_installation())
                return self.comparison_proxy('GET', '/')
            except Exception as error: return self.send({'error': str(error)}, status=400)
        if self.comparison_running() and (path.startswith('/api/') and path != '/api/ui-preferences' or path == '/audit.js'):
            return self.comparison_proxy('GET')
        if path == '/compare':
            html = (app.ROOT/'index.html').read_text(encoding='utf-8')
            style = '<style>body{background:white}main{padding:8px 4px;max-width:none}#installation,#browse,#scan,#installationPaths{display:none}section:first-of-type>label:first-child,section:first-of-type>p:first-of-type{display:none}#openSettings{display:inline-block}</style>'
            return self.send(html.replace('<main>',style+'<main>',1).encode(), 'text/html; charset=utf-8')
        if path == '/api/ui-preferences':
            try:
                with app.LOCK:
                    data=json.loads((app.DATA_ROOT/'ui-preferences.json').read_text(encoding='utf-8'))
            except (OSError,ValueError):
                data={}
            return self.send(data)
        return super().do_GET()

    def do_POST(self):
        if self.path in ('/api/tasks/recent','/api/tasks/delete'):
            try:
                self.tool_access(mutate=True)
                size=int(self.headers.get('Content-Length',0))
                if not 0<size<=4096: raise ValueError('Invalid task request.')
                request=json.loads(self.rfile.read(size))
                if not isinstance(request,dict): raise ValueError('Invalid task request.')
                with self.service_lock():
                    if self.path.endswith('/delete'):
                        self.reconcile_jobs()
                        return self.send(delete_task(self,request.get('id')))
                    self.reconcile_jobs()
                    if self.comparison_running():
                        with self.tools().request('ifs-model-vetting','api/recent') as response:
                            reports=json.load(response)['jobs']
                    else:
                        with app.LOCK:
                            reports=[]
                            for key,state in app.JOBS.items():
                                if state.get('_parent'): continue
                                report=state.get('report',{})
                                a=report.get('run1',state.get('run1',''))
                                b=report.get('run2',state.get('run2',''))
                                reports.append({'id':key,'status':state['status'],'created':state.get('created',0),
                                    'title':Path(a).name+' vs '+Path(b).name if a and b else 'Comparison '+key[:8]})
                    return self.send(sync_reports(self.conversations(),reports,self.jobs().list()))
            except (ValueError,OSError,TypeError) as error:
                return self.send({'error':str(error)},status=400)
        if self.path=='/api/compare':
            original=self.rfile
            try:
                self.tool_access()
                size=int(self.headers.get('Content-Length',0))
                if not 0<size<=8*1024**2:raise ValueError('Invalid comparison request size.')
                raw=self.rfile.read(size);request=json.loads(raw)
                runs=request.get('comparisons') or [request.get('b')]
                if not isinstance(runs,list):raise ValueError('Select comparison runs.')
                inputs=[request.get('a'),*runs]
                if any(not isinstance(p,str) for p in inputs):raise ValueError('Select exact run paths.')
                self.comparison_inputs=inputs
                controller=self.execution()
                with controller.lock:
                    root=app.saved_installation()
                    mutable={str((Path(root)/name).resolve()).casefold() for name in WORKING} if root else set()
                    if root and (controller.status()['running'] or (Path(root)/'.companion-recovery.json').exists()) and any(str(Path(p).resolve()).casefold() in mutable for p in inputs):
                        raise ValueError('IFs working files are in use. Compare completed saved runs, or wait for model execution and recovery to finish.')
                    self.rfile=io.BytesIO(raw)
                    if self.comparison_running():return self.comparison_proxy('POST')
                    return super().do_POST()
            except (ValueError,OSError,TypeError) as error:return self.send({'error':str(error)},status=400)
            finally:self.rfile=original
        if self.path in ('/api/runs/prepare','/api/runs/start','/api/runs/save','/api/jobs/cancel','/api/jobs/recover'):
            try:
                self.tool_access(mutate=True)
                size=int(self.headers.get('Content-Length',0))
                if not 0<size<=6_100_000:raise ValueError('Invalid request size.')
                request=json.loads(self.rfile.read(size))
                if not isinstance(request,dict):raise ValueError('Invalid request.')
                if self.path.endswith('/save'):
                    with self.conversations().lock:
                        return self.send(self.runner().save_to_ifs(request.get('id'),request.get('name')))
                if self.path.endswith('/prepare'):return self.send(self.prepare_run(request))
                if self.path.endswith('/start'):
                    with self.approval_lock():
                        owner=request.get('chat');approval=self.conversations().state(owner,'run-approval')
                        if not approval or approval['id']!=request.get('approval') or approval['sha256']!=request.get('sha256'):
                            raise ValueError('Review the latest run approval before executing.')
                        existing=next((j for j in self.jobs().list(owner) if j['data'].get('approval_id')==approval['id']),None)
                        if existing:return self.send(existing)
                        if approval.get('session'):
                            with self.tools().request('ifs-scenario-builder','api/scenario/preview','POST',json.dumps({'session':approval['session'],'draft':approval['draft']}).encode()) as response:
                                preview=json.load(response)
                            if hashlib.sha256(preview['text'].encode()).hexdigest()!=approval['sha256']:raise ValueError('The draft changed. Review it again.')
                        self.reconcile_jobs()
                        job=self.runner().start(approval)
                        self.conversations().append(owner,'assistant','Approved scenario submitted to IFs. Follow its job for progress and results.',
                            [{'kind':'job','id':job['id'],'title':'View scenario run'}])
                    return self.send(job)
                job=self.jobs().get(request.get('id'))
                if self.path.endswith('/recover'):return self.send(self.runner().recover(job['id']))
                if job['status'] in TERMINAL:return self.send(job)
                if job['kind']=='scenario_run':return self.send(self.runner().cancel(job['id']))
                if job['kind']=='chat':
                    self.stop_chat(job['owner'])
                    return self.send(self.jobs().update(job['id'],stage='stopping'))
                if job['kind']=='knowledge':
                    with self.tools().request('ifs-code-reader','api/stop','POST',b'{}') as response:response.read()
                    return self.send(self.jobs().update(job['id'],'cancelled',stage='finished'))
                if job['kind']=='comparison':
                    data=json.dumps({'job':job['data']['backend_id']}).encode()
                    if self.comparison_running():
                        with self.tools().request('ifs-model-vetting','api/stop','POST',data) as response:response.read()
                    else:
                        with app.LOCK:
                            state=app.JOBS.get(job['data']['backend_id'])
                            if state:state.update(stop_requested=True,progress='Stopping…')
                    return self.send(self.jobs().update(job['id'],stage='stopping'))
                raise ValueError('This job does not support cancellation.')
            except (ValueError,OSError,KeyError,TypeError) as error:return self.send({'error':str(error)},status=400)
        if self.path in ('/api/execution/acquire','/api/execution/release'):
            try:
                controller=self.execution()
                if not secrets.compare_digest(self.headers.get('X-IFs-Execution-Token',''),self.server.execution_token):
                    raise ValueError('Execution authentication required.')
                size=int(self.headers.get('Content-Length',0))
                if not 0<size<=4096:raise ValueError('Invalid execution request.')
                request=json.loads(self.rfile.read(size))
                if self.path.endswith('/release'):return self.send(controller.release(request.get('lease')))
                return self.send(controller.acquire('Autotune'))
            except (ValueError,OSError) as error:return self.send({'error':str(error)},status=400)
        if self.path in ('/api/chats/create','/api/chats/send','/api/chats/stop','/api/chats/event','/api/chats/touch'):
            try:
                self.tool_access(mutate=True)
                size = int(self.headers.get('Content-Length', 0))
                if not 0 < size <= 70000: raise ValueError('Invalid request size.')
                request = json.loads(self.rfile.read(size))
                if not isinstance(request, dict): raise ValueError('Invalid request.')
                service = self.conversations()
                if self.path.endswith('/touch'): return self.send(service.touch(request.get('id')))
                if self.path.endswith('/event'):
                    identity = request.get('id')
                    service.read(identity)
                    if request.get('kind') == 'comparison':
                        job = request.get('job')
                        if not isinstance(job,str) or not job.isalnum(): raise ValueError('Invalid comparison ID.')
                        if self.comparison_running():
                            with self.tools().request('ifs-model-vetting','api/job?job='+job) as response: json.load(response)
                        elif job not in app.JOBS: raise ValueError('Unknown comparison.')
                        unified='comparison-'+job
                        try:self.jobs().get(unified)
                        except ValueError:self.jobs().create('comparison',data={'backend_id':job},identity=unified)
                        self.jobs().claim(unified,identity)
                        service.append(identity,'assistant','Comparison submitted from the reviewed Model Vetting selections.',
                            [{'kind':'report','id':job,'title':'Open comparison results'}])
                    return self.send({'ok':True})
                if self.path.endswith('/create'): return self.send(service.create())
                if self.path.endswith('/stop'):
                    return self.send(self.stop_chat(request.get('id')))
                owner=request.get('id');service.read(owner)
                job=self.jobs().create('chat',owner,{'stage':'responding'})
                try:
                    result=service.send(owner,request.get('message'))
                    cancelled=bool(result['messages'] and result['messages'][-1]['content']=='Stopped.')
                    self.jobs().update(job['id'],'cancelled' if cancelled else 'complete',stage='finished')
                    return self.send(result)
                except Exception as error:
                    self.jobs().update(job['id'],'failed',error=str(error));raise
            except (ValueError, OSError) as error: return self.send({'error':str(error)}, status=400)
        if self.path in ('/api/app-update/check','/api/app-update/download','/api/app-update/install'):
            try:
                self.tool_access(mutate=True)
                size=int(self.headers.get('Content-Length',0))
                if not 0 < size < 4096: raise ValueError('Invalid update request.')
                request=json.loads(self.rfile.read(size))
                if not isinstance(request,dict): raise ValueError('Invalid update request.')
                updater=self.updater()
                if self.path.endswith('/check'): return self.send(updater.check())
                if self.path.endswith('/download'): return self.send(updater.download(request.get('kind')))
                self.reconcile_jobs()
                if self.execution().status()['running'] or any(j['status']=='running' for j in self.jobs().list()) or any(j['status']=='running' for j in app.JOBS.values()) or self.tools().busy() or self.official().progress()['status'] in ('checking','downloading','verifying','installing'):
                    raise ValueError('Wait for running work and tool installations to finish before updating Companion.')
                return self.send(updater.prepare_install())
            except (ValueError,OSError) as error:
                return self.send({'error':str(error)},status=400)
        if self.path.startswith('/api/scenario/'):
            return self.send({'error': 'Install Scenario Builder from Manage tools.'}, status=404)
        if self.path == '/api/storage':
            try:
                self.tool_access(mutate=True)
                if any(job['kind']=='scenario_run' and job['data'].get('installation') and (Path(job['data']['installation'])/'.companion-recovery.json').exists() for job in self.jobs().list()):
                    raise ValueError('Restore IFs working files before changing the storage location.')
                size = int(self.headers.get('Content-Length', 0))
                if not 0 < size < 16384: raise ValueError('Invalid storage request.')
                request = json.loads(self.rfile.read(size))
                return self.send(storage.schedule(app.DATA_ROOT, request.get('location')))
            except (ValueError, OSError, AttributeError) as error:
                return self.send({'error': str(error)}, status=400)
        if self.path in ('/api/ai-settings/test', '/api/ai-settings/models'):
            try:
                self.tool_access(mutate=True)
                size = int(self.headers.get('Content-Length', 0))
                if not 0 < size < 16384: raise ValueError('Invalid AI settings request.')
                request = json.loads(self.rfile.read(size))
                return self.send(ai_settings.probe(app.DATA_ROOT / 'companion' / 'ai-settings.json',
                                                  request, models=self.path.endswith('/models')))
            except (ValueError, OSError) as error:
                return self.send({'error': str(error)}, status=400)
        if self.path == '/api/ai-settings':
            try:
                self.tool_access(mutate=True)
                size = int(self.headers.get('Content-Length', 0))
                if not 0 < size < 16384: raise ValueError('Invalid AI settings request.')
                request = json.loads(self.rfile.read(size))
                with app.LOCK:
                    result = ai_settings.save(app.DATA_ROOT / 'companion' / 'ai-settings.json', request)
                return self.send(result)
            except (ValueError, OSError) as error:
                return self.send({'error': str(error)}, status=400)
        if self.path == '/api/installation':
            try:
                self.tool_access(mutate=True)
                if self.execution().status()['running']: raise ValueError('Wait for IFs execution to finish before changing installations.')
                if hasattr(self.server,'conversations') and self.server.conversations.busy(): raise ValueError('Wait for chat responses to finish before changing installations.')
                size = int(self.headers.get('Content-Length', 0))
                if not 0 < size < 16384:
                    raise ValueError('Invalid installation request.')
                request = json.loads(self.rfile.read(size))
                request['installation'] = str(request.get('installation') or '').strip()
                metadata = validate_installation(request['installation'])
                layout = {**app.installation_layout(request['installation']), **metadata}
                app.DATA_ROOT.mkdir(parents=True, exist_ok=True)
                with app.LOCK:
                    app.SETTINGS.write_text(json.dumps({'installation': layout['installation']}, indent=2), encoding='utf-8')
                return self.send(layout)
            except (ValueError, TypeError, AttributeError, OSError) as error:
                return self.send({'error': str(error)}, status=400)
        if self.path.startswith(('/api/tools/', '/tools/')):
            try:
                if self.path.startswith('/tools/'): return self.proxy_tool('POST')
                return self.tool_post()
            except Exception as error: return self.send({'error': str(error)}, status=400)
        if self.path != '/api/ui-preferences':
            if self.comparison_running():
                try: return self.comparison_proxy('POST')
                except Exception as error: return self.send({'error': str(error)}, status=400)
            return super().do_POST()
        try:
            request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            preferences={key:bool(request.get(key,False)) for key in ('toolsGroup','recentGroup')}
            app.DATA_ROOT.mkdir(parents=True,exist_ok=True)
            with app.LOCK:
                (app.DATA_ROOT/'ui-preferences.json').write_text(json.dumps(preferences),encoding='utf-8')
            return self.send(preferences)
        except (ValueError,TypeError,KeyError,OSError) as exc:
            return self.send({'error':str(exc)},status=400)

def create_server(port=0):
    if not (app.DECODER_EXE.exists() or app.DECODER.exists()):
        raise RuntimeError('The bundled IFs decoder is missing. Reinstall the application.')
    app.DATA_ROOT.mkdir(parents=True, exist_ok=True)
    app.restore_jobs()
    server=app.ThreadingHTTPServer(('127.0.0.1',port), Handler)
    server.RequestHandlerClass=Handler
    server.tools = ToolManager(app.DATA_ROOT / 'companion')
    server.tool_token = secrets.token_urlsafe(32)
    original_close = server.server_close
    def close():
        if hasattr(server,'conversations'):
            for identity in list(server.conversations.active):server.conversations.stop(identity)
        if hasattr(server,'runner'):server.runner.close()
        server.tools.close()
        if hasattr(server,'execution'):server.execution.close()
        original_close()
    server.server_close = close
    return server

if __name__ == '__main__':
    app.DATA_ROOT = storage.initialize()
    app.SETTINGS = app.DATA_ROOT / 'settings.json'
    server=create_server(8766)
    print('IFsCompanion: http://127.0.0.1:8766',flush=True)
    try: server.serve_forever()
    finally: server.server_close()
