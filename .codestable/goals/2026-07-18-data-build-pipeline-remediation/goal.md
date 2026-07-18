---
doc_type: goal
goal: data-build-pipeline-remediation
status: complete
---

# 数据构建质量修复 Goal

## Objective

彻底修复 2026-07-18 数据构建链路审计确认的六项 P1 缺陷，纠正错误的完成表述，并以真实官方资产和独立验收证明数据包可供用户使用后才标记完成。

## Starting Point

当前 `dist/stardew-zh-cn.svdata` 中已有 57 条纯数字名称、无描述且无图片的实体；四类视觉实体共 884 条无图且未被报告。构建报告能在记录错误时仍声明成功，现有回归测试主要使用人工 `entries` 夹具，无法防止真实资产回归。

## Acceptance Criteria

以 `state.yaml` 的七条 acceptance 为准：六项审计发现必须有失效回归测试，真实资产必须通过展示、图片和质量状态验证，包契约与独立打包路径必须完整，历史完成表述必须有勘误，且最终须通过自动检查、真实黑盒验证、独立代码审查和 Task agent 功能验收。

## Non-Goals

不改写 Git 历史；不扩大为 GUI、Web、联网下载或社区数据功能；不将虚构夹具当作真实资产验收；不覆盖现有 `dist/` 作为验证副作用。

## Decisions And Assumptions

- Owner 已明确要求将全部问题放在一个 Goal 中持续推进，不以中间测试绿灯为完成。
- 已确认的 `data-build-pipeline-quality` issue 是本 Goal 的问题记录；需要时会在其下写根因分析与修复记录。
- “仅完成一半”没有可验证的量化依据；本 Goal 使用“当前不可发布、原验收失效”作为事实基线。
- 已知官方本身不存在的资源不能被静默忽略，必须与构建器遗漏明确区分并可审计。

## Current State

六项 P1 与最终 closure 中发现的 fixture 旧包遗留路径均已修复。正式官方资产重建、独立打包、最小独立代码复核和可见 Task agent 功能验收均已通过；历史完成记录已附加勘误而不篡改 Git 历史。

## Next Action

Goal complete.
