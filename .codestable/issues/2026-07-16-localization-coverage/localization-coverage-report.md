---
doc_type: issue-report
issue: 2026-07-16-localization-coverage
status: confirmed
severity: P1
summary: 真实构建未将部分官方中文文本投影到标准化实体字段，且把技术键误报为缺汉化。
tags: [localization, official-data, parser]
---

# 真实数据本地化覆盖不足 Issue Report

## 1. 问题现象

真实构建的 `missing-translations.json` 报告 1,653 条缺汉化。其中家具实体的 `name_zh` 被写成数字 ID，特别订单、怪物击杀任务和部分配方的用户可见中文名称或文本未进入标准化字段；同时 NPC 日程键和裁缝规则等技术记录也被计为缺汉化。

## 2. 复现步骤

1. 使用真实游戏解包目录和本地社区数据执行构建。
2. 打开构建产物的 `reports/missing-translations.json`。
3. 观察到 `furniture:0` 的中文名为 `0`，`special_order:Caroline` 与 `quest:Bats` 没有中文名，且 `npc_schedule:Abigail:11`、`crafting_recipe:(H)43` 被列入报告。

复现频率：稳定。

## 3. 期望 vs 实际

**期望行为**：官方已提供中文字符串的用户可见实体应写入 `name_zh`、`description_zh` 等标准字段；内部键不应被视为缺少汉化。

**实际行为**：部分用户可见文本未被解析或关联，技术键也触发了缺汉化告警。

## 4. 环境信息

- 涉及模块 / 功能：真实官方数据解析、本地化、标准化与构建报告。
- 相关文件 / 函数：待分析。
- 运行环境：Windows，本地《星露谷物语》1.6.15.24356 解包目录与本地社区数据。
- 其他上下文：最终产物位于 `C:\tmp\stardew-real-final-validate-20260716`。

## 5. 严重程度

**P1** — 数据库可构建，但中文检索和展示的核心用户可见内容不完整，影响真实数据包的可用性。

## 备注

用户已预授权直接完成修复并明确要求不进行多轮审批，因此本报告完成后继续分析、修复和验证。
