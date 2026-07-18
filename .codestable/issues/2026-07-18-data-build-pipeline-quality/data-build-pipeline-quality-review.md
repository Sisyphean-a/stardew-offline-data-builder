---
doc_type: issue-review
issue: 2026-07-18-data-build-pipeline-quality
status: passed
reviewed: 2026-07-18
round: 5
lane_a_state: completed
lane_a_ref: "/root/visual_integration_test"
lane_a_reason: "以最小 closure 范围独立复核最终发布链路；Round 4 的六项 blocking 和 fixture 旧包遗留路径均已关闭。"
lane_b_state: unavailable
lane_b_ref: ""
lane_b_reason: "OCR 会话目录在沙箱中无写权限；提权会向未授权第三方服务发送未提交源码，已拒绝，不执行。"
---

# 数据构建质量修复代码审查报告

## 1. Scope And Inputs

- Issue report / analysis / fix note：`.codestable/issues/2026-07-18-data-build-pipeline-quality/`。
- Goal evidence：`data-build-pipeline-remediation-evidence-pack.md`、gate results、DoD results。
- Diff basis：当前未提交、可归因于本 Goal 的生产代码、测试和发布勘误。
- Review mode：initial。
- Baseline dirty files：本 Goal 的全部未提交改动；无已知无关改动。

### Independent Review

- 环节 A：独立 Task agent `/root/visual_integration_test`，Round 5 closure review passed；其只读复核了最终发布路径及回归证据。
- 环节 B：OCR CLI 不可用；其会话目录无权限，且外部源码审查未获授权。
- OCR severity mapping：High→blocking/important，Medium→nit/suggestion，Low→discarded。
- Merge policy：Task agent 的结论已由主代理依据代码路径和测试范围核验；OCR 未启动。
- Gate effect：环节 A 已返回 passed；OCR lane 不可用不改变本地独立 review 的结论。

## 2. Diff Summary

- 新增：真实旧格式视觉规则、质量/metadata 模块及质量回归测试。
- 修改：构建、报告、数据库、打包、CLI、标准化、官方解析、图片管线及历史完成表述。
- 删除：无。
- 风险热点：构建失败时的发布包生命周期、SQLite metadata 与 manifest 一致性、图集裁切边界。

## 3. Adversarial Pass

- 假设的生产 bug：失败构建复用既有输出目录后，旧 `.svdata` 被误认为是本次构建的成功产物。
- 主动攻击：质量失败路径、独立打包 metadata 保真、图集裁切边界、真实旧格式与测试假阳性。
- Round 1 结果：失败构建保留旧同名包被升级为 REV-001；其余攻击路径无可验证 blocking/important。
- Round 2 任务：复核修复后是否消除 canonical 包路径歧义，且未破坏质量与打包契约。

## 4. Findings

### blocking

- [x] REV-001 `src/builder/commands/build.py:202` 质量失败时保留同名旧 `.svdata`。
  - Evidence: 质量失败仅跳过 `create_svdata_package`；复用成功输出目录时，旧包仍留在 canonical 文件名，而新的 DB、报告和 manifest 已失败。
  - Impact: 用户或自动化可能将旧包当作本次产物，重新引入“失败构建仍可发布”的误判。
  - Expected fix scope: 失败时移除 canonical 包路径的歧义，同时以可恢复方式保留旧包或拒绝产生混合输出。
  - Round 1 closure candidate: `quarantine_existing_package` 将旧包重命名为 `.failed`，`test_failed_rebuild_quarantines_previous_package` 覆盖先成功、后失败的同一输出目录路径；Round 2 独立复审中。

### important

- none

### nit

- none

### suggestion

- `build_fixture_command` 不生成 `.svdata`，但可另行确认其数据库 metadata 是否应走同一图片质量门禁。

### learning

- 质量门禁必须覆盖输出目录中已存在的发布物，而不仅是本次是否调用打包函数。

### praise

- SQLite `artifact_metadata` 被独立 package 原样读取并校验，避免了旧实现的摘要重建丢失。
- 必需图片缺源和裁切越界都已转化为结构化错误与回归测试。

## 5. Test And QA Focus

- QA 必须重点复核：先成功生成包、再复用同一输出目录触发质量失败时，canonical 包不会继续存在或被误用。
- Evidence pack residual risks / gate warnings：`build_fixture_command` 不生成包；是否需要同一门禁为非阻断后续关注。
- 建议新增或加强的测试：上述复用输出目录的失败路径。
- 不能靠 review 完全确认的点：真实用户在外部目录中保留历史产物时的迁移提示，应由功能验收检查。

## 6. Residual Risk

- `build_fixture_command` 不直接发布，未纳入本次阻断范围；后续若把它作为公开数据产物入口，应复核其质量契约。

## 7. 历史 Verdict

- Round 2 当时为 blocked，原因是等待独立复审；该状态已被后续轮次取代。

## 8. Round 5 Closure

- Round 4 B1：早期失败会遗留旧数据库并允许独立打包。现以持久化 release block 拒绝 standalone package，测试覆盖成功后删除 Fish 的路径。
- Round 4 B2：八类必需类型不足。发布构建现在要求当前基线的全部 25 类官方实体，缺少 monster 等非视觉类型同样阻断。
- Round 4 B3：fixture 能打包。fixture metadata 为不可发布，CLI 说明其仅用于开发检查；成功 fixture 覆盖已有输出时也隔离旧 canonical 包。
- Round 4 B4：override 可篡改必需图片的裁切或来源。必需图片的全部解析字段均受保护，回归包含 imageRect 和 imageRequired 攻击。
- Round 4 B5：独立 package 不验证磁盘图片。打包前现在校验每一个数据库图片引用，缺失 achievement 图片会拒绝打包。
- Round 4 B6：打包异常会破坏 canonical 包。归档先写唯一临时文件、校验条目后再原子替换；异常保留旧包且不遗留临时包。
- 最终 closure：相对 output 路径图片归档已修复；fixture 覆盖真实输出的旧包遗留问题已由 release block、隔离和回归测试关闭。

## 9. Final Verdict

- Status: passed。
- Round 5 独立 reviewer 未发现 blocking；范围内验证为 `python -m pytest -q` 102 passed、Ruff 与 diff check 通过，真实产物为 schema 4、3,688 实体、984/984 必需图片、25 类中文标签完整。
- OCR lane 仍因外部源码传输未获授权而保持 unavailable，未重试或绕过该限制。
