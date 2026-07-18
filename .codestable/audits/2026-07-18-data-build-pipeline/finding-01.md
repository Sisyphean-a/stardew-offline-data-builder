---
doc_type: audit-finding
audit: 2026-07-18-data-build-pipeline
finding_id: "bug-01"
nature: bug
severity: P1
confidence: high
suggested_action: cs-issue
status: open
---

# Finding 01：成就与鞋类旧格式被解析成数字 ID

## 速答

旧格式记录一律按 `/` 分割，但真实成就记录使用 `^` 分隔；未被专门识别的旧格式又以源 ID 作为名称回退。因此真实包内的 39 条成就和 18 条鞋类都成为数字名称。

## 关键证据

- `src/builder/parsers/official.py:102` — `build_legacy_entity` 固定使用 `value.split("/")`。
- `src/builder/parsers/official.py:229-240` — `legacy_display_name` 只处理 `quest`、`bundle`、`object`、`furniture`、`fish`；其他类型返回传入的回退值。
- `dist/stardew-zh-cn.svdata` 中 `achievement:0` 的 `legacyValue` 为 `Greenhorn (15k)^Earn 15,000g^true^-1^18`，而 `name_zh`、`name_en`、`internal_name` 均为 `0`，两个描述字段和 `image_path` 均为空。
- 同一包中 39 条 `achievement` 与 18 条 `footwear` 全部满足“纯数字名称、无描述、无图片”。

## 影响

成就和鞋类在消费者中没有可读标题，列表按字符串排序时还出现 `0、1、11、12…` 的顺序。`achievement` 分类已在真实 Android 导入后复现为不可理解的列表。

## 建议动作

`cs-issue`。本审计按委托要求不提供修复方案。
