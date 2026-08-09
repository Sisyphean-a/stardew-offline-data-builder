---
scope: shared:artifact-contract
applies-to:
  - package:builder
---

# 构建产物契约

构建元数据是 SQLite、manifest、报告和 `.svdata` 之间的共同契约；发布包只能由同一份通过质量校验的元数据产生。

## 规则

- `pipeline/artifact_metadata.py:build_artifact_metadata` 生成 schema、构建器版本、语言、生成时间、游戏版本、源哈希、可发布状态、内容统计和质量状态。
- `database/writer.py` 将该元数据写入 `build_meta.artifact_metadata`；`commands/package.py` 读取并校验它，再生成 manifest 和 ZIP。
- 质量状态不是提示信息：翻译缺失/无效、数据或图片错误、缺少实体类型中文标签都会使构建不可发布。
- fixture 的 metadata 明确 `publishable: false`；失败构建和 fixture 输出使用 `.release-blocked.json`，独立 `package` 必须拒绝。
- 图片引用必须解析到输出目录 `images/` 内的实际 `.webp` 文件；ZIP 先写临时文件、验证成员和 CRC，再原子替换正式包。

## 代码锚点

- `src/builder/pipeline/artifact_metadata.py`
- `src/builder/pipeline/quality.py`
- `src/builder/pipeline/package_integrity.py`
- `src/builder/pipeline/release_state.py`
- `src/builder/commands/build_output.py`
- `src/builder/commands/package.py`
- `src/builder/database/writer.py`
