# 反馈契约

模型把自然语言反馈解析为下面的可选字段，不要求用户填写。

```json
{
  "summary": "保留简洁线条，降低色彩刺激",
  "preserve": ["line"],
  "prefer": ["低饱和", "黑白"],
  "avoid": ["高饱和"],
  "metrics": {"color_intensity": 0}
}
```

- preserve：line、medium、palette、space、shape。对应线条、媒介、配色、空间、造型。
- prefer/avoid：与画像traits能对齐的具体视觉短语，不要机械复制长句。avoid为硬排除，只对新增候选生效，锚点仍展示。
- metrics：color_intensity、visual_energy、graphic_clarity、narrative_density，值0–3。把“颜色太艳”转成更低目标而非保留原锚点色彩。
- summary：完整描述当前有效视觉调整，必须忠实于用户。不能擅自扩写主体或剧情。
- 未传字段继承上轮；空数组或空对象明确清除该项。更新summary时概括累计仍有效的约束。

快速模式用文字规则的视觉特征做邻近召回，属于初筛，不能声称所有风格已经视觉校准。精细模式由当前Codex实际看图后精排，无独立模型API。

## 精细模式的细节入口

用户须提供至少一条具体反馈，表达重点或情绪可写入summary，能对齐视觉描述时再填写prefer/avoid/metrics。原主题、仅选编号、模式开关及“更准”“不满意”不构成细节。不要为了通过门槛虚构反馈。已有本任务有效反馈可继承，无须重复询问。

`shortlist --feedback-file feedback.json`合并新反馈后召回；没有细节返回needs_details，不写短名单或改变会话状态。代码只能检查结构与常见空泛输入，反馈是否真正具体仍由Agent依据用户原话判断。

引导时围绕当前主题给两三个具体方向示例，用户任选或另提方向即可。示例未经用户选择不能写入反馈JSON；用户不确定时仍可继续快速探索。快速候选展示后的精细模式入口遵循SKILL.md，不以本契约中的输入门槛代替入口提示。
