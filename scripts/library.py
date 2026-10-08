"""Pin and validate a whole upstream snapshot before atomic activation."""
import hashlib
import json
import os
import re
import shutil
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image
from common import RUNTIME, locked, now, read, write
from profile_builder import SCHEMA_VERSION, build_profiles

UPSTREAM = 'yang0/handraw-style'
PREFIX = 'skills/handdraw-style-prompter/references/'

def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'handraw-style-router/2.0'})
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read()

def git_blob_hash(content):
    return hashlib.sha1(b'blob ' + str(len(content)).encode('ascii') + b'\0' + content).hexdigest()

def canonical(value, aliases=None):
    value = str(value).strip().upper()
    if value.isdigit():
        value = value.zfill(3)
    else:
        match = re.fullmatch(r'([A-Z]{2})[-_]?(\d+)', value)
        if match:
            value = f'{match[1]}-{int(match[2]):03}'
    return (aliases or {}).get('legacy_to_new', {}).get(value, value)

def validate_catalog(styles):
    if not isinstance(styles, list) or not styles:
        raise ValueError('风格索引必须是非空数组')
    seen = set()
    for entry in styles:
        if not isinstance(entry, dict):
            raise ValueError('风格条目不是对象')
        for key in ('number', 'group', 'generation_name', 'reference'):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise ValueError(f'风格条目缺少有效字段：{key}')
        if not isinstance(entry.get('traits'), str):
            raise ValueError('traits 必须是字符串；允许为空并用参考图兜底')
        number = entry['number']
        if not re.fullmatch(r'(?:[A-Z]{2}-\d{3}|\d{3})', number) or number in seen:
            raise ValueError(f'编号不合法或重复：{number}')
        seen.add(number)
    return styles

def asset_path(number, paths):
    if '-' in number:
        category = number.split('-')[0]
        stem = f'images/individual/{category}/{number}'
    else:
        bucket = '001-200' if int(number) <= 200 else '201-400'
        stem = f'images/individual/{bucket}/{number}'
    for suffix in ('_grid.webp', '.webp', '_grid.png', '.png'):
        if stem + suffix in paths:
            return stem + suffix
    raise ValueError(f'找不到编号对应的参考图：{number}')

def verify_image(path):
    with Image.open(path) as image:
        if image.width < 1 or image.height < 1:
            raise ValueError('Invalid image dimensions')
        image.verify()
    with Image.open(path) as image:
        image.load()

def validate_policy(policy):
    if not isinstance(policy, dict) or not isinstance(policy.get('default', {}), dict) or not isinstance(policy.get('models', {}), dict):
        raise ValueError('Invalid model capability schema')
    entries = [policy.get('default', {})]
    for model in policy.get('models', {}).values():
        if not isinstance(model, dict) or not isinstance(model.get('styles', {}), dict):
            raise ValueError('Invalid model capability schema')
        entries.append(model)
        entries.extend(model.get('styles', {}).values())
    for entry in entries:
        if not isinstance(entry, dict) or any(entry.get(key, 'unknown') not in {'strong', 'weak', 'none', 'unknown'} for key in ('name_activation', 'traits_activation')):
            raise ValueError('Invalid activation capability')

def inspect_snapshot(directory):
    directory = Path(directory)
    styles = validate_catalog(read(directory / 'catalog.json'))
    profiles = read(directory / 'profiles.json')['styles']
    assets = read(directory / 'assets.json')
    ids = {x['number'] for x in styles}
    validate_policy(read(directory / 'model_capabilities.json'))
    if {x['style_id'] for x in profiles} != ids or set(assets) != ids:
        raise ValueError('数据库、画像与图片编号不一致')
    for number, asset in assets.items():
        path = (directory / asset['local']).resolve()
        if not path.is_relative_to(directory.resolve()):
            raise ValueError('Unsafe asset path')
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != asset['sha256'] or git_blob_hash(content) != asset['blob']:
            raise ValueError(f'图片校验失败：{number}')
        verify_image(path)
    # All entries must be usable, including new entries.
    from scoring import infer_topic_features, score_profile
    features = infer_topic_features('办公室讨论人工智能')
    for profile in profiles:
        score_profile('办公室讨论人工智能', features, profile)
    return {'style_count': len(styles), 'validated': True}

def current(runtime=RUNTIME):
    pointer = read(Path(runtime) / 'CURRENT.json')
    revision = pointer['revision']
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Invalid snapshot revision')
    directory = Path(runtime) / 'libraries' / revision
    refresh_profiles(directory)
    return directory, read(directory / 'profiles.json')['styles']

def refresh_profiles(directory):
    """Local code fixes rebuild derived labels without changing pinned assets."""
    directory = Path(directory)
    if read(directory / 'profiles.json').get('schema_version') == SCHEMA_VERSION:
        return
    with locked(directory):
        if read(directory / 'profiles.json').get('schema_version') == SCHEMA_VERSION:
            return
        payload = build_profiles(read(directory / 'catalog.json'), source=read(directory / 'source.json'))
        assets = read(directory / 'assets.json')
        for profile in payload['styles']:
            profile['status'] = 'ready'
            profile['preview_path'] = str((directory / assets[profile['style_id']]['local']).resolve())
        write(directory / 'profiles.json', payload)

def sync(runtime=RUNTIME, getter=fetch):
    runtime = Path(runtime)
    with locked(runtime):
        sha = json.loads(getter(f'https://api.github.com/repos/{UPSTREAM}/git/ref/heads/master'))['object']['sha']
        if not re.fullmatch(r'[0-9a-f]{40}', sha):
            raise ValueError('Invalid upstream commit')
        final = runtime / 'libraries' / sha
        if final.exists():
            refresh_profiles(final)
            checked = inspect_snapshot(final)
            write(runtime / 'CURRENT.json', {'revision': sha, 'activated_at': now()})
            return {'library': 'current', 'revision': sha, **checked}
        tree = json.loads(getter(f'https://api.github.com/repos/{UPSTREAM}/git/trees/{sha}?recursive=1'))
        if tree.get('truncated'):
            raise ValueError('上游文件清单被截断，停止更新')
        files = {item['path']: item['sha'] for item in tree['tree'] if item['type'] == 'blob'}
        base = f'https://raw.githubusercontent.com/{UPSTREAM}/{sha}/'
        index = PREFIX + 'styles.json'
        if index not in files:
            raise ValueError('上游结构不兼容：没有预期的 styles.json；原库保留')
        catalog = validate_catalog(json.loads(getter(base + index)))
        previous_dir = None
        previous_assets = {}
        if (runtime / 'CURRENT.json').exists():
            previous_dir, _ = current(runtime)
            previous_assets = read(previous_dir / 'assets.json')
        stage = Path(tempfile.mkdtemp(prefix='sync-', dir=runtime))
        try:
            assets = {}
            def download(entry):
                number = entry['number']
                source = asset_path(number, files)
                relative = f'previews/{Path(source).name}'
                destination = stage / relative
                destination.parent.mkdir(exist_ok=True)
                old = previous_assets.get(number, {})
                if old.get('blob') == files[source] and previous_dir:
                    old_path = previous_dir / old['local']
                    if hashlib.sha256(old_path.read_bytes()).hexdigest() == old.get('sha256'):
                        shutil.copy2(old_path, destination)
                    else:
                        destination.write_bytes(getter(base + source))
                else:
                    destination.write_bytes(getter(base + source))
                if git_blob_hash(destination.read_bytes()) != files[source]:
                    raise ValueError(f'上游图片blob校验失败：{number}')
                verify_image(destination)
                return number, {'source': source, 'blob': files[source], 'local': relative,
                                'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}
            with ThreadPoolExecutor(max_workers=8) as executor:
                assets.update(executor.map(download, catalog))
            for name, fallback in [('style_alias_map.json', {}), ('model_capabilities.json', {})]:
                source = PREFIX + name
                value = json.loads(getter(base + source)) if source in files else fallback
                if not isinstance(value, dict):
                    raise ValueError(f'上游结构不兼容：{name}')
                write(stage / name, value)
            validate_policy(read(stage / 'model_capabilities.json'))
            aliases = read(stage / 'style_alias_map.json').get('legacy_to_new', {})
            if not isinstance(aliases, dict) or any(target not in assets for target in aliases.values()):
                raise ValueError('旧编号映射指向不存在的风格')
            license_bytes = getter(base + 'LICENSE')
            (stage / 'UPSTREAM-LICENSE').write_bytes(license_bytes)
            if not license_bytes.strip():
                raise ValueError('Missing upstream license')
            write(stage / 'catalog.json', catalog)
            write(stage / 'assets.json', assets)
            source = {'repository': UPSTREAM, 'revision': sha, 'fetched_at': now()}
            profiles = build_profiles(catalog, source=source)
            for profile in profiles['styles']:
                profile['status'] = 'ready'
                profile['preview_path'] = str((final / assets[profile['style_id']]['local']).resolve())
            write(stage / 'profiles.json', profiles)
            write(stage / 'source.json', source)
            checked = inspect_snapshot(stage)
            final.parent.mkdir(exist_ok=True)
            os.replace(stage, final)
            write(runtime / 'CURRENT.json', {'revision': sha, 'activated_at': now()})
            return {'library': 'updated', 'revision': sha, **checked}
        finally:
            if stage.exists():
                shutil.rmtree(stage)
