---
doc_type: goal-iteration
goal: data-build-pipeline-remediation
iteration: 1
status_after: active
next_action: "执行独立代码审查与 Task agent 功能验收；通过后关闭 Goal。"
blocker_signature: null
functional_acceptance: null
updated_at: 2026-07-18
---

# 迭代 1：真实格式、图片与质量契约修复

## Current Understanding

审计的六项 P1 共享发布完整性缺口：真实格式解析、图片状态、翻译质量、构建成功状态和独立打包契约彼此脱节。

## Implementation Approach

以真实官方字段和图集规则修复数据，再把质量状态持久化为所有产物的唯一契约；任何失败只保留诊断信息，不生成新包。

## Changes This Iteration

- 建立成就、鞋类、大型可制作物、家具的真实格式和图片端到端回归，并增加必需图片缺失的失败门禁测试。
- 修复旧格式字段、图集裁切、怪物中文末字段、翻译 `invalid` 判定和隐藏 NPC 图片不适用状态。
- 引入 schema v3 持久化 artifact metadata、质量派生报告、类型中文目录，以及拒绝失真独立打包的门禁。
- 修复独立审查发现的陈旧 canonical 包路径：失败重建会可恢复地隔离旧包，而不会让其被误认为本次产物。
- fixture 构建也写入失败质量 metadata；无论是在输入、基础数据断言还是图片质量阶段失败，复用输出目录中的 canonical 包都会被可恢复地隔离。
- 将四个审计视觉类型纳入必需官方类型契约；手工覆盖不能伪造完整翻译、移除必需图片或覆盖物化后的图片路径。
- 对历史发布完成表述增加勘误链接，不修改历史 Git 记录。

## Verification Evidence

- 自动化：`python -m pytest` 95 passed，`python -m ruff check .` 通过。
- 真实资产：3,688 实体、0 不可用翻译、0 数据错误、984/984 必需图片；审计四类图片数量为 39、182、645、18。
- 产物：`build/goal-real-output-final2` 的报告、SQLite、manifest、`.svdata` 和独立 `package` 元数据一致。

## Problems Encountered

真实结构夹具最初遗漏怪物中文末字段；已按官方 `Monsters.zh-CN.json` 结构补齐，并将末字段作为显示名解析。没有降低门禁。

## Next Attempt

进行最小必要的独立代码审查与 Task agent 功能验收，然后更新 Goal 状态。

## State Update

`state.yaml.current_iteration` 更新为 1，Goal 保持 `active`，无 blocker。
