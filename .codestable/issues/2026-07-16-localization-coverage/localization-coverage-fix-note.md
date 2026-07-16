---
doc_type: issue-fix
issue: 2026-07-16-localization-coverage
path: standard
fix_date: 2026-07-16
related: [localization-coverage-analysis.md]
tags: [localization, official-data, parser]
---

# 真实数据本地化覆盖修复记录

## 1. 实际采用方案

采用分析中的方案 A：以真实官方 `Strings/*.json` 与 `Strings/*.zh-CN.json` 为唯一文本来源，补齐旧式家具、特别订单、怪物任务、任务、收集包、料理/制作配方和收集包区域的标准化中文投影；配方只在缺少显式官方名时才回填产物名；技术记录改为显式 `not_applicable`，不再伪装成缺失翻译。

第一性原则 pre-pass：外部行为是用户可见实体获得官方中文且告警只统计真实缺失；保持官方优先、社区仅补充、原始属性可追溯；最小充分改动限于真实格式解析、关联和状态统计；未引入人工中文表、静默回退或无关重构。

## 2. 改动文件清单

- `src/builder/parsers/official.py`：识别大写 `Name`、家具/任务/收集包旧式显示字段、配方显式名及产物 ID。
- `src/builder/parsers/localization.py`：解析特别订单短占位符，规范双反斜杠资产路径。
- `src/builder/parsers/localization_values.py`：用官方 `Strings/Locations` 键值对解析收集包区域名。
- `src/builder/parsers/official_assets.py`、`src/builder/config.py`：将裁缝规则与普通制作配方区分。
- `src/builder/sources/game_source.py`：让料理和制作配方仅在无显式名时关联官方产物的名称、描述与图片。
- `src/builder/pipeline/normalize.py`、`src/builder/models.py`、`src/builder/pipeline/reports.py`：引入 `not_applicable` 翻译状态及其报告计数。
- `tests/test_real_official_data.py`：覆盖家具、订单、任务、配方、收集包和技术键的真实结构契约。
- `tests/test_legacy_localization.py`：覆盖显式配方名优先、料理产物回填、旧式任务标题/描述和收集包末尾名称。

## 3. 验证结果

- 定向真实结构测试：`tests/test_real_official_data.py` 与 `tests/test_legacy_localization.py`，5 passed。
- 全量测试：31 passed。
- 静态检查：`python -m ruff check .` 通过；`git diff --check` 通过。
- 真实游戏 1.6.15.24356 与本地社区数据黑盒构建成功；`PRAGMA integrity_check` 为 `ok`。
- 最终构建的 `missingTranslations` 为 0，`notApplicableTranslations` 为 869；家具、特别订单、怪物任务、任务、收集包、料理和制作配方均已验证为官方中文。旧式 247 条记录中没有空中文名或内部键冒充显示名；6 条显式制作配方名均来自官方字符串表。
- 代码审查：第一轮的 REV-001、REV-002、REV-003 已修复；第二轮独立 review gate 结论为 `passed`。

## 4. 遗留事项

- `RandomBundles` 内嵌的原始项目明细仍保留在 `extra_json`，本次只将其可展示区域名称标准化；未把嵌套明细拆成独立实体。
- 构建报告仍保留 143 条社区未匹配和 1 条 Welwick 官方肖像缺失，它们与本问题无关且未被隐藏。
