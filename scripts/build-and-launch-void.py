#!/usr/bin/env python3
"""Build, install and launch the user's VOID PROTOCOL instance (Python 3.11+)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import tomllib
import urllib.request
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
INSTANCE = Path('/Users/crococrystal/Library/Application Support/PrismLauncher/instances/VOID PROTOCOL 1.21.1')
PRISM = Path('/Applications/Prism Launcher.app/Contents/MacOS/prismlauncher')
JAVA = Path('/Users/crococrystal/.sdkman/candidates/java/21.0.5-zulu/zulu-21.jdk/Contents/Home')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def mod_ids(path):
    with ZipFile(path) as jar:
        for name in ('META-INF/neoforge.mods.toml', 'META-INF/mods.toml'):
            if name in jar.namelist():
                return {mod['modId'] for mod in tomllib.loads(jar.read(name).decode())['mods']}
    return set()


def install(changes, backup):
    originals = {path: path.read_bytes() if path.exists() else None for path in changes}
    for path, data in originals.items():
        if data is not None:
            saved = backup / path.relative_to(INSTANCE)
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(data)
    replaced = []
    try:
        for path, data in changes.items():
            if data is None:
                path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as staged:
                    staged.write(data)
                try:
                    os.replace(staged.name, path)
                finally:
                    Path(staged.name).unlink(missing_ok=True)
            replaced.append(path)
    except OSError:
        for path in reversed(replaced):
            if originals[path] is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(originals[path])
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-only', action='store_true', help='Install an already verified build')
    args = parser.parse_args()
    if not INSTANCE.is_dir() or not PRISM.is_file():
        raise RuntimeError('The configured instance or PrismLauncher is missing')
    if not args.install_only:
        subprocess.run([str(ROOT / 'gradlew'), 'spotlessCheck', 'build'], cwd=ROOT,
                       env={**os.environ, 'JAVA_HOME': str(JAVA)}, check=True)
    version = re.search(r'^mod_version=(.+)$', (ROOT / 'gradle.properties').read_text(), re.M)[1]
    artifact = ROOT / f'build/libs/ic2-neoforge-{version}.jar'
    assert mod_ids(artifact) == {'ic2'}, 'Unexpected build artifact'
    with ZipFile(artifact) as jar:
        metadata = tomllib.loads(jar.read('META-INF/neoforge.mods.toml').decode())
        assert metadata['mods'][0]['version'] == version, 'Stale build artifact'
    subprocess.run(['python3', str(ROOT / 'scripts/verify_legacy_textures.py'), str(artifact)], check=True)
    subprocess.run(['python3', str(ROOT / 'scripts/check-russian-localization.py')], check=True)

    pack = ROOT / 'modpack/void-protocol'
    deps = json.loads((pack / 'mods.lock.json').read_text())
    cache = ROOT / 'build/external-tabs'
    cache.mkdir(parents=True, exist_ok=True)
    desired = {INSTANCE / 'minecraft/mods' / artifact.name: artifact.read_bytes()}
    for dep in deps:
        assert Path(dep['filename']).name == dep['filename']
        cached = cache / dep['filename']
        if not cached.exists():
            request = urllib.request.Request(dep['url'], headers={'User-Agent': 'IC2R-local-setup/1.0'})
            with urllib.request.urlopen(request, timeout=60) as response:
                cached.write_bytes(response.read())
        data = cached.read_bytes()
        assert hashlib.sha512(data).hexdigest() == dep['sha512'], 'Dependency checksum mismatch'
        assert dep['mod_id'] in mod_ids(cached), 'Unexpected dependency mod ID'
        desired[INSTANCE / 'minecraft/mods' / cached.name] = data

    state = INSTANCE / 'codex-ic2r-deploy.json'
    previous = json.loads(state.read_text()) if state.exists() else {}
    deployed = {}
    for source in sorted((pack / 'kubejs').rglob('*')):
        if not source.is_file():
            continue
        relative = source.relative_to(pack).as_posix()
        target = INSTANCE / 'minecraft' / relative
        data = source.read_bytes()
        deployed[relative] = sha(data)
        if target.exists() and target.read_bytes() != data and previous.get(relative) != sha(target.read_bytes()):
            if previous.get(relative) == sha(data):
                print('Preserving user configuration:', target)
                continue
            raise RuntimeError(f'Project and instance configuration differ; reconcile before installation: {target}')
        desired[target] = data
    desired[state] = (json.dumps(deployed, indent=2) + '\n').encode()
    changes = {path: data for path, data in desired.items() if not path.exists() or path.read_bytes() != data}
    managed_ids = {'ic2'} | {dep['mod_id'] for dep in deps}
    for installed in (INSTANCE / 'minecraft/mods').glob('*.jar'):
        if installed not in desired and mod_ids(installed) & managed_ids:
            changes[installed] = None
    backup_root = INSTANCE / 'codex-backups'
    backup_root.mkdir(exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix='ic2r-', dir=backup_root))
    install(changes, backup)
    target = INSTANCE / 'minecraft/mods' / artifact.name
    assert target.read_bytes() == artifact.read_bytes(), 'Installed build mismatch'
    assert sum('ic2' in mod_ids(p) for p in target.parent.glob('*.jar')) == 1, 'Duplicate IC2 JARs'
    print('Installed:', target, '\nBackup:', backup, flush=True)
    # ponytail: Prism itself guards duplicate launches; don't kill a running game here.
    with (ROOT / 'build/prism-launch.log').open('ab') as log:
        subprocess.Popen([str(PRISM), '--dir', str(INSTANCE.parent.parent), '--launch', INSTANCE.name],
                         stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    print('Launch requested through PrismLauncher.', flush=True)


if __name__ == '__main__':
    main()
