---
doc_type: goal-evidence-pack
goal: data-build-pipeline-remediation
status: complete
iteration: 2
updated_at: 2026-07-18
---

# 数据构建质量修复证据包

## 范围与改动

- 真实旧格式解析：成就、鞋类、怪物显示字段；大型可制作物、家具、鞋类和成就的官方图片规则。
- 质量契约：`invalid` 翻译状态、必需图片错误、schema v4 artifact metadata、质量派生报告和发布门禁。
- 打包契约：SQLite、manifest 和独立 `package` 保留同一 metadata；缺失、旧版本、语言不符、失败构建标记或 fixture 均拒绝打包。
- 完整性与覆盖契约：当前发布基线的全部 25 个实体类型缺失即阻断；手工覆盖后重算翻译状态，且不得降级必需图片或伪造 `image_path`。
- 失败隔离：普通失败和 fixture 覆盖已有输出时均写入 release block 并隔离 canonical 包；独立打包先验证数据库图片引用，再以临时归档校验后原子替换。
- 回归与勘误：真实格式图片端到端、失败门禁、陈旧包隔离、metadata 保真测试，以及历史发布完成表述的勘误链接。

## 自动验证

- `python -m pytest -q`：102 passed。
- `python -m ruff check .`：通过。
- `git diff --check`：通过。

## 真实官方资产验证

输出目录：`build/goal-real-output-final3`（未覆盖 `dist/`）。

- 3,688 条标准化实体；0 条 `missing` / `invalid` 翻译；0 条数据错误。
- 984 / 984 条必需图片已物化；成就 39、大型可制作物 182、家具 645、鞋类 18 条均有图片路径。
- `build-summary.json` 为 `success: true`、`quality: passed`；manifest 和 SQLite metadata 均为 schema v4，且 `publishable: true`。
- 独立 `python -m builder package --output build/goal-real-output-final3` 成功，manifest 的生成时间、游戏版本、源哈希、内容和质量均与 SQLite metadata 一致。
- 成就共用 `LooseSprites/Cursors.png` 的 `[192, 128, 64, 64]`；这是本机官方 `CollectionsPage` 的 tile 25 规则，第五个 `^` 字段不参与图片选择。

## 验收映射

| Goal acceptance | 证据 | 状态 |
| --- | --- | --- |
| Finding 01–06 回归 | `test_legacy_localization`、`test_legacy_visuals`、`test_quality_gate`、`test_artifact_metadata`、真实端到端测试 | passed |
| 数字 ID 不算完成翻译 | `test_translation_quality`、真实构建 0 invalid | passed |
| 图片状态可审计 | 图片端到端和失败门禁测试；真实构建 984/984 | passed |
| 质量状态一致且失败不发布 | `test_quality_gate`、metadata/manifest 测试 | passed |
| 完整中文类型目录与独立打包 | `test_artifact_metadata`、真实独立 package | passed |
| 历史声明勘误 | `completion-claim-correction.md` 和受影响历史记录指针 | passed |
| 独立 review 与功能验收 | 独立 closure review passed；可见 Task agent 对 final3 产物验收 pass | passed |
