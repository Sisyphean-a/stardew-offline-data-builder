---
id: 002
title: 质量门禁与可发布产物一致性
status: accepted
scope: shared:artifact-contract
---

# 002 质量门禁与可发布产物一致性

## 背景

真实官方资产审计曾发现：旧格式实体可能只有数字显示名，多个视觉类型可能缺图，解析或资源错误可能仍生成成功包；仅在报告中记录错误无法保护离线应用消费者。

## 决定

把质量状态纳入 SQLite 的 `artifact_metadata`，并让报告、manifest 和 `.svdata` 共享同一份构建元数据。翻译缺失或无效、数据/图片错误、缺少实体类型中文标签和必需图片缺失都阻止可发布包。fixture 明确 `publishable: false`。失败构建或 fixture 输出写入 `.release-blocked.json`，独立 `package` 必须拒绝；正式 ZIP 先临时写入、完整性校验后原子替换。

## 备选方案

- 只写 warnings、仍生成包：消费者无法可靠判断包是否可用，错误成功会继续传播。
- 仅由 `package` 临时重算质量：SQLite、manifest、报告可能不一致，且绕过首次构建的诊断证据。
- 覆盖旧包并在失败时保留 canonical 路径：会让旧包看起来像本次成功结果。

## 后果

- 构建失败会留下诊断数据库、报告和阻断标记，而不是静默丢失证据。
- 发布门槛更严格，真实资产变化可能使构建退出；这是保护消费者而非回退到模拟成功。
- 数据库和 `.svdata` 生成使用临时文件替换，失败不会覆盖既有正式包；旧包在失败重建时隔离为 `.failed` 文件。

## 代码锚点

- `src/builder/pipeline/artifact_metadata.py`
- `src/builder/pipeline/quality.py`
- `src/builder/pipeline/release_state.py`
- `src/builder/pipeline/package_integrity.py`
- `src/builder/commands/build_output.py`
- `src/builder/commands/package.py`
- `src/builder/database/writer.py`
- `tests/test_quality_gate.py`
- `tests/test_package.py`

## 相关历史

- `.codestable/history/2026-07.md`：2026-07-18 数据构建质量门禁。
- Git `e7f8b71`：修复数据构建质量缺陷并添加发布认证。
