#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import uuid
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.utils.cell import quote_sheetname
from openpyxl.worksheet.datavalidation import DataValidation


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE_PATH = ROOT_DIR / "docs" / "templates" / "标准化筛号需求模板-v1.xlsx"
DEFAULT_SPEC_PATH = ROOT_DIR / "docs" / "templates" / "标准化筛号需求模板-v1-说明.md"
DEFAULT_CONTRACT_PATH = ROOT_DIR / "docs" / "templates" / "标准化筛号需求模板-v1-contract.md"
DEFAULT_OUTPUT_ROOT = ROOT_DIR / "temp" / "compiled_requirement_workbook"
WORKBOOK_VERSION = "v1-sectioned"

MAIN_SHEET_NAME = "需求主表"
PREVIEW_SHEET_NAME = "compiler_preview"
OPTION_SHEET_NAME = "系统下拉选项"
LEGACY_SHEET_NAMES = ["自动初筛规则", "词组配置", "视觉复核规则", "人工判断项", "填写说明"]

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
SECTION_FILL = PatternFill("solid", fgColor="D9EAF7")
NOTE_FILL = PatternFill("solid", fgColor="F7F7F7")
MUTED_FILL = PatternFill("solid", fgColor="F3F6F8")
HEADER_FONT = Font(color="FFFFFF", bold=True)
SECTION_FONT = Font(color="1F1F1F", bold=True)
THIN_BORDER = Border(
    left=Side(style="thin", color="D0D7DE"),
    right=Side(style="thin", color="D0D7DE"),
    top=Side(style="thin", color="D0D7DE"),
    bottom=Side(style="thin", color="D0D7DE"),
)

YES_NO_MAP = {"是": True, "否": False}
PLATFORM_SCOPE_MAP = {
    "TikTok": ["tiktok"],
    "Instagram": ["instagram"],
    "两者": ["tiktok", "instagram"],
}
QUALIFICATION_SCOPE_MAP = {
    "主页资料": "profile_metadata",
    "内容整体": "all_content",
}
FAIL_ACTION_MAP = {
    "直接不通过": "reject",
    "转人工": "manual_review",
}
DATA_RELATION_MAP = {
    "同时满足": "all",
    "任一满足": "any",
}
MANUAL_HIT_ACTION_MAP = {
    "转人工": "manual_review",
    "仅提醒": "note_only",
}
OUTPUT_STATUS_MAP = {
    "通过": "pass",
    "不通过": "reject",
    "转人工": "manual_review",
}
STEP_NAME_MAP = {
    "步骤1：基础资质审核": "step_1_qualification",
    "步骤2：数据审核": "step_2_data",
    "步骤3：内容 / 视觉审核": "step_3_visual",
    "步骤4：排除项审核": "step_4_exclusions",
}
STEP_ID_TO_LABEL = {value: key for key, value in STEP_NAME_MAP.items()}

VISUAL_FEATURE_DEFS = [
    {"row": 38, "key": "multi_person_interaction", "label": "多人互动", "rulespec_key": "multi_person_interaction"},
    {"row": 39, "key": "speaking_led", "label": "Speaking-led", "rulespec_key": "speaking_led"},
    {"row": 40, "key": "real_life_scene", "label": "真实生活场景", "rulespec_key": "real_life_scene"},
    {"row": 41, "key": "kid_interaction", "label": "孩子互动", "rulespec_key": "kid_interaction"},
    {"row": 42, "key": "product_display", "label": "产品展示", "rulespec_key": "product_display"},
    {"row": 43, "key": "outdoor_yard", "label": "户外庭院", "rulespec_key": "outdoor_yard"},
    {"row": 44, "key": "pet_interaction", "label": "宠物互动", "rulespec_key": "pet_interaction"},
]

OPTION_SETS = {
    "yes_no": ["是", "否"],
    "platform_scope": ["TikTok", "Instagram", "两者"],
    "qualification_scope": ["主页资料", "内容整体"],
    "fail_action": ["直接不通过", "转人工"],
    "data_relation": ["同时满足", "任一满足"],
    "manual_hit_action": ["转人工", "仅提醒"],
    "output_status": ["通过", "不通过", "转人工"],
}


def build_choice_normalizer(choice_map: dict[str, Any]) -> Callable[[Any], Any]:
    def normalize(value: Any) -> Any:
        text = normalize_cell_value(value)
        if not text:
            return None
        return choice_map.get(text)

    return normalize


def normalize_cell_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def split_list_text(value: str) -> list[str]:
    if not value:
        return []
    normalized = value.replace("；", ",").replace("，", ",").replace("\n", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def parse_optional_int(text: str) -> int | None:
    if not text:
        return None
    return int(text)


def parse_required_int(text: str) -> int:
    if not text:
        raise ValueError("不能为空")
    return int(text)


def value_cell(row: int) -> str:
    return f"B{row}"


def note_cell(row: int) -> str:
    return f"C{row}"


SECTIONED_FIELD_DEFS = [
    {
        "section_key": "basic_info",
        "title": "A. 基本信息",
        "title_row": 4,
        "fields": [
            {
                "row": 5,
                "key": "project_name",
                "label": "项目名称",
                "required": True,
                "type": "string",
                "default": "",
                "example": "示例：Tapo 北美生活方式达人筛号",
                "compile_rule": "metadata only",
                "error_message": "项目名称不能为空",
            },
            {
                "row": 6,
                "key": "brand_product",
                "label": "品牌 / 产品",
                "required": True,
                "type": "string",
                "default": "",
                "example": "示例：Tapo 智能家居 / 宠物 / 户外生活场景",
                "compile_rule": "metadata only",
                "error_message": "品牌 / 产品不能为空",
            },
            {
                "row": 7,
                "key": "platform_scope",
                "label": "适用平台",
                "required": True,
                "type": "choice",
                "default": "两者",
                "option_set": "platform_scope",
                "normalizer": build_choice_normalizer(PLATFORM_SCOPE_MAP),
                "example": "可选：TikTok / Instagram / 两者",
                "compile_rule": "controls per-rule platform intersection",
                "error_message": "适用平台 只能填写 TikTok、Instagram 或 两者",
            },
            {
                "row": 8,
                "key": "audit_goal",
                "label": "审核目标",
                "required": True,
                "type": "string",
                "default": "",
                "example": "示例：判断达人是否符合 Tapo 家庭 / 宠物 / 户外生活内容合作标准",
                "compile_rule": "metadata only",
                "error_message": "审核目标不能为空",
            },
            {
                "row": 9,
                "key": "reference_accounts",
                "label": "参考账号",
                "required": False,
                "type": "list",
                "default": "",
                "example": "多个账号可用逗号分隔",
                "compile_rule": "metadata only",
                "error_message": "参考账号格式无效",
            },
            {
                "row": 10,
                "key": "counterexample_accounts",
                "label": "反例账号",
                "required": False,
                "type": "list",
                "default": "",
                "example": "多个账号可用逗号分隔",
                "compile_rule": "metadata only",
                "error_message": "反例账号格式无效",
            },
            {
                "row": 11,
                "key": "notes",
                "label": "备注",
                "required": False,
                "type": "string",
                "default": "",
                "example": "补充上下文、品牌特殊要求或排雷背景",
                "compile_rule": "metadata only",
                "error_message": "",
            },
        ],
    },
    {
        "section_key": "qualification",
        "title": "B. 步骤1：基础资质审核",
        "title_row": 14,
        "fields": [
            {
                "row": 15,
                "key": "region_requirement",
                "label": "地区要求",
                "required": False,
                "type": "list",
                "default": "",
                "example": "示例：美国, 加拿大",
                "compile_rule": "compile to Instagram-only region_gate rule",
                "error_message": "地区要求格式无效",
            },
            {
                "row": 16,
                "key": "language_requirement",
                "label": "语言要求",
                "required": False,
                "type": "list",
                "default": "",
                "example": "示例：英语, English, en",
                "compile_rule": "compile to Instagram-only language_gate rule",
                "error_message": "语言要求格式无效",
            },
            {
                "row": 17,
                "key": "check_scope",
                "label": "检查位置",
                "required": False,
                "type": "choice",
                "default": "主页资料",
                "option_set": "qualification_scope",
                "normalizer": build_choice_normalizer(QUALIFICATION_SCOPE_MAP),
                "example": "地区 / 语言通常填写 主页资料",
                "compile_rule": "metadata for qualification rules",
                "error_message": "检查位置 只能填写 主页资料 或 内容整体",
            },
            {
                "row": 18,
                "key": "fail_action",
                "label": "不符合时处理",
                "required": False,
                "type": "choice",
                "default": "直接不通过",
                "option_set": "fail_action",
                "normalizer": build_choice_normalizer(FAIL_ACTION_MAP),
                "example": "示例：直接不通过",
                "compile_rule": "qualification fail action",
                "error_message": "不符合时处理 只能填写 直接不通过 或 转人工",
            },
            {
                "row": 19,
                "key": "notes",
                "label": "补充说明",
                "required": False,
                "type": "string",
                "default": "",
                "example": "示例：语言以主页简介和近期内容整体为准",
                "compile_rule": "metadata only",
                "error_message": "",
            },
        ],
    },
    {
        "section_key": "data_audit",
        "title": "C. 步骤2：数据审核",
        "title_row": 22,
        "fields": [
            {
                "row": 23,
                "key": "sample_size",
                "label": "取样视频数",
                "required": False,
                "type": "int",
                "default": "50",
                "example": "示例：50",
                "compile_rule": "shared window size for view metrics",
                "error_message": "取样视频数 必须是整数",
            },
            {
                "row": 24,
                "key": "mean_view_threshold",
                "label": "平均播放量阈值",
                "required": False,
                "type": "int",
                "default": "",
                "example": "示例：10000",
                "compile_rule": "compile to TikTok-only view_count_mean rule",
                "error_message": "平均播放量阈值 必须是整数",
            },
            {
                "row": 25,
                "key": "median_view_threshold",
                "label": "中位数播放量阈值",
                "required": False,
                "type": "int",
                "default": "",
                "example": "示例：10000",
                "compile_rule": "compile to TikTok-only view_count_median rule",
                "error_message": "中位数播放量阈值 必须是整数",
            },
            {
                "row": 26,
                "key": "follower_threshold",
                "label": "粉丝数阈值（可选）",
                "required": False,
                "type": "int",
                "default": "",
                "example": "示例：50000",
                "compile_rule": "compile to follower_count rule",
                "error_message": "粉丝数阈值 必须是整数",
            },
            {
                "row": 27,
                "key": "recent_active_days",
                "label": "最近活跃要求（天，可选）",
                "required": False,
                "type": "int",
                "default": "",
                "example": "示例：30 表示 30 天内有更新",
                "compile_rule": "compile to activity_recency_days rule",
                "error_message": "最近活跃要求 必须是整数",
            },
            {
                "row": 28,
                "key": "judgement_relation",
                "label": "判定关系",
                "required": False,
                "type": "choice",
                "default": "同时满足",
                "option_set": "data_relation",
                "normalizer": build_choice_normalizer(DATA_RELATION_MAP),
                "example": "示例：同时满足",
                "compile_rule": "data step aggregation logic",
                "error_message": "判定关系 只能填写 同时满足 或 任一满足",
            },
            {
                "row": 29,
                "key": "fail_action",
                "label": "不符合时处理",
                "required": False,
                "type": "choice",
                "default": "直接不通过",
                "option_set": "fail_action",
                "normalizer": build_choice_normalizer(FAIL_ACTION_MAP),
                "example": "示例：直接不通过",
                "compile_rule": "data step fail action",
                "error_message": "不符合时处理 只能填写 直接不通过 或 转人工",
            },
            {
                "row": 30,
                "key": "notes",
                "label": "补充说明",
                "required": False,
                "type": "string",
                "default": "",
                "example": "示例：播放量按最近前 50 个视频统计",
                "compile_rule": "metadata only",
                "error_message": "",
            },
        ],
    },
    {
        "section_key": "visual_audit",
        "title": "D. 步骤3：内容 / 视觉审核",
        "title_row": 33,
        "fields": [
            {
                "row": 34,
                "key": "cover_count",
                "label": "查看封面数量",
                "required": False,
                "type": "int",
                "default": "18",
                "example": "建议：18；如果只做单九宫格可填 9",
                "compile_rule": "shared visual cover count",
                "error_message": "查看封面数量 必须是整数",
            },
            {
                "row": 35,
                "key": "min_hit_features",
                "label": "至少命中几类特征",
                "required": False,
                "type": "int",
                "default": "1",
                "example": "示例：1",
                "compile_rule": "visual step group threshold",
                "error_message": "至少命中几类特征 必须是整数",
            },
            {
                "row": 36,
                "key": "notes",
                "label": "补充说明",
                "required": False,
                "type": "string",
                "default": "",
                "example": "这里只保留封面能稳定看出来的自动化项；鲜明人设 / 垂直 niche 请放到人工判断项。",
                "compile_rule": "metadata only",
                "error_message": "",
            },
        ],
    },
    {
        "section_key": "exclusions",
        "title": "E. 步骤4：排除项审核",
        "title_row": 47,
        "fields": [
            {
                "row": 48,
                "key": "text_keyword_blocklist",
                "label": "文本关键词排除",
                "required": False,
                "type": "list",
                "default": "",
                "example": "示例：beauty, makeup, skincare",
                "compile_rule": "compile to content keyword blocklist",
                "error_message": "文本关键词排除 格式无效",
            },
            {
                "row": 49,
                "key": "relationship_keyword_blocklist",
                "label": "关系词排除",
                "required": False,
                "type": "list",
                "default": "",
                "example": "示例：partner, boyfriend, girlfriend, husband, wife",
                "compile_rule": "compile to relationship keyword blocklist",
                "error_message": "关系词排除 格式无效",
            },
            {
                "row": 50,
                "key": "beauty_ratio_threshold",
                "label": "美妆内容占比阈值（%）",
                "required": False,
                "type": "int",
                "default": "",
                "example": "示例：50",
                "compile_rule": "compile to content_keyword_ratio threshold",
                "error_message": "美妆内容占比阈值 必须是整数",
            },
            {
                "row": 51,
                "key": "multi_dance_ratio_threshold",
                "label": "多人跳舞占比阈值（%）",
                "required": False,
                "type": "int",
                "default": "",
                "example": "示例：30",
                "compile_rule": "compile to visual risk ratio",
                "error_message": "多人跳舞占比阈值 必须是整数",
            },
            {
                "row": 52,
                "key": "selfie_couple_ratio_threshold",
                "label": "自拍 / 情侣出镜占比阈值（%）",
                "required": False,
                "type": "int",
                "default": "",
                "example": "示例：70",
                "compile_rule": "compile to selfie_or_couple_ratio rule",
                "error_message": "自拍 / 情侣出镜占比阈值 必须是整数",
            },
            {
                "row": 53,
                "key": "green_screen_direct_reject",
                "label": "绿幕是否直接排除",
                "required": False,
                "type": "choice",
                "default": "否",
                "option_set": "yes_no",
                "normalizer": build_choice_normalizer(YES_NO_MAP),
                "example": "示例：是",
                "compile_rule": "compile to green_screen must_not_appear rule",
                "error_message": "绿幕是否直接排除 只能填写 是 或 否",
            },
            {
                "row": 54,
                "key": "other_exclusion_items",
                "label": "其他排除项",
                "required": False,
                "type": "string",
                "default": "",
                "example": "自由文本只会进入人工提醒，不会自动编译成 RuleSpec",
                "compile_rule": "manual note only",
                "error_message": "",
            },
            {
                "row": 55,
                "key": "notes",
                "label": "补充说明",
                "required": False,
                "type": "string",
                "default": "",
                "example": "示例：如果出现自拍 / 情侣比例过高，还需结合缺少产品 / 宠物 / 孩子元素人工判断",
                "compile_rule": "metadata only",
                "error_message": "",
            },
        ],
    },
    {
        "section_key": "manual_review",
        "title": "F. 人工判断项 / 合规提醒",
        "title_row": 58,
        "fields": [
            {
                "row": 59,
                "key": "comment_emoji_abnormal",
                "label": "评论区 emoji 异常",
                "required": False,
                "type": "choice",
                "default": "否",
                "option_set": "yes_no",
                "normalizer": build_choice_normalizer(YES_NO_MAP),
                "example": "示例：是；只进入人工判断，不进自动规则",
                "compile_rule": "manual review item only",
                "error_message": "评论区 emoji 异常 只能填写 是 或 否",
            },
            {
                "row": 60,
                "key": "persona_or_niche_manual",
                "label": "鲜明人设 / 垂直 niche",
                "required": False,
                "type": "choice",
                "default": "否",
                "option_set": "yes_no",
                "normalizer": build_choice_normalizer(YES_NO_MAP),
                "example": "示例：是；统一放人工判断，不进入内容 / 视觉自动化项",
                "compile_rule": "manual review item only",
                "error_message": "鲜明人设 / 垂直 niche 只能填写 是 或 否",
            },
            {
                "row": 61,
                "key": "full_video_review",
                "label": "完整视频内容判断",
                "required": False,
                "type": "choice",
                "default": "否",
                "option_set": "yes_no",
                "normalizer": build_choice_normalizer(YES_NO_MAP),
                "example": "示例：是；当前系统只看封面，完整视频判断需人工",
                "compile_rule": "manual review item only",
                "error_message": "完整视频内容判断 只能填写 是 或 否",
            },
            {
                "row": 62,
                "key": "other_subjective_items",
                "label": "其他主观判断项",
                "required": False,
                "type": "string",
                "default": "",
                "example": "示例：solo POV 是否缺少互动感；只进入人工判断",
                "compile_rule": "manual review item only",
                "error_message": "",
            },
            {
                "row": 63,
                "key": "protected_attribute_notice",
                "label": "受保护属性相关判断",
                "required": False,
                "type": "string",
                "default": "",
                "example": "如出现年龄 / 种族 / 民族等判断，只保留为合规提醒，永不进入 RuleSpec",
                "compile_rule": "compliance note only; never compile",
                "error_message": "",
            },
            {
                "row": 64,
                "key": "notes",
                "label": "补充说明",
                "required": False,
                "type": "string",
                "default": "",
                "example": "可写人工复核时需要特别关注的点",
                "compile_rule": "metadata only",
                "error_message": "",
            },
        ],
    },
    {
        "section_key": "final_logic",
        "title": "G. 最终判定逻辑",
        "title_row": 67,
        "fields": [
            {
                "row": 68,
                "key": "must_pass_steps",
                "label": "必须满足哪些步骤",
                "required": True,
                "type": "step_list",
                "default": "步骤1：基础资质审核,步骤2：数据审核,步骤3：内容 / 视觉审核",
                "example": "可填写多个步骤，使用逗号分隔",
                "compile_rule": "final_logic.must_pass_steps",
                "error_message": "必须满足哪些步骤 只能填写固定步骤名称，并使用逗号分隔",
            },
            {
                "row": 69,
                "key": "reject_if_any_steps",
                "label": "任一触发即不通过的项",
                "required": True,
                "type": "step_list",
                "default": "步骤4：排除项审核",
                "example": "通常填写：步骤4：排除项审核",
                "compile_rule": "final_logic.reject_if_any_steps",
                "error_message": "任一触发即不通过的项 只能填写固定步骤名称，并使用逗号分隔",
            },
            {
                "row": 70,
                "key": "manual_hit_action",
                "label": "人工判断项命中时如何处理",
                "required": True,
                "type": "choice",
                "default": "转人工",
                "option_set": "manual_hit_action",
                "normalizer": build_choice_normalizer(MANUAL_HIT_ACTION_MAP),
                "example": "示例：转人工",
                "compile_rule": "final_logic.manual_hit_action",
                "error_message": "人工判断项命中时如何处理 只能填写 转人工 或 仅提醒",
            },
            {
                "row": 71,
                "key": "success_output",
                "label": "满足条件时输出",
                "required": True,
                "type": "choice",
                "default": "通过",
                "option_set": "output_status",
                "normalizer": build_choice_normalizer(OUTPUT_STATUS_MAP),
                "example": "示例：通过",
                "compile_rule": "final_logic.success_output",
                "error_message": "满足条件时输出 只能填写 通过 / 不通过 / 转人工",
            },
            {
                "row": 72,
                "key": "failure_output",
                "label": "不满足时输出",
                "required": True,
                "type": "choice",
                "default": "不通过",
                "option_set": "output_status",
                "normalizer": build_choice_normalizer(OUTPUT_STATUS_MAP),
                "example": "示例：不通过",
                "compile_rule": "final_logic.failure_output",
                "error_message": "不满足时输出 只能填写 通过 / 不通过 / 转人工",
            },
            {
                "row": 73,
                "key": "notes",
                "label": "补充说明",
                "required": False,
                "type": "string",
                "default": "",
                "example": "可补充最终判定时的优先级说明",
                "compile_rule": "metadata only",
                "error_message": "",
            },
        ],
    },
]

PREVIEW_HEADERS = [
    "预览编号",
    "来源区块",
    "来源字段",
    "来源单元格",
    "状态",
    "规则类型",
    "平台范围",
    "标准化值",
    "说明",
]

AUTOMATION_FIELD_SUPPORT = {
    "region_requirement": ["instagram"],
    "language_requirement": ["instagram"],
    "mean_view_threshold": ["tiktok"],
    "median_view_threshold": ["tiktok"],
    "follower_threshold": ["tiktok", "instagram"],
    "recent_active_days": ["tiktok", "instagram"],
    "text_keyword_blocklist": ["tiktok", "instagram"],
    "relationship_keyword_blocklist": ["instagram"],
    "beauty_ratio_threshold": ["tiktok", "instagram"],
    "multi_dance_ratio_threshold": ["tiktok", "instagram"],
    "selfie_couple_ratio_threshold": ["tiktok", "instagram"],
    "green_screen_direct_reject": ["tiktok", "instagram"],
    "visual_features": ["tiktok", "instagram"],
}

# Legacy compatibility
AUTO_CATEGORY_MAP = {
    "基础数据": "metrics",
    "主页资格": "profile_gate",
    "文本排雷": "text_risk",
}
LOCATION_MAP = {
    "账号整体": "profile_overview",
    "主页资料": "profile_metadata",
    "最近内容": "recent_posts",
}
WINDOW_UNIT_MAP = {
    "条": "posts",
    "天": "days",
    "张": "covers",
}
COMPARISON_MAP = {
    "大于": ">",
    "大于等于": ">=",
    "小于": "<",
    "小于等于": "<=",
    "占比超过": "ratio_gt",
    "包含任一项": "contains_any",
    "不得出现": "must_not_contain",
}
DECISION_EFFECT_MAP = {
    "不通过": "reject_if_fail",
    "转人工": "manual_review",
    "仅标记": "flag_only",
}
VISUAL_OPERATOR_MAP = {
    "至少出现1类": "at_least_one",
    "占比超过": "ratio_gt",
    "不得出现": "must_not_appear",
}
VISUAL_HIT_EFFECT_MAP = {
    "通过": "pass_if_hit",
    "不通过": "reject_if_hit",
    "转人工": "manual_review",
}
GROUP_TYPE_MAP = {
    "地区组": "region_group",
    "语言组": "language_group",
    "内容关键词": "content_keywords",
    "关系词": "relationship_keywords",
    "主页简介禁词": "profile_bio_blocklist",
    "外链禁词": "external_link_blocklist",
    "视觉场景": "visual_scene_group",
    "视觉排除项": "visual_risk_group",
}
MANUAL_SCOPE_MAP = {
    "主页资料": "profile_metadata",
    "评论区": "comments",
    "内容整体": "all_content",
    "视觉复核": "visual_review",
}
MANUAL_ACTION_MAP = {
    "不通过": "reject",
    "转 PM": "handoff_pm",
    "仅备注": "note_only",
}

AUTO_RULE_ITEM_DEFS = {
    "粉丝数": {
        "internal_key": "follower_count",
        "supported_platforms": ["TikTok", "Instagram"],
        "field_basis": [
            "TikTok：tiktok_api.authorMeta.fans",
            "Instagram：instagram_api.followersCount",
        ],
    },
    "平均播放量": {
        "internal_key": "view_count_mean",
        "supported_platforms": ["TikTok"],
        "field_basis": ["TikTok：tiktok_api.playCount（最近内容）"],
    },
    "播放量中位数": {
        "internal_key": "view_count_median",
        "supported_platforms": ["TikTok"],
        "field_basis": ["TikTok：tiktok_api.playCount（最近内容）"],
    },
    "最近是否活跃": {
        "internal_key": "activity_recency_days",
        "supported_platforms": ["TikTok", "Instagram"],
        "field_basis": ["TikTok：tiktok_api.createTimeISO", "Instagram：latestPosts[].timestamp"],
    },
    "地区要求": {
        "internal_key": "region_gate",
        "supported_platforms": ["Instagram"],
        "field_basis": ["Instagram：upload_metadata.region / biography"],
    },
    "语言要求": {
        "internal_key": "language_gate",
        "supported_platforms": ["Instagram"],
        "field_basis": ["Instagram：upload_metadata.language / biography"],
    },
    "内容关键词占比": {
        "internal_key": "content_keyword_ratio",
        "supported_platforms": ["TikTok", "Instagram"],
        "field_basis": ["TikTok：text + hashtags", "Instagram：caption"],
    },
    "关系词排雷": {
        "internal_key": "relationship_keyword_block",
        "supported_platforms": ["Instagram"],
        "field_basis": ["Instagram：caption"],
    },
    "主页简介禁词": {
        "internal_key": "profile_bio_blocklist",
        "supported_platforms": ["TikTok", "Instagram"],
        "field_basis": ["TikTok：signature", "Instagram：biography"],
    },
    "主页外链禁词": {
        "internal_key": "profile_external_link_blocklist",
        "supported_platforms": ["TikTok", "Instagram"],
        "field_basis": ["TikTok：bioLink", "Instagram：externalUrls"],
    },
}

VISUAL_RULE_ITEM_DEFS = {
    "家庭场景": {"internal_key": "home_scene", "field_basis": ["TikTok / Instagram 封面图"]},
    "孩子互动": {"internal_key": "kid_interaction", "field_basis": ["TikTok / Instagram 封面图"]},
    "宠物互动": {"internal_key": "pet_interaction", "field_basis": ["TikTok / Instagram 封面图"]},
    "产品展示": {"internal_key": "product_display", "field_basis": ["TikTok / Instagram 封面图"]},
    "户外庭院": {"internal_key": "outdoor_yard", "field_basis": ["TikTok / Instagram 封面图"]},
    "多人互动": {"internal_key": "multi_person_interaction", "field_basis": ["TikTok / Instagram 封面图"]},
    "Speaking-led": {"internal_key": "speaking_led", "field_basis": ["TikTok / Instagram 封面图"]},
    "真实生活场景": {"internal_key": "real_life_scene", "field_basis": ["TikTok / Instagram 封面图"]},
    "绿幕背景": {"internal_key": "green_screen", "field_basis": ["TikTok / Instagram 封面图"]},
    "自拍/情侣占比过高": {"internal_key": "selfie_or_couple_ratio", "field_basis": ["TikTok / Instagram 封面图"]},
    "多人跳舞占比过高": {"internal_key": "multi_dance_ratio", "field_basis": ["TikTok / Instagram 封面图"]},
    "缺少产品/宠物/孩子元素": {"internal_key": "missing_product_pet_kid", "field_basis": ["TikTok / Instagram 封面图"]},
}

MANUAL_REVIEW_ITEM_DEFS = {
    "评论区好评/差评倾向": "当前没有评论正文主链路，不能稳定自动化。",
    "评论区 emoji 异常": "当前没有评论正文主链路，不能稳定自动化。",
    "是否刷量/水军": "需要评论语义和异常行为判断，V1 不自动化。",
    "是否有公关风险": "需要评论语义和历史内容综合判断，V1 不自动化。",
    "达人画像/一级标签": "适合做标签，不适合直接做自动 Pass/Reject。",
    "人设鲜明程度": "语义主观性高，建议人工判断。",
    "完整视频内容判断": "当前视觉链路只看封面，不看完整视频。",
    "受保护属性相关判断": "年龄、种族等不能进入自动化规则。",
}

LEGACY_AUTO_RULE_SHEET = {
    "name": "自动初筛规则",
    "slug": "automatic_rules",
    "columns": [
        {"label": "规则编号", "key": "rule_id", "required": True},
        {"label": "是否启用", "key": "enabled", "required": True, "normalize": build_choice_normalizer(YES_NO_MAP)},
        {"label": "适用平台", "key": "platform_scope", "required": True, "normalize": build_choice_normalizer(PLATFORM_SCOPE_MAP)},
        {"label": "规则分类", "key": "rule_category", "required": True, "normalize": build_choice_normalizer(AUTO_CATEGORY_MAP)},
        {"label": "审核步骤", "key": "step_name", "required": True},
        {"label": "判断项", "key": "judgement_item", "required": True, "normalize": lambda value: AUTO_RULE_ITEM_DEFS.get(normalize_cell_value(value), {}).get("internal_key")},
        {"label": "判断位置", "key": "judgement_scope", "required": True, "normalize": build_choice_normalizer(LOCATION_MAP)},
        {"label": "取样数量", "key": "window_size"},
        {"label": "取样单位", "key": "window_unit", "normalize": build_choice_normalizer(WINDOW_UNIT_MAP)},
        {"label": "判断方式", "key": "operator", "required": True, "normalize": build_choice_normalizer(COMPARISON_MAP)},
        {"label": "标准值", "key": "threshold_value"},
        {"label": "单位", "key": "threshold_unit"},
        {"label": "引用词组编号", "key": "group_id"},
        {"label": "不满足时处理", "key": "decision_effect", "required": True, "normalize": build_choice_normalizer(DECISION_EFFECT_MAP)},
        {"label": "备注", "key": "notes"},
    ],
}
LEGACY_VALUE_GROUP_SHEET = {
    "name": "词组配置",
    "slug": "value_groups",
    "columns": [
        {"label": "词组编号", "key": "group_id", "required": True},
        {"label": "词组名称", "key": "group_name", "required": True},
        {"label": "词组类型", "key": "group_type", "required": True, "normalize": build_choice_normalizer(GROUP_TYPE_MAP)},
        {"label": "词组内容", "key": "values", "required": True},
        {"label": "适用平台", "key": "platform_scope", "normalize": build_choice_normalizer(PLATFORM_SCOPE_MAP)},
        {"label": "备注", "key": "notes"},
    ],
}
LEGACY_VISUAL_RULE_SHEET = {
    "name": "视觉复核规则",
    "slug": "visual_rules",
    "columns": [
        {"label": "规则编号", "key": "rule_id", "required": True},
        {"label": "是否启用", "key": "enabled", "required": True, "normalize": build_choice_normalizer(YES_NO_MAP)},
        {"label": "适用平台", "key": "platform_scope", "required": True, "normalize": build_choice_normalizer(PLATFORM_SCOPE_MAP)},
        {"label": "审核步骤", "key": "step_name", "required": True},
        {"label": "视觉判断项", "key": "visual_item", "required": True, "normalize": lambda value: VISUAL_RULE_ITEM_DEFS.get(normalize_cell_value(value), {}).get("internal_key")},
        {"label": "看最近多少张封面", "key": "cover_count", "required": True, "normalize": lambda value: int(normalize_cell_value(value)) if normalize_cell_value(value) else None},
        {"label": "判断方式", "key": "operator", "required": True, "normalize": build_choice_normalizer(VISUAL_OPERATOR_MAP)},
        {"label": "标准值", "key": "threshold_value"},
        {"label": "单位", "key": "threshold_unit"},
        {"label": "引用词组编号", "key": "group_id"},
        {"label": "命中后处理", "key": "hit_effect", "required": True, "normalize": build_choice_normalizer(VISUAL_HIT_EFFECT_MAP)},
        {"label": "备注", "key": "notes"},
    ],
}
LEGACY_MANUAL_REVIEW_SHEET = {
    "name": "人工判断项",
    "slug": "manual_items",
    "columns": [
        {"label": "项目编号", "key": "item_id", "required": True},
        {"label": "是否启用", "key": "enabled", "required": True, "normalize": build_choice_normalizer(YES_NO_MAP)},
        {"label": "适用平台", "key": "platform_scope", "normalize": build_choice_normalizer(PLATFORM_SCOPE_MAP)},
        {"label": "审核步骤", "key": "step_name"},
        {"label": "人工判断项", "key": "manual_item", "required": True, "normalize": lambda value: normalize_cell_value(value)},
        {"label": "判断范围", "key": "manual_scope", "normalize": build_choice_normalizer(MANUAL_SCOPE_MAP)},
        {"label": "判断说明", "key": "manual_instruction", "required": True},
        {"label": "建议处理", "key": "manual_action", "normalize": build_choice_normalizer(MANUAL_ACTION_MAP)},
        {"label": "备注", "key": "notes"},
    ],
}
LEGACY_DATA_SHEETS = [
    LEGACY_AUTO_RULE_SHEET,
    LEGACY_VALUE_GROUP_SHEET,
    LEGACY_VISUAL_RULE_SHEET,
    LEGACY_MANUAL_REVIEW_SHEET,
]


def build_options_sheet(workbook: Workbook) -> dict[str, tuple[str, int, int]]:
    worksheet = workbook.create_sheet(OPTION_SHEET_NAME)
    worksheet.sheet_state = "hidden"
    option_ranges: dict[str, tuple[str, int, int]] = {}

    for column_index, (option_name, options) in enumerate(OPTION_SETS.items(), start=1):
        worksheet.cell(row=1, column=column_index, value=option_name)
        for row_index, item in enumerate(options, start=2):
            worksheet.cell(row=row_index, column=column_index, value=item)
        option_ranges[option_name] = (get_column_letter(column_index), 2, len(options) + 1)

    return option_ranges


def add_cell_validation(worksheet, cell_ref: str, option_set: str, option_ranges: dict[str, tuple[str, int, int]]) -> None:
    column_letter, start_row, end_row = option_ranges[option_set]
    formula = f"{quote_sheetname(OPTION_SHEET_NAME)}!${column_letter}${start_row}:${column_letter}${end_row}"
    validation = DataValidation(type="list", formula1=formula, allow_blank=True)
    validation.prompt = f"请选择：{cell_ref}"
    validation.error = "该单元格只能填写模板下拉选项。"
    worksheet.add_data_validation(validation)
    validation.add(cell_ref)


def style_field_row(worksheet, row: int, label: str, default_value: str, example_text: str) -> None:
    label_ref = f"A{row}"
    value_ref = value_cell(row)
    note_ref = note_cell(row)

    worksheet[label_ref] = label
    worksheet[label_ref].fill = SECTION_FILL
    worksheet[label_ref].font = Font(bold=True)
    worksheet[label_ref].border = THIN_BORDER

    worksheet[value_ref] = default_value
    worksheet[value_ref].border = THIN_BORDER
    worksheet[value_ref].alignment = Alignment(vertical="top", wrap_text=True)

    worksheet[note_ref] = example_text
    worksheet[note_ref].border = THIN_BORDER
    worksheet[note_ref].fill = NOTE_FILL
    worksheet[note_ref].alignment = Alignment(vertical="top", wrap_text=True)


def build_main_sheet(workbook: Workbook, option_ranges: dict[str, tuple[str, int, int]]) -> None:
    worksheet = workbook.create_sheet(MAIN_SHEET_NAME)
    worksheet.sheet_view.showGridLines = True
    worksheet.column_dimensions["A"].width = 26
    worksheet.column_dimensions["B"].width = 28
    worksheet.column_dimensions["C"].width = 70

    worksheet.merge_cells("A1:C1")
    worksheet["A1"] = "标准化筛号需求主表"
    worksheet["A1"].fill = HEADER_FILL
    worksheet["A1"].font = HEADER_FONT
    worksheet["A1"].alignment = Alignment(horizontal="center")
    worksheet["A1"].border = THIN_BORDER

    worksheet.merge_cells("A2:C2")
    worksheet["A2"] = "这是唯一默认填写入口。source of truth 只来自本主表固定区块与固定单元格；compiler_preview 只做输出预览，不参与输入解析。"
    worksheet["A2"].border = THIN_BORDER
    worksheet["A2"].fill = MUTED_FILL
    worksheet["A2"].alignment = Alignment(wrap_text=True)

    worksheet["A3"] = "字段"
    worksheet["B3"] = "填写值"
    worksheet["C3"] = "说明 / 示例"
    for cell_ref in ("A3", "B3", "C3"):
        worksheet[cell_ref].fill = HEADER_FILL
        worksheet[cell_ref].font = HEADER_FONT
        worksheet[cell_ref].border = THIN_BORDER

    for section in SECTIONED_FIELD_DEFS:
        title_cell = f"A{section['title_row']}"
        worksheet.merge_cells(start_row=section["title_row"], start_column=1, end_row=section["title_row"], end_column=3)
        worksheet[title_cell] = section["title"]
        worksheet[title_cell].fill = SECTION_FILL
        worksheet[title_cell].font = SECTION_FONT
        worksheet[title_cell].border = THIN_BORDER

        for field in section["fields"]:
            style_field_row(
                worksheet,
                field["row"],
                field["label"],
                field.get("default", ""),
                field.get("example", ""),
            )
            if field.get("option_set"):
                add_cell_validation(worksheet, value_cell(field["row"]), field["option_set"], option_ranges)

    worksheet.merge_cells("A37:C37")
    worksheet["A37"] = "自动化特征清单（只保留封面能稳定看出来的项）"
    worksheet["A37"].fill = MUTED_FILL
    worksheet["A37"].font = Font(bold=True)
    worksheet["A37"].border = THIN_BORDER

    feature_examples = {
        "多人互动": "示例：街访、朋友互动、陌生人交流",
        "Speaking-led": "示例：镜头前开口说话，有表达能力",
        "真实生活场景": "示例：非绿幕、非强剧本感情景剧",
        "孩子互动": "示例：室内环境与孩子互动",
        "产品展示": "示例：手持或展示产品",
        "户外庭院": "示例：室外、庭院、院子场景",
        "宠物互动": "示例：与宠物互动",
    }
    for feature in VISUAL_FEATURE_DEFS:
        style_field_row(
            worksheet,
            feature["row"],
            feature["label"],
            "否",
            feature_examples.get(feature["label"], ""),
        )
        add_cell_validation(worksheet, value_cell(feature["row"]), "yes_no", option_ranges)

    worksheet.freeze_panes = "A4"


def build_preview_sheet(workbook: Workbook) -> None:
    worksheet = workbook.create_sheet(PREVIEW_SHEET_NAME)
    worksheet.sheet_state = "hidden"
    for index, title in enumerate(PREVIEW_HEADERS, start=1):
        cell = worksheet.cell(row=1, column=index, value=title)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.border = THIN_BORDER
        worksheet.column_dimensions[get_column_letter(index)].width = 24
    worksheet["A2"] = "系统输出预览，不作为输入来源。"


def create_template_workbook() -> Workbook:
    workbook = Workbook()
    workbook.remove(workbook.active)
    option_ranges = build_options_sheet(workbook)
    build_main_sheet(workbook, option_ranges)
    build_preview_sheet(workbook)
    workbook.properties.title = "标准化筛号需求模板"
    workbook.properties.subject = WORKBOOK_VERSION
    workbook.properties.creator = "Codex"
    workbook.properties.description = "分区式筛号需求主表；品牌方与内部统一填写入口。"
    workbook._sheets = [workbook[MAIN_SHEET_NAME], workbook[PREVIEW_SHEET_NAME], workbook[OPTION_SHEET_NAME]]
    return workbook


def create_legacy_template_workbook() -> Workbook:
    workbook = Workbook()
    workbook.remove(workbook.active)
    option_ranges = build_options_sheet(workbook)

    for schema in LEGACY_DATA_SHEETS:
        worksheet = workbook.create_sheet(schema["name"])
        for index, column in enumerate(schema["columns"], start=1):
            cell = worksheet.cell(row=1, column=index, value=column["label"])
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.border = THIN_BORDER
            worksheet.column_dimensions[get_column_letter(index)].width = 18

    info_sheet = workbook.create_sheet("填写说明")
    info_sheet["A1"] = "旧版行式模板，仅保留兼容读取。"
    info_sheet["A1"].fill = SECTION_FILL
    info_sheet["A1"].font = SECTION_FONT

    workbook._sheets = [workbook[name] for name in LEGACY_SHEET_NAMES] + [workbook[OPTION_SHEET_NAME]]
    return workbook


def build_contract_markdown() -> str:
    lines = [
        "# 标准化筛号需求模板 Contract",
        "",
        f"- 模板版本：`{WORKBOOK_VERSION}`",
        f"- Excel 路径：`{DEFAULT_TEMPLATE_PATH.relative_to(ROOT_DIR)}`",
        "- 新版分区式需求主表是唯一默认入口。",
        "- source of truth 只来自主表固定区块和固定单元格。",
        "- `compiler_preview` 只作为输出预览，不作为输入来源。",
        "- 旧版行式模板只保留兼容读取，不再继续扩展功能。",
        "",
        "## Sheet 结构",
        "",
        "| Sheet | 角色 | 输入 / 输出 | 说明 |",
        "| --- | --- | --- | --- |",
        f"| {MAIN_SHEET_NAME} | 主表 | 输入 | 品牌方 / 内部统一填写入口。 |",
        f"| {PREVIEW_SHEET_NAME} | 预览表 | 输出 | 编译后系统生成的内部规则预览。 |",
        f"| {OPTION_SHEET_NAME} | 隐藏选项 | 系统 | 下拉选项源。 |",
        "",
    ]

    for section in SECTIONED_FIELD_DEFS:
        lines.extend([
            f"## {section['title']}",
            "",
            f"- 区块标题位置：`A{section['title_row']}:C{section['title_row']}`",
            "",
            "| 字段 | value cell | note cell | 必填 | 类型 | 默认值 | 编译规则 | 校验失败时错误 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ])
        for field in section["fields"]:
            required = "是" if field.get("required") else "否"
            default = field.get("default", "") or "-"
            lines.append(
                f"| {field['label']} | `{value_cell(field['row'])}` | `{note_cell(field['row'])}` | {required} | {field['type']} | {default} | {field['compile_rule']} | {field.get('error_message') or '-'} |"
            )
        lines.append("")

        if section["section_key"] == "visual_audit":
            lines.extend([
                "### 自动化特征固定行",
                "",
                "| 特征 | value cell | note cell | 编译规则 |",
                "| --- | --- | --- | --- |",
            ])
            for feature in VISUAL_FEATURE_DEFS:
                lines.append(
                    f"| {feature['label']} | `{value_cell(feature['row'])}` | `{note_cell(feature['row'])}` | 编译为 `visual_feature_group.features[]` 成员 |"
                )
            lines.extend([
                "",
                "- `鲜明人设 / 垂直 niche` 不在此区块，统一放到 `F. 人工判断项 / 合规提醒`。",
                "",
            ])

    lines.extend([
        "## 编译约束",
        "",
        "- `内容 / 视觉审核` 只保留封面能稳定看出来的自动化项。",
        "- 受保护属性相关内容永远不进入 `rulespec.json`，只保留为 `structured_requirement.json` 的合规提醒。",
        "- 自由文本的 `其他排除项` 与 `其他主观判断项` 不自动编译为 RuleSpec，只保留为人工项 / 备注。",
        "- `compiler_preview` 由主表编译生成，不反向参与解析。",
        "",
        "## 编译输出",
        "",
        "| 文件 / 产物 | 内容 |",
        "| --- | --- |",
        "| `structured_requirement.json` | 主表固定单元格解析后的结构化需求。 |",
        "| `rulespec.json` | 仅包含稳定可自动化项的 RuleSpec。 |",
        "| `compiled_requirement_workbook.xlsx` | 附带 `compiler_preview` 预览 sheet 的编译结果工作簿。 |",
        "",
        "## 兼容策略",
        "",
        "- 旧版行式模板仍可通过 `parse` 读取，但不再作为默认生成模板。",
        "- 新功能只围绕分区式主表扩展。",
        "",
    ])

    return "\n".join(lines)


def build_employee_manual_markdown() -> str:
    lines = [
        "# 标准化筛号需求模板填写手册",
        "",
        f"- 对应 Excel：`{DEFAULT_TEMPLATE_PATH.relative_to(ROOT_DIR)}`",
        f"- 当前版本：`{WORKBOOK_VERSION}`",
        "- 这份手册是给员工看的，不需要理解 RuleSpec、compiler、JSON。",
        "- 你只需要打开 Excel 主表，按照业务需求把每个区块填好即可。",
        "",
        "## 先记住 3 件事",
        "",
        "1. 只填写 `需求主表` 这一张表。",
        "2. 能用下拉选项就用下拉选项，不要自己改写。",
        "3. 不确定能不能自动判断的内容，优先放到 `F. 人工判断项 / 合规提醒`。",
        "",
        "## 一张表怎么填",
        "",
        "Excel 里每一行通常有 3 列：",
        "",
        "- `A 列`：字段名称，不用改。",
        "- `B 列`：你真正要填写的值。",
        "- `C 列`：示例和提示，不是正式填写区。",
        "",
        "简单理解：",
        "",
        "- `B` 列填“这个品牌到底想怎么筛人”。",
        "- `C` 列只是告诉你“可以怎么写”。",
        "",
        "## 填表顺序建议",
        "",
        "建议从上到下按这个顺序填：",
        "",
        "1. 先填 `A. 基本信息`",
        "2. 再填 `B. 基础资质审核`",
        "3. 再填 `C. 数据审核`",
        "4. 再填 `D. 内容 / 视觉审核`",
        "5. 再填 `E. 排除项审核`",
        "6. 最后填 `F. 人工判断项 / 合规提醒` 和 `G. 最终判定逻辑`",
        "",
        "如果品牌方给你的是一整段 SOP，也不要原文整段复制进去，而是按这 7 个区块拆开填。",
        "",
        "## A. 基本信息怎么填",
        "",
        "- `项目名称`：写清楚这次筛号任务的名字。",
        "- `品牌 / 产品`：写品牌名或产品线。",
        "- `适用平台`：选 `TikTok`、`Instagram` 或 `两者`。",
        "- `审核目标`：一句话说明想找什么样的达人。",
        "- `参考账号`：如果有正向参考达人，可以填。",
        "- `反例账号`：如果有明显不想要的账号，也可以填。",
        "- `备注`：补充背景，比如“这个项目偏家庭场景，不要强剧情号”。",
        "",
        "示例：",
        "",
        "- 项目名称：`Tapo 北美生活方式达人筛号`",
        "- 品牌 / 产品：`Tapo 智能家居`",
        "- 适用平台：`两者`",
        "- 审核目标：`判断达人是否符合家庭 / 宠物 / 户外生活场景合作标准`",
        "",
        "## B. 基础资质审核怎么填",
        "",
        "这一块适合填写账号的基础门槛，例如：",
        "",
        "- 地区要求",
        "- 语言要求",
        "- 不符合就直接淘汰，还是转人工再看",
        "",
        "适合写的：",
        "",
        "- `美国, 加拿大`",
        "- `英语, English`",
        "",
        "不适合写的：",
        "",
        "- 一长段自然语言描述",
        "- 视频播放量、粉丝数这类数据条件",
        "",
        "## C. 数据审核怎么填",
        "",
        "这一块只放数字门槛。",
        "",
        "常见写法：",
        "",
        "- `取样视频数`：通常填 `50`",
        "- `平均播放量阈值`：比如 `10000`",
        "- `中位数播放量阈值`：比如 `10000`",
        "- `粉丝数阈值`：如果品牌有要求再填，没有就留空",
        "- `最近活跃要求`：比如 `30`，表示近 30 天内要有更新",
        "- `判定关系`：如果品牌说“都要满足”，填 `同时满足`；如果说“满足其中一个就可以”，填 `任一满足`",
        "",
        "注意：",
        "",
        "- 不要写 `>10000`，只写数字 `10000`。",
        "- 百分比也只写数字，比如 `50`，不要写 `%`。",
        "",
        "## D. 内容 / 视觉审核怎么填",
        "",
        "这一块只保留“看封面就能相对稳定判断”的内容。",
        "",
        "你只需要做两件事：",
        "",
        "- 先填看多少张封面，比如 `18`",
        "- 再把需要的特征改成 `是`",
        "",
        "可以放在这里的特征有：",
        "",
        "- 多人互动",
        "- Speaking-led",
        "- 真实生活场景",
        "- 孩子互动",
        "- 产品展示",
        "- 户外庭院",
        "- 宠物互动",
        "",
        "不要放在这里的内容：",
        "",
        "- 鲜明人设 / 垂直 niche",
        "- 评论区情况",
        "- 完整视频内容判断",
        "- 年龄 / 种族等敏感属性",
        "",
        "这些都应该去 `F. 人工判断项 / 合规提醒`。",
        "",
        "## E. 排除项审核怎么填",
        "",
        "这一块写“出现什么情况就不想要”。",
        "",
        "常见能填的有：",
        "",
        "- 文本关键词排除：比如 `beauty, makeup, skincare`",
        "- 关系词排除：比如 `partner, boyfriend, girlfriend, husband, wife`",
        "- 美妆内容占比阈值：比如 `50`",
        "- 多人跳舞占比阈值：比如 `30`",
        "- 自拍 / 情侣出镜占比阈值：比如 `70`",
        "- 绿幕是否直接排除：选 `是` 或 `否`",
        "",
        "`其他排除项` 怎么用：",
        "",
        "- 如果品牌方给了很主观、很难自动化的排除要求，可以先写在这里做记录。",
        "- 但要知道：这里的自由文本不一定会进入自动规则，很多时候只会进入人工提醒。",
        "",
        "## F. 人工判断项 / 合规提醒怎么填",
        "",
        "只要你觉得“系统自己判断不稳”，就放这里。",
        "",
        "典型情况：",
        "",
        "- 评论区 emoji 异常",
        "- 鲜明人设 / 垂直 niche",
        "- 完整视频内容判断",
        "- 其他主观判断项",
        "",
        "最重要的一条：",
        "",
        "- 只要涉及年龄、种族、民族等受保护属性，永远只写在 `受保护属性相关判断` 这一格里，当作合规提醒。",
        "- 这种内容不会进入自动通过 / 不通过规则。",
        "",
        "## G. 最终判定逻辑怎么填",
        "",
        "这一块就是告诉系统“最后怎么下结论”。",
        "",
        "- `必须满足哪些步骤`：通常填 `步骤1：基础资质审核,步骤2：数据审核,步骤3：内容 / 视觉审核`",
        "- `任一触发即不通过的项`：通常填 `步骤4：排除项审核`",
        "- `人工判断项命中时如何处理`：一般填 `转人工`",
        "- `满足条件时输出`：一般填 `通过`",
        "- `不满足时输出`：一般填 `不通过`",
        "",
        "## 你可以直接照着填的例子",
        "",
        "如果品牌方说：",
        "",
        "> 账号地区要美国 / 加拿大，语言要英语；最近 50 条视频平均播放量和中位数都要大于 10000；封面里只要出现孩子互动、产品展示、户外庭院或宠物互动任意一种就可以；如果美妆内容占比过高则淘汰。",
        "",
        "你可以拆成这样填：",
        "",
        "- `B15` 地区要求：`美国, 加拿大`",
        "- `B16` 语言要求：`英语, English`",
        "- `B23` 取样视频数：`50`",
        "- `B24` 平均播放量阈值：`10000`",
        "- `B25` 中位数播放量阈值：`10000`",
        "- `B41` 孩子互动：`是`",
        "- `B42` 产品展示：`是`",
        "- `B43` 户外庭院：`是`",
        "- `B44` 宠物互动：`是`",
        "- `B48` 文本关键词排除：`beauty, makeup, skincare`",
        "- `B50` 美妆内容占比阈值：`50`",
        "",
        "## 常见错误",
        "",
        "- 把整段 SOP 原文直接贴进某一个单元格",
        "- 该用下拉时不用下拉，自己写了别的词",
        "- 数字格里写 `>10000`、`50%` 这种带符号的内容",
        "- 把 `鲜明人设 / 垂直 niche` 填进视觉自动化项",
        "- 把年龄 / 种族等敏感属性当成自动淘汰规则",
        "",
        "## 不会填时怎么判断",
        "",
        "如果你分不清该填哪里，用这个最简单的判断方法：",
        "",
        "- 是账号基础门槛？放 `B. 基础资质审核`",
        "- 是数字门槛？放 `C. 数据审核`",
        "- 是封面一眼能看出来的特征？放 `D. 内容 / 视觉审核`",
        "- 是排雷条件？放 `E. 排除项审核`",
        "- 是主观、模糊、敏感、需要人工看的？放 `F. 人工判断项 / 合规提醒`",
        "",
        "## 最后一句",
        "",
        "宁可少放一点自动规则，也不要把不稳定、主观或敏感的判断硬塞进自动化。拿不准时，优先转到人工判断。",
        "",
    ]
    return "\n".join(lines)


def save_template(template_path: Path, spec_path: Path) -> dict[str, str]:
    ensure_parent(template_path)
    ensure_parent(spec_path)
    contract_path = DEFAULT_CONTRACT_PATH
    ensure_parent(contract_path)
    workbook = create_template_workbook()
    workbook.save(template_path)
    spec_path.write_text(build_employee_manual_markdown(), encoding="utf-8")
    contract_path.write_text(build_contract_markdown(), encoding="utf-8")
    return {
        "template_path": str(template_path),
        "spec_path": str(spec_path),
        "contract_path": str(contract_path),
    }


def parse_field_value(raw_value: str, field: dict[str, Any]) -> Any:
    field_type = field["type"]
    if field_type == "string":
        return raw_value or None
    if field_type == "list":
        return split_list_text(raw_value)
    if field_type == "int":
        return parse_optional_int(raw_value)
    if field_type == "choice":
        if not raw_value:
            return None
        normalizer = field.get("normalizer")
        return normalizer(raw_value) if normalizer else raw_value
    if field_type == "step_list":
        values = split_list_text(raw_value)
        normalized_steps = []
        for item in values:
            if item not in STEP_NAME_MAP:
                return None
            normalized_steps.append(STEP_NAME_MAP[item])
        return normalized_steps
    raise ValueError(f"Unsupported field type: {field_type}")


def collect_sectioned_requirement(worksheet) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    requirement: dict[str, Any] = {
        "version": WORKBOOK_VERSION,
        "layout": "sectioned_main_sheet_v1",
        "basic_info": {},
        "qualification": {},
        "data_audit": {},
        "visual_audit": {"features": []},
        "exclusions": {},
        "manual_review": {},
        "final_logic": {},
    }
    errors: list[dict[str, Any]] = []
    warnings: list[str] = []

    for section in SECTIONED_FIELD_DEFS:
        section_payload = requirement[section["section_key"]]
        for field in section["fields"]:
            raw_value = normalize_cell_value(worksheet[value_cell(field["row"])].value)
            note_value = normalize_cell_value(worksheet[note_cell(field["row"])].value)
            if not raw_value and field.get("default"):
                raw_value = str(field["default"])

            if field.get("required") and not raw_value:
                errors.append({
                    "field": field["key"],
                    "cell": value_cell(field["row"]),
                    "message": field["error_message"] or f"{field['label']} 不能为空",
                })
                continue

            try:
                parsed_value = parse_field_value(raw_value, field) if raw_value else (
                    [] if field["type"] in {"list", "step_list"} else None
                )
            except Exception:
                errors.append({
                    "field": field["key"],
                    "cell": value_cell(field["row"]),
                    "message": field["error_message"] or f"{field['label']} 格式无效",
                })
                continue

            if raw_value and field["type"] == "choice" and parsed_value is None:
                errors.append({
                    "field": field["key"],
                    "cell": value_cell(field["row"]),
                    "message": field["error_message"] or f"{field['label']} 不是有效选项",
                })
                continue
            if raw_value and field["type"] == "step_list" and parsed_value is None:
                errors.append({
                    "field": field["key"],
                    "cell": value_cell(field["row"]),
                    "message": field["error_message"],
                })
                continue

            section_payload[field["key"]] = parsed_value
            if note_value:
                section_payload[f"{field['key']}_note"] = note_value

    for feature in VISUAL_FEATURE_DEFS:
        raw_value = normalize_cell_value(worksheet[value_cell(feature["row"])].value) or "否"
        note_value = normalize_cell_value(worksheet[note_cell(feature["row"])].value)
        enabled = YES_NO_MAP.get(raw_value)
        if enabled is None:
            errors.append({
                "field": feature["key"],
                "cell": value_cell(feature["row"]),
                "message": f"{feature['label']} 只能填写 是 或 否",
            })
            continue
        requirement["visual_audit"]["features"].append({
            "key": feature["key"],
            "label": feature["label"],
            "enabled": enabled,
            "note": note_value or None,
            "rulespec_key": feature["rulespec_key"],
            "source_cell": value_cell(feature["row"]),
        })

    if requirement["manual_review"].get("protected_attribute_notice"):
        warnings.append("受保护属性相关内容只会进入合规提醒，不会编译进 RuleSpec。")
    if requirement["manual_review"].get("persona_or_niche_manual"):
        warnings.append("鲜明人设 / 垂直 niche 已固定归入人工判断项，不参与自动化视觉规则。")

    return requirement, errors, warnings


def resolve_supported_platforms(requested: list[str], capability_key: str) -> list[str]:
    supported = AUTOMATION_FIELD_SUPPORT.get(capability_key, [])
    return [platform for platform in requested if platform in supported]


def build_preview_row(
    preview_id: int,
    section: str,
    field_label: str,
    source_cell: str,
    status: str,
    rule_type: str,
    platforms: list[str],
    normalized_value: Any,
    note: str,
) -> dict[str, Any]:
    return {
        "preview_id": f"P{preview_id:03d}",
        "section": section,
        "field_label": field_label,
        "source_cell": source_cell,
        "status": status,
        "rule_type": rule_type,
        "platforms": ", ".join(platforms) if platforms else "-",
        "normalized_value": normalized_value if isinstance(normalized_value, str) else json.dumps(normalized_value, ensure_ascii=False),
        "note": note or "",
    }


def compile_structured_requirement(structured_requirement: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    requested_platforms = structured_requirement["basic_info"]["platform_scope"]
    rules: list[dict[str, Any]] = []
    preview_rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    compile_errors: list[dict[str, Any]] = []
    preview_id = 1

    def add_preview(section: str, field_label: str, source_cell: str, status: str, rule_type: str, platforms: list[str], normalized_value: Any, note: str) -> None:
        nonlocal preview_id
        preview_rows.append(build_preview_row(preview_id, section, field_label, source_cell, status, rule_type, platforms, normalized_value, note))
        preview_id += 1

    qualification = structured_requirement["qualification"]
    qualification_platforms = resolve_supported_platforms(requested_platforms, "region_requirement")
    if qualification.get("region_requirement"):
        if qualification_platforms:
            rules.append({
                "id": "qualification_region_gate",
                "step": "step_1_qualification",
                "rule_type": "region_gate",
                "platforms": qualification_platforms,
                "operator": "contains_any",
                "values": qualification["region_requirement"],
                "check_scope": qualification.get("check_scope"),
                "fail_action": qualification.get("fail_action") or "reject",
                "source_cell": "B15",
            })
            add_preview("步骤1：基础资质审核", "地区要求", "B15", "compiled", "region_gate", qualification_platforms, qualification["region_requirement"], qualification.get("region_requirement_note", ""))
        else:
            warnings.append("地区要求 当前只支持 Instagram，已跳过不支持的平台。")
            add_preview("步骤1：基础资质审核", "地区要求", "B15", "unsupported", "region_gate", [], qualification["region_requirement"], "当前字段仅支持 Instagram。")

    language_platforms = resolve_supported_platforms(requested_platforms, "language_requirement")
    if qualification.get("language_requirement"):
        if language_platforms:
            rules.append({
                "id": "qualification_language_gate",
                "step": "step_1_qualification",
                "rule_type": "language_gate",
                "platforms": language_platforms,
                "operator": "contains_any",
                "values": qualification["language_requirement"],
                "check_scope": qualification.get("check_scope"),
                "fail_action": qualification.get("fail_action") or "reject",
                "source_cell": "B16",
            })
            add_preview("步骤1：基础资质审核", "语言要求", "B16", "compiled", "language_gate", language_platforms, qualification["language_requirement"], qualification.get("language_requirement_note", ""))
        else:
            warnings.append("语言要求 当前只支持 Instagram，已跳过不支持的平台。")
            add_preview("步骤1：基础资质审核", "语言要求", "B16", "unsupported", "language_gate", [], qualification["language_requirement"], "当前字段仅支持 Instagram。")

    data_audit = structured_requirement["data_audit"]
    sample_size = data_audit.get("sample_size") or 50
    data_step_rules = []
    for field_key, rule_id, metric_key, source_cell in [
        ("mean_view_threshold", "data_mean_view_threshold", "view_count_mean", "B24"),
        ("median_view_threshold", "data_median_view_threshold", "view_count_median", "B25"),
        ("follower_threshold", "data_follower_threshold", "follower_count", "B26"),
        ("recent_active_days", "data_recent_active_days", "activity_recency_days", "B27"),
    ]:
        threshold = data_audit.get(field_key)
        if threshold is None:
            continue
        supported = resolve_supported_platforms(requested_platforms, field_key)
        if not supported:
            warnings.append(f"{field_key} 当前平台范围内没有稳定字段支持，已跳过。")
            add_preview("步骤2：数据审核", field_key, source_cell, "unsupported", metric_key, [], threshold, "当前平台范围内没有稳定字段支持。")
            continue
        operator = ">" if field_key != "recent_active_days" else "<="
        compiled_rule = {
            "id": rule_id,
            "step": "step_2_data",
            "rule_type": "metric_threshold",
            "metric_key": metric_key,
            "platforms": supported,
            "operator": operator,
            "threshold": threshold,
            "window": {"size": sample_size, "unit": "posts"} if field_key in {"mean_view_threshold", "median_view_threshold"} else None,
            "fail_action": data_audit.get("fail_action") or "reject",
            "source_cell": source_cell,
        }
        data_step_rules.append(compiled_rule)
        add_preview("步骤2：数据审核", field_key, source_cell, "compiled", metric_key, supported, threshold, "")

    rules.extend(data_step_rules)

    visual_audit = structured_requirement["visual_audit"]
    enabled_features = [feature for feature in visual_audit["features"] if feature["enabled"]]
    visual_platforms = resolve_supported_platforms(requested_platforms, "visual_features")
    if enabled_features:
        if visual_platforms:
            rules.append({
                "id": "visual_feature_group",
                "step": "step_3_visual",
                "rule_type": "visual_feature_group",
                "platforms": visual_platforms,
                "cover_count": visual_audit.get("cover_count") or 18,
                "min_hit_features": visual_audit.get("min_hit_features") or 1,
                "features": [
                    {"key": feature["rulespec_key"], "label": feature["label"], "note": feature.get("note")}
                    for feature in enabled_features
                ],
                "source_cells": [feature["source_cell"] for feature in enabled_features],
            })
            for feature in enabled_features:
                add_preview("步骤3：内容 / 视觉审核", feature["label"], feature["source_cell"], "compiled", "visual_feature", visual_platforms, True, feature.get("note") or "")
        else:
            warnings.append("视觉特征当前没有可用平台支持，已全部跳过。")
            for feature in enabled_features:
                add_preview("步骤3：内容 / 视觉审核", feature["label"], feature["source_cell"], "unsupported", "visual_feature", [], True, "当前平台范围内没有稳定字段支持。")

    exclusions = structured_requirement["exclusions"]
    for field_key, rule_id, rule_type, source_cell in [
        ("text_keyword_blocklist", "exclusion_text_keywords", "text_keyword_blocklist", "B48"),
        ("relationship_keyword_blocklist", "exclusion_relationship_keywords", "relationship_keyword_block", "B49"),
    ]:
        values = exclusions.get(field_key)
        if not values:
            continue
        supported = resolve_supported_platforms(requested_platforms, field_key)
        if not supported:
            warnings.append(f"{field_key} 当前平台范围内没有稳定字段支持，已跳过。")
            add_preview("步骤4：排除项审核", field_key, source_cell, "unsupported", rule_type, [], values, "当前平台范围内没有稳定字段支持。")
            continue
        rules.append({
            "id": rule_id,
            "step": "step_4_exclusions",
            "rule_type": rule_type,
            "platforms": supported,
            "values": values,
            "operator": "contains_any",
            "source_cell": source_cell,
        })
        add_preview("步骤4：排除项审核", field_key, source_cell, "compiled", rule_type, supported, values, "")

    for field_key, rule_id, rule_type, source_cell in [
        ("beauty_ratio_threshold", "exclusion_beauty_ratio", "content_keyword_ratio", "B50"),
        ("multi_dance_ratio_threshold", "exclusion_multi_dance_ratio", "multi_dance_ratio", "B51"),
        ("selfie_couple_ratio_threshold", "exclusion_selfie_couple_ratio", "selfie_or_couple_ratio", "B52"),
    ]:
        threshold = exclusions.get(field_key)
        if threshold is None:
            continue
        supported = resolve_supported_platforms(requested_platforms, field_key)
        if not supported:
            warnings.append(f"{field_key} 当前平台范围内没有稳定字段支持，已跳过。")
            add_preview("步骤4：排除项审核", field_key, source_cell, "unsupported", rule_type, [], threshold, "当前平台范围内没有稳定字段支持。")
            continue
        rule_payload = {
            "id": rule_id,
            "step": "step_4_exclusions",
            "rule_type": rule_type,
            "platforms": supported,
            "operator": "ratio_gt",
            "threshold_percent": threshold,
            "source_cell": source_cell,
        }
        if field_key == "beauty_ratio_threshold":
            rule_payload["keyword_values"] = exclusions.get("text_keyword_blocklist") or []
        rules.append(rule_payload)
        add_preview("步骤4：排除项审核", field_key, source_cell, "compiled", rule_type, supported, threshold, "")

    if exclusions.get("green_screen_direct_reject"):
        supported = resolve_supported_platforms(requested_platforms, "green_screen_direct_reject")
        if supported:
            rules.append({
                "id": "exclusion_green_screen",
                "step": "step_4_exclusions",
                "rule_type": "green_screen",
                "platforms": supported,
                "operator": "must_not_appear",
                "source_cell": "B53",
            })
            add_preview("步骤4：排除项审核", "green_screen_direct_reject", "B53", "compiled", "green_screen", supported, True, "")
        else:
            add_preview("步骤4：排除项审核", "green_screen_direct_reject", "B53", "unsupported", "green_screen", [], True, "当前平台范围内没有稳定字段支持。")

    manual_review_items = []
    manual_review = structured_requirement["manual_review"]
    for field_key, label, source_cell in [
        ("comment_emoji_abnormal", "评论区 emoji 异常", "B59"),
        ("persona_or_niche_manual", "鲜明人设 / 垂直 niche", "B60"),
        ("full_video_review", "完整视频内容判断", "B61"),
    ]:
        if manual_review.get(field_key):
            manual_review_items.append({"key": field_key, "label": label, "source_cell": source_cell})
            add_preview("F. 人工判断项 / 合规提醒", label, source_cell, "manual_only", "manual_review_item", [], True, "")

    if manual_review.get("other_subjective_items"):
        manual_review_items.append({
            "key": "other_subjective_items",
            "label": "其他主观判断项",
            "value": manual_review["other_subjective_items"],
            "source_cell": "B62",
        })
        add_preview("F. 人工判断项 / 合规提醒", "其他主观判断项", "B62", "manual_only", "manual_review_item", [], manual_review["other_subjective_items"], "")

    compliance_notes = []
    if manual_review.get("protected_attribute_notice"):
        compliance_notes.append({
            "key": "protected_attribute_notice",
            "label": "受保护属性相关判断",
            "value": manual_review["protected_attribute_notice"],
            "source_cell": "B63",
            "policy": "never_compile_to_rulespec",
        })
        add_preview("F. 人工判断项 / 合规提醒", "受保护属性相关判断", "B63", "compliance_only", "protected_attribute_notice", [], manual_review["protected_attribute_notice"], "永不进入 RuleSpec。")

    final_logic = structured_requirement["final_logic"]
    compiled_step_ids = {rule["step"] for rule in rules}
    for step_id in final_logic.get("must_pass_steps") or []:
        if step_id not in compiled_step_ids:
            compile_errors.append({
                "field": "must_pass_steps",
                "cell": "B68",
                "message": f"{STEP_ID_TO_LABEL[step_id]} 被列为必须满足，但当前没有任何可编译规则。",
            })
    for step_id in final_logic.get("reject_if_any_steps") or []:
        if step_id not in compiled_step_ids:
            compile_errors.append({
                "field": "reject_if_any_steps",
                "cell": "B69",
                "message": f"{STEP_ID_TO_LABEL[step_id]} 被列为任一触发即不通过，但当前没有任何可编译规则。",
            })

    rulespec = {
        "version": WORKBOOK_VERSION,
        "compile_mode": "workbook_strict_v1",
        "source_layout": "sectioned_main_sheet_v1",
        "basic_info": deepcopy(structured_requirement["basic_info"]),
        "platform_scope": requested_platforms,
        "rules": rules,
        "manual_review_items": manual_review_items,
        "compliance_notes": compliance_notes,
        "final_logic": {
            "must_pass_steps": final_logic.get("must_pass_steps") or [],
            "reject_if_any_steps": final_logic.get("reject_if_any_steps") or [],
            "manual_hit_action": final_logic.get("manual_hit_action"),
            "success_output": final_logic.get("success_output"),
            "failure_output": final_logic.get("failure_output"),
        },
    }
    return rulespec, preview_rows, warnings, compile_errors


def populate_preview_sheet(workbook: Workbook, preview_rows: list[dict[str, Any]]) -> None:
    worksheet = workbook[PREVIEW_SHEET_NAME]
    worksheet.sheet_state = "hidden"
    for row in range(2, worksheet.max_row + 1):
        for col in range(1, len(PREVIEW_HEADERS) + 1):
            worksheet.cell(row=row, column=col, value=None)

    for row_index, row in enumerate(preview_rows, start=2):
        values = [
            row["preview_id"],
            row["section"],
            row["field_label"],
            row["source_cell"],
            row["status"],
            row["rule_type"],
            row["platforms"],
            row["normalized_value"],
            row["note"],
        ]
        for col_index, value in enumerate(values, start=1):
            cell = worksheet.cell(row=row_index, column=col_index, value=value)
            cell.border = THIN_BORDER


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_compile_output_dir(output_dir: str | None = None) -> Path:
    if output_dir:
        path = Path(output_dir)
        ensure_parent(path / "placeholder.txt")
        path.mkdir(parents=True, exist_ok=True)
        return path
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    path = DEFAULT_OUTPUT_ROOT / f"workbook-{timestamp}-{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def parse_sectioned_workbook(workbook_path: Path) -> dict[str, Any]:
    workbook = load_workbook(workbook_path, data_only=True)
    if MAIN_SHEET_NAME not in workbook.sheetnames:
        raise ValueError(f"模板缺少工作表：{MAIN_SHEET_NAME}")
    requirement, errors, warnings = collect_sectioned_requirement(workbook[MAIN_SHEET_NAME])
    return {
        "version": WORKBOOK_VERSION,
        "layout": "sectioned_main_sheet_v1",
        "workbook_path": str(workbook_path),
        "structured_requirement": requirement,
        "errors": errors,
        "warnings": warnings,
        "parsed_at": datetime.utcnow().isoformat() + "Z",
    }


def compile_requirement_workbook(workbook_path: Path, output_dir: str | None = None) -> dict[str, Any]:
    parsed = parse_sectioned_workbook(workbook_path)
    if parsed["errors"]:
        return {
            "success": False,
            "stage": "parse",
            "structured_requirement": parsed.get("structured_requirement"),
            "errors": parsed["errors"],
            "warnings": parsed["warnings"],
        }

    structured_requirement = parsed["structured_requirement"]
    rulespec, preview_rows, compile_warnings, compile_errors = compile_structured_requirement(structured_requirement)
    warnings = list(parsed["warnings"]) + list(compile_warnings)
    if compile_errors:
        return {
            "success": False,
            "stage": "compile",
            "structured_requirement": structured_requirement,
            "rulespec": rulespec,
            "errors": compile_errors,
            "warnings": warnings,
            "preview_rows": preview_rows,
        }

    compiled_at = datetime.utcnow().isoformat() + "Z"
    rulespec["compiled_at"] = compiled_at
    output_root = build_compile_output_dir(output_dir)
    structured_path = output_root / "structured_requirement.json"
    rulespec_path = output_root / "rulespec.json"
    workbook_path_out = output_root / "compiled_requirement_workbook.xlsx"

    write_json(structured_path, structured_requirement)
    write_json(rulespec_path, rulespec)

    workbook = load_workbook(workbook_path)
    if PREVIEW_SHEET_NAME not in workbook.sheetnames:
        build_preview_sheet(workbook)
    populate_preview_sheet(workbook, preview_rows)
    workbook.save(workbook_path_out)

    return {
        "success": True,
        "stage": "compiled",
        "structured_requirement": structured_requirement,
        "rulespec": rulespec,
        "preview_rows": preview_rows,
        "warnings": warnings,
        "errors": [],
        "output_dir": str(output_root),
        "artifacts": {
            "structured_requirement_json": str(structured_path),
            "rulespec_json": str(rulespec_path),
            "compiled_workbook": str(workbook_path_out),
        },
    }


def find_header_row(worksheet, schema, search_limit: int = 20) -> int:
    expected_headers = [column["label"] for column in schema["columns"]]
    last_row = min(worksheet.max_row, search_limit)
    for row_index in range(1, last_row + 1):
        actual_headers = [
            normalize_cell_value(worksheet.cell(row=row_index, column=col).value)
            for col in range(1, len(expected_headers) + 1)
        ]
        if actual_headers == expected_headers:
            return row_index
    raise ValueError(f"{schema['name']} 表头不匹配。")


def normalize_legacy_sheet_rows(worksheet, schema):
    header_row = find_header_row(worksheet, schema)
    parsed_rows = []
    errors = []
    for row_index in range(header_row + 1, worksheet.max_row + 1):
        raw_row = {}
        any_value = False
        for column_index, column in enumerate(schema["columns"], start=1):
            text = normalize_cell_value(worksheet.cell(row=row_index, column=column_index).value)
            if text:
                any_value = True
            raw_row[column["key"]] = text
        if not any_value:
            continue

        normalized = {}
        row_errors = []
        for column in schema["columns"]:
            raw_value = raw_row[column["key"]]
            if column.get("required") and not raw_value:
                row_errors.append(f"{column['label']} 不能为空")
            normalizer = column.get("normalize")
            if normalizer:
                normalized_value = normalizer(raw_value)
                if raw_value and normalized_value is None:
                    row_errors.append(f"{column['label']} 不是有效选项：{raw_value}")
                normalized[column["key"]] = normalized_value
            else:
                normalized[column["key"]] = raw_value or None

        if schema["name"] == "自动初筛规则" and normalized.get("judgement_item"):
            normalized["field_basis"] = AUTO_RULE_ITEM_DEFS.get(raw_row["judgement_item"], {}).get("field_basis", [])
        if schema["name"] == "视觉复核规则" and normalized.get("visual_item"):
            normalized["field_basis"] = VISUAL_RULE_ITEM_DEFS.get(raw_row["visual_item"], {}).get("field_basis", [])
        if schema["name"] == "人工判断项" and raw_row.get("manual_item"):
            normalized["manual_reason"] = MANUAL_REVIEW_ITEM_DEFS.get(raw_row["manual_item"])

        parsed_rows.append({
            "row_number": row_index,
            "raw": raw_row,
            "normalized": normalized,
            "errors": row_errors,
        })
        if row_errors:
            errors.append({"sheet": schema["name"], "row": row_index, "errors": row_errors})
    return parsed_rows, errors


def parse_legacy_workbook(workbook_path: Path) -> dict[str, Any]:
    workbook = load_workbook(workbook_path, data_only=True)
    missing_sheets = [schema["name"] for schema in LEGACY_DATA_SHEETS if schema["name"] not in workbook.sheetnames]
    if missing_sheets:
        raise ValueError(f"模板缺少工作表：{', '.join(missing_sheets)}")
    sheet_results = {}
    errors = []
    for schema in LEGACY_DATA_SHEETS:
        rows, row_errors = normalize_legacy_sheet_rows(workbook[schema["name"]], schema)
        sheet_results[schema["slug"]] = rows
        errors.extend(row_errors)
    return {
        "version": WORKBOOK_VERSION,
        "layout": "legacy_multi_sheet",
        "workbook_path": str(workbook_path),
        "sheets": sheet_results,
        "errors": errors,
        "warnings": ["旧版行式模板仅保留兼容读取，不再继续扩展功能。"],
        "parsed_at": datetime.utcnow().isoformat() + "Z",
    }


def parse_requirement_workbook(workbook_path: Path) -> dict[str, Any]:
    workbook = load_workbook(workbook_path, data_only=True)
    if MAIN_SHEET_NAME in workbook.sheetnames:
        return parse_sectioned_workbook(workbook_path)
    return parse_legacy_workbook(workbook_path)


def main():
    parser = argparse.ArgumentParser(description="Build, parse, or compile the screening requirement workbook.")
    subparsers = parser.add_subparsers(dest="command")

    build_parser = subparsers.add_parser("build", help="Generate the workbook template and contract markdown")
    build_parser.add_argument("--template-path", default=str(DEFAULT_TEMPLATE_PATH))
    build_parser.add_argument("--spec-path", default=str(DEFAULT_SPEC_PATH))

    parse_parser = subparsers.add_parser("parse", help="Parse a workbook into structured JSON")
    parse_parser.add_argument("--input", required=True)

    compile_parser = subparsers.add_parser("compile", help="Compile a sectioned workbook into JSON artifacts")
    compile_parser.add_argument("--input", required=True)
    compile_parser.add_argument("--output-dir")

    args = parser.parse_args()
    command = args.command or "build"

    if command == "build":
        result = save_template(Path(args.template_path), Path(args.spec_path))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if command == "parse":
        result = parse_requirement_workbook(Path(args.input))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if command == "compile":
        result = compile_requirement_workbook(Path(args.input), output_dir=args.output_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    raise SystemExit(f"Unsupported command: {command}")


if __name__ == "__main__":
    main()
