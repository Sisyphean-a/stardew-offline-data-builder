---
doc_type: functional-acceptance
goal: "phase-5-to-8"
verdict: pass
updated_at: "2026-07-15"
---

# 功能验收

> **2026-07-18 发布勘误**：此历史 `pass` 不再作为当前数据包发布认证；原因和修复验证见 [当前勘误](../2026-07-18-data-build-pipeline-remediation/completion-claim-correction.md)。

## Reviewer

- 只读功能验收代理
- agent_id：`019f6665-9c2f-7b71-8c15-233410e3057a`
- 关闭结果：已消费结果并关闭 agent

## Acceptance Checks

- 阶段 5：稳定 ID / internal name / 英文名精确匹配 / override 合并，且无自动模糊合并
- 阶段 6：`manifest.json`、SHA-256、`.svdata` ZIP、包结构与重复构建一致性
- 阶段 7：`PROJECT.md` 列出的扩展类型已接入通用解析与真实构建统计
- 阶段 8：图片提取、裁剪、缩略图、无损 WebP、`image_path` 写库、图片入包
- `python -m builder build ...` 可跑通
- `pytest` 与 `ruff check .` 通过

## Functional Evidence

- 阶段 5
  - `src/builder/pipeline/match.py` 仅使用稳定 ID、`internal_name`、英文名精确匹配和 override
  - `tests/test_match_merge.py` 验证稳定匹配与 unmatched 记录
  - `tests/test_build.py` 验证 `unmatched.json` 会落盘
- 阶段 6
  - `src/builder/commands/package.py` 会写 `manifest.json`、数据库 SHA-256，并生成 `.svdata`
  - `tests/test_package.py` 验证 ZIP 结构和固定时间下的重复构建一致性
- 阶段 7
  - `src/builder/parsers/localization.py` 已覆盖 `villager_gift`、`npc_schedule`、`cooking_recipe`、`crafting_recipe`、`shop`、`quest`、`bundle`、`monster`、`drop`、`mineral`、`weapon`、`ring`、`achievement`、`special_order`、`ginger_island`
  - `tests/test_phase7_generic_types.py` 验证通用解析
  - `tests/test_package.py` 与 `tests/test_database.py` 验证真实构建统计与检视输出
- 阶段 8
  - `src/builder/utils/images.py` 实现透明边裁剪、缩略图和无损 WebP
  - `src/builder/pipeline/images.py` 基于 `imageSource` + `imageRect` 生成 `images/*.webp`
  - `src/builder/database/writer.py` 将 `image_path` 写入 `entities`
  - 实测数据库中 `object:24` 的 `image_path` 为 `images/object-24.webp`
  - 实测 `.svdata` 包内包含 `images/object-24.webp`
- 全量验证
  - `pytest`：`25 passed`
  - `ruff check .`：`All checks passed!`
  - `python -m builder build --game-dir "build/acceptance-game" --community-data "tests/fixtures/community-data" --output "build/acceptance-dist"`：成功

## Residual Risks

- 阶段 7 的扩展类型目前主要依赖通用 `entries` 结构，后续若要细化领域字段语义，需要补更针对性的夹具与验收。
- `errors.json` 在成功构建路径下为空；若后续强调“单条数据错误继续构建”的异常路径，可再补专门夹具。

## Follow-up

- 本 goal 无阻塞，验收通过。
