---
doc_type: audit-finding
audit: 2026-07-18-data-build-pipeline
finding_id: "maintainability-05"
nature: maintainability
severity: P1
confidence: high
suggested_action: cs-issue
status: open
---

# Finding 05：测试夹具未覆盖真实旧格式和最终展示质量

## 速答

当前测试验证了人工构造的 `entries` 格式和四个基础实体，却没有覆盖真实 `Data/Achievements*.json` 的 `^` 分隔记录、成就/鞋类的用户可读字段、图片覆盖率或“成功报告与数据质量一致性”。因此全部 58 个测试通过时，真实产物仍可包含已知的不可展示数据。

## 关键证据

- `tests/test_phase7_generic_types.py:33-42` — 成就测试使用 `{entries: [{id, internalName, name, description}]}`，不使用真实旧格式。
- `tests/test_real_official_data.py:20-58` — 黑盒构建断言只覆盖 `object`、`crop`、`fish`、`villager` 四个基础实体及一张普通物品图片。
- `tests/test_legacy_localization.py:28-63` — 旧格式测试覆盖料理、制作配方、任务、收集包，不覆盖成就或鞋类。
- 执行结果：`python -m pytest` 为 58 passed，当前 `dist/stardew-zh-cn.svdata` 仍含 Finding 01 至 04 所述缺陷。

## 影响

测试绿灯无法作为真实游戏资产构建质量的发布依据。旧格式或扩展类别发生回归时，问题只会在用户导入后暴露。

## 建议动作

`cs-issue`。本审计按委托要求不提供修复方案。
