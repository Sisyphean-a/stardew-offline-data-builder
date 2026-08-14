---
scope: package:builder
code-paths:
  - src/builder
  - tests
---

# builder 包

`builder` 把本机《星露谷物语》官方资产转换为可检索的 SQLite、图片、报告和 `.svdata` 数据包。

## 公开边界

- `src/builder/cli.py` 暴露正式 schema 5 `build`、显式迁移基线 `build-v4-legacy`、`build-schema5-staging`、`build-fixture`、`doctor`、`unpack`、`inspect`、`package`。
- `src/builder/__main__.py` 让 `python -m builder` 调用 Typer CLI。
- `build`、`unpack`、`doctor` 通过 `builder.sources.steam_discovery.resolve_game_directory` 解析显式或自动发现的游戏目录；显式路径优先，自动发现必须只有一个完整候选。

## 主流程

1. `commands/build.py:build_command` 解析游戏目录和解包目录，加载官方实体与支持数据，并委托 `commands/schema5_candidate.py`；schema 4 `build-v4-legacy` 保留为显式迁移基线。
2. `sources/game_source.py:load_game_data_from_unpacked_dir` 发现 `Data/`、角色日程等官方 JSON，调用 `parsers/official.py` 解析，再合并 `Strings/*.json` 的英文和官方中文；读取失败和解析失败保留在 `GameSourceLoad.errors`。
3. `pipeline/normalize.py:normalize_entities` 以 `<entity_type>:<official source id>` 形成稳定 ID，合并语言、别名、分类、来源和翻译状态。
4. pipeline 从 `NormalizedEntity.source_attributes` 和官方支持文件映射官方字段、跨表关系、可验证计算和受控补充事实，规范化为 `player-facts-v1` 的事实、关系、条件和逐 claim 证据；展示覆盖之后应用且不能改写事实/证据。schema 4 的 `officialDerived` 不再是发布 API。
5. `pipeline/images.py:materialize_entity_images_with_report` 按解析器写入的官方图片元数据裁切、缩略和 WebP 化，并返回结构化资源错误。
6. `commands/schema5_candidate.py` 在临时目录完成 typed projection、核心槽覆盖门槛、schema 5 SQLite/manifest 2/conformance、报告和视觉绑定；质量不通过时保留失败目录和发布阻断标记，成功后整体替换输出并创建 `.svdata`。manifest 还绑定 conformance 与 reports 的内容哈希。
7. `commands/package.py:package_existing_output` 按 manifest 版本分派；schema 5 重新校验契约、数据库哈希、schema fingerprint、typed value/evidence/claim 图、user_version、quick_check、foreign_key_check、conformance、报告与视觉哈希，用临时 ZIP 校验后原子替换正式包。

## 模块职责

- `sources/`：游戏目录/Steam 发现、官方 JSON 与支持文件、项目本地配置输入。
- `parsers/`：官方现代结构、旧字符串结构、本地化和旧格式视觉规则。
- `pipeline/`：稳定化、结构化官方属性映射、跨表事实、图片、搜索、质量、覆盖报告、发布状态、artifact 内容绑定和包完整性。
- `database/`：SQLite schema、事务性临时文件写入、查询和 artifact metadata 读取。
- `commands/`：CLI 用例编排，不承担解析细节。
- `utils/`：路径、JSON、哈希、时间、图片和外部进程等无领域所有权的基础机制。

## 稳定实现规则

- `config.py` 的 `ENTITY_TYPE_LABELS` 是当前支持实体类型及其中文展示名的代码清单；缺少必需类型或中文标签时质量门禁失败。
- `pipeline/normalize.py` 将纯数字中文显示名判为 `invalid`；不可本地化的技术记录才使用 `not_applicable`。
- 每个实体使用明确视觉状态和分类必需名单；`parsers/legacy_visuals.py` 为旧格式建立有版本视觉规则。无源、碰撞、缺裁切、越界、解码/透明错误、哈希不一致或待复核都会阻断发布。
- schema 5 的稳定表启用外键并提供事实、双向关系、证据、条件、视觉、卡片和筛选查询所需索引；预计算投影由规范事实生成并校验，不成为第二事实源。
- `database/writer.py` 通过 `stardew.db.tmp` 写入后替换正式数据库；`commands/package.py` 通过临时归档校验后替换正式 `.svdata`。
- `pipeline/release_state.py` 用 `.release-blocked.json` 隔离失败构建和 fixture 输出，`package` 不得绕过该标记。

## 验证锚点

- 单元和真实数据回归：`tests/`，尤其是 `test_real_official_data.py`、`test_quality_gate.py`、`test_package.py`、`test_legacy_visuals.py`。
- 格式和静态检查：`python -m pytest`、`python -m ruff check .`。
