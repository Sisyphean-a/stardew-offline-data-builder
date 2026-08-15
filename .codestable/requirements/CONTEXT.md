---
scope: workspace
---

# 领域上下文

本项目把用户本机《星露谷物语》的官方资产转换为离线应用可消费的数据包。

## 作用域

- [context:offline-official-data](contexts/offline-official-data.md)：官方资产、本地化、标准化和质量边界。代码位置：`src/builder/sources`、`src/builder/parsers`、`src/builder/pipeline`、`tests`。
- [package:builder](../architecture/packages/builder.md)：实现该领域上下文的唯一 Python 包。
- [shared:artifact-contract](../architecture/shared/artifact-contract.md)：构建产物跨 SQLite、manifest、报告和 `.svdata` 的共享契约。
- 架构决定：[`adrs/003-official-evidence-first-and-governed-supplements.md`](adrs/003-official-evidence-first-and-governed-supplements.md)、[`adrs/002-quality-gated-publish-artifacts.md`](adrs/002-quality-gated-publish-artifacts.md)、[`adrs/004-player-facts-v1-publish-contract.md`](adrs/004-player-facts-v1-publish-contract.md)、[`adrs/005-current-version-unobtainable-weapons.md`](adrs/005-current-version-unobtainable-weapons.md)；ADR 003 已替代 ADR 001。

## 通用语言

**官方资产**：用户本机游戏安装中的 `Content` 或其本地解包 JSON、PNG；它是游戏事实的第一优先来源。只有相关官方路径无法稳定表达已确认的玩家核心语义时，才能使用经过版本化审核的补充事实。
_避免_：未经调查就改用社区数据、运行时网络数据或无来源推测。

**离线数据包**：由 SQLite、manifest、报告和实际生成图片组成的 `.svdata` ZIP 产物。
_避免_：只包含数据库的导出文件。

## 稳定规则

- 构建器与应用运行时不联网、不下载、不上传、不提交游戏资源，也不修改原始 `Content`；补充事实只能作为仓库中经过审核的版本化输入。
- 解析失败、缺失支持文件、未知官方资产、图片错误和质量失败必须显式进入诊断结果；失败不能伪装成可发布成功。
- 本地别名、分类和人工覆盖只改变规范化或展示字段，不替换官方事实；覆盖的字段范围和图片保护规则由代码校验。
