---
doc_type: audit-finding
audit: 2026-07-18-data-build-pipeline
finding_id: "bug-02"
nature: bug
severity: P1
confidence: high
suggested_action: cs-issue
status: open
---

# Finding 02：翻译状态和报告把失效文本误报为完整

## 速答

翻译状态仅判断中文名称是否为非空字符串；数字 ID 也会被视为“完整翻译”。因此构建报告和 manifest 都把已经不可展示的数据报告为零缺失翻译。

## 关键证据

- `src/builder/pipeline/normalize.py:64-69` — `translation_status` 在 `if chinese_name:` 时直接返回 `complete`，没有校验名称是否是可展示文本。
- `src/builder/pipeline/reports.py:11-22` — 汇总仅计算状态为 `missing` 的实体。
- `src/builder/commands/package.py:48-56` — manifest 的 `missingTranslations` 直接使用该汇总值。
- 真实包中 57 条“纯数字名称、无描述、无图片”的记录均标记为 `translation_status = complete`；`manifest.json` 和 `reports/build-summary.json` 都声明 `missingTranslations: 0`。

## 影响

构建成功、翻译完整和数据可展示这三个结论被错误地等同。使用构建报告、manifest 或应用数据管理页判断数据质量时，会得到“翻译完整”的错误结论。

## 建议动作

`cs-issue`。本审计按委托要求不提供修复方案。
