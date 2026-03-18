#!/usr/bin/env python3
from generate_screening_templates import (
    build_platform_capabilities,
    build_platform_template,
    load_field_mapping,
    parse_sop_text,
)


SAMPLE_TAPO = """【AI 审核目标】
判断该达人是否符合 Tapo 家庭/宠物/户外生活场景类内容合作标准。

【步骤 1：数据审核】
- 抓取最近前 50 个视频播放量
- 计算平均播放量和中位数播放量
- 若平均播放量 > 10000 且中位数播放量 > 10000，则通过
- 否则不通过

【步骤 2：内容场景审核】
- 查看最近前 10 个视频封面
- 判断是否出现以下任一场景：
  A. 室内环境和孩子互动
  B. 手持或展示产品
  C. 室外环境、庭院、院子
  D. 与宠物互动
- 若至少出现 1 类场景，则通过
- 若 4 类场景都未出现，则不通过

【步骤 3：排除项审核】
- 查看前 100 个视频标题，判断美妆相关内容占比
- 若美妆相关内容 > 50%，直接不通过

- 查看前 10 个视频封面
- 若自拍或情侣两人出镜占比 >= 70%，且封面中基本无产品、无宠物、无孩子，则直接不通过

【最终结果】
- 同时满足步骤 1、步骤 2
- 且不触发步骤 3 任一排除项
- 最终判定为“通过”
- 否则判定为“不通过”
"""


SAMPLE_INTERACTIVE = """【步骤 1：基础资质审核】
确认账号地区为美国、加拿大本土（查看主页简介）
确认内容语言以英语为主（非英语内容账号直接不通过）
若以上任一不符合，直接不通过

【步骤 2：内容风格审核】
查看最近前 10 个视频封面及内容
判断是否出现以下任一特征：
A. 多人出镜对话（街访、朋友互动、陌生人交流等）
B. Speaking-led（镜头前开口说话，有表达能力）
C. 真实生活场景（非绿幕、非剧本感情景剧）
D. 有鲜明人设或垂直 niche（运动、校园、约会等）
若至少出现 1 类特征，则通过

【步骤 3：受众与互动审核】
查看近期 5 个视频的评论区，若评论多为 emoji 则不通过
查看前 100 个视频标题及封面，若人物多为中老年则不通过

【步骤 4：排除项审核】
查看前 100 个视频标题及封面，判断以下内容占比：
若多人跳舞 > 30%，直接不通过
若多为黑人，直接不通过
若 solo 单人 POV 内容（无互动、无第二人）占比 > 50%，直接不通过
查看前 10 个视频封面：
若出现绿幕背景，直接不通过
若出现“partner”“boyfriend”“girlfriend”“husband”“wife”则不通过
"""


SAMPLE_BUSINESS_FLOW = """达人商务 AI 流程搭建
红人资源开发：由红人开发专员在市场上各种渠道获取网红名单和联系方式。
1. 获取资源（第三方数据库，easykol 爬虫和数据库）
2. 群发信建联
- 上传发信名单
- 通过多个公共邮箱发信
3. 红人回信
- 获取回信名单
- 红人的报价层级（如果没给，则 AI 立刻追问）
4. 筛号
- 粉丝量
- 播放量（近 10-30 条中位数/近一个月中位数）
- 评论中好评或者对视频中出现的产品的好评占比大于 50%
- 封面：是否有植入产品的内容场景
5. 把合适的名单自动同步内部表，PM 审核并报价
- 接入飞书 MCP
6. 品牌方砍价反馈
- 品牌方选择不合作，则 ai 自动回信婉拒达人
7. 选中跟进
- 邮件看板：检查品牌选中的达人邮件回复情况
"""


def find_checks(template, check_type):
    return [item for item in template["checks"] if item["check_type"] == check_type]


def test_tapo_template_generation():
    parsed = parse_sop_text(SAMPLE_TAPO)
    assert parsed["goal"].startswith("判断该达人是否符合 Tapo")
    assert parsed["final_decision"]["logic_hint"] == "step_1 && step_2 && !step_3"

    check_types = [item["check_type"] for item in parsed["rules"]]
    assert "metric_threshold" in check_types
    assert "vision_presence" in check_types
    assert "keyword_ratio" in check_types
    assert "vision_ratio_threshold" in check_types

    capabilities = build_platform_capabilities(load_field_mapping())
    tiktok = build_platform_template(parsed, "tiktok", capabilities["tiktok"])
    instagram = build_platform_template(parsed, "instagram", capabilities["instagram"])

    metric_rules = find_checks(tiktok, "metric_threshold")
    assert metric_rules
    assert all(item["status"] == "supported" for item in metric_rules)

    instagram_metric_rules = find_checks(instagram, "metric_threshold")
    assert instagram_metric_rules
    assert all(item["status"] == "partial" for item in instagram_metric_rules)


def test_sensitive_and_comment_gaps():
    parsed = parse_sop_text(SAMPLE_INTERACTIVE)
    capabilities = build_platform_capabilities(load_field_mapping())

    instagram = build_platform_template(parsed, "instagram", capabilities["instagram"])
    youtube = build_platform_template(parsed, "youtube", capabilities["youtube"])

    comment_rules = find_checks(instagram, "comment_quality")
    assert comment_rules
    assert comment_rules[0]["status"] == "unsupported"

    blocked_rules = instagram["blocked_rules"]
    assert blocked_rules
    assert any(item["status"] == "blocked_sensitive_attribute" for item in blocked_rules)

    youtube_keyword_rules = find_checks(youtube, "keyword_presence")
    assert youtube_keyword_rules
    assert youtube_keyword_rules[0]["status"] == "supported"


def test_numeric_steps_and_manual_requirements():
    parsed = parse_sop_text(SAMPLE_BUSINESS_FLOW)
    assert len(parsed["steps"]) == 7

    rule_types = [item["check_type"] for item in parsed["rules"]]
    assert "manual_requirement" in rule_types
    assert "keyword_ratio" in rule_types

    capabilities = build_platform_capabilities(load_field_mapping())
    instagram = build_platform_template(parsed, "instagram", capabilities["instagram"])
    assert any(item["check_type"] == "manual_requirement" for item in instagram["checks"])
    assert any(item["status"] == "unsupported" for item in instagram["checks"])


if __name__ == "__main__":
    test_tapo_template_generation()
    test_sensitive_and_comment_gaps()
    test_numeric_steps_and_manual_requirements()
    print("ok")
