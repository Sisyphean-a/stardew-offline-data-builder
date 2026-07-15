# Stardew Offline Data Builder

## 1. 项目概述

开发一个《星露谷物语》离线数据生成器。

生成器从用户自己的正版 PC 游戏目录中读取游戏资源，提取官方简体中文名称和描述，并与社区结构化数据合并，最终生成供 Android 离线查询 App 使用的数据包。

项目不爬取 Wiki，不依赖在线服务器，不在仓库中保存或分发完整游戏资源。

项目名称：

```text
stardew-offline-data-builder
```

第一阶段仅开发 Windows 命令行版本，不开发图形界面，不开发 Android App。

---

## 2. 最终目标

用户执行一条命令：

```powershell
python -m builder build ^
  --game-dir "D:\SteamLibrary\steamapps\common\Stardew Valley" ^
  --output ".\dist"
```

程序自动完成：

```text
检查游戏目录
→ 解包游戏数据
→ 读取官方中英文文本
→ 读取社区结构化数据
→ 根据稳定 ID 合并数据
→ 生成中文搜索字段
→ 写入 SQLite
→ 输出 .svdata 数据包
```

最终生成：

```text
dist/
├── stardew-zh-cn.svdata
├── stardew.db
├── manifest.json
└── reports/
    ├── build-summary.json
    ├── unmatched.json
    ├── missing-translations.json
    └── errors.json
```

`.svdata` 本质上是 ZIP 文件，但使用自定义扩展名。

---

## 3. 当前 MVP 范围

第一版只处理以下四类数据：

1. 普通物品
2. 作物
3. 鱼类
4. NPC / 村民

第一版必须实现：

* 检查游戏目录是否有效；
* 检查 StardewXnbHack 是否存在；
* 支持读取测试夹具数据；
* 创建 SQLite 数据库；
* 写入中英文名称和描述；
* 生成拼音、拼音首字母和别名搜索字段；
* 输出构建报告；
* 数据缺失时继续构建，不允许整个程序直接崩溃。

第一版暂时不实现：

* 游戏图片提取；
* 礼物喜好；
* NPC 日程；
* 商店；
* 料理与制作配方；
* 怪物和掉落；
* 任务；
* 收集包；
* Wiki 攻略；
* 自动下载第三方工具；
* 图形界面；
* Android App。

---

## 4. 数据来源

### 4.1 官方游戏数据

从用户电脑中的正版《星露谷物语》游戏目录读取。

使用 StardewXnbHack 解包 `Content` 目录。

生成器不得修改原始游戏文件。

原始目录和解包目录必须分开：

```text
Stardew Valley/
├── Content/
└── Content (unpacked)/
```

生成器只能读取：

```text
Content (unpacked)/
```

不能直接修改：

```text
Content/
```

### 4.2 社区结构化数据

使用 `stardew-valley-data` 提供的原始 JSON 数据补充：

* 价格；
* 季节；
* 生长时间；
* 钓鱼时间；
* 钓鱼位置；
* 分类；
* 其他数值关系。

社区数据必须通过本地目录传入，第一版不自动联网下载。

示例：

```powershell
python -m builder build ^
  --game-dir "D:\Games\Stardew Valley" ^
  --community-data ".\vendor\stardew-valley-data\data" ^
  --output ".\dist"
```

### 4.3 人工修正规则

项目中保留少量人工维护文件：

```text
data/
├── aliases.zh-CN.json
├── overrides.zh-CN.json
└── categories.zh-CN.json
```

作用：

* 增加玩家常用别名；
* 修复自动匹配错误；
* 补充缺少的中文分类；
* 解决游戏 ID 与社区 ID 不一致的问题。

人工修正数据的优先级最高。

---

## 5. 技术栈

使用：

```text
Python 3.12
Typer
Rich
Pydantic
orjson
pypinyin
pytest
ruff
SQLite
```

要求：

* 使用 `pyproject.toml` 管理项目；
* 使用 Python 内置的 `sqlite3`；
* 不引入 ORM；
* 不引入 Web 框架；
* 不使用 Node.js 作为运行时；
* 不要求用户安装数据库软件；
* 所有文件统一使用 UTF-8；
* 所有路径使用 `pathlib.Path`；
* Windows 路径必须正确处理空格和中文。

---

## 6. 项目目录

```text
stardew-offline-data-builder/
├── PROJECT.md
├── README.md
├── pyproject.toml
├── .gitignore
│
├── src/
│   └── builder/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── config.py
│       ├── models.py
│       │
│       ├── commands/
│       │   ├── doctor.py
│       │   ├── unpack.py
│       │   ├── build.py
│       │   ├── inspect.py
│       │   └── package.py
│       │
│       ├── sources/
│       │   ├── game_source.py
│       │   ├── community_source.py
│       │   └── override_source.py
│       │
│       ├── parsers/
│       │   ├── objects.py
│       │   ├── crops.py
│       │   ├── fish.py
│       │   ├── villagers.py
│       │   └── localization.py
│       │
│       ├── pipeline/
│       │   ├── normalize.py
│       │   ├── match.py
│       │   ├── merge.py
│       │   ├── search_tokens.py
│       │   └── reports.py
│       │
│       ├── database/
│       │   ├── schema.sql
│       │   ├── writer.py
│       │   └── validator.py
│       │
│       └── utils/
│           ├── paths.py
│           ├── hashing.py
│           ├── json_io.py
│           └── subprocesses.py
│
├── data/
│   ├── aliases.zh-CN.json
│   ├── overrides.zh-CN.json
│   └── categories.zh-CN.json
│
├── tests/
│   ├── fixtures/
│   │   ├── game-data/
│   │   └── community-data/
│   ├── test_doctor.py
│   ├── test_normalize.py
│   ├── test_match.py
│   ├── test_database.py
│   └── test_build.py
│
├── vendor/
│   └── .gitkeep
│
├── build/
│   └── .gitkeep
│
└── dist/
    └── .gitkeep
```

---

## 7. CLI 设计

### 7.1 查看帮助

```powershell
python -m builder --help
```

### 7.2 环境检查

```powershell
python -m builder doctor
```

或者：

```powershell
python -m builder doctor --game-dir "D:\Games\Stardew Valley"
```

输出示例：

```text
✓ Python 环境正常
✓ 找到游戏目录
✓ 找到 Content 目录
✓ 找到 Stardew Valley.dll
✓ 找到 StardewXnbHack.exe
✓ 找到社区数据目录
✓ SQLite 支持 FTS4

环境检查通过
```

失败示例：

```text
✗ 未找到 StardewXnbHack.exe

请将 StardewXnbHack.exe 放到游戏目录，
或通过 --xnb-hack 指定文件路径。
```

### 7.3 解包游戏数据

```powershell
python -m builder unpack --game-dir "D:\Games\Stardew Valley"
```

规则：

* 如果已经存在有效的 `Content (unpacked)`，默认不重复解包；
* 使用 `--force` 时重新解包；
* 调用外部程序时必须捕获退出码、标准输出和标准错误；
* 不允许使用 `shell=True`；
* 解包失败时给出清晰错误信息。

### 7.4 构建数据库

```powershell
python -m builder build ^
  --game-dir "D:\Games\Stardew Valley" ^
  --community-data ".\vendor\stardew-valley-data\data" ^
  --output ".\dist"
```

可选参数：

```text
--unpacked-dir
--xnb-hack
--community-data
--output
--locale zh-CN
--force
--keep-temp
--verbose
```

### 7.5 检查数据库

```powershell
python -m builder inspect ".\dist\stardew.db"
```

输出：

```text
数据库版本：1
语言：zh-CN
实体总数：234
物品：100
作物：46
鱼类：54
村民：34
缺少中文：3
未匹配数据：7
FTS 搜索：正常
```

---

## 8. 数据处理流程

### 步骤一：环境验证

验证以下内容：

```text
游戏目录存在
Content 目录存在
Stardew Valley.dll 存在
StardewXnbHack 可执行文件存在
社区数据目录存在
输出目录可写
SQLite FTS4 可用
```

任何错误都必须返回：

* 错误代码；
* 中文说明；
* 建议解决方式。

### 步骤二：解包

运行：

```powershell
StardewXnbHack.exe --clean
```

程序不能假设解包后的文件结构永远不变。

必须使用文件发现机制寻找候选 JSON：

```text
递归扫描 JSON
→ 根据文件名和 JSON 结构判断类型
→ 记录发现结果
→ 将无法识别的文件写入报告
```

禁止只写死一个绝对文件路径。

### 步骤三：加载原始数据

每个数据源先转换成统一的中间模型：

```python
class RawEntity:
    source: str
    entity_type: str
    source_id: str
    internal_name: str | None
    name: str | None
    description: str | None
    locale: str | None
    attributes: dict
    source_file: str
```

解析器不能直接写数据库。

### 步骤四：标准化 ID

统一实体 ID 格式：

```text
object:24
crop:parsnip
fish:sturgeon
villager:Abigail
```

规则：

* 优先使用游戏内部稳定 ID；
* 没有数值 ID 时使用稳定内部名称；
* 不使用中文名称作为唯一 ID；
* 不使用数据库自增 ID 作为跨版本标识；
* ID 必须区分大小写规则并统一处理。

### 步骤五：合并

合并优先级：

```text
人工 overrides
    ↓
官方游戏中文数据
    ↓
官方游戏英文数据
    ↓
社区结构化数据
```

名称和描述：

```text
name_zh：优先官方简体中文
name_en：优先官方英文
description_zh：优先官方简体中文
description_en：优先官方英文
```

数值属性：

```text
优先官方游戏数据
缺少时使用社区数据
```

匹配优先级：

```text
稳定游戏 ID
→ 内部名称完全匹配
→ 英文名称标准化后完全匹配
→ 人工映射
```

禁止自动使用模糊匹配合并实体。

模糊匹配只能生成建议报告，不能直接写入正式数据库。

### 步骤六：缺失数据处理

中文缺失时：

```text
name_zh = name_en
translation_status = "missing"
```

数据不匹配时：

* 不终止整个构建；
* 保存仍然可信的数据；
* 写入 `unmatched.json`；
* 在最终摘要中显示数量。

### 步骤七：搜索字段生成

每个实体生成：

```text
name_zh
name_en
pinyin
pinyin_initials
aliases
keywords
search_text
```

示例：

```json
{
  "name_zh": "防风草",
  "name_en": "Parsnip",
  "pinyin": "fang feng cao",
  "pinyin_initials": "ffc",
  "aliases": ["萝卜", "春季作物"],
  "search_text": "防风草 parsnip fang feng cao ffc 萝卜 春季作物"
}
```

搜索字段在电脑端提前生成。

手机端不进行拼音转换和中文分词。

---

## 9. SQLite 数据库设计

第一版使用通用实体模型，不为每种数据建立复杂表。

### 9.1 `build_meta`

```sql
CREATE TABLE build_meta (
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL
);
```

保存：

```text
schema_version
builder_version
game_version
locale
generated_at
community_data_version
source_hash
```

### 9.2 `entities`

```sql
CREATE TABLE entities (
    id TEXT PRIMARY KEY NOT NULL,
    entity_type TEXT NOT NULL,
    game_id TEXT,
    internal_name TEXT,

    name_zh TEXT NOT NULL,
    name_en TEXT,
    description_zh TEXT,
    description_en TEXT,

    category TEXT,
    translation_status TEXT NOT NULL DEFAULT 'complete',

    image_path TEXT,
    extra_json TEXT NOT NULL DEFAULT '{}',

    source_file TEXT,
    created_at TEXT NOT NULL
);
```

索引：

```sql
CREATE INDEX index_entities_type
ON entities(entity_type);

CREATE INDEX index_entities_name_zh
ON entities(name_zh);

CREATE INDEX index_entities_game_id
ON entities(game_id);
```

### 9.3 `entity_aliases`

```sql
CREATE TABLE entity_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id TEXT NOT NULL,
    alias TEXT NOT NULL,
    alias_type TEXT NOT NULL,
    FOREIGN KEY(entity_id) REFERENCES entities(id)
);
```

### 9.4 `entity_search`

使用 FTS4：

```sql
CREATE VIRTUAL TABLE entity_search USING fts4(
    entity_id,
    name_zh,
    name_en,
    pinyin,
    pinyin_initials,
    aliases,
    keywords,
    search_text
);
```

不使用数据库触发器自动同步。

由生成器在构建阶段一次性写入搜索表。

---

## 10. 数据包格式

`manifest.json`：

```json
{
  "format": "stardew-offline-data",
  "schemaVersion": 1,
  "builderVersion": "0.1.0",
  "gameVersion": "unknown",
  "language": "zh-CN",
  "generatedAt": "2026-07-15T00:00:00Z",
  "database": {
    "file": "stardew.db",
    "sha256": ""
  },
  "content": {
    "entities": 0,
    "objects": 0,
    "crops": 0,
    "fish": 0,
    "villagers": 0,
    "missingTranslations": 0
  }
}
```

打包结构：

```text
stardew-zh-cn.svdata
├── manifest.json
├── stardew.db
└── reports/
    └── build-summary.json
```

图片功能完成前，不创建空的 `images` 目录。

---

## 11. 构建报告

### `build-summary.json`

```json
{
  "success": true,
  "counts": {
    "entities": 234,
    "objects": 100,
    "crops": 46,
    "fish": 54,
    "villagers": 34
  },
  "warnings": {
    "missingTranslations": 3,
    "unmatched": 7,
    "duplicateIds": 0
  }
}
```

### `unmatched.json`

保存：

* 来源文件；
* 来源 ID；
* 名称；
* 尝试过的匹配方式；
* 候选结果；
* 未匹配原因。

### `missing-translations.json`

保存缺少简体中文的实体。

### `errors.json`

只保存单条数据处理错误。

严重环境错误不写入这里，而是直接让命令失败并返回非零退出码。

---

## 12. 错误处理

定义错误类型：

```text
ConfigurationError
GameDirectoryError
UnpackerNotFoundError
UnpackError
SourceDataError
SchemaError
DatabaseBuildError
PackageError
```

CLI 退出码：

```text
0  成功
1  未知错误
2  参数或配置错误
3  游戏目录错误
4  解包工具错误
5  数据解析错误
6  数据库生成错误
7  打包错误
```

用户界面显示简短中文错误。

详细堆栈只在 `--verbose` 模式显示。

---

## 13. 安全与版权规则

必须遵守：

1. 不将原始游戏数据提交到 Git 仓库；
2. 不将解包后的游戏文本或图片提交到仓库；
3. 不自动上传用户数据；
4. 不访问 Wiki；
5. 不修改游戏文件；
6. 不把用户游戏目录写死在配置中；
7. 日志中不能记录用户名等不必要的完整路径；
8. `build/`、`dist/`、`Content (unpacked)/` 必须加入 `.gitignore`；
9. 第三方数据必须保留来源和许可证信息；
10. 数据包默认面向用户个人使用。

---

## 14. 测试要求

测试不能依赖用户真实安装游戏。

必须提供最小测试夹具：

```text
tests/fixtures/game-data/
tests/fixtures/community-data/
```

夹具使用自行编写的虚构数据，不复制完整游戏文本。

必须测试：

* 中文路径；
* 含空格路径；
* 缺少游戏目录；
* 缺少解包工具；
* JSON 格式错误；
* 重复实体 ID；
* 中文翻译缺失；
* 社区数据无法匹配；
* SQLite 数据写入；
* FTS 搜索；
* 重复执行构建；
* 输出文件哈希；
* 构建失败时不留下半成品数据库。

数据库必须使用临时文件构建：

```text
stardew.db.tmp
```

全部成功后再重命名：

```text
stardew.db
```

---

## 15. 性能要求

第一版目标：

```text
不含解包时间的构建时间：10 秒以内
数据库体积：20 MB 以内
测试数据构建：2 秒以内
内存峰值：300 MB 以内
```

不需要过早进行极端优化。

优先保证：

```text
数据正确
→ 构建结果可重复
→ 错误可诊断
→ 性能
```

---

## 16. 开发阶段

### 阶段 0：初始化项目

只完成：

* 创建目录结构；
* 创建 `pyproject.toml`；
* 配置 Ruff；
* 配置 pytest；
* 创建 Typer CLI；
* 实现 `python -m builder --help`；
* 编写 `.gitignore`；
* 编写最小 README；
* 所有测试通过。

验收命令：

```powershell
python -m builder --help
pytest
ruff check .
```

### 阶段 1：最小数据库闭环

只使用测试夹具，不读取真实游戏。

完成：

```text
读取 fixtures JSON
→ 转换成 RawEntity
→ 标准化实体
→ 生成拼音搜索字段
→ 创建 stardew.db
→ 写入 entities
→ 写入 entity_search
→ 执行搜索验证
```

验收命令：

```powershell
python -m builder build-fixture --output ".\dist"
python -m builder inspect ".\dist\stardew.db"
pytest
```

必须能够搜索：

```text
防风草
parsnip
fang feng cao
ffc
```

四种关键词必须返回同一条测试数据。

### 阶段 2：环境检查

实现：

* `doctor`；
* 游戏目录验证；
* StardewXnbHack 验证；
* 社区数据目录验证；
* FTS4 验证。

此阶段不调用解包工具。

### 阶段 3：调用 StardewXnbHack

实现：

* `unpack` 命令；
* 捕获外部进程日志；
* 检查解包结果；
* 支持跳过已有结果；
* 支持 `--force`。

### 阶段 4：解析官方中文

先只解析普通物品。

跑通后依次加入：

```text
作物
→ 鱼类
→ 村民
```

每增加一种类型，都必须先添加测试再添加解析器。

### 阶段 5：合并社区数据

实现稳定 ID 匹配和人工映射。

禁止自动模糊合并。

### 阶段 6：生成 `.svdata`

实现：

* manifest；
* SHA-256；
* ZIP 打包；
* 包结构验证；
* 重复构建结果一致性检查。

### 阶段 7：扩展完整数据

依次添加：

```text
村民礼物
NPC 日程
料理
制作配方
商店
任务
收集包
怪物
掉落
矿物
武器
戒指
成就
特殊订单
姜岛数据
```

### 阶段 8：图片

最后才实现图片：

* 从用户游戏目录提取；
* 拆分精灵图；
* 去除多余透明边缘；
* 生成缩略图；
* 转换为无损 WebP；
* 写入 `image_path`。

---

## 17. AI 编码规则

AI 必须遵守：

1. 每次只实现当前指定阶段；
2. 不提前开发后续阶段；
3. 修改前先阅读本文件；
4. 不改变已确定的技术栈；
5. 不添加 GUI；
6. 不添加 Web 服务；
7. 不添加 ORM；
8. 不自动联网下载文件；
9. 不复制 Wiki 数据；
10. 不把真实游戏资源提交到仓库；
11. 每个功能必须有测试；
12. 完成后运行测试和静态检查；
13. 不隐藏错误；
14. 不为了“代码优雅”过度抽象；
15. 公共接口需要类型注解；
16. 数据源解析与数据库写入必须解耦；
17. 任何猜测出的数据字段都必须标记，不得伪装成已确认事实；
18. 遇到真实游戏文件结构不确定时，先添加诊断输出，不要凭空写死路径。

---

## 18. 完成标准

数据生成器完成时，必须满足：

* 用户无需手工翻译官方名称；
* 用户无需访问 Wiki；
* 用户无需安装数据库；
* 用户只需提供自己的游戏目录；
* 数据缺失不会导致整个构建失败；
* 每条数据都能追踪来源；
* 中文、英文、拼音和首字母均可搜索；
* 数据库能直接被 Android App 导入；
* 游戏更新后可以重新生成数据包；
* 用户收藏和个人备注不存放在数据包中；
* App 数据与用户个人数据完全分离。
