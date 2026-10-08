import hashlib
import io
import json
import sys
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from common import read, write
from library import asset_path, canonical, current, git_blob_hash, inspect_snapshot, sync, validate_catalog
from profile_builder import build_profiles
from updates import check_code, install_code, update
from workflow import (deliver, explore, generated, recommend, refine, select,
                      shortlist, start, stats, validate_feedback)

def image_bytes(format='WEBP'):
    buffer = io.BytesIO()
    Image.new('RGB', (12, 12), 'white').save(buffer, format=format)
    return buffer.getvalue()

def catalog(size=16):
    return [{'number': f'FA-{i:03}', 'group': 'FA 国际社论幽默',
             'reference': 'Test artist', 'generation_name': f'Style {i}',
             'traits': ('极细钢笔线、黑白、大量留白、日常幽默' if i % 2 else '粗黑线、高饱和、强烈色块、夸张人物')} for i in range(1, size + 1)]

class Remote:
    def __init__(self, sha='a' * 40, size=16):
        self.sha = sha
        self.styles = catalog(size)
        self.assets = {f'images/individual/FA/{x["number"]}.webp': image_bytes() for x in self.styles}
        self.corrupt = False
        self.invalid_index = False
        self.fail = False
        self.asset_requests = 0

    def __call__(self, url):
        if self.fail:
            raise OSError('network unavailable')
        if url.endswith('release.json'):
            raise urllib.error.HTTPError(url, 404, 'not published', {}, None)
        if '/git/ref/' in url:
            return json.dumps({'object': {'sha': self.sha}}).encode()
        if '/git/trees/' in url:
            paths = list(self.assets) + ['skills/handdraw-style-prompter/references/' + x for x in ('styles.json', 'style_alias_map.json', 'model_capabilities.json')]
            return json.dumps({'tree': [{'type': 'blob', 'path': p, 'sha': git_blob_hash(self.assets.get(p, p.encode()))} for p in paths]}).encode()
        if url.endswith('styles.json'):
            value = [self.styles[0], self.styles[0]] if self.invalid_index else self.styles
            return json.dumps(value).encode()
        if url.endswith('style_alias_map.json'):
            return json.dumps({'legacy_to_new': {'001': 'FA-001'}, 'new_to_legacy': {'FA-001': '001'}}).encode()
        if url.endswith('model_capabilities.json'):
            return json.dumps({'default': {'name_activation': 'unknown', 'traits_activation': 'unknown'},
                               'models': {'known': {'styles': {'FA-001': {'name_activation': 'strong'}}}}}).encode()
        if url.endswith('LICENSE'):
            return b'MIT License with attribution to yang0'
        path = url.split(self.sha + '/', 1)[-1]
        if path in self.assets:
            self.asset_requests += 1
            return b'corrupt' if self.corrupt else self.assets[path]
        raise ValueError(url)

FEATURES = {'subject': ['technology'], 'action': ['conversation'], 'scene': ['office'],
            'abstraction': ['editorial'], 'mood': ['serious'], 'narrative_density': 1}

class V2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = Path(self.tmp.name)
        self.remote = Remote()
        sync(self.runtime, self.remote)

    def tearDown(self):
        self.tmp.cleanup()

    def profiles(self):
        return current(self.runtime)[1]

    def begin(self):
        return start('人工智能与职场', 'chat1', FEATURES, runtime=self.runtime)

    def choose(self, n=1):
        state = self.begin()
        ids = [x['style_id'] for x in state['history'][-1]['candidates'][:n]]
        select('chat1', ids, 'select1', self.runtime)
        return ids

    def test_delivery_preserves_original_topic_and_user_words(self):
        topic = 'OpenAI 接下来 28 天：每天要么改进，要么重置。\n保留  两个空格！'
        state = start(topic, 'chat1', FEATURES, runtime=self.runtime)
        chosen = state['history'][-1]['candidates'][0]['style_id']
        select('chat1', [chosen], 'verbatim-select', self.runtime)
        requirements = ['强调28天持续推进的决心，但可能只是小更新。', '风格完全开放，要有趣味性。']
        result = deliver('chat1', 'verbatim-deliver', user_requirements=requirements, runtime=self.runtime)
        prompt = result['materials'][0]['prompt']
        self.assertTrue(prompt.startswith('原始主题（逐字保留）：\n' + topic))
        self.assertIn('\n'.join(requirements), prompt)
        saved = read(Path(result['directory']) / 'materials.json')
        self.assertEqual(saved['topic'], topic)
        self.assertEqual(saved['user_requirements'], requirements)
        again = deliver('chat1', 'verbatim-again', runtime=self.runtime)
        self.assertIn('\n'.join(requirements), again['materials'][0]['prompt'])
        cleared = deliver('chat1', 'verbatim-clear', user_requirements=[], runtime=self.runtime)
        self.assertNotIn(requirements[0], cleared['materials'][0]['prompt'])

    def test_sync_validates_full_webp_library_and_alias(self):
        directory, profiles = current(self.runtime)
        self.assertEqual(inspect_snapshot(directory)['style_count'], 16)
        self.assertEqual(canonical('1', read(directory / 'style_alias_map.json')), 'FA-001')
        self.assertTrue(all(x['status'] == 'ready' for x in profiles))

    def test_new_entries_immediately_recommendable(self):
        remote = Remote('b' * 40, 17)
        sync(self.runtime, remote)
        profiles = self.profiles()
        self.assertIn('FA-017', {x['style_id'] for x in profiles})
        self.assertEqual(len(recommend('主题', profiles, FEATURES, count=10)['candidates']), 10)

    def test_failed_download_does_not_change_pointer(self):
        before = read(self.runtime / 'CURRENT.json')
        remote = Remote('b' * 40, 17)
        remote.corrupt = True
        with self.assertRaises(Exception):
            sync(self.runtime, remote)
        self.assertEqual(read(self.runtime / 'CURRENT.json'), before)
        self.assertFalse(any(self.runtime.glob('sync-*')))

    def test_duplicate_database_is_rejected_before_activation(self):
        before = read(self.runtime / 'CURRENT.json')
        remote = Remote('b' * 40)
        remote.invalid_index = True
        with self.assertRaises(ValueError):
            sync(self.runtime, remote)
        self.assertEqual(read(self.runtime / 'CURRENT.json'), before)

    def test_unchanged_blobs_reuse_local_images(self):
        remote = Remote('b' * 40)
        sync(self.runtime, remote)
        self.assertEqual(remote.asset_requests, 0)

    def test_current_snapshot_corruption_is_detected(self):
        directory, _ = current(self.runtime)
        (directory / 'previews/FA-001.webp').write_bytes(b'bad')
        with self.assertRaises(ValueError):
            inspect_snapshot(directory)

    def test_default_smart_and_count_bounds(self):
        self.assertEqual(len(self.begin()['history'][0]['candidates']), 5)
        for count in (1, 3, 10):
            result = recommend('主题', self.profiles(), FEATURES, count=count)
            self.assertEqual(result['count'], count)
        self.assertLessEqual(recommend('主题', self.profiles(), FEATURES, smart=True)['count'], 10)
        for count in (0, 11, True):
            with self.assertRaises(ValueError):
                recommend('主题', self.profiles(), count=count)

    def test_fallback_is_not_labeled_as_model_semantics(self):
        result = recommend('主题', self.profiles())
        self.assertEqual(result['feature_source'], 'keyword_fallback')
        self.assertTrue(any('降级' in x for x in result['warnings']))

    def test_two_anchors_retained_and_seen_candidates_not_repeated(self):
        ids = self.choose(2)
        initial = set(x['style_id'] for x in read(self.runtime / 'sessions/chat1.json')['history'][0]['candidates'])
        result = explore('chat1', {'summary': '降低饱和度', 'preserve': ['line'], 'metrics': {'color_intensity': 0}}, runtime=self.runtime)
        self.assertEqual({x['style_id'] for x in result['candidates'] if x['kind'] == 'anchor'}, set(ids))
        self.assertFalse({x['style_id'] for x in result['candidates'] if x['kind'] == 'new'} & initial)
        self.assertEqual({x['anchor'] for x in result['candidates'] if x['kind'] == 'new'}, set(ids))

    def test_feedback_accumulates_and_avoid_excludes_new_only(self):
        self.choose()
        first = explore('chat1', {'preserve': ['line'], 'avoid': ['高饱和'], 'summary': '降低色彩刺激'}, runtime=self.runtime)
        self.assertTrue(all('高饱和' not in x['traits'] for x in first['candidates'] if x['kind'] == 'new'))
        second = explore('chat1', {'summary': '继续降低色彩刺激'}, runtime=self.runtime)
        self.assertEqual(second['feedback']['preserve'], ['line'])
        self.assertEqual(second['feedback']['avoid'], ['高饱和'])

    def test_new_tasks_and_new_chats_ignore_history_counts(self):
        first = self.begin()
        self.choose()
        second = start(first['topic'], 'chat2', FEATURES, runtime=self.runtime)
        self.assertNotEqual(first['task_id'], second['task_id'])
        self.assertEqual(first['history'][0]['candidates'], second['history'][0]['candidates'])
        self.assertEqual(second['selected'], [])

    def test_select_requires_visible_candidates_and_returns_action_question(self):
        ids = self.choose()
        result = select('chat1', ids, 'select1', self.runtime)
        self.assertEqual(result['next_action'], 'ask')
        with self.assertRaises(ValueError):
            select('chat1', ['FA-999'], 'bad', self.runtime)
        self.assertEqual(stats(self.runtime)['counts'][ids[0]]['selected'], 1)

    def test_materials_are_paired_reference_isolation_and_attribution(self):
        ids = self.choose(2)
        result = deliver('chat1', 'export1', runtime=self.runtime)
        self.assertEqual(len(result['materials']), 2)
        for material in result['materials']:
            self.assertTrue(Path(material['reference_path']).exists())
            self.assertTrue(material['reference_required'])
            self.assertIn('仅用于参考画风', material['prompt'])
            self.assertIn('人工智能与职场', material['prompt'])
            self.assertIn('yang0', Path(material['prompt_path']).read_text())
        deliver('chat1', 'export1', runtime=self.runtime)
        counts = stats(self.runtime)
        self.assertEqual(counts['counts'][ids[0]]['delivered'], 1)
        self.assertEqual(counts['external_generation'], 'unknown')
        self.assertFalse(counts['affects_ranking'])

    def test_known_model_policy_can_omit_reference_requirement(self):
        state = self.begin()
        state['selected'] = ['FA-001']
        write(self.runtime / 'sessions/chat1.json', state)
        result = deliver('chat1', 'known', model='known', runtime=self.runtime)
        self.assertFalse(result['materials'][0]['reference_required'])
        self.assertTrue(Path(result['materials'][0]['reference_path']).exists())

    def test_generation_requires_actual_file_and_selected_style(self):
        ids = self.choose()
        with self.assertRaises(ValueError):
            generated('chat1', ids, 'tool1', ['/missing'], self.runtime)
        output = self.runtime / 'output.png'
        output.write_bytes(image_bytes('PNG'))
        self.assertEqual(generated('chat1', ids, 'tool1', [str(output)], self.runtime)['status'], '已生成，未检查')
        generated('chat1', ids, 'tool1', [str(output)], self.runtime)
        self.assertEqual(stats(self.runtime)['counts'][ids[0]]['generated'], 1)

    def test_feedback_changes_recall_without_selected_anchor(self):
        import copy
        a = copy.deepcopy(self.profiles()[0])
        b = copy.deepcopy(a)
        a['style_id'], b['style_id'] = 'FA-001', 'FA-002'
        a['route_affordances']['color_intensity'] = 0
        b['route_affordances']['color_intensity'] = 3
        pool = [a, b]
        low = recommend('主题', pool, FEATURES, count=1, feedback={'metrics': {'color_intensity': 0}})
        high = recommend('主题', pool, FEATURES, count=1, feedback={'metrics': {'color_intensity': 3}})
        self.assertEqual(low['candidates'][0]['style_id'], 'FA-001')
        self.assertEqual(high['candidates'][0]['style_id'], 'FA-002')

    def test_fine_mode_requires_details_without_changing_state(self):
        self.begin()
        path = self.runtime / 'sessions/chat1.json'
        original = path.read_bytes()
        for feedback in (None, {}, {'summary': '开启精细模式'}, {'summary': '不满意'}):
            result = shortlist('chat1', self.runtime, feedback=feedback)
            self.assertEqual(result['status'], 'needs_details')
            self.assertNotIn('candidates', result)
            self.assertEqual(path.read_bytes(), original)
        self.choose()
        self.assertEqual(shortlist('chat1', self.runtime)['status'], 'needs_details')

    def test_fine_mode_uses_details_and_keeps_existing_constraints(self):
        self.choose()
        explore('chat1', {'prefer': ['黑白'], 'summary': '保留黑白'}, runtime=self.runtime)
        result = shortlist('chat1', self.runtime, feedback={'avoid': ['高饱和']})
        self.assertTrue(result['candidates'])
        state = read(self.runtime / 'sessions/chat1.json')
        self.assertEqual(state['fine_feedback']['prefer'], ['黑白'])
        self.assertEqual(state['fine_feedback']['avoid'], ['高饱和'])
        self.assertTrue(set(state['selected']) <= {x['style_id'] for x in result['candidates']})

    def test_fine_mode_rejects_invented_ids_and_unviewed_images(self):
        self.choose()
        candidates = shortlist('chat1', self.runtime, feedback={'prefer': ['细线']})['candidates']
        picks = [{'style_id': x['style_id'], 'reason': '比较线条与留白'} for x in candidates[:5]]
        with self.assertRaises(ValueError):
            refine('chat1', {'viewed_images': False, 'candidates': picks}, self.runtime)
        result = refine('chat1', {'viewed_images': True, 'candidates': picks}, self.runtime)
        self.assertEqual(result['mode'], 'fine')

    def test_fine_mode_does_not_expand_default_count_silently(self):
        self.begin()
        candidates = shortlist('chat1', self.runtime, feedback={'prefer': ['细线']})['candidates']
        picks = [{'style_id': x['style_id'], 'reason': '实际参考图的线条对比'} for x in candidates[:6]]
        with self.assertRaises(ValueError):
            refine('chat1', {'viewed_images': True, 'candidates': picks}, self.runtime)

    def test_library_update_does_not_change_active_task_snapshot(self):
        state = self.begin()
        ids = [state['history'][0]['candidates'][0]['style_id']]
        select('chat1', ids, 'selection', self.runtime)
        sync(self.runtime, Remote('b' * 40, 17))
        self.assertEqual(read(self.runtime / 'sessions/chat1.json')['library'], state['library'])
        result = explore('chat1', {}, runtime=self.runtime)
        self.assertNotIn('FA-017', {x['style_id'] for x in result['candidates']})

    def test_new_conversation_has_no_resume_state(self):
        self.begin()
        from workflow import load_session
        with self.assertRaises(FileNotFoundError):
            load_session('different-conversation', self.runtime)

    def test_smart_mode_can_be_disabled_and_feedback_can_be_cleared(self):
        self.choose()
        explore('chat1', {'avoid': ['高饱和']}, smart=True, runtime=self.runtime)
        result = explore('chat1', {'avoid': []}, smart=False, runtime=self.runtime)
        self.assertFalse(read(self.runtime / 'sessions/chat1.json')['smart'])
        self.assertEqual(result['feedback']['avoid'], [])

    def test_blank_traits_are_legal_and_invalid_fields_are_not(self):
        entry = catalog(1)[0]
        entry['traits'] = ''
        validate_catalog([entry])
        entry['traits'] = None
        with self.assertRaises(ValueError):
            validate_catalog([entry])
        with self.assertRaises(ValueError):
            validate_feedback({'preserve': ['invented-axis']})

    def test_artist_handle_and_new_group_do_not_inject_technology(self):
        entry = {'number': 'FF-008', 'group': 'FF 3D黏土毛毡与纸雕',
                 'reference': 'OscarAI', 'generation_name': 'Fuzzy Plush Toy',
                 'traits': '可爱的毛绒人偶，温暖柔和'}
        profile = build_profiles([entry])['styles'][0]
        self.assertNotIn('technology', profile['route_affordances']['subject'])
        entry['reference'] = 'Another artist'
        self.assertEqual(profile['route_affordances'], build_profiles([entry])['styles'][0]['route_affordances'])

    def test_reference_grid_is_preferred(self):
        self.assertEqual(asset_path('FA-001', {'images/individual/FA/FA-001.webp', 'images/individual/FA/FA-001_grid.webp'}), 'images/individual/FA/FA-001_grid.webp')

    def test_unified_update_reports_code_and_library_separately(self):
        result = update(runtime=self.runtime, getter=self.remote)
        self.assertEqual(result['router']['code'], 'unpublished')
        self.assertEqual(result['library']['library'], 'current')
        self.remote.fail = True
        result = update(runtime=self.runtime, getter=self.remote)
        self.assertEqual(result['library']['library'], 'failed')
        self.assertEqual(result['router']['code'], 'failed')

    def test_code_archive_validation_and_install_preserve_runtime(self):
        root = self.runtime / 'package'
        root.mkdir()
        (root / 'SKILL.md').write_text('old')
        files = {'SKILL.md': b'new', 'version.json': b'{"version":"2.1.0"}', 'scripts/router.py': b'print("new")\n'}
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as stream:
            for name, value in files.items():
                stream.writestr(name, value)
        content = archive.getvalue()
        release = {'version': '2.1.0', 'archive_url': 'https://github.com/lacemou/handraw-style-router/releases/download/v2.1.0/skill.zip',
                   'archive_sha256': hashlib.sha256(content).hexdigest(),
                   'files': {k: hashlib.sha256(v).hexdigest() for k, v in files.items()}}
        bad = {**release, 'archive_sha256': 'bad'}
        with self.assertRaises(ValueError):
            install_code(bad, root=root, runtime=self.runtime, getter=lambda _: content)
        self.assertEqual((root / 'SKILL.md').read_text(), 'old')
        result = install_code(release, root=root, runtime=self.runtime, getter=lambda _: content)
        self.assertEqual(result['code'], 'updated')
        self.assertEqual((root / 'SKILL.md').read_text(), 'new')
        self.assertTrue((self.runtime / 'CURRENT.json').exists())

if __name__ == '__main__':
    unittest.main()
