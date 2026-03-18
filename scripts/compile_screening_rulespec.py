#!/usr/bin/env python3
import argparse
import json
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from generate_screening_templates import (
    build_platform_capabilities,
    load_field_mapping,
    normalize_space,
    parse_sop_text,
)


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = ROOT_DIR / "temp" / "compiled_rulespec"
STRICT_SUPPORTED_PLATFORMS = ["tiktok", "instagram"]
ALL_PLATFORMS = ["tiktok", "instagram", "youtube"]
AMBIGUOUS_RULE_TYPES = {"manual_requirement", "needs_manual_review"}
CAPABILITY_GAP_NAMES = {"comment_text", "video_content_vision"}

SCREENING_SCOPE_TERMS = [
    "筛号",
    "审核",
    "资质",
    "基础数据",
    "数据审核",
    "内容风格",
    "内容场景",
    "排除项",
    "受众",
    "互动",
    "封面",
    "播放量",
    "中位数",
    "平均播放量",
    "评论",
    "标题",
    "文案",
    "标签",
    "语言",
    "地区",
    "简介",
    "场景",
    "through",
    "pass",
    "reject",
]

OUT_OF_SCOPE_TERMS = [
    "群发信",
    "发信",
    "回信",
    "追问",
    "报价",
    "飞书",
    "同步",
    "邮件",
    "邮箱",
    "建联",
    "跟进",
    "砍价",
    "合作意愿",
    "总邮箱",
    "大盘价",
    "运营成本",
    "服务费",
    "MCP",
    "签约",
    "触达",
]

METRIC_INTENT_MAP = {
    "mean_view_count": "view_count_mean",
    "median_view_count": "view_count_median",
}


def write_json(path, payload):
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def count_keyword_hits(text, keywords):
    haystack = normalize_space(text).lower()
    hits = 0
    for item in keywords:
        term = str(item or "").strip().lower()
        if term and term in haystack:
            hits += 1
    return hits


def is_out_of_scope_line(line):
    text = normalize_space(line)
    if not text:
        return False
    screening_hits = count_keyword_hits(text, SCREENING_SCOPE_TERMS)
    out_hits = count_keyword_hits(text, OUT_OF_SCOPE_TERMS)
    return out_hits > 0 and out_hits >= screening_hits


def classify_step_scope(step):
    title = normalize_space(step.get("title"))
    lines = [normalize_space(item) for item in step.get("lines", []) if normalize_space(item)]
    joined = " ".join([title] + lines)
    title_screening_hits = count_keyword_hits(title, SCREENING_SCOPE_TERMS)
    title_out_hits = count_keyword_hits(title, OUT_OF_SCOPE_TERMS)
    total_screening_hits = count_keyword_hits(joined, SCREENING_SCOPE_TERMS)
    total_out_hits = count_keyword_hits(joined, OUT_OF_SCOPE_TERMS)

    if "最终结果" in title or "最终判定" in title:
        return "screening"

    if title_out_hits > title_screening_hits and title_out_hits > 0:
        return "out_of_scope"

    if title_screening_hits > 0:
        return "screening"

    actionable_rules = [
        rule
        for rule in step.get("rules", [])
        if rule.get("check_type") not in AMBIGUOUS_RULE_TYPES
    ]
    if actionable_rules:
        return "screening"

    if total_out_hits > total_screening_hits and total_out_hits > 0:
        return "out_of_scope"

    return "screening"


def split_scope(parsed_sop):
    screening_steps = []
    out_of_scope_actions = []

    for step in parsed_sop.get("steps", []):
        scope = classify_step_scope(step)
        if scope == "out_of_scope":
            raw_lines = step.get("lines") or [step.get("title")]
            out_of_scope_actions.append(
                {
                    "step_title": step.get("title"),
                    "scope": "out_of_scope_actions",
                    "items": [normalize_space(item) for item in raw_lines if normalize_space(item)],
                }
            )
            continue

        kept_rules = []
        for rule in step.get("rules", []):
            if rule.get("check_type") in AMBIGUOUS_RULE_TYPES and is_out_of_scope_line(rule.get("source_line")):
                out_of_scope_actions.append(
                    {
                        "step_title": step.get("title"),
                        "scope": "out_of_scope_actions",
                        "items": [normalize_space(rule.get("source_line"))],
                    }
                )
                continue
            kept_rules.append(rule)

        step_copy = deepcopy(step)
        step_copy["rules"] = kept_rules
        screening_steps.append(step_copy)

    screening_rules = []
    for step in screening_steps:
        screening_rules.extend(step.get("rules", []))

    return {
        "goal": parsed_sop.get("goal") or "",
        "steps": screening_steps,
        "rules": screening_rules,
        "final_decision": deepcopy(parsed_sop.get("final_decision") or {}),
        "out_of_scope_actions": out_of_scope_actions,
    }


def build_rule_spec_rule(rule, index):
    compiled = {
        "id": f"rule_{index:03d}",
        "step_number": rule.get("step_number"),
        "step_title": rule.get("step_title"),
        "platforms": list(STRICT_SUPPORTED_PLATFORMS),
        "rule_type": rule.get("check_type"),
        "source_text": rule.get("source_line") or "",
        "subject": rule.get("subject"),
        "window": rule.get("window"),
        "operator": rule.get("operator"),
        "required_capabilities": list(rule.get("required_capabilities") or []),
    }

    metric = rule.get("metric")
    if metric:
        compiled["metric_intent"] = METRIC_INTENT_MAP.get(metric, metric)

    if rule.get("threshold") is not None:
        compiled["threshold"] = rule.get("threshold")
    if rule.get("threshold_days") is not None:
        compiled["threshold_days"] = rule.get("threshold_days")
    if rule.get("threshold_percent") is not None:
        compiled["threshold_percent"] = rule.get("threshold_percent")
    if rule.get("allowed_regions"):
        compiled["allowed_regions"] = list(rule.get("allowed_regions") or [])
    if rule.get("expected_language"):
        compiled["expected_language"] = rule.get("expected_language")
    if rule.get("keywords"):
        compiled["keywords"] = list(rule.get("keywords") or [])
    if rule.get("keyword_group"):
        compiled["keyword_group"] = rule.get("keyword_group")
    if rule.get("categories"):
        compiled["categories"] = list(rule.get("categories") or [])
    if rule.get("category"):
        compiled["category"] = rule.get("category")
    if rule.get("heuristic"):
        compiled["heuristic"] = rule.get("heuristic")
    if rule.get("extra_conditions"):
        compiled["extra_conditions"] = rule.get("extra_conditions")
    if rule.get("policy_reason"):
        compiled["policy_reason"] = rule.get("policy_reason")
    if rule.get("notes"):
        compiled["notes"] = rule.get("notes")

    return compiled


def build_rule_spec(parsed_sop):
    rules = [
        build_rule_spec_rule(rule, index)
        for index, rule in enumerate(parsed_sop.get("rules", []), start=1)
    ]
    return {
        "version": "v1",
        "compile_mode": "strict_deterministic",
        "scope": "screening_rules_only",
        "goal": parsed_sop.get("goal") or "",
        "platform_scope": {
            "strict_supported": list(STRICT_SUPPORTED_PLATFORMS),
            "unsupported": ["youtube"],
        },
        "rules": rules,
        "final_logic": parsed_sop.get("final_decision", {}).get("logic_hint") or "",
        "out_of_scope_actions": deepcopy(parsed_sop.get("out_of_scope_actions") or []),
    }


def build_platform_catalog():
    base_capabilities = build_platform_capabilities(load_field_mapping())
    strict_unsupported_note = (
        "V1 strict mode 只允许使用 config/field_mapping.json 中的机读字段词典；"
        "当前 YouTube 尚未进入该词典，因此整个平台标记为 unsupported。"
    )
    return {
        "tiktok": {
            "platform": "tiktok",
            "mode": "strict_supported",
            "mapping_basis": base_capabilities["tiktok"]["mapping_basis"],
            "capabilities": base_capabilities["tiktok"]["capabilities"],
            "platform_note": "",
        },
        "instagram": {
            "platform": "instagram",
            "mode": "strict_supported",
            "mapping_basis": base_capabilities["instagram"]["mapping_basis"],
            "capabilities": base_capabilities["instagram"]["capabilities"],
            "platform_note": "",
        },
        "youtube": {
            "platform": "youtube",
            "mode": "strict_unsupported",
            "mapping_basis": ["strict_mode: config/field_mapping.json 缺少 youtube_api"],
            "capabilities": {},
            "platform_note": strict_unsupported_note,
        },
    }


def summarize_statuses(matches):
    summary = {
        "matched": 0,
        "partial": 0,
        "missing_capabilities": 0,
        "ambiguous": 0,
        "unsupported": 0,
        "blocked_sensitive_attribute": 0,
    }
    for item in matches:
        status = item.get("status")
        if status in summary:
            summary[status] += 1
    return summary


def determine_match_status(rule, platform_info, capability_matches):
    if rule.get("rule_type") == "blocked_sensitive_attribute":
        return "blocked_sensitive_attribute"

    if platform_info["mode"] == "strict_unsupported":
        return "unsupported"

    if rule.get("rule_type") in AMBIGUOUS_RULE_TYPES:
        return "ambiguous"

    if not capability_matches:
        return "ambiguous"

    if any(item["name"] in CAPABILITY_GAP_NAMES and item["status"] in {"partial", "unsupported"} for item in capability_matches):
        return "missing_capabilities"

    if any(item["status"] == "unsupported" for item in capability_matches):
        return "unsupported"

    if any(item["status"] == "partial" for item in capability_matches):
        return "partial"

    return "matched"


def build_rule_match(rule, platform_name, platform_info):
    if rule.get("rule_type") == "blocked_sensitive_attribute":
        return {
            "rule_id": rule["id"],
            "platform": platform_name,
            "status": "blocked_sensitive_attribute",
            "rule_type": rule.get("rule_type"),
            "source_text": rule.get("source_text") or "",
            "step_title": rule.get("step_title"),
            "matched_fields": [],
            "required_capabilities": list(rule.get("required_capabilities") or []),
            "matched_capabilities": [],
            "notes": rule.get("policy_reason") or "受保护属性规则不能进入自动化审核。",
            "confidence_mode": "deterministic",
        }

    if platform_info["mode"] == "strict_unsupported":
        return {
            "rule_id": rule["id"],
            "platform": platform_name,
            "status": "unsupported",
            "rule_type": rule.get("rule_type"),
            "source_text": rule.get("source_text") or "",
            "step_title": rule.get("step_title"),
            "matched_fields": [],
            "required_capabilities": list(rule.get("required_capabilities") or []),
            "matched_capabilities": [],
            "notes": platform_info["platform_note"],
            "confidence_mode": "deterministic",
        }

    capability_matches = []
    matched_fields = []
    notes = []
    missing_capabilities = []

    for capability_name in rule.get("required_capabilities") or []:
        capability = deepcopy(platform_info["capabilities"].get(capability_name) or {})
        capability_status = capability.get("status") or "unsupported"
        capability_fields = list(capability.get("fields") or [])
        capability_note = capability.get("notes") or ""
        capability_matches.append(
            {
                "name": capability_name,
                "status": capability_status,
                "fields": capability_fields,
                "notes": capability_note,
            }
        )
        matched_fields.extend(capability_fields)
        if capability_note:
            notes.append(capability_note)
        if capability_status in {"partial", "unsupported"}:
            missing_capabilities.append(capability_name)

    status = determine_match_status(rule, platform_info, capability_matches)
    if rule.get("notes"):
        notes.insert(0, rule.get("notes"))

    return {
        "rule_id": rule["id"],
        "platform": platform_name,
        "status": status,
        "rule_type": rule.get("rule_type"),
        "source_text": rule.get("source_text") or "",
        "step_title": rule.get("step_title"),
        "matched_fields": sorted(set(matched_fields)),
        "required_capabilities": list(rule.get("required_capabilities") or []),
        "matched_capabilities": capability_matches,
        "missing_capabilities": sorted(set(missing_capabilities)),
        "notes": " ".join(item for item in notes if item).strip(),
        "confidence_mode": "deterministic",
    }


def build_field_match_report(rule_spec):
    platform_catalog = build_platform_catalog()
    platform_reports = {}

    for platform_name in ALL_PLATFORMS:
        platform_info = platform_catalog[platform_name]
        rule_matches = [
            build_rule_match(rule, platform_name, platform_info)
            for rule in rule_spec.get("rules", [])
        ]
        platform_reports[platform_name] = {
            "platform": platform_name,
            "platform_status": "supported" if platform_info["mode"] == "strict_supported" else "unsupported",
            "mapping_basis": platform_info["mapping_basis"],
            "platform_note": platform_info["platform_note"],
            "summary": summarize_statuses(rule_matches),
            "rule_matches": rule_matches,
        }

    return {
        "version": "v1",
        "compile_mode": "strict_deterministic",
        "platforms": platform_reports,
    }


def build_missing_capabilities_report(field_match_report):
    items = []
    for platform_name, platform_report in (field_match_report.get("platforms") or {}).items():
        for item in platform_report.get("rule_matches", []):
            if item.get("status") != "missing_capabilities":
                continue
            items.append(
                {
                    "platform": platform_name,
                    "rule_id": item.get("rule_id"),
                    "source_text": item.get("source_text"),
                    "required": item.get("missing_capabilities") or item.get("required_capabilities") or [],
                    "reason": item.get("notes") or "当前能力链路不足。",
                }
            )

    return {
        "version": "v1",
        "items": items,
    }


def render_review_notes(rule_spec, field_match_report, missing_capabilities):
    lines = [
        "# RuleSpec 编译摘要",
        "",
        f"- 审核目标：{rule_spec.get('goal') or '未提供'}",
        f"- 已编译规则数：{len(rule_spec.get('rules') or [])}",
        f"- 严格支持平台：{', '.join(rule_spec.get('platform_scope', {}).get('strict_supported') or []) or '无'}",
        f"- 暂不支持平台：{', '.join(rule_spec.get('platform_scope', {}).get('unsupported') or []) or '无'}",
    ]

    if rule_spec.get("final_logic"):
        lines.append(f"- 最终逻辑：{rule_spec['final_logic']}")

    out_of_scope_actions = rule_spec.get("out_of_scope_actions") or []
    lines.append(f"- 范围外动作：{len(out_of_scope_actions)}")
    lines.append("")
    lines.append("## 平台结果")
    lines.append("")

    for platform_name in ALL_PLATFORMS:
        report = (field_match_report.get("platforms") or {}).get(platform_name) or {}
        summary = report.get("summary") or {}
        lines.append(f"### {platform_name}")
        lines.append("")
        if report.get("platform_note"):
            lines.append(f"- 平台说明：{report['platform_note']}")
        lines.append(f"- matched: {summary.get('matched', 0)}")
        lines.append(f"- partial: {summary.get('partial', 0)}")
        lines.append(f"- missing_capabilities: {summary.get('missing_capabilities', 0)}")
        lines.append(f"- ambiguous: {summary.get('ambiguous', 0)}")
        lines.append(f"- unsupported: {summary.get('unsupported', 0)}")
        lines.append(f"- blocked_sensitive_attribute: {summary.get('blocked_sensitive_attribute', 0)}")
        lines.append("")

    if missing_capabilities.get("items"):
        lines.append("## 能力缺口")
        lines.append("")
        for item in missing_capabilities["items"]:
            required = ", ".join(item.get("required") or []) or "未标注"
            lines.append(f"- {item['platform']} · {item['rule_id']} · {required}：{item['reason']}")
        lines.append("")

    if out_of_scope_actions:
        lines.append("## 范围外动作")
        lines.append("")
        for item in out_of_scope_actions:
            raw_text = "；".join(item.get("items") or []) or item.get("step_title") or ""
            lines.append(f"- {item.get('step_title') or '未命名步骤'}：{raw_text}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def persist_compile_output(output_dir, rule_spec, field_match_report, missing_capabilities, review_notes_markdown):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    write_json(output_path / "rule_spec.json", rule_spec)
    write_json(output_path / "field_match_report.json", field_match_report)
    write_json(output_path / "missing_capabilities.json", missing_capabilities)
    (output_path / "review_notes.md").write_text(review_notes_markdown, encoding="utf-8")
    return str(output_path)


def compile_rulespec_from_text(text, output_dir=None):
    raw_text = normalize_space(text)
    if not raw_text:
        raise ValueError("sop_text 不能为空")

    parsed = parse_sop_text(text)
    scoped = split_scope(parsed)
    rule_spec = build_rule_spec(scoped)
    field_match_report = build_field_match_report(rule_spec)
    missing_capabilities = build_missing_capabilities_report(field_match_report)
    review_notes_markdown = render_review_notes(rule_spec, field_match_report, missing_capabilities)

    persisted_dir = None
    if output_dir:
        persisted_dir = persist_compile_output(
            output_dir,
            rule_spec,
            field_match_report,
            missing_capabilities,
            review_notes_markdown,
        )

    parsed_summary = {
        "goal": scoped.get("goal") or "",
        "steps": [
            {
                "title": step.get("title"),
                "rule_count": len(step.get("rules") or []),
            }
            for step in scoped.get("steps", [])
        ],
        "final_decision": scoped.get("final_decision") or {},
        "out_of_scope_actions": scoped.get("out_of_scope_actions") or [],
    }

    return {
        "output_dir": persisted_dir,
        "parsed_sop": parsed_summary,
        "rule_spec": rule_spec,
        "field_match_report": field_match_report,
        "missing_capabilities": missing_capabilities,
        "review_notes_markdown": review_notes_markdown,
        "compiled_at": datetime.utcnow().isoformat() + "Z",
    }


def read_input_text(path_value):
    if path_value:
        return Path(path_value).read_text(encoding="utf-8")
    return sys.stdin.read()


def main():
    parser = argparse.ArgumentParser(description="Compile screening SOP text into a strict RuleSpec.")
    parser.add_argument("--input", help="Path to a txt or md file containing screening SOP text")
    parser.add_argument("--output-dir", help="Directory to persist compile artifacts")
    args = parser.parse_args()

    text = read_input_text(args.input)
    if not normalize_space(text):
        raise SystemExit("ERROR: input text is empty")

    result = compile_rulespec_from_text(text, output_dir=args.output_dir)
    print(
        json.dumps(
            {
                "output_dir": result.get("output_dir"),
                "compiled_at": result.get("compiled_at"),
                "rule_count": len(result.get("rule_spec", {}).get("rules") or []),
                "out_of_scope_actions": len(result.get("rule_spec", {}).get("out_of_scope_actions") or []),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
