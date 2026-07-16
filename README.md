# Stardew Offline Data Builder

面向用户本机《星露谷物语》安装目录的离线数据构建器。它读取解包后的官方数据和本地化文本，
可选地以本地 `stardew-valley-data` 目录补充字段与校验匹配，生成可检索的 SQLite、图片资源、
构建报告和 `.svdata` 数据包。

不会联网下载、上传或提交游戏资源，也不会修改游戏原始 `Content` 目录。

## 使用

```powershell
python -m builder doctor `
  --game-dir "D:\SteamLibrary\steamapps\common\Stardew Valley"

python -m builder build `
  --game-dir "D:\SteamLibrary\steamapps\common\Stardew Valley" `
  --community-data "E:\github\stardew-valley-data-main\data" `
  --output ".\dist"
```

`--community-data` 是可选项；未传入时仅使用官方数据。默认读取
`<game-dir>/Content (unpacked)`，若不存在有效 JSON，则会调用本地的 `StardewXnbHack` 解包器。
也可通过 `--unpacked-dir` 指定已解包目录，通过 `--xnb-hack` 指定解包器路径。

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
    ├── unmatched.json
    ├── missing-translations.json
    └── errors.json
```

官方字段优先于社区补充，`data/overrides.zh-CN.json` 中的 `entity_overrides` 字段级修正优先级最高。
每个实体在 `extra_json._provenance` 中保留参与构建的数据来源文件。

## 验证

```powershell
python -m pytest
python -m ruff check .
```
