# 风格画像字段

风格画像是路由器的中间数据，不是对作者或作品的艺术史判断。每个条目必须能追溯到上游的 `group`、`traits`、`generation_name` 和 `reference`。

## 顶层结构

```json
{
  "schema_version": "0.1",
  "profile_status": "heuristic_pending_review",
  "source": {
    "repository": "yang0/handraw-style",
    "revision": "<commit>"
  },
  "styles": []
}
```

## 单个风格

```json
{
  "style_id": "022",
  "generation_name": "Flat Everyday Women Lifestyle",
  "reference": "Sally Nixon",
  "group": "A 国际社论漫画 / 幽默手绘",
  "preview_path": ".runtime/style-library/previews/022.png",
  "visual_facts": {
    "traits": "上游 styles.json 中的原始 traits",
    "source_fields": ["group", "traits", "generation_name", "reference"]
  },
  "route_affordances": {
    "subject": ["people", "daily-life"],
    "action": ["observation"],
    "scene": ["everyday", "public"],
    "abstraction": ["lifestyle", "editorial"],
    "mood": ["gentle", "humorous"],
    "narrative_density": 2,
    "visual_energy": 1,
    "graphic_clarity": 2,
    "color_intensity": 1
  },
  "evidence": {
    "method": "derived_from_upstream_metadata",
    "confidence": 0.45
  },
  "status": "heuristic_pending_review"
}
```

## 状态

- `heuristic_pending_review`：由 `group` 和 `traits` 规则生成，可以用于开发测试，但正式推荐必须带“标签待复核”提示。
- `reviewed`：人工或模型复核过视觉事实和路由适配，允许进入正常推荐。
- `gallery_only`：可以展示在本地画廊，但暂不参与 Top 5。
- `disabled`：来源缺失、图片损坏或标签冲突，不参与路由。

自动标签只能描述“看起来适合什么任务”，不能把某个作者的名字直接当成风格语义，也不能据此宣称生图模型一定会复现原作。

