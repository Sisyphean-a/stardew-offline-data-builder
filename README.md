# Stardew Offline Data Builder

面向用户本机《星露谷物语》安装目录的离线数据构建器。数据事实仅来自本机官方游戏资产，
生成可检索的 SQLite、图片资源、构建报告和 `.svdata` 数据包。

程序不会联网下载、上传或提交游戏资源，也不会修改游戏原始 `Content` 目录。

## 使用

```powershell
python -m builder doctor `
  --game-dir "D:\SteamLibrary\steamapps\common\Stardew Valley"

python -m builder build `
  --game-dir "D:\SteamLibrary\steamapps\common\Stardew Valley" `
  --output ".\dist"
```

默认读取 `<game-dir>/Content (unpacked)`。若目录不存在有效 JSON，则调用游戏目录中的
`StardewXnbHack`；也可通过 `--unpacked-dir` 指定已解包目录，通过 `--xnb-hack` 指定工具。

## 官方数据关联

构建器解析物品、作物、鱼类、村民、配方、任务、商店等官方资产，并对以下支持文件做跨表关联：

- `Data/Shops.json`：商品、价格、交换物和出售条件；
- `Data/Locations.json`：鱼类地点、季节、概率和钓鱼条件；
- `Data/FishPondData.json`：鱼塘产物、人口门槛和生成规则；
- `Data/Machines.json`：机器输入标签、产物和处理时间；
- 料理与制作配方：原料和物品用途反向索引。

直接字段保留在实体 `extra_json` 根层；标准化和跨表派生字段写入
`extra_json.officialDerived`。参与关联的官方文件记录在 `extra_json._provenance.official`。

官方资产没有结构化表达的攻略标签、自然语言事件摘要等内容不会被推测或伪造。

## 产物

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

`data/aliases.zh-CN.json` 和 `data/categories.zh-CN.json` 提供本地搜索增强；
`data/overrides.zh-CN.json` 可做显式字段修正，优先级高于官方解析结果。

## 验证

```powershell
python -m pytest
python -m ruff check .
```
