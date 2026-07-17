---
doc_type: feature-review
feature: 2026-07-17-steam-game-discovery
status: passed
reviewer: subagent+ocr
reviewed: 2026-07-17
round: 1
lane_a_state: completed
lane_a_ref: "/root/steam_implementation_reviewer"
lane_a_reason: "首轮独立 Task agent 审查已完成并完成本地事实核验"
lane_b_state: completed
lane_b_ref: ""
lane_b_reason: "首轮 ocr review 已完成并完成本地事实核验"
---

# steam-game-discovery 代码审查报告

## 1. Scope And Inputs

- Design: `.codestable/features/2026-07-17-steam-game-discovery/steam-game-discovery-design.md`
- Checklist: `.codestable/features/2026-07-17-steam-game-discovery/steam-game-discovery-checklist.yaml`
- Evidence pack: none
- Gate results: none
- DoD results: none
- Implementation evidence: 本会话实现记录；`REV-001` 以 RED→GREEN 修复，目标测试、全量测试与 Ruff 已通过。
- Diff basis: 当前未暂存工作区改动与未跟踪实现文件。
- Review mode: initial review + user-authorized closure
- Baseline dirty files: `.codestable/reference/` 与 `.codestable/runtime-manifest.json` 为本会话 CodeStable runtime 同步产物，不属于业务代码审查范围。

### Independent Review

- Detection: Task agent 与 `ocr` CLI 均可用。
- 环节 A 独立隔离 Task agent: independent-agent + completed，引用 `/root/steam_implementation_reviewer`。
- 环节 B OCR CLI: completed；已运行 `ocr review --audience agent`，范围为本次功能的人写代码、测试与 README。
- OCR severity mapping: High→blocking/important，Medium→nit/suggestion，Low→discarded。
- Merge policy: 首轮两个环节均已返回并完成本地事实核验。修复 `REV-001` 后，本应进行完整复审；用户明确要求“最多一轮审核，禁止多轮审核”，已中止尚未产生结论的第二轮 Task agent 与 OCR，改以首轮 reviewer 结论和本地回归证据收尾。
- Gate effect: 用户明确限制仅保留首轮审核；本报告不将已中止的第二轮计为审核结果。

## 2. Diff Summary

- 新增：`src/builder/sources/steam_keyvalues.py`、`src/builder/sources/steam_discovery.py`、`tests/test_steam_discovery.py`。
- 修改：README、CLI、build/unpack/doctor 命令与对应测试。
- 删除：none。
- 未跟踪 / staged：新增文件尚未跟踪；无 staged diff。
- 风险热点：跨命令 CLI 契约与本机 Steam 元数据解析。

## 3. Adversarial Pass

- 假设的生产 bug：显式空路径被误认为省略，从而触发 Steam 自动发现。
- 主动攻击过的反例：三个命令分别以 `--game-dir ""` 运行；修复前均将 `None` 传给 resolver，修复后均传递 `Path("")`。
- 结果：`REV-001` 已解除；全量回归通过。VDF/ACF 带 BOM 的兼容性保留为 residual risk。

## 4. Findings

### blocking

- none。

### important

- [x] REV-001 `src/builder/commands/build.py:116`、`src/builder/commands/unpack.py:29`、`src/builder/commands/doctor.py:26`：空字符串显式路径曾因真值判断被误认为省略。
  - Evidence: RED 阶段 3 个参数化入口测试均收到 `None`；三个入口改为 `game_dir is not None` 后，目标测试通过并收到 `Path("")`。
  - Impact: 显式路径优先契约已恢复，空字符串不会再触发自动发现。
  - Expected fix scope: 已完成，未扩展到审查建议的其他非阻塞项。

### nit

- none。

### suggestion

- 后续可让三个“自动发现一次”测试同时对 fake resolver 计数，直接断言调用次数为一。
- 后续可模拟注册表与 Program Files 根，覆盖默认根的过滤与去重。

### learning

- 有限 KeyValues 解析器只在受约束层级读取必要字段，未知嵌套对象不会被误作候选元数据。

### praise

- manifest 的 appid、单段 installdir、`common` 直接子目录关系和 Content/DLL 类型校验共同确认自动候选，避免目录名猜测。
- `ResolvedGameDirectory` 分离显式与自动来源，且低层解包未引入二次发现，符合设计边界。

## 5. Test And QA Focus

- QA 必须重点复核：真实 Windows Steam 注册表、默认库、附加库与损坏元数据。
- Evidence pack residual risks / gate warnings：无 evidence pack；BOM 元数据兼容性留给 QA。
- 建议新增或加强的测试：解析器精确调用次数；默认根的注册表/Program Files 过滤与去重。
- 不能靠 review 完全确认的点：真实 Steam 客户端的注册表与库配置。

## 6. Residual Risk

- VDF/ACF 以 `utf-8` 读取；带 UTF-8 BOM 的文件会被视为无候选。真实本机 Steam 验证未见此格式。
- 用户明确禁止多轮审核；`REV-001` 修复后的代码未进行第二个独立 reviewer 轮次，仅有 RED→GREEN、全量测试、Ruff 与 diff 清洁度验证。

## 7. Verdict

- Status: passed
- Next: Standard feature 进入 accept-inline。

## 8. Focused Closure

- Closed findings: REV-001。
- Attributed delta: `src/builder/commands/build.py`、`src/builder/commands/unpack.py`、`src/builder/commands/doctor.py`；`tests/test_build.py`、`tests/test_unpack.py`、`tests/test_doctor.py`。
- Targeted verification: 修复前目标测试 `3 failed`；修复后 `3 passed`；`python -m pytest -q` 为 `58 passed`；`python -m ruff check src tests` 通过；`git diff --check` 通过。
- Classification: 这是公开行为修复，正常流程应完整复审；因用户明确限制最多一轮审核，按该限制保留首轮 reviewer gate 并将该例外记录为 residual risk。
