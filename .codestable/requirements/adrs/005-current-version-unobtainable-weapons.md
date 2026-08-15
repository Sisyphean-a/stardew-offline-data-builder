---
id: 005
title: 当前版本不可获得武器的受限分类
status: accepted
scope: context:offline-official-data
---

# 005 当前版本不可获得武器的受限分类

## 背景

`Weapons.json` 中的 Galaxy Slingshot（`weapon:34`）和 Rapier（`weapon:49`）仍作为物品记录存在，但完整本机 1.6.15.24356 官方 JSON、`Data/Shops.json`、矿井特殊奖励/宝箱/重混宝箱、钓鱼宝箱、火山宝箱、怪物猎杀奖励，以及 `Stardew Valley.dll` 的相关创建、奖励、事件和动作分支均未提供当前版本的获得路径。把这两个条目的 `acquisition` 长期保留为 `not_collected` 会阻断完整真实候选；把它们猜成可获得地点或一般性地免除缺失又会污染玩家事实语义。

## 决定

仅对如下不可分割的官方发布绑定，将 `weapon:34` 与 `weapon:49` 的 `acquisition` 标为 `not_applicable`：

- 游戏版本：`1.6.15.24356`；
- `Stardew Valley.dll` SHA-256：`7f1e5b8e58d2758b78570ba771bbeb03d33522f62188bf6c32edf0cf626deaee`；
- 完整本机解包官方 JSON（以解包根相对路径与文件字节计算）SHA-256：`d582dd6b3e9260eee2f26c00d16a14704e4ef44a3d2cf0a4de94f9375c356222`。

该结论是**当前版本无可获得路径**，不声称为官方直接字段，也不适用于其他武器、其他版本、DLL 或官方资产哈希。投影保留 DLL 定位、版本/双哈希来源文档、逐槽 evidence 和转换规则 `official-current-version-unobtainable-weapon-v1`。任何绑定不匹配时，构建器不得应用该规则，应由常规核心槽补成 `not_collected` 并要求重新调查与审核。

## 备选方案

- **继续标为 `not_collected`：** 忠实表达未闭合调查，但永久阻断已穷尽的当前版本真实候选。
- **把武器档案或基础矿层当成获得路径：** 没有运行时创建证据，会向玩家发布错误地点。
- **对缺失武器自动标为 `not_applicable`：** 可通过覆盖门禁，但没有逐项调查、范围或版本保护。
- **使用社区补充事实：** 当前官方程序集已能给出可审计的否定结论，额外来源不会提高该版本约束的可信度，且会引入版本漂移。

## 后果

- 正式候选读取 DLL 与完整解包 JSON 的哈希，并仅在三项绑定全部匹配时投影这两个槽。
- 游戏更新、重新解包差异或 DLL 改动会安全地恢复为 `not_collected`，必须重新进行官方证据调查并更新本 ADR、规则、测试和历史。
- 该例外不会改变普通武器的获得路径投影，也不会改变 C1 的购买价格或兑换成本语义。

## 代码锚点

- `src/builder/commands/schema5_candidate.py`
- `src/builder/pipeline/schema5_projection.py`
- `tests/test_schema5_staging.py`

## 相关历史

- `.codestable/history/2026-08.md`：当前版本武器获得缺口的调查与闭合。
