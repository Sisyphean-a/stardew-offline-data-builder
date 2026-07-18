---
doc_type: audit-finding
audit: 2026-07-18-data-build-pipeline
finding_id: "bug-03"
nature: bug
severity: P1
confidence: high
suggested_action: cs-issue
status: open
---

# Finding 03：多个可视实体类别没有图片元数据且未被标为异常

## 速答

图片管线只处理已经携带 `imageSource` 的实体；没有该字段时静默保留无图实体。旧格式的大型制造物、家具、鞋类和成就没有建立该元数据，最终包中这四类共 884 条全部无图。

## 关键证据

- `src/builder/pipeline/images.py:51-54` — `imageSource` 不是字符串时，实体直接进入输出，没有错误记录。
- `src/builder/parsers/official.py:258-269` — `apply_image_metadata` 只为村民、带 `Texture` 的字典对象和普通 `object` 建立图片来源；没有处理旧格式的 `achievement`、`big_craftable`、`furniture`、`footwear`。
- 真实包查询结果：`achievement` 39/39、`big_craftable` 182/182、`furniture` 645/645、`footwear` 18/18 的 `image_path` 为空。
- `reports/errors.json` 仅有 1 条未找到村民头像的错误；上述 884 条无图记录没有任何对应错误或警告。

## 影响

这些类别在消费者中只能显示图片占位。构建报告无法区分“官方确实没有图片”和“构建器没有建立图片关联”，因此无图状态对发布者不可见。

## 建议动作

`cs-issue`。本审计按委托要求不提供修复方案。
