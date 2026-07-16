# Stardew Offline Data Builder

## 1. 项目定位

本项目是 Windows 命令行离线数据生成器。它读取用户本机《星露谷物语》官方资产，生成供离线
应用消费的 SQLite 数据库、图片、报告和 `.svdata` 包。

核心原则：

- 游戏事实只来自本机官方资产；
- 不联网，不下载数据，不上传或提交游戏资源；
- 不修改原始 `Content`；
- 解析失败、未知资产和缺失资源必须通过退出码或报告显式暴露；
- 不以硬编码快照、模拟数据或静默回退替代官方输入。

## 2. 输入

### 2.1 游戏目录

必需参数：

```text
--game-dir <Stardew Valley 安装目录>
```

目录必须包含：

- `Content/`
- `Stardew Valley.dll`

### 2.2 解包目录

默认使用：

```text
<game-dir>/Content (unpacked)/
```

可以通过 `--unpacked-dir` 指定其他目录。若默认目录不存在有效 JSON，构建器调用本地
`StardewXnbHack`。工具路径可通过 `--xnb-hack` 指定。

### 2.3 项目配置

- `data/aliases.zh-CN.json`：搜索别名；
- `data/categories.zh-CN.json`：展示分类和搜索关键词；
- `data/overrides.zh-CN.json`：显式人工字段修正。

这些文件只做本地规范化与修正，不作为游戏事实主数据源。

## 3. 官方资产范围

### 3.1 实体资产

当前支持：

- 物品、作物、鱼类、村民；
- 大型制造物、家具、鞋、工具、饰品；
- 矿物、戒指、武器、怪物、掉落；
- 料理、制作配方、裁缝规则；
- 商店、任务、特殊订单、收集包、成就；
- NPC 日程、礼物偏好、姜岛事件。

### 3.2 本地化

英文结构数据与 `Strings/*.json`、`Strings/*.zh-CN.json` 联合解析。可展示实体必须优先使用
官方中文；技术记录标记为 `not_applicable`，真实缺失标记为 `missing`。

### 3.3 支持资产

以下文件不独立生成实体，而是在标准化后参与关联：

| 文件 | 作用 |
|---|---|
| `Data/Shops.json` | 商品、价格、交换物、库存和条件 |
| `Data/Locations.json` | 鱼类地点、季节、概率和钓鱼条件 |
| `Data/FishPondData.json` | 鱼塘规则、产物和人口门槛 |
| `Data/Machines.json` | 机器输入、输出和处理时间 |

料理与制作配方还会生成原料到配方的反向用途索引。

## 4. 数据流程

```text
验证环境
  -> 复用或生成官方解包目录
  -> 发现并解析官方实体资产
  -> 解析官方本地化
  -> 稳定 ID 标准化
  -> 官方支持资产跨表关联
  -> 本地别名、分类和显式 override
  -> 官方图片裁切与 WebP 转换
  -> SQLite + 报告 + manifest
  -> .svdata 打包
```

实体稳定 ID：

```text
<entity_type>:<official source id>
```

示例：

```text
object:24
crop:24
fish:128
villager:Abigail
```

## 5. 字段规则

`entities` 的核心列保存稳定查询字段：

- `id`
- `entity_type`
- `game_id`
- `internal_name`
- `name_zh` / `name_en`
- `description_zh` / `description_en`
- `category`
- `translation_status`
- `image_path`
- `extra_json`
- `source_file`

官方原始字段保留在 `extra_json` 根层。统一命名和跨表关联结果写入
`extra_json.officialDerived`，包括：

- 作物季节、成长阶段、种子 ID、商店报价；
- 鱼类难度、时间、季节、天气、地点、鱼塘和机器用途；
- NPC 生日、地区、性别和婚恋属性；
- 物品售价、可食用值、上下文标签、商店和机器用途；
- 配方原料、产物和反向用途。

来源写入：

```json
{
  "_provenance": {
    "official": [
      "Data/Objects.json",
      "Data/Shops.json"
    ]
  }
}
```

官方没有结构化等价物的事件摘要、攻略说明和主观分类不进入产物。

## 6. SQLite

主要表：

- `build_meta`：schema、builder、游戏版本、语言、生成时间、实体数、输入哈希；
- `entities`：实体核心字段和 JSON 扩展；
- `entity_aliases`：本地搜索别名；
- `entity_search`：FTS4 搜索文档。

搜索覆盖中文、英文、拼音、拼音首字母、别名和关键词。

当前 schema version：`2`。

## 7. CLI

```powershell
python -m builder doctor --game-dir <path>
python -m builder unpack --game-dir <path>
python -m builder build --game-dir <path> --output .\dist
python -m builder inspect .\dist\stardew.db
python -m builder package --output .\dist
```

退出码：

| 代码 | 含义 |
|---:|---|
| 0 | 成功 |
| 1 | 未知错误 |
| 2 | 配置错误 |
| 3 | 游戏目录错误 |
| 4 | 解包工具错误 |
| 5 | 官方源数据错误 |
| 6 | 数据库错误 |
| 7 | 打包错误 |

## 8. 输出

```text
dist/
├── stardew.db
├── manifest.json
├── stardew-zh-cn.svdata
├── images/
└── reports/
    ├── build-summary.json
    ├── coverage.json
    ├── source-discovery.json
    ├── missing-translations.json
    └── errors.json
```

报告必须显示实体覆盖、本地化状态、无法识别的官方文件、图片缺失和解析错误。

## 9. 数据包

`.svdata` 是 ZIP 格式，包含数据库、manifest、全部报告和实际生成的图片。相同输入与固定生成
时间必须得到一致的数据库、manifest 和数据包哈希。

## 10. 质量要求

- 函数不超过 50 行；
- 文件不超过 300 行；
- 嵌套不超过 3 层；
- 业务依赖通过参数传递；
- 不修改输入对象；
- 外部 JSON 必须做根结构校验；
- SQLite 写入使用参数化语句和临时文件原子替换；
- 后端测试 60 秒内完成；
- `pytest` 与 `ruff check .` 必须通过。

## 11. 完成标准

1. 只提供有效游戏目录即可完成构建；
2. 主要实体和扩展类型均非空；
3. 官方中文、英文、图片和搜索可用；
4. 支持资产产生可追溯的官方派生字段；
5. SQLite integrity check 为 `ok`；
6. manifest 哈希与数据库一致；
7. `.svdata` 内容完整；
8. 错误和未知资产没有被隐藏；
9. 自动化检查和真实游戏黑盒构建通过。
