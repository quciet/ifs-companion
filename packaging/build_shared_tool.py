"""Build thin official packages. No Python runtime or library copies in tools.

Use --tool ID --version VERSION. Companion's shipped lock owns dependencies.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
PROFILE='official-python-v1'
NAMES={'ifs-model-vetting':'IFs Vetting','ifs-code-reader':'Code Interpreter',
       'ifs-autotune':'Autotune','ifs-scenario-builder':'Scenario Builder'}


def tree(source,target):
    shutil.copytree(source,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc','.cache'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tool',choices=NAMES,required=True)
    parser.add_argument('--version',required=True)
    parser.add_argument('--source',type=Path,help='Override the sibling source checkout')
    parser.add_argument('--output-dir',type=Path,help='Override the release output directory')
    parser.add_argument('--release-notes',type=Path)
    parser.add_argument('--release-date',default=datetime.now(timezone.utc).date().isoformat())
    args=parser.parse_args()
    import re
    if not re.fullmatch(r'\d+\.\d+\.\d+',args.version):raise ValueError('Invalid version')
    source=ROOT.parent/('ifs-code-interpreter' if args.tool=='ifs-code-reader' else args.tool)
    source=(args.source or source).resolve()
    release=args.output_dir or source/'release'
    release.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        stage=Path(temporary)
        if args.tool=='ifs-model-vetting':
            for file in source.glob('*.py'):shutil.copy2(file,stage/file.name)
            for name in ('index.html','audit.js','LICENSE','THIRD_PARTY_NOTICES.txt'):shutil.copy2(source/name,stage/name)
            tree(source/'decoder-runtime',stage/'decoder-runtime')
            tree(source/'licenses',stage/'licenses')
            entry='comparison_tool.py'
        elif args.tool=='ifs-code-reader':
            # Verify the source/model manifests before publishing a new snapshot.
            snapshots=json.loads((source/'data/sources.json').read_text(encoding='utf-8'))
            for snapshot in snapshots['sources']:
                for item in snapshot['files']:
                    if hashlib.sha256((source/snapshot['directory']/item['path']).read_bytes()).hexdigest()!=item['sha256']:
                        raise ValueError('Source snapshot checksum mismatch: '+item['path'])
            model=json.loads((source/'data/embedding-model.json').read_text(encoding='utf-8'))
            for name,digest in model['files'].items():
                if hashlib.sha256((source/'workspace/model'/name).read_bytes()).hexdigest()!=digest:
                    raise ValueError('Embedding model checksum mismatch: '+name)
            tree(source/'tool',stage/'tool');tree(source/'data',stage/'data')
            tree(source/'workspace/model',stage/'data/embedding-model')
            shutil.copy2(source/'README.md',stage/'README.md')
            entry='tool/companion_service.py'
        elif args.tool=='ifs-scenario-builder':
            for name in ('service.py','index.html','base.css','bridge.js','scenario_service.py',
                         'scenario_compiler.py','scenario_intelligence.py','scenario.js','scenario.css','LICENSE'):
                shutil.copy2(source/name,stage/name)
            # Host-owned helpers are bundled so installed tools need no source checkout.
            for name in ('ai_settings.py','installation_validation.py'):
                shutil.copy2(ROOT/name,stage/name)
            entry='service.py'
        else:
            subprocess.run(['npm.cmd','run','build'],cwd=source/'frontend',check=True)
            tree(source/'desktop/node_modules/electron/dist',stage/'electron')
            (stage/'electron/electron.exe').rename(stage/'electron/IFsAutotune.exe')
            app=stage/'electron/resources/app';app.mkdir(parents=True)
            (app/'package.json').write_text(json.dumps({'name':'ifs-autotune','version':args.version,'main':'desktop/main.js'}),encoding='utf-8')
            desktop=app/'desktop';desktop.mkdir()
            for name in ('main.js','preload.js','companion-host.js','companion-bridge.js'):
                shutil.copy2(source/'desktop'/name,desktop/name)
            tree(source/'frontend/dist',desktop/'frontend/dist')
            files=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard'],cwd=source,text=True).splitlines()
            for rel in sorted(set(files)):
                file=source/rel
                if file.is_file() and ((rel.startswith('backend/') and (file.suffix=='.py' or rel=='backend/tools/ParquetReaderlite.exe')) or rel.startswith('desktop/input/template/') or rel=='LICENSE'):
                    target=app/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,target)
            entry='electron/IFsAutotune.exe'
        meta={'id':args.tool,'name':NAMES[args.tool],'version':args.version,'api_version':1,
              'platform':'win-x64','kind':'web-service','entrypoint':entry,'python_profile':PROFILE,
              'min_companion_version':'0.3.6' if args.tool=='ifs-scenario-builder' else '0.3.0','released_at':args.release_date,
              'release_notes':args.release_notes.read_text(encoding='utf-8') if args.release_notes else 'Uses Companion’s shared Python runtime and libraries. Missing libraries download on first installation.'}
        (stage/'tool.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
        package=release/f'{args.tool}-{args.version}-win-x64.ifstool'
        if package.exists():raise ValueError('Choose a new version; release packages are immutable: '+str(package))
        pending=package.with_suffix('.partial')
        with zipfile.ZipFile(pending,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            for file in sorted(stage.rglob('*')):
                if file.is_file():archive.write(file,file.relative_to(stage).as_posix())
        with zipfile.ZipFile(pending) as archive:
            if archive.testzip():raise ValueError('Invalid archive')
            meta['installed_size']=sum(info.file_size for info in archive.infolist())
        pending.replace(package)
        with package.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        meta.update(size=package.stat().st_size,sha256=digest)
        package.with_suffix('.sha256').write_text(digest+'  '+package.name+'\n',encoding='ascii')
        package.with_suffix('.release.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
        print(package)


if __name__=='__main__':main()
