"""Build the independently installable Windows Scenario Builder package."""
import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', default='0.1.0')
    parser.add_argument('--release-date', default=date.today().isoformat())
    args = parser.parse_args()
    command = [sys.executable,'-m','PyInstaller','--noconfirm','--name','ScenarioBuilder','--console',
               '--distpath',str(ROOT/'dist'),'--workpath',str(ROOT/'build/ScenarioBuilder'),
               '--specpath',str(ROOT/'build/ScenarioBuilder'),'--paths',str(ROOT)]
    for path in [ROOT/'scenario-tool/index.html', ROOT/'scenario-tool/base.css', ROOT/'scenario-tool/bridge.js',
                 ROOT/'scenario.js',ROOT/'scenario.css']:
        command.extend(['--add-data',str(path)+';.'])
    subprocess.run([*command,str(ROOT/'scenario-tool/service.py')],cwd=ROOT,check=True)
    stage = ROOT/'dist/ScenarioBuilder'
    shutil.copy2(ROOT/'LICENSE',stage/'LICENSE')
    shutil.copy2(ROOT/'scenario-tool/README.md',stage/'README.md')
    runtime = Path(sys.base_prefix)
    for path in runtime.glob('LICENSE*'): shutil.copy2(path,stage/('Python-'+path.name))
    meta = {'id':'ifs-scenario-builder','name':'Scenario Builder','version':args.version,'api_version':1,
            'platform':'win-x64','kind':'web-service','entrypoint':'ScenarioBuilder.exe',
            'min_companion_version':'0.2.1','released_at':args.release_date,
            'release_notes':'Optional AI-assisted .sce creation and editing. Unified chat, attachments, parameter/country/subgroup graph inspector, shared AI settings and installation metadata, and descriptive generation comments.'}
    meta['installed_size'] = sum(p.stat().st_size for p in stage.rglob('*') if p.is_file())
    (stage/'tool.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    folder=ROOT/'scenario-tool/release';folder.mkdir(exist_ok=True)
    package=folder/f'ifs-scenario-builder-{args.version}-win-x64.ifstool'
    pending=package.with_suffix('.partial')
    with zipfile.ZipFile(pending,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sorted(stage.rglob('*')):
            if path.is_file(): archive.write(path,path.relative_to(stage).as_posix())
    with zipfile.ZipFile(pending) as archive:
        if archive.testzip(): raise RuntimeError('Package CRC validation failed.')
        installed_size=sum(info.file_size for info in archive.infolist())
    pending.replace(package)
    digest=hashlib.sha256(package.read_bytes()).hexdigest()
    package.with_suffix('.sha256').write_text(digest+'  '+package.name+'\n',encoding='ascii')
    meta.update(sha256=digest,size=package.stat().st_size,installed_size=installed_size)
    package.with_suffix('.release.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    print(json.dumps({'package':str(package),'sha256':digest,'size':package.stat().st_size}))


if __name__=='__main__':
    import os
    import sys
    if '--standalone' in sys.argv:
        sys.argv.remove('--standalone')
        main()
    else:
        parser=argparse.ArgumentParser(description='Build a shared-Python Companion tool. Use --standalone for the legacy format.')
        parser.add_argument('--python',default=sys.executable)
        parser.add_argument('--version',default='0.3.1')
        parser.add_argument('--release-notes')
        parser.add_argument('--release-date')
        args=parser.parse_args()
        companion=Path(os.environ.get('IFS_COMPANION_PATH', Path(__file__).resolve().parents[1]))
        command=[args.python,str(companion/'packaging/build_shared_tool.py'),'--tool','ifs-scenario-builder','--version',args.version]
        if args.release_notes:command+=['--release-notes',args.release_notes]
        if args.release_date:command+=['--release-date',args.release_date]
        subprocess.run(command,check=True)
