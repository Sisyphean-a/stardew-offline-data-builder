---
id: 001
title: 官方资产作为事实来源
status: superseded
superseded-by: 003
scope: workspace
---

# 001 官方资产作为唯一事实来源

## 背景

项目最初的阶段记录允许把社区数据作为便利字段来源，但本项目的用户目标是从本机正版游戏生成离线数据；社区数据会让事实来源、版本和离线边界变得不清晰。

## 决定

> 本决定已由 [003 官方证据优先与受控补充事实](003-official-evidence-first-and-governed-supplements.md) 替代。下文保留当时决定。

正式构建只读取用户本机的 `Content`、`Content (unpacked)` 和其中的官方 JSON/PNG。`Data/Shops.json`、`Locations.json`、`FishPondData.json`、`Machines.json` 等官方支持资产可以用于跨表派生，但不能被外部资料替代。`data/aliases.zh-CN.json`、`data/categories.zh-CN.json`、`data/overrides.zh-CN.json` 只做本地展示、搜索和显式人工字段修正。

程序不联网、不下载、不上传、不提交游戏资源，也不修改原始 `Content`。

## 备选方案

- 保留社区数据合并：能快速补充便利字段，但会把非官方内容混入事实层，且无法保证离线来源一致。
- 使用硬编码快照或模拟数据：能让测试通过，但不能随本机游戏版本更新，也会制造虚假成功。
- 在线查询补全：违反离线边界，并引入网络可用性和数据许可风险。

## 后果

- 解析器和官方支持关联必须持续覆盖本机资产格式；官方未结构化表达的攻略、摘要和主观标签不进入产物。
- 构建结果可通过 `_provenance.official` 追溯到官方文件；本地覆盖不再被误认为游戏事实。
- 删除社区输入是有意的兼容性破坏，后续不得恢复旧参数来绕过该边界。

## 代码锚点

- `src/builder/sources/game_source.py`
- `src/builder/sources/official_support.py`
- `src/builder/pipeline/official_enrichment.py`
- `src/builder/pipeline/overrides.py`
- `PROJECT.md` 第 1、2、3、5 节

## 相关历史

- `.codestable/history/2026-07.md`：2026-07-16 官方数据独立构建。
- Git `4d4137a`：移除社区数据依赖，纯官方数据构建。
