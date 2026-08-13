---
scope: shared:artifact-contract
applies-to:
  - package:builder
---

# 构建产物契约

构建元数据是 SQLite、manifest、报告、图片清单和 `.svdata` 之间的共同契约；发布包只能由同一份通过质量校验的元数据产生。当前目标协议是 SQLite schema 5、manifestVersion 2、`player-facts-v1`。

## 规则

- `pipeline/artifact_metadata.py:build_artifact_metadata` 生成 manifest/schema/content contract、必需/可选能力、构建器/语言/游戏/发布策略版本、源哈希、可发布状态、内容与质量摘要。
- schema 5 将实体、核心事实槽/多值事实、关系组/有向关系、条件、来源/证据、视觉、列表卡片/筛选、别名/ID 重定向分离为可校验表或等价只读投影；`officialDerived` 不再是发布读取 API。
- `entity_cards`、搜索投影和 `browse_facets` 由规范事实确定性生成；facet 绑定稳定规则 scope、类型化值/区间、状态和条件完整性，关系提供有向正反查询索引。质量门禁校验投影与规范事实一致，不允许投影成为第二事实源。
- `database/writer.py` 将该元数据写入 `build_meta.artifact_metadata`；`commands/package.py` 读取并校验它，再生成 manifest 和 ZIP。
- 质量状态不是提示信息：翻译缺失/无效、数据或图片错误、缺少实体类型中文标签都会使构建不可发布。
- fixture 的 metadata 明确 `publishable: false`；失败构建和 fixture 输出使用 `.release-blocked.json`，独立 `package` 必须拒绝。
- 图片清单把实体、视觉状态、路径、实际来源、裁切、规则版本与文件哈希绑定；独立 package 重新校验内容而非只看路径存在。
- 构建和打包启用并执行 SQLite `foreign_key_check`，校验核心槽、状态组合、条件、证据、关系、必需索引、投影一致性、覆盖摘要和内容哈希；半迁移或未知必需能力拒绝。
- 真实候选报告逐分类逐核心槽给出 eligible/answered/investigated/not_collected 分母与失败实体，并绑定条件、证据、关系、补充事实、搜索/facet、查询计划、视觉复核和相对上个获准包的差异。P0/P1、直接字段、关系、条件、搜索/facet 和视觉门槛由 `context:offline-official-data` 规定，总体平均不能掩盖最差槽。
- 发布证明保留当前和前两个发布的完整证据，且完整证据至少保留 12 个月；精简版本、输入 hash、审批、门禁摘要和最终结论长期保留。真实资产和图片不进入 Git，工作区外证据通过内容 hash 与发布物绑定。
- ZIP 先写临时文件，验证成员、CRC 和所有内容绑定后原子替换正式包。

## 代码锚点

- `src/builder/pipeline/artifact_metadata.py`
- `src/builder/pipeline/quality.py`
- `src/builder/pipeline/package_integrity.py`
- `src/builder/pipeline/release_state.py`
- `src/builder/commands/build_output.py`
- `src/builder/commands/package.py`
- `src/builder/database/writer.py`
