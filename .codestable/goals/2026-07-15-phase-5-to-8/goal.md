---
doc_type: goal
goal: phase-5-to-8
status: active
---

# 完成阶段 5 到阶段 8

## Objective

把项目从阶段 4 推进到完整 MVP，完成社区数据合并、`.svdata` 打包、完整数据扩展与图片处理。

## Starting Point

当前仓库已经完成阶段 1 到阶段 4：fixture 构建闭环、`doctor`、`unpack`、四类官方中文解析、SQLite 写入与检视均已可用，并已有验收记录。

## Acceptance Criteria

- 阶段 5：稳定 ID 匹配、人工映射与报告输出完成，禁止自动模糊合并。
- 阶段 6：可生成 `manifest.json`、`stardew.db`、`stardew-zh-cn.svdata`，并校验 SHA-256 与重复构建一致性。
- 阶段 7：按 `PROJECT.md` 扩展完整数据类型并持续补测试。
- 阶段 8：完成图片提取、裁剪、缩略图、无损 WebP 与 `image_path` 写入。
- `python -m builder build ...` 能跑通完整构建。
- `pytest` 与 `ruff check .` 通过。

## Non-Goals

- 不做 GUI。
- 不做 Web 服务。
- 不自动联网下载第三方工具。

## Decisions And Assumptions

- 先严格按阶段顺序推进，不提前跳到图片。
- 阶段 5 会在当前四类实体基础上先打通完整 `build` 命令，再逐步扩展更多数据类型。
- 所有新增能力都以本地夹具和虚构数据先建测试，再接入真实目录流程。

## Current State

新 goal 已创建，尚未开始阶段 5 实现。

## Next Action

梳理 `build` 命令、数据库 schema、报告输出、社区数据输入格式与当前代码差距，确定阶段 5 最小闭环。
