#!/usr/bin/env python3
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import backend.app as backend_app
import data_cleaner


def iso_days_ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_tiktok_items(count=60, days_ago=5, play_count=20000, text=""):
    items = []
    for idx in range(count):
        items.append({
            "createTimeISO": iso_days_ago(days_ago),
            "playCount": play_count,
            "text": text,
            "hashtags": [{"name": "beauty"}],
            "isSlideshow": False,
            "videoMeta": {
                "originalCoverUrl": f"https://example.com/covers/{idx}.jpg",
                "coverUrl": f"https://example.com/covers/{idx}.jpg",
            },
            "authorMeta": {
                "name": "creatoralpha",
                "profileUrl": "https://www.tiktok.com/@creatoralpha",
            },
        })
    return items


def build_instagram_profile(days_ago=5, captions=None):
    captions = captions or ["daily life"]
    return {
        "username": "creatorbeta",
        "url": "https://www.instagram.com/creatorbeta",
        "biography": "Seattle creator",
        "latestPosts": [
            {
                "timestamp": iso_days_ago(days_ago),
                "caption": caption,
                "displayUrl": f"https://example.com/ig/{idx}.jpg",
            }
            for idx, caption in enumerate(captions, start=1)
        ],
    }


def test_check_tiktok_tapo_rejects_inactive_accounts():
    result = data_cleaner.check_tiktok_tapo(build_tiktok_items(days_ago=45))
    assert result["status"] == "Reject", result
    assert result["reason"] == data_cleaner.REASON_INACTIVE, result


def test_check_tiktok_tapo_no_longer_rejects_beauty_ratio_only():
    items = build_tiktok_items(text="makeup skincare get ready with me")
    result = data_cleaner.check_tiktok_tapo(items)
    assert result["status"] == "Pass", result
    assert "播放量达标" in result["reason"], result
    assert "beauty_ratio" not in (result.get("stats") or {}), result


def test_check_instagram_custom_uses_us_only_without_language_or_relationship_gate():
    profile = build_instagram_profile(captions=["date night with boyfriend", "couple vlog"])
    result = data_cleaner.check_instagram_custom(
        profile,
        upload_metadata={"region": "US", "language": "es"},
    )
    assert result["status"] == "Pass", result
    assert "地区符合（美国）" in result["reason"], result


def test_check_instagram_custom_rejects_canada_region():
    profile = build_instagram_profile()
    result = data_cleaner.check_instagram_custom(
        profile,
        upload_metadata={"region": "CA", "language": "en"},
    )
    assert result["status"] == "Reject", result
    assert "Region 未命中美国" in result["reason"], result


def test_tapo_visual_prompt_matches_new_template():
    prompt = backend_app.VISION_PROMPT_TAPO
    assert "Speaking-led" in prompt, prompt
    assert "真实生活场景" in prompt, prompt
    assert "孩子互动" in prompt, prompt
    assert "产品展示" in prompt, prompt
    assert "户外庭院" in prompt, prompt
    assert "宠物互动" in prompt, prompt
    assert "多人跳舞内容占比过高" in prompt, prompt
    assert "自拍/情侣出镜占比过高" in prompt, prompt
    assert "不要根据年龄、种族、民族等受保护属性做判断" in prompt, prompt
    assert "中老年" not in prompt, prompt
    assert "黑人" not in prompt, prompt
    assert backend_app.VISION_PROMPT_INSTAGRAM_CUSTOM == backend_app.VISION_PROMPT_TAPO


if __name__ == "__main__":
    test_check_tiktok_tapo_rejects_inactive_accounts()
    test_check_tiktok_tapo_no_longer_rejects_beauty_ratio_only()
    test_check_instagram_custom_uses_us_only_without_language_or_relationship_gate()
    test_check_instagram_custom_rejects_canada_region()
    test_tapo_visual_prompt_matches_new_template()
    print("ok")
