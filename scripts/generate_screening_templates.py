#!/usr/bin/env python3
import argparse
import json
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
FIELD_MAPPING_PATH = ROOT_DIR / "config" / "field_mapping.json"
DEFAULT_OUTPUT_ROOT = ROOT_DIR / "temp" / "generated_templates"

OPTION_RE = re.compile(r"^(?:[A-Z]|[①②③④⑤⑥⑦⑧⑨]|[一二三四五六七八九十])[\.、:：]\s*(.+)$")
WINDOW_RE = re.compile(r"(?:最近|近期|前)\s*前?\s*(\d+)\s*(?:个|条)")
STEP_NUMBER_RE = re.compile(r"步骤\s*(\d+)")
NUMERIC_STEP_HEADING_RE = re.compile(r"^(\d+)\s*[\.、:：]\s*(.+)$")

RELATIONSHIP_KEYWORDS = ["partner", "boyfriend", "girlfriend", "husband", "wife"]
PROTECTED_ATTRIBUTE_TERMS = [
    "黑人",
    "白人",
    "黄种人",
    "亚裔",
    "拉丁裔",
    "中老年",
    "老年",
    "老人",
    "年龄",
]
VISUAL_HINT_TERMS = [
    "封面",
    "出镜",
    "场景",
    "绿幕",
    "跳舞",
    "互动",
    "产品",
    "宠物",
    "孩子",
    "情侣",
    "自拍",
    "pov",
]


def load_field_mapping():
    with FIELD_MAPPING_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_space(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def strip_bullet_prefix(line):
    return re.sub(r"^[\-\*\u2022]\s*", "", line).strip()


def slugify(text):
    base = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "_", str(text or "").strip().lower())
    base = base.strip("_")
    return base or "rule"


def extract_heading(line):
    bracket_match = re.match(r"^[【\[](.+?)[】\]]$", line)
    if bracket_match:
        return bracket_match.group(1).strip()
    numeric_step_match = NUMERIC_STEP_HEADING_RE.match(line)
    if numeric_step_match:
        return f"步骤 {numeric_step_match.group(1)}：{numeric_step_match.group(2).strip()}"
    if re.match(r"^步骤\s*\d+", line):
        return line.strip()
    return None


def extract_window(text, default=None):
    match = WINDOW_RE.search(str(text or ""))
    if match:
        return int(match.group(1))
    return default


def extract_operator_and_value(text, phrase, expect_percent=False):
    operators = {
        ">=": ">=",
        "≥": ">=",
        ">": ">",
        "大于": ">",
        "超过": ">",
    }
    for raw_op, normalized in operators.items():
        pattern = re.escape(phrase) + rf"\s*(?:占比\s*)?{re.escape(raw_op)}\s*(\d+(?:\.\d+)?)"
        if expect_percent:
            pattern += r"\s*%"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = float(match.group(1))
            if value.is_integer():
                value = int(value)
            return normalized, value
    return None, None


def extract_percent_rule(line):
    match = re.search(
        r"(?:若|如果)?\s*(.+?)(?:占比)?\s*(>=|>|≥|大于|超过)\s*(\d+(?:\.\d+)?)\s*%",
        line,
        re.IGNORECASE,
    )
    if not match:
        return None
    label = normalize_space(match.group(1))
    label = re.sub(r"^(出现|为|多为)", "", label).strip()
    value = float(match.group(3))
    if value.is_integer():
        value = int(value)
    operator = ">=" if match.group(2) in {">=", "≥"} else ">"
    return {
        "label": label,
        "operator": operator,
        "threshold": value,
    }


def extract_keywords_from_line(line):
    quoted = [normalize_space(item) for item in re.findall(r"[\"“”](.*?)[\"“”]", line)]
    if quoted:
        return [item for item in quoted if item]
    lowered = line.lower()
    hits = [item for item in RELATIONSHIP_KEYWORDS if item in lowered]
    return hits


def detect_subject(text):
    lowered = str(text or "").lower()
    if "评论" in text or "emoji" in lowered:
        return "comments"
    if "标题及封面" in text:
        return "titles_and_covers"
    if "封面及内容" in text:
        return "covers_and_content"
    if "标题和封面" in text:
        return "titles_and_covers"
    if "封面" in text:
        return "covers"
    if "标题" in text:
        return "titles"
    if "文案" in text or "caption" in lowered:
        return "captions"
    if "简介" in text or "主页" in text:
        return "profile"
    if "播放量" in text:
        return "posts"
    if "视频" in text or "帖子" in text or "内容" in text:
        return "posts"
    return None


def is_scene_intro(line):
    return "判断是否出现以下任一" in line or "判断是否出现以下特征" in line


def is_significant_line(line):
    text = normalize_space(line)
    if not text:
        return False
    if text.startswith("http://") or text.startswith("https://"):
        return False
    if OPTION_RE.match(text):
        return False
    trivial_prefixes = [
        "抓取",
        "查看",
        "确认",
        "计算",
        "判断是否",
        "判断以下",
    ]
    if any(text.startswith(prefix) for prefix in trivial_prefixes):
        return False
    return True


def build_manual_requirement_rule(step, source_line, note):
    return build_rule(
        step,
        source_line,
        "manual_requirement",
        "unsupported",
        [],
        label=source_line[:32],
        notes=note,
    )


def build_rule(step, source_line, check_type, execution_layer, required_capabilities, **extra):
    step_number = extract_step_number(step["title"])
    label = extra.get("label") or check_type
    rule_id = f"step_{step_number}_{slugify(label)}"
    rule = {
        "id": rule_id,
        "step_number": step_number,
        "step_title": step["title"],
        "source_line": source_line,
        "check_type": check_type,
        "execution_layer": execution_layer,
        "required_capabilities": required_capabilities,
    }
    rule.update(extra)
    return rule


def extract_step_number(title):
    match = STEP_NUMBER_RE.search(str(title or ""))
    if match:
        return int(match.group(1))
    return 0


def parse_sop_text(text):
    goal_lines = []
    final_lines = []
    steps = []
    current_mode = "preamble"
    current_step = None

    for raw_line in text.splitlines():
        clean = normalize_space(strip_bullet_prefix(raw_line))
        if not clean:
            continue

        heading = extract_heading(clean)
        if heading:
            if "审核目标" in heading:
                current_mode = "goal"
                current_step = None
            elif "最终结果" in heading or "最终判定" in heading:
                current_mode = "final"
                current_step = None
            elif "步骤" in heading:
                current_mode = "step"
                current_step = {"title": heading, "lines": []}
                steps.append(current_step)
            else:
                current_mode = "preamble"
                current_step = None
            continue

        if current_mode == "goal":
            goal_lines.append(clean)
        elif current_mode == "final":
            final_lines.append(clean)
        elif current_mode == "step" and current_step is not None:
            current_step["lines"].append(clean)
        else:
            if not steps:
                goal_lines.append(clean)
            elif current_step is not None:
                current_step["lines"].append(clean)

    parsed_steps = []
    all_rules = []
    for step in steps:
        parsed = parse_step_rules(step)
        parsed_steps.append(parsed)
        all_rules.extend(parsed["rules"])

    return {
        "goal": " ".join(goal_lines).strip(),
        "steps": parsed_steps,
        "final_decision": build_final_decision(final_lines),
        "rules": all_rules,
    }


def parse_step_rules(step):
    context = {
        "window": extract_window(step["title"]),
        "subject": detect_subject(step["title"]),
    }
    rules = []
    consumed = set()
    scene_buffer = None

    for idx, line in enumerate(step["lines"]):
        current_line = normalize_space(line)

        if scene_buffer and OPTION_RE.match(current_line):
            option_text = OPTION_RE.match(current_line).group(1).strip()
            scene_buffer["options"].append(option_text)
            scene_buffer["line_indexes"].append(idx)
            consumed.add(idx)
            continue

        if scene_buffer and (current_line.startswith("若") or current_line.startswith("如果")):
            rules.append(
                build_scene_rule(
                    step,
                    current_line,
                    scene_buffer["options"],
                    scene_buffer["context"],
                )
            )
            consumed.update(scene_buffer["line_indexes"])
            consumed.add(idx)
            scene_buffer = None
            continue

        detected_window = extract_window(current_line, default=context.get("window"))
        detected_subject = detect_subject(current_line)
        if detected_window is not None:
            context["window"] = detected_window
            consumed.add(idx)
        if detected_subject:
            context["subject"] = detected_subject
            consumed.add(idx)

        if is_scene_intro(current_line):
            scene_buffer = {
                "options": [],
                "context": deepcopy(context),
                "line_indexes": [idx],
            }
            consumed.add(idx)
            continue

        if contains_protected_attribute(current_line):
            rules.append(
                build_rule(
                    step,
                    current_line,
                    "blocked_sensitive_attribute",
                    "blocked",
                    [],
                    status="blocked_sensitive_attribute",
                    label="sensitive_attribute",
                    policy_reason="受保护属性规则不能进入自动化审核模板",
                )
            )
            consumed.add(idx)
            continue

        line_rules = []
        line_rules.extend(parse_region_language_rule(step, current_line, context))
        line_rules.extend(parse_metric_rules(step, current_line, context))
        line_rules.extend(parse_comment_rule(step, current_line, context))
        line_rules.extend(parse_keyword_presence_rule(step, current_line, context))
        line_rules.extend(parse_ratio_rule(step, current_line, context))
        line_rules.extend(parse_single_vision_rule(step, current_line, context))
        line_rules.extend(parse_activity_rule(step, current_line, context))

        if line_rules:
            rules.extend(line_rules)
            consumed.add(idx)

    if scene_buffer and scene_buffer["options"]:
        rules.append(
            build_rule(
                step,
                " / ".join(scene_buffer["options"]),
                "needs_manual_review",
                "unsupported",
                [],
                label="scene_rule_incomplete",
                notes="识别到场景候选项，但缺少明确的通过/拒绝阈值描述",
            )
        )
        consumed.update(scene_buffer["line_indexes"])

    unmapped_lines = [
        line
        for idx, line in enumerate(step["lines"])
        if idx not in consumed and is_significant_line(line)
    ]

    if unmapped_lines:
        default_note = "当前无法自动映射为三平台审核规则，需人工补充为流程动作、阈值或执行节点。"
        for line in unmapped_lines:
            rules.append(build_manual_requirement_rule(step, line, default_note))
        unmapped_lines = []

    if not rules:
        fallback_line = "；".join(step["lines"]).strip()
        if not fallback_line:
            fallback_line = step["title"].split("：", 1)[-1].strip()
        rules.append(build_manual_requirement_rule(step, fallback_line, "当前解析器未识别到可用规则。"))

    return {
        "title": step["title"],
        "lines": step["lines"],
        "rules": rules,
        "unmapped_lines": unmapped_lines,
    }


def contains_protected_attribute(line):
    lowered = str(line or "").lower()
    return any(term in line or term in lowered for term in PROTECTED_ATTRIBUTE_TERMS)


def parse_region_language_rule(step, line, context):
    rules = []
    if ("美国" in line or "加拿大" in line or "US" in line or "CA" in line) and "地区" in line:
        rules.append(
            build_rule(
                step,
                line,
                "region_gate",
                "rule_engine",
                ["region_signal"],
                label="region_gate",
                allowed_regions=["US", "CA"],
                window=context.get("window"),
                subject=context.get("subject") or "profile",
            )
        )
    if "英语" in line or "english" in line.lower():
        rules.append(
            build_rule(
                step,
                line,
                "language_gate",
                "rule_engine",
                ["language_signal"],
                label="language_gate",
                expected_language="english",
                window=context.get("window"),
                subject=context.get("subject") or "profile",
            )
        )
    return rules


def parse_metric_rules(step, line, context):
    rules = []
    mean_op, mean_value = extract_operator_and_value(line, "平均播放量")
    if mean_value is not None:
        rules.append(
            build_rule(
                step,
                line,
                "metric_threshold",
                "rule_engine",
                ["view_count"],
                label="mean_view_count",
                metric="mean_view_count",
                operator=mean_op,
                threshold=mean_value,
                window=context.get("window"),
                subject=context.get("subject") or "posts",
            )
        )
    median_op, median_value = extract_operator_and_value(line, "中位数播放量")
    if median_value is not None:
        rules.append(
            build_rule(
                step,
                line,
                "metric_threshold",
                "rule_engine",
                ["view_count"],
                label="median_view_count",
                metric="median_view_count",
                operator=median_op,
                threshold=median_value,
                window=context.get("window"),
                subject=context.get("subject") or "posts",
            )
        )
    return rules


def parse_comment_rule(step, line, context):
    if "评论" not in line and "emoji" not in line.lower():
        return []
    if "emoji" not in line.lower():
        return []
    return [
        build_rule(
            step,
            line,
            "comment_quality",
            "future_collection",
            ["comment_text"],
            label="emoji_comment_quality",
            heuristic="emoji_dominant",
            window=context.get("window"),
            subject="comments",
        )
    ]


def parse_keyword_presence_rule(step, line, context):
    keywords = extract_keywords_from_line(line)
    if not keywords:
        return []
    return [
        build_rule(
            step,
            line,
            "keyword_presence",
            "rule_engine",
            ["text_content"],
            label="keyword_presence",
            keywords=keywords,
            window=context.get("window"),
            subject=context.get("subject") or "titles",
        )
    ]


def parse_ratio_rule(step, line, context):
    extracted = extract_percent_rule(line)
    if not extracted:
        return []

    label = extracted["label"]
    subject = context.get("subject") or "posts"
    lowered = label.lower()
    looks_visual = ("评论" not in line and subject != "comments") and (
        subject in {"covers", "covers_and_content", "titles_and_covers"} or any(
            term in label or term in lowered for term in VISUAL_HINT_TERMS
        )
    )

    if looks_visual:
        required = ["cover_vision"]
        if subject in {"covers_and_content", "titles_and_covers"} or "内容" in line:
            required.append("video_content_vision")
        extra_conditions = None
        if "且" in line:
            extra_conditions = normalize_space(line.split("且", 1)[1])
        return [
            build_rule(
                step,
                line,
                "vision_ratio_threshold",
                "vision_review",
                required,
                label=label,
                category=label,
                operator=extracted["operator"],
                threshold_percent=extracted["threshold"],
                extra_conditions=extra_conditions,
                window=context.get("window"),
                subject=subject,
            )
        ]

    return [
        build_rule(
            step,
            line,
            "keyword_ratio",
            "rule_engine",
            ["text_content"],
            label=label,
            keyword_group=label,
            operator=extracted["operator"],
            threshold_percent=extracted["threshold"],
            window=context.get("window"),
            subject=subject,
        )
    ]


def parse_single_vision_rule(step, line, context):
    if "绿幕" in line:
        required = ["cover_vision"]
        if context.get("subject") in {"covers_and_content", "titles_and_covers"} or "内容" in line:
            required.append("video_content_vision")
        return [
            build_rule(
                step,
                line,
                "vision_presence",
                "vision_review",
                required,
                label="green_screen",
                categories=["绿幕背景"],
                operator="contains_any",
                threshold=1,
                window=context.get("window"),
                subject=context.get("subject") or "covers",
            )
        ]
    return []


def parse_activity_rule(step, line, context):
    day_match = re.search(r"(\d+)\s*天", line)
    if not day_match or ("更新" not in line and "最近一条" not in line):
        return []
    return [
        build_rule(
            step,
            line,
            "activity_recency",
            "rule_engine",
            ["recency_timestamp"],
            label="activity_recency",
            operator="<=",
            threshold_days=int(day_match.group(1)),
            window=context.get("window"),
            subject=context.get("subject") or "posts",
        )
    ]


def build_scene_rule(step, source_line, options, context):
    required = ["cover_vision"]
    subject = context.get("subject") or "covers"
    if subject in {"covers_and_content", "titles_and_covers"} or "内容" in source_line:
        required.append("video_content_vision")
    return build_rule(
        step,
        source_line,
        "vision_presence",
        "vision_review",
        required,
        label="scene_presence",
        categories=options,
        operator="at_least",
        threshold=1,
        window=context.get("window"),
        subject=subject,
    )


def build_final_decision(lines):
    raw_text = " ".join(lines).strip()
    positive_steps = []
    negative_steps = []

    positive_match = re.search(r"(?:同时满足|满足|符合)(.+?)(?:且|并且|最终|否则|$)", raw_text)
    if positive_match:
        positive_steps = [int(item) for item in re.findall(r"步骤\s*(\d+)", positive_match.group(1))]

    negative_match = re.search(r"(?:不触发|未触发)(.+?)(?:且|并且|最终|否则|$)", raw_text)
    if negative_match:
        negative_steps = [int(item) for item in re.findall(r"步骤\s*(\d+)", negative_match.group(1))]

    logic_parts = []
    if positive_steps:
        logic_parts.extend([f"step_{item}" for item in positive_steps])
    if negative_steps:
        logic_parts.extend([f"!step_{item}" for item in negative_steps])

    return {
        "raw_lines": lines,
        "logic_hint": " && ".join(logic_parts) if logic_parts else "",
    }


def build_platform_capabilities(mapping):
    upload_fields = mapping.get("upload_metadata", {}).get("fields", {})
    instagram_fields = mapping.get("instagram_api", {})
    tiktok_fields = mapping.get("tiktok_api", {})

    return {
        "tiktok": {
            "mapping_basis": [
                "config/field_mapping.json:tiktok_api",
                "scripts/data_cleaner.py:check_tiktok_tapo",
            ],
            "capabilities": {
                "view_count": {
                    "status": "supported",
                    "fields": ["tiktok_api.playCount"],
                    "notes": "当前主链路已使用 TikTok 播放量均值/中位数门槛。",
                },
                "text_content": {
                    "status": "supported",
                    "fields": ["tiktok_api.text", "tiktok_api.hashtags[].name"],
                    "notes": "当前主链路已使用文案与标签做内容比例判断。",
                },
                "region_signal": {
                    "status": "unsupported",
                    "fields": [],
                    "notes": "当前没有稳定的 TikTok 地区资格字段或主链路规则。",
                },
                "language_signal": {
                    "status": "partial",
                    "fields": ["tiktok_api.textLanguage"],
                    "notes": "字段存在，但当前主链路未使用，且只能反映文案语言。",
                },
                "recency_timestamp": {
                    "status": "partial",
                    "fields": ["tiktok_api.createTimeISO"],
                    "notes": "字段存在，但当前仅备用逻辑读取。",
                },
                "cover_vision": {
                    "status": "supported",
                    "fields": [
                        "tiktok_api.slideshowImageLinks[].tiktokLink",
                        "tiktok_api.videoMeta.originalCoverUrl",
                        "tiktok_api.videoMeta.coverUrl",
                    ],
                    "notes": "当前视觉复核基于封面九宫格。",
                },
                "video_content_vision": {
                    "status": "unsupported",
                    "fields": [],
                    "notes": "当前没有视频内容级视觉分析，只有封面。",
                },
                "comment_text": {
                    "status": "partial",
                    "fields": ["tiktok_api.commentsDatasetUrl"],
                    "notes": "存在评论数据集入口，但当前主链路未抓评论正文。",
                },
                "paid_content_flag": {
                    "status": "unsupported",
                    "fields": [],
                    "notes": "当前没有等价的 paid content 标记字段。",
                },
            },
        },
        "instagram": {
            "mapping_basis": [
                "config/field_mapping.json:instagram_api",
                "scripts/data_cleaner.py:check_instagram_custom",
            ],
            "capabilities": {
                "view_count": {
                    "status": "partial",
                    "fields": ["instagram_api.latestPosts[].videoViewCount"],
                    "notes": "字段存在，但并非所有帖子都有，当前主链路未用它做门槛。",
                },
                "text_content": {
                    "status": "supported",
                    "fields": ["instagram_api.latestPosts[].caption"],
                    "notes": "当前主链路已使用 caption。",
                },
                "region_signal": {
                    "status": "supported",
                    "fields": [
                        "upload_metadata.region",
                        "instagram_api.biography",
                        "instagram_api.addressStreet",
                        "instagram_api.cityName",
                        "instagram_api.location",
                        "instagram_api.businessAddressJson",
                    ],
                    "notes": "当前主链路已融合上传表和 API 字段判断地区。",
                },
                "language_signal": {
                    "status": "supported",
                    "fields": ["upload_metadata.language", "instagram_api.biography"],
                    "notes": "当前主链路已融合上传表与简介做英语判断。",
                },
                "recency_timestamp": {
                    "status": "supported",
                    "fields": ["instagram_api.latestPosts[].timestamp"],
                    "notes": "当前主链路已使用最近帖子时间。",
                },
                "cover_vision": {
                    "status": "supported",
                    "fields": ["instagram_api.latestPosts[].displayUrl"],
                    "notes": "当前视觉复核基于帖子封面。",
                },
                "video_content_vision": {
                    "status": "unsupported",
                    "fields": [],
                    "notes": "当前没有视频内容级视觉分析，只有封面。",
                },
                "comment_text": {
                    "status": "unsupported",
                    "fields": [],
                    "notes": "当前只有 commentsCount，没有评论正文。",
                },
                "paid_content_flag": {
                    "status": "unsupported",
                    "fields": [],
                    "notes": "当前没有等价的 paid content 标记字段。",
                },
            },
        },
        "youtube": {
            "mapping_basis": [
                "scripts/data_cleaner.py:check_youtube",
                "docs/prd/youtube_prd_mapping.md",
            ],
            "capabilities": {
                "view_count": {
                    "status": "partial",
                    "fields": ["youtube_api.viewCount"],
                    "notes": "字段存在于采集结果，但当前主链路未把它接成门槛。",
                },
                "text_content": {
                    "status": "supported",
                    "fields": [
                        "youtube_api.title",
                        "youtube_api.text",
                        "youtube_api.aboutChannelInfo.channelDescription",
                    ],
                    "notes": "当前主链路已读取标题、描述、频道简介。",
                },
                "region_signal": {
                    "status": "partial",
                    "fields": ["youtube_api.channelLocation"],
                    "notes": "采集结果里有频道地点，但当前尚未形成稳定地区资格规则。",
                },
                "language_signal": {
                    "status": "partial",
                    "fields": ["youtube_api.title", "youtube_api.text"],
                    "notes": "可做启发式语言判断，但当前主链路未实现。",
                },
                "recency_timestamp": {
                    "status": "supported",
                    "fields": ["youtube_api.date"],
                    "notes": "当前主链路已使用最近发布时间。",
                },
                "cover_vision": {
                    "status": "supported",
                    "fields": ["youtube_api.thumbnailUrl"],
                    "notes": "当前视觉复核基于视频封面。",
                },
                "video_content_vision": {
                    "status": "unsupported",
                    "fields": [],
                    "notes": "当前没有视频内容级视觉分析。",
                },
                "comment_text": {
                    "status": "unsupported",
                    "fields": [],
                    "notes": "当前没有评论正文采集。",
                },
                "paid_content_flag": {
                    "status": "supported",
                    "fields": ["youtube_api.isPaidContent"],
                    "notes": "当前主链路已使用 paid content 比例规则。",
                },
            },
        },
        "_meta": {
            "upload_field_names": sorted(upload_fields.keys()),
            "instagram_sections": sorted(instagram_fields.keys()),
            "tiktok_sections": sorted(tiktok_fields.keys()),
        },
    }


def combine_statuses(statuses):
    if not statuses:
        return "unsupported"
    if all(status == "supported" for status in statuses):
        return "supported"
    if any(status == "unsupported" for status in statuses):
        if any(status in {"supported", "partial"} for status in statuses):
            return "partial"
        return "unsupported"
    if any(status == "partial" for status in statuses):
        return "partial"
    return "unsupported"


def evaluate_rule_for_platform(rule, platform_name, platform_info):
    if rule["check_type"] == "blocked_sensitive_attribute":
        blocked = deepcopy(rule)
        blocked["status"] = "blocked_sensitive_attribute"
        blocked["fields"] = []
        return blocked

    capabilities = platform_info["capabilities"]
    required_caps = rule.get("required_capabilities", [])
    statuses = []
    fields = []
    notes = []

    for capability_name in required_caps:
        capability = capabilities.get(capability_name)
        if not capability:
            capability = {
                "status": "unsupported",
                "fields": [],
                "notes": f"{platform_name} 当前没有 {capability_name} 能力描述。",
            }
        statuses.append(capability["status"])
        fields.extend(capability.get("fields", []))
        if capability.get("notes"):
            notes.append(capability["notes"])

    status = combine_statuses(statuses)
    evaluated = deepcopy(rule)
    evaluated["status"] = status
    evaluated["fields"] = sorted(set(fields))

    if evaluated["execution_layer"] == "rule_engine" and status == "unsupported":
        evaluated["execution_layer"] = "unsupported"
    elif evaluated["execution_layer"] == "rule_engine" and status == "partial":
        evaluated["execution_layer"] = "partial_rule_engine"
    elif evaluated["execution_layer"] == "vision_review" and status == "partial":
        evaluated["execution_layer"] = "partial_vision_review"
    elif evaluated["execution_layer"] == "future_collection":
        if status == "supported":
            evaluated["execution_layer"] = "future_collection"
        elif status == "partial":
            evaluated["execution_layer"] = "future_collection"
        else:
            evaluated["execution_layer"] = "unsupported"

    rule_notes = []
    if evaluated.get("notes"):
        rule_notes.append(evaluated["notes"])
    rule_notes.extend(notes)
    if platform_name == "youtube":
        rule_notes.append("当前 YouTube 模板基于代码与 PRD 推断，不来自机读字段字典。")
    evaluated["notes"] = " ".join(rule_notes).strip()
    return evaluated


def build_platform_template(parsed_sop, platform_name, platform_info):
    checks = []
    gaps = []
    blocked_rules = []

    for rule in parsed_sop["rules"]:
        evaluated = evaluate_rule_for_platform(rule, platform_name, platform_info)
        if evaluated["status"] == "blocked_sensitive_attribute":
            blocked_rules.append(evaluated)
        else:
            checks.append(evaluated)
            if evaluated["status"] in {"partial", "unsupported"}:
                gaps.append(
                    {
                        "rule_id": evaluated["id"],
                        "check_type": evaluated["check_type"],
                        "status": evaluated["status"],
                        "reason": evaluated.get("notes") or "当前平台能力不足",
                    }
                )

    supported_count = sum(1 for item in checks if item["status"] == "supported")
    partial_count = sum(1 for item in checks if item["status"] == "partial")
    unsupported_count = sum(1 for item in checks if item["status"] == "unsupported")

    return {
        "platform": platform_name,
        "goal": parsed_sop.get("goal") or "",
        "template_version": datetime.now().strftime("%Y-%m-%d"),
        "mapping_basis": platform_info["mapping_basis"],
        "checks": checks,
        "final_decision": parsed_sop["final_decision"],
        "gaps": gaps,
        "blocked_rules": blocked_rules,
        "summary": {
            "supported": supported_count,
            "partial": partial_count,
            "unsupported": unsupported_count,
            "blocked": len(blocked_rules),
        },
    }


def render_summary_markdown(parsed_sop, templates):
    lines = [
        "# 模板生成摘要",
        "",
        f"- 审核目标：{parsed_sop.get('goal') or '未提供'}",
        f"- 步骤数：{len(parsed_sop.get('steps', []))}",
        f"- 最终判定：{'; '.join(parsed_sop.get('final_decision', {}).get('raw_lines', [])) or '未提供'}",
        "",
        "## 解析到的步骤",
        "",
    ]

    for step in parsed_sop.get("steps", []):
        lines.append(f"### {step['title']}")
        lines.append("")
        for rule in step["rules"]:
            lines.append(
                f"- `{rule['check_type']}`: {rule['source_line']}"
            )
        if step.get("unmapped_lines"):
            lines.append(f"- 未自动识别：{'；'.join(step['unmapped_lines'])}")
        lines.append("")

    lines.extend(
        [
            "## 三平台支持矩阵",
            "",
            "| 平台 | Supported | Partial | Unsupported | Blocked |",
            "| --- | --- | --- | --- | --- |",
        ]
    )

    for platform_name in ("tiktok", "instagram", "youtube"):
        summary = templates[platform_name]["summary"]
        lines.append(
            f"| `{platform_name}` | {summary['supported']} | {summary['partial']} | {summary['unsupported']} | {summary['blocked']} |"
        )

    for platform_name in ("tiktok", "instagram", "youtube"):
        template = templates[platform_name]
        lines.extend(
            [
                "",
                f"## {platform_name.capitalize()}",
                "",
                "| Rule ID | Type | Status | Fields | Notes |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for check in template["checks"]:
            fields = ", ".join(f"`{field}`" for field in check.get("fields", [])) or "-"
            notes = check.get("notes") or "-"
            lines.append(
                f"| `{check['id']}` | `{check['check_type']}` | `{check['status']}` | {fields} | {notes} |"
            )
        if template["blocked_rules"]:
            lines.append("")
            lines.append("### Blocked Rules")
            lines.append("")
            for item in template["blocked_rules"]:
                lines.append(
                    f"- `{item['id']}`: {item.get('policy_reason') or '受保护属性规则不能自动化'}"
                )

    return "\n".join(lines) + "\n"


def read_input_text(args):
    if args.input:
        return Path(args.input).read_text(encoding="utf-8")
    return input_stream_text()


def input_stream_text():
    import sys

    return sys.stdin.read()


def ensure_output_dir(path_arg):
    if path_arg:
        return Path(path_arg)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return DEFAULT_OUTPUT_ROOT / timestamp


def write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_generation_output(output_dir, parsed_sop, templates, summary):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "parsed_sop.json", parsed_sop)
    for platform_name in ("tiktok", "instagram", "youtube"):
        write_json(output_dir / f"{platform_name}.template.json", templates[platform_name])
    (output_dir / "template_summary.md").write_text(summary, encoding="utf-8")


def generate_templates_from_text(text, output_dir=None):
    if not normalize_space(text):
        raise ValueError("SOP 输入为空，无法生成模板。")

    mapping = load_field_mapping()
    parsed_sop = parse_sop_text(text)
    capabilities = build_platform_capabilities(mapping)

    templates = {}
    for platform_name in ("tiktok", "instagram", "youtube"):
        templates[platform_name] = build_platform_template(parsed_sop, platform_name, capabilities[platform_name])

    summary = render_summary_markdown(parsed_sop, templates)
    resolved_output_dir = Path(output_dir) if output_dir else None
    if resolved_output_dir is not None:
        write_generation_output(resolved_output_dir, parsed_sop, templates, summary)

    return {
        "output_dir": str(resolved_output_dir) if resolved_output_dir else None,
        "parsed_sop": parsed_sop,
        "templates": templates,
        "summary_markdown": summary,
    }


def main():
    parser = argparse.ArgumentParser(
        description="根据自由文本审核需求生成 TikTok / Instagram / YouTube 模板"
    )
    parser.add_argument("--input", help="输入 SOP 文本文件路径")
    parser.add_argument("--output-dir", help="输出目录，默认写入 temp/generated_templates/<timestamp>")
    args = parser.parse_args()

    text = read_input_text(args)
    output_dir = ensure_output_dir(args.output_dir)
    result = generate_templates_from_text(text, output_dir=output_dir)
    print(f"Generated templates in {result['output_dir']}")


if __name__ == "__main__":
    main()
