"""Build a source-only archive and a versioned manifest; never publish."""
import hashlib
import json
import zipfile
from pathlib import Path

from common import ROOT, VERSION, write

def build():
    destination = ROOT / 'dist'
    destination.mkdir(exist_ok=True)
    files = [ROOT / name for name in ('SKILL.md', 'README.md', 'LICENSE', 'version.json', 'requirements.txt', '.gitignore')]
    for folder in ('scripts', 'references', 'agents', 'tests'):
        files += [path for path in (ROOT / folder).rglob('*') if path.is_file() and '__pycache__' not in path.parts and path.suffix in {'.py', '.md', '.json', '.yaml', '.yml'} and not path.name.startswith('.')]
    # Keep the archive installable and keep local source/runtime records out.
    files = [p for p in files if p.name != '.gitignore']
    archive = destination / f'handraw-style-router-{VERSION}.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(files):
            bundle.write(path, str(path.relative_to(ROOT)))
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    release = {'schema': 1, 'version': VERSION,
               'archive_url': f'https://github.com/lacemou/handraw-style-router/releases/download/v{VERSION}/{archive.name}',
               'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'files': hashes}
    write(destination / 'release.json', release)
    return {'archive': str(archive), 'manifest': str(destination / 'release.json'), 'published': False}

if __name__ == '__main__':
    print(json.dumps(build(), ensure_ascii=False, indent=2))
