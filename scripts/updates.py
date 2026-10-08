"""One update entry, two independently reported update targets."""
import hashlib
import io
import json
import re
import shutil
import tempfile
import urllib.error
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from common import ROOT, RUNTIME, VERSION, locked, now, read, write
from library import fetch, sync

RELEASE_URL = 'https://raw.githubusercontent.com/lacemou/handraw-style-router/master/release.json'

def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d+\.\d+\.\d+', value):
        raise ValueError('Invalid release version')
    return tuple(map(int, value.split('.')))

def check_code(getter=fetch):
    try:
        release = json.loads(getter(RELEASE_URL))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return {'code': 'unpublished', 'local_version': VERSION,
                    'message': '远端尚未发布版本化更新清单；未替换本地第二版。'}
        raise
    if not isinstance(release, dict) or release.get('schema') != 1:
        raise ValueError('Unsupported Router release manifest')
    status = 'available' if version_tuple(release['version']) > version_tuple(VERSION) else 'current'
    return {'code': status, 'local_version': VERSION, 'remote_version': release['version'], 'release': release}

def safe_relative(name):
    path = Path(name)
    if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0].startswith('.') or '\\' in name:
        raise ValueError('Unsafe release file path')
    return path

def install_code(release, *, root=ROOT, runtime=RUNTIME, getter=fetch):
    parsed = urlparse(release['archive_url'])
    if parsed.scheme != 'https' or parsed.hostname != 'github.com' or not parsed.path.startswith('/lacemou/handraw-style-router/releases/download/'):
        raise ValueError('Router archive must be from this repository GitHub releases')
    archive = getter(release['archive_url'])
    if hashlib.sha256(archive).hexdigest() != release['archive_sha256']:
        raise ValueError('Router archive hash mismatch')
    files = release['files']
    if not isinstance(files, dict) or not {'SKILL.md', 'version.json', 'scripts/router.py'} <= set(files):
        raise ValueError('Incomplete Router release')
    root, runtime = Path(root), Path(runtime)
    with locked(runtime / 'code-update'):
        stage = Path(tempfile.mkdtemp(prefix='code-stage-', dir=runtime))
        backup = runtime / 'code-backups' / stage.name
        backup.mkdir(parents=True)
        originals = {}
        changed = []
        try:
            with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
                if len(bundle.namelist()) != len(set(bundle.namelist())) or set(bundle.namelist()) != set(files):
                    raise ValueError('Release archive and manifest disagree')
                for name, digest in files.items():
                    relative = safe_relative(name)
                    if bundle.getinfo(name).file_size > 10_000_000:
                        raise ValueError('Release file too large')
                    content = bundle.read(name)
                    if len(content) > 10_000_000 or hashlib.sha256(content).hexdigest() != digest:
                        raise ValueError('Release file validation failed')
                    target = stage / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(content)
            if read(stage / 'version.json')['version'] != release['version']:
                raise ValueError('Release version mismatch')
            # Validate syntax before touching current source.
            for source in (stage / 'scripts').rglob('*.py'):
                compile(source.read_text(encoding='utf-8'), str(source), 'exec')
            for name in files:
                relative = safe_relative(name)
                target = root / relative
                if target.is_symlink() or not target.resolve().is_relative_to(root.resolve()):
                    raise ValueError('Unsafe installed file')
                originals[name] = target.exists()
                if target.exists():
                    saved = backup / relative
                    saved.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, saved)
            write(backup / 'rollback.json', {'originals': originals, 'time': now()})
            try:
                for name in files:
                    relative = safe_relative(name)
                    target = root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    changed.append(name)
                    shutil.copy2(stage / relative, target)
            except Exception:
                for name in reversed(changed):
                    target = root / name
                    if originals[name]:
                        shutil.copy2(backup / name, target)
                    elif target.exists():
                        target.unlink()
                raise
            return {'code': 'updated', 'version': release['version'], 'backup': str(backup)}
        finally:
            shutil.rmtree(stage)

def update(*, check_only=False, runtime=RUNTIME, root=ROOT, getter=fetch):
    result = {}
    try:
        code = check_code(getter)
        result['router'] = {k: v for k, v in code.items() if k != 'release'}
        if code['code'] == 'available' and not check_only:
            result['router'] = install_code(code['release'], root=root, runtime=runtime, getter=getter)
    except Exception as error:
        result['router'] = {'code': 'failed', 'error': str(error), 'changed': False}
    try:
        if check_only:
            upstream = json.loads(getter('https://api.github.com/repos/yang0/handraw-style/git/ref/heads/master'))['object']['sha']
            pointer = Path(runtime) / 'CURRENT.json'
            local = read(pointer)['revision'] if pointer.exists() else None
            result['library'] = {'library': 'current' if local == upstream else 'available', 'local': local, 'remote': upstream}
        else:
            result['library'] = sync(runtime, getter)
    except Exception as error:
        result['library'] = {'library': 'failed', 'error': str(error), 'previous_pointer_retained': True}
    return result
