#!/usr/bin/env python3
"""Route a topic to five diverse handraw-style candidates."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable


WEIGHTS = {
    "subject_action": 0.40,
    "abstraction": 0.25,
    "scene_story": 0.20,
    "mood": 0.15,
}

ROLES = [
    "最稳妥",
    "最有表现力",
    "最具故事感",
    "最容易读懂主题",
    "差异化候选",
]

DIMENSION_LABELS = {
    "subject": "主体",
    "action": "动作",
    "scene": "场景",
    "abstraction": "表达方式",
    "mood": "气质",
}

FEATURE_KEYS = ("subject", "action", "scene", "abstraction", "mood", "narrative_density")
FEATURE_LIST_KEYS = ("subject", "action", "scene", "abstraction", "mood")

ALIASES = {
    "人": "people",
    "人物": "people",
    "角色": "people",
    "日常": "daily-life",
    "生活": "daily-life",
    "科技": "technology",
    "技术": "technology",
    "城市": "city",
    "都市": "urban",
    "自然": "nature",
    "物体": "objects",
    "物件": "objects",
    "概念": "conceptual",
    "抽象": "conceptual",
    "故事": "narrative",
    "叙事": "narrative",
    "解释": "explanatory",
    "教程": "explanatory",
    "方法": "explanatory",
    "对话": "conversation",
    "讨论": "conversation",
    "工作": "work",
    "办公": "work",
    "办公室": "office",
    "家": "home",
    "街道": "urban",
    "温柔": "gentle",
    "温暖": "warm",
    "幽默": "humorous",
    "轻松": "humorous",
    "焦虑": "anxious",
    "严肃": "serious",
    "好奇": "curious",
}


def _norm(value: Any) -> str:
    raw = str(value).strip().lower()
    return ALIASES.get(raw, raw)


def _values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [_norm(item) for item in value if str(item).strip()]
    return [_norm(value)] if str(value).strip() else []


def _contains_any(text: str, words: Iterable[str]) -> bool:
    return any(word and word in text for word in words)


def validate_topic_features(features: Any) -> dict[str, Any]:
    """Validate and normalize the six-dimensional model output."""
    if not isinstance(features, dict):
        raise ValueError("topic features must be a JSON object")
    missing = [key for key in FEATURE_KEYS if key not in features]
    unknown = sorted(set(features) - set(FEATURE_KEYS))
    if missing:
        raise ValueError(f"topic features missing required fields: {', '.join(missing)}")
    if unknown:
        raise ValueError(f"topic features contain unknown fields: {', '.join(unknown)}")

    normalized: dict[str, Any] = {}
    for key in FEATURE_LIST_KEYS:
        values = features[key]
        if not isinstance(values, list) or not values:
            raise ValueError(f"topic feature '{key}' must be a non-empty JSON array")
        if not all(isinstance(value, str) and value.strip() for value in values):
            raise ValueError(f"topic feature '{key}' must contain non-empty strings")
        normalized[key] = list(dict.fromkeys(_norm(value) for value in values))

    density = features["narrative_density"]
    if isinstance(density, bool) or not isinstance(density, int) or not 0 <= density <= 3:
        raise ValueError("narrative_density must be an integer from 0 to 3")
    normalized["narrative_density"] = density
    return normalized


def infer_topic_features(topic: str) -> dict[str, Any]:
    text = topic.strip().lower()
    subject: list[str] = []
    action: list[str] = []
    scene: list[str] = []
    abstraction: list[str] = []
    mood: list[str] = []

    keyword_groups = {
        "people": ["人", "人物", "职场", "团队", "员工", "孩子", "家庭", "用户"],
        "technology": ["ai", "人工智能", "模型", "代码", "软件", "数字", "电脑", "算法"],
        "city": ["城市", "都市", "街道", "建筑", "地铁"],
        "nature": ["自然", "山", "海", "森林", "公园"],
        "objects": ["产品", "工具", "书", "手机", "设备"],
    }
    for tag, words in keyword_groups.items():
        if _contains_any(text, words):
            subject.append(tag)

    action_groups = {
        "conversation": ["讨论", "对话", "聊天", "沟通", "会议"],
        "work": ["工作", "使用", "制作", "学习", "写作", "编程", "实践"],
        "movement": ["旅行", "行走", "奔跑", "移动"],
        "observation": ["观察", "思考", "阅读", "等待"],
        "transformation": ["变化", "成长", "升级", "转变", "从零"],
        "comparison": ["比较", "对比", "选择", "差异"],
        "presentation": ["解释", "讲解", "介绍", "展示", "科普", "教程"],
        "storytelling": ["故事", "经历", "案例", "回忆", "一天"],
    }
    for tag, words in action_groups.items():
        if _contains_any(text, words):
            action.append(tag)

    scene_groups = {
        "office": ["办公室", "办公", "会议室", "职场"],
        "home": ["家里", "家庭", "房间", "厨房", "卧室"],
        "urban": ["城市", "都市", "街道", "地铁"],
        "nature": ["山", "海边", "森林", "户外", "公园"],
        "digital": ["线上", "网页", "屏幕", "网络", "数字空间"],
        "everyday": ["日常", "生活", "一天"],
    }
    for tag, words in scene_groups.items():
        if _contains_any(text, words):
            scene.append(tag)

    abstraction_groups = {
        "conceptual": ["本质", "原理", "趋势", "观点", "概念", "为什么", "思考"],
        "narrative": ["故事", "经历", "案例", "回忆", "人物"],
        "lifestyle": ["日常", "生活", "职场", "经验", "习惯"],
        "editorial": ["问题", "批评", "社会", "公共", "争议"],
        "explanatory": ["教程", "解释", "步骤", "流程", "方法", "科普", "如何"],
        "graphic": ["海报", "视觉", "设计", "图解", "信息图"],
    }
    for tag, words in abstraction_groups.items():
        if _contains_any(text, words):
            abstraction.append(tag)

    mood_groups = {
        "humorous": ["幽默", "搞笑", "吐槽", "轻松", "荒诞"],
        "gentle": ["温柔", "治愈", "安静", "细腻"],
        "warm": ["温暖", "陪伴", "亲切"],
        "intellectual": ["理性", "思考", "深度"],
        "energetic": ["活泼", "热烈", "兴奋", "大胆"],
        "anxious": ["焦虑", "困惑", "疲惫", "压力", "迷茫"],
        "serious": ["重要", "警惕", "风险", "严肃"],
        "curious": ["好奇", "探索", "发现", "尝试"],
    }
    for tag, words in mood_groups.items():
        if _contains_any(text, words):
            mood.append(tag)

    if not subject:
        subject = ["ideas"]
    if not action:
        action = ["observation"]
    if not scene:
        scene = ["everyday"]
    if not abstraction:
        abstraction = ["conceptual"]
    if not mood:
        mood = ["curious"]

    narrative_density = 3 if _contains_any(text, ["故事", "经历", "案例", "人物关系", "一天", "成长"]) else 0
    if _contains_any(text, ["解释", "教程", "方法", "原理", "如何"]):
        narrative_density = max(narrative_density, 1)
    if len(subject) >= 2 or len(action) >= 2:
        narrative_density = max(narrative_density, 2)

    return {
        "subject": list(dict.fromkeys(subject)),
        "action": list(dict.fromkeys(action)),
        "scene": list(dict.fromkeys(scene)),
        "abstraction": list(dict.fromkeys(abstraction)),
        "mood": list(dict.fromkeys(mood)),
        "narrative_density": min(3, narrative_density),
    }


def _jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    a, b = set(left), set(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _dimension_match(topic_values: list[str], style_values: list[str]) -> float:
    if not topic_values or not style_values:
        return 0.35
    normalized_topic = {_norm(value) for value in topic_values}
    normalized_style = {_norm(value) for value in style_values}
    exact = len(normalized_topic & normalized_style)
    if exact:
        return min(1.0, 0.55 + 0.15 * exact)
    families = {
        frozenset({"people", "daily-life"}),
        frozenset({"city", "urban"}),
        frozenset({"ideas", "conceptual", "editorial"}),
        frozenset({"narrative", "storytelling"}),
        frozenset({"technology", "digital"}),
        frozenset({"gentle", "warm", "quiet"}),
        frozenset({"humorous", "playful"}),
    }
    for family in families:
        if normalized_topic & family and normalized_style & family:
            return 0.48
    return 0.12


def _profile_text(profile: dict[str, Any]) -> str:
    facts = profile.get("visual_facts", {})
    return " ".join(
        str(profile.get(key, "")) for key in ("generation_name", "reference", "group")
    ) + " " + str(facts.get("traits", ""))


def _text_bonus(topic: str, profile: dict[str, Any]) -> float:
    tokens = [token for token in re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z0-9]{2,}", topic.lower()) if token]
    if not tokens:
        return 0.0
    profile_text = _profile_text(profile).lower()
    hits = sum(1 for token in tokens if token in profile_text)
    return min(0.08, hits * 0.02)


def score_profile(topic: str, features: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    affordances = profile.get("route_affordances", {})
    subject = _dimension_match(_values(features.get("subject")), _values(affordances.get("subject")))
    action = _dimension_match(_values(features.get("action")), _values(affordances.get("action")))
    abstraction = _dimension_match(_values(features.get("abstraction")), _values(affordances.get("abstraction")))
    scene = _dimension_match(_values(features.get("scene")), _values(affordances.get("scene")))
    mood = _dimension_match(_values(features.get("mood")), _values(affordances.get("mood")))
    topic_density = float(features.get("narrative_density", 0))
    style_density = float(affordances.get("narrative_density", 0))
    story = 1.0 - abs(topic_density - style_density) / 3.0
    score = (
        ((subject + action) / 2.0) * WEIGHTS["subject_action"]
        + abstraction * WEIGHTS["abstraction"]
        + ((scene + story) / 2.0) * WEIGHTS["scene_story"]
        + mood * WEIGHTS["mood"]
        + _text_bonus(topic, profile)
    )
    return {
        "base": max(0.0, min(1.0, score)),
        "dimensions": {
            "subject": subject,
            "action": action,
            "abstraction": abstraction,
            "scene": scene,
            "story": story,
            "mood": mood,
        },
    }


def _distance(left: dict[str, Any], right: dict[str, Any]) -> float:
    la = left.get("route_affordances", {})
    ra = right.get("route_affordances", {})
    dimension_distances = []
    for dimension in ("subject", "action", "scene", "abstraction", "mood"):
        dimension_distances.append(1.0 - _jaccard(_values(la.get(dimension)), _values(ra.get(dimension))))
    density_distance = abs(float(la.get("narrative_density", 0)) - float(ra.get("narrative_density", 0))) / 3.0
    group_distance = 1.0 if left.get("group") != right.get("group") else 0.0
    return max(0.0, min(1.0, sum(dimension_distances) / len(dimension_distances) * 0.72 + density_distance * 0.13 + group_distance * 0.15))


def _role_bonus(role: str, profile: dict[str, Any], base: float) -> float:
    affordances = profile.get("route_affordances", {})
    if role == "最稳妥":
        return base * 0.03
    if role == "最有表现力":
        return 0.08 * (float(affordances.get("visual_energy", 0)) / 3.0) + 0.04 * (float(affordances.get("color_intensity", 0)) / 3.0)
    if role == "最具故事感":
        return 0.12 * (float(affordances.get("narrative_density", 0)) / 3.0)
    if role == "最容易读懂主题":
        return 0.10 * (float(affordances.get("graphic_clarity", 0)) / 3.0)
    return 0.0


def _reason(role: str, score: dict[str, Any], profile: dict[str, Any]) -> str:
    dimensions = score["dimensions"]
    ranked = sorted(
        ((value, name) for name, value in dimensions.items() if name != "story"),
        reverse=True,
    )
    labels = [DIMENSION_LABELS.get(name, "故事适配") for value, name in ranked[:2] if value >= 0.45]
    if not labels:
        labels = ["主题方向"]
    group = str(profile.get("group", "")).split(" ", 1)[-1]
    if role == "最稳妥":
        ending = "与主题的核心信息最贴近"
    elif role == "最有表现力":
        ending = "保留主题关系，同时把视觉冲击拉高"
    elif role == "最具故事感":
        ending = "更适合把主题展开成一个可叙述的场景"
    elif role == "最容易读懂主题":
        ending = "画面结构更容易承担清晰的信息表达"
    else:
        ending = "与前四个候选拉开视觉方向，提供另一条可试路径"
    return f"{group}方向在{'、'.join(labels)}上有较强对应，{ending}。"


def _preview_markdown(style_id: str, preview_path: str | None) -> str | None:
    """Return a directly renderable local Markdown image, not just a link."""
    if not preview_path:
        return None
    normalized_path = str(preview_path).replace("\\", "/")
    return f"![#{style_id} 示意图]({normalized_path})"


def load_profiles(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload, {}
    styles = payload.get("styles")
    if not isinstance(styles, list):
        raise ValueError("profiles file must be a list or an object with a styles array")
    return styles, payload


def route_topic(
    topic: str,
    profiles: list[dict[str, Any]],
    features: dict[str, Any] | None = None,
    *,
    feature_source: str | None = None,
) -> dict[str, Any]:
    if len(profiles) < 5:
        raise ValueError("at least 5 style profiles are required")
    if features is None:
        features = infer_topic_features(topic)
        feature_source = "keyword_fallback"
    else:
        feature_source = feature_source or "structured_features"
    features = validate_topic_features(features)
    scored = []
    for profile in profiles:
        if profile.get("status") in {"disabled", "gallery_only"}:
            continue
        score = score_profile(topic, features, profile)
        scored.append({"profile": profile, "score": score})
    if len(scored) < 5:
        raise ValueError("fewer than 5 routeable style profiles remain after status filtering")
    scored.sort(key=lambda item: (-item["score"]["base"], str(item["profile"].get("style_id", ""))))
    top_base = scored[0]["score"]["base"]
    threshold = max(0.40, top_base * 0.58)
    diversity_floor = max(0.30, top_base * 0.45)
    selected: list[dict[str, Any]] = []
    relaxed_diversity = False
    for role in ROLES:
        candidates = [item for item in scored if item not in selected]
        if role == "差异化候选":
            eligible = [item for item in candidates if item["score"]["base"] >= threshold]
            if eligible:
                candidates = eligible
        if selected:
            selected_groups = {str(item["profile"].get("group", "")) for item in selected}
            unseen_group_candidates = [
                item for item in candidates
                if str(item["profile"].get("group", "")) not in selected_groups
                and item["score"]["base"] >= threshold
            ]
            if role == "差异化候选" and not unseen_group_candidates:
                unseen_group_candidates = [
                    item for item in scored
                    if item not in selected
                    and str(item["profile"].get("group", "")) not in selected_groups
                    and item["score"]["base"] >= diversity_floor
                ]
                if unseen_group_candidates:
                    relaxed_diversity = True
            if unseen_group_candidates:
                candidates = unseen_group_candidates
        best_item = None
        best_value = float("-inf")
        for item in candidates:
            base = item["score"]["base"]
            role_score = base + _role_bonus(role, item["profile"], base)
            if selected:
                min_distance = min(_distance(item["profile"], chosen["profile"]) for chosen in selected)
            else:
                min_distance = 0.0
            selected_groups = {str(chosen["profile"].get("group", "")) for chosen in selected}
            item_group = str(item["profile"].get("group", ""))
            group_bonus = 0.08 if item_group not in selected_groups else -0.12
            diversity_bonus = min_distance * (0.20 if role != "最稳妥" else 0.0)
            value = role_score + group_bonus + diversity_bonus
            if value > best_value:
                best_value = value
                best_item = item
        assert best_item is not None
        best_item["role"] = role
        best_item["final"] = best_value
        best_item["diversity"] = min(
            (_distance(best_item["profile"], chosen["profile"]) for chosen in selected),
            default=1.0,
        )
        selected.append(best_item)

    warnings = []
    if feature_source == "keyword_fallback":
        warnings.append("本次使用关键词降级解析；正式推荐应先由模型形成六维主题 JSON，再交给脚本评分。")
    if top_base < 0.50:
        warnings.append("没有达到高匹配阈值的风格，以上为当前库中的最近候选。")
    if relaxed_diversity:
        warnings.append("差异化候选为拉开视觉方向，使用了较低但仍相关的匹配门槛。")
    if any(item["profile"].get("status") == "heuristic_pending_review" for item in selected):
        warnings.append("候选包含自动生成且待复核的风格标签；示意图和标签复核后再作为稳定推荐。")
    candidates = []
    for index, item in enumerate(selected, start=1):
        profile = item["profile"]
        score = item["score"]
        candidates.append(
            {
                "recommendation": index,
                "role": item["role"],
                "style_id": str(profile.get("style_id", "")).zfill(3),
                "generation_name": profile.get("generation_name", ""),
                "reference": profile.get("reference", ""),
                "group": profile.get("group", ""),
                "preview_path": profile.get("preview_path"),
                "preview_markdown": _preview_markdown(
                    str(profile.get("style_id", "")).zfill(3),
                    profile.get("preview_path"),
                ),
                "reason": _reason(item["role"], score, profile),
                "status": profile.get("status", "unknown"),
                "scores": {
                    "base": round(score["base"], 4),
                    "final": round(item["final"], 4),
                    "diversity": round(item["diversity"], 4),
                    "threshold": round(threshold, 4),
                },
            }
        )
    return {
        "schema_version": "0.1",
        "topic": topic,
        "feature_source": feature_source,
        "topic_features": features,
        "candidates": candidates,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Route a topic to five diverse handraw-style candidates")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--profiles", type=Path, required=True)
    feature_group = parser.add_mutually_exclusive_group()
    feature_group.add_argument(
        "--features-file",
        type=Path,
        help="Model-produced six-dimensional topic JSON file",
    )
    feature_group.add_argument(
        "--features-json",
        help="Model-produced six-dimensional topic JSON object",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    profiles, library = load_profiles(args.profiles)
    if args.features_file:
        features = json.loads(args.features_file.read_text(encoding="utf-8"))
    elif args.features_json:
        features = json.loads(args.features_json)
    else:
        features = None
    result = route_topic(args.topic, profiles, features, feature_source="structured_features" if features is not None else None)
    result["library"] = {
        "profile_status": library.get("profile_status"),
        "source": library.get("source", {}),
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for candidate in result["candidates"]:
            print(f"推荐{candidate['recommendation']}：{candidate['role']} · #{candidate['style_id']} {candidate['generation_name']}")
            print(f"参考：{candidate['reference']}")
            print(f"示意图：{candidate['preview_markdown'] or '未同步'}")
            print(f"理由：{candidate['reason']}")
        for warning in result["warnings"]:
            print(f"提示：{warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
