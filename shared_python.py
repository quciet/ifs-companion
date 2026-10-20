"""One private interpreter and a reference-tracked, immutable library store.

Only Companion's shipped lock selects versions/URLs. Tool packages select an
official profile, never arbitrary pip commands or dependency download locations.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

PROFILE = 'official-python-v1'
OFFICIAL_IDS = {'ifs-model-vetting', 'ifs-autotune', 'ifs-code-reader', 'ifs-scenario-builder'}
ROOT = Path(__file__).resolve().parent


def validate_profile(meta):
    profile = meta.get('python_profile')
    if profile is not None and (profile != PROFILE or meta.get('id') not in OFFICIAL_IDS):
        raise ValueError('This shared Python profile is not supported. Update Companion first.')
    return profile


class SharedPython:
    def __init__(self, root, runtime=None, lock=None):
        self.store = Path(root) / 'python-libraries'
        self.runtime = Path(runtime or os.environ.get('IFS_COMPANION_PYTHON') or
                            ROOT / 'build/shared-dev/python/python.exe')
        self.lock = lock or json.loads((ROOT/'shared-python-lock.json').read_text(encoding='utf-8'))

    def requirements(self, meta):
        if not validate_profile(meta): return []
        return self.lock['tools'][meta['id']]

    def folder(self, name):
        return self.store / (name + '-' + self.lock['packages'][name]['version'])

    def paths(self, meta):
        return [str(self.folder(name)) for name in self.requirements(meta) if name not in self.lock['core']]

    def ensure(self, meta):
        if not validate_profile(meta): return
        if not self.runtime.is_file():
            raise ValueError('The shared Python runtime is missing. Rebuild or reinstall Companion.')
        self.store.mkdir(parents=True, exist_ok=True)
        for name in self.requirements(meta):
            if name in self.lock['core']: continue
            row = self.lock['packages'][name]
            destination = self.folder(name)
            if (destination/'.complete').is_file() and (destination/'.complete').read_text(encoding='ascii') == row['sha256']: continue
            # Install outside the live store entry. Interrupted downloads cannot
            # replace a working library; leftovers are disposable on the next run.
            with tempfile.TemporaryDirectory(prefix='.install-', dir=self.store) as temporary:
                stage = Path(temporary)/'package'
                requirement = Path(temporary)/'requirement.txt'
                requirement.write_text(f"{name} @ {row['url']} --hash=sha256:{row['sha256']}\n", encoding='utf-8')
                command = [str(self.runtime), '-I', '-m', 'pip', '--isolated', 'install',
                           '--no-deps', '--no-cache-dir', '--no-compile', '--only-binary=:all:',
                           '--require-hashes', '--disable-pip-version-check', '--target', str(stage),
                           '-r', str(requirement)]
                result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True, timeout=600,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                if result.returncode:
                    raise ValueError(f'Could not install shared library {name}. Check your internet connection and try again.')
                (stage/'.complete').write_text(row['sha256'], encoding='ascii')
                if destination.exists(): shutil.rmtree(destination)
                stage.rename(destination)

    def environment(self, meta, env):
        paths = self.paths(meta)
        if any(not (Path(path)/'.complete').is_file() for path in paths):
            raise ValueError('A shared library is missing. Reinstall this tool to repair it.')
        # sitecustomize activates .pth files too (needed by some wheel packages).
        return dict(env, IFS_COMPANION_PYTHON=str(self.runtime),
                    IFS_SHARED_LIBRARY_PATHS=os.pathsep.join(paths),
                    PYTHONPATH=str(ROOT/'python-bootstrap'), PYTHONNOUSERSITE='1',
                    PYTHONDONTWRITEBYTECODE='1', PYTHONHOME='')

    def cleanup(self, installed):
        """Recompute ownership from manifests, including all indirect dependencies.

        No stored counters to drift. Caller must read every manifest successfully
        and prevent concurrent changes. Failure to delete an unused locked folder
        merely leaves reclaimable disk space; it never removes a referenced one.
        """
        keep = {self.folder(name).name for meta in installed for name in self.requirements(meta)
                if name not in self.lock['core']}
        if not self.store.exists(): return
        for folder in self.store.iterdir():
            if folder.is_dir() and folder.name not in keep:
                try: shutil.rmtree(folder)
                except OSError: pass
