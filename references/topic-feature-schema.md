# 主题六维解析契约

正式路由流程由模型先把自然语言主题解析为六维 JSON，再由 `scripts/route_topic.py` 做确定性评分。用户不需要填写这些字段。

## JSON 结构

```json
{
  "subject": ["technology", "objects"],
  "action": ["comparison"],
  "scene": ["digital", "everyday"],
  "abstraction": ["editorial", "lifestyle"],
  "mood": ["anxious", "curious"],
  "narrative_density": 1
}
```

`subject`、`action`、`scene`、`abstraction`、`mood` 必须是非空字符串数组；`narrative_density` 必须是 0–3 的整数。不要增加 `domain`、`keywords` 等额外字段。

模型应把具体词汇归一到当前风格画像使用的视觉语义标签，而不是把原句机械复制进去。常用标签包括：

- 主体：`people`、`technology`、`objects`、`ideas`、`city`、`nature`、`daily-life`
- 动作：`conversation`、`work`、`movement`、`observation`、`transformation`、`comparison`、`presentation`、`storytelling`
- 场景：`office`、`home`、`urban`、`digital`、`nature`、`everyday`、`public`
- 表达方式：`conceptual`、`narrative`、`lifestyle`、`editorial`、`explanatory`、`graphic`
- 气质：`humorous`、`gentle`、`warm`、`intellectual`、`energetic`、`anxious`、`serious`、`curious`

## 两个回归例子

### 消费科技与购买犹豫

主题：“iphone 18 duo 发布，售价太贵，买不买，很纠结。”

```json
{
  "subject": ["technology", "objects"],
  "action": ["comparison"],
  "scene": ["digital", "everyday"],
  "abstraction": ["editorial", "lifestyle"],
  "mood": ["anxious", "curious"],
  "narrative_density": 1
}
```

### 金融亏损与情绪

主题：“今天股票又亏钱了。”

```json
{
  "subject": ["objects", "ideas"],
  "action": ["observation"],
  "scene": ["digital", "everyday"],
  "abstraction": ["editorial"],
  "mood": ["anxious", "serious"],
  "narrative_density": 0
}
```

## 降级边界

如果没有模型生成的结构化 JSON，脚本仍可用硬编码关键词运行，但结果必须标记 `feature_source: keyword_fallback` 并给出警告，不能把它当成完整语义解析结果。
