---
doc_type: audit-finding
audit: 2026-07-18-data-build-pipeline
finding_id: "bug-06"
nature: bug
severity: P1
confidence: high
suggested_action: cs-issue
status: open
---

# Finding 06：数据包契约没有提供完整的用户可读类型元数据

## 速答

构建器内部虽定义了一部分中文类型标签，但该信息只用于命令行 `inspect`，没有写入 SQLite 或 manifest。数据包只提供原始 `entity_type` 字符串和原始 `extraCounts` 键，消费者无法从包中获得完整、稳定的用户展示名称。

## 关键证据

- `src/builder/config.py:15-36` — `ENTITY_TYPE_LABELS` 仅包含部分类型；例如 `big_craftable`、`furniture`、`footwear`、`tool`、`trinket`、`weapon` 不在映射中。
- `src/builder/commands/inspect.py:7,23-24` — 该映射只在命令行数据库检查输出中使用。
- `src/builder/commands/package.py:30-57` — manifest 仅写入原始 `extraCounts`，没有类型标签或展示属性。
- 真实 `manifest.json` 的键为 `achievement`、`big_craftable` 等技术标识；实际消费者据此展示英文 `achievement`。

## 影响

数据包不自描述其面向用户的分类含义，消费者界面只能自行硬编码或直接展示技术标识。当前导入后的列表正是以 `achievement` 而非“成就”呈现。

## 建议动作

`cs-issue`。本审计按委托要求不提供修复方案。
