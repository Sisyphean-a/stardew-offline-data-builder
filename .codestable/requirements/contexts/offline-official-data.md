---
scope: context:offline-official-data
code-paths:
  - src/builder/sources
  - src/builder/parsers
  - src/builder/pipeline
  - src/builder/database
  - tests
---

# 离线官方数据领域上下文

该边界拥有从本机官方资产得到实体、语言、图片和官方派生关联的含义与质量规则。

## 通用语言

**实体**：由官方数据记录规范化后、以稳定 ID 写入 SQLite 的可查询记录。
_避免_：仅存在于某个原始 JSON 的临时行。

**稳定 ID**：`<entity_type>:<official source id>` 形式的实体标识；同一官方来源 ID 在不同实体类型下仍是不同实体。
_避免_：按遍历顺序生成的序号。

**官方派生字段**：由官方支持文件或官方实体之间关联计算出的 `extra_json.officialDerived` 内容，并通过 `_provenance.official` 记录来源。
_避免_：攻略、主观分类或没有官方结构化依据的推断。

**翻译状态**：实体展示文本的 `complete`、`missing`、`invalid` 或 `not_applicable` 状态。纯数字名称不能证明可展示，技术记录可明确声明不适用。
_避免_：把非空字符串一律称为完整翻译。

**必需图片**：实体的 `extra_json.imageRequired` 为真时，构建必须能从官方 PNG 及其裁切元数据物化 WebP 图片；官方明确不具备展示图片的记录才标记 `imageAvailability: not_applicable`。
_避免_：无图片来源时静默成功。

## 稳定规则

- 现代官方 JSON、旧格式字符串和 `Strings/*.json` 联合解析；英文与官方中文优先，真实缺失与技术不适用分开记录。
- `Data/Shops.json`、`Locations.json`、`FishPondData.json`、`Machines.json` 等支持资产只用于官方跨表关联，不独立伪造实体事实。
- 成就、鞋类、大型可制作物和家具等旧格式需要按官方视觉规则建立图片来源、裁切矩形或 sprite 元数据；裁切越界、资源缺失和解析异常必须构成质量错误。
- 当前发布基线要求 `config.py` 中声明的官方实体类型齐全且有中文展示标签；任何缺失类型、无效翻译或数据错误都会阻断 `.svdata`。
- 手工覆盖只能修改允许的展示/搜索字段；必需图片元数据不能被覆盖以规避质量门禁，覆盖名称后必须重新计算翻译状态。
