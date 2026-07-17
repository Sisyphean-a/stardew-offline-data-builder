---
doc_type: feature-design-review
feature: 2026-07-17-steam-game-discovery
status: passed
review_state: passed
review_reason: ""
reviewer_id: /root/steam_design_reviewer_final
reviewed: 2026-07-17
round: 4
---

# steam-game-discovery feature design 审查报告

## 1. Scope And Inputs

- Design: `.codestable/features/2026-07-17-steam-game-discovery/steam-game-discovery-design.md`
- Checklist: `.codestable/features/2026-07-17-steam-game-discovery/steam-game-discovery-checklist.yaml`
- Intent / brainstorm: none
- Requirement / roadmap: none
- Related docs: 已完成的 `official-only-data` 目标；requirements、roadmap、compound 均无相关文档。
- Code facts checked: `src/builder/cli.py`、`src/builder/commands/build.py`、`src/builder/commands/unpack.py`、`src/builder/commands/doctor.py`、`src/builder/utils/paths.py` 与相关 tests。

### Independent Review

- Status: completed
- Detection: independent-agent
- Provider / agent: `/root/steam_design_reviewer`、`/root/steam_design_reviewer_round2`、`/root/steam_design_reviewer_round3`、`/root/steam_design_reviewer_final`。
- Raw output: 前三轮分别发现自动候选校验、manifest 边界、根目录来源、文件类型、KeyValues 语法、显式兼容、审计输出、帮助和 DoD 契约缺口；均已逐条修订。最终审查只发现 DoD 字段缺失。
- Merge policy: 主 agent 已用 design、checklist 与现有代码核验所有 finding；最终 DoD finding 由限定 diff 和 `codestable-dod-contract-gate.py` 通过结果关闭。
- Gate effect: independent review completed；focused closure 后允许交给用户整体 review。

## 2. Design Summary

- Goal: Windows 用户省略 `--game-dir` 时，仅从本机 Steam 注册表与已声明库中发现已安装的星露谷物语。
- Key contracts: 显式路径优先；自动候选必须经根/库路径、KeyValues、appid、installdir、common 边界和完整文件类型校验；零或多候选失败；三个公开命令自动时各输出一次审计行。
- Steps: 4 个独立步骤，风险热点是 Steam KeyValues 输入与显式路径兼容。
- Checks: 6 项，覆盖名词契约、编排、范围与验收场景。
- Baseline / validation: `python -m pytest -q` 已得 31 passed；`python -m ruff check src tests` 已通过。

## 3. Findings

### blocking

none

### important

none

### nit

none

### suggestion

- 多候选错误的路径应使用规范化后的稳定排序显示值；实现与测试应断言顺序。

### learning

- `unpack_game_directory` 是合适的低层边界：只接收已解析路径，不负责 Steam 发现或审计输出。

### praise

- 自动发现保持本地只读、显式路径优先和歧义即失败，与项目的官方本地数据边界一致。

## 4. User Review Focus

- 用户需要重点拍板：仅 Windows Steam 自动发现；多个有效安装时要求显式 `--game-dir`，不自动选择。
- implement 需要重点遵守：自动与显式路径的校验分工、固定 KeyValues 语法边界、每个公开命令只解析和打印一次。
- code review / acceptance 需要重点复核：三条无路径命令、附加库、错误文件类型和真实 Steam Windows 黑盒行为。

## 5. Evidence Confidence Ledger

| Check | Verdict | Evidence Class | Basis | Follow-up |
|---|---|---|---|---|
| Acceptance Coverage Matrix | pass | E | design 第 3 节将每个核心场景映射到步骤和命令 | implementation 核验测试 |
| DoD Contract | pass | E | `codestable-dod-contract-gate.py` 返回 passed | acceptance 核验交付物 |
| Steps and checks traceability | pass | E | checklist 的 4 steps、6 checks 均可回指 design | implementation 更新状态 |
| Roadmap contract compliance | n/a | E | feature 不来自 roadmap | none |
| Module interface design | pass | C | 解析结果携带 origin，命令边界单次调用 | code review 核验 |
| Validation and artifacts | pass | E | design 的 Validation Commands 与 Required Artifacts 明确 | acceptance 执行 |

Summary: E=5, C=1, H=0, H-only core checks=none。

## 6. Residual Risk

- 临时目录测试不能替代真实 Windows Steam 注册表、库配置与 reparse-point 行为；实现后必须用真实 Steam 安装完成一次无 `--game-dir` 的 doctor、unpack、build 黑盒验证。
- 本 feature 不改变 `StardewXnbHack` 前提：自动找到游戏目录但缺少解包工具时，仍按既有显式错误语义失败。

## 7. Verdict

- Status: passed
- Next: 交给用户整体 review；获得明确确认后进入 implementation。

## 8. Focused Closure

- Closed findings: final review FDR-001（DoD Contract 缺少机械门禁字段）。
- Attributed delta: 仅在 DoD Contract 内添加 `Validation Commands` 标题和非空 `Required Artifacts` 清单。
- Verification: `$env:PYTHONDONTWRITEBYTECODE='1'; python C:\Users\xiakn\.agents\skills\cs-onboard\tools\codestable-dod-contract-gate.py --design .codestable\features\2026-07-17-steam-game-discovery\steam-game-discovery-design.md` 返回 `status: passed`；checklist YAML 校验和 `git diff --check` 通过。
- Classification: 未改变功能行为、公开契约、架构边界、验收语义或范围；属于单一机械门禁字段修复。
