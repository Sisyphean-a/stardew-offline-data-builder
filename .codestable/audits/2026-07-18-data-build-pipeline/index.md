---
doc_type: audit-index
audit: 2026-07-18-data-build-pipeline
scope: 官方游戏 JSON 到 SQLite、图片与 .svdata 的数据构建链路
created: 2026-07-18
status: active
total_findings: 6
---

# 数据构建链路审计报告

## 范围

审计 `src/builder/` 中官方资产发现、旧格式解析、本地化、图片物化、SQLite、报告与 `.svdata` 打包代码；同时以 `dist/stardew-zh-cn.svdata` 的真实产物作为黑盒证据。

已检查 bug、安全、性能、可维护性四个维度。仓库没有 `.codestable/requirements/adrs/`，因此未判定架构偏离。

## 总评

共确认 6 项问题，全部会使“构建成功”与“用户可用”脱钩。当前产物包含 3,688 条记录，但其中 57 条为纯数字名称、无描述、无图片；`achievement`、`big_craftable`、`furniture`、`footwear` 四个视觉类别共 884 条均没有图片。现有 58 个测试和 Ruff 均通过，说明测试覆盖的是构建流程和部分人工夹具，不足以验证真实官方资产产生的展示质量。

## 发现清单

| # | 性质 | 严重度 | 置信度 | 标题 | 文件 |
|---|---|---|---|---|---|
| 1 | bug | P1 | high | 成就与鞋类旧格式被解析成数字 ID | [finding-01.md](finding-01.md) |
| 2 | bug | P1 | high | 翻译状态和报告把失效文本误报为完整 | [finding-02.md](finding-02.md) |
| 3 | bug | P1 | high | 多个可视实体类别没有图片元数据且未被标为异常 | [finding-03.md](finding-03.md) |
| 4 | bug | P1 | high | 解析或资源错误不会阻止生成“成功”数据包 | [finding-04.md](finding-04.md) |
| 5 | maintainability | P1 | high | 测试夹具未覆盖真实旧格式和最终展示质量 | [finding-05.md](finding-05.md) |
| 6 | bug | P1 | high | 数据包契约没有提供完整的用户可读类型元数据 | [finding-06.md](finding-06.md) |

## 按维度分布

| 性质 | P0 | P1 | P2 | 合计 |
|---|---:|---:|---:|---:|
| bug | 0 | 5 | 0 | 5 |
| security | 0 | 0 | 0 | 0 |
| performance | 0 | 0 | 0 | 0 |
| maintainability | 0 | 1 | 0 | 1 |
| arch-drift | 0 | 0 | 0 | 0 |
| **合计** | **0** | **6** | **0** | **6** |

## 验证记录

- `python -m pytest`：58 passed。
- `python -m ruff check .`：通过。
- 对 `dist/stardew-zh-cn.svdata` 直接查询：3,688 条实体；57 条纯数字名称、无中文描述且无图片；1,630 张图片均被数据库引用。
- 构建报告中 `missingTranslations` 为 0，`dataErrors` 为 1，`success` 仍为 `true`。

本文件只记录问题和证据，不提供修复方案。
