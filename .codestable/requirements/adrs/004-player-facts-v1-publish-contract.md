---
id: 004
title: player-facts-v1 发布契约
status: accepted
scope: shared:artifact-contract
---

# 004 player-facts-v1 发布契约

## 背景

schema 4 把玩家事实、跨表关系和来源压入 `entities.extra_json.officialDerived`，应用必须再次解释原始字段。该结构无法校验事实状态、条件完整性、有向关系、逐事实证据、补充事实和实体视觉，也无法为搜索、覆盖报告和安装拒绝提供稳定分母。

## 决定

下一发布协议采用 SQLite schema 5、manifestVersion 2 和固定内容语义 `player-facts-v1`。这是破坏性升级：builder 默认只生成新协议，不长期双写 `officialDerived`，schema 4 保留为旧协议而不在设备上转换。

schema 5 以规范表或等价只读投影分别承载：实体身份、核心事实槽和多值事实、有向关系族与关系边、规范条件、来源文档与记录定位、逐 claim 证据与转换规则、实体视觉、列表卡片/浏览筛选投影、搜索别名与 ID 重定向。原始官方字段只进入构建诊断、报告或隔离证据区，不构成应用公共读取 API。

分类契约要求的每个核心问题恰有一个事实槽。发布状态为 `fixed`、`conditional`、`dynamic_rule`、`unknown`、`not_collected` 或 `not_applicable`；`rejected` 只属于构建诊断。已知状态具有类型化值和证据，条件事实引用完整条件集合，缺失行不代表任何状态。关系组表达关系族整体状态，关系边保留 subject、闭集 predicate、object、原始方向、条件和证据。

实体继续使用 `<entity_type>:<official-id>`。事实、关系、报价和加工规则使用不依赖中文名、数组序号、路径或当前值的稳定 ID；无官方稳定键时使用仓库审核登记键。外键在构建、打包和安装时启用并校验。

manifest 2 绑定数据库 schema/hash、必需与可选能力、builder/游戏/语言/发布策略版本、图片清单及 hash、事实/条件/来源/补充事实/关系/视觉覆盖摘要、质量与报告。未知必需能力拒绝，未知可选能力可忽略。

构建和独立打包必须拒绝版本组合不支持、产物元数据不一致、schema/外键/索引失败、核心槽缺失或重复、非法状态组合、断裂关系、证据缺失、条件不完整冒充固定事实、补充事实冲突/过期/冒充官方、图片清单不一致及半迁移数据库。

## 备选方案

- **继续扩展 schema 4 `officialDerived`：** 改动较小，但无法建立可校验公共语义，只会延续应用解释 raw JSON。
- **长期双写 schema 4 与 schema 5：** 有利于旧消费者，但会形成双事实源和持续测试矩阵。
- **只升级 manifest、不升级 SQLite：** 无法通过数据库约束和查询 API落实事实、关系与来源契约。
- **由应用原地转换 v4：** v4 缺少逐事实状态和证据，转换只能猜测。

## 后果

- builder 需要重构规范模型、SQLite schema、索引、报告、质量门禁和包验证。
- 首个 v5 包必须与冻结的真实 v4 包生成 ID、事实、关系、图片和分类覆盖迁移差异报告。
- `entity_cards` 和 `browse_facets` 是由规范事实生成并校验的一致性投影，不是第二事实源。
- 旧版本回滚依赖保留完整 v4 包；v5 错误通过重新发布完整 v5 包或升级 schema 修复。

## 代码锚点

- `src/builder/database/schema.sql`
- `src/builder/database/writer.py`
- `src/builder/pipeline/artifact_metadata.py`
- `src/builder/pipeline/official_enrichment.py`
- `src/builder/pipeline/package_integrity.py`
- `src/builder/commands/build_output.py`
- `src/builder/commands/package.py`

## 相关历史

- `.codestable/history/2026-08.md`：2026-08-13 确立 player-facts-v1 跨仓库契约。
- `E:/github/valley-dex/.wayfinding/player-first-encyclopedia/decisions/09-cross-repo-data-contract.md`：完整契约、拒绝和迁移裁决。
