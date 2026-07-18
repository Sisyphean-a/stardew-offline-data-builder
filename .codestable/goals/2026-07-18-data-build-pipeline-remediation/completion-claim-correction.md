---
doc_type: release-correction
goal: data-build-pipeline-remediation
status: verified
audit: 2026-07-18-data-build-pipeline
updated_at: 2026-07-18
---

# 历史完成表述勘误

2026-07-16 及更早的 `complete`、`pass` 记录只保留为当时的实现过程证据，不能再作为可发布数据包的认证。后续真实资产审计确认：成就和鞋类被解析为数字展示名，四类视觉实体共 884 条缺图未被报告，错误构建仍能声明成功，独立打包还会丢失扩展类型和质量状态。

本勘误不改写 Git 历史，也不否定此前已完成的局部实现；它明确撤销这些记录关于“当前数据包可发布”的推论。受影响记录已增加指向本文件的说明。

## 修复后的可发布证据

- 使用本机真实官方解包资产重建到 `build/goal-real-output-final3`，未覆盖既有 `dist/`。
- 产物包含 3,688 条标准化实体，`reports/build-summary.json` 为 `success: true`、`quality: passed`、不可用翻译和数据错误均为 0。
- 所有要求图片的 984 条实体均已物化；审计涉及的成就 39、大型可制作物 182、家具 645、鞋类 18 条均有图片路径。
- SQLite 持久化 schema v4 的 `artifact_metadata`；manifest 为 25 个实际类型提供非空中文展示名，且质量、生成时间、游戏版本和源哈希与数据库元数据一致。
- 独立 `package --locale zh-CN` 已复验，先验证全部数据库图片引用，并以临时包校验后原子替换，不重算或丢失上述元数据。

实现和验证细节见本 Goal 的迭代记录及关联 issue 的分析、修复记录；原始问题见 [审计报告](../../audits/2026-07-18-data-build-pipeline/index.md)。
