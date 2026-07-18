---
doc_type: issue-fix
issue: 2026-07-18-data-build-pipeline-quality
status: implemented
updated_at: 2026-07-18
related: [data-build-pipeline-quality-analysis.md]
---

# 数据构建质量修复记录

## 实现

- 按真实格式解析成就、鞋类、怪物，并为成就、大型可制作物、家具和鞋类生成可验证的图片元数据与裁切尺寸。
- 图片物化对 `imageRequired` 缺源和越界裁切产生结构化错误；隐藏且不可社交、无纹理的 NPC 显式标为图片不适用。
- 翻译状态新增 `invalid`，纯数字展示名不再计入完成翻译。
- 新增质量门禁和 SQLite schema v4 `artifact_metadata`；报告、manifest、数据库、独立打包共享同一质量状态和完整类型目录。
- 质量失败时写出诊断数据库、报告和失败 manifest，但以 exit code 8 阻止新的 `.svdata` 生成。
- 若复用输出目录触发失败构建，旧包会以 `.failed` 后缀隔离，canonical `.svdata` 路径不再保留陈旧产物。
- fixture 入口同样聚合图片错误和质量状态；输入解析、基础数据断言或后续写入异常也会隔离旧 canonical 包。
- 当前发布基线的全部 25 个官方实体类型任一缺失即阻断；手工覆盖会重算展示文本质量，且不得禁用、改写或伪造必需图片元数据。
- 独立打包会验证所有数据库引用的图片文件，并以临时归档校验后原子替换 canonical 包，失败不覆盖旧包。
- fixture 输出显式标为仅开发检查、不可打包；覆盖已有输出时也会写 release block 并隔离 canonical 包。
- 为真实旧格式、裁切、metadata 保真、独立打包、失败隔离和 fixture 旧包路径补齐回归测试。

## 验证

- `python -m pytest -q`：102 passed。
- `python -m ruff check .`：通过。
- 本机真实官方资产构建到 `build/goal-real-output-final3` 并独立执行 `package --locale zh-CN`：成功；3,688 实体、0 不可用翻译、0 数据错误、984/984 必需图片物化。

## 结果

审计 Finding 01 至 06 的触发路径均已被测试和真实产物验证覆盖；新的包只会在质量状态为 `passed`、发布未被阻断且图片完整时生成。fixture 不再能遗留可误用的旧 canonical 包。
