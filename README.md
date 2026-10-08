# Handraw Style Router V2

版本 **2.0.0**。用于 Codex：输入主题，从 handraw-style 风格库推荐五个不同方向；选中后用自然语言继续探索，或开启精细模式实际看参考图比较，最后交付可复制提示词与对应参考图。明确要求生图时，衔接 Codex 当前可用的生图工具。

## 安装

下载 [v2.0.0 发布包](https://github.com/lacemou/handraw-style-router/releases/tag/v2.0.0)，解压到 Codex 的 skills 目录下，目录名使用 `handraw-style-router`。也可克隆仓库，再把本目录的绝对路径交给 Codex。旧版用户更新前请备份旧安装；V1 可通过仓库 Git 历史取回。

需要 Python 3.10 或更新版本及 Pillow 10 或更新版本。首次运行从上游同步参考资源，耗时取决于网络；上游图片不随发布包分发。

## V2 更新

- 五种推荐侧重点继续保留，支持1–10个候选及可选智能数量。
- 选中1–2个方向后继续探索，保留锚点并继承本任务有效反馈。
- 每轮快速候选提示精细模式入口；用户补充具体方向后，Codex实际查看短名单参考图并精排。
- 交付提示词逐字保留原始主题，单列用户对话补充原话，再附画风与参考约束。
- 记录本地选择、材料交付与可确认生成；统一入口分别更新风格库与Router代码。

## 直接试用

把本目录的 `SKILL.md` 路径给 Codex：

> 请读取这个目录里的 SKILL.md，使用第二版 Router：主题是“为什么AI不会累？”。先给五个画风参考，不生图。

随后可说：

- “第二个和第四个不错，沿这两条路线找相近的。”
- “保留第二个的线条，颜色不要那么艳。”
- “开启智能数量。” / “关闭智能数量，回到五个。”
- “开启精细模式。我想突出脑内想得太多，希望更抽象、黑白、少细节。”
- “选这个，给我提示词和参考图。”
- “这两个分别生成图片。”（明确要求后才调用Codex的生图能力）
- “更新这个Skill，告诉我库和代码分别更新了什么。”

参考图展示的是上游画风示例，不是用户主题的预生成图。精细模式需要当前Codex实际看图；脚本本身不调用额外模型或生图API。其他Agent原则上可适配，未经验证。

## 工作方式

默认五候选保留不同推荐侧重点：最稳妥、最有表现力、最具故事感、最容易读懂主题、差异化候选。它们是选择提示，不是全库最优的保证。每轮快速候选后明确提示可选1–2个继续，或开启精细模式；数量可指定1–10；智能数量只在用户开启后使用。选中一或两个方向，分别探索邻近画风。锚点保留对照，新增候选标明路线，已看过而未选中的候选不反复推出。单路线最多5个，两条路线默认合计6个，最多10个。

快速模式：Codex解析主题/反馈，脚本按文字画像、视觉特征词与多样性进行初筛。精细模式：先取得用户具体反馈，再按反馈召回短名单并实际看图精排。仅说“开启精细模式”时，Skill先引导补充表达重点、情绪或视觉偏好；任选一个方面即可，已有有效细节不重复询问。短名单最多10个，默认展示5个，仍不是全库逐图比较。文字标签是启发式，不代表已完成全库视觉校准；尚无充分对照证据证明推荐质量普遍优于旧版。

历史只记选择、材料交付、当前Codex内可确认生成。外部生成未知；统计不参与推荐。任务进度只在当前会话继续，新任务从零开始。运行时会话文件不构成跨会话恢复功能。

## 命令与依赖

Python >=3.10，Pillow>=10.0。先安装 `requirements.txt`，使用绝对脚本路径；以下示例从本包根目录运行。

```sh
python3 -m pip install -r requirements.txt
python3 scripts/router.py init
python3 scripts/router.py check
python3 scripts/router.py start --conversation demo-current-chat --topic '为什么AI不会累？' --features-file topic.json
python3 scripts/router.py select --conversation demo-current-chat --styles FA-001 --event-id user-choice-1
python3 scripts/router.py explore --conversation demo-current-chat --feedback-file feedback.json
python3 scripts/router.py deliver --conversation demo-current-chat --event-id user-delivery-1 --model unknown
python3 scripts/router.py stats
python3 scripts/router.py update --check-only
python3 scripts/router.py update
```

上面的 `FA-001` 必须是当前结果中实际展示的风格，不能照抄示例选未展示的编号。CLI没有模型解析输入时明确标记关键词降级；正式使用由Codex形成JSON。feedback.json见 `references/feedback-contract.md`。`--smart`开启智能数量、`--fixed`关闭；`--count`给明确数量。

由当前Codex选择Python 3.10或更新的可用运行环境，不能直接使用不符合要求的系统Python。

## 更新与许可

用户主动更新才访问GitHub。更新把风格索引、编号别名、模型策略和完整参考图固定到同一上游提交。下载、图片读取、编号对应与评分冒烟检查通过后原子启用；失败保留原库。新增风格立即可推荐。新结构无法解析时明确失败，不忽略错误假装成功。未变化的Git图片blob复用本地文件。

当前任务固定开始时的库快照，更新不会暗中更换已经选择的风格。更新后新任务使用新库；旧快照保留供当前任务和回退。

统一更新入口分别报告资源库与代码。代码更新依赖本项目公开的版本化 `release.json` 和GitHub Release归档；通过本仓库默认分支的清单与对应Release归档获取更新；没有清单时明确报告代码更新尚不可用。

`python3 scripts/build_release.py` 生成源代码归档及发布清单，**不发布**。归档不含 `.runtime`、用户记录、测试运行结果或上游图片。代码升级校验归档与每个文件的SHA256、路径和Python语法，保留源码备份，写入异常回退。

本项目代码采用MIT。上游：yang0 / https://github.com/yang0/handraw-style 。上游目前采用MIT with Attribution Requirement：保留版权和许可，并展示作者和原仓库。同步快照与交付目录保留原许可文件。不能把软件许可扩大为所有第三方参考作品的权利授权。

## 验证

```sh
python3 -m unittest discover -s tests -v
```

功能回归覆盖更新事务、损坏/重复资源、增量复用、新条目即时推荐、数量上限、锚点与反馈、记录去重、交付配对、未知模型参考图兜底、精细模式输入与代码归档校验。

当前29项功能回归通过。其他Agent环境、全库逐图校准及公开更新链路的跨版本实际升级尚未完成验证；生成结果由用户判断。

生图输入保真：原始主题逐字保留在提示词最前，用户对话方向按原话单列，再附已选画风与参考约束。`deliver --requirements-file requirements.json`接收用户原话字符串数组，写入交付记录；解析摘要不代替原话。最终工具调用使用保存的完整提示词，不再另写压缩主题或擅自锁定构图。

## 隐私与网络范围

本Skill不要求API Key，不读取环境变量中的凭证，不上传主题、反馈或行为记录。主题、用户补充、候选状态与交付材料保存于本Skill的 `.runtime`，其中可能包含个人输入，请勿提交到公开仓库。首次资源同步与用户主动更新会访问GitHub；任务主题不会拼进网络请求。用户明确要求生图时，提示词与必要参考图会提交给当前环境的生图工具。源码仓库与发布包不含本地运行记录、开发记录、生成图片或上游参考图片。
