# 阶段 1 到阶段 4 功能验收

## Reviewer

- Task agent：`019f6645-3ea6-7e01-b18c-05014fb30049`
- 角色：独立只读功能验收 agent
- 关闭结果：已消费结果后关闭成功

## Scope

只验收阶段 1 到阶段 4：

- fixture 数据闭环
- `inspect`
- `doctor`
- `unpack`
- 四类官方中文解析
- `pytest` 与 `ruff check .`

## Acceptance Checks

1. `python -m builder build-fixture --output .\dist` 可生成可检索 SQLite。
2. `python -m builder inspect .\dist\stardew.db` 可输出数据库概要。
3. `doctor` 能检查游戏目录、Content、DLL、StardewXnbHack、社区数据目录与 SQLite FTS4。
4. `unpack` 能调用外部程序，支持跳过已有结果与 `--force`。
5. 普通物品、作物、鱼类、村民四类官方中文解析具备测试覆盖。
6. `pytest` 与 `ruff check .` 通过。

## Functional Evidence

- `python -m builder build-fixture --output .\dist` 输出 `已生成数据库：dist\stardew.db`。
- `python -m builder inspect .\dist\stardew.db` 输出版本 1、语言 `zh-CN`、四类实体各 1 条、`FTS 搜索：正常`。
- `pytest` 通过，结果为 `12 passed`。
- `ruff check .` 通过，结果为 `All checks passed!`。
- 手动构造中文和空格路径的临时游戏目录，`doctor` 输出 `环境检查通过`。
- 使用临时脚本工具测试 `unpack --force`，可生成 JSON；已有 JSON 时再次执行会跳过。
- 验收 agent 独立确认 `防风草`、`parsnip`、`fang feng cao`、`ffc` 均命中 `object:24`。

## Verdict

pass

## Residual Risks

- 默认工具探测已改为优先 `StardewXnbHack.exe`、回退 `StardewXnbHack.py`，但当前仓库内仍只用脚本夹具验证了解包执行链路，未用真实 `.exe` 做端到端回归。
- 阶段 4 的解析覆盖基于最小虚构夹具，不代表真实游戏所有 JSON 变体都已验证。

## Follow-up

- 最终实现提交见：`3cf2ed6`、`b509a8d`、`7c0863b`、`e9b32d4`、`f1d030a`
- 对应 final iteration：`iterations/001.md`
