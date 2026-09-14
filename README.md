# handraw-style-router

把一句主题，先路由成 5 个有差异的 handraw 手绘风格候选。

面对 `handraw-style` 的 261 个以上风格条目，用户通常不是缺少生图工具，而是不知道应该先选哪一种画风。本项目是一个轻量的初筛路由模块：用户只提供主题，Skill 解析主题的视觉语义，再返回 5 个拉开差异的候选风格、编号、上游参考信息、示意图和一句推荐理由。

它不替用户完成完整的生图流程，也不要求用户先填写画幅、配色、人物设定或文案。

## 它做什么

路由过程分成三步：

1. 把自然语言主题解析成六个内部维度：主体、动作、场景、表达方式、情绪和叙事密度；
2. 对风格画像进行确定性匹配和打分，先选最稳妥的候选，再用角色目标和多样性惩罚拉开其余候选；
3. 固定输出以下五个位置：

   - 推荐 1：最稳妥
   - 推荐 2：最有表现力
   - 推荐 3：最具故事感
   - 推荐 4：最容易读懂主题
   - 推荐 5：差异化候选

用户选择编号后，再把“原始主题 + 编号”交给上游 `handraw-style` 提示词模块或生图工具继续处理。

## 它不做什么

- 不替用户决定完整的图片规范；
- 不生成完整生图提示词；
- 不自动学习或累积账号视觉偏好；
- 不把自动生成的风格标签包装成人工艺术史判断；
- 不保证生图模型一定复现某位参考作者的画面；
- 不负责公众号、小红书或其他平台的发布。

本项目的生图验证范围为 OpenAI ImageGen 的 `gpt-image-2` / GPT-Image-2.5 系列（当前官方包含 Sunburst、Flare）；具体内置版本由当前运行环境决定，本项目不固定模型 ID。WorkBuddy、豆包工作等其他 Agent 的模型和生图效果目前只能说“理论上可适配”，不作相同效果保证。使用可显式指定模型的 API 或 CLI 时，应记录实际 model ID。

## 在 Codex 中使用

如果仓库已经发布到 GitHub，可以用下面的命令安装。将 `<owner>/<repo>` 替换为实际仓库坐标：

~~~bash
npx -y skills add <owner>/<repo> -g --all
~~~

安装后，直接输入类似下面的请求即可：

~~~text
使用 $handraw-style-router，根据我的主题推荐五个 handraw 风格候选，并附上示意图与一句选择理由。

主题：今天股票又亏钱了。
~~~

安装命令只负责安装 Skill 文件，不会执行仓库中的 Python 下载脚本。第一次真正调用 Skill 时，它会先运行初始化门禁：如果本地没有完整风格库，就自动下载固定版本的上游元数据和示意图；同步失败则停止路由并报告原因，不会假装已经查看过示意图。

## 本地运行

需要 Python 3.10 或更高版本。路由核心使用 Python 标准库；下载和修复示意图需要 Pillow。

安装依赖：

~~~bash
python -m pip install -r requirements.txt
~~~

首次使用时，先运行初始化门禁。已有完整资源时它只做检查；资源缺失时会自动完成首次同步：

~~~bash
python scripts/ensure_runtime.py
~~~

如果 Skill 安装目录不是当前工作目录，请使用该 Skill 目录下的 `scripts/ensure_runtime.py` 绝对路径。初始化需要网络和 Pillow，失败时可先运行：

~~~bash
python -m pip install -r requirements.txt
~~~

只同步元数据：

~~~bash
python scripts/update_style_library.py
~~~

本地已经有示意图，只想重新应用已确认的资源修复：

~~~bash
python scripts/update_style_library.py --repair-assets
~~~

使用关键词降级解析运行路由：

~~~bash
python scripts/route_topic.py --topic "办公室里，一个团队讨论如何使用人工智能" --profiles ".runtime/style-library/style-profiles.json" --json
~~~

正式流程应先由模型形成六维主题 JSON，再交给脚本进行确定性评分。示例：

~~~json
{
  "subject": ["technology", "objects"],
  "action": ["comparison"],
  "scene": ["digital", "everyday"],
  "abstraction": ["editorial", "lifestyle"],
  "mood": ["anxious", "curious"],
  "narrative_density": 1
}
~~~

~~~bash
python scripts/route_topic.py --topic "iphone 18 duo 发布，售价太贵，买不买，很纠结" --features-file topic-features.json --profiles ".runtime/style-library/style-profiles.json" --json
~~~

没有结构化 JSON 时，脚本可以使用关键词降级解析，但结果会标记 `feature_source: keyword_fallback` 并给出警告。降级结果不应被描述为已经完成完整的语义解析。

## 风格库与更新

本项目基于 [yang0/handraw-style](https://github.com/yang0/handraw-style) 的风格目录和示意图进行路由设计。首次使用时，初始化门禁会按需下载到本地 `.runtime/style-library/`；后续更新只有在用户明确触发时才执行。运行时资源不随代码仓库分发。

更新流程不会在后台运行：

1. 解析上游当前提交并保存版本信息；
2. 拉取新增或变化的元数据和示意图；
3. 对新条目标记为 `gallery_only` 或 `heuristic_pending_review`；
4. 复核视觉事实、路由标签和主题回归样本；
5. 复核通过后，才允许进入正常 Top 5 推荐。

因此，未来新增的 262、263 等条目可以被资源层识别，但不会因为下载成功就自动改变推荐结果。

风格画像目前主要由上游的 `group`、`traits`、`generation_name` 和 `reference` 推导，状态为 `heuristic_pending_review`。这意味着它适合开发和测试，但不应宣称 261 个条目都已经人工校准。

## 隐私与安全

- 路由器本身不需要 OpenAI API Key，也不在仓库中保存 API Key、Cookie、密码或登录凭证；
- 路由脚本不向外部服务发送用户主题，也不做遥测；
- 只有显式运行资源更新脚本时，才会从 GitHub 获取上游公开文件；该过程不要求配置个人凭证；
- 本地风格图片、抓取记录、生成图片、缓存和 Python 缓存都位于被 Git 忽略的运行时目录；
- 提交前不要把 `.runtime/`、`.cache/`、`.venv/`、`__pycache__/` 或本机绝对路径加入公开仓库；
- 上游示意图只按需下载到用户本地，不在本仓库中打包或再分发。

“注明上游来源”不等于“已经获得上游图片的再分发许可”。公开分享前，请分别核对本项目代码许可证和上游资源的许可证、作者归属及图片使用边界。

## 目录结构

~~~text
SKILL.md                              Agent 入口、行为边界和固定输出
agents/openai.yaml                    Codex UI 元数据
references/profile-schema.md          风格画像字段和状态
references/topic-feature-schema.md    六维主题解析契约和回归例子
references/update-policy.md           风格库更新与许可边界
scripts/update_style_library.py       上游资源同步
scripts/ensure_runtime.py             首次运行的资源初始化门禁
scripts/repair_style_assets.py        已确认的本地示意图修复规则
scripts/build_style_profiles.py       从上游元数据构建初版画像
scripts/route_topic.py                六维评分和五候选选择
tests/                                不依赖上游图片的本地回归测试
.runtime/                             本地资源缓存，不提交 Git
~~~

## 验证

运行本地回归测试：

~~~bash
python -m unittest discover -s tests -v
~~~

当前已覆盖：固定五个推荐位置、候选唯一性、结构化主题解析、降级警告、示意图 Markdown 渲染、046 资源修复、新条目 `gallery_only` 状态和字段校验。

## 许可证与上游归属

本仓库当前尚未选定代码许可证。在公开发布前，应由维护者选择并添加明确的 `LICENSE` 文件。

上游项目：[yang0/handraw-style](https://github.com/yang0/handraw-style)。本项目是基于其公开风格目录建立的路由工具，不代表上游作者参与本项目，也不代表本项目获得了上游示意图的再分发授权。
