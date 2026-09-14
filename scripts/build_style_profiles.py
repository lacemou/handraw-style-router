#!/usr/bin/env python3
"""Build routeable style profiles from handraw-style's upstream metadata.

The generated labels are deliberately marked as heuristic_pending_review. This
script provides a reproducible starting point; it is not an artistic ground
truth or a substitute for reviewing the reference images.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "0.1"

GROUP_DEFAULTS: dict[str, dict[str, Any]] = {
    "A": {
        "subject": ["people", "ideas"],
        "action": ["observation", "commentary"],
        "scene": ["public", "editorial"],
        "abstraction": ["editorial", "conceptual"],
        "mood": ["humorous", "intellectual"],
        "narrative_density": 1,
        "visual_energy": 2,
        "graphic_clarity": 3,
        "color_intensity": 1,
    },
    "B": {
        "subject": ["people", "animals", "daily-life"],
        "action": ["storytelling", "observation"],
        "scene": ["everyday", "nature", "home"],
        "abstraction": ["narrative", "lifestyle"],
        "mood": ["gentle", "warm"],
        "narrative_density": 3,
        "visual_energy": 2,
        "graphic_clarity": 2,
        "color_intensity": 2,
    },
    "C": {
        "subject": ["people", "objects", "ideas"],
        "action": ["presentation", "observation"],
        "scene": ["editorial", "public"],
        "abstraction": ["graphic", "conceptual"],
        "mood": ["modern", "intellectual"],
        "narrative_density": 1,
        "visual_energy": 3,
        "graphic_clarity": 3,
        "color_intensity": 2,
    },
    "D": {
        "subject": ["people", "daily-life"],
        "action": ["observation", "storytelling"],
        "scene": ["everyday", "urban", "nature"],
        "abstraction": ["lifestyle", "narrative"],
        "mood": ["gentle", "quiet"],
        "narrative_density": 2,
        "visual_energy": 1,
        "graphic_clarity": 2,
        "color_intensity": 1,
    },
    "E": {
        "subject": ["people", "daily-life", "ideas"],
        "action": ["observation", "storytelling"],
        "scene": ["everyday", "urban", "home"],
        "abstraction": ["narrative", "lifestyle"],
        "mood": ["warm", "poetic"],
        "narrative_density": 2,
        "visual_energy": 2,
        "graphic_clarity": 2,
        "color_intensity": 2,
    },
    "F": {
        "subject": ["people", "technology", "objects"],
        "action": ["work", "presentation", "commentary"],
        "scene": ["urban", "public", "media"],
        "abstraction": ["lifestyle", "editorial", "explanatory"],
        "mood": ["playful", "modern", "energetic"],
        "narrative_density": 1,
        "visual_energy": 3,
        "graphic_clarity": 3,
        "color_intensity": 3,
    },
    "G": {
        "subject": ["people", "daily-life", "ideas"],
        "action": ["observation", "storytelling", "presentation"],
        "scene": ["everyday", "urban", "nature"],
        "abstraction": ["narrative", "lifestyle", "graphic"],
        "mood": ["warm", "modern", "poetic"],
        "narrative_density": 2,
        "visual_energy": 2,
        "graphic_clarity": 2,
        "color_intensity": 2,
    },
}

TAG_RULES: dict[str, dict[str, list[str]]] = {
    "subject": {
        "people": ["人物", "人", "女性", "男性", "小人", "角色", "肖像", "孩子", "家庭", "情侣", "职场"],
        "animals": ["动物", "猫", "狗", "鸟", "兔", "鱼", "马", "狐狸", "熊"],
        "technology": ["科技", "电脑", "手机", "机器人", "AI", "数字", "屏幕", "代码", "互联网", "数据", "软件"],
        "city": ["城市", "都市", "街道", "建筑", "办公室", "地铁", "城市生活", "都市生活"],
        "nature": ["自然", "植物", "花", "树", "山", "海", "天空", "森林", "草地", "风景"],
        "objects": ["物件", "物体", "器物", "产品", "食物", "杯", "书", "家具", "工具"],
        "ideas": ["概念", "隐喻", "抽象", "思想", "观点", "哲学", "象征", "社论"],
    },
    "action": {
        "conversation": ["对话", "交谈", "讨论", "聊天", "沟通", "会议"],
        "work": ["工作", "办公", "使用", "操作", "制作", "学习", "写作", "编程"],
        "movement": ["行走", "奔跑", "旅行", "移动", "运动", "跳舞"],
        "observation": ["观察", "思考", "阅读", "等待", "注视"],
        "transformation": ["变化", "成长", "转变", "升级", "从零", "重建"],
        "comparison": ["比较", "对比", "选择", "区别", "差异"],
        "presentation": ["解释", "展示", "介绍", "教学", "讲解", "说明"],
        "storytelling": ["故事", "经历", "回忆", "叙事", "案例", "一天"],
        "commentary": ["吐槽", "评论", "批评", "讽刺", "观点"],
    },
    "scene": {
        "office": ["办公室", "办公桌", "会议室", "职场"],
        "home": ["家", "房间", "厨房", "卧室", "客厅"],
        "urban": ["城市", "都市", "街道", "地铁", "建筑", "商店"],
        "nature": ["自然", "山", "海", "森林", "公园", "户外"],
        "public": ["公共", "广场", "学校", "医院", "街头", "社交"],
        "digital": ["屏幕", "网页", "线上", "网络", "数字空间"],
        "everyday": ["日常", "生活", "一天", "普通人的生活"],
    },
    "abstraction": {
        "conceptual": ["概念", "隐喻", "抽象", "本质", "原理", "趋势", "观点", "哲学"],
        "narrative": ["故事", "经历", "案例", "叙事", "人物关系", "回忆"],
        "lifestyle": ["日常", "生活", "职场", "经验", "习惯"],
        "editorial": ["社论", "评论", "公共议题", "社会问题", "批评"],
        "explanatory": ["教程", "解释", "步骤", "流程", "方法", "知识", "科普"],
        "graphic": ["海报", "视觉", "设计", "平面", "信息图", "构成"],
    },
    "mood": {
        "humorous": ["幽默", "搞笑", "吐槽", "轻松", "荒诞", "尴尬"],
        "gentle": ["温柔", "治愈", "细腻", "柔和", "安静"],
        "warm": ["温暖", "亲切", "家庭", "陪伴", "人情"],
        "intellectual": ["理性", "思考", "智性", "严肃", "深度"],
        "energetic": ["活泼", "热烈", "兴奋", "大胆", "速度"],
        "anxious": ["焦虑", "困惑", "疲惫", "压力", "不安", "迷茫"],
        "serious": ["重要", "警惕", "风险", "严肃", "批判"],
        "curious": ["好奇", "探索", "发现", "新鲜", "尝试"],
    },
}

TEXT_ADJUSTMENTS = {
    "narrative_density": {
        "up": ["故事", "叙事", "人物关系", "场景", "动作", "经历", "案例", "一天"],
        "down": ["极简", "单一", "留白", "概念", "符号"],
    },
    "visual_energy": {
        "up": ["夸张", "鲜艳", "高饱和", "强烈", "大胆", "戏剧", "动态"],
        "down": ["低饱和", "柔和", "留白", "极简", "安静", "细腻"],
    },
    "graphic_clarity": {
        "up": ["清楚", "简洁", "几何", "色块", "平面", "轮廓", "明确"],
        "down": ["细密", "复杂", "纹理", "朦胧", "随意"],
    },
    "color_intensity": {
        "up": ["鲜艳", "高饱和", "彩色", "明亮", "丰富", "色块"],
        "down": ["低饱和", "单色", "黑白", "灰", "留白", "淡"],
    },
}


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _group_key(group: str) -> str:
    match = re.match(r"\s*([A-Z])", group or "")
    return match.group(1) if match else "G"


def _text_matches(text: str, words: list[str]) -> int:
    return sum(1 for word in words if word and word in text)


def _derive_tags(dimension: str, text: str, defaults: list[str]) -> list[str]:
    tags = list(defaults)
    for tag, words in TAG_RULES.get(dimension, {}).items():
        if _text_matches(text, words):
            tags.append(tag)
    return _unique(tags)


def _bounded(value: int) -> int:
    return max(0, min(3, value))


def _derive_metric(name: str, text: str, base: int) -> int:
    adjustment = 0
    rules = TEXT_ADJUSTMENTS[name]
    if _text_matches(text, rules["up"]):
        adjustment += 1
    if _text_matches(text, rules["down"]):
        adjustment -= 1
    return _bounded(base + adjustment)


def build_profiles(styles: list[dict[str, Any]], *, source: dict[str, Any] | None = None, preview_dir: str | None = None) -> dict[str, Any]:
    profiles: list[dict[str, Any]] = []
    source = source or {}
    for style in styles:
        number = str(style["number"]).zfill(3)
        group = str(style.get("group", ""))
        group_defaults = GROUP_DEFAULTS.get(_group_key(group), GROUP_DEFAULTS["G"])
        traits = str(style.get("traits", ""))
        text = " ".join(
            str(style.get(key, "")) for key in ("group", "reference", "generation_name", "traits")
        )
        affordances: dict[str, Any] = {
            dimension: _derive_tags(dimension, text, list(group_defaults[dimension]))
            for dimension in ("subject", "action", "scene", "abstraction", "mood")
        }
        narrative_density = int(group_defaults["narrative_density"])
        narrative_density += _text_matches(text, TEXT_ADJUSTMENTS["narrative_density"]["up"])
        narrative_density -= _text_matches(text, TEXT_ADJUSTMENTS["narrative_density"]["down"])
        affordances.update(
            {
                "narrative_density": _bounded(narrative_density),
                "visual_energy": _derive_metric("visual_energy", text, int(group_defaults["visual_energy"])),
                "graphic_clarity": _derive_metric("graphic_clarity", text, int(group_defaults["graphic_clarity"])),
                "color_intensity": _derive_metric("color_intensity", text, int(group_defaults["color_intensity"])),
            }
        )
        preview_path = None
        if preview_dir:
            preview_path = str(Path(preview_dir) / f"{number}.png")
        profiles.append(
            {
                "style_id": number,
                "generation_name": str(style.get("generation_name", "")),
                "reference": str(style.get("reference", "")),
                "group": group,
                "preview_path": preview_path,
                "visual_facts": {
                    "traits": traits,
                    "source_fields": ["group", "traits", "generation_name", "reference"],
                },
                "route_affordances": affordances,
                "evidence": {
                    "method": "derived_from_upstream_metadata",
                    "confidence": 0.45,
                    "source_revision": source.get("revision"),
                },
                "status": "heuristic_pending_review",
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "profile_status": "heuristic_pending_review",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "styles": profiles,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build routeable profiles from styles.json")
    parser.add_argument("--styles", required=True, type=Path, help="Path to upstream styles.json")
    parser.add_argument("--output", required=True, type=Path, help="Output style-profiles.json")
    parser.add_argument("--source", type=Path, help="Optional source.json used for revision metadata")
    parser.add_argument("--preview-dir", help="Directory containing local preview PNGs")
    args = parser.parse_args()

    styles = json.loads(args.styles.read_text(encoding="utf-8"))
    if not isinstance(styles, list) or not styles:
        raise SystemExit("styles.json must contain a non-empty JSON array")
    source = json.loads(args.source.read_text(encoding="utf-8")) if args.source else {}
    result = build_profiles(styles, source=source, preview_dir=args.preview_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"built {len(result['styles'])} profiles -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

