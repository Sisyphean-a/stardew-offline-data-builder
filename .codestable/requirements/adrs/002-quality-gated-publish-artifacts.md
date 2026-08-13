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

图片质量不只检查 `imageRequired` 和文件存在。每个实体具有明确视觉状态；所有应有图片的实体必须达到 100% 物化，并通过来源唯一、视觉规则、裁切、解码、尺寸、透明度和内容哈希校验。manifest 或同等清单把图片内容与实体、来源和视觉规则绑定，独立 `package` 重新验证。真实包还必须生成确定性视觉联系表和异常清单；全部新增/变化/异常候选、每类至少 5 张固定代表图及其余每类 5%（3–20 张）样本形成具名人工结论，错实体、碰撞、异常复用或歧义需要第二人复核，存在未处理待复核项时阻断发布。

质量门禁同时扩展到 schema 5 玩家事实：绝对结构正确性为零容错；覆盖按分类与核心槽而非总体 enriched 百分比计算；候选包相对上一个获准真实包产生差异报告，未解释删除/状态退化阻断，超过已批准回归预算的变化需要具名审批。fixture 不能替代真实官方资产构建和真实 App 包验收。

## 备选方案

- 只写 warnings、仍生成包：消费者无法可靠判断包是否可用，错误成功会继续传播。
- 仅由 `package` 临时重算质量：SQLite、manifest、报告可能不一致，且绕过首次构建的诊断证据。
- 覆盖旧包并在失败时保留 canonical 路径：会让旧包看起来像本次成功结果。

## 后果

- 构建失败会留下诊断数据库、报告和阻断标记，而不是静默丢失证据。
- 发布门槛更严格，真实资产变化可能使构建退出；这是保护消费者而非回退到模拟成功。
- 数据库和 `.svdata` 生成使用临时文件替换，失败不会覆盖既有正式包；旧包在失败重建时隔离为 `.failed` 文件。
- 发布报告增加逐分类和逐实体视觉状态、内容绑定、复用与人工复核证据；规则变化和游戏版本变化会扩大视觉复核范围。

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
- `src/builder/pipeline/images.py`
- `src/builder/pipeline/package_integrity.py`
- `src/builder/commands/build_output.py`

## 相关历史

- `.codestable/history/2026-07.md`：2026-07-18 数据构建质量门禁。
- Git `e7f8b71`：修复数据构建质量缺陷并添加发布认证。
