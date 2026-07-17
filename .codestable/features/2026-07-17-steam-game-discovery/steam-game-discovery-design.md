---
doc_type: feature-design
feature: 2026-07-17-steam-game-discovery
requirement: ""
roadmap: ""
roadmap_item: ""
execution_lane: standard
status: approved
summary: 省略游戏路径时自动发现 Windows 本机 Steam 中已安装的星露谷物语
tags: [steam, discovery, windows, local-data]
---

## 0. 术语约定

- **显式游戏目录**：用户通过 `--game-dir` 传入的目录；继续沿用各命令现有的目录、`Content/` 与 DLL 校验语义。
- **Steam 根目录**：本机 Steam 客户端目录；从 Windows 注册表和常见安装位置收集。输入必须非空、绝对、规范化且为现存目录，否则丢弃。
- **Steam 库目录**：Steam 根目录或 `libraryfolders.vdf` 声明的库根目录；输入同样必须非空、绝对、规范化且为现存目录，`steamapps/` 与其 `common/` 均必须为目录，才可检查应用 manifest。
- **有效自动候选**：其库的普通文件 `steamapps/appmanifest_413150.acf` 解析出 `appid == "413150"` 与安全的 `installdir`；由此构造的目录是 `common/` 的直接子目录，且游戏根与 `Content/` 为目录、`Stardew Valley.dll` 为普通文件。

## 1. 决策与约束

### 需求摘要

用户已拥有正版游戏，希望 `build`、`unpack`、`doctor` 在省略 `--game-dir` 时从 Windows 本机 Steam 安装与库配置中发现《星露谷物语》，并复用现有解包、解析和构建流程。

成功标准：只存在一个有效候选时，三个命令均可省略 `--game-dir`；显式路径优先；零个或多个候选时输出可操作错误，不任选一个目录。

明确不做：不联网、不下载或分发游戏数据、不扫描任意磁盘、不支持 Steam 以外的启动器、不改变官方资产解析与解包语义。

### 决策与深度

1. `--game-dir` 改为可选；给出显式值时只执行既有命令级校验，不探测 Steam。
2. 自动根提供器仅在 Windows 上读取 `HKCU\\Software\\Valve\\Steam` 的 `SteamPath`、`HKLM\\SOFTWARE\\WOW6432Node\\Valve\\Steam` 的 `InstallPath`，并检查 `%ProgramFiles(x86)%\\Steam`、`%ProgramFiles%\\Steam`；每个值必须为非空绝对路径，规范化后为现存目录。缺失、权限、格式与注册表读取错误均视为该来源无结果并继续；非 Windows 返回空结果。
3. 自动发现从已验证根目录及普通文件 `libraryfolders.vdf` 的结构化 `path` 字段得到库目录；VDF 路径也必须为非空绝对路径，规范化后为现存目录。VDF/ACF 或中间 `steamapps/`、`common/` 的文件类型不符时跳过该来源并继续其他来源。仅检查这些库的固定 `steamapps/appmanifest_413150.acf`，不遍历磁盘或按目录名猜测。
4. VDF/ACF 读取器接受 UTF-8 KeyValues：token 为 `{`、`}` 或引号字符串；字符串仅允许 `\\` 与 `\"` 转义；token 外跳过任意空白和以 `//` 开始至行尾的注释。解析器消费未知标量与嵌套对象，但顶层必须恰有一个对象：VDF 为 `libraryfolders`，ACF 为 `AppState`。未闭合引号/花括号、无效转义或重复的必要直接字段使该文件无效。VDF 仅读取 `libraryfolders` 的直接子对象中唯一的直接 `path` 字段；ACF 仅读取 `AppState` 的唯一直接 `appid` 与 `installdir` 字段。
5. Manifest 必须声明 `appid == "413150"`；`installdir` 必须是单个普通相对目录名，拒绝空值、`.`、绝对路径、分隔符和 `..`。构造后的路径 resolve 后必须满足 `candidate.parent == resolved_common`，并通过完整自动候选校验。
6. 候选稳定排序去重；仅一个候选时继续，零个或多个候选均失败并提示使用 `--game-dir`。

候选方案为只查默认 Steam 根与读取 Steam 库配置。额外库是实际用户安装的正确性关键路径，故选择后者。未增加第三方 VDF 依赖：该边界小、受控且可在临时目录中全面测试；无法解析时不得产生伪候选。

### 风险、依赖与验证

- 非默认库遗漏：以多库 VDF/manifest 夹具测试。
- 多副本误选：以多候选测试确认命令失败并列出路径。
- 注册表不可访问、空/相对/畸形根路径或仅有非 Windows 环境：以可注入根集合验证根提供器返回空结果或继续其他来源；仅预期的注册表/OSError 被忽略，编程错误显式暴露。
- 损坏或逃逸 manifest、空/相对 VDF 库路径与错误文件类型：以错误 appid、缺失 installdir、`.`、`..`、未闭合语法、无效转义、目录伪装 VDF/ACF 与不存在目录夹具测试。
- 破坏既有脚本：以显式路径优先和既有构建回归测试确认。

非显然依赖为当前 Windows 用户的 Steam 注册表与本地 `steamapps` 元数据。测试不得访问真实 Steam 目录或注册表，而应传入临时根或替换根提供器。关键假设：目标用户使用 Steam Windows 客户端；其他启动器和多安装用户仍显式传入 `--game-dir`。

基线及必跑验证：`python -m pytest -q`、`python -m ruff check src tests`；当前基线为 31 个测试通过、Ruff 通过。交付物为本地发现模块、三条命令入口、自动化测试和 README。不得引入调试输出、TODO/FIXME、注释掉代码、无用 import 或网络客户端。

## 2. 名词与编排

### 2.1 名词层

#### 现状

`builder.utils.paths.ensure_game_directory` 只校验调用方提供的路径；`build` 与 `unpack` 的 CLI 将 `--game-dir` 标为必填。`doctor` 的选项已可省略，但缺省时仍将 `None` 传给校验并失败；三个命令都没有自动发现逻辑。

#### 变化

新增 Steam 游戏目录发现器，输出稳定、去重且经完整校验的候选路径；新增统一目录解析入口，返回路径和来源：显式目录仅经既有 `ensure_game_directory` 校验且标记为 `explicit`，缺省目录只在候选数为一时以严格自动校验返回路径且标记为 `auto`。

```text
resolve_game_directory(None)
  一个有效 Steam 候选 → ResolvedGameDirectory(path, origin="auto")
  两个有效候选 → FileNotFoundError（列出路径并要求 --game-dir）
resolve_game_directory(Path("E:/Games/Stardew Valley"))
  → ResolvedGameDirectory(path, origin="explicit")；只校验显式路径
```

#### Interface 设计检查

- Module：新增 Steam 发现模块；现状无该能力。
- Interface：解析入口接收可选显式路径，返回含路径和来源的 `ResolvedGameDirectory` 或 `FileNotFoundError`；候选接口接收可注入 Steam 根目录集合并返回稳定列表。
- Seam：每个公开命令入口只调用一次解析入口；测试传入临时 Steam 根目录或替换根提供器，不读取开发机注册表或真实用户文件。
- Depth / locality：配置、库枚举、manifest 校验和歧义判断集中于发现模块，命令只处理一个目录或统一错误；删掉模块会使复杂度散回三条命令。
- Dependency strategy：本地可替代文件系统与 Windows 注册表。无 adapter；注册表是发现模块内部输入，不暴露伪注入层。
- Test surface：唯一候选、无候选、多候选、显式路径优先与三个 CLI 入口。

### 2.2 编排层

现状为线性流程：build/unpack CLI 接收必填目录，doctor 的可选目录在缺省时失败；命令校验后进入解包或构建。变化只在目录解析前增加条件分支，后续流程保持不变，故不画流程图。

1. CLI 接收可选 `--game-dir`。
2. 每个公开命令入口恰好调用一次解析：显式分支只走既有 `ensure_game_directory`；缺省分支枚举 Steam 根和库、解析 manifest 并严格校验候选。
3. 唯一自动候选在该命令边界恰好输出一次 `✓ 自动发现游戏目录：<path>`，再将已解析 `Path` 传入既有流程；显式路径不输出该行。
4. `unpack_game_directory` 保持只接收已解析 `Path`，不探测 Steam 也不输出审计行；build 内部调用它时不会重复解析或打印。
5. 零或多个候选走既有 CLI 错误退出路径。

显式路径的后置校验保持现有分工，自动路径仅在进入命令前额外经过严格候选校验：

| 命令 | 显式路径解析后 | 自动路径解析后 | 既有后续校验与输出 |
|---|---|---|---|
| build | 仅 `ensure_game_directory` | 已严格校验 | 继续现有解包目录/`--unpacked-dir` 逻辑；自动时一次审计行 |
| unpack | 仅 `ensure_game_directory` | 已严格校验 | 低层仍校验 `Content` 与解包工具；自动时一次审计行 |
| doctor | 仅 `ensure_game_directory` | 已严格校验 | 命令仍校验 `Content`、DLL 与解包工具；自动时一次审计行 |

约束：发现全程只读、不缓存或写回 Steam；候选稳定排序去重；显式路径不受自动发现失败影响；自动发现成功时输出实际目录以便审计。

### 2.3 挂载点清单

- `builder build --game-dir`：改为可选并接入自动目录解析。
- `builder unpack --game-dir`：改为可选并接入自动目录解析。
- `builder doctor --game-dir`：保留已可选的参数并接入自动目录解析。

### 2.4 推进策略

1. 实现 Windows Steam 根、库和受语法/路径/文件类型边界约束的 manifest 候选发现；退出信号：默认库、多库、根/VDF 路径错误、错误文件类型、错误 manifest 与注册表错误均得到确定结果。
2. 实现显式优先、唯一通过、零/多候选失败与来源标识的目录解析；退出信号：显式兼容与严格自动候选校验均有可观察结果。
3. 接入三个命令；退出信号：每个入口只解析一次，自动发现时均输出一次统一审计行，低层解包函数不发现也不打印。
4. 更新三个 CLI 帮助与 README 并覆盖发现边界、三条 CLI 行为和显式回退，运行全量检查；退出信号：帮助不再标记必填，文档与全部验收场景有自动化或差异证据。

### 2.5 结构健康度与微重构

- 文件级：`commands/build.py` 约 240 行，仅替换目录解析调用；`unpack.py`、`doctor.py` 保持命令编排职责。
- 目录级：`sources/` 现有 4 个同层文件（含 `__init__.py`）；新发现模块属于本机输入源，不造成摊平。

结论：**不做微重构**。Steam 发现逻辑置于独立模块，避免堆入命令或 `paths.py`。

## 3. 验收契约

### 关键场景

1. 默认 Steam 库有唯一、完整的有效自动候选 → 三个命令省略 `--game-dir` 后各输出一次 `✓ 自动发现游戏目录：<path>` 并继续原有流程。
2. 有效安装仅位于 `libraryfolders.vdf` 的附加库 → 自动发现该目录。
3. 有效显式 `--game-dir` 且 Steam 配置不可用 → 显式目录仍成功。
4. 无有效候选 → 以游戏目录错误退出，输出 `--game-dir` 指引。
5. 两个有效候选 → 以游戏目录错误退出并列出两个路径，不继续解包或构建。
6. 配置或 manifest 无法解析，appid 错误、缺失 installdir、`.`、逃逸路径、空/相对根或库路径，以及 VDF、ACF、steamapps、common、游戏根、Content、DLL 的错误文件类型或不存在目录 → 不产生伪候选；若无其他候选则按场景 4 失败。
7. 三个 `--help` 均不再将 `--game-dir` 标记为必填，且说明仅 Windows 可自动发现、显式路径仍可回退。
8. README 说明三个命令均可自动发现、无参数示例、`--game-dir` 的显式回退，以及 `StardewXnbHack` 仍是未解包游戏的既有独立前提。

### 反向核对

- 生产代码不得调用 HTTP、下载器或第三方数据 API。
- 发现模块不得遍历磁盘根目录，也不得写入 Steam 目录。
- CLI 不得移除 `--game-dir`。

### Acceptance Coverage Matrix

| Scenario | Covered By Step | Evidence Type | Command / Action | Core? |
|---|---|---|---|---|
| 默认库唯一候选与审计输出 | S1/S2/S3 | pytest | `python -m pytest -q` | yes |
| 附加库候选 | S1 | pytest | `python -m pytest -q` | yes |
| 显式路径优先 | S2/S3 | pytest | `python -m pytest -q` | yes |
| 无候选、多候选 | S2/S4 | pytest | `python -m pytest -q` | yes |
| 损坏语法、路径或文件类型 | S1/S4 | pytest | `python -m pytest -q` | yes |
| 三个 CLI 帮助 | S3/S4 | pytest | `python -m pytest -q` | yes |
| README 自动发现与显式回退说明 | S4 | diff review | README | yes |
| 静态检查 | S4 | Ruff | `python -m ruff check src tests` | yes |

### DoD Contract

| ID | 要求 | 证据 | 阻塞级别 |
|---|---|---|---|
| DOD-DESIGN-001 | 设计通过独立审查并获用户确认 | design review、用户确认 | blocking |
| DOD-IMPL-001 | checklist 步骤全部完成 | checklist 与实现证据 | blocking |
| DOD-REVIEW-001 | 独立代码审查无阻塞项 | review 报告 | blocking |
| DOD-QA-001 | Standard lane 的 acceptance-inline 覆盖全部核心场景与必跑命令 | acceptance 报告与命令输出 | blocking |
| DOD-ACCEPT-001 | 核心场景通过并完成最终核对 | acceptance 与命令输出 | blocking |

Validation Commands:

| ID | 命令 | 目的 | 核心性 | 失败处理 |
|---|---|---|---|---|
| CMD-001 | `python -m pytest -q` | 验证发现与既有构建回归 | core | fix-or-block |
| CMD-002 | `python -m ruff check src tests` | 验证静态规则 | core | fix-or-block |

Required Artifacts: `src/builder/sources/steam_discovery.py`、`src/builder/commands/build.py`、`src/builder/commands/unpack.py`、`src/builder/commands/doctor.py`、`src/builder/cli.py`、对应发现与 CLI 测试、`README.md`、review 与 acceptance 报告。

## 4. 与项目级架构文档的关系

本 feature 增加用户可见的本地输入发现能力，但不改变游戏事实来源、数据库契约或领域模型。验收时更新 README；无需新增 CONTEXT 或 ADR。
