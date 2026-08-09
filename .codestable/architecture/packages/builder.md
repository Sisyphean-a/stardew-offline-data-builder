---
scope: package:builder
code-paths:
  - src/builder
  - tests
---

# builder 包

`builder` 把本机《星露谷物语》官方资产转换为可检索的 SQLite、图片、报告和 `.svdata` 数据包。

## 公开边界

- `src/builder/cli.py` 暴露 `build`、`build-fixture`、`doctor`、`unpack`、`inspect`、`package`。
- `src/builder/__main__.py` 让 `python -m builder` 调用 Typer CLI。
- `build`、`unpack`、`doctor` 通过 `builder.sources.steam_discovery.resolve_game_directory` 解析显式或自动发现的游戏目录；显式路径优先，自动发现必须只有一个完整候选。

## 主流程

1. `commands/build.py:build_command` 解析游戏目录和解包目录，加载官方实体与支持数据。
2. `sources/game_source.py:load_game_data_from_unpacked_dir` 发现 `Data/`、角色日程等官方 JSON，调用 `parsers/official.py` 解析，再合并 `Strings/*.json` 的英文和官方中文；读取失败和解析失败保留在 `GameSourceLoad.errors`。
3. `pipeline/normalize.py:normalize_entities` 以 `<entity_type>:<official source id>` 形成稳定 ID，合并语言、别名、分类、来源和翻译状态。
4. `pipeline/official_enrichment.py:enrich_official_entities` 仅从官方支持资产建立 `officialDerived` 和 `_provenance.official` 关联；`pipeline/overrides.py` 之后才应用显式可编辑覆盖。
5. `pipeline/images.py:materialize_entity_images_with_report` 按解析器写入的官方图片元数据裁切、缩略和 WebP 化，并返回结构化资源错误。
6. `commands/build_output.py:write_build_output` 生成 SQLite、报告、manifest；质量不通过时保留诊断产物、写发布阻断标记并以质量退出码结束，通过后才创建 `.svdata`。
7. `commands/package.py:package_existing_output` 重新校验发布状态、artifact metadata 和数据库图片引用，用临时 ZIP 校验后原子替换正式包。

## 模块职责

- `sources/`：游戏目录/Steam 发现、官方 JSON 与支持文件、项目本地配置输入。
- `parsers/`：官方现代结构、旧字符串结构、本地化和旧格式视觉规则。
- `pipeline/`：稳定化、官方派生关联、图片、搜索、质量、报告、发布状态和包完整性。
- `database/`：SQLite schema、事务性临时文件写入、查询和 artifact metadata 读取。
- `commands/`：CLI 用例编排，不承担解析细节。
- `utils/`：路径、JSON、哈希、时间、图片和外部进程等无领域所有权的基础机制。

## 稳定实现规则

- `config.py` 的 `ENTITY_TYPE_LABELS` 是当前支持实体类型及其中文展示名的代码清单；缺少必需类型或中文标签时质量门禁失败。
- `pipeline/normalize.py` 将纯数字中文显示名判为 `invalid`；不可本地化的技术记录才使用 `not_applicable`。
- 必需图片由 `extra_json.imageRequired` 声明。`parsers/legacy_visuals.py` 为成就、鞋类、大型可制作物、家具等旧格式建立裁切元数据；无源或越界裁切都会形成错误。
- `database/writer.py` 通过 `stardew.db.tmp` 写入后替换正式数据库；`commands/package.py` 通过临时归档校验后替换正式 `.svdata`。
- `pipeline/release_state.py` 用 `.release-blocked.json` 隔离失败构建和 fixture 输出，`package` 不得绕过该标记。

## 验证锚点

- 单元和真实数据回归：`tests/`，尤其是 `test_real_official_data.py`、`test_quality_gate.py`、`test_package.py`、`test_legacy_visuals.py`。
- 格式和静态检查：`python -m pytest`、`python -m ruff check .`。
