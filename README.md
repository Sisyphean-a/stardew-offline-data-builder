# Stardew Offline Data Builder

面向用户本机《星露谷物语》安装目录的离线数据构建器。数据事实仅来自本机官方游戏资产，
生成可检索的 SQLite、图片资源、构建报告和 `.svdata` 数据包。

程序不会联网下载、上传或提交游戏资源，也不会修改游戏原始 `Content` 目录。

## 使用

在 Windows 上，`build`、`unpack` 和 `doctor` 省略 `--game-dir` 时会从本机 Steam 注册表与
已配置库中查找唯一有效的《星露谷物语》安装。找到多个或未找到时会显式报错，请传入
`--game-dir` 指定目录；显式路径始终优先。

```powershell
python -m builder doctor

python -m builder build `
  --output ".\dist"
```

`build` 生成正式 manifest 2 / schema 5 / `player-facts-v1` 候选，并在类型化事实、来源证据、视觉、外键和覆盖门禁未通过时保留失败诊断而不替换旧输出。旧 schema 4 只能通过显式的 `build-v4-legacy` 生成迁移基线，不能作为新版 App 的普通数据包。

多安装、非 Steam 安装或自动发现失败时，三个命令都可显式指定正版游戏目录：

```powershell
python -m builder unpack `
  --game-dir "D:\SteamLibrary\steamapps\common\Stardew Valley"
```

默认读取 `<game-dir>/Content (unpacked)`。若目录不存在有效 JSON，则调用游戏目录中的
`StardewXnbHack`；也可通过 `--unpacked-dir` 指定已解包目录，通过 `--xnb-hack` 指定工具。
候选输出中的 SQLite 只包含类型化实体、事实槽/事实项、条件、来源定位、证据、关系、视觉、卡片、facet 和 FTS 表，不把 `officialDerived` 作为 App 读取源。

## 官方数据关联

构建器解析物品、作物、鱼类、村民、配方、任务、商店等官方资产，并对以下支持文件做跨表关联：

- `Data/Shops.json`：商品、价格、交换物和出售条件；
- `Data/Locations.json`：鱼类地点、季节、概率和钓鱼条件；
- `Data/FishPondData.json`：鱼塘产物、人口门槛和生成规则；
- `Data/Machines.json`：机器输入标签、产物和处理时间；
- 料理与制作配方：原料和物品用途反向索引。

schema 5 构建阶段从解析后的结构化官方属性和支持文件投影 typed facts；每条事实保留来源定位、条件和派生转换证据。schema 4 的 `extra_json.officialDerived` 只留在显式迁移基线/legacy builder 路径，不是新版 App 的数据源。

官方资产没有结构化表达的攻略标签、自然语言事件摘要等内容不会被推测或伪造；无法确认的核心问题写成带证据的 `unknown` 或 `not_collected`，而不是猜测固定值。

### 补充来源（supplemental）

官方数据明确缺失、但对玩家有确定价值的内容，可以人工核对后以 `supplemental`
来源进入数据包，并保留版本、URL 与审核信息，与官方事实在来源类别上严格区分。
当前补充事实：

- **怪物矿井层段**（`floors`）：来源为星露谷官方中文维基的矿井楼层表，
  覆盖普通矿井有明确楼层说明的怪物；农场荒野、火山地牢等没有矿井楼层
  语义的怪物不生成该事实。

`build` 输出的 SQLite 同时包含任务（类型/目标/奖励/可重复）、成就（解锁条件/
隐藏）、收集包（区域/所需物品）、特殊订单（委托人/时限/目标）与商店（性质分类、
店主、商品数）的类型化事实，商店列表按性质排序（普通商店在前、节日商店在后）。

## 产物

```text
dist/
├── stardew.db
├── manifest.json
├── stardew-zh-cn.svdata
├── schema5-conformance.json
├── images/
└── reports/
    ├── build-summary.json
    ├── coverage.json
    ├── source-discovery.json
    ├── missing-translations.json
    └── errors.json
```

`data/aliases.zh-CN.json` 和 `data/categories.zh-CN.json` 提供本地搜索增强；
`data/overrides.zh-CN.json` 可做显式字段修正，优先级高于官方解析结果。

## 验证

```powershell
python -m pytest
python -m ruff check .
```
