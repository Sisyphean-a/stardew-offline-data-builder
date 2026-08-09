# 注意事项

本项目是 Windows 命令行离线数据构建器，默认只处理用户本机《星露谷物语》官方资产。

## 硬约束

- 游戏事实只来自本机官方 `Content` / `Content (unpacked)`；不联网、不下载、不上传、不提交游戏资源。
- 不修改原始 `Content`；解析失败、缺失支持数据、未知覆盖、图片错误和质量失败必须进入报告并阻止可发布包。
- `data/aliases.zh-CN.json`、`data/categories.zh-CN.json`、`data/overrides.zh-CN.json` 只负责本地规范化或显式人工修正，不替代官方事实。
- `build`、`unpack`、`doctor` 省略 `--game-dir` 时，只在本机 Steam 找到唯一有效安装才自动选择；零个或多个候选都必须显式报错。

## 验证

- 后端检查：`python -m pytest`、`python -m ruff check .`
- 发布包必须由通过质量门禁的真实构建生成；`build-fixture` 仅供开发验证，禁止打包。

## 记忆入口

- 当前架构：`.codestable/architecture/INDEX.md`
- 当前领域规则：`.codestable/requirements/CONTEXT.md`
- 变化原因与旧称：`.codestable/history/`
