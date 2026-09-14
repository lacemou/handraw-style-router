# 风格库更新策略

## 首次运行初始化

安装 Skill 后，第一次调用路由前必须运行初始化门禁：

```bash
python scripts/ensure_runtime.py
```

`ensure_runtime.py` 会检查画像、来源记录和示意图是否完整；如果缺失，就调用固定上游提交的同步流程。它会把上游 `styles.json`、单图示意图和抓取信息写入 `.runtime/style-library/`。这里的运行时目录不提交 Git，也不进入公开 Skill 包。下载单图后，脚本还会应用 `scripts/repair_style_assets.py` 中已确认的本地修复规则，并把修复来源、切片位置和 SHA-256 写入 `source.json`；这不修改上游仓库。

初始化失败时必须停止路由，并报告依赖或网络问题；不能把没有示意图的结果当成正常推荐。

如果本地已经同步过示意图，只需重新应用已知修复，不必重新下载全部图片：

```bash
python scripts/update_style_library.py --repair-assets
```

## 后续更新

不做后台检查。只有用户明确说“更新风格库”时才运行更新脚本。推荐流程是：

1. 用 `--latest` 解析上游 `master` 当前提交，并保存解析后的 commit；
2. 拉取新增或变化的元数据和示意图；
3. 新条目标记为 `gallery_only` 或 `heuristic_pending_review`；
4. 复核视觉事实、路由标签和 20–30 个主题回归样本；
5. 通过后才把条目改成 `reviewed` 并纳入 Top 5。

因此，262、263 等新条目可以被资源层识别，但不会因为下载成功就自动改变推荐结果。

## 许可边界

本路由器的代码和上游资源是两件事。README 必须保留 [handraw-style](https://github.com/yang0/handraw-style) 来源、具体提交版本和作者归属；来源说明不等于上游图片的再分发许可。在上游许可证未核实前，只在用户本地按需拉取图片，不将图片复制进公开仓库或发布包。
