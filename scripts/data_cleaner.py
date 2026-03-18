import json
import os
import re
import statistics
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
VISUAL_REVIEW_COVER_LIMIT = 18


def get_profile_reviews_path(platform):
    return os.path.join(DATA_DIR, platform, f'{platform}_profile_reviews.json')


def save_profile_reviews(platform, profile_reviews):
    path = get_profile_reviews_path(platform)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(profile_reviews, f, indent=2, ensure_ascii=False)
    return path

# 核心排雷关键词库 (统一转小写进行匹配)
KILL_KEYWORDS = ['temu', 'shein', 'aliexpress', '$1', 'pregnant', 'baby', 'expecting', 'momlife', 'motherhood']
IG_HARD_REJECT_EXTERNAL_KEYWORDS = ['temu', 'shein', 'aliexpress', 'wish']
IG_HARD_REJECT_TEXT_KEYWORDS = ['temu', 'shein', 'aliexpress', 'wish', 'pregnancy', 'pregnant', 'baby coming', 'expecting']
IG_SOFT_FLAG_TEXT_KEYWORDS = ['$1', 'baby', 'momlife', 'motherhood']
YT_HARD_REJECT_EXTERNAL_KEYWORDS = ['temu', 'shein', 'aliexpress', 'wish']
YT_HARD_REJECT_TEXT_KEYWORDS = ['temu', 'shein', 'aliexpress', 'wish', 'pregnancy', 'pregnant', 'baby coming', 'expecting']
YT_SOFT_FLAG_TEXT_KEYWORDS = ['$1', 'baby', 'momlife', 'motherhood']
PRIORITY_KEYWORDS = ['doctor', 'dermatologist', 'yoga', 'pilates', 'aesthetic', 'finance', 'lawyer', 'entrepreneur']

# Tapo (智能家居) 审核常量
TAPO_RECENT_ACTIVE_DAYS = 30
TAPO_MIN_AVG_VIEWS = 10000
TAPO_MIN_MEDIAN_VIEWS = 10000

# Instagram 定制审核常量
IG_CUSTOM_REGION_KEYWORDS_US = [
    'usa', 'united states', 'united states of america', 'american',
    'alabama', 'alaska', 'arizona', 'arkansas', 'california', 'colorado', 'connecticut',
    'delaware', 'florida', 'georgia', 'hawaii', 'idaho', 'illinois', 'indiana', 'iowa',
    'kansas', 'kentucky', 'louisiana', 'maine', 'maryland', 'massachusetts', 'michigan',
    'minnesota', 'mississippi', 'missouri', 'montana', 'nebraska', 'nevada', 'new hampshire',
    'new jersey', 'new mexico', 'new york', 'north carolina', 'north dakota', 'ohio',
    'oklahoma', 'oregon', 'pennsylvania', 'rhode island', 'south carolina', 'south dakota',
    'tennessee', 'texas', 'utah', 'vermont', 'virginia', 'washington', 'west virginia',
    'wisconsin', 'wyoming', 'district of columbia', 'washington dc', 'washington d.c.',
    'new york city', 'nyc', 'los angeles', 'san francisco', 'san diego', 'san jose',
    'orange county', 'bay area', 'miami', 'orlando', 'tampa', 'jacksonville', 'atlanta',
    'chicago', 'houston', 'dallas', 'austin', 'phoenix', 'seattle', 'boston', 'philadelphia',
    'las vegas', 'vegas', 'denver', 'nashville', 'charlotte', 'brooklyn', 'manhattan',
]
IG_CUSTOM_REGION_REGEX_PATTERNS = [
    re.compile(r'\bu\.?\s*s\.?\s*a\.?\b'),
    re.compile(r'\bu\.?\s*n\.?\s*i\.?\s*t\.?\s*e\.?\s*d\.?\s*s\.?\s*t\.?\s*a\.?\s*t\.?\s*e\.?\s*s\.?\b'),
]
IG_CUSTOM_UPLOAD_REGION_US = {
    'us', 'usa', 'united states', 'united states of america',
}
REASON_NO_DATA = '未抓取到数据'
REASON_NO_POSTS = '账号没有可用帖子'
REASON_INACTIVE = '近 30 天无更新'
REASON_MISSING_PROFILE = '采集器未返回该账号数据'
REASON_TOO_MUCH_PAID_CONTENT = '近期付费内容占比过高'
PROFILE_REVIEW_ALLOWED_STATUSES = {'Pass', 'Reject', 'Missing'}

# 字段维护入口：
# - 机器可读字段字典：config/field_mapping.json
# - 可读版字段总览：docs/field_dictionary.md
# 每次改动主链路读取字段、关键词或阈值时，必须同步更新以上两个文件和对应 PRD。

def normalize_identifier(value):
    if value is None:
        return ''
    text = str(value).strip().lower()
    if not text:
        return ''

    instagram_match = re.search(r'instagram\.com/([^/?#]+)', text, re.IGNORECASE)
    if instagram_match:
        return instagram_match.group(1).strip().lower().lstrip('@')

    tiktok_match = re.search(r'tiktok\.com/@([^/?#]+)', text, re.IGNORECASE)
    if tiktok_match:
        return tiktok_match.group(1).strip().lower().lstrip('@')

    youtube_patterns = (
        r'youtube\.com/@([^/?#]+)',
        r'youtube\.com/channel/([^/?#]+)',
        r'youtube\.com/c/([^/?#]+)',
        r'youtube\.com/user/([^/?#]+)',
    )
    for pattern in youtube_patterns:
        youtube_match = re.search(pattern, text, re.IGNORECASE)
        if youtube_match:
            return youtube_match.group(1).strip().lower().lstrip('@')

    return text.lstrip('@')


def extract_profile_name(platform, value):
    text = str(value or '').strip()
    if not text:
        return ''

    if platform == 'instagram':
        match = re.search(r'instagram\.com/([^/?#]+)', text, re.IGNORECASE)
        if match:
            return match.group(1).strip().lstrip('@')
    elif platform == 'tiktok':
        match = re.search(r'tiktok\.com/@([^/?#]+)', text, re.IGNORECASE)
        if match:
            return match.group(1).strip().lstrip('@')
    elif platform == 'youtube':
        patterns = (
            r'youtube\.com/@([^/?#]+)',
            r'youtube\.com/channel/([^/?#]+)',
            r'youtube\.com/c/([^/?#]+)',
            r'youtube\.com/user/([^/?#]+)',
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip().lstrip('@')

    return text.lstrip('@')


def build_profile_url(platform, profile_name):
    text = str(profile_name or '').strip()
    if not text:
        return ''
    if re.match(r'^https?://', text, re.IGNORECASE):
        return text

    identifier = text.lstrip('@')
    if platform == 'instagram':
        return f"https://www.instagram.com/{identifier}"
    if platform == 'tiktok':
        return f"https://www.tiktok.com/@{identifier}"
    if platform == 'youtube':
        lowered = text.lower().lstrip('/')
        if lowered.startswith(('channel/', 'c/', 'user/')):
            return f"https://www.youtube.com/{text.lstrip('/')}"
        if re.match(r'(?i)^uc[\w-]+$', identifier):
            return f"https://www.youtube.com/channel/{identifier}"
        return f"https://www.youtube.com/@{identifier}"
    return text


def build_profile_review_record(
    platform,
    username='',
    profile_url='',
    status='Reject',
    reason='',
    covers=None,
    latest_post_time=None,
    soft_flags=None,
    stats=None,
    upload_metadata=None,
):
    normalized_status = status if status in PROFILE_REVIEW_ALLOWED_STATUSES else 'Reject'
    normalized_covers = []
    if isinstance(covers, list):
        normalized_covers = [str(item).strip() for item in covers if str(item or '').strip()]

    normalized_soft_flags = soft_flags if isinstance(soft_flags, list) else []
    normalized_stats = dict(stats) if isinstance(stats, dict) else {}
    normalized_upload_metadata = dict(upload_metadata) if isinstance(upload_metadata, dict) else {}

    return {
        "platform": str(platform or '').strip(),
        "username": str(username or '').strip(),
        "profile_url": str(profile_url or '').strip(),
        "status": normalized_status,
        "reason": str(reason or '').strip(),
        "covers": normalized_covers,
        "latest_post_time": latest_post_time or None,
        "soft_flags": normalized_soft_flags,
        "stats": normalized_stats,
        "upload_metadata": normalized_upload_metadata,
    }

def parse_iso_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except Exception:
        return None

def sort_items_by_latest(items, time_field):
    fallback = datetime.min.replace(tzinfo=timezone.utc)
    return sorted(
        items,
        key=lambda item: parse_iso_datetime(item.get(time_field)) or fallback,
        reverse=True,
    )

def build_pass_reason(platform, latest_post_time=None, cover_count=0, soft_flag_count=0):
    reasons = ['未命中硬性排雷规则']
    if latest_post_time:
        reasons.append('账号近期有更新')
    if cover_count > 0:
        reasons.append(f'已提取 {cover_count} 张封面供视觉复核')

    if platform == 'tiktok':
        reasons.insert(1, '近期文案与标签未命中竞品/怀孕类关键词')
    elif platform == 'instagram':
        if soft_flag_count > 0:
            reasons.insert(1, f'存在 {soft_flag_count} 项待复核文本提示')
        else:
            reasons.insert(1, '近期简介与帖子未命中硬性外链/文本排雷规则')
    elif platform == 'youtube':
        if soft_flag_count > 0:
            reasons.insert(1, f'存在 {soft_flag_count} 项待复核文本提示')
        else:
            reasons.insert(1, '近期标题、描述与频道信息未命中硬性外链/文本排雷规则')

    return '；'.join(reasons)

def find_keywords(text, keywords):
    if not text:
        return []
    lowered = str(text).lower()
    return [kw for kw in keywords if kw in lowered]

def find_toxic_keywords(text):
    return find_keywords(text, KILL_KEYWORDS)

def is_toxic_text(text):
    return bool(find_toxic_keywords(text))

def clip_text(text, limit=80):
    cleaned = re.sub(r'\s+', ' ', str(text or '')).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit - 1] + '…'


def normalize_text_for_match(text):
    return re.sub(r'\s+', ' ', str(text or '').strip().lower())


def get_upload_metadata_path(platform):
    return os.path.join(DATA_DIR, platform, f"{platform}_upload_metadata.json")


def load_upload_metadata(platform):
    path = get_upload_metadata_path(platform)
    if not os.path.exists(path):
        return {}

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def resolve_upload_metadata(metadata_lookup, *candidates):
    if not isinstance(metadata_lookup, dict) or not metadata_lookup:
        return {}

    for candidate in candidates:
        identifier = normalize_identifier(candidate)
        if identifier and identifier in metadata_lookup:
            metadata = metadata_lookup.get(identifier)
            if isinstance(metadata, dict):
                return metadata
    return {}


def iter_text_values(value):
    if value is None:
        return
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned:
            yield cleaned
        return
    if isinstance(value, (int, float)):
        yield str(value)
        return
    if isinstance(value, dict):
        for nested in value.values():
            yield from iter_text_values(nested)
        return
    if isinstance(value, list):
        for nested in value:
            yield from iter_text_values(nested)


def build_instagram_region_text(profile):
    fields = [
        profile.get('biography'),
        profile.get('addressStreet'),
        profile.get('cityName'),
        profile.get('location'),
        profile.get('businessAddressJson'),
    ]
    parts = []
    for field in fields:
        parts.extend(iter_text_values(field))
    return normalize_text_for_match(' '.join(parts))


def has_instagram_us_region(profile, upload_metadata=None):
    upload_region = normalize_text_for_match((upload_metadata or {}).get('region'))
    if upload_region:
        return upload_region in IG_CUSTOM_UPLOAD_REGION_US

    region_text = build_instagram_region_text(profile)
    if not region_text:
        return False
    if any(keyword in region_text for keyword in IG_CUSTOM_REGION_KEYWORDS_US):
        return True
    return any(pattern.search(region_text) for pattern in IG_CUSTOM_REGION_REGEX_PATTERNS)

def build_toxic_reason(scope, source_label, keyword, text=None):
    parts = [f'{scope}命中禁词 "{keyword}"']
    if source_label:
        parts.append(f'来源：{source_label}')
    if text:
        snippet = clip_text(text)
        if snippet:
            parts.append(f'片段：{snippet}')
    return '；'.join(parts)

def build_keyword_hit(keyword, source_label, text=None):
    return {
        "keyword": keyword,
        "source": source_label,
        "snippet": clip_text(text) if text else ''
    }

def find_first_keyword_hit(sources, keywords):
    for source_label, text in sources:
        matches = find_keywords(text, keywords)
        if matches:
            return build_keyword_hit(matches[0], source_label, text)
    return None

def collect_keyword_hits(sources, keywords, max_hits=3):
    hits = []
    seen = set()
    for source_label, text in sources:
        matches = find_keywords(text, keywords)
        for keyword in matches:
            dedupe_key = (keyword, source_label)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            hits.append(build_keyword_hit(keyword, source_label, text))
            if len(hits) >= max_hits:
                return hits
    return hits

def build_soft_flag_reason(hit):
    parts = [f'命中提示词 "{hit.get("keyword", "")}"']
    if hit.get("source"):
        parts.append(f'来源：{hit["source"]}')
    if hit.get("snippet"):
        parts.append(f'片段：{hit["snippet"]}')
    return '；'.join(parts)

def find_first_toxic_source(sources, scope):
    hit = find_first_keyword_hit(sources, KILL_KEYWORDS)
    if hit:
        return build_toxic_reason(scope, hit.get("source"), hit.get("keyword"), hit.get("snippet"))
    return None


# 备用通用 TikTok 流程读取字段：
# - authorMeta.name / authorMeta.bioLink / authorMeta.signature
# - createTimeISO
# - text / hashtags[].name
# - isSlideshow / slideshowImageLinks[].tiktokLink / videoMeta.originalCoverUrl / videoMeta.coverUrl
def check_tiktok(data):
    """TikTok 第一道防线物理筛查"""
    if not data or len(data) == 0: return {"status": "Reject", "reason": REASON_NO_DATA}

    sorted_items = sort_items_by_latest(data, 'createTimeISO')
    first_item = sorted_items[0]
    author_meta = first_item.get('authorMeta', {})

    # 1. 粉丝量门槛 (根据最新SOP已移除)

    # 2. 活跃度门槛
    create_time_str = first_item.get('createTimeISO')
    if create_time_str:
        try:
            create_time = datetime.fromisoformat(create_time_str.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            if (now - create_time).days > 30:
                return {"status": "Reject", "reason": REASON_INACTIVE, "latest_post_time": create_time_str}
        except: pass

    # 3. 基础外链排雷
    bio_link = str(author_meta.get('bioLink', '')).lower()
    bio_link_keywords = find_toxic_keywords(bio_link)
    if bio_link_keywords:
        return {
            "status": "Reject",
            "reason": build_toxic_reason('主页外链', 'bioLink', bio_link_keywords[0], bio_link),
            "latest_post_time": create_time_str
        }

    # 4. 深度文本排雷 (所有文案 + 标签 + 简介)
    text_sources = [('个人简介', author_meta.get('signature', ''))]
    for idx, item in enumerate(sorted_items[:20], start=1):
        text_sources.append((f'视频文案#{idx}', item.get('text', '')))
        for tag in item.get('hashtags', []):
            text_sources.append((f'视频标签#{idx}', tag.get('name', '')))

    toxic_reason = find_first_toxic_source(text_sources, '文案/标签/简介')
    if toxic_reason:
        return {"status": "Reject", "reason": toxic_reason, "latest_post_time": create_time_str}

    # 5. 提取最近最多 18 条视觉封面的链接
    cover_urls = []
    for item in sorted_items[:VISUAL_REVIEW_COVER_LIMIT]:
        if item.get('isSlideshow'):
            try: cover_urls.append(item['slideshowImageLinks'][0]['tiktokLink'])
            except: pass
        else:
            vm = item.get('videoMeta', {})
            cover_urls.append(vm.get('originalCoverUrl') or vm.get('coverUrl'))

    filtered_covers = [c for c in cover_urls if c]
    return {
        "status": "Pass",
        "covers": filtered_covers,
        "latest_post_time": create_time_str,
        "reason": build_pass_reason('tiktok', create_time_str, len(filtered_covers))
    }

def check_tiktok_tapo(data):
    """TikTok Tapo 智能家居品牌定制审核逻辑"""
    if not data or len(data) == 0:
        return {"status": "Reject", "reason": REASON_NO_DATA}

    # 当前主链路读取字段：
    # - createTimeISO（30 天活跃度）
    # - playCount（最近 50 条，均值 + 中位数）
    # - isSlideshow / slideshowImageLinks[].tiktokLink / videoMeta.originalCoverUrl / videoMeta.coverUrl（封面提取）
    sorted_items = sort_items_by_latest(data, 'createTimeISO')
    first_item = sorted_items[0]
    create_time_str = first_item.get('createTimeISO')

    # 步骤2 — 活跃度：最近一条内容需在 30 天内
    if create_time_str:
        try:
            create_time = datetime.fromisoformat(create_time_str.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            if (now - create_time).days > TAPO_RECENT_ACTIVE_DAYS:
                return {"status": "Reject", "reason": REASON_INACTIVE, "latest_post_time": create_time_str}
        except Exception:
            pass

    # 步骤2 — 播放量门槛：前50条视频的平均值和中位数均需 > 10,000
    top_items = sorted_items[:50]
    play_counts = [item.get('playCount', 0) or 0 for item in top_items]
    avg_views = statistics.mean(play_counts) if play_counts else 0
    median_views = statistics.median(play_counts) if play_counts else 0

    if avg_views <= TAPO_MIN_AVG_VIEWS or median_views <= TAPO_MIN_MEDIAN_VIEWS:
        return {
            "status": "Reject",
            "reason": f"播放量不达标（均值 {avg_views:.0f}，中位数 {median_views:.0f}，门槛 {TAPO_MIN_AVG_VIEWS}）",
            "latest_post_time": create_time_str,
            "stats": {
                "avg_views": round(avg_views, 1),
                "median_views": round(median_views, 1),
                "video_count": len(play_counts),
            },
        }

    # 通过 — 提取最近最多 18 张封面供视觉复核
    cover_urls = []
    for item in sorted_items[:VISUAL_REVIEW_COVER_LIMIT]:
        if item.get('isSlideshow'):
            try:
                cover_urls.append(item['slideshowImageLinks'][0]['tiktokLink'])
            except Exception:
                pass
        else:
            vm = item.get('videoMeta', {})
            cover_urls.append(vm.get('originalCoverUrl') or vm.get('coverUrl'))

    filtered_covers = [c for c in cover_urls if c]
    return {
        "status": "Pass",
        "covers": filtered_covers,
        "latest_post_time": create_time_str,
        "reason": (
            f"近 {TAPO_RECENT_ACTIVE_DAYS} 天有更新；"
            f"播放量达标（均值 {avg_views:.0f}，中位数 {median_views:.0f}）；"
            f"已提取 {len(filtered_covers)} 张封面供视觉复核"
        ),
        "stats": {
            "avg_views": round(avg_views, 1),
            "median_views": round(median_views, 1),
            "video_count": len(play_counts),
        },
    }

def check_instagram(data):
    """Instagram 第一道防线物理筛查"""
    if not data or len(data) == 0: return {"status": "Reject", "reason": REASON_NO_DATA}
    
    # 备用通用 Instagram 流程读取字段：
    # - externalUrls[].url
    # - biography
    # - latestPosts[].timestamp / latestPosts[].caption / latestPosts[].displayUrl
    # Apify IG data is often a list with one dict or just the dict
    profile = data[0] if isinstance(data, list) else data
    
    # 1. 粉丝量门槛 (根据最新SOP已移除)
        
    # 2. 外链排雷 (核武级)
    urls = [ext.get('url', '') for ext in profile.get('externalUrls', [])]
    for idx, url in enumerate(urls, start=1):
        toxic_keywords = find_keywords(url, IG_HARD_REJECT_EXTERNAL_KEYWORDS)
        if toxic_keywords:
            return {
                "status": "Reject",
                "reason": build_toxic_reason('外链', f'externalUrls#{idx}', toxic_keywords[0], url)
            }
        
    posts = profile.get('latestPosts', [])
    if not posts: return {"status": "Reject", "reason": REASON_NO_POSTS}
    sorted_posts = sort_items_by_latest(posts, 'timestamp')
    
    # 3. 活跃度门槛
    timestamp_str = sorted_posts[0].get('timestamp')
    if timestamp_str:
        try:
            post_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            if (now - post_time).days > 30:
                return {"status": "Reject", "reason": REASON_INACTIVE}
        except: pass
        
    # 4. 深度文本排雷
    text_sources = [('个人简介', profile.get('biography', ''))]
    for idx, post in enumerate(sorted_posts[:20], start=1):
        text_sources.append((f'帖子文案#{idx}', post.get('caption', '')))

    hard_reject_hit = find_first_keyword_hit(text_sources, IG_HARD_REJECT_TEXT_KEYWORDS)
    if hard_reject_hit:
        return {
            "status": "Reject",
            "reason": build_toxic_reason('简介/帖子文案', hard_reject_hit.get("source"), hard_reject_hit.get("keyword"), hard_reject_hit.get("snippet"))
        }

    soft_flag_hits = collect_keyword_hits(text_sources, IG_SOFT_FLAG_TEXT_KEYWORDS)
        
    # 5. 提取视觉封面
    cover_urls = [p.get('displayUrl') for p in sorted_posts[:VISUAL_REVIEW_COVER_LIMIT] if p.get('displayUrl')]
    return {
        "status": "Pass",
        "covers": cover_urls,
        "soft_flags": soft_flag_hits,
        "latest_post_time": timestamp_str,
        "reason": build_pass_reason('instagram', timestamp_str, len(cover_urls), len(soft_flag_hits))
    }

def check_instagram_custom(data, upload_metadata=None):
    """Instagram 定制审核逻辑（美国本土 + 30 天活跃；视觉与排除项交给视觉复核）"""
    if not data or len(data) == 0:
        return {"status": "Reject", "reason": REASON_NO_DATA}

    # 当前主链路读取字段：
    # - 上传元数据：url / handle / region
    # - API 主页：username / url / biography / addressStreet / cityName / location / businessAddressJson
    # - API 帖子：latestPosts[].timestamp / latestPosts[].displayUrl
    profile = data[0] if isinstance(data, list) else data

    # 步骤1 — 基础资质：地区要求仅保留美国
    profile_has_us = has_instagram_us_region(profile, upload_metadata=upload_metadata)
    upload_region = normalize_text_for_match((upload_metadata or {}).get('region'))

    if not profile_has_us:
        return {
            "status": "Reject",
            "reason": (
                "上传表 Region 未命中美国"
                if upload_region
                else "简介或资料字段未识别到美国地区线索"
            ),
        }

    posts = profile.get('latestPosts', [])
    if not posts:
        return {"status": "Reject", "reason": REASON_NO_POSTS}
    sorted_posts = sort_items_by_latest(posts, 'timestamp')

    # 活跃度门槛
    timestamp_str = sorted_posts[0].get('timestamp')
    if timestamp_str:
        try:
            post_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            if (now - post_time).days > TAPO_RECENT_ACTIVE_DAYS:
                return {"status": "Reject", "reason": REASON_INACTIVE}
        except Exception:
            pass

    # 提取最近最多 18 张封面供视觉复核（步骤3/4 视觉部分交给视觉模型）
    cover_urls = [p.get('displayUrl') for p in sorted_posts[:VISUAL_REVIEW_COVER_LIMIT] if p.get('displayUrl')]
    return {
        "status": "Pass",
        "covers": cover_urls,
        "latest_post_time": timestamp_str,
        "reason": (
            f"地区符合（美国）；近 {TAPO_RECENT_ACTIVE_DAYS} 天有更新；"
            f"已提取 {len(cover_urls)} 张封面供视觉复核"
        ),
    }

def check_youtube(data):
    """YouTube 第一道防线物理筛查"""
    if not data or len(data) == 0: return {"status": "Reject", "reason": REASON_NO_DATA}

    sorted_items = sort_items_by_latest(data, 'date')
    first_item = sorted_items[0]
    
    # 1. 粉丝量门槛 (根据最新SOP已移除)
        
    # 2. 活跃度门槛
    date_str = first_item.get('date')
    if date_str:
        try:
            post_time = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            if (now - post_time).days > 30:
                return {"status": "Reject", "reason": REASON_INACTIVE}
        except: pass

    # 3. 外链与文本排雷
    about_info = first_item.get('aboutChannelInfo', {})
    text_sources = [('频道简介', about_info.get('channelDescription', ''))]
    
    # 全局外链
    for idx, link in enumerate(about_info.get('channelDescriptionLinks', []), start=1):
        toxic_keywords = find_keywords(link.get('url', ''), YT_HARD_REJECT_EXTERNAL_KEYWORDS)
        if toxic_keywords:
            return {
                "status": "Reject",
                "reason": build_toxic_reason('频道外链', f'channelDescriptionLinks#{idx}', toxic_keywords[0], link.get('url', ''))
            }
            
    # 遍历视频
    paid_count = 0
    for idx, item in enumerate(sorted_items[:20], start=1):
        text_sources.append((f'视频标题#{idx}', item.get('title', '')))
        text_sources.append((f'视频描述#{idx}', item.get('text', '')))
        
        # 视频带货外链
        for link_idx, link in enumerate(item.get('descriptionLinks', []), start=1):
            toxic_keywords = find_keywords(link.get('url', ''), YT_HARD_REJECT_EXTERNAL_KEYWORDS)
            if toxic_keywords:
                return {
                    "status": "Reject",
                    "reason": build_toxic_reason('视频描述外链', f'视频#{idx}-descriptionLinks#{link_idx}', toxic_keywords[0], link.get('url', ''))
                }
                
        if idx <= 10 and item.get('isPaidContent') is True:
            paid_count += 1
            
    # 恰饭浓度阻断 (>80% in last 10)
    if len(sorted_items) >= 10 and paid_count >= 8:
        return {"status": "Reject", "reason": REASON_TOO_MUCH_PAID_CONTENT, "latest_post_time": date_str}

    hard_reject_hit = find_first_keyword_hit(text_sources, YT_HARD_REJECT_TEXT_KEYWORDS)
    if hard_reject_hit:
        return {
            "status": "Reject",
            "reason": build_toxic_reason('标题/描述/频道信息', hard_reject_hit.get("source"), hard_reject_hit.get("keyword"), hard_reject_hit.get("snippet")),
            "latest_post_time": date_str
        }

    soft_flag_hits = collect_keyword_hits(text_sources, YT_SOFT_FLAG_TEXT_KEYWORDS)
        
    # 4. 提取视觉封面
    cover_urls = [vid.get('thumbnailUrl') for vid in sorted_items[:VISUAL_REVIEW_COVER_LIMIT] if vid.get('thumbnailUrl')]
    return {
        "status": "Pass",
        "covers": cover_urls,
        "soft_flags": soft_flag_hits,
        "latest_post_time": date_str,
        "reason": build_pass_reason('youtube', date_str, len(cover_urls), len(soft_flag_hits))
    }

def filter_and_save_dataset(file_path, platform, expected_profiles=None):
    print(f"\\n[{platform.upper()}] 开始初筛：{file_path}")
    try:
        with open(file_path, 'r') as f:
            raw_text = f.read()
            
        start_idx = -1
        for i, char in enumerate(raw_text):
            if char in ['[', '{']:
                start_idx = i
                break
                
        if start_idx == -1:
            return {"success": False, "error": "未找到可解析的 JSON 数据"}
            
        json_payload = raw_text[start_idx:]
        data = json.loads(json_payload)
        
        # Normalize to list
        if not isinstance(data, list):
            data = [data]
            
        filtered_data = []
        rejected_profiles = []
        profile_reviews = []
        returned_profiles = []
        missing_profiles = []
        original_profile_count = 0
        passed_profile_count = 0
        expected_profiles = expected_profiles or []
        expected_profile_keys = {normalize_identifier(item) for item in expected_profiles if normalize_identifier(item)}
        upload_metadata_lookup = load_upload_metadata(platform)
        
        if platform == 'tiktok':
            # 分组与回填阶段还会读取 authorMeta.name / authorMeta.profileUrl，
            # 用于把原始视频数组聚合为“按博主维度”的初筛结果。
            profiles = {}
            for item in data:
                author = item.get('authorMeta', {}).get('name', 'unknown')
                if author not in profiles: profiles[author] = []
                profiles[author].append(item)
            original_profile_count = len(profiles)

            for author, items in profiles.items():
                profile_url = items[0].get('authorMeta', {}).get('profileUrl')
                upload_metadata = resolve_upload_metadata(upload_metadata_lookup, profile_url, author)
                res = check_tiktok_tapo(items)
                profile_url = items[0].get('authorMeta', {}).get('profileUrl')
                latest_post_time = res.get("latest_post_time")
                returned_profiles.append(profile_url or author)
                if res['status'] == 'Pass':
                    items[0]['_vetting'] = res
                    filtered_data.extend(items)
                    passed_profile_count += 1
                    profile_reviews.append(build_profile_review_record(
                        platform,
                        username=author,
                        profile_url=profile_url,
                        status='Pass',
                        reason=res.get("reason"),
                        covers=res.get("covers", []),
                        latest_post_time=latest_post_time,
                        stats=res.get("stats"),
                        upload_metadata=upload_metadata,
                    ))
                else:
                    rejected_profiles.append({"username": author, "profile_url": profile_url, "reason": res['reason']})
                    profile_reviews.append(build_profile_review_record(
                        platform,
                        username=author,
                        profile_url=profile_url,
                        status='Reject',
                        reason=res['reason'],
                        latest_post_time=latest_post_time,
                        stats=res.get("stats"),
                        upload_metadata=upload_metadata,
                    ))

            returned_profile_keys = {normalize_identifier(item) for item in returned_profiles if normalize_identifier(item)}
            missing_profile_keys = expected_profile_keys - returned_profile_keys
            for profile in expected_profiles:
                normalized = normalize_identifier(profile)
                if normalized not in missing_profile_keys:
                    continue
                profile_name = extract_profile_name('tiktok', profile)
                profile_url = build_profile_url('tiktok', profile_name)
                upload_metadata = resolve_upload_metadata(upload_metadata_lookup, profile_url, profile_name, profile)
                missing_item = build_profile_review_record(
                    platform,
                    username=profile_name or str(profile).lstrip('@'),
                    profile_url=profile_url,
                    status='Missing',
                    reason=REASON_MISSING_PROFILE,
                    upload_metadata=upload_metadata,
                )
                missing_profiles.append(missing_item)
                rejected_profiles.append({
                    "username": missing_item["username"],
                    "profile_url": profile_url,
                    "reason": missing_item["reason"]
                })
                profile_reviews.append(missing_item)
                    
        elif platform == 'instagram':
            # Instagram 直接按 profile 对象逐条跑主链路，再把 upload_metadata 融合进 profile_reviews。
            original_profile_count = len(data)
            for profile in data:
                username = profile.get('username', 'unknown')
                profile_url = profile.get('url') or (f"https://www.instagram.com/{username}" if username != 'unknown' else None)
                upload_metadata = resolve_upload_metadata(upload_metadata_lookup, profile_url, username)
                returned_profiles.append(profile_url or username)
                res = check_instagram_custom(profile, upload_metadata=upload_metadata)
                if res['status'] == 'Pass':
                    profile['_vetting'] = res
                    filtered_data.append(profile)
                    passed_profile_count += 1
                    profile_reviews.append(build_profile_review_record(
                        platform,
                        username=username,
                        profile_url=profile_url,
                        status='Pass',
                        reason=res.get("reason"),
                        covers=res.get("covers", []),
                        latest_post_time=res.get("latest_post_time"),
                        soft_flags=res.get("soft_flags", []),
                        upload_metadata=upload_metadata,
                    ))
                else:
                    rejected_profiles.append({"username": username, "profile_url": profile_url, "reason": res['reason']})
                    profile_reviews.append(build_profile_review_record(
                        platform,
                        username=username,
                        profile_url=profile_url,
                        status='Reject',
                        reason=res['reason'],
                        latest_post_time=res.get("latest_post_time"),
                        soft_flags=res.get("soft_flags", []),
                        upload_metadata=upload_metadata,
                    ))

            returned_profile_keys = {normalize_identifier(item) for item in returned_profiles if normalize_identifier(item)}
            missing_profile_keys = expected_profile_keys - returned_profile_keys
            for profile in expected_profiles:
                normalized = normalize_identifier(profile)
                if normalized not in missing_profile_keys:
                    continue
                profile_name = extract_profile_name('instagram', profile)
                profile_url = build_profile_url('instagram', profile_name)
                upload_metadata = resolve_upload_metadata(upload_metadata_lookup, profile_url, profile_name, profile)
                missing_item = build_profile_review_record(
                    platform,
                    username=profile_name or str(profile).lstrip('@'),
                    profile_url=profile_url,
                    status='Missing',
                    reason=REASON_MISSING_PROFILE,
                    upload_metadata=upload_metadata,
                )
                missing_profiles.append(missing_item)
                rejected_profiles.append({
                    "username": missing_item["username"],
                    "profile_url": profile_url,
                    "reason": missing_item["reason"]
                })
                profile_reviews.append(missing_item)
                    
        elif platform == 'youtube':
            profiles = {}
            for item in data:
                channel = item.get('channelName', 'unknown')
                if channel not in profiles: profiles[channel] = []
                profiles[channel].append(item)
            original_profile_count = len(profiles)
                
            for channel, items in profiles.items():
                first_item = items[0] if items else {}
                profile_url = first_item.get('channelUrl') or first_item.get('channelLink')
                if not profile_url:
                    about_info = first_item.get('aboutChannelInfo', {})
                    profile_url = about_info.get('channelUrl')
                upload_metadata = resolve_upload_metadata(upload_metadata_lookup, profile_url, channel)
                res = check_youtube(items)
                returned_profiles.append(profile_url or channel)
                if res['status'] == 'Pass':
                    items[0]['_vetting'] = res
                    filtered_data.extend(items)
                    passed_profile_count += 1
                    profile_reviews.append(build_profile_review_record(
                        platform,
                        username=channel,
                        profile_url=profile_url,
                        status='Pass',
                        reason=res.get("reason"),
                        covers=res.get("covers", []),
                        latest_post_time=res.get("latest_post_time"),
                        soft_flags=res.get("soft_flags", []),
                        upload_metadata=upload_metadata,
                    ))
                else:
                    rejected_profiles.append({"username": channel, "profile_url": profile_url, "reason": res['reason']})
                    profile_reviews.append(build_profile_review_record(
                        platform,
                        username=channel,
                        profile_url=profile_url,
                        status='Reject',
                        reason=res['reason'],
                        latest_post_time=res.get("latest_post_time"),
                        soft_flags=res.get("soft_flags", []),
                        upload_metadata=upload_metadata,
                    ))

            returned_profile_keys = {normalize_identifier(item) for item in returned_profiles if normalize_identifier(item)}
            missing_profile_keys = expected_profile_keys - returned_profile_keys
            for profile in expected_profiles:
                normalized = normalize_identifier(profile)
                if normalized not in missing_profile_keys:
                    continue
                profile_name = extract_profile_name('youtube', profile)
                profile_url = build_profile_url('youtube', profile_name or profile)
                upload_metadata = resolve_upload_metadata(upload_metadata_lookup, profile_url, profile_name, profile)
                missing_item = build_profile_review_record(
                    platform,
                    username=profile_name or str(profile).lstrip('@'),
                    profile_url=profile_url,
                    status='Missing',
                    reason=REASON_MISSING_PROFILE,
                    upload_metadata=upload_metadata,
                )
                missing_profiles.append(missing_item)
                rejected_profiles.append({
                    "username": missing_item["username"],
                    "profile_url": profile_url,
                    "reason": missing_item["reason"]
                })
                profile_reviews.append(missing_item)
        else:
            return {"success": False, "error": "未知平台"}
            
        with open(file_path, 'w') as f:
            json.dump(filtered_data, f, indent=2)

        profile_reviews_path = save_profile_reviews(platform, profile_reviews)
            
        print(f"[{platform.upper()}] 初筛完成：通过 {len(filtered_data)} 条，筛掉 {len(rejected_profiles)} 个账号。")
        return {
            "success": True,
            "original_items": len(data),
            "filtered_items": len(filtered_data),
            "original_profiles": original_profile_count,
            "passed_profiles": passed_profile_count,
            "returned_profiles": returned_profiles,
            "missing_profiles": missing_profiles,
            "rejected_profiles_count": len(rejected_profiles),
            "rejected_profiles": rejected_profiles,
            "profile_reviews": profile_reviews,
            "profile_reviews_path": profile_reviews_path,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    test_files = [
        ("tiktok", os.path.join(base_dir, "data/tiktok/tiktok_data.json")),
        ("instagram", os.path.join(base_dir, "data/instagram/instagram_data.json")),
        ("youtube", os.path.join(base_dir, "data/youtube/youtube_data.json"))
    ]
    for platform, path in test_files:
        if os.path.exists(path):
            result = filter_and_save_dataset(path, platform)
            print(result)
