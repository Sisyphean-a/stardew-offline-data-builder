---
doc_type: issue-report
issue: 2026-07-18-data-build-pipeline-quality
status: confirmed
issue_path: standard
severity: P1
summary: 数据构建包在存在不可展示实体、缺图和数据错误时仍被标记为成功且翻译完整
tags: [data-pipeline, data-quality, release-integrity]
---

# 数据构建产物质量与成功状态不一致 Issue Report

## 1. 问题现象

使用真实官方游戏资产构建后，数据包会包含用户不可读或不可展示的实体，同时构建报告与 manifest 仍宣称构建成功、翻译无缺失。

审计已确认的可观察现象包括：

- 57 条实体使用纯数字作为名称，且没有描述和图片；其中包含全部 39 条成就和 18 条鞋类。
- 成就、大型制造物、家具、鞋类共 884 条视觉实体没有图片路径，报告中没有对应异常。
- `reports/build-summary.json` 的 `success` 为 `true`，即使构建记录了数据或资源错误。
- `missingTranslations` 为 `0`，但上述不可展示实体仍被计入“翻译完整”。
- 数据包未提供完整的中文类型展示元数据，消费者会展示技术标识。

## 2. 复现步骤

1. 使用真实官方解包资产执行数据构建，生成 `dist/stardew-zh-cn.svdata`。
2. 查询包内 SQLite 实体、图片路径、翻译状态，并读取 `manifest.json` 与 `reports/build-summary.json`。
3. 观察到：包内存在不可展示或缺图实体、构建错误和技术类型标识，但报告及 manifest 仍给出成功或完整结论。

复现频率：稳定；审计在当前真实构建产物中已复现。

## 3. 期望 vs 实际

**期望行为**：真实官方资产的构建只有在输出实体可展示、视觉实体图片状态可解释、数据错误被正确处理、报告与数据状态一致时，才标记为成功并可发布。

**实际行为**：构建会生成含有不可展示实体、未解释缺图和数据错误的包，同时仍标记成功和翻译完整；现有测试也未阻止该产物通过。

## 4. 环境信息

- 涉及模块 / 功能：`src/builder/` 的官方资产解析、标准化、图片物化、构建报告、打包与数据库检查。
- 相关文件 / 函数：`parsers/official.py`、`pipeline/normalize.py`、`pipeline/images.py`、`pipeline/reports.py`、`commands/build.py`、`commands/package.py` 及相关测试。
- 运行环境：真实官方解包资产的本地构建产物 `dist/stardew-zh-cn.svdata`。
- 其他上下文：审计 `2026-07-18-data-build-pipeline` 的 6 项高置信度 P1 发现均属于该问题范围。

## 5. 严重程度

**P1** — 数据包可被标记为成功并被发布，但其中多个面向用户的类别不可正确展示，且质量报告提供错误结论。

## 备注

本 issue 合并处理审计 Finding 01 至 06：旧格式实体的展示字段、翻译质量统计、视觉实体图片状态、构建发布门槛、真实资产回归测试与类型展示元数据。由于涉及解析、处理、报告、打包和测试多个模块，采用标准路径。

Owner 已于 2026-07-18 确认完整范围，并要求通过 `data-build-pipeline-remediation` Goal 持续推进到功能验收完成。本 issue 作为该 Goal 的问题记录和后续根因分析依据。
