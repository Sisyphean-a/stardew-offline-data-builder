---
doc_type: feature-acceptance
feature: 2026-07-17-steam-game-discovery
status: pending
audit_state: completed
audit_reason: ""
auditor_id: ""
acceptance_authorization_ref: ""
accepted: 2026-07-17
round: 1
---

# Steam 游戏目录自动发现验收报告

> 阶段：验收闭环
> 验收日期：2026-07-17
> 关联方案：`.codestable/features/2026-07-17-steam-game-discovery/steam-game-discovery-design.md`

## 1. 接口契约核对

- [x] `resolve_game_directory(None)`：唯一有效候选返回 `ResolvedGameDirectory(path, origin="auto")`；零/多候选抛出带 `--game-dir` 指引的 `FileNotFoundError`。
- [x] `resolve_game_directory(Path(...))`：显式路径仅经既有 `ensure_game_directory` 校验并标记 `explicit`；三个命令均仅在参数为 `None` 时进入自动发现。
- [x] `ResolvedGameDirectory`、KeyValues 解析和 Steam 根/库/manifest 校验集中在 `builder.sources`，命令层只消费已解析路径。
- [x] 方案第 2.2 节为线性流程且明确无需流程图；三个命令各一次解析、自动时各一次审计输出均有代码落点。

## 2. 行为与决策核对

- [x] `build`、`unpack`、`doctor` 的 `--game-dir` 均为可选；显式值优先，自动候选只接受唯一完整安装。
- [x] 默认 Steam 根、`libraryfolders.vdf` 附加库、固定 app id、受限 `installdir`、`common` 直接子目录和 Content/DLL 文件类型共同确认候选。
- [x] 自动发现只读、稳定排序去重；零/多候选不静默选择。
- [x] 反向核对：本次新增的 sources/commands 未发现 HTTP、下载器或磁盘根遍历；`--game-dir` 仍保留。
- [x] 挂载点：代码引用仅在 `build.py`、`unpack.py`、`doctor.py` 三个入口及对应测试；移除这三处解析调用与 CLI 选项文案即可拔除本 feature，不影响既有解包函数。

## 3. 验收场景核对

| ID | 场景与证据 | 结果 |
|---|---|---|
| S1 | 全量 pytest 覆盖三条命令的自动审计输出；本机无参数 `doctor` 与 `unpack` 实际定位 `D:\SteamLibrary\steamapps\common\Stardew Valley` | 通过 |
| S2 | `test_discovers_game_from_additional_steam_library` 读取附加库 VDF | 通过 |
| S3 | 显式路径测试阻止 Steam 探测；空字符串回归测试证明三个入口不会改走自动发现 | 通过 |
| S4/S5 | 零候选、多候选测试验证可操作错误与稳定排序 | 通过 |
| S6 | 损坏 KeyValues、appid、逃逸 installdir、相对库、各布局错误文件类型测试 | 通过 |
| S7 | 三个帮助测试验证 `--game-dir` 非必填，并标明 Steam/Windows | 通过 |
| S8 | README 包含无参数用法、Windows 限定、显式回退和 StardewXnbHack 前提 | 通过 |

- [x] review 的 Test And QA Focus：空字符串显式路径、真实 Steam 默认/附加库、损坏元数据已覆盖；默认根注册表模拟与精确解析调用计数为后续增强建议，不承载核心缺口。
- [x] 验证证据来源：accept-inline verification；`python -m pytest -q`（58 passed）、`python -m ruff check src tests`（通过）、真实无参数 `doctor` 与 `unpack`（通过）。
- [x] review residual risk：带 UTF-8 BOM 的 Steam 元数据仍会被视为无候选；真实 Steam 文件已验证未受影响，不影响当前核心验收。
- [x] Evidence pack / Gate results：Standard lane 无此类产物；DoD 必跑命令均有通过证据。

## 4. 术语一致性

- [x] 显式游戏目录、Steam 根目录、Steam 库目录、有效自动候选、`ResolvedGameDirectory` 与方案一致。
- [x] 未引入社区数据、下载器、其他启动器或网络客户端等范围外概念。

## 5. 领域影响盘点

- [x] 新名词：无需写入 CONTEXT；项目不存在 CONTEXT，且本 feature 不改变领域模型。
- [x] 结构性选择：无需 ADR；本地 Steam 输入发现是受限实现细节，无新外部依赖或难回退架构决策。
- [x] 流程级约束：无需 ADR；“显式优先、唯一候选”已由 feature design 与测试覆盖。

## 6. requirement delta / clarification 回写

- [x] 无 managed requirement；本 feature 是用户已确认的局部命令行为实现，不改变游戏数据来源、数据库契约或领域能力描述，跳过 requirement 回写。

## 7. roadmap 回写

- [x] 非 roadmap 起头：design 的 `roadmap` 与 `roadmap_item` 均为空，跳过。

## 8. attention.md 候选盘点

- [x] 无候选：本 feature 未暴露每次开发都需要写入 attention 的环境或工作流规则。

## 9. 遗留

- 已知限制：仅 Windows Steam；多个有效安装或发现失败时必须显式传入 `--game-dir`。
- 已知限制：不支持带 UTF-8 BOM 的 Steam VDF/ACF；当前真实安装未受影响。
- 非阻塞建议：可追加默认根提供器的模拟测试与解析器调用次数精确断言。

## 10. 最终审计

- 验证证据来源：accept-inline verification。
- Inline Verification Matrix：S1-S8 全部由全量 pytest、Ruff、README/diff 核对与真实无参数 `doctor`、`unpack` 覆盖。
- 聚合命令：`python -m pytest -q` → 58 passed；`python -m ruff check src tests` → passed；`python -m builder doctor`、`python -m builder unpack` → 均自动发现并成功。
- 场景复核：re-verified 8 / trust-prior-verify 0。
- 交付物复核：发现模块、三个命令、CLI、测试、README、review 与本报告均存在；无需 schema、architecture、requirement 或 roadmap 写回。
- 完整工作区复核：tracked、unstaged 与 untracked 交付物均已纳入；`.codestable/reference/` 与 runtime manifest 为本会话 runtime 同步产物，已与业务功能区分。
- diff 清洁度：`git diff --check` 通过；无新增 TODO/FIXME/XXX、注释掉代码、无用 import 或非功能性调试输出。
- 知识沉淀出口：无 attention、compound、guide 或 API 文档候选。
- 结论：验证通过，等待用户终审确认。
