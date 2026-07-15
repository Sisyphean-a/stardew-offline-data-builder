---
doc_type: goal
goal: phase-1-to-4
status: active
---

# 完成阶段 1 到阶段 4

## Objective

把项目从阶段 0 推进到阶段 4 完成，覆盖 fixture 数据闭环、环境检查、外部解包调用，以及普通物品、作物、鱼类、村民四类官方中文解析。

## Starting Point

当前仓库只有 Python 项目骨架、基础 CLI、Ruff 与 pytest 配置，以及一个 `python -m builder --help` 测试。没有数据模型、数据库写入、doctor、unpack 或解析实现。

## Acceptance Criteria

- `python -m builder build-fixture --output .\dist` 可生成 `stardew.db`。
- `python -m builder inspect .\dist\stardew.db` 可输出概要信息。
- `python -m builder doctor` 与相关路径参数检查行为正确。
- `python -m builder unpack` 可正确调起外部程序并处理跳过与强制重跑。
- 四类官方中文解析器实现完成并通过测试。
- `pytest` 与 `ruff check .` 全部通过。

## Non-Goals

- 不做社区数据合并。
- 不生成 `.svdata`。
- 不做图片、Android、联网下载、Wiki 数据。

## Decisions And Assumptions

- 阶段 1 的构建入口使用 `build-fixture`，保持与 `PROJECT.md` 一致。
- 阶段 4 以测试夹具模拟解包后的官方 JSON，完成解析器与测试，不提前进入阶段 5 合并逻辑。
- 所有路径统一使用 `pathlib.Path`，数据库使用内置 `sqlite3`。

## Current State

Goal 已创建，尚未开始业务实现。

## Next Action

梳理阶段 1 到阶段 4 的模块边界、CLI 入口、测试夹具格式与数据库最小 schema。
