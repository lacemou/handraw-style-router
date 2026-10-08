"""Deterministic candidates, conversation-scoped state and observable events."""
import hashlib
import json
import re
import shutil
import uuid
from pathlib import Path

from common import RUNTIME, locked, now, read, safe_id, write
from library import canonical, current, verify_image
from scoring import (_distance, _jaccard, _profile_text, _role_bonus, ROLES,
                     infer_topic_features, score_profile, validate_topic_features)

VISUAL_KEYS = ('line', 'medium', 'palette', 'space', 'shape')
VISUAL_WORDS = {
    'line': ('极细', '细线', '粗黑', '粗线', '轮廓', '排线', '钢笔', '毛笔', '断线', '连续线'),
    'medium': ('水彩', '油画', '油画棒', '版画', '木刻', '水墨', '铅笔', '数字', '拼贴', '纸纹'),
    'palette': ('低饱和', '高饱和', '黑白', '单色', '灰', '柔和', '鲜艳', '暖色', '冷色'),
    'space': ('留白', '平面', '透视', '小人物', '几何', '拥挤', '密集', '空间'),
    'shape': ('极简', '夸张', '写实', '圆头', '笨拙', '细长', '可爱', '怪诞'),
}

def visual(profile):
    text = profile['visual_facts']['traits']
    return {key: [word for word in words if word in text] for key, words in VISUAL_WORDS.items()}

def visual_similarity(a, b, preserve=None):
    left, right = visual(a), visual(b)
    keys = preserve or VISUAL_KEYS
    values = [_jaccard(left[key], right[key]) for key in keys if left[key] or right[key]]
    return sum(values) / len(values) if values else 0.5 * (1 - _distance(a, b))

def validate_feedback(feedback):
    if feedback is None:
        return {'summary': '', 'preserve': [], 'prefer': [], 'avoid': [], 'metrics': {}}
    if not isinstance(feedback, dict) or set(feedback) - {'summary', 'preserve', 'prefer', 'avoid', 'metrics'}:
        raise ValueError('Invalid feedback contract')
    result = validate_feedback(None)
    result.update(feedback)
    if not isinstance(result['summary'], str):
        raise ValueError('summary must be text')
    for key in ('preserve', 'prefer', 'avoid'):
        if not isinstance(result[key], list) or not all(isinstance(x, str) and x for x in result[key]):
            raise ValueError(f'{key} must be a string list')
    if set(result['preserve']) - set(VISUAL_KEYS):
        raise ValueError('preserve must use line/medium/palette/space/shape')
    metrics = result['metrics']
    if not isinstance(metrics, dict) or set(metrics) - {'visual_energy', 'color_intensity', 'graphic_clarity', 'narrative_density'}:
        raise ValueError('Invalid feedback metrics')
    if any(isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 3 for v in metrics.values()):
        raise ValueError('feedback metrics must be integers 0–3')
    return result

def feedback_score(profile, feedback):
    text = _profile_text(profile).lower()
    prefer = feedback['prefer']
    lexical = sum(word.lower() in text for word in prefer) / len(prefer) if prefer else 0.5
    metrics = feedback['metrics']
    metric = sum(1 - abs(profile['route_affordances'].get(k, 1) - v) / 3 for k, v in metrics.items()) / len(metrics) if metrics else 0.5
    return (lexical + metric) / 2

def recommend(topic, profiles, features=None, *, count=5, smart=False, anchors=None,
              feedback=None, seen=None):
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 10:
        raise ValueError('Candidate count must be 1–10')
    structured = features is not None
    features = validate_topic_features(features) if structured else infer_topic_features(topic)
    feedback = validate_feedback(feedback)
    by_id = {p['style_id']: p for p in profiles}
    anchors = list(dict.fromkeys(anchors or []))
    if len(anchors) > 2 or any(x not in by_id for x in anchors):
        raise ValueError('Choose one or two valid anchors')
    if anchors and count < len(anchors):
        raise ValueError('Candidate count cannot be smaller than anchor count')
    seen = set(seen or [])
    pool = [p for p in profiles if p['style_id'] not in seen | set(anchors)
            and not any(word.lower() in _profile_text(p).lower() for word in feedback['avoid'])]
    scores = {p['style_id']: score_profile(topic, features, p)['base'] for p in pool}
    if not anchors and (feedback['prefer'] or feedback['metrics']):
        scores = {p['style_id']: scores[p['style_id']] + .30 * feedback_score(p, feedback) for p in pool}
    if smart and not anchors:
        ranked = sorted(scores.values(), reverse=True)
        if ranked:
            # A heuristic count, never described as model certainty.
            near = sum(value >= ranked[0] - 0.075 for value in ranked)
            count = max(1, min(10, near))
    elif smart and anchors:
        near = 0
        for anchor in anchors:
            values = [visual_similarity(by_id[anchor], p, feedback['preserve']) * .55
                      + feedback_score(p, feedback) * .30 + scores[p['style_id']] * .15 for p in pool]
            if values:
                near += min(4, sum(value >= max(values) - .075 for value in values))
        count = max(len(anchors), min(5 if len(anchors) == 1 else 10, len(anchors) + near))
    if anchors:
        count = min(count, 5 if len(anchors) == 1 else 10)
    result = []
    for anchor in anchors:
        result.append({'style_id': anchor, 'anchor': anchor, 'kind': 'anchor',
                       'reason': '保留你选中的风格作为对照。'})
    while pool and len(result) < count:
        index = len(result) - len(anchors)
        anchor = anchors[index % len(anchors)] if anchors else None
        role = ROLES[len(result)] if not anchors and len(result) < 5 else '扩展候选'
        def merit(profile):
            base = scores[profile['style_id']]
            if anchor:
                value = .55 * visual_similarity(by_id[anchor], profile, feedback['preserve']) + .30 * feedback_score(profile, feedback) + .15 * base
            else:
                value = base + _role_bonus(role, profile, base)
            selected = [by_id[x['style_id']] for x in result if x['kind'] != 'anchor']
            if selected:
                value -= .12 * max(visual_similarity(profile, p) for p in selected)
            return value
        chosen = min(pool, key=lambda p: (-merit(p), p['style_id']))
        pool.remove(chosen)
        reason = (f'围绕 {anchor} 的画风探索；{feedback["summary"] or "比较邻近的视觉特征"}。'
                  if anchor else f'{role}；基于主题画像与候选差异初筛。')
        result.append({'style_id': chosen['style_id'], 'anchor': anchor, 'kind': 'new', 'reason': reason})
    for item in result:
        profile = by_id[item['style_id']]
        item.update({key: profile[key] for key in ('generation_name', 'reference', 'group', 'preview_path')})
        item['traits'] = profile['visual_facts']['traits']
        item['preview_markdown'] = f'![{item["style_id"]} 上游参考图](<{profile["preview_path"]}>)'
    return {'candidates': result, 'feedback': feedback, 'count': len(result),
            'mode': 'fast', 'feature_source': 'structured_features' if structured else 'keyword_fallback',
            'warnings': ['文字画像为自动推导，推荐质量尚待体验验收。'] + ([] if structured else ['缺少模型解析，正在使用关键词降级。'])}

def session_path(conversation, runtime=RUNTIME):
    return Path(runtime) / 'sessions' / (safe_id(conversation) + '.json')

def start(topic, conversation, features=None, *, count=5, smart=False, runtime=RUNTIME):
    if not topic.strip():
        raise ValueError('主题不能为空')
    directory, profiles = current(runtime)
    result = recommend(topic, profiles, features, count=count, smart=smart)
    state = {'conversation': safe_id(conversation), 'task_id': uuid.uuid4().hex, 'topic': topic,
             'library': str(directory.resolve()), 'features': features, 'round': 1,
             'smart': smart,
             'seen': [x['style_id'] for x in result['candidates']], 'selected': [],
             'history': [result], 'created_at': now()}
    write(session_path(conversation, runtime), state)
    return state

def load_session(conversation, runtime=RUNTIME):
    state = read(session_path(conversation, runtime))
    if state['conversation'] != conversation:
        raise ValueError('会话不匹配；请开始新任务')
    return state

def event(state, styles, kind, token, runtime=RUNTIME):
    if kind not in {'selected', 'delivered', 'generated'}:
        raise ValueError('Invalid event kind')
    if not isinstance(token, str) or not token:
        raise ValueError('Event ID required')
    path = Path(runtime) / 'events.json'
    with locked(Path(runtime) / 'events'):
        payload = read(path) if path.exists() else {'events': []}
        for style in styles:
            key = hashlib.sha256(json.dumps([state['task_id'], kind, token, style]).encode()).hexdigest()
            if not any(x['id'] == key for x in payload['events']):
                payload['events'].append({'id': key, 'style': style, 'kind': kind, 'time': now(), 'task': state['task_id']})
        write(path, payload)

def select(conversation, styles, token, runtime=RUNTIME):
    state = load_session(conversation, runtime)
    aliases = read(Path(state['library']) / 'style_alias_map.json')
    styles = list(dict.fromkeys(canonical(x, aliases) for x in styles))
    allowed = {x['style_id'] for x in state['history'][-1]['candidates']}
    if not 1 <= len(styles) <= 2 or not set(styles) <= allowed:
        raise ValueError('请选择本轮展示的一到两个编号')
    state['selected'] = styles
    event(state, styles, 'selected', token, runtime)
    write(session_path(conversation, runtime), state)
    return {'selected': styles, 'next_action': 'ask', 'options': ['继续探索', '交付材料', '分别生图']}

def explore(conversation, feedback, *, count=None, smart=None, runtime=RUNTIME):
    state = load_session(conversation, runtime)
    if not state['selected']:
        raise ValueError('先选择一到两个锚点')
    profiles = read(Path(state['library']) / 'profiles.json')['styles']
    requested = count if count is not None else (5 if len(state['selected']) == 1 else 6)
    previous = dict(state['history'][-1]['feedback'])
    if not isinstance(feedback, dict):
        raise ValueError('Feedback must be an object')
    previous.update(feedback)
    smart = state.get('smart', False) if smart is None else smart
    result = recommend(state['topic'], profiles, state['features'], count=requested, smart=smart,
                       anchors=state['selected'], feedback=previous, seen=state['seen'])
    state['round'] += 1
    state['smart'] = smart
    state['seen'] = list(dict.fromkeys(state['seen'] + [x['style_id'] for x in result['candidates']]))
    state['history'].append(result)
    write(session_path(conversation, runtime), state)
    return result

def shortlist(conversation, runtime=RUNTIME, *, feedback=None):
    """Fine mode is an Agent visual judgement, not a hidden model/API call."""
    state = load_session(conversation, runtime)
    latest = state['history'][-1]
    merged = dict(latest['feedback'])
    if feedback is not None:
        validate_feedback(feedback)
        merged.update(feedback)
    feedback = validate_feedback(merged)
    summary = feedback['summary'].strip().strip('。！! .')
    vague = {'', '精细模式', '开启精细模式', '开始精细模式', '尝试一次精细模式', '更准一点', '再看看', '不满意'}
    if not any(feedback[key] for key in ('preserve', 'prefer', 'avoid', 'metrics')) and summary in vague:
        return {'status': 'needs_details', 'message': '精细模式需要具体反馈；请先引导用户补充，不生成短名单或查看图片。',
                'guidance': ['想突出什么感受或矛盾？例如焦虑、自嘲，或想得太多。',
                             '现有五个中，喜欢或不喜欢哪一点？例如线条、颜色、人物或留白。',
                             '希望更直观，还是更抽象？任选一个方面回答即可。']}
    profiles = read(Path(state['library']) / 'profiles.json')['styles']
    result = recommend(state['topic'], profiles, state['features'], count=10,
                       anchors=state['selected'], feedback=feedback,
                       seen=set(state['seen']) - {x['style_id'] for x in latest['candidates']} if state['selected'] else [])
    state['fine_shortlist'] = result['candidates']
    state['fine_feedback'] = feedback
    state['fine_limit'] = 10 if state.get('smart') else len(latest['candidates'])
    write(session_path(conversation, runtime), state)
    return result

def refine(conversation, decisions, runtime=RUNTIME):
    state = load_session(conversation, runtime)
    pool = {x['style_id']: x for x in state.get('fine_shortlist', [])}
    if not isinstance(decisions, dict) or decisions.get('viewed_images') is not True:
        raise ValueError('精细模式必须实际查看参考图，不得声称已查看')
    picks = decisions.get('candidates')
    if not isinstance(picks, list) or not 1 <= len(picks) <= 10:
        raise ValueError('精细候选数量必须为1–10')
    if len(picks) > state.get('fine_limit', 5):
        raise ValueError('未开启智能数量或明确扩展时，精细模式不能增加展示数量')
    ids = [x.get('style_id') for x in picks]
    if len(set(ids)) != len(ids) or not set(ids) <= set(pool) or not set(state['selected']) <= set(ids):
        raise ValueError('精细结果须来自短名单，不能重复或丢失锚点')
    if len(state['selected']) == 1 and len(picks) > 5:
        raise ValueError('单路线最多5个')
    for pick in picks:
        if not isinstance(pick.get('reason'), str) or not pick['reason'].strip():
            raise ValueError('需要基于实际图像特征的理由')
    result = {'mode': 'fine', 'count': len(picks), 'feedback': state['fine_feedback'],
              'candidates': [{**pool[x['style_id']], 'reason': x['reason']} for x in picks],
              'warnings': ['参考图仅用于评估画风；不表示已生成用户主题的图片。']}
    state['history'][-1] = result
    state['seen'] = list(dict.fromkeys(state['seen'] + ids))
    state.pop('fine_shortlist', None)
    state.pop('fine_feedback', None)
    state.pop('fine_limit', None)
    write(session_path(conversation, runtime), state)
    return result

def positive_traits(text):
    return '；'.join(x.strip() for x in re.split(r'[；;。\n]+', text)
                    if x.strip() and not any(word in x for word in ('避免', '不要', '不准', '禁止'))
                    and not re.search(r'无(?:写实纹理|精细材质|真实纹理)', x))

ISOLATION = '所附图片仅用于参考画风。只提取线条、笔触、媒介、材质、色彩倾向和视觉语言；不要复制参考图中的主体、人物、服装、道具、动作、场景、构图、文字或故事。最终画面内容完全以用户主题为准。'

def deliver(conversation, token, *, model='unknown', user_requirements=None, runtime=RUNTIME):
    if user_requirements is not None and (not isinstance(user_requirements, list) or
            not all(isinstance(x, str) and x.strip() for x in user_requirements)):
        raise ValueError('user_requirements must be a list of verbatim user statements')
    state = load_session(conversation, runtime)
    if user_requirements is None:
        user_requirements = state.get('user_requirements', [])
    else:
        state['user_requirements'] = user_requirements
        write(session_path(conversation, runtime), state)
    if not state['selected']:
        raise ValueError('先选择风格')
    directory = Path(state['library'])
    catalog = {x['number']: x for x in read(directory / 'catalog.json')}
    assets = read(directory / 'assets.json')
    policy = read(directory / 'model_capabilities.json')
    aliases = read(directory / 'style_alias_map.json')
    destination = Path(runtime) / 'deliveries' / state['task_id'] / hashlib.sha256(token.encode()).hexdigest()[:16]
    destination.mkdir(parents=True, exist_ok=True)
    materials = []
    for number in state['selected']:
        style = catalog[number]
        model_policy = policy.get('models', {}).get(model, {})
        capability = dict(policy.get('default', {}))
        capability.update({k: v for k, v in model_policy.items() if k != 'styles'})
        legacy = aliases.get('new_to_legacy', {}).get(number, '')
        capability.update(model_policy.get('styles', {}).get(number) or model_policy.get('styles', {}).get(legacy, {}))
        raw = number in {'FE-048', 'FE-049', 'FE-051', 'FH-050', 'FD-042'}
        traits = style['traits'] if raw else positive_traits(style['traits'])
        strong_name = capability.get('name_activation') == 'strong'
        need_image = not strong_name and not (capability.get('traits_activation') == 'strong' and traits)
        if strong_name:
            traits = ''
        prompt = '原始主题（逐字保留）：\n' + state['topic']
        if user_requirements:
            prompt += '\n\n用户对话补充（原话，按对话顺序）：\n' + '\n'.join(user_requirements)
        prompt += f'\n\n已选画风：#{number} {style["generation_name"]}。参考作者/风格：{style["reference"]}。'
        if traits:
            prompt += f'\n核心风格特征：{traits}。'
        prompt += '\n忠实表达用户主题，不额外编造人物经历、事实或画面文字。'
        if need_image:
            prompt += '\n' + ISOLATION
        feedback = state['history'][-1]['feedback']
        if feedback['summary']:
            prompt += '\n反馈解析摘要（辅助理解，不替代以上用户原话）：' + feedback['summary']
        image = destination / Path(assets[number]['local']).name
        source_image = directory / assets[number]['local']
        if hashlib.sha256(source_image.read_bytes()).hexdigest() != assets[number]['sha256']:
            raise ValueError('参考图缓存已损坏，停止交付')
        verify_image(source_image)
        shutil.copy2(source_image, image)
        text_path = destination / (number + '.md')
        text_path.write_text(f'# {number} 生图材料\n\n```text\n{prompt}\n```\n\n'
                             f'参考图：{image.name}。' + ('请随提示词附上。' if need_image else '当前模型策略不要求附图，仅供比较。') +
                             f'\n\n来源：yang0 https://github.com/yang0/handraw-style\n版本：{directory.name}\n', encoding='utf-8')
        materials.append({'style_id': number, 'prompt': prompt, 'prompt_path': str(text_path.resolve()),
                          'reference_path': str(image.resolve()), 'reference_required': need_image,
                          'model': model, 'external_generation': 'unknown'})
    shutil.copy2(directory / 'UPSTREAM-LICENSE', destination / 'UPSTREAM-LICENSE')
    write(destination / 'materials.json', {'topic': state['topic'], 'user_requirements': user_requirements, 'materials': materials, 'source': read(directory / 'source.json')})
    event(state, state['selected'], 'delivered', token, runtime)
    return {'directory': str(destination.resolve()), 'materials': materials, 'status': '材料已交付；未生成图片'}

def generated(conversation, styles, token, output_paths, runtime=RUNTIME):
    state = load_session(conversation, runtime)
    if len(styles) != len(output_paths) or not styles or not set(styles) <= set(state['selected']):
        raise ValueError('生成记录需对应已选风格和实际输出文件')
    for path in output_paths:
        if not Path(path).is_file():
            raise ValueError('没有实际生成输出；不得记成功')
    event(state, styles, 'generated', token, runtime)
    return {'status': '已生成，未检查', 'external_generation': 'unknown'}

def stats(runtime=RUNTIME):
    path = Path(runtime) / 'events.json'
    events = read(path)['events'] if path.exists() else []
    counts = {}
    for entry in events:
        style = counts.setdefault(entry['style'], {'selected': 0, 'delivered': 0, 'generated': 0})
        style[entry['kind']] += 1
    return {'counts': counts, 'external_generation': 'unknown', 'affects_ranking': False}
