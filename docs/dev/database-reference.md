---
doc_type: dev-guide
slug: database-reference
component: offline-data-package
status: draft
summary: 面向移动端离线 Wiki 的 Stardew 数据包、SQLite 模式与实体字段使用参考。
tags: [sqlite, mobile, wiki, offline-data]
last_reviewed: 2026-07-18
---

# 离线 Wiki 数据库使用参考

本文面向把本项目构建产物内嵌到手机端 Wiki 的开发者。它描述当前 `schema_version = 4` 的数据包、SQLite 表、稳定 JSON 字段、查询方式和升级规则。

## 先读这一节：消费边界

- 应用只读消费 `stardew.db`；不要在原库中写用户收藏、历史或笔记。它们应放在应用自己的数据库，以 `entities.id` 作外键值。
- `entities` 是唯一的业务主表。`entity_aliases` 和 `entity_search` 是它的搜索辅助表；`build_meta` 是版本与完整性元数据。
- `extra_json` 中只有 `officialDerived`、`_provenance` 及本节明示的构建器补充字段可作为移动端的结构化接口。其余根字段是原样保留的官方资产，可能随游戏版本增删或改变嵌套形状。
- 可空字段、缺失 JSON 属性和空数组都表示“官方数据未提供”，不表示 `false`、`0` 或“永不发生”。不要自行补默认游戏规则。
- 只启用 `publishable = true` 且 `quality.status = "passed"` 的数据包；fixture 及质量失败产物不能作为用户数据导入。
- 稳定 ID 是 `<entity_type>:<official-source-id>`，例如 `object:24`、`crop:24`、`fish:128`、`villager:Abigail`。`object:24` 与 `crop:24` 是两个不同实体，不能只按数字 ID 关联。

## 数据包与内嵌流程

构建输出目录和 `.svdata` 包的结构相同；`.svdata` 是 ZIP，包含数据库、图片、manifest 和报告。

```text
stardew-zh-cn.svdata
├── manifest.json
├── stardew.db
├── images/<entity-type>-<source-id>.webp
└── reports/*.json
```

建议应用首次安装或更新数据时执行：

1. 解压整个包到应用数据目录的临时位置。
2. 读取 `manifest.json`，要求 `format = "stardew-offline-data"`、`publishable = true`、`quality.status = "passed"`，并只接受应用已支持的 `schemaVersion`。
3. 计算 `database.sha256`，必须等于 `stardew.db` 的 SHA-256；再执行 `PRAGMA quick_check`，结果必须为 `ok`。
4. 读取 `build_meta.schema_version` 和 `build_meta.artifact_metadata`；前者必须与 manifest 的 `schemaVersion` 一致，后者中的版本、语言、内容和质量必须与 manifest 对应字段一致。
5. 成功后以目录级原子替换启用新包。图片路径相对于数据包根目录：`images/object-24.webp`。

不要逐行合并新旧库：构建器会原子替换整个数据库，数据包才是可升级的最小单位。

### manifest.json

| 路径 | 类型 | 含义与用法 |
|---|---|---|
| `format` | string | 固定为 `stardew-offline-data`；用于识别包格式。 |
| `schemaVersion` | integer | SQLite 消费契约版本。版本不支持时停止导入，不要猜测字段。 |
| `builderVersion` | string | 构建器版本；用于诊断，不用于迁移判断。 |
| `gameVersion` | string | 源游戏版本；适合在应用“数据版本”页展示。 |
| `language` | string | 当前为 `zh-CN`；决定主要展示列语言。 |
| `generatedAt` | ISO 8601 string | 此包生成时间（UTC）。 |
| `sourceHash` | string | 官方解包 JSON 与本地配置的 SHA-256 汇总值；用于诊断输入变化。 |
| `publishable` | boolean | 仅 `true` 的包可被消费；fixture 为 `false`，必须拒绝导入。 |
| `database.file` | string | 数据库文件名，目前为 `stardew.db`。 |
| `database.sha256` | string | 数据库完整性校验值。 |
| `content.entities` | integer | 实体总数；可用于导入后交叉检查。 |
| `content.objects/crops/fish/villagers` | integer | 四类基础实体的数量。 |
| `content.extraCounts` | object | 其他实体类型到数量的映射。 |
| `content.missingTranslations` | integer | `translation_status = 'missing'` 的数量。 |
| `content.entityTypes` | object[] | 全部实际实体类型的 `id`、中文 `displayName` 与 `count`。 |
| `quality.status` | string | `passed` 或 `failed`；只有 `passed` 的包可导入。 |
| `quality.translations` | object | `complete`、`missing`、`invalid`、`notApplicable`、`unusable` 的计数。 |
| `quality.dataErrors` | integer | 构建数据错误数；可发布包必须为 0。 |

## SQLite 总览

| 表 | 用途 | 写入关系 | 移动端建议 |
|---|---|---|---|
| `build_meta` | 数据库级元数据 | 每次构建写 8 项 | 打开库时读取版本、语言、质量与发布资格。 |
| `entities` | 所有可展示或可关联的游戏实体 | 一行一个稳定 ID | 所有详情页、列表页的主查询表。 |
| `entity_aliases` | 本地配置提供的别名 | `entity_id → entities.id` | 展示别名或做精确补充搜索。 |
| `entity_search` | FTS4 全文搜索文档 | 与实体一一写入 | 搜索入口；命中后回连 `entities`。 |

数据库创建了 `entities(entity_type)`、`entities(name_zh)` 与 `entities(game_id)` 索引。`entity_search` 是 FTS4 虚拟表，不应按普通 B-tree 索引假设其实现。

### build_meta

键和值均为 `TEXT`。当前构建器固定写入以下所有键：

| key | value 的含义 |
|---|---|
| `schema_version` | 数据库模式版本，当前为 `4`。 |
| `builder_version` | 生成此库的构建器版本。 |
| `locale` | 数据语言，当前构建命令写入 `zh-CN`。 |
| `generated_at` | 生成时间，ISO 8601 UTC。 |
| `entity_count` | `entities` 总行数的字符串形式。 |
| `game_version` | 检测到的游戏版本；检测不到时为 `unknown`。 |
| `source_hash` | 解包 JSON 与本地别名、分类、覆盖配置的 SHA-256 汇总值；用于判断输入是否变化。 |
| `artifact_metadata` | JSON 对象；发布契约的权威副本，含 schema、语言、生成时间、源哈希、`publishable`、内容统计和质量状态。 |

### entities：标准列

| 列 | SQLite 类型 / 可空 | 含义与移动端用法 |
|---|---|---|
| `id` | `TEXT`，主键，非空 | 跨表关联、路由、收藏的唯一键。格式见本文开头。 |
| `entity_type` | `TEXT`，非空 | 类型筛选与详情渲染分派键。支持值见“实体类型”。 |
| `game_id` | `TEXT`，可空 | 官方源 ID；仅在同类实体内有意义。 |
| `internal_name` | `TEXT`，可空 | 官方内部名称；可用于调试或英文检索，不应作为主键。 |
| `name_zh` | `TEXT`，非空 | 主展示名。可发布包中所有要求翻译的实体都不能处于 `missing` 或 `invalid` 状态；不要把回退文本当作已完成中文翻译。 |
| `name_en` | `TEXT`，可空 | 英文展示名。 |
| `description_zh` | `TEXT`，可空 | 中文描述；优先中文，必要时回退英文。 |
| `description_en` | `TEXT`，可空 | 英文描述。 |
| `category` | `TEXT`，可空 | 本地 `categories.zh-CN.json` 提供的展示分类；不是官方分类。 |
| `translation_status` | `TEXT`，非空 | `complete`：可展示中文名；`missing`：应翻译但缺失；`invalid`：名称为空白或纯数字等不可展示值；`not_applicable`：技术记录等无需翻译。可发布包的 `missing` 和 `invalid` 均为 0。 |
| `image_path` | `TEXT`，可空 | 包根目录相对的 WebP 路径。非空路径在可发布包中一定有对应文件；空值表示没有物化图片或图片不适用，应用可显示本地占位图，但不要从 `imageSource` 现场裁图。 |
| `extra_json` | `TEXT`，非空 | UTF-8 JSON 对象；类型专属详情、派生关系与来源追踪。 |
| `source_file` | `TEXT`，可空 | 产生该实体的官方资产相对路径，例如 `Data/Objects.json`。 |
| `created_at` | `TEXT`，非空 | 写入此库的时间，ISO 8601 UTC；同一次构建的实体相同。 |

### entity_aliases 与 entity_search

| 表.列 | 类型 | 含义 |
|---|---|---|
| `entity_aliases.id` | `INTEGER` | 自增技术主键；不要跨数据包持久化它。 |
| `entity_aliases.entity_id` | `TEXT` | 指向 `entities.id`。 |
| `entity_aliases.alias` | `TEXT` | 本地人工搜索别名。 |
| `entity_aliases.alias_type` | `TEXT` | 当前构建器只写 `manual`。 |
| `entity_search.entity_id` | TEXT | 对应实体 ID；用于 JOIN。 |
| `name_zh` / `name_en` | TEXT | 搜索文档中的中英文名副本。 |
| `pinyin` | TEXT | `name_zh` 的空格分隔拼音。 |
| `pinyin_initials` | TEXT | 每个拼音音节的首字母，例如 `防风草 → ffc`。 |
| `aliases` / `keywords` | TEXT | 以空格连接的别名和分类关键词。 |
| `search_text` | TEXT | 前述全部检索文本的连接值；一般无需单独展示。 |

## 类型与 extra_json 的稳定使用方式

`extra_json` 解析后分三层：根层官方原始记录、构建器补充元数据、`officialDerived` 规范化派生数据。详情页应先使用标准列，再使用该类型的 `officialDerived`；根层仅在需要展示未规范化官方信息时按字段存在性读取。

所有类型都可能有：`_provenance.official`（参与生成的官方文件路径数组）。映像相关补充字段为 `imageSource`（原始 PNG 来源）、`imageFallbackSources`（备用图路径）、`imageRect`（显式裁切矩形）、`spriteIndex`（图集格索引）、`imageGridCellSize`、`imageSize`、`imageMode`、`imageRequired` 和 `imageAvailability`（例如 `not_applicable`）。它们仅用于构建追溯，不是移动端图片入口。

| `entity_type` | 说明 | 推荐详情字段 |
|---|---|---|
| `object` / `mineral` / `ring` | 普通物品及其按 `Type` 派生的矿物、戒指实体 | `sellPrice`、`edibility`、`contextTags`、商店/机器/配方关系。 |
| `crop` | 作物记录；与种子物品分离 | 季节、成长、再生、收获、种子商店。 |
| `fish` | 鱼类 | 难度、尺寸、时段、天气、地点、鱼塘、机器用途。 |
| `villager` | 村民/NPC 角色 | 生日、居住区域、性别、可婚配与恋人。 |
| `cooking_recipe` / `crafting_recipe` | 旧式斜杠配方 | 原料、产物 ID、产物类型。 |
| `big_craftable` / `furniture` / `footwear` / `tool` / `trinket` / `weapon` | 可展示物件、装备或工具 | 原始属性；有匹配时展示 `shopOffers`，部分有 `usedIn`。 |
| `bundle` / `quest` / `special_order` / `shop` / `tailoring_recipe` | 任务、收集包、订单、商店、裁缝规则 | 原始官方对象；按存在性渲染。 |
| `monster` / `drop` | 怪物和从旧怪物记录拆出的掉落 | `drop` 使用 `monsterId`、`itemId`、`chance`。 |
| `achievement` / `ginger_island` / `npc_schedule` / `villager_gift` | 旧式游戏记录 | 仅作为原始记录展示，避免按位置解释。 |

### officialDerived：字段完整参考

属性只在构建器成功得到值时出现。所有 ID 都是源 ID；用“关联 ID”查询时必须尝试合格 ID 和可兼容的实体类型，不能直接假定 `object:` 前缀。

| 适用类型 | 路径 | 类型 | 含义 |
|---|---|---|---|
| `crop` | `seedItemId` / `harvestItemId` | string | 种子物品 / 收获物品的官方 ID。 |
| `crop` | `seasons` | string[] | 小写季节名，如 `spring`。 |
| `crop` | `growDays` | integer | `growthPhases` 总和。 |
| `crop` | `growthPhases` | integer[] | 各成长阶段天数。 |
| `crop` | `regrowDays` | integer | 再生作物每次再生天数；不再生时属性缺失。 |
| `crop` | `needsWatering` / `isPaddyCrop` / `isTrellisCrop` | boolean | 浇水要求 / 水稻作物 / 需棚架。 |
| `crop` | `harvestMin` / `harvestMax` | integer | 一次收获数量的官方最小/最大堆叠数。 |
| `fish` | `difficulty` | integer | 钓鱼难度。 |
| `fish` | `behavior` | string | 官方鱼类行为代号。 |
| `fish` | `minSize` / `maxSize` | integer | 可钓尺寸范围。 |
| `fish` | `timeWindows` | integer[] | 旧式记录解析出的小时边界数组；按相邻成对的开始/结束时段消费。 |
| `fish` | `seasons` | string[] | 可出现季节，小写。 |
| `fish` | `weather` | string | 官方天气条件文本。 |
| `villager` | `birthday.season` / `birthday.day` | string / integer | 小写出生季节和日期；没有季节时仅可能有 `day: 0`。 |
| `villager` | `homeRegion` / `gender` / `loveInterest` | string | 官方居住区域、性别、恋爱对象 ID。 |
| `villager` | `canBeRomanced` | boolean | 是否可婚配。 |
| 配方 | `ingredients[]` | object[] | 原料项：`itemId`（官方 ID）、`quantity`（数量）。 |
| 配方 | `outputItemId` / `outputEntityType` | string | 产物 ID 与产物类型（当前为 `object` 或 `big_craftable`）。 |
| `object` / `mineral` / `ring` | `sellPrice` / `edibility` | integer | 官方售价与食用值；食用值的游戏效果仍由官方规则决定。 |
| `object` / `mineral` / `ring` | `contextTags` | string[] | 官方上下文标签；用于展示或本地筛选，不要把标签当自然语言。 |
| 所有可关联物品 | `shopOffers[]` | object[] | 可购买来源，结构见下一表。 |
| 可作机器输入的物品 | `machineUses[]` | object[] | 机器输入规则，结构见下一表。 |
| 原料、收集包项 | `usedIn[]` | object[] | 反向用途（哪些配方/收集包需要它），结构见下一表。 |
| `crop` | `seedShopOffers[]` | object[] | `seedItemId` 对应种子的购买来源；结构同 `shopOffers`。 |
| `fish` | `locations[]` | object[] | 鱼类地点规则，结构见下一表。 |
| `fish` | `fishPondRules[]` | object[] | 鱼塘规则，结构见下一表。 |

### 关系对象

所有关系对象都有 `_source`：提供该关系的官方资产文件；`condition`、`perItemCondition` 和标签是官方条件表达式或代号，构建器不求值，应用应原样展示或明确标注“不支持自动判定”。

| 对象 | 字段 | 含义 |
|---|---|---|
| `shopOffers[]` | `shopId`, `offerId`, `currency`, `itemId`, `randomItemIds`, `price` | 商店、报价、货币、固定/随机物品和价格。 |
|  | `shopPriceModifiers`, `priceModifiers`, `tradeItemId`, `tradeItemAmount` | 商店/商品价格修正与以物易物要求。 |
|  | `availableStock`, `availableStockLimit`, `availableStockModifiers`, `availableStockModifierMode`, `maxItems` | 库存及库存修正规则。`-1` 等数值保持官方语义，不要改写为零。 |
|  | `minStack`, `maxStack`, `quality`, `condition`, `perItemCondition`, `avoidRepeat`, `isRecipe` | 购买数量、品质、条件、防重复及是否售卖配方。 |
| `machineUses[]` | `machineId`, `ruleId`, `triggerId`, `requiredCount`, `requiredTags`, `condition` | 机器、输出规则、触发器及输入要求。 |
|  | `outputs[]` | 每项有 `itemId`、`randomItemIds`、`outputMethod`、`minStack`、`maxStack`、`quality`、`condition`。 |
|  | `minutesUntilReady`, `daysUntilReady` | 加工完成所需时间。 |
| `usedIn[]` | `usageId`, `usageType`, `quantity`, `quality` | 使用该物品的配方或收集包实体、数量和品质要求。 |
| `locations[]` | `locationId`, `season`, `areaId`, `chance`, `condition` | 鱼类地点、季节、区域、出现概率与条件。 |
|  | `minFishingLevel`, `minDistanceFromShore`, `maxDistanceFromShore` | 钓鱼等级、离岸距离下限/上限。 |
| `fishPondRules[]` | `ruleId`, `requiredTags`, `maxPopulation`, `spawnTime` | 鱼塘规则 ID、匹配标签、最大数量和繁殖时间。 |
|  | `producedItems[]` | 每项有 `itemId`、`requiredPopulation`、`chance`、`minStack`、`maxStack`、`condition`。 |
|  | `populationGates` | 官方原始人口门槛对象；因其嵌套形状属于官方资产，按字段存在性展示。 |

### 官方原始字段清单

以下是随当前仓库 `dist/stardew.db`（游戏 `1.6.15.24356`）实际出现的根字段集合。它是排查与增强展示的参考，不是跨游戏版本的稳定契约。`DisplayName`、`Description` 等值可能是 `[LocalizedText ...]` 引用；优先使用 `entities` 的已解析展示列。

| 类型 | 原始/补充字段（同一行字段按逗号分隔） |
|---|---|
| `object` / `mineral` / `ring` | `Name`, `DisplayName`, `Description`, `Type`, `Category`, `Price`, `Edibility`, `IsDrink`, `CanBeGivenAsGift`, `CanBeTrashed`, `ContextTags`, `Buffs`, `ArtifactSpotChances`, `GeodeDrops`, `GeodeDropsDefaultItems`, `ExcludeFromFishingCollection`, `ExcludeFromRandomSale`, `ExcludeFromShippingCollection`, `ColorOverlayFromNextIndex`, `Texture`, `SpriteIndex`, `CustomFields`。 |
| `crop` | `SeedItemId`, `DaysInPhase`, `Seasons`, `RegrowDays`, `NeedsWatering`, `IsPaddyCrop`, `IsRaised`, `HarvestItemId`, `HarvestMethod`, `HarvestMinStack`, `HarvestMaxStack`, `HarvestMinQuality`, `HarvestMaxQuality`, `HarvestMaxIncreasePerFarmingLevel`, `ExtraHarvestChance`, `PlantableLocationRules`, `TintColors`, `CountForMonoculture`, `CountForPolyculture`, `Texture`, `SpriteIndex`, `CustomFields`。 |
| `villager` | `DisplayName`, `BirthSeason`, `BirthDay`, `HomeRegion`, `Gender`, `Age`, `Language`, `Manner`, `SocialAnxiety`, `Optimism`, `CanBeRomanced`, `LoveInterest`, `Home`, `Appearance`, `FriendsAndFamily`, `Calendar`, `SocialTab`, `CanReceiveGifts`, `CanSocialize`, `CanVisitIsland`, `CanGreetNearbyCharacters`, `CanCommentOnPurchasedShopItems`, `UnlockConditions`, `SpouseRoom`, `SpousePatio`, `SpouseFloors`, `SpouseWallpapers`, `SpouseAdopts`, `SpouseWantsChildren`, `SpouseGiftJealousy`, `SpouseGiftJealousyFriendshipChange`, `WinterStarGifts`, `WinterStarParticipant`, `FlowerDanceCanDance`, `PerfectionScore`, `TextureName`，以及肖像/动画/布局字段。 |
| `big_craftable` | `Name`, `DisplayName`, `Description`, `Price`, `Fragility`, `CanBePlacedOutdoors`, `CanBePlacedIndoors`, `IsLamp`, `Texture`, `SpriteIndex`, `ContextTags`, `CustomFields`。 |
| `weapon` | `Name`, `DisplayName`, `Description`, `MinDamage`, `MaxDamage`, `Knockback`, `Speed`, `Precision`, `Defense`, `Type`, `MineBaseLevel`, `MineMinLevel`, `AreaOfEffect`, `CritChance`, `CritMultiplier`, `CanBeLostOnDeath`, `Texture`, `SpriteIndex`, `Projectiles`, `CustomFields`。 |
| `tool` | `Name`, `DisplayName`, `Description`, `ClassName`, `UpgradeLevel`, `UpgradeFrom`, `ConventionalUpgradeFrom`, `SalePrice`, `AttachmentSlots`, `CanBeLostOnDeath`, `Texture`, `SpriteIndex`, `MenuSpriteIndex`, `SetProperties`, `ModData`, `CustomFields`。 |
| `trinket` | `DisplayName`, `Description`, `Texture`, `SheetIndex`, `TrinketEffectClass`, `DropsNaturally`, `CanBeReforged`, `ModData`, `CustomFields`。 |
| `shop` | `Id`, `Items`, `Currency`, `Owners`, `PriceModifiers`, `PriceModifierMode`, `ApplyProfitMargins`, `RequireMailReceived`, `RequireEventSeen`, `SalableItemTags`, `StackSizeVisibility`, `VisualTheme`, `OpenSound`, `PurchaseSound`, `PurchaseRepeatSound`, `ItemId`, `CustomFields`。 |
| `special_order` | `Name`, `Text`, `Requester`, `OrderType`, `Duration`, `Repeatable`, `Condition`, `RequiredTags`, `Objectives`, `Rewards`, `RandomizedElements`, `SpecialRule`, `ItemToRemoveOnEnd`, `MailToRemoveOnEnd`, `CustomFields`。 |
| `tailoring_recipe` | `Id`, `FirstItemTags`, `SecondItemTags`, `CraftedItemId`, `CraftedItemIdFeminine`, `CraftedItemIds`, `SpendRightItem`。 |
| `quest` | `Targets`, `Count`, `RewardItemId`, `RewardItemPrice`, `RewardMail`, `RewardMailAll`, `RewardDialogue`, `RewardDialogueFlag`, `RewardFlag`, `RewardFlagAll`, `DisplayName`, `CustomFields`。 |
| `bundle` | `AreaName`, `Keys`, `BundleSets`, `Bundles`；其中包项有 `Name`, `Index`, `Sprite`, `Color`, `Items`, `Pick`, `RequiredItems`, `Reward`。 |
| `drop` | `monsterId`（掉落怪物 ID）、`itemId`（掉落物品 ID）、`chance`（旧式记录的概率文本）。 |
| `achievement` / `fish` / `furniture` / `footwear` / `monster` / `npc_schedule` / `villager_gift` / `ginger_island` / 配方 | `legacyValue` 为未拆分的官方斜杠记录，`legacyFields` 为按 `/` 切分后的数组。位置含义随资产类型不同；应用不要依赖其下标，改用已有标准列和 `officialDerived`。配方另有 `outputItemId`、`outputEntityType`；制作配方可有 `hasExplicitDisplayName`。 |

`_provenance`、`officialDerived` 及前述图像补充字段也可能出现在任意类型；`CustomFields`、`ModData` 是官方自定义扩展容器，内部键不属于本项目的稳定接口。

## 可直接复用的查询

所有应用层输入都应作为 SQLite 参数绑定。示例中的 `?` 是参数占位符。

```sql
-- 类型列表：只取首屏字段
SELECT id, name_zh, name_en, category, image_path
FROM entities
WHERE entity_type = ?
ORDER BY name_zh COLLATE NOCASE;

-- 详情页
SELECT * FROM entities WHERE id = ?;

-- 精确别名补充搜索
SELECT e.id, e.name_zh, e.entity_type, e.image_path
FROM entity_aliases AS a
JOIN entities AS e ON e.id = a.entity_id
WHERE a.alias = ?;

-- FTS：输入须转换为 FTS4 查询语法；空查询不要执行 MATCH
SELECT e.id, e.name_zh, e.name_en, e.entity_type, e.image_path
FROM entity_search AS s
JOIN entities AS e ON e.id = s.entity_id
WHERE entity_search MATCH ?
ORDER BY e.name_zh COLLATE NOCASE
LIMIT ?;
```

FTS 搜索返回的是文档命中，不保证与实体表有数据库级强制约束。应用可在安装校验中执行：`SELECT COUNT(*) FROM entities`、`SELECT COUNT(*) FROM entity_search` 与 `build_meta.entity_count` 的合理性比对。

## 详情页映射与升级策略

推荐把 UI 分为三个层次：通用头部（`name_zh`、`name_en`、图片、`category`）、类型卡片（读取该类型的 `officialDerived`）、关系卡片（商店、机器、用途、地点）。关系中的 ID 不总能唯一定位实体，例如未合格物品 ID 可以同时候选 `object`、`mineral`、`ring`；应按实体存在性解析，并允许“无对应实体”的纯文本降级展示。

当 `schemaVersion` 增大时，应用必须拒绝启用该包，直到完成数据库适配。无论 schema 是否相同，只要 `publishable` 为 `false`、质量不是 `passed`、存在数据错误或 `missing/invalid` 翻译，就必须拒绝启用。相同 schema 下即使 `builderVersion` 或 `gameVersion` 改变，也应以字段存在性读取 JSON：只展示认识的字段，忽略未知字段，绝不因未知字段而覆盖或删除原始数据。

## 数据边界

构建器只保留官方结构化资产并进行确定性关联，不执行游戏条件表达式，也不生成攻略结论、事件摘要或运行时计算结果。因此“可购买”“可捕获”等关系表示官方规则存在，是否在玩家当前存档、日期、天气和进度下成立，仍需应用自行实现条件解释或明确标注为条件信息。
