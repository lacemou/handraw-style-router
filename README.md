# handraw-style-router

把“我想做一个主题”先路由到 5 个有差异的 handraw 手绘风格候选。

这是一个初筛模块，不是完整生图工作流：用户只输入主题，路由器解析主题并给出固定顺序的五个候选；用户选定编号后，再把“原始主题 + 编号”交给上游 [handraw-style](https://github.com/yang0/handraw-style) 的提示词模块。

## 当前状态

首版核心原型：

- 支持上游当前 261 个条目的元数据同步，也能识别后续新增编号；
- 使用六维主题结构和确定性评分选择候选；
- 五个固定位置为“最稳妥、最有表现力、最具故事感、最容易读懂主题、差异化候选”；
- 初始风格画像由 `group` 和 `traits` 自动生成，状态是 `heuristic_pending_review`，还不能把它描述成 261 条都已人工校准；
- 上游示意图只在用户明确同步后保存到本地运行时目录，不随代码仓库分发；
- 生图效果的验证基准是 OpenAI Image 2。其他 Agent 目前只能说“理论上可适配”。

## 快速开始

需要 Python 3.10+。路由核心使用标准库；示意图资源修复需要 Pillow。

首次同步元数据和示意图：

```bash
python -m pip install -r requirements.txt
python scripts/update_style_library.py --with-images
```

资源更新后会自动修复已确认的上游异常示意图。如果本地已经同步过示意图，只想重新应用修复而不重新下载全部图片，可运行：

```bash
python scripts/update_style_library.py --repair-assets
```

只同步元数据：

```bash
python scripts/update_style_library.py
```

输入一个主题并取得 JSON 结果（不提供六维 JSON 时，只是关键词降级解析）：

```bash
python scripts/route_topic.py \
  --topic "办公室里，一个团队讨论如何使用人工智能" \
  --profiles .runtime/style-library/style-profiles.json \
  --json
```

路由器也接受模型解析后的主题结构：

```json
{
  "subject": ["people", "technology"],
  "action": ["conversation", "work"],
  "scene": ["office"],
  "abstraction": ["explanatory", "lifestyle"],
  "mood": ["curious", "serious"],
  "narrative_density": 2
}
```

```bash
python scripts/route_topic.py \
  --topic "办公室里，一个团队讨论如何使用人工智能" \
  --features-file topic-features.json \
  --profiles .runtime/style-library/style-profiles.json \
  --json
```

六维字段的解析契约和两个领域主题示例见 [references/topic-feature-schema.md](references/topic-feature-schema.md)。正式 Skill 流程应先由模型形成该 JSON，再交给脚本评分；脚本本身不调用另一个模型。

## 目录

```text
SKILL.md                         Agent 入口和行为边界
agents/openai.yaml               Codex UI 元数据
references/                      字段和更新策略
references/topic-feature-schema.md  模型主题解析契约和回归例子
scripts/update_style_library.py  明确触发的上游资源同步和已知资源修复
scripts/repair_style_assets.py   可追溯的示意图修复规则
scripts/build_style_profiles.py  从上游元数据构建初版画像
scripts/route_topic.py           六维评分和五候选选择
tests/                           不依赖上游图片的本地回归
.runtime/                        本地资源缓存，不提交 Git
```

## 上游与资源边界

本项目基于 [yang0/handraw-style](https://github.com/yang0/handraw-style) 的风格目录和示意图进行路由设计。上游资源的来源、commit 和抓取时间写入本地 `source.json`。本仓库目前不内置上游图片，也不把“注明来源”表述为“已获得再分发许可”。

代码许可证尚未在首版初始化时锁定；公开发布前需要补充明确的代码许可证，并再次核对上游资源的使用边界。

## 验证

```bash
python -m unittest discover -s tests -v
```

当前目标是先验证路由行为和边界，不把一次本地冒烟测试宣传成所有主题都稳定命中。
