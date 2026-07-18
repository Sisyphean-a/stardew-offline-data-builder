---
doc_type: audit-finding
audit: 2026-07-18-data-build-pipeline
finding_id: "bug-04"
nature: bug
severity: P1
confidence: high
suggested_action: cs-issue
status: open
---

# Finding 04：解析或资源错误不会阻止生成“成功”数据包

## 速答

单个官方 JSON 的读取或解析错误仅追加到报告后继续，构建命令只检查四个基础类别是否非空。任何扩展类别的整类缺失、部分解析失败或图片失败都可以随 `success: true` 的数据包一并发布。

## 关键证据

- `src/builder/sources/game_source.py:83-99` — JSON 读取或解析异常被写入 `result.errors` 后直接返回，遍历继续。
- `src/builder/commands/build.py:82-83`、`147-157` — 构建前只断言 `object`、`crop`、`fish`、`villager` 四类存在。
- `src/builder/commands/build.py:99-106` — 收集到的 `official.errors` 和图片错误直接写入报告，不影响数据库、manifest 或包的生成。
- `src/builder/pipeline/reports.py:63-78` — `build-summary.json` 无条件写入 `success: true`，即使 `dataErrors` 非零。
- 当前真实包已同时包含 `success: true`、`dataErrors: 1` 和一条未找到官方图片资源的错误。

## 影响

发布产物的“成功”标志不能代表数据完整。扩展类型的失败会在消费者侧表现为条目缺失、字段为空或无图，而非构建失败；消费者也不会读取构建报告来阻止导入。

## 建议动作

`cs-issue`。本审计按委托要求不提供修复方案。
