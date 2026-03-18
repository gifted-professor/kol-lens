import json
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config" / "field_mapping.json"
DOC_PATH = ROOT_DIR / "docs" / "field_dictionary.md"


def load_mapping():
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def clip_text(value, limit=100):
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."


def format_example(example):
    if example is None:
        return "`null`"
    if isinstance(example, (dict, list)):
        return "`" + clip_text(json.dumps(example, ensure_ascii=False)) + "`"
    return "`" + clip_text(example) + "`"


def usage_label(field):
    if field.get("used_in_active_screening"):
        return "主链路"
    if field.get("used_in_any_screening_code"):
        return "备用逻辑"
    return "未使用"


def render_field_table(fields, include_excel_columns=False):
    if include_excel_columns:
        lines = [
            "| 字段名 | 类型 | 原始列名 | 说明 | 示例值 | 当前使用 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    else:
        lines = [
            "| 字段路径 | 类型 | 说明 | 示例值 | 当前使用 |",
            "| --- | --- | --- | --- | --- |",
        ]

    for field_name, meta in fields.items():
        description = meta.get("description", "")
        example = format_example(meta.get("example"))
        usage = usage_label(meta)
        if include_excel_columns:
            excel_columns = ", ".join(meta.get("excel_columns") or []) or "-"
            lines.append(
                f"| `{field_name}` | `{meta.get('type', '')}` | {excel_columns} | {description} | {example} | {usage} |"
            )
        else:
            lines.append(
                f"| `{field_name}` | `{meta.get('type', '')}` | {description} | {example} | {usage} |"
            )
    return lines


def render_flow_table(flows):
    lines = [
        "| 流程 ID | 函数 | 状态 | 说明 | 当前读取字段 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for flow_id, flow in flows.items():
        reads = ", ".join(f"`{field}`" for field in flow.get("reads", []))
        lines.append(
            f"| `{flow_id}` | `{flow.get('function', '')}` | `{flow.get('status', '')}` | {flow.get('summary', '')} | {reads} |"
        )
    return lines


def build_markdown(mapping):
    meta = mapping.get("meta", {})
    upload = mapping.get("upload_metadata", {})
    instagram = mapping.get("instagram_api", {})
    tiktok = mapping.get("tiktok_api", {})

    lines = [
        "# 字段字典",
        "",
        "> 此文件由 `scripts/build_field_dictionary.py` 根据 `config/field_mapping.json` 生成。",
        f"> 最后同步：{meta.get('version', '')}",
        "",
        "## 说明",
        "",
        "- 这份字典是 PRD 和代码之间的字段总览，目的是回答“有哪些字段、来自哪里、当前有没有被初筛读取”。",
        "- `主链路` 表示当前批量初筛真实会读取该字段。",
        "- `备用逻辑` 表示代码里还有备用/旧逻辑会读取该字段，但不是当前主入口。",
        "- `未使用` 表示当前只存档或导出，不参与初筛判断。",
        "",
        "## 上传表字段（Upload Metadata）",
        "",
        upload.get("description", ""),
        "",
        f"内容列候选：{', '.join(f'`{item}`' for item in upload.get('content_column_candidates', []))}",
        "",
    ]
    lines.extend(render_field_table(upload.get("fields", {}), include_excel_columns=True))
    lines.extend(
        [
            "",
            "## Instagram API 字段",
            "",
            instagram.get("description", ""),
            "",
            "### 主页级字段",
            "",
        ]
    )
    lines.extend(render_field_table(instagram.get("profile_fields", {})))
    lines.extend(
        [
            "",
            "### 帖子级字段（latestPosts[]）",
            "",
        ]
    )
    lines.extend(render_field_table(instagram.get("post_fields", {})))
    lines.extend(
        [
            "",
            "### 当前代码中的 Instagram 流程",
            "",
        ]
    )
    lines.extend(render_flow_table(instagram.get("screening_flows", {})))
    lines.extend(
        [
            "",
            "## TikTok API 字段",
            "",
            tiktok.get("description", ""),
            "",
            "### 作者级字段（authorMeta）",
            "",
        ]
    )
    lines.extend(render_field_table(tiktok.get("author_fields", {})))
    lines.extend(
        [
            "",
            "### 视频级字段",
            "",
        ]
    )
    lines.extend(render_field_table(tiktok.get("post_fields", {})))
    lines.extend(
        [
            "",
            "### 当前代码中的 TikTok 流程",
            "",
        ]
    )
    lines.extend(render_flow_table(tiktok.get("screening_flows", {})))
    lines.extend(
        [
            "",
            "## 维护规则",
            "",
            "- 改 `backend/app.py` 的上传字段归一化逻辑时，要同步更新 `config/field_mapping.json` 并重新生成本文件。",
            "- 改 `scripts/data_cleaner.py` 的主链路字段读取、关键词、阈值或入口函数时，要同步更新本文件和对应平台 PRD。",
            "- 新增平台或新增大模型前置判断时，先在字典里补字段，再改规则。",
            "",
        ]
    )
    return "\n".join(lines)


def main():
    mapping = load_mapping()
    markdown = build_markdown(mapping)
    DOC_PATH.write_text(markdown + "\n", encoding="utf-8")
    print(f"Wrote {DOC_PATH}")


if __name__ == "__main__":
    main()
