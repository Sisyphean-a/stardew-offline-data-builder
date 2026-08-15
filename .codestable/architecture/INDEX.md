---
scope: workspace
---

# 架构索引

本项目是单仓单包 Python 命令行工具。实现包为 `package:builder`，领域范围为离线官方数据构建。

## 范围地图

- [package:builder](packages/builder.md)：CLI、官方资产发现与解析、标准化、关联、图片物化、SQLite、报告和 `.svdata` 发布。
- [shared:artifact-contract](shared/artifact-contract.md)：构建元数据在 SQLite、manifest、报告和 `.svdata` 之间保持一致的契约。
- 架构决定：[`requirements/adrs/002-quality-gated-publish-artifacts.md`](../requirements/adrs/002-quality-gated-publish-artifacts.md)、[`requirements/adrs/003-official-evidence-first-and-governed-supplements.md`](../requirements/adrs/003-official-evidence-first-and-governed-supplements.md)、[`requirements/adrs/004-player-facts-v1-publish-contract.md`](../requirements/adrs/004-player-facts-v1-publish-contract.md)、[`requirements/adrs/005-current-version-unobtainable-weapons.md`](../requirements/adrs/005-current-version-unobtainable-weapons.md)；ADR 001 已由 ADR 003 替代。

## 公开入口

- `src/builder/cli.py`：`build`、`build-fixture`、`doctor`、`unpack`、`inspect`、`package`。
- `src/builder/__main__.py`：`python -m builder` 入口。
- `README.md`、`PROJECT.md`：面向使用者和维护者的公开说明。

## 按范围加载

从 `package:builder` 开始，同时读取 `shared:artifact-contract` 和
`requirements/CONTEXT.md`；涉及官方数据边界时再读取
`requirements/contexts/offline-official-data.md`。原因、旧称和已替代材料只按需检索
`.codestable/history/` 与 Git。
