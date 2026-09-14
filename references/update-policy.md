# 风格库更新策略

## 首次同步

由用户明确触发：

```bash
python scripts/update_style_library.py --with-images
```

脚本会把上游 `styles.json`、单图示意图和抓取信息写入 `.runtime/style-library/`。这里的运行时目录不提交 Git，也不进入公开 Skill 包。

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

