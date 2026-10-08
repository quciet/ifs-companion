"""Approved tools published through IFsCompanion's public GitHub repository."""
import hashlib
import json
import re
import tempfile
import threading
import urllib.parse
import urllib.request
import zipfile
from tool_manager import MAX_UPLOAD, manifest

CATALOG_URL = 'https://raw.githubusercontent.com/quciet/ifs-companion/main/official-tools/catalog.json'
COMPANION_VERSION = (0, 1, 1)
RELEASE_PREFIX = 'https://github.com/quciet/ifs-companion/releases/download/'

def version(text):
    if not isinstance(text,str) or not re.fullmatch(r'\d+\.\d+\.\d+',text): raise ValueError('Invalid tool version in the official catalog.')
    return tuple(map(int,text.split('.')))

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target=urllib.parse.urlsplit(newurl)
        if target.scheme!='https' or target.hostname not in {'github.com','release-assets.githubusercontent.com','objects.githubusercontent.com','raw.githubusercontent.com'}:
            raise ValueError('The download redirected outside the approved GitHub hosts.')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def open_url(url):
    request=urllib.request.Request(url,headers={'User-Agent':'IFsCompanion/0.1.1','Cache-Control':'no-cache'})
    return urllib.request.build_opener(SafeRedirect()).open(request,timeout=30)

def validate_catalog(document):
    if not isinstance(document,dict) or document.get('schema_version')!=1 or not isinstance(document.get('tools'),list):
        raise ValueError('This official catalog needs a newer version of Companion.')
    if len(document['tools'])>100:raise ValueError('Invalid official catalog.')
    result=[];seen=set()
    for row in document['tools']:
        if not isinstance(row,dict):raise ValueError('Invalid catalog entry.')
        identity=row.get('id')
        if not isinstance(identity,str) or not re.fullmatch(r'[a-z][a-z0-9-]{2,63}',identity) or identity in seen:
            raise ValueError('Invalid or duplicate official tool ID.')
        seen.add(identity)
        if not isinstance(row.get('name'),str) or not 0<len(row['name'])<=80:raise ValueError('Invalid official tool name.')
        if not isinstance(row.get('description'),str) or len(row['description'])>1000:raise ValueError('Invalid tool description.')
        if row.get('status')=='coming-soon':
            result.append({key:row[key] for key in ('id','name','description','status')});continue
        version(row.get('version'))
        minimum=version(row.get('min_companion_version'))
        if row.get('api_version')!=1 or row.get('platform')!='win-x64':raise ValueError('Unsupported official tool format.')
        url=row.get('url','')
        if not isinstance(url,str) or not url.startswith(RELEASE_PREFIX) or len(url)>1000 or any(c in url for c in ('?','#','\\')):
            raise ValueError('Official packages must use versioned releases in the Companion repository.')
        suffix=url[len(RELEASE_PREFIX):].split('/')
        if len(suffix)!=2 or any(part in ('.','..') or not re.fullmatch(r'[A-Za-z0-9._-]+',part) for part in suffix) or not suffix[1].endswith('.ifstool'):
            raise ValueError('Invalid official release URL.')
        if not isinstance(row.get('sha256'),str) or not re.fullmatch('[a-f0-9]{64}',row['sha256']):raise ValueError('Missing package checksum.')
        if type(row.get('size')) is not int or not 0<row['size']<=MAX_UPLOAD:raise ValueError('Invalid package size.')
        item={key:row[key] for key in ('id','name','description','version','min_companion_version','api_version','platform','url','sha256','size')}
        item['compatible']=minimum<=COMPANION_VERSION
        item['status']='available'
        result.append(item)
    return result

class OfficialTools:
    def __init__(self,manager):
        self.manager=manager
        self.lock=threading.Lock()
        self.state={'status':'idle'}

    def catalog(self):
        try:
            with open_url(CATALOG_URL) as response:raw=response.read(256*1024+1)
            if len(raw)>256*1024:raise ValueError('Official catalog is too large.')
            tools=validate_catalog(json.loads(raw))
        except Exception as error:
            raise ValueError('Cannot load official tools. Check your internet connection and try again. Install from file still works.') from error
        return {'tools':tools}

    def progress(self):
        with self.lock:return dict(self.state)

    def _state(self,**values):
        with self.lock:self.state.update(values)

    def begin(self,identity):
        with self.lock:
            if self.state['status'] in ('checking','downloading','verifying','installing'):raise ValueError('Wait for the current tool installation to finish.')
            self.state={'status':'checking','id':identity,'received':0,'total':0,'message':'Checking the official release…'}
        threading.Thread(target=self._install,args=(identity,),daemon=True).start()
        return self.progress()

    def _install(self,identity):
        try:
            row=next((item for item in self.catalog()['tools'] if item['id']==identity),None)
            if not row or row.get('status')!='available':raise ValueError('This tool is not available yet.')
            if not row['compatible']:raise ValueError('Update Companion before installing this tool.')
            if self.manager._folder(identity).exists():self.manager.stop(identity);self.manager._require_stopped(identity)
            with tempfile.TemporaryFile() as package:
                digest=hashlib.sha256();received=0
                self._state(status='downloading',total=row['size'],message='Downloading '+row['name']+'…')
                with open_url(row['url']) as response:
                    while chunk:=response.read(1024*1024):
                        received+=len(chunk)
                        if received>row['size']:raise ValueError('The download size does not match the official release.')
                        digest.update(chunk);package.write(chunk);self._state(received=received)
                self._state(status='verifying',message='Verifying the downloaded package…')
                if received!=row['size'] or digest.hexdigest()!=row['sha256']:
                    raise ValueError('Package verification failed. Nothing was installed; please try again.')
                package.seek(0)
                with zipfile.ZipFile(package) as archive:
                    info=archive.getinfo('tool.json')
                    if info.file_size>16384:raise ValueError('Invalid package manifest.')
                    meta=manifest(json.loads(archive.read(info)))
                if meta['id']!=row['id'] or meta['version']!=row['version']:
                    raise ValueError('The package does not match the official tool and version.')
                self._state(status='installing',message='Installing '+row['name']+'…')
                package.seek(0);self.manager.install(package,expected_id=identity,official_sha256=row['sha256'])
                if identity == 'ifs-model-vetting': (self.manager.root / 'comparison-removed').unlink(missing_ok=True)
            self._state(status='complete',message=row['name']+' '+row['version']+' is ready.')
        except Exception as error:
            self._state(status='error',message=str(error))
