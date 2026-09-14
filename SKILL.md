---
name: handraw-style-router
description: 根据用户只提供的主题，从已同步的 handraw-style 风格库中筛选五个彼此拉开差异的候选风格，并返回编号、名称、上游示意图和推荐理由；只做初筛路由，不代替用户完成提示词或生图。
metadata:
  short-description: 主题到手绘风格的五选一初筛路由
---

# Handraw Style Router

把一个主题送入 `handraw-style` 的 261+ 个风格条目中，给用户五个有明确分工、彼此不重复的候选。这个 Skill 只负责“先选哪种画风”，不负责把主题扩写成完整提示词，也不负责调用生图模型。

## 使用边界

- 用户只需要提供主题；不要把画幅、配色、文案、人物设定等要求变成必填项。
- 如果用户已经有参考图，优先让用户直接把参考图交给生图模型；不要强行经过本路由器。
- 不学习账号历史偏好，也不加入账号视觉风格分数。每次只根据当前主题计算。
- 生图验证范围为 OpenAI ImageGen 的 `gpt-image-2` / GPT-Image-2.5 系列（当前官方包含 Sunburst、Flare）；具体内置版本由当前运行环境决定，本 Skill 不固定模型 ID。如使用可显式指定模型的 API 或 CLI，必须在运行记录中写明实际 model ID。WorkBuddy、豆包工作等其他 Agent 的适配只能表述为“理论上可适配”，不承诺相同生图效果。
- 选中编号后，才把“原始主题 + 编号”交给上游 `handraw-style` 的提示词模块；本 Skill 不复制那套提示词生成逻辑。

## 执行流程

### 1. 强制初始化本地风格库

运行时库默认位于项目的 `.runtime/style-library/`。在解析主题和调用路由脚本之前，必须先运行幂等的初始化门禁：

```bash
python scripts/ensure_runtime.py
```

如果 Skill 安装目录不是当前工作目录，先把 `scripts/ensure_runtime.py` 替换为该 Skill 目录下的绝对路径。这个脚本会检查 `style-profiles.json`、`source.json`、至少 5 个可路由风格和对应的有效 PNG 示意图：

- 已有完整运行时库：只检查，不重复下载；
- 目录不存在或不完整：自动按固定上游提交下载 261+ 张示意图，并构建风格画像；
- 依赖、网络或下载失败：停止本次路由，报告失败原因和修复命令，不返回没有示意图的假成功结果。

只有 `ensure_runtime.py` 成功后，才能进入下一步。首次同步是首次运行的必需项；后续更新仍然不在后台执行，只有用户明确说“更新风格库”时才运行更新命令。新条目先进入本地画廊，完成标签复核和路由回归后，才能进入正式推荐。

后续脚本应从包含本 `SKILL.md` 的 Skill 根目录执行，或全部使用该目录下的绝对路径；不要把调用方项目中的 `.runtime/` 误当成 Skill 的运行时目录。

后续明确更新时运行：

```bash
python scripts/update_style_library.py --latest --with-images
```

### 2. 解析主题

在调用路由脚本前，模型必须先把主题解析成内部结构，不要求用户填写或确认。字段固定为：

```json
{
  "subject": ["主题主体"],
  "action": ["主体正在做什么"],
  "scene": ["发生在哪里"],
  "abstraction": ["日常、叙事、概念、解释等"],
  "mood": ["情绪或气质"],
  "narrative_density": 0
}
```

`narrative_density` 为 0–3：0 表示单一对象或概念，3 表示人物关系、事件推进或强故事场景。模型输出必须遵守 [主题六维解析契约](references/topic-feature-schema.md)；不要把用户原句直接复制成标签，也不要新增未约定字段。

### 3. 运行确定性路由

模型只负责形成上面的主题结构，不直接凭感觉挑五个编号。将结构交给脚本：

```bash
python scripts/route_topic.py \
  --topic "用户原始主题" \
  --features-file topic-features.json \
  --profiles .runtime/style-library/style-profiles.json \
  --json
```

如已有模型解析结果，将其保存为临时 JSON 后传入 `--features-file`，或直接使用 `--features-json`。脚本会校验六个字段，再按以下顺序工作：

1. 对全部已进入推荐状态的风格计算基础匹配分：主体/动作 40%，视觉抽象 25%，场景/故事 20%，情绪 15%。
2. 先选“最稳妥”，再按角色目标和多样性惩罚选择其他候选，避免五张图只是同一类风格的近似重复。
3. “差异化候选”优先同时满足主题匹配达到最低阈值、并且与已选候选在视觉标签或风格组上有明显距离；如果没有未使用风格组达到主阈值，可以在较低但仍相关的次级阈值内保留一个差异化候选，并明确给出警告。

如果没有结构化主题 JSON，脚本可以运行关键词降级解析，但结果会标记 `feature_source: keyword_fallback` 并明确警告；不能把降级结果描述成已经完成模型语义解析。

## 对用户的固定输出

按脚本返回的顺序输出，不改成“角色”标签：

1. `推荐1：最稳妥`
2. `推荐2：最有表现力`
3. `推荐3：最具故事感`
4. `推荐4：最容易读懂主题`
5. `推荐5：差异化候选`

每条只展示：风格编号、风格名、上游参考作者/风格名、仓库中的示意图和一句基于匹配维度的理由。示意图必须使用可直接渲染的 Markdown 图片语法（图片替代文字加本地绝对 PNG 路径），而不是只输出普通链接或文件路径；程序内部仍可保留原始 `preview_path`。不要把内部 0–1 分数包装成精确结论；如标签仍是自动初版，明确标注“标签待复核”。

推荐结束后只问用户想选哪一个编号。用户选择后，说明可以继续把“原始主题 + 编号”交给 `handraw-style`；不要在本步骤自动生成完整提示词或图片。

## 资源与上游边界

本项目不把上游示意图直接打包进公开仓库。首次运行由 `ensure_runtime.py` 按固定提交版本拉取到本地运行时目录，后续更新必须由用户明确触发；运行时目录被 Git 忽略。上游来源、提交版本和抓取时间必须保留在 `source.json` 中；没有声明上游许可证时，不要把“已注明来源”说成“已获得再分发许可”。

详细字段结构见 [references/profile-schema.md](references/profile-schema.md)，主题解析契约见 [references/topic-feature-schema.md](references/topic-feature-schema.md)，更新策略见 [references/update-policy.md](references/update-policy.md)。
