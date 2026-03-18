from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import base64
import copy
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import hashlib
from io import BytesIO
import json
import math
import os
import re
import subprocess
import tempfile
import threading
import time
from datetime import datetime
import shlex
from urllib.parse import urlparse
import uuid

from openai import OpenAI
from PIL import Image, ImageOps, UnidentifiedImageError
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from werkzeug.utils import secure_filename


def load_local_env_file():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_file = os.path.join(repo_root, ".env.local")
    if not os.path.exists(env_file):
        return

    try:
        with open(env_file, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue

                key, raw_value = line.split("=", 1)
                key = key.strip()
                if not key or key in os.environ:
                    continue

                value = raw_value.strip()
                if value:
                    try:
                        parsed = shlex.split(value, comments=False, posix=True)
                        value = parsed[0] if len(parsed) == 1 else " ".join(parsed)
                    except ValueError:
                        value = value.strip("\"'")

                os.environ[key] = value
    except OSError:
        return


load_local_env_file()


def parse_allowed_origins(raw_value):
    if not raw_value:
        return ["http://127.0.0.1:5173", "http://localhost:5173"]

    origins = []
    for item in str(raw_value).split(","):
        origin = item.strip().rstrip("/")
        if not origin or origin == "*":
            continue
        origins.append(origin)

    return origins or ["http://127.0.0.1:5173", "http://localhost:5173"]


app = Flask(__name__)
BACKEND_ALLOWED_ORIGINS = parse_allowed_origins(os.getenv("BACKEND_ALLOWED_ORIGINS"))
BACKEND_BIND_HOST = str(os.getenv("BACKEND_BIND_HOST", "127.0.0.1") or "127.0.0.1").strip() or "127.0.0.1"
try:
    BACKEND_PORT = int(str(os.getenv("BACKEND_PORT", "5001") or "5001").strip())
except ValueError:
    BACKEND_PORT = 5001

# Restrict CORS to explicit local origins by default.
CORS(app, resources={r"/api/*": {"origins": BACKEND_ALLOWED_ORIGINS}})

OPENAI_MODEL = os.getenv("VISION_MODEL", "gpt-5.4")
OPENAI_API_KEY_PLACEHOLDER = "YOUR_API_KEY_HERE"
VISION_REQUEST_TIMEOUT = 30
VISION_API_STYLE_RESPONSES = "responses"
VISION_API_STYLE_CHAT_COMPLETIONS = "chat_completions"
MIN_VISUAL_REVIEW_COVER_COUNT = int(os.getenv("MIN_VISUAL_REVIEW_COVER_COUNT", "3"))
MAX_VISUAL_REVIEW_CANDIDATE_COVERS = int(os.getenv("MAX_VISUAL_REVIEW_CANDIDATE_COVERS", "50"))
MAX_COLLAGE_COVER_COUNT = 9
VISUAL_REVIEW_MODE_SIMPLE = "simple"
VISUAL_REVIEW_MODE_AUTO = "auto"
VISUAL_REVIEW_MODE_ENHANCED = "enhanced"
VISUAL_REVIEW_LIVE_CONTRACT_VERSION = "visual_review_live_v1"
VISUAL_REVIEW_MODES = {
    VISUAL_REVIEW_MODE_SIMPLE,
    VISUAL_REVIEW_MODE_AUTO,
    VISUAL_REVIEW_MODE_ENHANCED,
}
AUTO_ENHANCED_MIN_AVAILABLE_COVERS = int(os.getenv("AUTO_ENHANCED_MIN_AVAILABLE_COVERS", "14"))
AUTO_ENHANCED_MIN_SUCCESS_COVERS = int(os.getenv("AUTO_ENHANCED_MIN_SUCCESS_COVERS", "14"))
try:
    MAX_VISUAL_REVIEW_COLLAGE_COUNT = max(1, int(os.getenv("MAX_VISUAL_REVIEW_COLLAGE_COUNT", "2")))
except ValueError:
    MAX_VISUAL_REVIEW_COLLAGE_COUNT = 2
MAX_TOTAL_VISUAL_REVIEW_COVERS = MAX_COLLAGE_COVER_COUNT * MAX_VISUAL_REVIEW_COLLAGE_COUNT
VISION_IMAGE_CONNECT_TIMEOUT = float(os.getenv("VISION_IMAGE_CONNECT_TIMEOUT", "8"))
VISION_IMAGE_READ_TIMEOUT = float(os.getenv("VISION_IMAGE_READ_TIMEOUT", str(max(10, VISION_REQUEST_TIMEOUT))))
VISION_IMAGE_DOWNLOAD_RETRIES = int(os.getenv("VISION_IMAGE_DOWNLOAD_RETRIES", "3"))
VISION_IMAGE_RETRY_BACKOFF = float(os.getenv("VISION_IMAGE_RETRY_BACKOFF", "0.6"))
VISION_IMAGE_DOWNLOAD_MAX_WORKERS = int(os.getenv("VISION_IMAGE_DOWNLOAD_MAX_WORKERS", "2"))
VISION_IMAGE_RETRY_STATUS_CODES = (403, 429, 500, 502, 503, 504)
TIKTOK_DOWNLOAD_COVERS_BY_DEFAULT = os.getenv("TIKTOK_DOWNLOAD_COVERS_BY_DEFAULT", "1") != "0"
VISION_PROVIDERS = [
    {
        "name": "quan2go",
        "base_url": os.getenv("VISION_QUAN2GO_BASE_URL", "https://capi.quan2go.com/openai"),
        "api_key": os.getenv("VISION_QUAN2GO_API_KEY", ""),
        "stream_only": os.getenv("VISION_QUAN2GO_STREAM_ONLY", "1") != "0",
        "api_style": VISION_API_STYLE_RESPONSES,
    },
    {
        "name": "lemonapi",
        "base_url": os.getenv("VISION_LEMONAPI_BASE_URL", "https://new.lemonapi.site/v1"),
        "api_key": os.getenv("VISION_LEMONAPI_API_KEY", ""),
        "stream_only": False,
        "api_style": VISION_API_STYLE_CHAT_COMPLETIONS,
        "model": os.getenv("VISION_LEMONAPI_MODEL", "[L]gemini-3.1-pro-preview").strip(),
    },
    {
        "name": "auto-code",
        "base_url": os.getenv("VISION_AUTO_CODE_BASE_URL", "https://gpt.auto-code.net/rust/openai/v1"),
        "api_key": None,
        "stream_only": False,
        "api_style": VISION_API_STYLE_RESPONSES,
    },
]
COLLAGE_TILE_SIZE = 256
COLLAGE_GAP = 8
APIFY_API_BASE = "https://api.apify.com/v2"
APIFY_REQUEST_TIMEOUT = 60
APIFY_POLL_INTERVAL_SECONDS = 5
APIFY_HTTP_RETRY_ATTEMPTS = int(os.getenv("APIFY_HTTP_RETRY_ATTEMPTS", "3"))
APIFY_HTTP_RETRY_BACKOFF_SECONDS = float(os.getenv("APIFY_HTTP_RETRY_BACKOFF_SECONDS", "2"))
APIFY_TRANSIENT_STATUS_CODES = (429, 500, 502, 503, 504)
APIFY_MIN_WAIT_SECONDS = 180
APIFY_MAX_WAIT_SECONDS = 900
APIFY_COMMAND_TIMEOUT_SECONDS = 900
APIFY_BUDGET_RESERVATION_TTL_SECONDS = int(os.getenv("APIFY_BUDGET_RESERVATION_TTL_SECONDS", "21600"))
APIFY_RUN_GUARD_TTL_SECONDS = int(os.getenv("APIFY_RUN_GUARD_TTL_SECONDS", "1800"))
APIFY_AUTH_FILE = os.path.expanduser("~/.apify/auth.json")
APIFY_TOKEN_STATE_FILE = os.path.expanduser("~/.apify/token_manager_state.json")
APIFY_SOFT_CREDIT_LIMIT_USD = float(os.getenv("APIFY_SOFT_CREDIT_LIMIT_USD", "4.0"))
APIFY_BUDGET_SAFETY_MULTIPLIER = float(os.getenv("APIFY_BUDGET_SAFETY_MULTIPLIER", "1.1"))
APIFY_BUDGET_BUFFER_USD = float(os.getenv("APIFY_BUDGET_BUFFER_USD", "0.1"))
APIFY_MAX_BATCH_ATTEMPTS = int(os.getenv("APIFY_MAX_BATCH_ATTEMPTS", "3"))
APIFY_ESTIMATED_COST_PER_IDENTIFIER_USD = {
    "tiktok": float(os.getenv("APIFY_TIKTOK_COST_PER_PROFILE_USD", "0.04")),
    "instagram": float(os.getenv("APIFY_INSTAGRAM_COST_PER_PROFILE_USD", "0.08")),
    "youtube": float(os.getenv("APIFY_YOUTUBE_COST_PER_PROFILE_USD", "0.50")),
}
APIFY_ESTIMATED_COST_PER_RESULT_USD = {
    "tiktok": float(os.getenv("APIFY_TIKTOK_COST_PER_RESULT_USD", "0.004")),
    "instagram": float(os.getenv("APIFY_INSTAGRAM_COST_PER_RESULT_USD", "0.0027")),
    "youtube": float(os.getenv("APIFY_YOUTUBE_COST_PER_RESULT_USD", "0.004")),
}
APIFY_MAX_IDENTIFIERS_PER_BATCH = {
    "tiktok": int(os.getenv("TIKTOK_BATCH_SIZE", "20")),
    "instagram": int(os.getenv("INSTAGRAM_BATCH_SIZE", "50")),
    "youtube": int(os.getenv("YOUTUBE_BATCH_SIZE", "5")),
}
ALLOWED_APIFY_ACTORS = {
    "clockworks/tiktok-profile-scraper",
    "apify/instagram-profile-scraper",
    "streamers/youtube-scraper",
}
VISION_PROMPT = """你是 Ulike 达人初筛流程中的视觉复核员。输入图片是一位博主最近最多 18 张封面，按时间顺序拆成最多 2 张 3x3 九宫格。请综合全部输入图片一起判断。

只根据图片画面做初步判断，不要假设看不到的内容。重点排查：
1. 是否出现 Temu、Shein、AliExpress、Wish、TikTok Shop 等低价/竞品合作痕迹。
2. 是否明显过度性感或暴露，如大量内衣、比基尼、刻意卖弄身材。
3. 是否存在大面积明显纹身。
4. 画面环境是否长期杂乱、昏暗、模糊、缺乏生活质感。
5. 是否高度母婴/晒娃导向，封面主体大多是婴儿、儿童或孕期内容。
6. 是否整体过度商业化、假感很重，几乎全是广告式摆拍。

如果明显命中以上任一高风险情况，输出 Reject；否则输出 Pass。

如果同时命中多项，不要只写一项：
- `reason` 写一句主结论。
- `signals` 尽量列出所有已识别到的命中项，最多 3 个，宁可短一点，也不要漏掉明显命中项。
- `signals` 只写风险点，不要重复空话。

请只返回 JSON，不要加 markdown，不要加额外说明，格式固定为：
{"decision":"Pass 或 Reject","reason":"一句中文原因","signals":["最多 3 个简短中文信号"]}"""

VISION_PROMPT_TAPO = """你是 Tapo 智能家居品牌达人初筛流程中的视觉复核员。输入图片是一位博主最近最多 18 张封面，按时间顺序拆成最多 2 张 3x3 九宫格。请综合全部输入图片一起判断。

只根据图片画面做初步判断，不要假设看不到的内容。

步骤3 — 内容 / 视觉审核：检查是否命中以下至少 1 类特征：
- Speaking-led：镜头前开口说话，有明显表达感
- 真实生活场景：真实家庭 / 生活环境，非绿幕、非强剧本感
- 孩子互动：有孩子在家庭或生活场景中的互动
- 产品展示：手持、摆放或明确展示产品
- 户外庭院：庭院、花园、露台等户外家居场景
- 宠物互动：有宠物出现在生活场景中并形成互动

如果以上 6 类特征均未命中，输出 Reject，reason 写"未命中 Speaking-led/真实生活场景/孩子互动/产品展示/户外庭院/宠物互动"。

步骤4 — 排除项审核：
1. 若明显出现绿幕、抠图感虚拟背景或大面积纯色虚拟背景，输出 Reject，reason 写"出现绿幕背景"。
2. 若多人跳舞 / 舞蹈表演内容占比 > 30%，输出 Reject，reason 写"多人跳舞内容占比过高"。
3. 若自拍或情侣两人出镜内容占比 > 70%，输出 Reject，reason 写"自拍/情侣出镜占比过高"。

不要根据年龄、种族、民族等受保护属性做判断。
不要把鲜明人设 / 垂直 niche 当作自动通过或自动拒绝条件；这属于人工判断项。

如果通过以上检查，输出 Pass。

如果同时命中多项风险，不要只写一项：
- `reason` 写一句主结论。
- `signals` 尽量列出所有已识别到的命中项，最多 3 个，宁可短一点，也不要漏掉明显命中项。
- `signals` 只写风险点，不要重复空话。

请只返回 JSON，不要加 markdown，不要加额外说明，格式固定为：
{"decision":"Pass 或 Reject","reason":"一句中文原因","signals":["最多 3 个简短中文信号"]}"""
VISION_PROMPT_INSTAGRAM_CUSTOM = VISION_PROMPT_TAPO

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

APIFY_RUN_GUARD_STATE_FILE = os.path.join(DATA_DIR, "apify_run_guard_state.json")
VISION_PROVIDER_STATE_FILE = os.path.join(DATA_DIR, "vision_provider_state.json")

UPLOAD_FOLDER = os.path.join(DATA_DIR, 'uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

JOBS = {}
JOBS_LOCK = threading.Lock()
APIFY_TOKEN_STATE_LOCK = threading.RLock()
APIFY_RUN_GUARD_LOCK = threading.RLock()
VISUAL_PREVIEW_CACHE = {}
VISUAL_PREVIEW_CACHE_LOCK = threading.Lock()
MAX_VISUAL_PREVIEW_CACHE_ITEMS = 256
TIKTOK_COVER_CACHE_WARMERS = {}
TIKTOK_COVER_CACHE_WARMERS_LOCK = threading.Lock()
TIKTOK_DATA_CACHE = {"mtime": None, "grouped_items": {}}
TIKTOK_DATA_CACHE_LOCK = threading.Lock()
UPLOAD_METADATA_CONTENT_COLUMN_CANDIDATES = (
    "content",
    "url",
    "profile_url",
    "profile_link",
    "link",
)
UPLOAD_METADATA_FIELD_ALIASES = {
    "nickname": "nickname",
    "name": "nickname",
    "display_name": "nickname",
    "description": "description",
    "bio": "description",
    "username": "handle",
    "handle": "handle",
    "region": "region",
    "language": "language",
    "platform": "platform",
    "followers": "followers",
    "avg_views": "avg_views",
    "avg_likes": "avg_likes",
    "avg_comments": "avg_comments",
    "avg_collects": "avg_collects",
    "tags": "tags",
    "email": "email",
    "email_send_status": "email_send_status",
    "yt_email_button": "yt_email_button",
    "last_post": "last_post",
    "posts_7d": "posts_7d",
    "posts_30d": "posts_30d",
}
UPLOAD_METADATA_EXPORT_FIELDS = (
    ("upload_nickname", "nickname"),
    ("upload_handle", "handle"),
    ("upload_region", "region"),
    ("upload_language", "language"),
    ("upload_email", "email"),
    ("upload_followers", "followers"),
    ("upload_avg_views", "avg_views"),
    ("upload_avg_likes", "avg_likes"),
    ("upload_avg_comments", "avg_comments"),
    ("upload_avg_collects", "avg_collects"),
    ("upload_tags", "tags"),
    ("upload_last_post", "last_post"),
    ("upload_posts_7d", "posts_7d"),
    ("upload_posts_30d", "posts_30d"),
    ("upload_description", "description"),
    ("upload_source_filename", "source_filename"),
)
CANONICAL_UPLOAD_REQUIRED_FIELDS = (
    {
        "field": "platform",
        "label": "Platform",
        "accepted_columns": ("platform",),
    },
    {
        "field": "handle",
        "label": "@username",
        "accepted_columns": ("username", "handle"),
    },
)
UPLOAD_PLATFORM_RESPONSE_LABELS = {
    "tiktok": "TikTok",
    "instagram": "Instagram",
    "youtube": "YouTube",
}
UPLOAD_PLATFORM_ALIASES = {
    "tiktok": "tiktok",
    "tik_tok": "tiktok",
    "instagram": "instagram",
    "ig": "instagram",
    "youtube": "youtube",
    "yt": "youtube",
}
JOB_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
JOB_ACTIVE_STATUSES = {"queued", "running", "cancelling"}
JOB_CANCELLATION_REQUESTED_STATUSES = {"cancelling", "cancelled"}
SCRAPE_JOB_CONTRACT_VERSION = "scrape_job_v1"
SCRAPE_STAGE_ALIASES = {
    "queued": "queued",
    "starting": "starting",
    "preparing": "preparing",
    "batch_preparing": "batch_preparing",
    "scraping": "provider_start",
    "apify_start": "provider_start",
    "apify_running": "provider_running",
    "recovering_remote_run": "recovering_remote_run",
    "waiting_remote_run": "waiting_remote_run",
    "downloading": "downloading",
    "filtering": "filtering",
    "batch_completed": "batch_completed",
    "batch_failed": "batch_failed",
    "completed": "completed",
    "failed": "failed",
    "cancelling": "cancelling",
    "cancelled": "cancelled",
}
SCRAPE_STAGE_PROGRESS_MAP = {
    "queued": {"done": 0, "total": 100, "percent": 0},
    "starting": {"done": 2, "total": 100, "percent": 2},
    "preparing": {"done": 5, "total": 100, "percent": 5},
    "batch_preparing": {"done": 8, "total": 100, "percent": 8},
    "provider_start": {"done": 18, "total": 100, "percent": 18},
    "provider_running": {"done": 45, "total": 100, "percent": 45},
    "recovering_remote_run": {"done": 55, "total": 100, "percent": 55},
    "waiting_remote_run": {"done": 60, "total": 100, "percent": 60},
    "downloading": {"done": 72, "total": 100, "percent": 72},
    "filtering": {"done": 90, "total": 100, "percent": 90},
    "batch_completed": {"done": 94, "total": 100, "percent": 94},
    "batch_failed": {"done": 94, "total": 100, "percent": 94},
    "completed": {"done": 100, "total": 100, "percent": 100},
    "failed": {"done": 100, "total": 100, "percent": 100},
    "cancelling": {"done": 95, "total": 100, "percent": 95},
    "cancelled": {"done": 100, "total": 100, "percent": 100},
}
SCRAPE_BATCH_STAGE_FRACTIONS = {
    "batch_preparing": 0.08,
    "provider_start": 0.18,
    "provider_running": 0.45,
    "recovering_remote_run": 0.55,
    "waiting_remote_run": 0.6,
    "downloading": 0.72,
    "filtering": 0.9,
    "batch_completed": 1,
    "batch_failed": 1,
    "cancelling": 1,
}


def build_image_download_session():
    session = requests.Session()
    retry = Retry(
        total=VISION_IMAGE_DOWNLOAD_RETRIES,
        connect=VISION_IMAGE_DOWNLOAD_RETRIES,
        read=VISION_IMAGE_DOWNLOAD_RETRIES,
        status=VISION_IMAGE_DOWNLOAD_RETRIES,
        backoff_factor=VISION_IMAGE_RETRY_BACKOFF,
        allowed_methods=frozenset({"GET"}),
        status_forcelist=VISION_IMAGE_RETRY_STATUS_CODES,
        raise_on_status=False,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=16, pool_maxsize=32)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "image",
        "Sec-Fetch-Mode": "no-cors",
        "Sec-Fetch-Site": "cross-site",
    })
    return session


IMAGE_DOWNLOAD_SESSION_LOCAL = threading.local()


def get_image_download_session():
    session = getattr(IMAGE_DOWNLOAD_SESSION_LOCAL, "session", None)
    if session is None:
        session = build_image_download_session()
        IMAGE_DOWNLOAD_SESSION_LOCAL.session = session
    return session


def iso_now():
    return datetime.utcnow().isoformat() + "Z"


def is_job_cancellation_requested(status):
    return str(status or "").strip().lower() in JOB_CANCELLATION_REQUESTED_STATUSES


def normalize_job_stage(job_type, stage):
    normalized_stage = str(stage or "").strip().lower()
    if not normalized_stage:
        return "queued"
    if job_type == "scrape":
        return SCRAPE_STAGE_ALIASES.get(normalized_stage, normalized_stage)
    return normalized_stage


def build_default_job_progress():
    return {
        "done": 0,
        "total": None,
        "percent": 0,
        "determinate": False,
    }


def build_job_progress(job_type, status, stage, done=None, total=None, current_progress=None, extra=None):
    current_progress = current_progress or {}
    extra = extra or {}

    raw_done = done if isinstance(done, (int, float)) else current_progress.get("done", 0)
    raw_total = total if isinstance(total, (int, float)) else current_progress.get("total")

    if job_type == "scrape":
        batch_total = extra.get("batch_total")
        batch_index = extra.get("batch_index")
        if isinstance(batch_total, int) and batch_total > 0:
            resolved_total = batch_total
            inferred_done = (
                batch_total
                if status == "completed"
                else batch_index
                if stage in {"batch_completed", "batch_failed"} and isinstance(batch_index, int)
                else max(0, (batch_index or 0) - 1)
            )
            stage_fraction = SCRAPE_BATCH_STAGE_FRACTIONS.get(stage, 0)
            percent = int(round(min(
                100,
                max(
                    ((max(0, inferred_done) + stage_fraction) / resolved_total) * 100,
                    (float(raw_done) / resolved_total) * 100 if isinstance(raw_done, (int, float)) else 0,
                ),
            )))
            resolved_done = min(resolved_total, max(int(raw_done or 0), int(inferred_done)))
            return {
                "done": resolved_done,
                "total": resolved_total,
                "percent": percent,
                "determinate": True,
            }

        stage_progress = SCRAPE_STAGE_PROGRESS_MAP.get(stage) or SCRAPE_STAGE_PROGRESS_MAP.get(status)
        if status in JOB_TERMINAL_STATUSES or stage in {"cancelling", "cancelled", "failed", "completed"}:
            if stage_progress:
                return {
                    "done": int(stage_progress["done"]),
                    "total": int(stage_progress["total"]),
                    "percent": int(stage_progress["percent"]),
                    "determinate": True,
                }

        if isinstance(raw_total, (int, float)) and raw_total > 0:
            resolved_done = max(0, min(int(raw_done or 0), int(raw_total)))
            percent = int(round(min(100, max(0, (resolved_done / raw_total) * 100))))
            return {
                "done": resolved_done,
                "total": int(raw_total),
                "percent": percent,
                "determinate": True,
            }

        if stage_progress:
            return {
                "done": int(stage_progress["done"]),
                "total": int(stage_progress["total"]),
                "percent": int(stage_progress["percent"]),
                "determinate": True,
            }

    if isinstance(raw_total, (int, float)) and raw_total > 0:
        resolved_done = max(0, min(int(raw_done or 0), int(raw_total)))
        percent = int(round(min(100, max(0, (resolved_done / raw_total) * 100))))
        return {
            "done": resolved_done,
            "total": int(raw_total),
            "percent": percent,
            "determinate": True,
        }

    current_percent = current_progress.get("percent")
    return {
        "done": int(raw_done or 0),
        "total": raw_total if isinstance(raw_total, (int, float)) else None,
        "percent": int(current_percent or 0),
        "determinate": False,
    }


def apply_job_contract(job, fields):
    normalized_fields = dict(fields or {})
    job_type = str((normalized_fields.get("type") or job.get("type") or "")).strip().lower()
    status = str((normalized_fields.get("status") or job.get("status") or "")).strip().lower() or "queued"
    stage = normalize_job_stage(job_type, normalized_fields.get("stage") or job.get("stage"))

    normalized_fields["status"] = status
    normalized_fields["stage"] = stage

    progress = normalized_fields.pop("progress", None)
    current_progress = job.get("progress") or build_default_job_progress()
    progress_done = None
    progress_total = None
    if isinstance(progress, dict):
        progress_done = progress.get("done")
        progress_total = progress.get("total")
    normalized_fields["progress"] = build_job_progress(
        job_type,
        status,
        stage,
        done=progress_done,
        total=progress_total,
        current_progress=current_progress,
        extra=normalized_fields,
    )

    if job_type == "scrape":
        normalized_fields["contract_version"] = SCRAPE_JOB_CONTRACT_VERSION

        partial_result = normalized_fields.get("partial_result")
        if isinstance(partial_result, dict):
            normalized_fields["failed_batches"] = partial_result.get("failed_batches", normalized_fields.get("failed_batches", []))
            if partial_result.get("completed_batches") is not None or partial_result.get("total_batches") is not None:
                normalized_fields["batch_summary"] = {
                    "completed": partial_result.get("completed_batches"),
                    "total": partial_result.get("total_batches"),
                    "failed": len(partial_result.get("failed_batches") or []),
                }

        result = normalized_fields.get("result")
        if isinstance(result, dict):
            if "failed_batches" in result:
                normalized_fields["failed_batches"] = result.get("failed_batches") or []
            if "batch_summary" in result and isinstance(result.get("batch_summary"), dict):
                normalized_fields["batch_summary"] = result.get("batch_summary")

    if status == "cancelling" and not (job.get("cancel_requested_at") or normalized_fields.get("cancel_requested_at")):
        normalized_fields["cancel_requested_at"] = iso_now()

    if status in JOB_TERMINAL_STATUSES and not normalized_fields.get("finished_at"):
        normalized_fields["finished_at"] = iso_now()

    return normalized_fields


def load_template_generator_module():
    import sys

    scripts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
    if scripts_dir not in sys.path:
        sys.path.append(scripts_dir)

    import generate_screening_templates

    return generate_screening_templates


def load_rulespec_compiler_module():
    import sys

    scripts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
    if scripts_dir not in sys.path:
        sys.path.append(scripts_dir)

    import compile_screening_rulespec

    return compile_screening_rulespec


def build_template_generation_output_dir():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return os.path.join(repo_root, "temp", "generated_templates", f"api-{timestamp}-{uuid.uuid4().hex[:8]}")


def build_rulespec_compile_output_dir():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return os.path.join(repo_root, "temp", "compiled_rulespec", f"api-{timestamp}-{uuid.uuid4().hex[:8]}")


def normalize_job_payload_for_signature(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if value.is_integer():
            return int(value)
        return round(value, 6)
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return [normalize_job_payload_for_signature(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): normalize_job_payload_for_signature(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    return str(value)


def build_job_payload_signature(job_type, platform=None, payload=None):
    canonical_payload = {
        "type": str(job_type or "").strip().lower(),
        "platform": str(platform or "").strip().lower(),
        "payload": normalize_job_payload_for_signature(payload or {}),
    }
    raw = json.dumps(canonical_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def find_active_job(job_type=None, platform=None, payload_signature=None):
    target_type = str(job_type or "").strip().lower()
    target_platform = str(platform or "").strip().lower()
    target_signature = str(payload_signature or "").strip()

    with JOBS_LOCK:
        for job in JOBS.values():
            status = str(job.get("status") or "").strip().lower()
            if status not in JOB_ACTIVE_STATUSES:
                continue
            if target_type and str(job.get("type") or "").strip().lower() != target_type:
                continue
            if target_platform and str(job.get("platform") or "").strip().lower() != target_platform:
                continue
            if target_signature and str(job.get("payload_signature") or "").strip() != target_signature:
                continue
            return dict(job)
    return None


def create_job(job_type, platform=None, message="任务已创建", payload_signature=None):
    job_id = str(uuid.uuid4())
    job = {
        "id": job_id,
        "type": job_type,
        "platform": platform,
        "payload_signature": str(payload_signature or "").strip() or None,
        "status": "queued",
        "stage": "queued",
        "message": message,
        "progress": build_default_job_progress(),
        "result": None,
        "partial_result": None,
        "error": None,
        "failed_batches": [],
        "batch_summary": None,
        "contract_version": SCRAPE_JOB_CONTRACT_VERSION if job_type == "scrape" else None,
        "cancel_requested_at": None,
        "finished_at": None,
        "created_at": iso_now(),
        "updated_at": iso_now(),
    }
    job = apply_job_contract({}, job)
    with JOBS_LOCK:
        JOBS[job_id] = job
    return job


def update_job(job_id, **fields):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return None
        normalized_fields = apply_job_contract(job, fields)
        job.update(normalized_fields)
        job["updated_at"] = iso_now()
        return dict(job)


def get_job(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        return dict(job) if job else None


def is_job_cancelled(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        return bool(job and is_job_cancellation_requested(job.get("status")))


def build_cancelled_result(message="用户取消"):
    return {
        "success": False,
        "cancelled": True,
        "error": message,
        "message": message,
    }


def build_job_progress_callback(job_id):
    def callback(stage, message=None, done=None, total=None, **extra):
        current_job = get_job(job_id)
        if not current_job:
            return None
        if is_job_cancellation_requested(current_job.get("status")):
            return current_job
        payload = {
            "status": "running",
            "stage": stage,
            "message": message or stage,
        }
        if done is not None or total is not None:
            payload["progress"] = {
                "done": done if done is not None else current_job.get("progress", {}).get("done", 0),
                "total": total if total is not None else current_job.get("progress", {}).get("total"),
            }
        if extra:
            payload.update(extra)
        update_job(job_id, **payload)
    return callback


def get_openai_api_key():
    return os.getenv("OPENAI_API_KEY", "").strip()


def normalize_vision_provider_name(provider_name):
    return str(provider_name or "").strip().lower()


def get_runtime_config_error(error_code, error, details):
    return (
        jsonify({
            "success": False,
            "error_code": error_code,
            "error": error,
            "details": details,
        }),
        400,
    )


def get_apify_auth_file_token():
    try:
        with open(APIFY_AUTH_FILE, 'r') as f:
            token = json.load(f).get('token')
            if isinstance(token, str) and token.strip():
                return token.strip()
    except Exception:
        pass
    return None


def validate_apify_runtime_config():
    if get_apify_token():
        return None

    return get_runtime_config_error(
        "MISSING_APIFY_CONFIG",
        "缺少 Apify 配置：请设置 APIFY_TOKEN / APIFY_API_TOKEN，或在 ~/.apify/auth.json 中提供 token。",
        [
            "环境变量：APIFY_TOKEN 或 APIFY_API_TOKEN",
            "本地认证文件：~/.apify/auth.json（包含 token 字段）",
        ],
    )


def get_vision_provider_env_key(provider_name):
    normalized = normalize_vision_provider_name(provider_name)
    if normalized == "quan2go":
        return os.getenv("VISION_QUAN2GO_API_KEY", "").strip()
    if normalized == "lemonapi":
        return os.getenv("VISION_LEMONAPI_API_KEY", "").strip()
    if normalized == "auto-code":
        return get_openai_api_key()
    return ""


def get_configured_vision_provider_names():
    available = []
    for provider in VISION_PROVIDERS:
        provider_name = normalize_vision_provider_name(provider.get("name"))
        if provider_name and get_vision_provider_env_key(provider_name):
            available.append(provider_name)
    return available


def load_vision_provider_state():
    try:
        if not os.path.exists(VISION_PROVIDER_STATE_FILE):
            return {"providers": {}}
        with open(VISION_PROVIDER_STATE_FILE, 'r') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"providers": {}}
        if not isinstance(data.get("providers"), dict):
            data["providers"] = {}
        return data
    except Exception:
        return {"providers": {}}


def save_vision_provider_state(state):
    try:
        os.makedirs(os.path.dirname(VISION_PROVIDER_STATE_FILE), exist_ok=True)
        with open(VISION_PROVIDER_STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def get_current_vision_provider_name():
    available = get_configured_vision_provider_names()
    if not available:
        return ""

    state = load_vision_provider_state()
    current_provider = normalize_vision_provider_name(state.get("current_provider"))
    if current_provider in available:
        return current_provider
    return available[0]


def set_current_vision_provider(provider_name, result=None, error=None):
    normalized = normalize_vision_provider_name(provider_name)
    if not normalized:
        return False

    state = load_vision_provider_state()
    providers = state.setdefault("providers", {})
    provider_state = providers.get(normalized, {})
    timestamp = iso_now()

    if result == "success":
        provider_state["success_count"] = int(provider_state.get("success_count") or 0) + 1
        provider_state["last_success_at"] = timestamp
        provider_state.pop("last_error", None)
    elif result == "failed":
        provider_state["failure_count"] = int(provider_state.get("failure_count") or 0) + 1
        provider_state["last_failure_at"] = timestamp
        provider_state["last_error"] = str(error or "").strip()

    provider_state["last_result"] = result or provider_state.get("last_result") or ""
    provider_state["last_used_at"] = timestamp
    providers[normalized] = provider_state
    state["current_provider"] = normalized
    state["updated_at"] = timestamp
    return save_vision_provider_state(state)


def rotate_vision_provider(tried_providers=None):
    current_provider = get_current_vision_provider_name()
    pool = get_configured_vision_provider_names()
    tried_providers = {normalize_vision_provider_name(item) for item in (tried_providers or [])}

    if current_provider in pool:
        current_index = pool.index(current_provider)
        ordered_pool = pool[current_index + 1:] + pool[:current_index]
    else:
        ordered_pool = pool

    for candidate in ordered_pool:
        if not candidate or candidate == current_provider or candidate in tried_providers:
            continue
        if set_current_vision_provider(candidate, result="rotated_in"):
            print(f"[Vision Review] Provider rotated: {current_provider or 'none'} -> {candidate}")
            return candidate
    return None


def get_available_vision_provider_names():
    available = get_configured_vision_provider_names()
    current_provider = get_current_vision_provider_name()
    if current_provider in available:
        current_index = available.index(current_provider)
        return available[current_index:] + available[:current_index]
    return available


def get_available_vision_providers():
    provider_map = {}
    for provider in VISION_PROVIDERS:
        provider_name = normalize_vision_provider_name(provider.get("name"))
        if provider_name:
            provider_map[provider_name] = provider
    return [
        provider_map[provider_name]
        for provider_name in get_available_vision_provider_names()
        if provider_name in provider_map
    ]


def validate_vision_runtime_config():
    available = get_available_vision_provider_names()
    if available:
        return None

    return get_runtime_config_error(
        "MISSING_VISION_CONFIG",
        "缺少视觉模型配置：请设置 VISION_QUAN2GO_API_KEY 或 OPENAI_API_KEY。视觉模型只支持环境变量配置。",
        [
            "quan2go：设置 VISION_QUAN2GO_API_KEY",
            "lemonapi：设置 VISION_LEMONAPI_API_KEY",
            "auto-code：设置 OPENAI_API_KEY",
            "视觉模型路径不再从源码测试脚本或硬编码默认值回退",
        ],
    )


def normalize_visual_review_mode(value):
    normalized = str(value or "").strip().lower()
    if normalized in VISUAL_REVIEW_MODES:
        return normalized
    return VISUAL_REVIEW_MODE_AUTO


def recommend_visual_review_mode_for_cover_count(cover_count):
    if int(cover_count or 0) >= AUTO_ENHANCED_MIN_AVAILABLE_COVERS:
        return VISUAL_REVIEW_MODE_ENHANCED
    return VISUAL_REVIEW_MODE_SIMPLE


def determine_visual_review_target_collage_count(review_mode, requested_cover_total):
    normalized_mode = normalize_visual_review_mode(review_mode)
    requested_cover_total = max(0, int(requested_cover_total or 0))
    if requested_cover_total <= 0:
        return 1

    if normalized_mode == VISUAL_REVIEW_MODE_SIMPLE:
        return 1
    if (
        normalized_mode == VISUAL_REVIEW_MODE_AUTO
        and requested_cover_total < AUTO_ENHANCED_MIN_AVAILABLE_COVERS
    ):
        return 1

    return min(
        MAX_VISUAL_REVIEW_COLLAGE_COUNT,
        max(1, math.ceil(min(requested_cover_total, MAX_TOTAL_VISUAL_REVIEW_COVERS) / MAX_COLLAGE_COVER_COUNT)),
    )


def select_visual_review_bundle_assets(bundle_assets, review_mode):
    requested_mode = normalize_visual_review_mode(review_mode)
    collages = list(bundle_assets.get("collages") or [])
    if not collages:
        raise ValueError("No collage images available for visual review")

    total_loaded_cover_count = int(bundle_assets.get("cover_count") or 0)
    total_requested_cover_count = int(bundle_assets.get("requested_cover_count") or 0)
    selected_collages = list(collages)
    downgrade_reason = ""

    if requested_mode == VISUAL_REVIEW_MODE_SIMPLE:
        selected_collages = collages[:1]
    elif (
        requested_mode == VISUAL_REVIEW_MODE_AUTO
        and total_loaded_cover_count < AUTO_ENHANCED_MIN_SUCCESS_COVERS
    ):
        selected_collages = collages[:1]
        if len(collages) > 1:
            downgrade_reason = (
                f"自动模式检测到实际可用封面仅 {total_loaded_cover_count}/{total_requested_cover_count} 张，"
                f"未达到双九宫格门槛 {AUTO_ENHANCED_MIN_SUCCESS_COVERS} 张，已自动降级为单九宫格。"
            )

    applied_mode = VISUAL_REVIEW_MODE_ENHANCED if len(selected_collages) > 1 else VISUAL_REVIEW_MODE_SIMPLE
    selected_cover_count = sum(int(item.get("cover_count") or 0) for item in selected_collages)
    selected_requested_cover_count = sum(int(item.get("requested_cover_count") or 0) for item in selected_collages)
    selected_download_failures = []
    for item in selected_collages:
        selected_download_failures.extend(item.get("download_failures") or [])

    return {
        "collage_count": len(collages),
        "collages": collages,
        "reviewed_collage_count": len(selected_collages),
        "reviewed_collages": selected_collages,
        "unused_collage_count": max(0, len(collages) - len(selected_collages)),
        "cover_count": selected_cover_count,
        "requested_cover_count": selected_requested_cover_count,
        "download_failure_count": len(selected_download_failures),
        "download_failure_hosts": sorted({
            item.get("host") for item in selected_download_failures if str(item.get("host") or "").strip()
        }),
        "download_failures": selected_download_failures,
        "image_data_urls": [item["image_data_url"] for item in selected_collages],
        "preview_bytes_list": [item["preview_bytes"] for item in selected_collages],
        "reviewed_image_data_urls": [item["image_data_url"] for item in selected_collages],
        "reviewed_preview_bytes_list": [item["preview_bytes"] for item in selected_collages],
        "available_image_data_urls": [item["image_data_url"] for item in collages],
        "available_preview_bytes_list": [item["preview_bytes"] for item in collages],
        "image_data_url": selected_collages[0]["image_data_url"],
        "preview_bytes": selected_collages[0]["preview_bytes"],
        "requested_mode": requested_mode,
        "applied_mode": applied_mode,
        "downgrade_reason": downgrade_reason,
        "total_loaded_cover_count": total_loaded_cover_count,
        "total_requested_cover_count": total_requested_cover_count,
        "total_collage_count": len(collages),
    }


def extract_text_from_sse(raw_text):
    final_text = ""
    delta_parts = []

    for block in raw_text.split("\n\n"):
        lines = [line for line in block.splitlines() if line.strip()]
        event_name = None
        data_payload = None

        for line in lines:
            if line.startswith("event: "):
                event_name = line[len("event: "):]
            elif line.startswith("data: "):
                data_payload = line[len("data: "):]

        if not data_payload:
            continue

        try:
            payload = json.loads(data_payload)
        except json.JSONDecodeError:
            continue

        if event_name == "response.output_text.done":
            text = payload.get("text")
            if isinstance(text, str) and text.strip():
                final_text = text
        elif event_name == "response.output_text.delta":
            delta = payload.get("delta")
            if isinstance(delta, str):
                delta_parts.append(delta)

    if final_text:
        return final_text
    if delta_parts:
        return "".join(delta_parts)
    return raw_text.strip()


def extract_response_text(response):
    if isinstance(response, str):
        return extract_text_from_sse(response)

    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output = getattr(response, "output", None)
    if isinstance(output, list):
        text_parts = []
        for item in output:
            content_items = getattr(item, "content", None)
            if not isinstance(content_items, list):
                continue
            for content in content_items:
                text = getattr(content, "text", None)
                if isinstance(text, str):
                    text_parts.append(text)
        if text_parts:
            return "\n".join(text_parts)

    if hasattr(response, "model_dump"):
        return json.dumps(response.model_dump(), ensure_ascii=False, indent=2)

    return str(response)


def normalize_vision_api_style(raw_value):
    normalized = str(raw_value or "").strip().lower()
    if normalized == VISION_API_STYLE_CHAT_COMPLETIONS:
        return VISION_API_STYLE_CHAT_COMPLETIONS
    return VISION_API_STYLE_RESPONSES


def resolve_vision_provider_model(provider):
    provider_model = str((provider or {}).get("model") or "").strip()
    if provider_model:
        return provider_model
    return OPENAI_MODEL


def convert_input_messages_to_chat_messages(input_messages):
    chat_messages = []

    for message in input_messages or []:
        role = str((message or {}).get("role") or "user").strip() or "user"
        content = (message or {}).get("content")

        if isinstance(content, str):
            chat_messages.append({"role": role, "content": content})
            continue

        converted_content = []
        for item in content or []:
            item_type = str((item or {}).get("type") or "").strip().lower()
            if item_type == "input_text":
                text = str((item or {}).get("text") or "").strip()
                if text:
                    converted_content.append({"type": "text", "text": text})
            elif item_type == "input_image":
                image_url = str((item or {}).get("image_url") or "").strip()
                if image_url:
                    converted_content.append({"type": "image_url", "image_url": {"url": image_url}})

        if converted_content:
            chat_messages.append({"role": role, "content": converted_content})

    return chat_messages


def extract_chat_completion_text(response):
    if isinstance(response, str):
        return response.strip()

    choices = getattr(response, "choices", None)
    if choices is None and isinstance(response, dict):
        choices = response.get("choices")

    if isinstance(choices, list):
        text_parts = []
        for choice in choices:
            message = getattr(choice, "message", None)
            if message is None and isinstance(choice, dict):
                message = choice.get("message")
            if message is None:
                continue

            content = getattr(message, "content", None)
            if content is None and isinstance(message, dict):
                content = message.get("content")

            if isinstance(content, str) and content.strip():
                text_parts.append(content)
                continue

            if isinstance(content, list):
                for item in content:
                    text = getattr(item, "text", None)
                    if text is None and isinstance(item, dict):
                        text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        text_parts.append(text)

        if text_parts:
            return "\n".join(text_parts)

    if hasattr(response, "model_dump"):
        return json.dumps(response.model_dump(), ensure_ascii=False, indent=2)

    if isinstance(response, dict):
        return json.dumps(response, ensure_ascii=False, indent=2)

    return str(response)


def call_vision_chat_completion(client, model, input_messages):
    response = client.chat.completions.create(
        model=model,
        messages=convert_input_messages_to_chat_messages(input_messages),
    )
    return extract_chat_completion_text(response)


def call_vision_stream(client, model, input_messages):
    final_text = ""
    delta_parts = []
    stream = client.responses.create(
        model=model,
        input=input_messages,
        stream=True,
    )

    for event in stream:
        event_type = getattr(event, "type", "")
        if event_type == "response.output_text.done":
            text = getattr(event, "text", None)
            if isinstance(text, str) and text.strip():
                final_text = text
        elif event_type == "response.output_text.delta":
            delta = getattr(event, "delta", None)
            if isinstance(delta, str):
                delta_parts.append(delta)

    if final_text:
        return final_text
    if delta_parts:
        return "".join(delta_parts)
    raise ValueError("Streaming response did not contain output text")


def resolve_vision_provider_api_key(provider):
    provider_name = str((provider or {}).get("name") or "").strip()
    provider_key = get_vision_provider_env_key(provider_name)
    if provider_key:
        return provider_key
    return get_openai_api_key()


def strip_code_fences(text):
    stripped = (text or "").strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9_]*\n?", "", stripped)
        stripped = re.sub(r"\n?```$", "", stripped)
    return stripped.strip()


def parse_visual_review_result(raw_text):
    cleaned = strip_code_fences(raw_text)
    payload = None

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        start_idx = cleaned.find("{")
        end_idx = cleaned.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            snippet = cleaned[start_idx:end_idx + 1]
            try:
                payload = json.loads(snippet)
            except json.JSONDecodeError:
                payload = None

    if isinstance(payload, dict):
        decision = str(payload.get("decision") or "").strip().title()
        if decision not in {"Pass", "Reject"}:
            decision = "Reject" if "reject" in cleaned.lower() else "Pass"
        reason = str(payload.get("reason") or cleaned).strip()
        signals = payload.get("signals")
        if not isinstance(signals, list):
            signals = []
        return {
            "decision": decision,
            "reason": reason or cleaned,
            "signals": [str(item).strip() for item in signals if str(item).strip()][:3],
        }

    lowered = cleaned.lower()
    inferred_decision = "Reject" if "reject" in lowered else "Pass"
    return {
        "decision": inferred_decision,
        "reason": cleaned or "模型未返回可解析内容",
        "signals": [],
    }


class CoverDownloadError(RuntimeError):
    def __init__(self, url, exc):
        self.url = str(url or "").strip()
        self.host = urlparse(self.url).netloc or "unknown-host"
        self.error_type = classify_cover_download_error(exc)
        self.original_exception = exc
        super().__init__(f"{self.host}: {exc}")


def classify_cover_download_error(exc):
    if isinstance(exc, requests.exceptions.SSLError):
        return "ssl"
    if isinstance(exc, requests.exceptions.Timeout):
        return "timeout"
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "connection"
    if isinstance(exc, requests.exceptions.HTTPError):
        return "http"
    if isinstance(exc, (UnidentifiedImageError, OSError)):
        return "decode"
    return exc.__class__.__name__.lower()


def build_cover_download_failure(url, exc):
    if isinstance(exc, CoverDownloadError):
        return {
            "url": exc.url,
            "host": exc.host,
            "error_type": exc.error_type,
            "error": str(exc.original_exception or exc).strip() or exc.__class__.__name__,
        }

    host = urlparse(str(url or "").strip()).netloc or "unknown-host"
    return {
        "url": str(url or "").strip(),
        "host": host,
        "error_type": classify_cover_download_error(exc),
        "error": str(exc).strip() or exc.__class__.__name__,
    }


def download_image_bytes(url):
    try:
        response = get_image_download_session().get(
            url,
            timeout=(VISION_IMAGE_CONNECT_TIMEOUT, VISION_IMAGE_READ_TIMEOUT),
            allow_redirects=True,
        )
        response.raise_for_status()
        return response.content
    except requests.exceptions.RequestException as exc:
        raise CoverDownloadError(url, exc) from exc


def load_remote_image(url):
    image_bytes = download_image_bytes(url)
    with Image.open(BytesIO(image_bytes)) as image:
        return image.convert("RGB")


def load_image_source(source):
    source_text = str(source or "").strip()
    if not source_text:
        raise ValueError("Empty image source")

    if source_text.startswith("file://"):
        source_text = source_text[len("file://"):]

    if os.path.isfile(source_text):
        with Image.open(source_text) as image:
            return image.convert("RGB")

    return load_remote_image(source_text)


def persist_image_source_to_jpeg(source, output_path):
    image = load_image_source(source)
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        image.save(output_path, format="JPEG", quality=88)
        return output_path
    finally:
        image.close()


def hydrate_tiktok_cover_paths(scraped_items, profile_reviews):
    if not isinstance(scraped_items, list) or not isinstance(profile_reviews, list):
        return profile_reviews

    grouped_items = {}
    for item in scraped_items:
        if not isinstance(item, dict):
            continue
        author_meta = item.get("authorMeta") or {}
        author = normalize_tiktok_profile_key(author_meta.get("name") or author_meta.get("profileUrl"))
        if not author:
            continue
        grouped_items.setdefault(author, []).append(item)

    cache_root = get_tiktok_cover_cache_dir()

    for review in profile_reviews:
        if not isinstance(review, dict) or review.get("status") != "Pass":
            continue

        username = str(review.get("username") or "").strip()
        existing_paths = [
            str(path).strip()
            for path in (review.get("cover_paths") or [])
            if str(path).strip() and os.path.isfile(str(path).strip())
        ]
        requested_cover_count = max(
            len(review.get("cover_paths") or []),
            len(review.get("covers") or []),
            len(review.get("cover_urls") or []),
        )
        target_cached_cover_count = min(
            MAX_TOTAL_VISUAL_REVIEW_COVERS,
            requested_cover_count if requested_cover_count > 0 else MAX_TOTAL_VISUAL_REVIEW_COVERS,
        )

        if len(existing_paths) >= target_cached_cover_count:
            review["cover_paths"] = existing_paths[:target_cached_cover_count]
            review["cached_cover_count"] = len(review["cover_paths"])
            continue

        author_key = normalize_tiktok_profile_key(username or review.get("profile_url"))
        if not author_key:
            review["cover_paths"] = []
            continue

        author_items = grouped_items.get(author_key) or []
        if not author_items:
            review["cover_paths"] = []
            continue

        sorted_items = sorted(
            author_items,
            key=lambda item: str(item.get("createTimeISO") or ""),
            reverse=True,
        )[:target_cached_cover_count]

        user_dir = os.path.join(cache_root, secure_filename(username or author_key) or author_key)
        os.makedirs(user_dir, exist_ok=True)
        for filename in os.listdir(user_dir):
            if filename.startswith("cover_") and filename.endswith(".jpg"):
                try:
                    os.remove(os.path.join(user_dir, filename))
                except OSError:
                    pass

        local_paths = []
        for index, item in enumerate(sorted_items, start=1):
            output_path = os.path.join(user_dir, f"cover_{index:02d}.jpg")
            last_error = None
            for candidate in get_tiktok_item_cover_candidates(item):
                try:
                    persist_image_source_to_jpeg(candidate, output_path)
                    local_paths.append(output_path)
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    continue

            if last_error is not None:
                print(f"[Cover Cache] failed to persist cover {index} for {username}: {last_error}")

        review["cover_paths"] = local_paths
        review["cached_cover_count"] = len(local_paths)

    return profile_reviews


def has_missing_tiktok_cover_cache(profile_reviews):
    for review in profile_reviews or []:
        if not isinstance(review, dict) or review.get("status") != "Pass":
            continue

        existing_paths = [
            str(path).strip()
            for path in (review.get("cover_paths") or [])
            if str(path).strip() and os.path.isfile(str(path).strip())
        ]
        requested_cover_count = max(
            len(review.get("cover_paths") or []),
            len(review.get("covers") or []),
            len(review.get("cover_urls") or []),
        )
        target_cached_cover_count = min(
            MAX_TOTAL_VISUAL_REVIEW_COVERS,
            requested_cover_count if requested_cover_count > 0 else MAX_TOTAL_VISUAL_REVIEW_COVERS,
        )
        if len(existing_paths) < target_cached_cover_count:
            return True

    return False


def schedule_tiktok_cover_cache_warm(platform, scraped_items, profile_reviews):
    if platform != "tiktok":
        return
    if not isinstance(scraped_items, list) or not isinstance(profile_reviews, list) or not profile_reviews:
        return
    if not has_missing_tiktok_cover_cache(profile_reviews):
        return

    with TIKTOK_COVER_CACHE_WARMERS_LOCK:
        current_thread = TIKTOK_COVER_CACHE_WARMERS.get(platform)
        if current_thread and current_thread.is_alive():
            return

        def worker():
            try:
                items_snapshot = copy.deepcopy(scraped_items)
                reviews_snapshot = copy.deepcopy(profile_reviews)
                print(f"[Cover Cache] background warm-up started for {len(reviews_snapshot)} TikTok reviews")
                hydrated_reviews = hydrate_tiktok_cover_paths(items_snapshot, reviews_snapshot)
                save_profile_reviews(
                    platform,
                    hydrated_reviews,
                    metadata=load_profile_review_artifact_metadata(platform),
                )
                cached_profiles = sum(
                    1
                    for review in hydrated_reviews
                    if isinstance(review, dict) and (review.get("cached_cover_count") or 0) > 0
                )
                print(
                    f"[Cover Cache] background warm-up finished for {cached_profiles}/{len(hydrated_reviews)} TikTok reviews"
                )
            except Exception as exc:
                print(f"[Cover Cache] background warm-up failed: {exc}")
            finally:
                with TIKTOK_COVER_CACHE_WARMERS_LOCK:
                    active_thread = TIKTOK_COVER_CACHE_WARMERS.get(platform)
                    if active_thread is threading.current_thread():
                        TIKTOK_COVER_CACHE_WARMERS.pop(platform, None)

        warm_thread = threading.Thread(
            target=worker,
            daemon=True,
            name=f"{platform}-cover-cache-warmer",
        )
        TIKTOK_COVER_CACHE_WARMERS[platform] = warm_thread
        print(f"[Cover Cache] queued background warm-up for {len(profile_reviews)} TikTok reviews")
        warm_thread.start()


def build_cover_collage(cover_urls, min_required_cover_count=1, progress_callback=None):
    valid_urls = [str(url).strip() for url in cover_urls if str(url).strip()]
    if not valid_urls:
        raise ValueError("No cover URLs provided")

    loaded_images = {}
    download_failures = []
    requested_cover_count = len(valid_urls)
    target_cover_count = min(MAX_COLLAGE_COVER_COUNT, requested_cover_count)
    max_workers = max(1, min(VISION_IMAGE_DOWNLOAD_MAX_WORKERS, requested_cover_count))

    if progress_callback:
        progress_callback({
            "type": "start",
            "requested_cover_count": requested_cover_count,
            "loaded_cover_count": 0,
            "failed_cover_count": 0,
            "current_cover_index": 0,
            "current_cover_total": requested_cover_count,
            "min_required_cover_count": min_required_cover_count,
            "target_cover_count": target_cover_count,
            "max_workers": max_workers,
        })

    if progress_callback:
        progress_callback({
            "type": "loading",
            "requested_cover_count": requested_cover_count,
            "loaded_cover_count": 0,
            "failed_cover_count": 0,
            "current_cover_index": 0,
            "current_cover_total": requested_cover_count,
            "min_required_cover_count": min_required_cover_count,
            "target_cover_count": target_cover_count,
            "max_workers": max_workers,
        })

    completed_cover_count = 0
    stopped_early = False
    early_stop_reason = None
    impossible_notified = False
    future_to_meta = {}
    next_cover_index = 1
    reached_target_cover_count = False
    executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="cover-download")

    def submit_next_cover_tasks():
        nonlocal next_cover_index
        while len(future_to_meta) < max_workers and next_cover_index <= requested_cover_count:
            url = valid_urls[next_cover_index - 1]
            future = executor.submit(load_image_source, url)
            future_to_meta[future] = (next_cover_index, url)
            next_cover_index += 1

    try:
        submit_next_cover_tasks()

        while future_to_meta:
            completed_futures, _ = wait(tuple(future_to_meta.keys()), return_when=FIRST_COMPLETED)
            for future in completed_futures:
                order_index, url = future_to_meta.pop(future)
                completed_cover_count += 1
                try:
                    image = future.result()
                    if len(loaded_images) < target_cover_count:
                        loaded_images[order_index] = image
                    else:
                        image.close()
                    if progress_callback:
                        progress_callback({
                            "type": "success",
                            "url": url,
                            "cover_order_index": order_index,
                            "requested_cover_count": requested_cover_count,
                            "loaded_cover_count": len(loaded_images),
                            "failed_cover_count": len(download_failures),
                            "current_cover_index": completed_cover_count,
                            "current_cover_total": requested_cover_count,
                            "min_required_cover_count": min_required_cover_count,
                            "target_cover_count": target_cover_count,
                            "max_workers": max_workers,
                        })
                except Exception as exc:
                    failure = build_cover_download_failure(url, exc)
                    failure["cover_order_index"] = order_index
                    download_failures.append(failure)
                    if progress_callback:
                        progress_callback({
                            "type": "failure",
                            "url": url,
                            "cover_order_index": order_index,
                            "failure": failure,
                            "requested_cover_count": requested_cover_count,
                            "loaded_cover_count": len(loaded_images),
                            "failed_cover_count": len(download_failures),
                            "current_cover_index": completed_cover_count,
                            "current_cover_total": requested_cover_count,
                            "min_required_cover_count": min_required_cover_count,
                            "target_cover_count": target_cover_count,
                            "max_workers": max_workers,
                        })

                remaining_possible_cover_count = len(loaded_images) + len(future_to_meta) + (requested_cover_count - next_cover_index + 1)
                if (
                    not impossible_notified
                    and remaining_possible_cover_count < min_required_cover_count
                ):
                    stopped_early = True
                    early_stop_reason = (
                        f"当前最多只可能凑到 {remaining_possible_cover_count} 张可用封面，"
                        f"已不足 {min_required_cover_count} 张，后续将直接记为封面不足。"
                    )
                    impossible_notified = True
                    if progress_callback:
                        progress_callback({
                            "type": "impossible",
                            "reason": early_stop_reason,
                            "requested_cover_count": requested_cover_count,
                            "loaded_cover_count": len(loaded_images),
                            "failed_cover_count": len(download_failures),
                            "current_cover_index": completed_cover_count,
                            "current_cover_total": requested_cover_count,
                            "min_required_cover_count": min_required_cover_count,
                            "target_cover_count": target_cover_count,
                            "max_workers": max_workers,
                        })

                if len(loaded_images) >= target_cover_count:
                    reached_target_cover_count = True
                    break

            if reached_target_cover_count:
                break

            submit_next_cover_tasks()
    finally:
        executor.shutdown(wait=not reached_target_cover_count, cancel_futures=reached_target_cover_count)

    if not loaded_images:
        failure_hosts = sorted({
            item.get("host") for item in download_failures if str(item.get("host") or "").strip()
        })
        host_text = "、".join(failure_hosts[:3]) if failure_hosts else "unknown host"
        raise ValueError(f"无法加载任何封面图（共 {len(valid_urls)} 张，失败来源：{host_text}）")

    canvas_size = COLLAGE_TILE_SIZE * 3 + COLLAGE_GAP * 4
    collage = Image.new("RGB", (canvas_size, canvas_size), (245, 245, 245))

    for idx, image in enumerate([loaded_images[key] for key in sorted(loaded_images)], start=0):
        tile = ImageOps.fit(
            image,
            (COLLAGE_TILE_SIZE, COLLAGE_TILE_SIZE),
            method=Image.Resampling.LANCZOS,
        )
        row = idx // 3
        col = idx % 3
        x = COLLAGE_GAP + col * (COLLAGE_TILE_SIZE + COLLAGE_GAP)
        y = COLLAGE_GAP + row * (COLLAGE_TILE_SIZE + COLLAGE_GAP)
        collage.paste(tile, (x, y))

    if len(loaded_images) < min_required_cover_count:
        if not stopped_early:
            stopped_early = True
            early_stop_reason = (
                f"可用封面不足 {min_required_cover_count} 张，当前仅成功 {len(loaded_images)}/{requested_cover_count} 张。"
            )

    return collage, len(loaded_images), requested_cover_count, download_failures, stopped_early, early_stop_reason


def serialize_collage_jpeg(collage, quality=88, max_size=None):
    image = collage.copy()
    if max_size:
        image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def collage_to_data_url(collage, quality=88, max_size=None):
    encoded = base64.b64encode(
        serialize_collage_jpeg(collage, quality=quality, max_size=max_size)
    ).decode("utf-8")
    return f"data:image/jpeg;base64,{encoded}"


def build_cover_collage_assets(cover_urls, min_required_cover_count=1, progress_callback=None):
    collage, cover_count, requested_cover_count, download_failures, stopped_early, early_stop_reason = build_cover_collage(
        cover_urls,
        min_required_cover_count=min_required_cover_count,
        progress_callback=progress_callback,
    )
    return {
        "cover_count": cover_count,
        "requested_cover_count": requested_cover_count,
        "download_failure_count": len(download_failures),
        "download_failure_hosts": sorted({
            item.get("host") for item in download_failures if str(item.get("host") or "").strip()
        }),
        "download_failures": download_failures,
        "stopped_early": stopped_early,
        "early_stop_reason": early_stop_reason,
        "min_required_cover_count": min_required_cover_count,
        "image_data_url": collage_to_data_url(collage, quality=88),
        "preview_bytes": serialize_collage_jpeg(collage, quality=72, max_size=420),
    }


def build_cover_collage_bundle_assets(
    cover_urls,
    min_required_cover_count=1,
    max_collage_count=MAX_VISUAL_REVIEW_COLLAGE_COUNT,
    progress_callback=None,
):
    collage_cover_groups = split_cover_urls_for_visual_review(
        cover_urls,
        max_collage_count=max_collage_count,
    )
    if not collage_cover_groups:
        raise ValueError("No cover URLs provided")

    total_requested_cover_count = sum(len(group) for group in collage_cover_groups)
    total_cover_count = 0
    total_download_failures = []
    stopped_early = False
    early_stop_reasons = []
    collage_errors = []
    collage_assets_list = []
    collage_total = len(collage_cover_groups)

    for collage_index, group_urls in enumerate(collage_cover_groups, start=1):
        def handle_group_progress(event):
            if not progress_callback:
                return

            event_payload = dict(event or {})
            event_payload["collage_index"] = collage_index
            event_payload["collage_total"] = collage_total
            event_payload["aggregate_requested_cover_count"] = total_requested_cover_count
            event_payload["aggregate_loaded_cover_count"] = total_cover_count + int(event_payload.get("loaded_cover_count") or 0)
            event_payload["aggregate_failed_cover_count"] = len(total_download_failures) + int(event_payload.get("failed_cover_count") or 0)
            progress_callback(event_payload)

        try:
            collage_assets = build_cover_collage_assets(
                group_urls,
                min_required_cover_count=1,
                progress_callback=handle_group_progress,
            )
        except Exception as exc:
            collage_errors.append({
                "collage_index": collage_index,
                "requested_cover_count": len(group_urls),
                "error": str(exc),
            })
            if progress_callback:
                progress_callback({
                    "type": "collage_error",
                    "collage_index": collage_index,
                    "collage_total": collage_total,
                    "requested_cover_count": len(group_urls),
                    "aggregate_requested_cover_count": total_requested_cover_count,
                    "aggregate_loaded_cover_count": total_cover_count,
                    "aggregate_failed_cover_count": len(total_download_failures),
                    "error": str(exc),
                })
            continue

        total_cover_count += collage_assets["cover_count"]
        total_download_failures.extend(collage_assets.get("download_failures") or [])

        if collage_assets.get("stopped_early"):
            stopped_early = True
        if collage_assets.get("early_stop_reason"):
            early_stop_reasons.append(str(collage_assets["early_stop_reason"]).strip())

        collage_assets["collage_index"] = collage_index
        collage_assets["collage_total"] = collage_total
        collage_assets_list.append(collage_assets)

    if not collage_assets_list:
        first_error = collage_errors[0]["error"] if collage_errors else "无法加载任何封面图"
        raise ValueError(first_error)

    if total_cover_count < min_required_cover_count and not early_stop_reasons:
        early_stop_reasons.append(
            f"可用封面不足 {min_required_cover_count} 张，当前仅成功 {total_cover_count}/{total_requested_cover_count} 张。"
        )

    return {
        "collage_count": len(collage_assets_list),
        "collages": collage_assets_list,
        "collage_errors": collage_errors,
        "cover_count": total_cover_count,
        "requested_cover_count": total_requested_cover_count,
        "download_failure_count": len(total_download_failures),
        "download_failure_hosts": sorted({
            item.get("host") for item in total_download_failures if str(item.get("host") or "").strip()
        }),
        "download_failures": total_download_failures,
        "stopped_early": stopped_early,
        "early_stop_reason": " ".join(reason for reason in early_stop_reasons if reason),
        "min_required_cover_count": min_required_cover_count,
        "image_data_urls": [item["image_data_url"] for item in collage_assets_list],
        "preview_bytes_list": [item["preview_bytes"] for item in collage_assets_list],
        "image_data_url": collage_assets_list[0]["image_data_url"],
        "preview_bytes": collage_assets_list[0]["preview_bytes"],
    }


def cache_visual_review_preview(job_id, username, preview_bytes):
    safe_username = secure_filename(username) or "profile"
    preview_id = f"{job_id}-{safe_username}-{uuid.uuid4().hex[:10]}"

    with VISUAL_PREVIEW_CACHE_LOCK:
        VISUAL_PREVIEW_CACHE[preview_id] = {
            "bytes": preview_bytes,
            "created_at": time.time(),
        }
        overflow = len(VISUAL_PREVIEW_CACHE) - MAX_VISUAL_PREVIEW_CACHE_ITEMS
        if overflow > 0:
            oldest_ids = sorted(
                VISUAL_PREVIEW_CACHE.items(),
                key=lambda item: item[1]["created_at"],
            )[:overflow]
            for stale_preview_id, _ in oldest_ids:
                VISUAL_PREVIEW_CACHE.pop(stale_preview_id, None)

    return f"/api/visual-review-preview/{preview_id}"


def append_visual_review_log(log_lines, text, tone="info", max_items=24):
    if not text:
        return log_lines or []

    entries = [
        item
        for item in (log_lines or [])
        if isinstance(item, dict) and str(item.get("text") or "").strip()
    ]
    entries.append({
        "id": uuid.uuid4().hex[:12],
        "text": str(text).strip(),
        "tone": tone,
    })
    return entries[-max_items:]


def build_visual_review_live_snapshot(base=None, **overrides):
    snapshot = {
        "contract_version": VISUAL_REVIEW_LIVE_CONTRACT_VERSION,
        "current_username": "",
        "provider": "",
        "current_collage_url": None,
        "current_collage_urls": [],
        "reviewed_collage_urls": [],
        "collage_count": 0,
        "reviewed_collage_count": 0,
        "unused_collage_count": 0,
        "target_collage_count": 0,
        "requested_mode": VISUAL_REVIEW_MODE_AUTO,
        "recommended_mode": VISUAL_REVIEW_MODE_SIMPLE,
        "applied_mode": VISUAL_REVIEW_MODE_SIMPLE,
        "downgrade_reason": "",
        "cover_count": 0,
        "requested_cover_count": 0,
        "target_cover_count": 0,
        "failed_cover_count": 0,
        "current_cover_index": 0,
        "current_cover_total": 0,
        "min_required_cover_count": MIN_VISUAL_REVIEW_COVER_COUNT,
        "collage_error_count": 0,
        "step": "preparing",
        "decision": "",
        "reason": "",
        "signals": [],
        "log_lines": [],
        "updated_at": iso_now(),
    }
    if isinstance(base, dict):
        snapshot.update(base)
    for key, value in overrides.items():
        if value is not None:
            snapshot[key] = value

    snapshot["current_username"] = str(snapshot.get("current_username") or snapshot.get("username") or "").strip()
    snapshot["current_collage_urls"] = [
        str(item).strip()
        for item in (snapshot.get("current_collage_urls") or [])
        if str(item or "").strip()
    ]
    snapshot["reviewed_collage_urls"] = [
        str(item).strip()
        for item in (snapshot.get("reviewed_collage_urls") or [])
        if str(item or "").strip()
    ]
    if snapshot["current_collage_urls"]:
        snapshot["current_collage_url"] = snapshot["current_collage_urls"][0]
    elif snapshot.get("current_collage_url"):
        snapshot["current_collage_url"] = str(snapshot.get("current_collage_url") or "").strip() or None
    else:
        snapshot["current_collage_url"] = None

    snapshot["collage_count"] = int(snapshot.get("collage_count") or len(snapshot["current_collage_urls"]) or 0)
    snapshot["reviewed_collage_count"] = int(
        snapshot.get("reviewed_collage_count")
        or len(snapshot["reviewed_collage_urls"])
        or 0
    )
    snapshot["unused_collage_count"] = max(
        0,
        int(snapshot.get("unused_collage_count") or (snapshot["collage_count"] - snapshot["reviewed_collage_count"]) or 0),
    )
    snapshot["signals"] = [
        str(item).strip()
        for item in (snapshot.get("signals") or [])
        if str(item or "").strip()
    ]
    snapshot["log_lines"] = list(snapshot.get("log_lines") or [])
    return snapshot


def build_visual_review_history_item(live_review, success=True):
    snapshot = build_visual_review_live_snapshot(live_review)
    username = str(snapshot.get("current_username") or snapshot.get("username") or "").strip()
    if not username:
        return None

    history_item = {
        "contract_version": snapshot.get("contract_version"),
        "username": username,
        "provider": snapshot.get("provider"),
        "current_collage_url": snapshot.get("current_collage_url"),
        "current_collage_urls": list(snapshot.get("current_collage_urls") or []),
        "reviewed_collage_urls": list(snapshot.get("reviewed_collage_urls") or []),
        "collage_count": snapshot.get("collage_count"),
        "reviewed_collage_count": snapshot.get("reviewed_collage_count"),
        "unused_collage_count": snapshot.get("unused_collage_count"),
        "target_collage_count": snapshot.get("target_collage_count"),
        "requested_mode": snapshot.get("requested_mode"),
        "applied_mode": snapshot.get("applied_mode"),
        "recommended_mode": snapshot.get("recommended_mode"),
        "downgrade_reason": snapshot.get("downgrade_reason"),
        "cover_count": snapshot.get("cover_count"),
        "requested_cover_count": snapshot.get("requested_cover_count"),
        "failed_cover_count": snapshot.get("failed_cover_count"),
        "current_cover_index": snapshot.get("current_cover_index"),
        "current_cover_total": snapshot.get("current_cover_total"),
        "min_required_cover_count": snapshot.get("min_required_cover_count"),
        "collage_error_count": snapshot.get("collage_error_count"),
        "step": snapshot.get("step"),
        "decision": snapshot.get("decision"),
        "reason": snapshot.get("reason"),
        "signals": list(snapshot.get("signals") or []),
        "log_lines": list(snapshot.get("log_lines") or []),
        "updated_at": snapshot.get("updated_at"),
        "success": success,
    }
    if not success:
        history_item["error"] = str(snapshot.get("reason") or "")
    return history_item


def build_visual_review_partial(results, total, passed, rejected, failed, live_review=None, review_history=None):
    payload = {
        "visual_results": dict(results),
        "summary": {
            "total": total,
            "passed": passed,
            "rejected": rejected,
            "failed": failed,
        },
    }
    if live_review is not None:
        payload["live_review"] = build_visual_review_live_snapshot(live_review)
    if review_history is not None:
        payload["review_history"] = list(review_history)
    return payload


def evaluate_cover_collage(username, cover_urls=None, collage_assets=None, platform="tiktok"):
    assets = collage_assets or build_cover_collage_bundle_assets(cover_urls or [])
    image_data_urls = [
        str(item).strip()
        for item in (assets.get("image_data_urls") or [assets.get("image_data_url")])
        if str(item or "").strip()
    ]
    if not image_data_urls:
        raise ValueError("No collage images available for visual review")

    # 根据平台选择 prompt
    if platform == "instagram":
        prompt = VISION_PROMPT_INSTAGRAM_CUSTOM
    elif platform == "tiktok":
        prompt = VISION_PROMPT_TAPO
    else:
        prompt = VISION_PROMPT  # 默认 Ulike prompt

    content_items = [{"type": "input_text", "text": f"博主用户名：{username}\n{prompt}"}]
    content_items.extend(
        {"type": "input_image", "image_url": image_data_url}
        for image_data_url in image_data_urls
    )

    input_messages = [
        {
            "role": "user",
            "content": content_items,
        }
    ]

    attempted_providers = []
    last_error = None

    for provider in get_available_vision_providers():
        provider_name = normalize_vision_provider_name(provider.get("name")) or "unknown"
        attempted_providers.append(provider_name)
        api_key = resolve_vision_provider_api_key(provider)
        if not api_key or api_key == OPENAI_API_KEY_PLACEHOLDER:
            continue

        try:
            model_name = resolve_vision_provider_model(provider)
            client = OpenAI(
                api_key=api_key,
                base_url=provider["base_url"],
                timeout=VISION_REQUEST_TIMEOUT,
            )
            api_style = normalize_vision_api_style(provider.get("api_style"))
            if api_style == VISION_API_STYLE_CHAT_COMPLETIONS:
                raw_text = call_vision_chat_completion(client, model_name, input_messages)
            elif provider.get("stream_only"):
                raw_text = call_vision_stream(client, model_name, input_messages)
            else:
                response = client.responses.create(
                    model=model_name,
                    input=input_messages,
                )
                raw_text = extract_response_text(response)

            if not isinstance(raw_text, str) or not raw_text.strip():
                raise ValueError("Provider returned empty response")

            parsed = parse_visual_review_result(raw_text)
            parsed["raw_text"] = raw_text
            parsed["cover_count"] = assets["cover_count"]
            parsed["collage_count"] = len(image_data_urls)
            parsed["requested_mode"] = assets.get("requested_mode")
            parsed["applied_mode"] = assets.get("applied_mode")
            parsed["downgrade_reason"] = assets.get("downgrade_reason")
            parsed["provider"] = provider_name
            set_current_vision_provider(provider_name, result="success")
            return parsed
        except Exception as exc:
            last_error = RuntimeError(f"{provider_name}: {exc}")
            set_current_vision_provider(provider_name, result="failed", error=exc)
            print(f"[Vision Review] provider {provider_name} failed for {username}: {exc}")
            rotate_vision_provider(attempted_providers)
            continue

    if last_error is not None:
        raise last_error

    attempted_text = ", ".join(attempted_providers) if attempted_providers else "none"
    raise ValueError(f"No available vision provider credentials found ({attempted_text})")

# Helper to get platform data directory
def get_platform_dir(platform):
    path = os.path.join(DATA_DIR, platform)
    if not os.path.exists(path):
        os.makedirs(path)
    return path


def get_raw_data_path(platform):
    return os.path.join(get_platform_dir(platform), f"{platform}_data.json")


def get_last_non_empty_raw_snapshot_path(platform):
    return os.path.join(get_platform_dir(platform), f"{platform}_data_last_non_empty.json")


def save_last_non_empty_raw_snapshot(platform, items):
    if not isinstance(items, list) or len(items) == 0:
        return None

    path = get_last_non_empty_raw_snapshot_path(platform)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    return path


def get_file_updated_at(file_path):
    try:
        return datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat()
    except OSError:
        return ''


def write_json_file(file_path, payload):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return file_path


def get_profile_reviews_path(platform):
    return os.path.join(get_platform_dir(platform), f"{platform}_profile_reviews.json")


def get_profile_reviews_meta_path(platform):
    return os.path.join(get_platform_dir(platform), f"{platform}_profile_reviews_meta.json")


def get_visual_results_path(platform):
    return os.path.join(get_platform_dir(platform), f"{platform}_visual_results.json")


def get_visual_review_history_path(platform):
    return os.path.join(get_platform_dir(platform), f"{platform}_visual_review_history.json")


def get_visual_live_review_path(platform):
    return os.path.join(get_platform_dir(platform), f"{platform}_live_review.json")


def get_visual_review_meta_path(platform):
    return os.path.join(get_platform_dir(platform), f"{platform}_visual_review_meta.json")


def load_saved_artifact_metadata(metadata_path):
    payload = load_json_payload(metadata_path)
    return payload if isinstance(payload, dict) else {}


def normalize_saved_artifact_metadata(metadata=None, *, default_source_path='', default_updated_at=''):
    payload = metadata if isinstance(metadata, dict) else {}
    raw_data_source = str(payload.get("raw_data_source") or "current").strip() or "current"
    source_path = str(payload.get("source_path") or default_source_path or '').strip()
    updated_at = str(payload.get("updated_at") or default_updated_at or '').strip() or iso_now()
    return {
        "cached": bool(payload.get("cached")),
        "stale_result": bool(payload.get("stale_result")),
        "used_fallback": bool(payload.get("used_fallback")),
        "raw_data_source": raw_data_source,
        "source_path": source_path,
        "updated_at": updated_at,
    }


def merge_saved_artifact_metadata(*metadata_items):
    merged = {}
    for metadata in metadata_items:
        if not isinstance(metadata, dict):
            continue
        for key in ("cached", "stale_result", "used_fallback"):
            if metadata.get(key):
                merged[key] = True
        for key in ("raw_data_source", "source_path", "updated_at"):
            value = str(metadata.get(key) or '').strip()
            if value:
                if key == "updated_at":
                    merged[key] = max(value, str(merged.get(key) or '').strip())
                else:
                    merged[key] = value
    return normalize_saved_artifact_metadata(merged)


def build_saved_artifact_export_fields(metadata=None):
    artifact_meta = normalize_saved_artifact_metadata(metadata)
    return {
        "cached": artifact_meta.get("cached"),
        "stale_result": artifact_meta.get("stale_result"),
        "used_fallback": artifact_meta.get("used_fallback"),
        "raw_data_source": artifact_meta.get("raw_data_source"),
        "raw_data_source_path": artifact_meta.get("source_path"),
        "raw_data_source_updated_at": artifact_meta.get("updated_at"),
    }


def load_profile_review_artifact_metadata(platform):
    metadata_path = get_profile_reviews_meta_path(platform)
    profile_reviews_path = get_profile_reviews_path(platform)
    return normalize_saved_artifact_metadata(
        load_saved_artifact_metadata(metadata_path),
        default_source_path=profile_reviews_path,
        default_updated_at=get_file_updated_at(profile_reviews_path),
    )


def load_latest_usable_profile_review_artifact(platform):
    profile_reviews_path = get_profile_reviews_path(platform)
    return {
        "profile_reviews": load_profile_reviews(platform),
        "path": profile_reviews_path,
        **load_profile_review_artifact_metadata(platform),
    }


def load_saved_visual_review_artifact(platform):
    visual_results_path = get_visual_results_path(platform)
    review_history_path = get_visual_review_history_path(platform)
    live_review_path = get_visual_live_review_path(platform)
    visual_results = load_json_payload(visual_results_path)
    review_history = load_json_payload(review_history_path)
    live_review = load_json_payload(live_review_path)
    last_updated_at = max(
        [
            get_file_updated_at(visual_results_path),
            get_file_updated_at(review_history_path),
            get_file_updated_at(live_review_path),
            '',
        ]
    )
    metadata = normalize_saved_artifact_metadata(
        load_saved_artifact_metadata(get_visual_review_meta_path(platform)),
        default_source_path=visual_results_path,
        default_updated_at=last_updated_at,
    )
    return {
        "visual_results": visual_results if isinstance(visual_results, dict) else {},
        "review_history": review_history if isinstance(review_history, list) else [],
        "live_review": live_review if isinstance(live_review, dict) else {},
        "path": visual_results_path,
        "visual_results_path": visual_results_path,
        "review_history_path": review_history_path,
        "live_review_path": live_review_path,
        **metadata,
    }


def build_saved_final_review_artifact_status(platform, profile_review_artifact=None, visual_artifact=None):
    profile_review_artifact = profile_review_artifact or load_latest_usable_profile_review_artifact(platform)
    visual_artifact = visual_artifact or load_saved_visual_review_artifact(platform)
    updated_at = max(
        [
            str(profile_review_artifact.get("updated_at") or '').strip(),
            str(visual_artifact.get("updated_at") or '').strip(),
            '',
        ]
    )
    return {
        "saved_final_review_artifacts_available": bool(
            (profile_review_artifact.get("profile_reviews") or [])
            and (visual_artifact.get("visual_results") or {})
        ),
        "saved_final_review_artifacts_updated_at": updated_at,
    }


def save_profile_reviews(platform, profile_reviews, metadata=None):
    profile_reviews_path = get_profile_reviews_path(platform)
    write_json_file(profile_reviews_path, profile_reviews)
    merged_metadata = merge_saved_artifact_metadata(
        load_profile_review_artifact_metadata(platform),
        metadata,
        {
            "source_path": (metadata or {}).get("source_path") or profile_reviews_path,
            "updated_at": iso_now(),
        },
    )
    write_json_file(get_profile_reviews_meta_path(platform), merged_metadata)
    return profile_reviews_path


def save_visual_review_artifacts(platform, result, metadata=None):
    visual_results = (result or {}).get("visual_results") or {}
    review_history = (result or {}).get("review_history") or []
    live_review = (result or {}).get("live_review") or {}
    visual_results_path = write_json_file(get_visual_results_path(platform), visual_results)
    write_json_file(get_visual_review_history_path(platform), review_history)
    write_json_file(get_visual_live_review_path(platform), live_review)
    merged_metadata = merge_saved_artifact_metadata(
        load_saved_visual_review_artifact(platform),
        metadata,
        {
            "source_path": (metadata or {}).get("source_path") or visual_results_path,
            "updated_at": iso_now(),
        },
    )
    write_json_file(get_visual_review_meta_path(platform), merged_metadata)
    visual_artifact = load_saved_visual_review_artifact(platform)
    return {
        **visual_artifact,
        **build_saved_final_review_artifact_status(platform, visual_artifact=visual_artifact),
    }


def load_raw_items_for_test_export(platform):
    current_path = get_raw_data_path(platform)
    snapshot_path = get_last_non_empty_raw_snapshot_path(platform)

    current_items = load_json_payload(current_path)
    if current_items is None:
        current_items = []
    elif not isinstance(current_items, list):
        current_items = [current_items]

    if current_items:
        return {
            "items": current_items,
            "source": "current",
            "path": current_path,
            "updated_at": get_file_updated_at(current_path),
            "used_fallback": False,
        }

    snapshot_items = load_json_payload(snapshot_path)
    if snapshot_items is None:
        snapshot_items = []
    elif not isinstance(snapshot_items, list):
        snapshot_items = [snapshot_items]

    if snapshot_items:
        print(
            f"[Test Export] {platform} raw data empty at {current_path}, "
            f"falling back to last non-empty snapshot {snapshot_path}"
        )
        return {
            "items": snapshot_items,
            "source": "last_non_empty_snapshot",
            "path": snapshot_path,
            "updated_at": get_file_updated_at(snapshot_path),
            "used_fallback": True,
        }

    return {
        "items": [],
        "source": "unavailable",
        "path": snapshot_path if os.path.exists(snapshot_path) else current_path,
        "updated_at": '',
        "used_fallback": False,
    }


def load_latest_usable_scrape_artifact(platform, current_path=None):
    artifact = load_raw_items_for_test_export(platform)
    if current_path:
        artifact = dict(artifact)
        artifact["requested_path"] = current_path
    return artifact


def get_upload_metadata_path(platform):
    return os.path.join(get_platform_dir(platform), f"{platform}_upload_metadata.json")


def save_upload_metadata(platform, metadata_map, replace=False):
    path = get_upload_metadata_path(platform)
    payload = metadata_map if isinstance(metadata_map, dict) else {}

    if not replace:
        merged = load_upload_metadata(platform)
        if not isinstance(merged, dict):
            merged = {}
        merged.update(payload)
        payload = merged

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path


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


def normalize_upload_column_name(name):
    text = str(name or '').strip().lower().replace('@', '')
    if not text:
        return ''
    return re.sub(r'[^a-z0-9]+', '_', text).strip('_')


def clean_upload_metadata_value(value):
    if value is None:
        return ''

    if hasattr(value, 'item') and not isinstance(value, (str, bytes, bytearray)):
        try:
            value = value.item()
        except Exception:
            pass

    if isinstance(value, float):
        if math.isnan(value):
            return ''
        if value.is_integer():
            return int(value)
        return round(value, 6)

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, str):
        return value.strip()

    return value


def sanitize_json_compatible(value):
    if value is None:
        return None

    if hasattr(value, 'item') and not isinstance(value, (str, bytes, bytearray)):
        try:
            value = value.item()
        except Exception:
            pass

    if isinstance(value, dict):
        return {
            str(key): sanitize_json_compatible(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [sanitize_json_compatible(item) for item in value]

    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        if value.is_integer():
            return int(value)
        return value

    if isinstance(value, datetime):
        return value.isoformat()

    return value


def find_upload_content_column(columns):
    normalized_lookup = {}
    for column in columns:
        normalized = normalize_upload_column_name(column)
        if normalized and normalized not in normalized_lookup:
            normalized_lookup[normalized] = column

    for candidate in UPLOAD_METADATA_CONTENT_COLUMN_CANDIDATES:
        matched = normalized_lookup.get(candidate)
        if matched:
            return matched
    return None


def resolve_canonical_upload_columns(columns):
    normalized_lookup = {}
    for column in columns:
        normalized = normalize_upload_column_name(column)
        if normalized and normalized not in normalized_lookup:
            normalized_lookup[normalized] = column

    resolved_columns = {}
    missing_labels = []
    for spec in CANONICAL_UPLOAD_REQUIRED_FIELDS:
        matched = None
        for candidate in spec["accepted_columns"]:
            matched = normalized_lookup.get(candidate)
            if matched:
                break
        if matched:
            resolved_columns[spec["field"]] = matched
        else:
            missing_labels.append(spec["label"])

    resolved_columns["url"] = find_upload_content_column(columns)
    return resolved_columns, missing_labels


def normalize_upload_platform_value(value):
    normalized = normalize_upload_column_name(value)
    if not normalized:
        return ''
    return UPLOAD_PLATFORM_ALIASES.get(normalized, '')


def is_empty_upload_row(row_dict):
    for key, raw_value in row_dict.items():
        if str(key or "").startswith("__"):
            continue
        clean_value = clean_upload_metadata_value(raw_value)
        if clean_value not in ('', None):
            return False
    return True


def build_canonical_profile_url(platform, identifier, raw_handle=''):
    text = str(raw_handle or '').strip()
    if re.match(r'^https?://', text, re.IGNORECASE):
        return text

    if platform == 'tiktok':
        return f"https://www.tiktok.com/@{identifier}"
    if platform == 'instagram':
        return f"https://www.instagram.com/{identifier}/"
    if platform == 'youtube':
        lowered = text.lower().lstrip('/')
        if lowered.startswith('channel/'):
            return f"https://www.youtube.com/{text.lstrip('/')}"
        if lowered.startswith('c/'):
            return f"https://www.youtube.com/{text.lstrip('/')}"
        if lowered.startswith('user/'):
            return f"https://www.youtube.com/{text.lstrip('/')}"
        if re.match(r'(?i)^uc[\w-]+$', text):
            return f"https://www.youtube.com/channel/{text}"
        handle = text.lstrip('@') or identifier
        return f"https://www.youtube.com/@{handle}"
    return ''


def build_grouped_upload_value(platform, identifier, raw_handle='', raw_url=''):
    for candidate in (raw_url, raw_handle):
        text = str(candidate or '').strip()
        if re.match(r'^https?://', text, re.IGNORECASE):
            return text

    if platform == 'youtube':
        return build_canonical_profile_url(platform, identifier, raw_handle)

    return identifier


def build_upload_validation_error(message, details, error_code="UPLOAD_TEMPLATE_INVALID"):
    payload = {
        "success": False,
        "error": message,
        "error_code": error_code,
        "details": [str(item) for item in details if str(item).strip()],
    }
    return jsonify(payload), 400


def format_upload_row_location(row_dict, fallback_row_num):
    if not isinstance(row_dict, dict):
        return f"第 {fallback_row_num} 行"

    sheet_name = str(row_dict.get("__sheet_name") or "").strip()
    sheet_row_num = clean_upload_metadata_value(row_dict.get("__sheet_row_num"))
    try:
        sheet_row_num = int(sheet_row_num)
    except (TypeError, ValueError):
        sheet_row_num = fallback_row_num

    if sheet_name:
        return f"Sheet `{sheet_name}` 第 {sheet_row_num} 行"
    return f"第 {sheet_row_num} 行"


def load_canonical_upload_workbook_frames(filepath):
    import pandas as pd

    workbook = pd.read_excel(filepath, sheet_name=None)
    if not isinstance(workbook, dict) or not workbook:
        return []

    frames = []
    for sheet_name, df in workbook.items():
        if df is None or not hasattr(df, "empty") or df.empty:
            continue

        prepared_df = df.copy()
        prepared_df["__sheet_name"] = str(sheet_name or "").strip() or "Sheet1"
        prepared_df["__sheet_row_num"] = [index + 2 for index in range(len(prepared_df))]

        has_visible_value = False
        visible_columns = [column for column in prepared_df.columns if not str(column or "").startswith("__")]
        for column in visible_columns:
            series = prepared_df[column]
            if series is None:
                continue
            for value in series.tolist():
                cleaned = clean_upload_metadata_value(value)
                if cleaned not in ("", None):
                    has_visible_value = True
                    break
            if has_visible_value:
                break

        if has_visible_value:
            frames.append(prepared_df)

    return frames


def extract_platform_identifier_from_value(platform, value):
    text = str(value or "").strip()
    if not text:
        return ''

    if platform == 'instagram':
        match = re.search(r'instagram\.com/([^/?#]+)', text, re.IGNORECASE)
        if match:
            return normalize_identifier(match.group(1))
    elif platform == 'tiktok':
        match = re.search(r'tiktok\.com/@([^/?#]+)', text, re.IGNORECASE)
        if match:
            return normalize_identifier(match.group(1))
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
                return normalize_identifier(match.group(1))

    return normalize_identifier(text)


def build_upload_metadata_record(row_dict, platform, content_value, source_filename):
    metadata = {
        "url": str(content_value or "").strip(),
        "source_filename": source_filename,
    }

    for column_name, raw_value in row_dict.items():
        normalized_column = normalize_upload_column_name(column_name)
        mapped_field = UPLOAD_METADATA_FIELD_ALIASES.get(normalized_column)
        if not mapped_field:
            continue
        clean_value = clean_upload_metadata_value(raw_value)
        if clean_value in ('', None):
            continue
        metadata[mapped_field] = clean_value

    if not metadata.get("handle"):
        metadata["handle"] = extract_platform_identifier_from_value(platform, content_value)

    return metadata


def parse_canonical_upload_workbook(df, source_filename):
    resolved_columns, missing_labels = resolve_canonical_upload_columns(df.columns)
    if missing_labels:
        detail_lines = [f"缺少必填列：{label}" for label in missing_labels]
        detail_lines.append("固定模板至少需要 `Platform` 和 `@username` 两列。")
        return None, build_upload_validation_error(
            f"上传模板缺少必填列：{', '.join(missing_labels)}",
            detail_lines,
        )

    grouped_data = {
        "tiktok": [],
        "instagram": [],
        "youtube": [],
    }
    metadata_by_platform = {
        "tiktok": {},
        "instagram": {},
        "youtube": {},
    }
    preview_rows = []
    invalid_platform_rows = []
    invalid_identifier_rows = []
    processed_rows = 0

    for index, (_, row_series) in enumerate(df.iterrows(), start=2):
        row_dict = row_series.to_dict()
        if not isinstance(row_dict, dict) or is_empty_upload_row(row_dict):
            continue

        processed_rows += 1
        row_location = format_upload_row_location(row_dict, index)
        raw_platform = clean_upload_metadata_value(row_dict.get(resolved_columns["platform"]))
        platform = normalize_upload_platform_value(raw_platform)
        if not platform:
            invalid_platform_rows.append(
                f"{row_location} Platform=`{raw_platform}` 无效，只支持 Instagram / TikTok / YouTube。"
            )
            continue

        raw_handle = clean_upload_metadata_value(row_dict.get(resolved_columns["handle"]))
        raw_url = clean_upload_metadata_value(row_dict.get(resolved_columns.get("url"))) if resolved_columns.get("url") else ''
        identifier = (
            extract_platform_identifier_from_value(platform, raw_handle)
            or extract_platform_identifier_from_value(platform, raw_url)
        )
        if not identifier:
            invalid_identifier_rows.append(
                f"{row_location} @username 为空或无法识别：`{raw_handle}`。"
            )
            continue

        canonical_url = raw_url or build_canonical_profile_url(platform, identifier, raw_handle)
        metadata = build_upload_metadata_record(row_dict, platform, canonical_url, source_filename)
        metadata["handle"] = identifier
        metadata["platform"] = platform
        if canonical_url:
            metadata["url"] = canonical_url
        metadata_by_platform[platform][identifier] = sanitize_json_compatible(metadata)
        grouped_data[platform].append(
            build_grouped_upload_value(platform, identifier, raw_handle, canonical_url)
        )

        if len(preview_rows) < 5:
            preview_rows.append(sanitize_json_compatible({
                "Platform": UPLOAD_PLATFORM_RESPONSE_LABELS.get(platform, platform),
                "@username": identifier,
                "URL": canonical_url,
                "nickname": metadata.get("nickname", ""),
                "Region": metadata.get("region", ""),
                "Language": metadata.get("language", ""),
                "Followers": metadata.get("followers", ""),
            }))

    if processed_rows == 0:
        return None, build_upload_validation_error(
            "上传表没有可用数据行",
            ["请确认表头下方至少有一行 `Platform` 和 `@username` 都已填写的账号数据。"],
        )

    error_details = invalid_platform_rows + invalid_identifier_rows
    if error_details:
        return None, build_upload_validation_error(
            "上传模板存在无效数据，请修正后重试",
            error_details[:20],
        )

    deduped_grouped_data = {
        platform: list(dict.fromkeys(values))
        for platform, values in grouped_data.items()
    }
    stats = {
        UPLOAD_PLATFORM_RESPONSE_LABELS[platform]: len(deduped_grouped_data[platform])
        for platform in ("tiktok", "instagram", "youtube")
    }
    stats["Unknown"] = 0

    return {
        "grouped_data": deduped_grouped_data,
        "metadata_by_platform": metadata_by_platform,
        "preview": preview_rows,
        "stats": stats,
    }, None


def build_upload_metadata_by_platform(rows, source_filename):
    grouped = {
        "tiktok": {},
        "instagram": {},
        "youtube": {},
    }

    for row in rows:
        if not isinstance(row, dict):
            continue
        platform_label = str(row.get("Platform") or "").strip().lower()
        content_value = str(row.get("content") or "").strip()
        if platform_label not in grouped or not content_value:
            continue

        metadata = build_upload_metadata_record(row, platform_label, content_value, source_filename)
        identifier = (
            extract_platform_identifier_from_value(platform_label, metadata.get("url"))
            or extract_platform_identifier_from_value(platform_label, metadata.get("handle"))
            or extract_platform_identifier_from_value(platform_label, row.get("username"))
        )
        if not identifier:
            continue
        grouped[platform_label][identifier] = metadata

    return grouped


def merge_upload_metadata_into_reviews(platform, profile_reviews):
    if not isinstance(profile_reviews, list):
        return profile_reviews

    metadata_lookup = load_upload_metadata(platform)

    merged_reviews = []
    for item in profile_reviews:
        if not isinstance(item, dict):
            merged_reviews.append(item)
            continue

        merged_reviews.append(
            merge_upload_metadata_into_review_item(
                platform,
                item,
                metadata_lookup=metadata_lookup,
            )
        )

    return merged_reviews


def normalize_profile_review_item(platform, item):
    if not isinstance(item, dict):
        return item

    normalized = dict(item)
    status = str(normalized.get("status") or "").strip()
    if status not in {"Pass", "Reject", "Missing"}:
        status = "Reject"

    covers = normalized.get("covers")
    if not isinstance(covers, list):
        covers = []
    else:
        covers = [str(value).strip() for value in covers if str(value or "").strip()]

    soft_flags = normalized.get("soft_flags")
    if not isinstance(soft_flags, list):
        soft_flags = []

    stats = normalized.get("stats")
    if not isinstance(stats, dict):
        stats = {}

    upload_metadata = normalized.get("upload_metadata")
    if not isinstance(upload_metadata, dict):
        upload_metadata = {}

    normalized["platform"] = str(normalized.get("platform") or platform or "").strip()
    normalized["username"] = str(normalized.get("username") or "").strip()
    normalized["profile_url"] = str(normalized.get("profile_url") or "").strip()
    normalized["status"] = status
    normalized["reason"] = str(normalized.get("reason") or "").strip()
    normalized["covers"] = covers
    normalized["latest_post_time"] = normalized.get("latest_post_time") or None
    normalized["soft_flags"] = soft_flags
    normalized["stats"] = stats
    normalized["upload_metadata"] = upload_metadata
    return normalized


def resolve_profile_review_identifier(platform, item, preferred_identifier=None):
    candidates = [preferred_identifier]
    if isinstance(item, dict):
        candidates.extend([
            item.get("profile_url"),
            item.get("username"),
        ])
        upload_metadata = item.get("upload_metadata")
        if isinstance(upload_metadata, dict):
            candidates.extend([
                upload_metadata.get("url"),
                upload_metadata.get("handle"),
            ])

    for candidate in candidates:
        identifier = extract_platform_identifier_from_value(platform, candidate)
        if identifier:
            return identifier
    return ""


def merge_upload_metadata_into_review_item(platform, item, metadata_lookup=None, preferred_identifier=None):
    normalized = normalize_profile_review_item(platform, item)
    if not isinstance(normalized, dict):
        return normalized

    if metadata_lookup is None:
        metadata_lookup = load_upload_metadata(platform)
    if not isinstance(metadata_lookup, dict):
        metadata_lookup = {}

    identifier = resolve_profile_review_identifier(
        platform,
        normalized,
        preferred_identifier=preferred_identifier,
    )
    canonical_metadata = metadata_lookup.get(identifier) if identifier else None
    existing_metadata = normalized.get("upload_metadata")
    if not isinstance(existing_metadata, dict):
        existing_metadata = {}

    normalized["upload_metadata"] = dict(canonical_metadata) if isinstance(canonical_metadata, dict) else dict(existing_metadata)
    if not normalized.get("profile_url") and normalized["upload_metadata"].get("url"):
        normalized["profile_url"] = str(normalized["upload_metadata"].get("url") or "").strip()
    if not normalized.get("username") and normalized["upload_metadata"].get("handle"):
        normalized["username"] = str(normalized["upload_metadata"].get("handle") or "").strip()
    return normalized


def append_upload_metadata_to_export_row(row, item):
    metadata = item.get("upload_metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    for export_key, metadata_key in UPLOAD_METADATA_EXPORT_FIELDS:
        row[export_key] = metadata.get(metadata_key, '')
    return row


def get_tiktok_cover_cache_dir():
    path = os.path.join(get_platform_dir("tiktok"), "covers")
    os.makedirs(path, exist_ok=True)
    return path


def normalize_tiktok_profile_key(value):
    text = str(value or "").strip().lower()
    if text.startswith("@"):
        text = text[1:]
    return text


def append_unique_candidate(candidates, seen, value):
    text = str(value or "").strip()
    if not text or text in seen:
        return
    seen.add(text)
    candidates.append(text)


def extract_media_url_candidates(media_urls):
    candidates = []
    seen = set()
    if not isinstance(media_urls, list):
        return candidates

    for entry in media_urls:
        if isinstance(entry, str):
            append_unique_candidate(candidates, seen, entry)
            continue
        if not isinstance(entry, dict):
            continue
        for key in (
            "downloadUrl",
            "downloadLink",
            "originalUrl",
            "mediaUrl",
            "url",
            "src",
            "fileUrl",
            "imageUrl",
            "thumbnailUrl",
        ):
            append_unique_candidate(candidates, seen, entry.get(key))
    return candidates


def get_tiktok_item_cover_candidates(item):
    candidates = []
    seen = set()
    if not isinstance(item, dict):
        return candidates

    for candidate in extract_media_url_candidates(item.get("mediaUrls")):
        append_unique_candidate(candidates, seen, candidate)

    if item.get("isSlideshow"):
        for link in item.get("slideshowImageLinks") or []:
            if not isinstance(link, dict):
                continue
            append_unique_candidate(candidates, seen, link.get("downloadLink"))
            append_unique_candidate(candidates, seen, link.get("tiktokLink"))
            append_unique_candidate(candidates, seen, link.get("url"))

    video_meta = item.get("videoMeta") or {}
    for key in (
        "originalCoverMediumUrl",
        "coverMediumUrl",
        "originalCoverUrl",
        "coverUrl",
    ):
        append_unique_candidate(candidates, seen, video_meta.get(key))

    return candidates


def get_tiktok_grouped_items():
    data_file_path = os.path.join(get_platform_dir("tiktok"), "tiktok_data.json")
    if not os.path.exists(data_file_path):
        return {}

    try:
        mtime = os.path.getmtime(data_file_path)
    except OSError:
        return {}

    with TIKTOK_DATA_CACHE_LOCK:
        cached_mtime = TIKTOK_DATA_CACHE.get("mtime")
        cached_grouped = TIKTOK_DATA_CACHE.get("grouped_items") or {}
        if cached_mtime == mtime and cached_grouped:
            return cached_grouped

        raw_payload = load_json_payload(data_file_path)
        if raw_payload is None:
            TIKTOK_DATA_CACHE["mtime"] = mtime
            TIKTOK_DATA_CACHE["grouped_items"] = {}
            return {}
        if not isinstance(raw_payload, list):
            raw_payload = [raw_payload]

        grouped_items = {}
        for raw_item in raw_payload:
            if not isinstance(raw_item, dict):
                continue
            author_meta = raw_item.get("authorMeta") or {}
            author_key = normalize_tiktok_profile_key(author_meta.get("name") or author_meta.get("profileUrl"))
            if not author_key:
                continue
            grouped_items.setdefault(author_key, []).append(raw_item)

        for author_key, items in grouped_items.items():
            grouped_items[author_key] = sorted(
                items,
                key=lambda item: str(item.get("createTimeISO") or ""),
                reverse=True,
            )

        TIKTOK_DATA_CACHE["mtime"] = mtime
        TIKTOK_DATA_CACHE["grouped_items"] = grouped_items
        return grouped_items


def get_tiktok_profile_cover_candidates(review_item, max_candidates=MAX_VISUAL_REVIEW_CANDIDATE_COVERS):
    if max_candidates <= 0 or not isinstance(review_item, dict):
        return []

    username = normalize_tiktok_profile_key(review_item.get("username") or review_item.get("profile_url"))
    if not username:
        return []

    matched_items = get_tiktok_grouped_items().get(username) or []

    candidates = []
    seen = set()
    for raw_item in matched_items:
        for candidate in get_tiktok_item_cover_candidates(raw_item):
            append_unique_candidate(candidates, seen, candidate)
            if len(candidates) >= max_candidates:
                return candidates

    return candidates


def build_visual_review_cover_candidates(review_item, platform="tiktok"):
    candidates = []
    seen = set()
    if platform == "tiktok":
        max_candidates = max(MAX_VISUAL_REVIEW_CANDIDATE_COVERS, MAX_TOTAL_VISUAL_REVIEW_COVERS)
    else:
        max_candidates = MAX_TOTAL_VISUAL_REVIEW_COVERS

    for source in review_item.get("cover_paths") or []:
        append_unique_candidate(candidates, seen, source)
    for source in review_item.get("covers") or []:
        append_unique_candidate(candidates, seen, source)
    for source in review_item.get("cover_urls") or []:
        append_unique_candidate(candidates, seen, source)

    if platform == "tiktok":
        for source in get_tiktok_profile_cover_candidates(review_item, max_candidates=max_candidates):
            append_unique_candidate(candidates, seen, source)
            if len(candidates) >= max_candidates:
                break

    return candidates[:max_candidates]


def split_cover_urls_for_visual_review(cover_urls, max_collage_count=MAX_VISUAL_REVIEW_COLLAGE_COUNT):
    valid_urls = [str(url).strip() for url in cover_urls if str(url).strip()]
    if not valid_urls:
        return []

    collage_count = max(1, max_collage_count)
    selected_urls = valid_urls[:MAX_COLLAGE_COVER_COUNT * collage_count]
    return [
        selected_urls[idx:idx + MAX_COLLAGE_COVER_COUNT]
        for idx in range(0, len(selected_urls), MAX_COLLAGE_COVER_COUNT)
        if selected_urls[idx:idx + MAX_COLLAGE_COVER_COUNT]
    ]

def classify_platform(url):
    if not isinstance(url, str):
        return 'Unknown'
    url = url.lower()
    if 'tiktok.com' in url:
        return 'TikTok'
    elif 'instagram.com' in url:
        return 'Instagram'
    elif 'youtube.com' in url or 'youtu.be' in url:
        return 'YouTube'
    return 'Unknown'

def load_json_payload(file_path):
    """
    Load JSON from a file that may contain CLI logs before the JSON payload.
    Returns None when the file is missing, empty, or does not contain valid JSON.
    """
    if not os.path.exists(file_path):
        return None

    with open(file_path, 'r') as f:
        raw_text = f.read().strip()

    if not raw_text:
        return None

    for idx, char in enumerate(raw_text):
        if char in ['[', '{']:
            try:
                return json.loads(raw_text[idx:])
            except json.JSONDecodeError:
                return None

    return None

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

    return text.lstrip('@')

def get_review_stage_label(status, reason):
    if status == 'Pass':
        return 'passed_prescreen'
    if status == 'Missing' or reason in {'No data returned by scraper', '采集器未返回该账号数据'}:
        return 'missing_data'
    if status == 'Reject':
        return 'rejected_prescreen'
    return status or 'unknown'

def format_soft_flags_for_export(soft_flags):
    if not isinstance(soft_flags, list):
        return ''

    parts = []
    for item in soft_flags:
        if isinstance(item, dict):
            keyword = str(item.get('keyword') or '').strip()
            source = str(item.get('source') or '').strip()
            if keyword and source:
                parts.append(f'"{keyword}"@{source}')
            elif keyword:
                parts.append(f'"{keyword}"')
            elif source:
                parts.append(source)
        elif item:
            parts.append(str(item).strip())

    return '；'.join(part for part in parts if part)


def build_audit_export_context(
    platform,
    review_item=None,
    metadata_lookup=None,
    preferred_identifier=None,
    raw_item=None,
):
    if metadata_lookup is None:
        metadata_lookup = load_upload_metadata(platform)
    if not isinstance(metadata_lookup, dict):
        metadata_lookup = {}

    raw_item = raw_item if isinstance(raw_item, dict) else {}
    identifier = (
        preferred_identifier
        or get_profile_review_identifier(platform, review_item)
        or get_raw_item_identifier(platform, raw_item)
    )

    canonical_review_item = {}
    if isinstance(review_item, dict) and review_item:
        canonical_review_item = merge_upload_metadata_into_review_item(
            platform,
            review_item,
            metadata_lookup=metadata_lookup,
            preferred_identifier=identifier,
        )

    metadata = {}
    if identifier and isinstance(metadata_lookup.get(identifier), dict):
        metadata = dict(metadata_lookup.get(identifier) or {})
    elif isinstance(canonical_review_item.get("upload_metadata"), dict):
        metadata = dict(canonical_review_item.get("upload_metadata") or {})

    username = (
        str(canonical_review_item.get("username") or "").strip()
        or str(metadata.get("handle") or "").strip()
        or get_raw_item_username(platform, raw_item)
        or identifier
    )
    profile_url = (
        str(canonical_review_item.get("profile_url") or "").strip()
        or str(metadata.get("url") or "").strip()
        or get_raw_item_profile_url(platform, raw_item)
    )
    account_id = str(canonical_review_item.get("account_id") or "").strip() or username or identifier
    source_filename = str(metadata.get("source_filename") or "").strip()

    export_item = dict(canonical_review_item) if isinstance(canonical_review_item, dict) else {}
    if metadata and not export_item.get("upload_metadata"):
        export_item["upload_metadata"] = metadata

    return {
        "platform": platform,
        "identifier": identifier,
        "username": username,
        "account_id": account_id,
        "profile_url": profile_url,
        "source_filename": source_filename,
        "metadata": metadata,
        "review_item": canonical_review_item,
        "export_item": export_item,
    }


def build_audit_export_row_base(
    platform,
    review_item=None,
    metadata_lookup=None,
    preferred_identifier=None,
    raw_item=None,
    include_account_id=False,
):
    context = build_audit_export_context(
        platform,
        review_item=review_item,
        metadata_lookup=metadata_lookup,
        preferred_identifier=preferred_identifier,
        raw_item=raw_item,
    )
    row = {
        "platform": context["platform"],
        "identifier": context["identifier"],
        "username": context["username"],
        "profile_url": context["profile_url"],
        "source_filename": context["source_filename"],
    }
    if include_account_id:
        row["account_id"] = context["account_id"]
    return append_upload_metadata_to_export_row(row, context["export_item"]), context


def append_runtime_stats_to_export_row(row, review_item):
    stats = {}
    if isinstance(review_item, dict) and isinstance(review_item.get("stats"), dict):
        stats = review_item.get("stats") or {}

    for export_key, stats_key in (
        ("runtime_avg_views", "avg_views"),
        ("runtime_median_views", "median_views"),
        ("runtime_video_count", "video_count"),
    ):
        value = stats.get(stats_key)
        row[export_key] = value if value not in (None, "") else ""
    return row


def build_image_review_rows(platform, profile_reviews, artifact_metadata=None):
    rows = []
    metadata_lookup = load_upload_metadata(platform)
    export_fields = build_saved_artifact_export_fields(artifact_metadata)
    for item in merge_upload_metadata_into_reviews(platform, profile_reviews):
        covers = item.get('covers') or []
        row, context = build_audit_export_row_base(
            platform,
            review_item=item,
            metadata_lookup=metadata_lookup,
        )
        review_item = context["review_item"]
        append_runtime_stats_to_export_row(row, review_item)
        row.update({
            'status': review_item.get('status'),
            'reason': review_item.get('reason'),
            'stage_status': get_review_stage_label(review_item.get('status'), review_item.get('reason')),
            'stage_reason': review_item.get('reason'),
            'latest_post_time': review_item.get('latest_post_time'),
            'soft_flags': format_soft_flags_for_export(review_item.get('soft_flags')),
            'cover_count': len(covers),
        })
        row.update(export_fields)
        for idx in range(9):
            row[f'cover_{idx + 1}'] = covers[idx] if idx < len(covers) else ''
        rows.append(row)
    return rows


def build_prescreen_review_rows(platform, profile_reviews, artifact_metadata=None):
    rows = []
    metadata_lookup = load_upload_metadata(platform)
    export_fields = build_saved_artifact_export_fields(artifact_metadata)
    for item in merge_upload_metadata_into_reviews(platform, profile_reviews):
        if not isinstance(item, dict):
            continue
        row, context = build_audit_export_row_base(
            platform,
            review_item=item,
            metadata_lookup=metadata_lookup,
        )
        review_item = context["review_item"]
        append_runtime_stats_to_export_row(row, review_item)
        row.update({
            'status': review_item.get('status'),
            'stage_status': get_review_stage_label(review_item.get('status'), review_item.get('reason')),
            'reason': review_item.get('reason'),
            'latest_post_time': review_item.get('latest_post_time'),
            'soft_flags': format_soft_flags_for_export(review_item.get('soft_flags')),
            'cover_count': len(review_item.get('covers') or []),
        })
        row.update(export_fields)
        rows.append(row)
    return rows


def format_visual_signals_for_export(signals):
    if not isinstance(signals, list):
        return ''

    parts = []
    for item in signals:
        text = str(item or '').strip()
        if text:
            parts.append(text)
    return '；'.join(parts)


def build_final_review_rows(platform, profile_reviews, visual_results, artifact_metadata=None):
    rows = []
    visual_lookup = {}
    merged_reviews = merge_upload_metadata_into_reviews(platform, profile_reviews)
    metadata_lookup = load_upload_metadata(platform)
    export_fields = build_saved_artifact_export_fields(artifact_metadata)

    if isinstance(visual_results, dict):
        for key, review in visual_results.items():
            if not isinstance(review, dict):
                continue
            review_username = review.get('username') or key
            normalized_username = normalize_identifier(review_username)
            if normalized_username:
                visual_lookup[normalized_username] = review

    for item in merged_reviews:
        if not isinstance(item, dict):
            continue

        context = build_audit_export_context(
            platform,
            review_item=item,
            metadata_lookup=metadata_lookup,
        )
        review_item = context["review_item"]
        username = context["username"]
        normalized_username = normalize_identifier(username)
        prescreen_status = str(review_item.get('status') or '').strip()
        prescreen_reason = str(review_item.get('reason') or '').strip()
        review = visual_lookup.get(normalized_username)

        visual_status = 'Not Reviewed'
        visual_reason = ''
        visual_signals = ''
        final_status = prescreen_status
        final_reason = prescreen_reason

        if prescreen_status == 'Pass' and isinstance(review, dict):
            if review.get('success') is False:
                visual_status = 'Error'
                visual_reason = str(review.get('error') or '').strip()
                final_status = 'Error'
                final_reason = visual_reason or prescreen_reason
            else:
                visual_status = str(review.get('decision') or 'Pass').strip() or 'Pass'
                visual_reason = str(review.get('reason') or '').strip()
                visual_signals = format_visual_signals_for_export(review.get('signals'))
                final_status = visual_status
                final_reason = visual_reason or prescreen_reason

        row, _ = build_audit_export_row_base(
            platform,
            review_item=review_item,
            metadata_lookup=metadata_lookup,
            include_account_id=True,
        )
        append_runtime_stats_to_export_row(row, review_item)
        row.update({
            'prescreen_status': prescreen_status,
            'prescreen_reason': prescreen_reason,
            'visual_status': visual_status,
            'visual_reason': visual_reason,
            'visual_signals': visual_signals,
            'status': final_status,
            'reason': final_reason,
            'final_status': final_status,
            'final_reason': final_reason,
        })
        row.update(export_fields)
        rows.append(row)

    return rows


def get_profile_review_identifier(platform, item):
    if not isinstance(item, dict):
        return ''

    return (
        extract_platform_identifier_from_value(platform, item.get('profile_url'))
        or extract_platform_identifier_from_value(platform, item.get('username'))
        or extract_platform_identifier_from_value(platform, item.get('account_id'))
    )


def get_raw_item_identifier(platform, item):
    if not isinstance(item, dict):
        return ''

    if platform == 'instagram':
        return (
            extract_platform_identifier_from_value(platform, item.get('username'))
            or extract_platform_identifier_from_value(platform, item.get('url'))
            or extract_platform_identifier_from_value(platform, item.get('inputUrl'))
        )

    if platform == 'tiktok':
        author_meta = item.get('authorMeta') or {}
        return (
            extract_platform_identifier_from_value(platform, author_meta.get('name'))
            or extract_platform_identifier_from_value(platform, author_meta.get('profileUrl'))
            or extract_platform_identifier_from_value(platform, item.get('webVideoUrl'))
            or extract_platform_identifier_from_value(platform, item.get('url'))
        )

    if platform == 'youtube':
        return (
            extract_platform_identifier_from_value(platform, item.get('channelUrl'))
            or extract_platform_identifier_from_value(platform, item.get('url'))
            or normalize_identifier(item.get('channelName'))
        )

    return ''


def get_raw_item_username(platform, item):
    if not isinstance(item, dict):
        return ''

    if platform == 'instagram':
        return str(item.get('username') or '').strip().lstrip('@')

    if platform == 'tiktok':
        author_meta = item.get('authorMeta') or {}
        return str(author_meta.get('name') or '').strip().lstrip('@')

    if platform == 'youtube':
        return str(item.get('channelName') or item.get('author') or '').strip()

    return ''


def get_raw_item_profile_url(platform, item):
    if not isinstance(item, dict):
        return ''

    if platform == 'instagram':
        return str(item.get('url') or item.get('inputUrl') or '').strip()

    if platform == 'tiktok':
        author_meta = item.get('authorMeta') or {}
        return str(author_meta.get('profileUrl') or item.get('url') or '').strip()

    if platform == 'youtube':
        return str(item.get('channelUrl') or item.get('url') or '').strip()

    return ''


def build_profile_review_lookup(platform, profile_reviews):
    lookup = {}
    ordered_identifiers = []

    for item in profile_reviews or []:
        if not isinstance(item, dict):
            continue
        identifier = get_profile_review_identifier(platform, item)
        if not identifier:
            continue
        if identifier not in lookup:
            ordered_identifiers.append(identifier)
        lookup[identifier] = item

    return lookup, ordered_identifiers


def merge_saved_profile_reviews(platform, requested_profile_reviews, saved_profile_reviews):
    requested_reviews = (
        merge_upload_metadata_into_reviews(platform, requested_profile_reviews)
        if isinstance(requested_profile_reviews, list) else []
    )
    saved_reviews = (
        merge_upload_metadata_into_reviews(platform, saved_profile_reviews)
        if isinstance(saved_profile_reviews, list) else []
    )
    requested_lookup, requested_order = build_profile_review_lookup(platform, requested_reviews)
    saved_lookup, saved_order = build_profile_review_lookup(platform, saved_reviews)

    if not requested_lookup:
        return saved_reviews
    if not saved_lookup:
        return requested_reviews

    merged_reviews = []
    seen_identifiers = set()
    for identifier in requested_order + saved_order:
        if not identifier or identifier in seen_identifiers:
            continue
        seen_identifiers.add(identifier)
        merged_reviews.append(requested_lookup.get(identifier) or saved_lookup.get(identifier))

    return [item for item in merged_reviews if isinstance(item, dict)]


def build_visual_results_lookup(visual_results):
    lookup = {}
    ordered_keys = []
    if not isinstance(visual_results, dict):
        return lookup, ordered_keys

    for key, review in visual_results.items():
        if not isinstance(review, dict):
            continue
        identifier = normalize_identifier(review.get("username") or key)
        if not identifier:
            continue
        if identifier not in lookup:
            ordered_keys.append(identifier)
        review_payload = dict(review)
        if not review_payload.get("username"):
            review_payload["username"] = key
        lookup[identifier] = review_payload

    return lookup, ordered_keys


def merge_saved_visual_results(requested_visual_results, saved_visual_results):
    requested_lookup, requested_order = build_visual_results_lookup(requested_visual_results)
    saved_lookup, saved_order = build_visual_results_lookup(saved_visual_results)

    if not requested_lookup:
        merged_lookup = saved_lookup
        ordered_identifiers = saved_order
    elif not saved_lookup:
        merged_lookup = requested_lookup
        ordered_identifiers = requested_order
    else:
        merged_lookup = dict(saved_lookup)
        merged_lookup.update(requested_lookup)
        ordered_identifiers = []
        for identifier in requested_order + saved_order:
            if identifier and identifier not in ordered_identifiers:
                ordered_identifiers.append(identifier)

    merged_results = {}
    for identifier in ordered_identifiers:
        review = merged_lookup.get(identifier)
        if not isinstance(review, dict):
            continue
        key = str(review.get("username") or identifier).strip() or identifier
        merged_results[key] = review
    return merged_results


def resolve_final_review_export_payload(platform, payload):
    requested_profile_reviews = payload.get("profile_reviews")
    requested_visual_results = payload.get("visual_results")

    if requested_profile_reviews is not None and not isinstance(requested_profile_reviews, list):
        raise ValueError("profile_reviews must be an array when provided")
    if requested_visual_results is not None and not isinstance(requested_visual_results, dict):
        raise ValueError("visual_results must be an object when provided")

    profile_review_artifact = load_latest_usable_profile_review_artifact(platform)
    visual_artifact = load_saved_visual_review_artifact(platform)
    resolved_profile_reviews = merge_saved_profile_reviews(
        platform,
        requested_profile_reviews or [],
        profile_review_artifact.get("profile_reviews") or [],
    )
    resolved_visual_results = merge_saved_visual_results(
        requested_visual_results or {},
        visual_artifact.get("visual_results") or {},
    )
    merged_metadata = merge_saved_artifact_metadata(profile_review_artifact, visual_artifact)

    return {
        "profile_reviews": resolved_profile_reviews,
        "visual_results": resolved_visual_results,
        "artifact_metadata": merged_metadata,
        **build_saved_final_review_artifact_status(
            platform,
            profile_review_artifact=profile_review_artifact,
            visual_artifact=visual_artifact,
        ),
    }


def build_test_info_json_payload(platform, profile_reviews, raw_items, metadata_lookup, raw_export_meta=None):
    raw_export_meta = raw_export_meta or {}
    merged_reviews = merge_upload_metadata_into_reviews(platform, profile_reviews)
    review_lookup, ordered_identifiers = build_profile_review_lookup(platform, merged_reviews)
    raw_items_by_identifier = {}

    for raw_item in raw_items or []:
        identifier = get_raw_item_identifier(platform, raw_item)
        if not identifier:
            continue
        if identifier not in raw_items_by_identifier:
            raw_items_by_identifier[identifier] = []
            if identifier not in review_lookup:
                ordered_identifiers.append(identifier)
        raw_items_by_identifier[identifier].append(raw_item)

    metadata_keys = list(metadata_lookup.keys()) if isinstance(metadata_lookup, dict) else []
    for identifier in metadata_keys:
        if identifier not in review_lookup and identifier not in raw_items_by_identifier:
            ordered_identifiers.append(identifier)

    profiles = []
    for identifier in ordered_identifiers:
        review_item = review_lookup.get(identifier)
        matched_raw_items = raw_items_by_identifier.get(identifier) or []
        first_raw_item = matched_raw_items[0] if matched_raw_items else {}
        context = build_audit_export_context(
            platform,
            review_item=review_item,
            metadata_lookup=metadata_lookup,
            preferred_identifier=identifier,
            raw_item=first_raw_item,
        )
        canonical_review_item = context["review_item"] if context["review_item"] else None

        profiles.append(sanitize_json_compatible({
            "identifier": context["identifier"],
            "username": context["username"],
            "account_id": context["account_id"],
            "profile_url": context["profile_url"],
            "source_filename": context["source_filename"],
            "raw_data_source": raw_export_meta.get("source") or "current",
            "raw_data_source_path": raw_export_meta.get("path") or "",
            "raw_data_source_updated_at": raw_export_meta.get("updated_at") or "",
            "status": (canonical_review_item or {}).get("status", ""),
            "reason": (canonical_review_item or {}).get("reason", ""),
            "review": canonical_review_item or None,
            "upload_metadata": context["metadata"] or None,
            "raw_item_count": len(matched_raw_items),
            "raw_items": matched_raw_items,
        }))

    return sanitize_json_compatible({
        "platform": platform,
        "exported_at": iso_now(),
        "raw_data": {
            "source": raw_export_meta.get("source") or "current",
            "path": raw_export_meta.get("path") or "",
            "updated_at": raw_export_meta.get("updated_at") or "",
            "used_fallback": bool(raw_export_meta.get("used_fallback")),
            "note": (
                "当前原始抓取为空，已回退到最近一次非空快照"
                if raw_export_meta.get("source") == "last_non_empty_snapshot"
                else "当前原始抓取为空，且无最近一次非空快照可回退"
                if raw_export_meta.get("source") == "unavailable"
                else ""
            ),
            "item_count": len(raw_items or []),
        },
        "profile_review_count": len(profile_reviews or []),
        "upload_metadata_count": len(metadata_lookup or {}),
        "profiles": profiles,
        "raw_items": raw_items or [],
    })


def build_test_info_summary_rows(platform, profile_reviews, raw_items, metadata_lookup):
    merged_reviews = merge_upload_metadata_into_reviews(platform, profile_reviews)
    review_lookup, ordered_identifiers = build_profile_review_lookup(platform, merged_reviews)
    raw_items_by_identifier = {}

    for raw_item in raw_items or []:
        identifier = get_raw_item_identifier(platform, raw_item)
        if not identifier:
            continue
        if identifier not in raw_items_by_identifier:
            raw_items_by_identifier[identifier] = []
            if identifier not in review_lookup:
                ordered_identifiers.append(identifier)
        raw_items_by_identifier[identifier].append(raw_item)

    rows = []
    for identifier in ordered_identifiers:
        review_item = review_lookup.get(identifier) or {}
        matched_raw_items = raw_items_by_identifier.get(identifier) or []
        first_raw_item = matched_raw_items[0] if matched_raw_items else {}
        row, context = build_audit_export_row_base(
            platform,
            review_item=review_item,
            metadata_lookup=metadata_lookup,
            preferred_identifier=identifier,
            raw_item=first_raw_item,
        )
        canonical_review_item = context["review_item"]
        row.update({
            'status': canonical_review_item.get('status', ''),
            'stage_status': (
                get_review_stage_label(canonical_review_item.get('status'), canonical_review_item.get('reason'))
                if canonical_review_item else 'raw_only'
            ),
            'reason': canonical_review_item.get('reason', ''),
            'latest_post_time': canonical_review_item.get('latest_post_time', ''),
            'soft_flags': format_soft_flags_for_export(canonical_review_item.get('soft_flags')),
            'cover_count': len(canonical_review_item.get('covers') or []),
            'raw_item_count': len(matched_raw_items),
            'returned_by_apify': 'Yes' if matched_raw_items else 'No',
        })
        rows.append(row)

    return rows


def build_test_info_raw_rows(platform, raw_items, profile_reviews, metadata_lookup, raw_export_meta=None):
    merged_reviews = merge_upload_metadata_into_reviews(platform, profile_reviews)
    review_lookup, _ = build_profile_review_lookup(platform, merged_reviews)
    rows = []
    raw_export_meta = raw_export_meta or {}
    raw_data_source = str(raw_export_meta.get("source") or "current").strip() or "current"
    raw_data_source_path = str(raw_export_meta.get("path") or "").strip()
    raw_data_source_updated_at = str(raw_export_meta.get("updated_at") or "").strip()
    raw_data_note = ''
    if raw_data_source == "last_non_empty_snapshot":
        raw_data_note = "当前原始抓取为空，已回退到最近一次非空快照"
    elif raw_data_source == "unavailable":
        raw_data_note = "当前原始抓取为空，且无最近一次非空快照可回退"

    if not raw_items:
        rows.append({
            'test_row_index': 1,
            'platform': platform,
            'identifier': '',
            'username': '',
            'profile_url': '',
            'source_filename': '',
            'matched_identifier': '',
            'matched_username': '',
            'matched_profile_url': '',
            'status': '',
            'review_status': '',
            'review_stage_status': 'raw_unavailable',
            'reason': '',
            'review_reason': '',
            'review_latest_post_time': '',
            'review_soft_flags': '',
            'review_cover_count': '',
            'raw_data_source': raw_data_source,
            'raw_data_source_path': raw_data_source_path,
            'raw_data_source_updated_at': raw_data_source_updated_at,
            'raw_data_note': raw_data_note,
        })
        return rows

    for index, raw_item in enumerate(raw_items or [], start=1):
        identifier = get_raw_item_identifier(platform, raw_item)
        review_item = review_lookup.get(identifier) or {}
        row, context = build_audit_export_row_base(
            platform,
            review_item=review_item,
            metadata_lookup=metadata_lookup,
            preferred_identifier=identifier,
            raw_item=raw_item,
        )
        canonical_review_item = context["review_item"]
        row.update({
            'test_row_index': index,
            'matched_identifier': identifier,
            'matched_username': get_raw_item_username(platform, raw_item),
            'matched_profile_url': get_raw_item_profile_url(platform, raw_item),
            'status': canonical_review_item.get('status', ''),
            'review_status': canonical_review_item.get('status', ''),
            'review_stage_status': (
                get_review_stage_label(canonical_review_item.get('status'), canonical_review_item.get('reason'))
                if canonical_review_item else 'raw_only'
            ),
            'reason': canonical_review_item.get('reason', ''),
            'review_reason': canonical_review_item.get('reason', ''),
            'review_latest_post_time': canonical_review_item.get('latest_post_time', ''),
            'review_soft_flags': format_soft_flags_for_export(canonical_review_item.get('soft_flags')),
            'review_cover_count': len(canonical_review_item.get('covers') or []),
            'raw_data_source': raw_data_source,
            'raw_data_source_path': raw_data_source_path,
            'raw_data_source_updated_at': raw_data_source_updated_at,
            'raw_data_note': raw_data_note,
        })

        sanitized_item = sanitize_json_compatible(raw_item)
        if isinstance(sanitized_item, dict):
            row.update(sanitized_item)
        else:
            row['raw_value'] = sanitized_item

        rows.append(row)

    return rows


def load_profile_reviews(platform):
    profile_reviews_path = get_profile_reviews_path(platform)
    if not os.path.exists(profile_reviews_path):
        return []

    try:
        with open(profile_reviews_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        reviews = data if isinstance(data, list) else []
        return merge_upload_metadata_into_reviews(platform, reviews)
    except Exception:
        return []


@app.route('/api/evaluate_influencer', methods=['POST'])
def evaluate_influencer():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username") or "").strip()
    cover_urls = payload.get("cover_urls") or []
    platform = payload.get("platform") or "tiktok"

    if not username:
        return jsonify({"success": False, "error": "username is required"}), 400
    if not isinstance(cover_urls, list) or len(cover_urls) == 0:
        return jsonify({"success": False, "error": "cover_urls must be a non-empty array"}), 400

    vision_config_error = validate_vision_runtime_config()
    if vision_config_error:
        return vision_config_error

    started_at = time.perf_counter()
    try:
        review = evaluate_cover_collage(username, cover_urls, platform=platform)
        elapsed = time.perf_counter() - started_at
        return jsonify({
            "success": True,
            "username": username,
            "model": OPENAI_MODEL,
            "provider": review.get("provider"),
            "elapsed_seconds": round(elapsed, 2),
            "decision": review["decision"],
            "reason": review["reason"],
            "signals": review["signals"],
            "raw_text": review["raw_text"],
            "cover_count": review["cover_count"],
            "collage_count": review.get("collage_count", 1),
        })
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except requests.RequestException as exc:
        return jsonify({"success": False, "error": f"Failed to download cover images: {exc}"}), 502
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "ok",
        "smoke_ready": True,
        "checks": {
            "apify": "configured" if get_apify_token() else "unconfigured",
            "vision": "configured" if get_available_vision_provider_names() else "unconfigured",
            "vision_providers": get_available_vision_provider_names(),
            "active_vision_provider": get_current_vision_provider_name() or None,
            "origins": BACKEND_ALLOWED_ORIGINS,
        },
    })


@app.route('/api/upload', methods=['POST'])
def upload_file():
    import pandas as pd

    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if file:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        try:
            frames = load_canonical_upload_workbook_frames(filepath)
            if not frames:
                return build_upload_validation_error(
                    "上传表没有可用数据行",
                    ["请确认至少有一个 sheet 包含表头和账号数据，且不要只上传空白页。"],
                )

            df = pd.concat(frames, ignore_index=True)
            parsed_upload, error_response = parse_canonical_upload_workbook(df, filename)
            if error_response:
                return error_response

            metadata_by_platform = parsed_upload["metadata_by_platform"]
            for platform_key in ('tiktok', 'instagram', 'youtube'):
                save_upload_metadata(platform_key, metadata_by_platform.get(platform_key, {}), replace=True)

            processed_filename = f"processed_{filename}"
            payload = sanitize_json_compatible({
                "success": True,
                "filename": processed_filename,
                "stats": parsed_upload["stats"],
                "preview": parsed_upload["preview"],
                "grouped_data": parsed_upload["grouped_data"],
                "metadata_counts": {
                    platform_key: len(metadata_by_platform.get(platform_key, {}))
                    for platform_key in ('tiktok', 'instagram', 'youtube')
                }
            })
            return app.response_class(
                response=json.dumps(payload, ensure_ascii=False, allow_nan=False),
                mimetype='application/json',
            )
            
        except Exception as e:
            return jsonify({"error": str(e)}), 500

# Persistent storage for scraped profiles
HISTORY_FILE = os.path.join(DATA_DIR, "scrape_history.json")

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_history(history):
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)

def update_history(platform, identifiers, status="success"):
    history = load_history()
    if platform not in history:
        history[platform] = {}
        
    now = datetime.now().isoformat()
    for ident in identifiers:
        history[platform][ident] = {
            "last_scraped": now,
            "status": status
        }
    save_history(history)

def filter_unscraped(platform, identifiers, days_limit=7):
    """
    Returns a list of identifiers that need to be scraped.
    Skips if scraped within `days_limit` days.
    """
    history = load_history()
    if platform not in history:
        return identifiers
        
    needed = []
    now = datetime.now()
    
    for ident in identifiers:
        if ident in history[platform]:
            last_scraped = datetime.fromisoformat(history[platform][ident]["last_scraped"])
            if (now - last_scraped).days < days_limit:
                continue # Skip recently scraped
        needed.append(ident)
        
    return needed

def get_apify_token():
    pool = get_apify_token_pool()
    if pool:
        pool_tokens = [item.get("token") for item in pool if item.get("token")]
        state = load_apify_token_state()
        current_token = str(state.get("current_token") or "").strip()
        if current_token in pool_tokens:
            return current_token
        return pool_tokens[0]
    return get_apify_auth_file_token()


def mask_apify_token(token):
    if not token:
        return ""
    return f"...{token[-5:]}"


def load_apify_token_state():
    try:
        with APIFY_TOKEN_STATE_LOCK:
            if not os.path.exists(APIFY_TOKEN_STATE_FILE):
                return {"tokens": {}, "budget_reservations": {}}
            with open(APIFY_TOKEN_STATE_FILE, 'r') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {"tokens": {}, "budget_reservations": {}}
            if not isinstance(data.get("tokens"), dict):
                data["tokens"] = {}
            if not isinstance(data.get("budget_reservations"), dict):
                data["budget_reservations"] = {}
            return data
    except Exception:
        return {"tokens": {}, "budget_reservations": {}}


def save_apify_token_state(state):
    try:
        with APIFY_TOKEN_STATE_LOCK:
            os.makedirs(os.path.dirname(APIFY_TOKEN_STATE_FILE), exist_ok=True)
            payload = dict(state or {})
            if not isinstance(payload.get("tokens"), dict):
                payload["tokens"] = {}
            if not isinstance(payload.get("budget_reservations"), dict):
                payload["budget_reservations"] = {}
            with open(APIFY_TOKEN_STATE_FILE, 'w') as f:
                json.dump(payload, f, indent=2)
            return True
    except Exception:
        return False


def load_apify_run_guard_state():
    try:
        with APIFY_RUN_GUARD_LOCK:
            if not os.path.exists(APIFY_RUN_GUARD_STATE_FILE):
                return {"guards": {}}
            with open(APIFY_RUN_GUARD_STATE_FILE, "r") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {"guards": {}}
            if not isinstance(data.get("guards"), dict):
                data["guards"] = {}
            return data
    except Exception:
        return {"guards": {}}


def save_apify_run_guard_state(state):
    try:
        with APIFY_RUN_GUARD_LOCK:
            os.makedirs(os.path.dirname(APIFY_RUN_GUARD_STATE_FILE), exist_ok=True)
            payload = dict(state or {})
            if not isinstance(payload.get("guards"), dict):
                payload["guards"] = {}
            with open(APIFY_RUN_GUARD_STATE_FILE, "w") as f:
                json.dump(payload, f, indent=2)
            return True
    except Exception:
        return False


def prune_apify_run_guards(state):
    guards = state.setdefault("guards", {})
    now_ts = time.time()
    stale_keys = []
    for guard_key, guard in guards.items():
        if not isinstance(guard, dict):
            stale_keys.append(guard_key)
            continue
        expires_at_ts = float(guard.get("expires_at_ts") or 0.0)
        if expires_at_ts and expires_at_ts <= now_ts:
            stale_keys.append(guard_key)

    for guard_key in stale_keys:
        guards.pop(guard_key, None)

    return stale_keys


def build_apify_run_guard_key(actor_id, output_filename, input_data):
    canonical_payload = {
        "actor_id": str(actor_id or "").strip(),
        "platform": str(output_filename or "").strip().lower(),
        "input": normalize_job_payload_for_signature(input_data or {}),
    }
    raw = json.dumps(canonical_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_apify_run_guard(guard_key):
    cleaned_key = str(guard_key or "").strip()
    if not cleaned_key:
        return None

    with APIFY_RUN_GUARD_LOCK:
        state = load_apify_run_guard_state()
        prune_apify_run_guards(state)
        guard = state.get("guards", {}).get(cleaned_key)
        save_apify_run_guard_state(state)
        return dict(guard) if isinstance(guard, dict) else None


def remember_apify_run_guard(
    guard_key,
    *,
    actor_id,
    output_filename,
    input_data,
    reason,
    token=None,
    run_id=None,
    dataset_id=None,
    status=None,
):
    cleaned_key = str(guard_key or "").strip()
    if not cleaned_key:
        return None

    guard = {
        "key": cleaned_key,
        "actor_id": str(actor_id or "").strip(),
        "platform": str(output_filename or "").strip().lower(),
        "input_identifiers": list(get_scrape_identifiers(output_filename, input_data) or []),
        "token": str(token or "").strip() or None,
        "token_masked": mask_apify_token(token),
        "run_id": str(run_id or "").strip() or None,
        "dataset_id": str(dataset_id or "").strip() or None,
        "status": str(status or "").strip() or None,
        "reason": str(reason or "").strip(),
        "created_at": iso_now(),
        "expires_at_ts": time.time() + APIFY_RUN_GUARD_TTL_SECONDS,
    }

    with APIFY_RUN_GUARD_LOCK:
        state = load_apify_run_guard_state()
        prune_apify_run_guards(state)
        state.setdefault("guards", {})[cleaned_key] = guard
        save_apify_run_guard_state(state)

    return guard


def clear_apify_run_guard(guard_key):
    cleaned_key = str(guard_key or "").strip()
    if not cleaned_key:
        return None

    with APIFY_RUN_GUARD_LOCK:
        state = load_apify_run_guard_state()
        guards = state.setdefault("guards", {})
        removed = guards.pop(cleaned_key, None)
        prune_apify_run_guards(state)
        save_apify_run_guard_state(state)
        return removed


def build_apify_run_guard_message(guard):
    if not isinstance(guard, dict):
        return "同一批次存在待人工确认的 Apify 提交记录，为避免重复扣费，系统已阻止自动再次提交。"

    run_id = str(guard.get("run_id") or "").strip()
    reason = str(guard.get("reason") or "").strip()
    if run_id:
        return (
            f"同一批次已有待人工确认的 Apify run（run_id: {run_id}）。"
            f"上次记录原因：{reason or '状态不确定'}。"
            f"为避免重复扣费，系统暂时阻止再次自动提交。"
        )
    return (
        f"同一批次上次提交状态不确定：{reason or '未拿到可确认的提交结果'}。"
        f"为避免重复扣费，系统暂时阻止再次自动提交。"
    )


def get_apify_env_tokens():
    candidates = []

    primary_token = os.getenv("APIFY_TOKEN") or os.getenv("APIFY_API_TOKEN")
    if primary_token and str(primary_token).strip():
        candidates.append(str(primary_token).strip())

    backup_tokens = os.getenv("APIFY_BACKUP_TOKENS") or os.getenv("APIFY_TOKENS")
    if backup_tokens:
        for token in str(backup_tokens).split(","):
            cleaned = token.strip()
            if cleaned:
                candidates.append(cleaned)

    deduped = []
    seen = set()
    for token in candidates:
        if token in seen:
            continue
        seen.add(token)
        deduped.append(token)
    return deduped


def split_apify_token_list(raw_value):
    tokens = []
    if raw_value is None:
        return tokens

    for token in str(raw_value).split(","):
        cleaned = token.strip()
        if cleaned:
            tokens.append(cleaned)
    return tokens


def get_apify_free_env_tokens():
    candidates = split_apify_token_list(os.getenv("APIFY_FREE_TOKENS"))
    deduped = []
    seen = set()
    for token in candidates:
        if token in seen:
            continue
        seen.add(token)
        deduped.append(token)
    return deduped


def get_apify_token_pool_strategy():
    strategy = str(os.getenv("APIFY_TOKEN_POOL_STRATEGY") or "paid_first_free_fallback").strip()
    if not strategy:
        return "paid_first_free_fallback"
    return strategy


def get_apify_free_token_hard_limit_usd():
    hard_limit = safe_positive_float(os.getenv("APIFY_FREE_TOKEN_HARD_LIMIT_USD"), 5.0)
    if hard_limit <= 0:
        return 5.0
    return round(hard_limit, 6)


def build_apify_token_descriptor(token, tier="paid", priority=0, hard_limit_usd=None):
    cleaned_token = str(token or "").strip()
    if not cleaned_token:
        return None

    cleaned_tier = "free" if str(tier or "").strip().lower() == "free" else "paid"
    descriptor = {
        "token": cleaned_token,
        "tier": cleaned_tier,
        "priority": int(priority or 0),
        "hard_limit_usd": None,
        "masked": mask_apify_token(cleaned_token),
    }
    if cleaned_tier == "free":
        descriptor["hard_limit_usd"] = get_apify_free_token_hard_limit_usd() if hard_limit_usd is None else round(
            safe_positive_float(hard_limit_usd, get_apify_free_token_hard_limit_usd()),
            6,
        )
    return descriptor


def get_apify_token_pool():
    strategy = get_apify_token_pool_strategy()
    if strategy != "paid_first_free_fallback":
        strategy = "paid_first_free_fallback"

    descriptors = []
    seen = set()

    def add_descriptor(token, tier, priority, hard_limit_usd=None):
        descriptor = build_apify_token_descriptor(
            token,
            tier=tier,
            priority=priority,
            hard_limit_usd=hard_limit_usd,
        )
        if not descriptor:
            return
        cleaned_token = descriptor["token"]
        if cleaned_token in seen:
            return
        seen.add(cleaned_token)
        descriptors.append(descriptor)

    paid_tokens = get_apify_env_tokens()
    free_tokens = get_apify_free_env_tokens()
    priority = 0

    for token in paid_tokens:
        add_descriptor(token, "paid", priority)
        priority += 1

    if not paid_tokens and not free_tokens:
        auth_token = get_apify_auth_file_token()
        add_descriptor(auth_token, "paid", priority)
        if auth_token:
            priority += 1

        state = load_apify_token_state()
        current_token = str(state.get("current_token") or "").strip()
        add_descriptor(current_token, "paid", priority)
        if current_token:
            priority += 1

        for token in (state.get("tokens") or {}).keys():
            add_descriptor(token, "paid", priority)
            if token:
                priority += 1

    if strategy == "paid_first_free_fallback":
        for token in free_tokens:
            add_descriptor(token, "free", priority, hard_limit_usd=get_apify_free_token_hard_limit_usd())
            priority += 1

    return descriptors


def get_apify_token_candidates():
    return [item.get("token") for item in get_apify_token_pool() if item.get("token")]


def set_apify_token(token):
    if not token:
        return False
    try:
        state = load_apify_token_state()
        state["current_token"] = token
        state["current_token_masked"] = mask_apify_token(token)
        tokens = state.setdefault("tokens", {})
        token_state = tokens.get(token, {})
        token_state["masked"] = mask_apify_token(token)
        tokens[token] = token_state
        state_saved = save_apify_token_state(state)

        env_tokens = get_apify_env_tokens()
        if env_tokens:
            return state_saved

        if not os.path.exists(APIFY_AUTH_FILE):
            return state_saved
        with open(APIFY_AUTH_FILE, 'r') as f:
            auth_payload = json.load(f)
        auth_payload['token'] = token
        with open(APIFY_AUTH_FILE, 'w') as f:
            json.dump(auth_payload, f, indent='\t')

        return state_saved
    except Exception:
        return False


def rotate_apify_token(tried_tokens=None):
    current_token = get_apify_token()
    pool = get_apify_token_candidates()
    tried_tokens = set(tried_tokens or [])

    if current_token in pool:
        current_index = pool.index(current_token)
        ordered_pool = pool[current_index + 1:] + pool[:current_index]
    else:
        ordered_pool = pool

    for candidate in ordered_pool:
        if not candidate or candidate == current_token or candidate in tried_tokens:
            continue
        if set_apify_token(candidate):
            print(f"[Apify] Token rotated: {mask_apify_token(current_token)} -> {mask_apify_token(candidate)}")
            return candidate
    return None


def get_apify_batch_size(platform, input_data=None):
    max_batch_size = max(1, APIFY_MAX_IDENTIFIERS_PER_BATCH.get(platform, 50))
    estimated_cost = estimate_apify_identifier_cost_usd(platform, input_data or {})
    if not isinstance(estimated_cost, (int, float)) or estimated_cost <= 0:
        return max_batch_size
    budget_batch_size = max(1, int(APIFY_SOFT_CREDIT_LIMIT_USD / float(estimated_cost)))
    return max(1, min(max_batch_size, budget_batch_size))


def get_apify_attempt_budget():
    token_pool_size = len(get_apify_token_candidates())
    return max(1, APIFY_MAX_BATCH_ATTEMPTS, token_pool_size)

def extract_returned_identifiers(platform, items):
    returned = set()
    if not isinstance(items, list):
        return returned

    for item in items:
        identifier = get_scrape_item_identifier(platform, item)
        if identifier:
            returned.add(identifier)
    return returned


def get_scrape_item_identifier(platform, item):
    if not isinstance(item, dict):
        return ''

    if platform == 'instagram':
        return (
            extract_platform_identifier_from_value(platform, item.get('username'))
            or extract_platform_identifier_from_value(platform, item.get('url'))
            or extract_platform_identifier_from_value(platform, item.get('inputUrl'))
        )

    if platform == 'tiktok':
        author_meta = item.get('authorMeta') or {}
        return (
            extract_platform_identifier_from_value(platform, author_meta.get('name'))
            or extract_platform_identifier_from_value(platform, author_meta.get('profileUrl'))
            or extract_platform_identifier_from_value(platform, item.get('webVideoUrl'))
            or extract_platform_identifier_from_value(platform, item.get('url'))
        )

    if platform == 'youtube':
        return (
            extract_platform_identifier_from_value(platform, item.get('channelUrl'))
            or extract_platform_identifier_from_value(platform, item.get('channelLink'))
            or extract_platform_identifier_from_value(platform, item.get('channelName'))
        )

    return ''


def get_scrape_item_key(platform, item):
    if not isinstance(item, dict):
        return json.dumps(item, sort_keys=True, ensure_ascii=False)

    if platform == 'instagram':
        identifier = (
            extract_platform_identifier_from_value(platform, item.get('username'))
            or extract_platform_identifier_from_value(platform, item.get('url'))
            or extract_platform_identifier_from_value(platform, item.get('inputUrl'))
        )
        return f"instagram::{identifier or item.get('id') or json.dumps(item, sort_keys=True, ensure_ascii=False)}"

    if platform == 'tiktok':
        author_meta = item.get('authorMeta') or {}
        author = (
            extract_platform_identifier_from_value(platform, author_meta.get('name'))
            or extract_platform_identifier_from_value(platform, author_meta.get('profileUrl'))
        )
        item_id = item.get('id') or item.get('awemeId') or item.get('videoId')
        fallback = f"{author}::{item.get('createTimeISO') or item.get('text') or ''}"
        return f"tiktok::{item_id or fallback}"

    if platform == 'youtube':
        return f"youtube::{item.get('id') or item.get('url') or item.get('channelUrl') or json.dumps(item, sort_keys=True, ensure_ascii=False)}"

    return json.dumps(item, sort_keys=True, ensure_ascii=False)


def merge_scrape_items(platform, existing_items, incoming_items):
    merged = []
    seen = set()

    for collection in (existing_items or [], incoming_items or []):
        for item in collection:
            item_key = get_scrape_item_key(platform, item)
            if item_key in seen:
                continue
            seen.add(item_key)
            merged.append(item)

    return merged


def dedupe_requested_identifiers(platform, identifiers):
    deduped = []
    seen = set()

    for value in identifiers or []:
        identifier = extract_platform_identifier_from_value(platform, value)
        if not identifier or identifier in seen:
            continue
        seen.add(identifier)
        deduped.append(value)

    return deduped


def filter_scrape_items_by_identifiers(platform, items, identifiers):
    requested_keys = {
        extract_platform_identifier_from_value(platform, value)
        for value in identifiers or []
        if extract_platform_identifier_from_value(platform, value)
    }
    if not requested_keys:
        return list(items or [])

    return [
        item for item in (items or [])
        if get_scrape_item_identifier(platform, item) in requested_keys
    ]


def build_missing_profile_review(platform, requested_identifier):
    identifier = extract_platform_identifier_from_value(platform, requested_identifier)
    username = identifier or normalize_identifier(requested_identifier) or str(requested_identifier or '').strip().lstrip('@')
    profile_url = build_canonical_profile_url(platform, username, requested_identifier)
    review = {
        "platform": platform,
        "username": username,
        "profile_url": profile_url,
        "status": "Missing",
        "reason": "采集器未返回该账号数据",
        "covers": [],
        "latest_post_time": None,
        "soft_flags": [],
        "stats": {},
        "upload_metadata": {},
    }
    return merge_upload_metadata_into_review_item(
        platform,
        review,
        preferred_identifier=identifier or requested_identifier,
    )


def merge_profile_reviews_for_requested_identifiers(platform, requested_identifiers, current_reviews, fallback_reviews=None):
    current_reviews = [
        normalize_profile_review_item(platform, item)
        for item in merge_upload_metadata_into_reviews(platform, current_reviews or [])
        if isinstance(item, dict)
    ]
    fallback_reviews = [
        normalize_profile_review_item(platform, item)
        for item in merge_upload_metadata_into_reviews(platform, fallback_reviews or [])
        if isinstance(item, dict)
    ]

    normalized_requested = dedupe_requested_identifiers(platform, requested_identifiers)
    if not normalized_requested:
        return current_reviews

    current_lookup = {}
    for item in current_reviews:
        identifier = resolve_profile_review_identifier(platform, item)
        if identifier and identifier not in current_lookup:
            current_lookup[identifier] = item

    fallback_lookup = {}
    for item in fallback_reviews:
        identifier = resolve_profile_review_identifier(platform, item)
        if identifier and identifier not in fallback_lookup:
            fallback_lookup[identifier] = item

    merged_reviews = []
    for requested_identifier in normalized_requested:
        identifier = extract_platform_identifier_from_value(platform, requested_identifier)
        review_item = (
            current_lookup.get(identifier)
            or fallback_lookup.get(identifier)
            or build_missing_profile_review(platform, requested_identifier)
        )
        merged_reviews.append(
            merge_upload_metadata_into_review_item(
                platform,
                review_item,
                preferred_identifier=identifier or requested_identifier,
            )
        )

    return merged_reviews


def build_cached_scrape_response(output_filename, output_file_path, skipped_count, progress_callback=None, requested_identifiers=None):
    raw_artifact = load_latest_usable_scrape_artifact(output_filename, output_file_path)
    cached_data = filter_scrape_items_by_identifiers(
        output_filename,
        raw_artifact.get("items") or [],
        requested_identifiers,
    )
    cached_profile_reviews = merge_profile_reviews_for_requested_identifiers(
        output_filename,
        requested_identifiers,
        load_profile_reviews(output_filename),
    )
    if not cached_data and not cached_profile_reviews:
        return None
    if output_filename == "tiktok" and cached_profile_reviews:
        schedule_tiktok_cover_cache_warm(output_filename, cached_data, cached_profile_reviews)
    if progress_callback:
        progress_callback("completed", "命中缓存，已返回最近结果", done=4, total=4)
    source_message = "最近一次采集结果"
    if raw_artifact.get("used_fallback"):
        source_message = "最近一次非空快照结果"
    requested_identifiers = dedupe_requested_identifiers(output_filename, requested_identifiers)
    successful_identifiers = [
        item.get("username")
        for item in cached_profile_reviews
        if isinstance(item, dict) and item.get("status") != "Missing"
    ]
    save_profile_reviews(
        output_filename,
        cached_profile_reviews,
        metadata={
            "cached": True,
            "stale_result": False,
            "used_fallback": bool(raw_artifact.get("used_fallback")),
            "raw_data_source": raw_artifact.get("source"),
            "source_path": raw_artifact.get("path") or output_file_path,
            "updated_at": iso_now(),
        },
    )
    response = {
        "success": True,
        "cached": True,
        "count": len(cached_data),
        "file": raw_artifact.get("path") or output_file_path,
        "profile_reviews": cached_profile_reviews,
        "requested_total": len(requested_identifiers) or len(cached_profile_reviews),
        "requested_identifiers": list(requested_identifiers or []),
        "successful_identifiers": successful_identifiers,
        "used_fallback": bool(raw_artifact.get("used_fallback")),
        "raw_data_source": raw_artifact.get("source"),
        "message": f"本次有 {skipped_count} 个账号命中缓存，当前展示的是{source_message}。勾选“强制刷新缓存”可重新采集。"
    }
    response.update(build_saved_final_review_artifact_status(output_filename))
    return response


def build_preserved_failure_response(output_filename, output_file_path, failed_batches, progress_callback=None, requested_identifiers=None):
    raw_artifact = load_latest_usable_scrape_artifact(output_filename, output_file_path)
    preserved_items = filter_scrape_items_by_identifiers(
        output_filename,
        raw_artifact.get("items") or [],
        requested_identifiers,
    )
    profile_reviews = merge_profile_reviews_for_requested_identifiers(
        output_filename,
        requested_identifiers,
        load_profile_reviews(output_filename),
    )
    if not preserved_items and not profile_reviews:
        return None
    if output_filename == "tiktok" and profile_reviews:
        schedule_tiktok_cover_cache_warm(output_filename, preserved_items, profile_reviews)

    message = (
        f"本次抓取失败，但已保留最近一次可用结果；当前展示的是"
        f"{'最近一次非空快照' if raw_artifact.get('used_fallback') else '最近一次成功采集'}。"
    )
    if failed_batches:
        message = f"{message} 当前共有 {len(failed_batches)} 个失败批次。"

    if progress_callback:
        progress_callback("completed", message, done=4, total=4, failed_count=len(failed_batches or []))

    save_profile_reviews(
        output_filename,
        profile_reviews,
        metadata={
            "cached": True,
            "stale_result": True,
            "used_fallback": bool(raw_artifact.get("used_fallback")),
            "raw_data_source": raw_artifact.get("source"),
            "source_path": raw_artifact.get("path") or output_file_path,
            "updated_at": iso_now(),
        },
    )
    response = {
        "success": True,
        "cached": True,
        "stale_result": True,
        "count": len(preserved_items),
        "file": raw_artifact.get("path") or output_file_path,
        "profile_reviews": profile_reviews,
        "requested_total": len(dedupe_requested_identifiers(output_filename, requested_identifiers)) or len(profile_reviews),
        "requested_identifiers": list(dedupe_requested_identifiers(output_filename, requested_identifiers)),
        "successful_identifiers": [
            item.get("username")
            for item in profile_reviews
            if isinstance(item, dict) and item.get("status") != "Missing"
        ],
        "failed_batches": list(failed_batches or []),
        "used_fallback": bool(raw_artifact.get("used_fallback")),
        "raw_data_source": raw_artifact.get("source"),
        "message": message,
    }
    response.update(build_saved_final_review_artifact_status(output_filename))
    return response

def chunk_list(items, chunk_size):
    if chunk_size <= 0:
        return [list(items)]
    return [items[idx:idx + chunk_size] for idx in range(0, len(items), chunk_size)]


def build_target_preview(identifiers, max_items=5):
    cleaned = [str(item).strip() for item in identifiers if str(item).strip()]
    if not cleaned:
        return {"current_targets": [], "current_target_count": 0}
    return {
        "current_targets": cleaned[:max_items],
        "current_target_count": len(cleaned),
    }


def safe_positive_float(value, default=0.0):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return float(default)
    return max(0.0, parsed)


def safe_positive_int(value, default=0):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return int(default)
    return max(0, parsed)


def build_apify_auth_headers(token):
    cleaned = str(token or "").strip()
    return {"Authorization": f"Bearer {cleaned}"} if cleaned else {}


def extract_apify_response_error(response):
    if response is None:
        return "unknown error"

    try:
        payload = response.json() or {}
    except ValueError:
        payload = {}

    if isinstance(payload.get("error"), dict):
        error_message = payload["error"].get("message") or payload["error"].get("type")
        if error_message:
            return str(error_message).strip()

    if payload.get("error"):
        return str(payload.get("error")).strip()

    text = str(getattr(response, "text", "") or "").strip()
    if text:
        return text
    return f"HTTP {getattr(response, 'status_code', 'unknown')}"


def get_apify_requested_results_per_identifier(platform, input_data):
    if platform == "tiktok":
        return max(1, safe_positive_int((input_data or {}).get("resultsPerPage"), 20))
    if platform == "youtube":
        return max(1, safe_positive_int((input_data or {}).get("maxResults"), 10))
    return 1


def estimate_apify_identifier_cost_usd(platform, input_data):
    per_identifier_cost = safe_positive_float(APIFY_ESTIMATED_COST_PER_IDENTIFIER_USD.get(platform), 0.0)
    per_result_cost = safe_positive_float(APIFY_ESTIMATED_COST_PER_RESULT_USD.get(platform), 0.0)
    requested_results = get_apify_requested_results_per_identifier(platform, input_data)
    if per_result_cost > 0 and requested_results > 0:
        per_identifier_cost = max(per_identifier_cost, requested_results * per_result_cost)
    return round(per_identifier_cost, 6)


def estimate_apify_request_cost_usd(platform, input_data, identifiers):
    cleaned_identifiers = [item for item in identifiers if str(item or "").strip()]
    if not cleaned_identifiers:
        return 0.0
    estimated_cost = estimate_apify_identifier_cost_usd(platform, input_data) * len(cleaned_identifiers)
    return round(estimated_cost, 6)


def apply_apify_budget_guard_band(estimated_cost_usd):
    guarded_cost = safe_positive_float(estimated_cost_usd, 0.0) * APIFY_BUDGET_SAFETY_MULTIPLIER
    guarded_cost += APIFY_BUDGET_BUFFER_USD
    return round(guarded_cost, 6)


def remember_apify_budget_snapshot(snapshot):
    token = str((snapshot or {}).get("token") or "").strip()
    if not token:
        return

    state = load_apify_token_state()
    tokens = state.setdefault("tokens", {})
    token_state = tokens.get(token, {})
    token_state.update({
        "masked": snapshot.get("masked") or mask_apify_token(token),
        "max_monthly_usage_usd": snapshot.get("max_monthly_usage_usd"),
        "monthly_usage_usd": snapshot.get("monthly_usage_usd"),
        "remaining_monthly_usage_usd": snapshot.get("remaining_monthly_usage_usd"),
        "monthly_usage_cycle_start_at": snapshot.get("monthly_usage_cycle_start_at"),
        "monthly_usage_cycle_end_at": snapshot.get("monthly_usage_cycle_end_at"),
        "budget_checked_at": snapshot.get("checked_at") or iso_now(),
    })
    tokens[token] = token_state
    save_apify_token_state(state)


def fetch_apify_budget_snapshot(token, cancel_check=None):
    cleaned_token = str(token or "").strip()
    if not cleaned_token:
        raise RuntimeError("缺少 Apify token，无法查询月额度。")

    response = apify_request(
        "GET",
        f"{APIFY_API_BASE}/users/me/limits",
        headers=build_apify_auth_headers(cleaned_token),
        cancel_check=cancel_check,
        retry_context="get account limits",
    )
    if response.status_code != 200:
        raise RuntimeError(f"查询 Apify 月额度失败：{extract_apify_response_error(response)}")

    payload = (response.json() or {}).get("data") or {}
    limits = payload.get("limits") or {}
    current = payload.get("current") or {}
    cycle = payload.get("monthlyUsageCycle") or {}
    max_monthly_usage_usd = safe_positive_float(limits.get("maxMonthlyUsageUsd"), 0.0)
    monthly_usage_usd = safe_positive_float(current.get("monthlyUsageUsd"), 0.0)
    snapshot = {
        "token": cleaned_token,
        "masked": mask_apify_token(cleaned_token),
        "max_monthly_usage_usd": round(max_monthly_usage_usd, 6),
        "monthly_usage_usd": round(monthly_usage_usd, 6),
        "remaining_monthly_usage_usd": round(max(0.0, max_monthly_usage_usd - monthly_usage_usd), 6),
        "monthly_usage_cycle_start_at": (
            cycle.get("startedAt")
            or cycle.get("startAt")
            or cycle.get("startDate")
            or current.get("monthlyUsageCycleStartedAt")
        ),
        "monthly_usage_cycle_end_at": (
            cycle.get("endsAt")
            or cycle.get("endAt")
            or cycle.get("endDate")
            or current.get("monthlyUsageCycleEndsAt")
        ),
        "checked_at": iso_now(),
    }
    remember_apify_budget_snapshot(snapshot)
    return snapshot


def prune_apify_budget_reservations(state):
    reservations = state.setdefault("budget_reservations", {})
    now_ts = time.time()
    stale_keys = []
    for reservation_key, reservation in reservations.items():
        if not isinstance(reservation, dict):
            stale_keys.append(reservation_key)
            continue
        expires_at_ts = float(reservation.get("expires_at_ts") or 0.0)
        if expires_at_ts and expires_at_ts <= now_ts:
            stale_keys.append(reservation_key)

    for reservation_key in stale_keys:
        reservations.pop(reservation_key, None)

    return stale_keys


def get_apify_reserved_budget_usd(token, state=None):
    cleaned_token = str(token or "").strip()
    if not cleaned_token:
        return 0.0

    payload = state or load_apify_token_state()
    prune_apify_budget_reservations(payload)
    reservations = payload.get("budget_reservations") or {}
    total = 0.0
    for reservation in reservations.values():
        if not isinstance(reservation, dict):
            continue
        if str(reservation.get("token") or "").strip() != cleaned_token:
            continue
        total += safe_positive_float(reservation.get("amount_usd"), 0.0)
    return round(total, 6)


def apply_apify_reserved_budget(snapshot, state=None):
    payload = dict(snapshot or {})
    token = str(payload.get("token") or "").strip()
    monthly_usage_usd = safe_positive_float(payload.get("monthly_usage_usd"), 0.0)
    remaining_budget_usd = safe_positive_float(payload.get("remaining_monthly_usage_usd"), 0.0)
    hard_limit_usd = payload.get("hard_limit_usd")
    hard_limit_remaining_usd = None
    if hard_limit_usd is not None:
        hard_limit_usd = round(safe_positive_float(hard_limit_usd, 0.0), 6)
        payload["hard_limit_usd"] = hard_limit_usd
        hard_limit_remaining_usd = round(max(0.0, hard_limit_usd - monthly_usage_usd), 6)
        payload["hard_limit_remaining_usd"] = hard_limit_remaining_usd
        remaining_budget_usd = min(remaining_budget_usd, hard_limit_remaining_usd)

    reserved_budget_usd = get_apify_reserved_budget_usd(token, state=state)
    payload["policy_remaining_monthly_usage_usd"] = round(remaining_budget_usd, 6)
    payload["reserved_budget_usd"] = reserved_budget_usd
    payload["effective_remaining_monthly_usage_usd"] = round(max(0.0, remaining_budget_usd - reserved_budget_usd), 6)
    return payload


def reserve_apify_budget(snapshot, amount_usd, reservation_key, metadata=None):
    cleaned_key = str(reservation_key or "").strip()
    cleaned_token = str((snapshot or {}).get("token") or "").strip()
    required_amount = safe_positive_float(amount_usd, 0.0)
    if not cleaned_key or not cleaned_token or required_amount <= 0:
        return {"success": False, "error": "预留 Apify 额度所需参数不完整。"}

    with APIFY_TOKEN_STATE_LOCK:
        state = load_apify_token_state()
        prune_apify_budget_reservations(state)
        reservations = state.setdefault("budget_reservations", {})
        existing = reservations.get(cleaned_key)
        if isinstance(existing, dict):
            existing_token = str(existing.get("token") or "").strip()
            existing_amount = safe_positive_float(existing.get("amount_usd"), 0.0)
            if existing_token == cleaned_token and abs(existing_amount - required_amount) < 1e-9:
                save_apify_token_state(state)
                return {"success": True, "reservation": dict(existing)}
            reservations.pop(cleaned_key, None)

        reserved_budget_usd = get_apify_reserved_budget_usd(cleaned_token, state=state)
        remaining_budget_usd = safe_positive_float((snapshot or {}).get("remaining_monthly_usage_usd"), 0.0)
        effective_remaining_usd = round(max(0.0, remaining_budget_usd - reserved_budget_usd), 6)
        if effective_remaining_usd + 1e-9 < required_amount:
            save_apify_token_state(state)
            return {
                "success": False,
                "error": (
                    f"{mask_apify_token(cleaned_token)} 当前可用额度仅 {effective_remaining_usd:.3f} USD，"
                    f"不足以为当前批次预留 {required_amount:.3f} USD。"
                ),
            }

        reservation = {
            "key": cleaned_key,
            "token": cleaned_token,
            "masked": mask_apify_token(cleaned_token),
            "amount_usd": round(required_amount, 6),
            "created_at": iso_now(),
            "expires_at_ts": time.time() + APIFY_BUDGET_RESERVATION_TTL_SECONDS,
            "metadata": metadata or {},
        }
        reservations[cleaned_key] = reservation
        save_apify_token_state(state)
        return {"success": True, "reservation": reservation}


def release_apify_budget_reservation(reservation_key):
    cleaned_key = str(reservation_key or "").strip()
    if not cleaned_key:
        return None

    with APIFY_TOKEN_STATE_LOCK:
        state = load_apify_token_state()
        reservations = state.setdefault("budget_reservations", {})
        released = reservations.pop(cleaned_key, None)
        prune_apify_budget_reservations(state)
        save_apify_token_state(state)
        return released


def get_ordered_apify_token_candidates(preferred_tokens=None):
    return [item.get("token") for item in get_ordered_apify_token_pool(preferred_tokens=preferred_tokens)]


def get_ordered_apify_token_pool(preferred_tokens=None):
    pool = list(get_apify_token_pool())
    ordered = []
    added = set()

    for token in preferred_tokens or []:
        cleaned = str(token or "").strip()
        if not cleaned or cleaned in added:
            continue
        descriptor = next((item for item in pool if item.get("token") == cleaned), None)
        if descriptor is None:
            continue
        ordered.append(descriptor)
        added.add(cleaned)

    for descriptor in pool:
        token = descriptor.get("token")
        if not token or token in added:
            continue
        ordered.append(descriptor)
        added.add(token)

    return ordered


def collect_apify_budget_snapshots(cancel_check=None, preferred_tokens=None):
    snapshots = []
    errors = []

    for descriptor in get_ordered_apify_token_pool(preferred_tokens=preferred_tokens):
        candidate = descriptor.get("token")
        if cancel_check and cancel_check():
            raise RuntimeError("用户取消")
        try:
            snapshot = fetch_apify_budget_snapshot(candidate, cancel_check=cancel_check)
            snapshot["tier"] = descriptor.get("tier")
            snapshot["priority"] = descriptor.get("priority")
            snapshot["hard_limit_usd"] = descriptor.get("hard_limit_usd")
            snapshot["masked"] = descriptor.get("masked") or snapshot.get("masked")
            snapshots.append(snapshot)
        except Exception as exc:
            errors.append(f"{mask_apify_token(candidate)}: {exc}")

    return snapshots, errors


def normalize_apify_batch_plan_inputs(identifiers_or_batches):
    if not identifiers_or_batches:
        return []

    first_item = identifiers_or_batches[0]
    if isinstance(first_item, (list, tuple, set)):
        normalized_batches = []
        for batch in identifiers_or_batches:
            cleaned_batch = [item for item in batch if str(item or "").strip()]
            if cleaned_batch:
                normalized_batches.append(cleaned_batch)
        return normalized_batches

    cleaned_batch = [item for item in identifiers_or_batches if str(item or "").strip()]
    return [cleaned_batch] if cleaned_batch else []


def plan_apify_token_batches(
    platform,
    input_data,
    identifiers_or_batches,
    cancel_check=None,
    preferred_tokens=None,
    snapshots=None,
    state=None,
):
    normalized_batches = normalize_apify_batch_plan_inputs(identifiers_or_batches)
    if not normalized_batches:
        return {
            "success": False,
            "planned_batches": [],
            "failed_batches": [],
            "snapshots": [],
            "lookup_errors": [],
        }

    snapshot_errors = []
    source_snapshots = snapshots
    if source_snapshots is None:
        source_snapshots, snapshot_errors = collect_apify_budget_snapshots(
            cancel_check=cancel_check,
            preferred_tokens=preferred_tokens,
        )
    if not source_snapshots:
        return {
            "success": False,
            "planned_batches": [],
            "failed_batches": [
                {
                    "batch_index": 1,
                    "identifiers": normalized_batches[0],
                    "error": "没有可用 token",
                }
            ],
            "snapshots": [],
            "lookup_errors": snapshot_errors,
        }

    state = state or load_apify_token_state()
    effective_snapshots = [apply_apify_reserved_budget(item, state=state) for item in source_snapshots]
    planning_slots = []
    for snapshot in effective_snapshots:
        planning_slots.append({
            "token": str(snapshot.get("token") or "").strip(),
            "snapshot": snapshot,
            "available_budget_usd": safe_positive_float(
                snapshot.get("effective_remaining_monthly_usage_usd"),
                0.0,
            ),
        })

    planned_batches = []
    failed_batches = []
    for batch_index, batch_identifiers in enumerate(normalized_batches, start=1):
        estimated_cost_usd = estimate_apify_request_cost_usd(platform, input_data, batch_identifiers)
        required_budget_usd = apply_apify_budget_guard_band(estimated_cost_usd)
        candidate_tokens = []

        for slot in planning_slots:
            available_budget_usd = safe_positive_float(slot.get("available_budget_usd"), 0.0)
            if available_budget_usd + 1e-9 < required_budget_usd:
                continue
            candidate_tokens.append({
                "token": slot.get("token"),
                "snapshot": slot.get("snapshot"),
                "available_budget_usd": round(available_budget_usd, 6),
            })

        if not candidate_tokens:
            failed_batches.append({
                "batch_index": batch_index,
                "identifiers": list(batch_identifiers),
                "estimated_cost_usd": estimated_cost_usd,
                "required_budget_usd": required_budget_usd,
            })
            continue

        selected_token = candidate_tokens[0]
        selected_slot = next(
            (slot for slot in planning_slots if slot.get("token") == selected_token.get("token")),
            None,
        )
        if selected_slot is not None:
            selected_slot["available_budget_usd"] = round(
                max(0.0, safe_positive_float(selected_slot.get("available_budget_usd"), 0.0) - required_budget_usd),
                6,
            )

        planned_batches.append({
            "batch_index": batch_index,
            "identifiers": list(batch_identifiers),
            "token": selected_token.get("token"),
            "snapshot": selected_token.get("snapshot"),
            "estimated_cost_usd": estimated_cost_usd,
            "required_budget_usd": required_budget_usd,
            "candidate_tokens": candidate_tokens,
        })

    return {
        "success": len(failed_batches) == 0,
        "planned_batches": planned_batches,
        "failed_batches": failed_batches,
        "snapshots": effective_snapshots,
        "lookup_errors": snapshot_errors,
    }


def build_apify_budget_failure(platform, identifiers, input_data, estimated_cost_usd, required_budget_usd, snapshots, scope):
    cleaned_identifiers = [item for item in identifiers if str(item or "").strip()]
    total_available = round(sum(
        safe_positive_float(
            item.get("effective_remaining_monthly_usage_usd", item.get("remaining_monthly_usage_usd")),
            0.0,
        )
        for item in snapshots
    ), 6)
    max_available = round(max([
        safe_positive_float(
            item.get("effective_remaining_monthly_usage_usd", item.get("remaining_monthly_usage_usd")),
            0.0,
        )
        for item in snapshots
    ] or [0.0]), 6)
    per_identifier_cost = estimate_apify_identifier_cost_usd(platform, input_data)
    requested_results = get_apify_requested_results_per_identifier(platform, input_data)
    platform_label = {"tiktok": "TikTok", "instagram": "Instagram", "youtube": "YouTube"}.get(platform, platform)
    target_hint = "请减少本次账号数量或降低单账号抓取上限后重试。"
    if platform == "instagram":
        target_hint = "请减少本次账号数量后重试。"

    error_message = (
        f"Apify 月额度不足：{platform_label} 本次{scope}预计消耗约 {estimated_cost_usd:.3f} USD，"
        f"按安全系数需预留 {required_budget_usd:.3f} USD，但当前可用 token 总剩余额度仅 {total_available:.3f} USD。"
        f"{target_hint}"
    )
    return {
        "success": False,
        "error_code": "APIFY_MONTHLY_BUDGET_EXCEEDED",
        "error": error_message,
        "message": error_message,
        "details": [
            f"平台：{platform_label}",
            f"目标数量：{len(cleaned_identifiers)}",
            f"单目标预估费用：{per_identifier_cost:.3f} USD",
            f"单目标结果上限：{requested_results}",
            f"本次预估费用：{estimated_cost_usd:.3f} USD",
            f"安全预留后所需额度：{required_budget_usd:.3f} USD",
            f"当前单 token 最多剩余：{max_available:.3f} USD",
            f"当前全部 token 总剩余：{total_available:.3f} USD",
        ],
        "budget": {
            "platform": platform,
            "estimated_cost_usd": estimated_cost_usd,
            "required_budget_usd": required_budget_usd,
            "available_budget_usd": total_available,
            "max_token_budget_usd": max_available,
            "target_count": len(cleaned_identifiers),
            "requested_results_per_identifier": requested_results,
            "tokens": [
                {
                    "masked": item.get("masked"),
                    "tier": item.get("tier"),
                    "hard_limit_usd": item.get("hard_limit_usd"),
                    "hard_limit_remaining_usd": item.get("hard_limit_remaining_usd"),
                    "policy_remaining_monthly_usage_usd": item.get("policy_remaining_monthly_usage_usd"),
                    "remaining_monthly_usage_usd": item.get("remaining_monthly_usage_usd"),
                    "effective_remaining_monthly_usage_usd": item.get("effective_remaining_monthly_usage_usd"),
                    "reserved_budget_usd": item.get("reserved_budget_usd"),
                    "max_monthly_usage_usd": item.get("max_monthly_usage_usd"),
                    "monthly_usage_usd": item.get("monthly_usage_usd"),
                    "monthly_usage_cycle_end_at": item.get("monthly_usage_cycle_end_at"),
                }
                for item in snapshots
            ],
        },
    }


def ensure_apify_budget_for_request(platform, input_data, identifiers, cancel_check=None, progress_callback=None):
    cleaned_identifiers = [item for item in identifiers if str(item or "").strip()]
    if not cleaned_identifiers:
        return {"success": True, "estimated_cost_usd": 0.0, "required_budget_usd": 0.0, "snapshots": []}

    if progress_callback:
        progress_callback(
            "preparing",
            "正在检查 Apify 月额度",
            done=0,
            total=4,
            **build_target_preview(cleaned_identifiers),
        )

    estimated_cost_usd = estimate_apify_request_cost_usd(platform, input_data, cleaned_identifiers)
    required_budget_usd = apply_apify_budget_guard_band(estimated_cost_usd)
    snapshots, snapshot_errors = collect_apify_budget_snapshots(cancel_check=cancel_check)
    if not snapshots:
        joined_errors = "；".join(snapshot_errors) if snapshot_errors else "没有可用 token"
        error_message = f"无法查询 Apify 月额度，已阻止本次采集启动：{joined_errors}"
        return {
            "success": False,
            "error_code": "APIFY_BUDGET_LOOKUP_FAILED",
            "error": error_message,
            "message": error_message,
            "details": snapshot_errors,
        }

    state = load_apify_token_state()
    effective_snapshots = [apply_apify_reserved_budget(item, state=state) for item in snapshots]
    total_available = sum(
        safe_positive_float(item.get("effective_remaining_monthly_usage_usd"), 0.0)
        for item in effective_snapshots
    )
    if total_available + 1e-9 < required_budget_usd:
        return build_apify_budget_failure(
            platform,
            cleaned_identifiers,
            input_data,
            estimated_cost_usd,
            required_budget_usd,
            effective_snapshots,
            "请求",
        )

    return {
        "success": True,
        "estimated_cost_usd": estimated_cost_usd,
        "required_budget_usd": required_budget_usd,
        "snapshots": effective_snapshots,
        "lookup_errors": snapshot_errors,
    }


def ensure_apify_budget_for_run(
    platform,
    input_data,
    identifiers,
    cancel_check=None,
    reservation_key=None,
    reservation_metadata=None,
    preferred_tokens=None,
):
    cleaned_identifiers = [item for item in identifiers if str(item or "").strip()]
    if not cleaned_identifiers:
        return {"success": False, "error": "当前批次没有可执行的目标。"}

    snapshots, snapshot_errors = collect_apify_budget_snapshots(
        cancel_check=cancel_check,
        preferred_tokens=preferred_tokens,
    )
    if not snapshots:
        joined_errors = "；".join(snapshot_errors) if snapshot_errors else "没有可用 token"
        error_message = f"无法查询 Apify 月额度，已阻止当前批次执行：{joined_errors}"
        return {
            "success": False,
            "error_code": "APIFY_BUDGET_LOOKUP_FAILED",
            "error": error_message,
            "message": error_message,
            "details": snapshot_errors,
        }

    state = load_apify_token_state()
    effective_snapshots = [apply_apify_reserved_budget(item, state=state) for item in snapshots]
    plan_result = plan_apify_token_batches(
        platform,
        input_data,
        [cleaned_identifiers],
        snapshots=snapshots,
        state=state,
    )
    planned_batches = plan_result.get("planned_batches") or []
    if not planned_batches:
        estimated_cost_usd = estimate_apify_request_cost_usd(platform, input_data, cleaned_identifiers)
        required_budget_usd = apply_apify_budget_guard_band(estimated_cost_usd)
        return build_apify_budget_failure(
            platform,
            cleaned_identifiers,
            input_data,
            estimated_cost_usd,
            required_budget_usd,
            effective_snapshots,
            "批次",
        )

    batch_plan = planned_batches[0]
    estimated_cost_usd = batch_plan.get("estimated_cost_usd")
    required_budget_usd = batch_plan.get("required_budget_usd")

    for candidate in batch_plan.get("candidate_tokens") or []:
        snapshot = candidate.get("snapshot") or {}
        selected_token = str(candidate.get("token") or snapshot.get("token") or "").strip()
        if not selected_token:
            continue

        reservation = None
        if reservation_key:
            reservation_result = reserve_apify_budget(
                snapshot,
                required_budget_usd,
                reservation_key,
                metadata=reservation_metadata,
            )
            if not reservation_result.get("success"):
                continue
            reservation = reservation_result.get("reservation")
        return {
            "success": True,
            "token": selected_token,
            "snapshot": snapshot,
            "estimated_cost_usd": estimated_cost_usd,
            "required_budget_usd": required_budget_usd,
            "lookup_errors": snapshot_errors,
            "reservation": reservation,
            "plan": batch_plan,
        }

    refreshed_state = load_apify_token_state()
    refreshed_snapshots = [apply_apify_reserved_budget(item, state=refreshed_state) for item in snapshots]
    return build_apify_budget_failure(
        platform,
        cleaned_identifiers,
        input_data,
        estimated_cost_usd,
        required_budget_usd,
        refreshed_snapshots,
        "批次",
    )


def translate_apify_status(status):
    status_map = {
        "SUCCEEDED": "已成功",
        "RUNNING": "运行中",
        "READY": "排队中",
        "FAILED": "失败",
        "ABORTED": "已中止",
        "TIMED-OUT": "超时",
        "PARTIAL": "部分成功",
    }
    return status_map.get(status, status or "未知状态")


def is_apify_terminal_status(status):
    return str(status or "").strip().upper() in {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}


def build_apify_progress_metadata(run_id=None, dataset_id=None, status=None, safe_to_retry=False, **extra):
    payload = {"safe_to_retry": bool(safe_to_retry)}
    if run_id:
        payload["apify_run_id"] = run_id
    if dataset_id:
        payload["apify_dataset_id"] = dataset_id
    if status:
        payload["apify_status"] = status
        payload["apify_status_text"] = translate_apify_status(status)
    if extra:
        payload.update(extra)
    return payload


def poll_apify_run_until_terminal(
    token,
    run_id,
    *,
    cancel_check=None,
    progress_callback=None,
    progress_stage="provider_running",
    progress_message=None,
    progress_payload=None,
    max_wait_seconds=None,
):
    status_url = f"{APIFY_API_BASE}/actor-runs/{run_id}"
    started_polling_at = time.monotonic()
    last_run_data = {}

    while True:
        if cancel_check and cancel_check():
            return {"cancelled": True}

        try:
            status_resp = apify_request(
                "GET",
                status_url,
                params={"token": token},
                cancel_check=cancel_check,
                retry_context=f"poll run {run_id}",
            )
        except requests.RequestException as exc:
            return {
                "success": False,
                "terminal": False,
                "recoverable": True,
                "error": f"获取运行状态异常：{exc}",
                "run_data": last_run_data,
            }

        if status_resp.status_code != 200:
            return {
                "success": False,
                "terminal": False,
                "recoverable": True,
                "error": f"获取运行状态失败：{extract_apify_response_error(status_resp)}",
                "run_data": last_run_data,
            }

        last_run_data = (status_resp.json() or {}).get("data") or {}
        final_status = last_run_data.get("status")
        default_dataset_id = last_run_data.get("defaultDatasetId")

        if final_status == "SUCCEEDED":
            return {
                "success": True,
                "terminal": True,
                "status": final_status,
                "run_data": last_run_data,
                "dataset_id": default_dataset_id,
            }

        if final_status in {"FAILED", "ABORTED", "TIMED-OUT"}:
            return {
                "success": False,
                "terminal": True,
                "status": final_status,
                "run_data": last_run_data,
                "dataset_id": default_dataset_id,
                "error": f"远端 run 已结束：{translate_apify_status(final_status)}",
            }

        if progress_callback:
            payload = dict(progress_payload or {})
            payload.update(
                build_apify_progress_metadata(
                    run_id=run_id,
                    dataset_id=default_dataset_id,
                    status=final_status,
                    safe_to_retry=False,
                )
            )
            progress_callback(
                progress_stage,
                progress_message or f"Apify 运行中：{translate_apify_status(final_status)}",
                **payload,
            )

        if max_wait_seconds is not None and (time.monotonic() - started_polling_at) >= max_wait_seconds:
            return {
                "success": False,
                "terminal": False,
                "recoverable": True,
                "timed_out": True,
                "status": final_status,
                "run_data": last_run_data,
                "dataset_id": default_dataset_id,
            }

        time.sleep(APIFY_POLL_INTERVAL_SECONDS)


def download_apify_dataset_items(token, dataset_id, *, cancel_check=None):
    dataset_url = f"{APIFY_API_BASE}/datasets/{dataset_id}/items"

    try:
        dataset_resp = apify_request(
            "GET",
            dataset_url,
            params={"token": token},
            cancel_check=cancel_check,
            retry_context=f"download dataset {dataset_id}",
        )
    except requests.RequestException as exc:
        return {
            "success": False,
            "recoverable": True,
            "error": f"下载数据集异常：{exc}",
        }

    if dataset_resp.status_code != 200:
        return {
            "success": False,
            "recoverable": True,
            "error": f"下载数据集失败：{extract_apify_response_error(dataset_resp)}",
        }

    return {
        "success": True,
        "items": dataset_resp.json(),
    }


def recover_guarded_apify_run(
    actor_id,
    input_data,
    output_filename,
    output_file_path,
    identifiers,
    original_identifiers,
    skipped_count,
    guard,
    *,
    progress_callback=None,
    cancel_check=None,
):
    if not isinstance(guard, dict):
        return None

    run_id = str(guard.get("run_id") or "").strip()
    dataset_id = str(guard.get("dataset_id") or "").strip()
    token = str(guard.get("token") or "").strip()
    if not run_id or not dataset_id or not token:
        return None

    run_guard_key = build_apify_run_guard_key(actor_id, output_filename, input_data)
    base_progress_payload = build_target_preview(identifiers)

    if progress_callback:
        progress_callback(
            "recovering_remote_run",
            "检测到已有远端 Apify run，正在尝试恢复结果",
            done=1,
            total=4,
            **base_progress_payload,
            **build_apify_progress_metadata(
                run_id=run_id,
                dataset_id=dataset_id,
                status=guard.get("status"),
                safe_to_retry=False,
            ),
        )

    recovery_stage = "recovering_remote_run"
    waiting_started = False
    while True:
        poll_result = poll_apify_run_until_terminal(
            token,
            run_id,
            cancel_check=cancel_check,
            progress_callback=progress_callback,
            progress_stage=recovery_stage,
            progress_message=(
                "正在恢复已有远端 Apify run"
                if recovery_stage == "recovering_remote_run"
                else "远端 Apify run 仍在运行，继续等待恢复结果"
            ),
            progress_payload={
                "done": 1,
                "total": 4,
                **base_progress_payload,
            },
            max_wait_seconds=max(APIFY_MIN_WAIT_SECONDS, min(APIFY_MAX_WAIT_SECONDS, max(1, len(identifiers)) * 45)) if not waiting_started else None,
        )

        if poll_result.get("cancelled"):
            return build_cancelled_result()

        run_data = poll_result.get("run_data") or {}
        current_status = poll_result.get("status") or run_data.get("status")
        dataset_id = str(poll_result.get("dataset_id") or run_data.get("defaultDatasetId") or dataset_id).strip()

        if poll_result.get("success"):
            while True:
                if progress_callback:
                    progress_callback(
                        "downloading",
                        "正在下载已恢复的 Apify 数据集结果",
                        done=2,
                        total=4,
                        **base_progress_payload,
                        **build_apify_progress_metadata(
                            run_id=run_id,
                            dataset_id=dataset_id,
                            status=current_status or "SUCCEEDED",
                            safe_to_retry=False,
                        ),
                    )
                if cancel_check and cancel_check():
                    return build_cancelled_result()

                dataset_result = download_apify_dataset_items(token, dataset_id, cancel_check=cancel_check)
                if dataset_result.get("success"):
                    items = dataset_result.get("items")
                    with open(output_file_path, 'w', encoding='utf-8') as f:
                        json.dump(items, f, indent=2, ensure_ascii=False)

                    apify_summary = build_apify_run_summary(
                        actor_id,
                        "rest",
                        run_data,
                        cost_available=True,
                    )
                    result = finalize_apify_output(
                        output_filename,
                        output_file_path,
                        identifiers,
                        skipped_count,
                        progress_callback,
                        apify_summary=apify_summary,
                        requested_identifiers=original_identifiers,
                    )
                    if result.get("success"):
                        result["raw_items"] = items
                        clear_apify_run_guard(run_guard_key)
                    return result

                remember_apify_run_guard(
                    run_guard_key,
                    actor_id=actor_id,
                    output_filename=output_filename,
                    input_data=input_data,
                    reason=dataset_result.get("error") or "下载已恢复数据集失败",
                    token=token,
                    run_id=run_id,
                    dataset_id=dataset_id,
                    status=current_status or "SUCCEEDED",
                )
                recovery_stage = "waiting_remote_run"
                waiting_started = True
                if progress_callback:
                    progress_callback(
                        "waiting_remote_run",
                        dataset_result.get("error") or "已恢复 run 成功结束，但暂时还拿不到数据集，继续等待",
                        done=1,
                        total=4,
                        **base_progress_payload,
                        **build_apify_progress_metadata(
                            run_id=run_id,
                            dataset_id=dataset_id,
                            status=current_status or "SUCCEEDED",
                            safe_to_retry=False,
                        ),
                    )
                time.sleep(APIFY_POLL_INTERVAL_SECONDS)

        if poll_result.get("terminal"):
            clear_apify_run_guard(run_guard_key)
            return build_apify_non_retryable_run_failure(
                actor_id,
                output_filename,
                token,
                run_id,
                dataset_id,
                poll_result.get("error") or f"远端 run 已结束：{translate_apify_status(current_status)}",
                run_data=run_data,
                error_code="APIFY_REMOTE_RUN_FAILED",
                status=current_status,
            )

        waited_seconds = None
        if poll_result.get("timed_out"):
            waited_seconds = max(APIFY_MIN_WAIT_SECONDS, min(APIFY_MAX_WAIT_SECONDS, max(1, len(identifiers)) * 45))
        remember_apify_run_guard(
            run_guard_key,
            actor_id=actor_id,
            output_filename=output_filename,
            input_data=input_data,
            reason=(
                f"远端 run 仍在恢复中，已切换到持续等待模式。"
                if poll_result.get("timed_out")
                else (poll_result.get("error") or "远端 run 仍在运行，继续等待")
            ),
            token=token,
            run_id=run_id,
            dataset_id=dataset_id,
            status=current_status,
        )
        recovery_stage = "waiting_remote_run"
        waiting_started = True
        if progress_callback:
            progress_callback(
                "waiting_remote_run",
                (
                    f"远端 Apify run 仍在运行，继续等待恢复结果"
                    if waited_seconds is None
                    else f"本地等待约 {waited_seconds} 秒后仍未结束，继续等待远端 run"
                ),
                done=1,
                total=4,
                **base_progress_payload,
                **build_apify_progress_metadata(
                    run_id=run_id,
                    dataset_id=dataset_id,
                    status=current_status,
                    safe_to_retry=False,
                ),
            )

def build_apify_cost_summary_text(cost_available, usage_total_usd, execution_method, note=None):
    if note:
        return note
    if cost_available and isinstance(usage_total_usd, (int, float)):
        return f"本次 Apify 预估费用：{round(float(usage_total_usd), 6)} 美元。"
    if execution_method == "cli":
        return "当前 CLI 执行路径暂未返回单次运行费用。"
    return "本次 Apify 运行已完成，但暂未返回费用数据。"


def apify_request(
    method,
    url,
    *,
    cancel_check=None,
    timeout=APIFY_REQUEST_TIMEOUT,
    retry_context=None,
    allow_retries=True,
    **kwargs,
):
    last_exception = None
    last_response = None
    attempt_budget = APIFY_HTTP_RETRY_ATTEMPTS if allow_retries else 1

    for attempt in range(1, attempt_budget + 1):
        if cancel_check and cancel_check():
            raise RuntimeError("用户取消")

        try:
            response = requests.request(
                method,
                url,
                timeout=timeout,
                **kwargs,
            )
        except requests.RequestException as exc:
            last_exception = exc
            if attempt >= attempt_budget:
                raise
            print(
                f"[Apify] {retry_context or method.upper()} request exception "
                f"(attempt {attempt}/{attempt_budget}): {exc}"
            )
        else:
            if response.status_code not in APIFY_TRANSIENT_STATUS_CODES:
                return response

            last_response = response
            if attempt >= attempt_budget:
                return response
            print(
                f"[Apify] {retry_context or method.upper()} transient status "
                f"{response.status_code} (attempt {attempt}/{attempt_budget})"
            )

        time.sleep(APIFY_HTTP_RETRY_BACKOFF_SECONDS * attempt)

    if last_response is not None:
        return last_response
    if last_exception is not None:
        raise last_exception
    raise RuntimeError(f"Apify request failed without response ({retry_context or method.upper()})")


def build_apify_run_summary(actor_id, execution_method, run_data=None, cost_available=False, note=None):
    run_data = run_data or {}
    status = run_data.get("status")
    usage_total_usd = run_data.get("usageTotalUsd")
    return {
        "actor_id": actor_id,
        "execution_method": execution_method,
        "run_id": run_data.get("id"),
        "status": status,
        "status_text": translate_apify_status(status),
        "dataset_id": run_data.get("defaultDatasetId"),
        "usage_total_usd": usage_total_usd,
        "usage_usd": run_data.get("usageUsd"),
        "charged_event_counts": run_data.get("chargedEventCounts"),
        "pricing_info": run_data.get("pricingInfo"),
        "cost_available": cost_available,
        "note": note,
        "summary_text": build_apify_cost_summary_text(cost_available, usage_total_usd, execution_method, note),
    }


def log_apify_run_summary(platform, apify_summary):
    if not isinstance(apify_summary, dict):
        return

    print(
        "[Apify费用]",
        json.dumps(
            {
                "平台": platform,
                "Actor": apify_summary.get("actor_id"),
                "执行方式": apify_summary.get("execution_method"),
                "运行ID": apify_summary.get("run_id"),
                "运行状态": apify_summary.get("status_text") or apify_summary.get("status"),
                "本次预估费用(USD)": apify_summary.get("usage_total_usd"),
                "费用明细(USD)": apify_summary.get("usage_usd"),
                "事件计费明细": apify_summary.get("charged_event_counts"),
                "是否拿到费用": apify_summary.get("cost_available"),
                "摘要": apify_summary.get("summary_text"),
                "备注": apify_summary.get("note"),
            },
            ensure_ascii=False,
        ),
    )


def get_scrape_identifiers(output_filename, input_data):
    if output_filename == 'tiktok':
        return list(input_data.get('profiles', []))
    if output_filename == 'instagram':
        return list(input_data.get('usernames', []))
    if output_filename == 'youtube':
        if 'searchQueries' in input_data:
            return list(input_data.get('searchQueries', []))
        if 'startUrls' in input_data:
            return [u['url'] for u in input_data.get('startUrls', []) if isinstance(u, dict) and u.get('url')]
    return []

def set_scrape_identifiers(output_filename, input_data, identifiers):
    if output_filename == 'tiktok':
        input_data['profiles'] = identifiers
    elif output_filename == 'instagram':
        input_data['usernames'] = identifiers
    elif output_filename == 'youtube':
        if 'searchQueries' in input_data:
            input_data['searchQueries'] = identifiers
        elif 'startUrls' in input_data:
            input_data['startUrls'] = [{"url": u} for u in identifiers]

def finalize_apify_output(output_filename, output_file_path, identifiers, skipped_count, progress_callback=None, apify_summary=None, requested_identifiers=None):
    requested_identifiers = dedupe_requested_identifiers(output_filename, requested_identifiers or identifiers)
    cached_profile_reviews = load_profile_reviews(output_filename) if skipped_count > 0 else []
    raw_artifact = load_latest_usable_scrape_artifact(output_filename, output_file_path)
    data = list(raw_artifact.get("items") or [])
    if not data:
        if os.path.exists(output_file_path):
            return {"success": False, "error": f"Output file is empty or invalid JSON: {output_file_path}"}
        return {"success": False, "error": "Output file not found"}

    if raw_artifact.get("source") == "current":
        save_last_non_empty_raw_snapshot(output_filename, data)

    import sys
    scripts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
    if scripts_dir not in sys.path:
        sys.path.append(scripts_dir)
    import data_cleaner

    if progress_callback:
        progress_callback("filtering", "正在执行初筛与结果整理", done=3, total=4)

    source_path = str(raw_artifact.get("path") or output_file_path)
    filter_result = data_cleaner.filter_and_save_dataset(source_path, output_filename, identifiers)
    profile_reviews = merge_profile_reviews_for_requested_identifiers(
        output_filename,
        requested_identifiers,
        filter_result.get("profile_reviews", []),
        cached_profile_reviews,
    )
    filter_result["profile_reviews"] = profile_reviews
    profile_reviews_path = save_profile_reviews(
        output_filename,
        profile_reviews,
        metadata={
            "cached": False,
            "stale_result": False,
            "used_fallback": bool(raw_artifact.get("used_fallback")),
            "raw_data_source": raw_artifact.get("source"),
            "source_path": source_path,
            "updated_at": iso_now(),
        },
    )
    if output_filename == "tiktok" and profile_reviews:
        schedule_tiktok_cover_cache_warm(output_filename, data, profile_reviews)

    returned_profile_keys = {
        resolve_profile_review_identifier(output_filename, item)
        for item in profile_reviews
        if isinstance(item, dict) and item.get("status") != "Missing"
    }
    successful_identifiers = [
        ident for ident in requested_identifiers
        if normalize_identifier(ident) in returned_profile_keys
    ]
    fresh_successful_identifiers = [
        ident for ident in identifiers
        if normalize_identifier(ident) in returned_profile_keys
    ]
    if fresh_successful_identifiers:
        update_history(output_filename, fresh_successful_identifiers)
    elif successful_identifiers and skipped_count > 0:
        update_history(output_filename, successful_identifiers)

    result = {
        "success": True,
        "cached": False,
        "count": len(data),
        "file": source_path,
        "profile_reviews_file": profile_reviews_path,
        "profile_reviews": profile_reviews,
        "filter_stats": filter_result,
        "rejected_profiles": filter_result.get("rejected_profiles", []),
        "rejected_count": filter_result.get("rejected_profiles_count", 0),
        "successful_identifiers": successful_identifiers,
        "fresh_successful_identifiers": fresh_successful_identifiers,
        "requested_total": len(requested_identifiers) or len(profile_reviews),
        "requested_identifiers": list(requested_identifiers or []),
        "used_fallback": bool(raw_artifact.get("used_fallback")),
        "raw_data_source": raw_artifact.get("source"),
        "message": f"本次新抓取 {len(fresh_successful_identifiers)} 个账号，命中缓存 {skipped_count} 个；当前共整理出 {len(successful_identifiers)} / {len(requested_identifiers) or len(profile_reviews)} 个账号的初筛结果。"
    }
    result.update(build_saved_final_review_artifact_status(output_filename))
    if raw_artifact.get("used_fallback"):
        result["message"] = (
            f"本次抓取未产出新的可用原始文件，已回退到最近一次可用结果；"
            f"当前返回 {len(successful_identifiers)} / {len(requested_identifiers) or len(profile_reviews)} 个账号的最近可用初筛结果。"
        )
    if apify_summary:
        result["apify"] = apify_summary
        log_apify_run_summary(output_filename, apify_summary)
    if progress_callback:
        progress_callback("completed", "采集与初筛已完成", done=4, total=4)
    return result


def build_partial_scrape_result(platform, items, identifiers, requested_total=None, batch_index=None, batch_total=None, failed_batches=None):
    failed_batches = failed_batches or []

    import sys
    scripts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
    if scripts_dir not in sys.path:
        sys.path.append(scripts_dir)
    import data_cleaner

    temp_file_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix=f'_{platform}_partial.json', delete=False, dir='/tmp', encoding='utf-8') as tmp_file:
            json.dump(items, tmp_file, indent=2, ensure_ascii=False)
            temp_file_path = tmp_file.name

        filter_result = data_cleaner.filter_and_save_dataset(temp_file_path, platform, identifiers)
        profile_reviews = merge_upload_metadata_into_reviews(platform, filter_result.get("profile_reviews", []))
        filter_result["profile_reviews"] = profile_reviews
        returned_count = len(profile_reviews)
        total_requested = requested_total if isinstance(requested_total, int) and requested_total > 0 else returned_count

        message = f"已完成第 {batch_index}/{batch_total} 批，当前已返回 {returned_count}/{total_requested} 个博主的初筛结果。"
        if failed_batches:
            message += f" 当前有 {len(failed_batches)} 个失败批次。"

        return {
            "success": True,
            "is_partial": True,
            "cached": False,
            "count": len(items),
            "profile_reviews": profile_reviews,
            "filter_stats": filter_result,
            "rejected_profiles": filter_result.get("rejected_profiles", []),
            "rejected_count": filter_result.get("rejected_profiles_count", 0),
            "requested_total": total_requested,
            "completed_batches": batch_index,
            "total_batches": batch_total,
            "failed_batches": failed_batches,
            "message": message,
        }
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except OSError:
                pass

def build_apify_non_retryable_run_failure(
    actor_id,
    output_filename,
    token,
    run_id,
    dataset_id,
    reason,
    *,
    run_data=None,
    error_code="APIFY_REMOTE_RUN_UNCERTAIN",
    status=None,
):
    status_text = translate_apify_status(status)
    message = (
        f"Apify 远端任务已创建（run_id: {run_id}），但本地无法安全确认最终结果：{reason}。"
        f"为避免重复扣费，系统已停止自动重试，也不会自动再次提交这一批。"
        f"请先到 Apify 控制台确认该 run 状态，再决定是否手动重试。"
    )
    if error_code == "APIFY_REMOTE_RUN_FAILED":
        message = (
            f"Apify 远端任务已终止（run_id: {run_id}，状态：{status_text}）。"
            f"为避免重复扣费，系统已停止自动重试当前批次。"
            f"请人工确认失败原因后再决定是否重试。"
        )
    result = {
        "success": False,
        "safe_to_retry": False,
        "error_code": error_code,
        "error": message,
        "message": message,
        "remote_run_started": True,
        "apify_run_id": run_id,
        "apify_dataset_id": dataset_id,
        "apify_token_masked": mask_apify_token(token),
    }
    if status:
        result["apify_status"] = status
        result["apify_status_text"] = status_text
    apify_summary = build_apify_run_summary(
        actor_id,
        "rest",
        run_data or {
            "id": run_id,
            "status": status,
            "defaultDatasetId": dataset_id,
        },
        cost_available=False,
        note=reason,
    )
    if isinstance(apify_summary, dict):
        log_apify_run_summary(output_filename, apify_summary)
        result["apify"] = apify_summary
    return result


def build_apify_uncertain_submission_failure(actor_id, output_filename, token, reason, guard=None, *, error_code="APIFY_RUN_SUBMISSION_UNCERTAIN"):
    message = (
        f"Apify 任务提交阶段状态不确定：{reason}。"
        f"为避免重复扣费，系统已停止自动重试，也不会自动再次提交这一批。"
        f"请先到 Apify 控制台确认最近 run，再决定是否手动重试。"
    )
    result = {
        "success": False,
        "safe_to_retry": False,
        "error_code": error_code,
        "error": message,
        "message": message,
        "remote_run_started": False,
        "apify_token_masked": mask_apify_token(token),
    }
    if isinstance(guard, dict):
        result["guard"] = guard
        if guard.get("run_id"):
            result["apify_run_id"] = guard.get("run_id")
        if guard.get("dataset_id"):
            result["apify_dataset_id"] = guard.get("dataset_id")
    apify_summary = build_apify_run_summary(
        actor_id,
        "rest",
        run_data={"status": None},
        cost_available=False,
        note=reason,
    )
    if isinstance(apify_summary, dict):
        log_apify_run_summary(output_filename, apify_summary)
        result["apify"] = apify_summary
    return result


def run_apify_rest_command(
    actor_id,
    input_data,
    output_filename,
    force_refresh=False,
    progress_callback=None,
    cancel_check=None,
    preferred_tokens=None,
):
    if actor_id not in ALLOWED_APIFY_ACTORS:
        return {"success": False, "error": f"不允许调用该 Actor：{actor_id}"}

    platform_dir = get_platform_dir(output_filename)
    input_file_path = os.path.join(platform_dir, f"{output_filename}_input.json")
    output_file_path = os.path.join(platform_dir, f"{output_filename}_data.json")

    identifiers = get_scrape_identifiers(output_filename, input_data)
    original_identifiers = list(identifiers)
    run_guard_key = build_apify_run_guard_key(actor_id, output_filename, input_data)

    if cancel_check and cancel_check():
        return build_cancelled_result()

    existing_guard = get_apify_run_guard(run_guard_key)
    if existing_guard:
        if existing_guard.get("run_id") and existing_guard.get("dataset_id"):
            recovered_result = recover_guarded_apify_run(
                actor_id,
                input_data,
                output_filename,
                output_file_path,
                identifiers,
                original_identifiers,
                0,
                existing_guard,
                progress_callback=progress_callback,
                cancel_check=cancel_check,
            )
            if recovered_result is not None:
                return recovered_result
        message = build_apify_run_guard_message(existing_guard)
        return {
            "success": False,
            "safe_to_retry": False,
            "error_code": "APIFY_SUBMISSION_LOCKED",
            "error": message,
            "message": message,
            "guard": existing_guard,
            "apify_run_id": existing_guard.get("run_id"),
            "apify_dataset_id": existing_guard.get("dataset_id"),
        }

    skipped_count = 0
    if not force_refresh and identifiers:
        original_count = len(identifiers)
        identifiers = filter_unscraped(output_filename, identifiers)
        skipped_count = original_count - len(identifiers)
        set_scrape_identifiers(output_filename, input_data, identifiers)
    if progress_callback:
        progress_callback(
            "preparing",
            "正在准备采集任务",
            done=0,
            total=4,
            **build_target_preview(identifiers),
        )

    if len(identifiers) == 0 and skipped_count > 0:
        if cancel_check and cancel_check():
            return build_cancelled_result()
        cached_result = build_cached_scrape_response(
            output_filename,
            output_file_path,
            skipped_count,
            progress_callback,
            requested_identifiers=original_identifiers,
        )
        if cached_result is not None:
            return cached_result

        print(f"缓存文件为空或无效，准备重新抓取：{output_file_path}")
        identifiers = list(original_identifiers)
        set_scrape_identifiers(output_filename, input_data, identifiers)
        skipped_count = 0

    reservation_key = f"apify-run:{output_filename}:{uuid.uuid4().hex}"
    budget_guard = ensure_apify_budget_for_run(
        output_filename,
        input_data,
        identifiers,
        cancel_check=cancel_check,
        reservation_key=reservation_key,
        reservation_metadata={
            "actor_id": actor_id,
            "platform": output_filename,
            "identifier_count": len(identifiers),
        },
        preferred_tokens=preferred_tokens,
    )
    if not budget_guard.get("success"):
        return budget_guard

    with open(input_file_path, 'w') as f:
        json.dump(input_data, f, indent=2)

    token = budget_guard.get("token") or get_apify_token()
    if not token:
        return {"success": False, "error": "未配置 Apify token"}

    actor_ref = actor_id.replace("/", "~")
    run_url = f"{APIFY_API_BASE}/acts/{actor_ref}/runs"
    run_id = None
    dataset_id = None

    try:
        run_info = {}
        final_run_data = {}
        if cancel_check and cancel_check():
            return build_cancelled_result()
        if progress_callback:
            progress_callback(
                "apify_start",
                "正在提交 Apify 任务",
                done=1,
                total=4,
                **build_target_preview(identifiers),
            )
        start_resp = apify_request(
            "POST",
            run_url,
            params={"token": token},
            json=input_data,
            cancel_check=cancel_check,
            retry_context=f"start run {actor_id}",
            allow_retries=False,
        )
        if start_resp.status_code not in (200, 201):
            reason = f"启动 Apify 任务失败：{extract_apify_response_error(start_resp)}"
            if start_resp.status_code in APIFY_TRANSIENT_STATUS_CODES:
                guard = remember_apify_run_guard(
                    run_guard_key,
                    actor_id=actor_id,
                    output_filename=output_filename,
                    input_data=input_data,
                    reason=reason,
                    token=token,
                )
                return build_apify_uncertain_submission_failure(
                    actor_id,
                    output_filename,
                    token,
                    reason,
                    guard=guard,
                )
            return {"success": False, "error": reason}

        run_info = (start_resp.json() or {}).get('data', {})
        run_id = run_info.get('id')
        dataset_id = run_info.get('defaultDatasetId')
        if not run_id or not dataset_id:
            return {"success": False, "error": "Apify API 未返回 run_id 或 dataset_id"}

        remember_apify_run_guard(
            run_guard_key,
            actor_id=actor_id,
            output_filename=output_filename,
            input_data=input_data,
            reason="远端 run 已创建，正在等待本地确认最终结果。",
            token=token,
            run_id=run_id,
            dataset_id=dataset_id,
            status=run_info.get("status"),
        )

        poll_result = poll_apify_run_until_terminal(
            token,
            run_id,
            cancel_check=cancel_check,
            progress_callback=progress_callback,
            progress_stage="apify_running",
            progress_payload={
                "done": 1,
                "total": 4,
                **build_target_preview(identifiers),
            },
            max_wait_seconds=max(APIFY_MIN_WAIT_SECONDS, min(APIFY_MAX_WAIT_SECONDS, len(identifiers) * 45)),
        )

        if poll_result.get("cancelled"):
            return build_cancelled_result()

        final_run_data = poll_result.get("run_data") or run_info or {}
        final_status = poll_result.get("status") or final_run_data.get("status")
        dataset_id = str(poll_result.get("dataset_id") or final_run_data.get("defaultDatasetId") or dataset_id).strip()

        if not poll_result.get("success"):
            if poll_result.get("terminal"):
                clear_apify_run_guard(run_guard_key)
                return build_apify_non_retryable_run_failure(
                    actor_id,
                    output_filename,
                    token,
                    run_id,
                    dataset_id,
                    poll_result.get("error") or f"远端 run 已结束：{translate_apify_status(final_status)}",
                    run_data=final_run_data or run_info,
                    error_code="APIFY_REMOTE_RUN_FAILED",
                    status=final_status,
                )

            guard = remember_apify_run_guard(
                run_guard_key,
                actor_id=actor_id,
                output_filename=output_filename,
                input_data=input_data,
                reason=(
                    poll_result.get("error")
                    or f"本地等待超时，已切换到远端恢复模式。"
                ),
                token=token,
                run_id=run_id,
                dataset_id=dataset_id,
                status=final_status,
            )
            return recover_guarded_apify_run(
                actor_id,
                input_data,
                output_filename,
                output_file_path,
                identifiers,
                original_identifiers,
                skipped_count,
                guard,
                progress_callback=progress_callback,
                cancel_check=cancel_check,
            )

        if progress_callback:
            progress_callback(
                "downloading",
                "正在下载数据集结果",
                done=2,
                total=4,
                **build_target_preview(identifiers),
                **build_apify_progress_metadata(
                    run_id=run_id,
                    dataset_id=dataset_id,
                    status=final_status,
                    safe_to_retry=False,
                ),
            )
        if cancel_check and cancel_check():
            return build_cancelled_result()

        dataset_result = download_apify_dataset_items(token, dataset_id, cancel_check=cancel_check)
        if not dataset_result.get("success"):
            guard = remember_apify_run_guard(
                run_guard_key,
                actor_id=actor_id,
                output_filename=output_filename,
                input_data=input_data,
                reason=dataset_result.get("error") or "下载数据集失败",
                token=token,
                run_id=run_id,
                dataset_id=dataset_id,
                status=final_status or "SUCCEEDED",
            )
            return recover_guarded_apify_run(
                actor_id,
                input_data,
                output_filename,
                output_file_path,
                identifiers,
                original_identifiers,
                skipped_count,
                guard,
                progress_callback=progress_callback,
                cancel_check=cancel_check,
            )

        items = dataset_result.get("items")
        with open(output_file_path, 'w', encoding='utf-8') as f:
            json.dump(items, f, indent=2, ensure_ascii=False)

        if cancel_check and cancel_check():
            return build_cancelled_result()

        apify_summary = build_apify_run_summary(
            actor_id,
            "rest",
            final_run_data or run_info,
            cost_available=True,
        )
        result = finalize_apify_output(
            output_filename,
            output_file_path,
            identifiers,
            skipped_count,
            progress_callback,
            apify_summary=apify_summary,
            requested_identifiers=original_identifiers,
        )
        if result.get("success"):
            result["raw_items"] = items
            clear_apify_run_guard(run_guard_key)
        return result
    except requests.RequestException as e:
        if run_id and dataset_id:
            guard = remember_apify_run_guard(
                run_guard_key,
                actor_id=actor_id,
                output_filename=output_filename,
                input_data=input_data,
                reason=f"Apify REST 请求异常：{e}",
                token=token,
                run_id=run_id,
                dataset_id=dataset_id,
            )
            return build_apify_non_retryable_run_failure(
                actor_id,
                output_filename,
                token,
                run_id,
                dataset_id,
                f"Apify REST 请求异常：{e}",
                run_data=final_run_data or run_info,
            )
        guard = remember_apify_run_guard(
            run_guard_key,
            actor_id=actor_id,
            output_filename=output_filename,
            input_data=input_data,
            reason=f"提交 Apify 任务时请求异常：{e}",
            token=token,
        )
        return build_apify_uncertain_submission_failure(
            actor_id,
            output_filename,
            token,
            f"提交 Apify 任务时请求异常：{e}",
            guard=guard,
        )
    finally:
        release_apify_budget_reservation(reservation_key)

def run_apify_command(actor_id, input_data, output_filename, force_refresh=False, progress_callback=None, cancel_check=None):
    if actor_id not in ALLOWED_APIFY_ACTORS:
        return {"success": False, "error": f"不允许调用该 Actor：{actor_id}"}

    platform_dir = get_platform_dir(output_filename) # output_filename matches platform name (tiktok, instagram, etc)
    input_file_path = os.path.join(platform_dir, f"{output_filename}_input.json")
    output_file_path = os.path.join(platform_dir, f"{output_filename}_data.json")
    
    # Identify what we are scraping
    identifiers = get_scrape_identifiers(output_filename, input_data)
            
    original_identifiers = list(identifiers)

    if cancel_check and cancel_check():
        return build_cancelled_result()

    # Filter if not forcing refresh
    skipped_count = 0
    if not force_refresh and identifiers:
        original_count = len(identifiers)
        identifiers = filter_unscraped(output_filename, identifiers)
        skipped_count = original_count - len(identifiers)
        set_scrape_identifiers(output_filename, input_data, identifiers)
    if progress_callback:
        progress_callback(
            "preparing",
            "正在准备采集任务",
            done=0,
            total=4,
            **build_target_preview(identifiers),
        )
    
    # If nothing new to scrape, return early (but maybe return cached data?)
    # For simplicity, if skipped > 0 and identifiers == 0, we imply success but no new data
    if len(identifiers) == 0 and skipped_count > 0:
        if cancel_check and cancel_check():
            return build_cancelled_result()
        cached_result = build_cached_scrape_response(
            output_filename,
            output_file_path,
            skipped_count,
            progress_callback,
            requested_identifiers=original_identifiers,
        )
        if cached_result is not None:
            return cached_result

        print(f"缓存文件为空或无效，准备重新抓取：{output_file_path}")
        identifiers = list(original_identifiers)
        set_scrape_identifiers(output_filename, input_data, identifiers)
        skipped_count = 0

    with open(input_file_path, 'w') as f:
        json.dump(input_data, f, indent=2)
        
    # Path to the token manager script
    script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "apify_token_manager.py")
    
    # Prefix the apify command with our token manager
    # We use python3 explicitly
    command = f"python3 {script_path} 'cat {input_file_path} | apify call {actor_id} --output-dataset > {output_file_path}'"
    
    print(f"正在执行命令：{command}")
    
    try:
        if cancel_check and cancel_check():
            return build_cancelled_result()
        if progress_callback:
            progress_callback(
                "scraping",
                "正在调用 Apify Actor",
                done=1,
                total=4,
                **build_target_preview(identifiers),
            )
        # Using shell=True to support pipe and redirection
        # Capture output for debugging
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=True,
            text=True,
            timeout=APIFY_COMMAND_TIMEOUT_SECONDS,
        )
        print(f"命令标准输出：{result.stdout}")
        print(f"命令标准错误：{result.stderr}")

        if cancel_check and cancel_check():
            return build_cancelled_result()
        
        apify_summary = build_apify_run_summary(
            actor_id,
            "cli",
            cost_available=False,
            note="当前 CLI 执行路径未采集单次 run 费用；如需单次费用请切换到 REST 执行路径。",
        )
        return finalize_apify_output(
            output_filename,
            output_file_path,
            identifiers,
            skipped_count,
            progress_callback,
            apify_summary=apify_summary,
            requested_identifiers=original_identifiers,
        )
            
    except subprocess.CalledProcessError as e:
        print(f"命令执行失败：{e.stderr}")
        return {"success": False, "error": f"命令执行失败：{e.stderr}"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"命令执行超时：已超过 {APIFY_COMMAND_TIMEOUT_SECONDS} 秒"}
    except Exception as e:
        print(f"发生异常：{str(e)}")
        return {"success": False, "error": str(e)}


def perform_batched_rest_scrape(platform, actor_id, common_input, identifiers, output_filename, force_refresh=False, progress_callback=None, cancel_check=None):
    platform_dir = get_platform_dir(output_filename)
    output_file_path = os.path.join(platform_dir, f"{output_filename}_data.json")

    original_identifiers = [item for item in identifiers if str(item).strip()]
    identifiers = list(original_identifiers)
    skipped_count = 0

    if cancel_check and cancel_check():
        return build_cancelled_result()

    if not force_refresh and identifiers:
        original_count = len(identifiers)
        identifiers = filter_unscraped(output_filename, identifiers)
        skipped_count = original_count - len(identifiers)

    if len(identifiers) == 0 and skipped_count > 0:
        cached_result = build_cached_scrape_response(
            output_filename,
            output_file_path,
            skipped_count,
            progress_callback,
            requested_identifiers=original_identifiers,
        )
        if cached_result is not None:
            return cached_result
        print(f"缓存文件为空或无效，准备重新抓取：{output_file_path}")
        identifiers = list(original_identifiers)
        skipped_count = 0

    request_budget_guard = ensure_apify_budget_for_request(
        platform,
        common_input,
        identifiers,
        cancel_check=cancel_check,
        progress_callback=progress_callback,
    )
    if not request_budget_guard.get("success"):
        return request_budget_guard

    if progress_callback:
        progress_callback(
            "preparing",
            "正在准备采集任务",
            done=0,
            total=4,
            **build_target_preview(identifiers),
        )

    batch_size = get_apify_batch_size(platform, common_input)
    batched_identifiers = chunk_list(identifiers, batch_size)

    aggregated_items = []
    processed_identifiers = []
    successful_identifiers = set()
    aggregate_success_count = 0
    failed_batches = []
    apify_runs = []
    apify_total_cost = 0.0
    has_apify_cost = False
    abort_remaining_batches = False

    for batch_index, batch in enumerate(batched_identifiers, start=1):
        if cancel_check and cancel_check():
            return build_cancelled_result()

        pending_identifiers = list(batch)
        batch_items = []
        batch_attempt = 0
        batch_attempt_budget = get_apify_attempt_budget()
        token_candidates = get_ordered_apify_token_candidates()
        tried_tokens = set()
        batch_completed_without_gap = False
        batch_total = len(batched_identifiers)
        last_retry_strategy = None

        def forward_batch_progress(stage, message=None, done=None, total=None, **extra):
            if not progress_callback:
                return

            if stage == "completed":
                return

            forwarded_message = message
            if message and stage in {"apify_start", "apify_running", "recovering_remote_run", "waiting_remote_run", "downloading", "filtering"}:
                forwarded_message = f"第 {batch_index}/{batch_total} 批：{message}"

            forwarded_done = batch_index - 1
            if stage in {"batch_completed", "batch_failed", "failed", "cancelled"}:
                forwarded_done = batch_index

            payload = {
                "batch_index": batch_index,
                "batch_total": batch_total,
                "batch_size": len(batch),
                "attempt": batch_attempt,
                "attempt_budget": batch_attempt_budget,
            }
            payload.update(extra)
            progress_callback(
                stage,
                forwarded_message,
                done=forwarded_done,
                total=batch_total,
                **payload,
            )

        while pending_identifiers and batch_attempt < batch_attempt_budget:
            if cancel_check and cancel_check():
                return build_cancelled_result()

            batch_attempt += 1
            batch_input = dict(common_input)
            set_scrape_identifiers(output_filename, batch_input, pending_identifiers)
            preferred_tokens = [
                token for token in token_candidates
                if token not in tried_tokens
            ] + [
                token for token in token_candidates
                if token in tried_tokens
            ]
            attempted_token = preferred_tokens[0] if preferred_tokens else None
            if attempted_token:
                tried_tokens.add(attempted_token)

            if progress_callback:
                if batch_attempt == 1:
                    stage = "batch_preparing"
                    message = f"正在处理第 {batch_index}/{len(batched_identifiers)} 批（{len(pending_identifiers)} 个）"
                else:
                    stage = "batch_preparing"
                    retry_clause = "尝试其他 token" if last_retry_strategy == "rotated_token" else "继续使用当前策略"
                    message = f"第 {batch_index}/{len(batched_identifiers)} 批上次返回不完整或失败，{retry_clause}重试剩余 {len(pending_identifiers)} 个"
                progress_callback(
                    stage,
                    message,
                    done=batch_index - 1,
                    total=batch_total,
                    batch_index=batch_index,
                    batch_total=batch_total,
                    batch_size=len(batch),
                    attempt=batch_attempt,
                    attempt_budget=batch_attempt_budget,
                    **build_target_preview(pending_identifiers),
                )

            batch_result = run_apify_rest_command(
                actor_id,
                batch_input,
                output_filename,
                True,
                forward_batch_progress,
                cancel_check=cancel_check,
                preferred_tokens=preferred_tokens,
            )

            if batch_result.get("cancelled"):
                return batch_result

            batch_apify = batch_result.get("apify")
            if isinstance(batch_apify, dict):
                apify_runs.append(batch_apify)
                batch_cost = batch_apify.get("usage_total_usd")
                if isinstance(batch_cost, (int, float)):
                    apify_total_cost += float(batch_cost)
                    has_apify_cost = True

            if not batch_result.get("success"):
                batch_error = batch_result.get("error") or f"{platform} batch scrape failed"
                safe_to_retry = batch_result.get("safe_to_retry", True)
                if safe_to_retry and batch_attempt < batch_attempt_budget:
                    has_untried_tokens = any(token not in tried_tokens for token in token_candidates)
                    last_retry_strategy = "rotated_token" if has_untried_tokens else "same_token"
                    continue
                if not safe_to_retry:
                    abort_remaining_batches = True

                failed_batches.append({
                    "batch_index": batch_index,
                    "batch_total": len(batched_identifiers),
                    "identifiers": list(pending_identifiers),
                    "error": batch_error,
                    "attempts": batch_attempt,
                    "attempt_budget": batch_attempt_budget,
                    "safe_to_retry": bool(safe_to_retry),
                    "error_code": batch_result.get("error_code"),
                    "apify_run_id": batch_result.get("apify_run_id"),
                })
                if progress_callback:
                    progress_callback(
                        "batch_failed",
                        f"第 {batch_index}/{batch_total} 批失败：{batch_error}",
                        done=batch_index,
                        total=batch_total,
                        batch_index=batch_index,
                        batch_total=batch_total,
                        failed_count=len(failed_batches),
                        attempt=batch_attempt,
                        attempt_budget=batch_attempt_budget,
                        **build_target_preview(pending_identifiers),
                    )
                break

            new_items = batch_result.get("raw_items") or []
            if not isinstance(new_items, list):
                new_items = [new_items]
            batch_items = merge_scrape_items(platform, batch_items, new_items)

            returned_identifiers = extract_returned_identifiers(platform, batch_items)
            missing_identifiers = [
                ident for ident in batch
                if normalize_identifier(ident) not in returned_identifiers
            ]

            if not missing_identifiers:
                batch_completed_without_gap = True
                break

            if batch_attempt < batch_attempt_budget:
                has_untried_tokens = any(token not in tried_tokens for token in token_candidates)
                last_retry_strategy = "rotated_token" if has_untried_tokens else "same_token"
                pending_identifiers = missing_identifiers
                continue

            failed_batches.append({
                "batch_index": batch_index,
                "batch_total": len(batched_identifiers),
                "identifiers": list(missing_identifiers),
                "error": f"第 {batch_index} 批返回不完整，仅拿到 {len(returned_identifiers)}/{len(batch)} 个账号",
                "attempts": batch_attempt,
                "attempt_budget": batch_attempt_budget,
            })
            if progress_callback:
                progress_callback(
                    "batch_failed",
                    f"第 {batch_index}/{batch_total} 批返回不完整，仅拿到 {len(returned_identifiers)}/{len(batch)} 个账号",
                    done=batch_index,
                    total=batch_total,
                    batch_index=batch_index,
                    batch_total=batch_total,
                    failed_count=len(failed_batches),
                    attempt=batch_attempt,
                    attempt_budget=batch_attempt_budget,
                    **build_target_preview(missing_identifiers),
                )
            break

        processed_identifiers.extend(batch)
        processed_identifiers = list(dict.fromkeys(processed_identifiers))

        if batch_items:
            batch_returned_identifiers = extract_returned_identifiers(platform, batch_items)
            successful_identifiers.update(
                ident for ident in batch
                if normalize_identifier(ident) in batch_returned_identifiers
            )
            aggregated_items = merge_scrape_items(platform, aggregated_items, batch_items)
            aggregate_success_count += 1

            with open(output_file_path, 'w', encoding='utf-8') as f:
                json.dump(aggregated_items, f, indent=2, ensure_ascii=False)

            partial_result = build_partial_scrape_result(
                platform,
                aggregated_items,
                processed_identifiers,
                requested_total=len(original_identifiers),
                batch_index=batch_index,
                batch_total=len(batched_identifiers),
                failed_batches=failed_batches,
            )

            if progress_callback:
                progress_callback(
                    "batch_completed",
                    (
                        f"第 {batch_index}/{batch_total} 批完成，"
                        f"已累计返回 {len(successful_identifiers)}/{len(identifiers)} 个账号"
                    ),
                    done=batch_index,
                    total=batch_total,
                    batch_index=batch_index,
                    batch_total=batch_total,
                    batch_size=len(batch),
                    partial_result=partial_result,
                    **build_target_preview(batch),
                )
        elif progress_callback and batch_completed_without_gap:
            progress_callback(
                "batch_completed",
                f"第 {batch_index}/{batch_total} 批完成，但当前未返回可用结果",
                done=batch_index,
                total=batch_total,
                batch_index=batch_index,
                batch_total=batch_total,
                batch_size=len(batch),
                **build_target_preview(batch),
            )

        if abort_remaining_batches:
            break

    if len(aggregated_items) == 0:
        preserved_result = build_preserved_failure_response(
            output_filename,
            output_file_path,
            failed_batches,
            progress_callback,
            requested_identifiers=original_identifiers,
        )
        if preserved_result is not None:
            return preserved_result
        error_message = failed_batches[0]["error"] if failed_batches else f"{platform} batch scrape failed"
        return {
            "success": False,
            "error": error_message,
            "failed_batches": failed_batches,
        }

    with open(output_file_path, 'w', encoding='utf-8') as f:
        json.dump(aggregated_items, f, indent=2, ensure_ascii=False)

    result = finalize_apify_output(
        output_filename,
        output_file_path,
        identifiers,
        skipped_count,
        None,
        requested_identifiers=original_identifiers,
    )
    if not result.get("success"):
        return result

    result["failed_batches"] = failed_batches
    result["successful_batches"] = aggregate_success_count
    result["batch_summary"] = {
        "total": len(batched_identifiers),
        "successful": aggregate_success_count,
        "failed": len(failed_batches),
        "batch_size": batch_size,
    }
    result_requested_total = result.get("requested_total") or len(original_identifiers)
    result["apify"] = {
        "actor_id": actor_id,
        "execution_method": "rest-batched",
        "cost_available": has_apify_cost,
        "usage_total_usd": round(apify_total_cost, 6) if has_apify_cost else None,
        "runs": apify_runs,
        "note": (
            "分批模式下总费用为各批次 usageTotalUsd 累加；当某批返回不完整时，"
            "会自动切换 token 并重试缺失账号。"
        ),
        "status_text": "部分成功" if failed_batches else "已成功",
        "summary_text": build_apify_cost_summary_text(
            has_apify_cost,
            round(apify_total_cost, 6) if has_apify_cost else None,
            "rest-batched",
            None if has_apify_cost else "分批任务已完成，但暂未拿到费用数据。"
        ),
    }
    if failed_batches:
        result["message"] = (
            f"{platform.capitalize()} 分批采集完成，共返回 {len(result.get('successful_identifiers') or [])}/{result_requested_total} 个账号；"
            f"{len(failed_batches)} 个批次或缺失子集失败，当前仅展示成功抓回的结果。"
        )
    else:
        result["message"] = (
            f"{platform.capitalize()} 分批采集完成，共返回 {len(result.get('successful_identifiers') or [])}/{result_requested_total} 个账号。"
        )
    log_apify_run_summary(output_filename, result["apify"])
    if progress_callback:
        progress_callback(
            "completed",
            result["message"],
            done=len(batched_identifiers),
            total=len(batched_identifiers),
            batch_index=aggregate_success_count,
            batch_total=len(batched_identifiers),
            failed_count=len(failed_batches),
        )
    return result


def perform_scrape(platform, data, progress_callback=None, cancel_check=None):
    force_refresh = data.get("forceRefresh", False)

    if platform == 'tiktok':
        profiles = [item for item in data.get("profiles", []) if str(item).strip()]
        should_download_covers = bool(data.get("downloadCovers", TIKTOK_DOWNLOAD_COVERS_BY_DEFAULT))
        input_data = {
            "resultsPerPage": int(data.get("limit", 20)),
            "excludePinnedPosts": data.get("excludePinnedPosts", False),
            "shouldDownloadVideos": data.get("downloadVideos", False),
            "shouldDownloadCovers": should_download_covers,
            "shouldDownloadAvatars": data.get("downloadAvatars", False),
            "shouldDownloadSlideshowImages": bool(data.get("downloadSlideshow", False) or should_download_covers),
            "shouldDownloadSubtitles": data.get("downloadSubtitles", False)
        }
        return perform_batched_rest_scrape(
            "tiktok",
            "clockworks/tiktok-profile-scraper",
            input_data,
            profiles,
            "tiktok",
            force_refresh,
            progress_callback,
            cancel_check=cancel_check,
        )

    if platform == 'instagram':
        usernames = [item for item in data.get("usernames", []) if str(item).strip()]
        input_data = {
            "includeAboutSection": data.get("includeAbout", False)
        }
        return perform_batched_rest_scrape(
            "instagram",
            "apify/instagram-profile-scraper",
            input_data,
            usernames,
            "instagram",
            force_refresh,
            progress_callback,
            cancel_check=cancel_check,
        )

    if platform == 'youtube':
        mode = data.get("mode", "search")
        common_input = {
            "maxResults": int(data.get("limit", 10)),
            "maxResultsShorts": 0,
            "maxResultStreams": 0,
            "subtitlesLanguage": "en",
            "subtitlesFormat": "srt",
            "downloadSubtitles": data.get("downloadSubtitles", False),
            "hasCC": data.get("hasCC", False)
        }
        identifiers = data.get("queries", []) if mode == "search" else data.get("urls", [])
        identifiers = [item for item in identifiers if str(item).strip()]

        if cancel_check and cancel_check():
            return build_cancelled_result()

        max_direct_batch_size = get_apify_batch_size("youtube", common_input)
        if len(identifiers) <= max_direct_batch_size:
            input_data = dict(common_input)
            if mode == "search":
                input_data["searchQueries"] = identifiers
            else:
                input_data["startUrls"] = [{"url": url} for url in identifiers]
            return run_apify_rest_command("streamers/youtube-scraper", input_data, "youtube", force_refresh, progress_callback, cancel_check=cancel_check)

        platform_dir = get_platform_dir("youtube")
        output_file_path = os.path.join(platform_dir, "youtube_data.json")
        original_identifiers = list(identifiers)
        skipped_count = 0

        if not force_refresh and identifiers:
            original_count = len(identifiers)
            identifiers = filter_unscraped("youtube", identifiers)
            skipped_count = original_count - len(identifiers)

        if len(identifiers) == 0 and skipped_count > 0:
            cached_result = build_cached_scrape_response(
                "youtube",
                output_file_path,
                skipped_count,
                progress_callback,
                requested_identifiers=original_identifiers,
            )
            if cached_result is not None:
                return cached_result

            identifiers = list(original_identifiers)
            skipped_count = 0

        request_budget_guard = ensure_apify_budget_for_request(
            "youtube",
            common_input,
            identifiers,
            cancel_check=cancel_check,
            progress_callback=progress_callback,
        )
        if not request_budget_guard.get("success"):
            return request_budget_guard

        batched_identifiers = chunk_list(identifiers, get_apify_batch_size("youtube", common_input))
        aggregated_items = []
        aggregate_success_count = 0
        failed_batches = []
        successful_identifiers = set()
        apify_runs = []
        apify_total_cost = 0.0
        has_apify_cost = False
        abort_remaining_batches = False

        for batch_index, batch in enumerate(batched_identifiers, start=1):
            if cancel_check and cancel_check():
                return build_cancelled_result()

            batch_input = dict(common_input)
            if mode == "search":
                batch_input["searchQueries"] = batch
            else:
                batch_input["startUrls"] = [{"url": url} for url in batch]

            if progress_callback:
                progress_callback(
                    "batch_preparing",
                    f"正在处理第 {batch_index}/{len(batched_identifiers)} 批（{len(batch)} 个）",
                    done=batch_index - 1,
                    total=len(batched_identifiers),
                    batch_index=batch_index,
                    batch_total=len(batched_identifiers),
                    batch_size=len(batch),
                    **build_target_preview(batch),
                )

            batch_result = run_apify_rest_command(
                "streamers/youtube-scraper",
                batch_input,
                "youtube",
                True,
                None,
                cancel_check=cancel_check,
            )

            if batch_result.get("cancelled"):
                return batch_result

            if not batch_result.get("success"):
                batch_error = batch_result.get("error") or "YouTube batch scrape failed"
                safe_to_retry = batch_result.get("safe_to_retry", True)
                if not safe_to_retry:
                    abort_remaining_batches = True
                failed_batches.append({
                    "batch_index": batch_index,
                    "batch_total": len(batched_identifiers),
                    "identifiers": batch,
                    "error": batch_error,
                    "safe_to_retry": bool(safe_to_retry),
                    "error_code": batch_result.get("error_code"),
                    "apify_run_id": batch_result.get("apify_run_id"),
                })
                if progress_callback:
                    progress_callback(
                        "batch_failed",
                        f"第 {batch_index}/{len(batched_identifiers)} 批失败：{batch_error}",
                        done=batch_index,
                        total=len(batched_identifiers),
                        batch_index=batch_index,
                        batch_total=len(batched_identifiers),
                        failed_count=len(failed_batches),
                        **build_target_preview(batch),
                    )
                if abort_remaining_batches:
                    break
                continue

            batch_items = batch_result.get("raw_items") or []
            if not isinstance(batch_items, list):
                batch_items = [batch_items]
            aggregated_items = merge_scrape_items("youtube", aggregated_items, batch_items)
            aggregate_success_count += 1
            returned_identifiers = extract_returned_identifiers("youtube", batch_items)
            successful_identifiers.update(
                ident for ident in batch
                if normalize_identifier(ident) in returned_identifiers
            )
            batch_apify = batch_result.get("apify")
            if isinstance(batch_apify, dict):
                apify_runs.append(batch_apify)
                batch_cost = batch_apify.get("usage_total_usd")
                if isinstance(batch_cost, (int, float)):
                    apify_total_cost += float(batch_cost)
                    has_apify_cost = True

            with open(output_file_path, 'w', encoding='utf-8') as f:
                json.dump(aggregated_items, f, indent=2, ensure_ascii=False)

            partial_result = build_partial_scrape_result(
                "youtube",
                aggregated_items,
                successful_identifiers,
                requested_total=len(original_identifiers),
                batch_index=batch_index,
                batch_total=len(batched_identifiers),
                failed_batches=failed_batches,
            )

            if progress_callback:
                progress_callback(
                    "batch_completed",
                    f"第 {batch_index}/{len(batched_identifiers)} 批完成，已累计返回 {len(successful_identifiers)}/{len(identifiers)} 个账号",
                    done=batch_index,
                    total=len(batched_identifiers),
                    batch_index=batch_index,
                    batch_total=len(batched_identifiers),
                    batch_size=len(batch),
                    **build_target_preview(batch),
                    partial_result=partial_result,
                )

            if abort_remaining_batches:
                break

        if aggregate_success_count == 0:
            preserved_result = build_preserved_failure_response(
                "youtube",
                output_file_path,
                failed_batches,
                progress_callback,
                requested_identifiers=original_identifiers,
            )
            if preserved_result is not None:
                return preserved_result
            error_message = failed_batches[0]["error"] if failed_batches else "YouTube batch scrape failed"
            return {
                "success": False,
                "error": error_message,
                "failed_batches": failed_batches,
            }

        with open(output_file_path, 'w', encoding='utf-8') as f:
            json.dump(aggregated_items, f, indent=2, ensure_ascii=False)

        result = finalize_apify_output(
            "youtube",
            output_file_path,
            identifiers,
            skipped_count,
            None,
            requested_identifiers=original_identifiers,
        )
        if not result.get("success"):
            return result

        result["failed_batches"] = failed_batches
        result["successful_batches"] = aggregate_success_count
        result["batch_summary"] = {
            "total": len(batched_identifiers),
            "successful": aggregate_success_count,
            "failed": len(failed_batches),
        }
        result_requested_total = result.get("requested_total") or len(original_identifiers)
        result["apify"] = {
            "actor_id": "streamers/youtube-scraper",
            "execution_method": "rest-batched",
            "cost_available": has_apify_cost,
            "usage_total_usd": round(apify_total_cost, 6) if has_apify_cost else None,
            "runs": apify_runs,
            "note": "分批模式下总费用为各成功批次 usageTotalUsd 累加；失败批次若未返回 run 费用则不会计入。",
            "status_text": "部分成功" if failed_batches else "已成功",
            "summary_text": build_apify_cost_summary_text(
                has_apify_cost,
                round(apify_total_cost, 6) if has_apify_cost else None,
                "rest-batched",
                None if has_apify_cost else "分批任务已完成，但暂未拿到费用数据。"
            ),
        }
        if failed_batches:
            result["message"] = (
                f"YouTube 分批采集完成，共返回 {len(result.get('successful_identifiers') or [])}/{result_requested_total} 个账号；"
                f"{len(failed_batches)} 批失败，当前仅展示成功抓回的结果。"
            )
        else:
            result["message"] = f"YouTube 分批采集完成，共返回 {len(result.get('successful_identifiers') or [])}/{result_requested_total} 个账号。"
        log_apify_run_summary("youtube", result["apify"])
        if progress_callback:
            progress_callback(
                "completed",
                result["message"],
                done=len(batched_identifiers),
                total=len(batched_identifiers),
                batch_index=aggregate_success_count,
                batch_total=len(batched_identifiers),
                failed_count=len(failed_batches),
            )
        return result

    return {"success": False, "error": f"未知平台：{platform}"}


def perform_visual_review(job_id, profiles, platform="tiktok", review_mode=VISUAL_REVIEW_MODE_AUTO, progress_callback=None, cancel_check=None):
    total = len(profiles)
    results = {}
    review_history = []
    passed = 0
    rejected = 0
    failed = 0
    current_live_review = None
    normalized_review_mode = normalize_visual_review_mode(review_mode)

    for index, item in enumerate(profiles, start=1):
        if cancel_check and cancel_check():
            return build_cancelled_result()
        username = str(item.get("username") or f"profile-{index}").strip()
        cover_urls = build_visual_review_cover_candidates(item, platform=platform)
        requested_cover_total = len([str(url).strip() for url in cover_urls if str(url).strip()])
        recommended_mode = recommend_visual_review_mode_for_cover_count(requested_cover_total)
        target_collage_count = determine_visual_review_target_collage_count(normalized_review_mode, requested_cover_total)
        target_cover_total = min(MAX_COLLAGE_COVER_COUNT * target_collage_count, requested_cover_total)

        current_live_review = build_visual_review_live_snapshot(
            current_username=username,
            requested_mode=normalized_review_mode,
            recommended_mode=recommended_mode,
            applied_mode=VISUAL_REVIEW_MODE_SIMPLE if target_collage_count == 1 else VISUAL_REVIEW_MODE_ENHANCED,
            requested_cover_count=requested_cover_total,
            target_cover_count=target_cover_total,
            current_cover_total=requested_cover_total,
            target_collage_count=target_collage_count,
        )

        def publish_live_review(
            text=None,
            *,
            tone="info",
            step=None,
            done=index - 1,
            preview_url=None,
            preview_urls=None,
            cover_count=None,
            requested_cover_count=None,
            failed_cover_count=None,
            current_cover_index=None,
            current_cover_total=None,
            min_required_cover_count=None,
            target_cover_count=None,
            collage_count=None,
            reviewed_collage_count=None,
            reviewed_collage_urls=None,
            unused_collage_count=None,
            collage_error_count=None,
            target_collage_count=None,
            requested_mode=None,
            recommended_mode=None,
            applied_mode=None,
            downgrade_reason=None,
            provider=None,
            decision=None,
            reason=None,
            signals=None,
        ):
            nonlocal current_live_review

            next_live_review = build_visual_review_live_snapshot(
                current_live_review,
                current_username=username,
                step=step or (current_live_review or {}).get("step") or "preparing",
                updated_at=iso_now(),
                cover_count=cover_count,
                requested_cover_count=requested_cover_count,
                failed_cover_count=failed_cover_count,
                current_cover_index=current_cover_index,
                current_cover_total=current_cover_total,
                min_required_cover_count=min_required_cover_count,
                target_cover_count=target_cover_count,
                collage_count=collage_count,
                reviewed_collage_count=reviewed_collage_count,
                reviewed_collage_urls=reviewed_collage_urls,
                unused_collage_count=unused_collage_count,
                collage_error_count=collage_error_count,
                target_collage_count=target_collage_count,
                requested_mode=requested_mode,
                recommended_mode=recommended_mode,
                applied_mode=applied_mode,
                downgrade_reason=downgrade_reason,
                provider=provider,
                decision=decision,
                reason=reason,
                signals=signals,
            )
            if preview_url is not None:
                next_live_review["current_collage_url"] = preview_url
            if preview_urls is not None:
                next_live_review["current_collage_urls"] = list(preview_urls or [])
                if preview_url is None:
                    next_live_review["current_collage_url"] = next_live_review["current_collage_urls"][0] if next_live_review["current_collage_urls"] else None
            if text:
                next_live_review["log_lines"] = append_visual_review_log(
                    next_live_review.get("log_lines"),
                    text,
                    tone=tone,
                )

            current_live_review = build_visual_review_live_snapshot(next_live_review)
            if progress_callback:
                progress_callback(
                    "visual_reviewing",
                    text or f"正在复核 {username}（{index}/{total}）",
                    done=done,
                    total=total,
                    current_username=username,
                    passed_count=passed,
                    rejected_count=rejected,
                    failed_count=failed,
                    partial_result=build_visual_review_partial(
                        results,
                        total,
                        passed,
                        rejected,
                        failed,
                        current_live_review,
                        review_history,
                    ),
                )

        publish_live_review(
            f"已接收 {username} 的封面，共 {requested_cover_total} 张候选图。当前模式：{normalized_review_mode}；系统建议：{recommended_mode}；最多生成 {target_collage_count} 张九宫格。",
            step="preparing",
            requested_cover_count=requested_cover_total,
            target_cover_count=target_cover_total,
            current_cover_total=requested_cover_total,
            current_cover_index=0,
            failed_cover_count=0,
            min_required_cover_count=MIN_VISUAL_REVIEW_COVER_COUNT,
            collage_count=0,
            target_collage_count=target_collage_count,
            requested_mode=normalized_review_mode,
            recommended_mode=recommended_mode,
            applied_mode=VISUAL_REVIEW_MODE_SIMPLE if target_collage_count == 1 else VISUAL_REVIEW_MODE_ENHANCED,
            downgrade_reason="",
        )

        def handle_collage_progress(event):
            event_type = str((event or {}).get("type") or "").strip()
            requested_count = event.get("requested_cover_count", requested_cover_total)
            loaded_count = event.get("loaded_cover_count", 0)
            failed_count = event.get("failed_cover_count", 0)
            current_index = event.get("current_cover_index", 0)
            current_total = event.get("current_cover_total", requested_cover_total)
            min_required = event.get("min_required_cover_count", MIN_VISUAL_REVIEW_COVER_COUNT)
            target_cover_count = event.get("target_cover_count", target_cover_total)
            max_workers = event.get("max_workers", 1)
            cover_order_index = event.get("cover_order_index", current_index)
            collage_index = int(event.get("collage_index") or 1)
            collage_total = int(event.get("collage_total") or 1)
            aggregate_requested_count = event.get("aggregate_requested_cover_count", requested_count)
            aggregate_loaded_count = event.get("aggregate_loaded_cover_count", loaded_count)
            aggregate_failed_count = event.get("aggregate_failed_cover_count", failed_count)
            collage_prefix = ""
            if collage_total > 1:
                collage_prefix = f"第 {collage_index}/{collage_total} 张九宫格："

            if event_type == "start":
                publish_live_review(
                    f"{collage_prefix}开始并行加载封面，共 {requested_count} 张候选图，最多同时 {max_workers} 张，当前累计成功 {aggregate_loaded_count} 张，目标凑满 {target_cover_total} 张，至少需要 {min_required} 张可用图。",
                    step="collage_loading",
                    cover_count=aggregate_loaded_count,
                    requested_cover_count=aggregate_requested_count,
                    target_cover_count=target_cover_total,
                    failed_cover_count=aggregate_failed_count,
                    current_cover_index=current_index,
                    current_cover_total=current_total,
                    min_required_cover_count=min_required,
                    target_collage_count=collage_total,
                )
                return

            if event_type == "loading":
                publish_live_review(
                    f"{collage_prefix}已提交首批封面加载任务，当前候选图共 {current_total} 张，等待返回。",
                    step="collage_progress",
                    cover_count=aggregate_loaded_count,
                    requested_cover_count=aggregate_requested_count,
                    target_cover_count=target_cover_total,
                    failed_cover_count=aggregate_failed_count,
                    current_cover_index=current_index,
                    current_cover_total=current_total,
                    min_required_cover_count=min_required,
                    target_collage_count=collage_total,
                )
                return

            if event_type == "success":
                publish_live_review(
                    f"{collage_prefix}第 {cover_order_index}/{current_total} 张已返回成功，当前分组完成 {current_index}/{current_total} 张；本组成功 {loaded_count} 张，累计成功 {aggregate_loaded_count} 张，失败 {aggregate_failed_count} 张。",
                    tone="success",
                    step="collage_progress",
                    cover_count=aggregate_loaded_count,
                    requested_cover_count=aggregate_requested_count,
                    target_cover_count=target_cover_total,
                    failed_cover_count=aggregate_failed_count,
                    current_cover_index=current_index,
                    current_cover_total=current_total,
                    min_required_cover_count=min_required,
                    target_collage_count=collage_total,
                )
                return

            if event_type == "failure":
                failure = event.get("failure") or {}
                failure_type = str(failure.get("error_type") or "error").strip() or "error"
                failure_host = str(failure.get("host") or "").strip()
                failure_suffix = f"（{failure_type}）" if failure_type else ""
                if failure_host and failure_host != "unknown-host":
                    failure_suffix = f"{failure_suffix} {failure_host}".strip()
                publish_live_review(
                    f"{collage_prefix}第 {cover_order_index}/{current_total} 张返回失败{failure_suffix}，当前分组完成 {current_index}/{current_total} 张；本组成功 {loaded_count} 张，累计成功 {aggregate_loaded_count} 张，失败 {aggregate_failed_count} 张。",
                    tone="warning",
                    step="collage_progress",
                    cover_count=aggregate_loaded_count,
                    requested_cover_count=aggregate_requested_count,
                    target_cover_count=target_cover_total,
                    failed_cover_count=aggregate_failed_count,
                    current_cover_index=current_index,
                    current_cover_total=current_total,
                    min_required_cover_count=min_required,
                    target_collage_count=collage_total,
                )
                print(
                    "[Vision Review] cover load failed",
                    json.dumps(
                        {
                            "username": username,
                            "current_cover_index": current_index,
                            "current_cover_total": current_total,
                            "requested_cover_count": requested_count,
                            "loaded_cover_count": loaded_count,
                            "failed_cover_count": failed_count,
                            "host": failure.get("host"),
                            "error_type": failure.get("error_type"),
                            "error": failure.get("error"),
                        },
                        ensure_ascii=False,
                    ),
                )
                return

            if event_type == "impossible":
                publish_live_review(
                    f"{collage_prefix}{str(event.get('reason') or '当前剩余封面不足以继续完成九宫格复核。')}",
                    tone="warning",
                    step="collage_progress",
                    cover_count=aggregate_loaded_count,
                    requested_cover_count=aggregate_requested_count,
                    target_cover_count=target_cover_total,
                    failed_cover_count=aggregate_failed_count,
                    current_cover_index=current_index,
                    current_cover_total=current_total,
                    min_required_cover_count=min_required,
                    target_collage_count=collage_total,
                )
                print(
                    "[Vision Review] cover load stopped early",
                    json.dumps(
                        {
                            "username": username,
                            "current_cover_index": current_index,
                            "current_cover_total": current_total,
                            "requested_cover_count": requested_count,
                            "loaded_cover_count": loaded_count,
                            "failed_cover_count": failed_count,
                            "reason": event.get("reason"),
                        },
                        ensure_ascii=False,
                    ),
                )
                return

            if event_type == "collage_error":
                publish_live_review(
                    f"{collage_prefix}整张九宫格加载失败：{str(event.get('error') or 'unknown error')}",
                    tone="warning",
                    step="collage_progress",
                    cover_count=aggregate_loaded_count,
                    requested_cover_count=event.get("aggregate_requested_cover_count", requested_cover_total),
                    target_cover_count=target_cover_total,
                    failed_cover_count=aggregate_failed_count,
                    current_cover_index=current_index,
                    current_cover_total=current_total,
                    min_required_cover_count=min_required,
                    target_collage_count=collage_total,
                )

        try:
            collage_assets = build_cover_collage_bundle_assets(
                cover_urls,
                min_required_cover_count=MIN_VISUAL_REVIEW_COVER_COUNT,
                max_collage_count=target_collage_count,
                progress_callback=handle_collage_progress,
            )
            effective_collage_assets = select_visual_review_bundle_assets(
                collage_assets,
                normalized_review_mode,
            )
            available_preview_urls = [
                cache_visual_review_preview(job_id, f"{username}-collage-{asset_index}", preview_bytes)
                for asset_index, preview_bytes in enumerate(effective_collage_assets.get("available_preview_bytes_list") or [], start=1)
            ]
            reviewed_collage_count = int(effective_collage_assets.get("reviewed_collage_count") or 0)
            reviewed_preview_urls = available_preview_urls[:reviewed_collage_count]
            preview_url = (reviewed_preview_urls or available_preview_urls or [None])[0]
            cover_count = int(
                effective_collage_assets.get("total_loaded_cover_count")
                or effective_collage_assets.get("cover_count")
                or 0
            )
            requested_cover_count = int(
                effective_collage_assets.get("total_requested_cover_count")
                or collage_assets.get("requested_cover_count")
                or cover_count
            )
            download_failure_count = collage_assets.get("download_failure_count") or 0
            min_required_cover_count = collage_assets.get("min_required_cover_count") or MIN_VISUAL_REVIEW_COVER_COUNT
            stopped_early = bool(collage_assets.get("stopped_early"))
            collage_count = int(effective_collage_assets.get("collage_count") or len(available_preview_urls))
            collage_errors = collage_assets.get("collage_errors") or []
            applied_mode = effective_collage_assets.get("applied_mode") or VISUAL_REVIEW_MODE_SIMPLE
            downgrade_reason = str(effective_collage_assets.get("downgrade_reason") or "").strip()
            unused_collage_count = int(effective_collage_assets.get("unused_collage_count") or 0)
            collage_error_count = len(collage_errors)

            if download_failure_count > 0:
                print(
                    "[Vision Review] partial cover load",
                    json.dumps(
                        {
                            "username": username,
                            "loaded_cover_count": cover_count,
                            "requested_cover_count": requested_cover_count,
                            "download_failure_count": download_failure_count,
                            "download_failures": [
                                {
                                    "host": item.get("host"),
                                    "error_type": item.get("error_type"),
                                    "error": item.get("error"),
                                }
                                for item in (collage_assets.get("download_failures") or [])
                            ],
                        },
                        ensure_ascii=False,
                    ),
                )
            if downgrade_reason:
                print(
                    "[Vision Review] auto mode downgraded",
                    json.dumps(
                        {
                            "username": username,
                            "requested_mode": normalized_review_mode,
                            "applied_mode": applied_mode,
                            "reason": downgrade_reason,
                        },
                        ensure_ascii=False,
                    ),
                )
            if collage_errors:
                print(
                    "[Vision Review] collage segment errors",
                    json.dumps(
                        {
                            "username": username,
                            "collage_errors": collage_errors,
                        },
                        ensure_ascii=False,
                    ),
                )

            if cover_count < min_required_cover_count:
                failed += 1
                failure_reason = (
                    f"可用封面不足 {min_required_cover_count} 张，"
                    f"当前仅成功 {cover_count}/{requested_cover_count} 张，跳过该账号视觉复核。"
                )
                if stopped_early and collage_assets.get("early_stop_reason"):
                    failure_reason = (
                        f"{failure_reason} {str(collage_assets.get('early_stop_reason')).strip()}"
                    )

                results[username] = {
                    "success": False,
                    "username": username,
                    "error": failure_reason,
                    "cover_count": cover_count,
                    "requested_cover_count": requested_cover_count,
                    "download_failure_count": download_failure_count,
                }
                publish_live_review(
                    failure_reason,
                    tone="error",
                    step="collage_failed",
                    done=index,
                    preview_url=preview_url,
                    preview_urls=available_preview_urls,
                    cover_count=cover_count,
                    requested_cover_count=requested_cover_count,
                    failed_cover_count=download_failure_count,
                    current_cover_index=current_live_review.get("current_cover_index") or requested_cover_count,
                    current_cover_total=current_live_review.get("current_cover_total") or requested_cover_count,
                    min_required_cover_count=min_required_cover_count,
                    collage_count=collage_count,
                    reviewed_collage_count=reviewed_collage_count,
                    reviewed_collage_urls=reviewed_preview_urls,
                    unused_collage_count=unused_collage_count,
                    collage_error_count=collage_error_count,
                    target_collage_count=target_collage_count,
                    decision="Error",
                    reason=failure_reason,
                )
                history_item = build_visual_review_history_item(current_live_review, success=False)
                if history_item is not None:
                    review_history.append(history_item)
                continue

            if reviewed_collage_count > 0 and reviewed_collage_count < collage_count:
                collage_ready_text = (
                    f"已整理 {cover_count}/{requested_cover_count} 张可用封面，共生成 {collage_count} 张九宫格；"
                    f"本轮按 {applied_mode} 模式送审 {reviewed_collage_count} 张，其余 {unused_collage_count} 张保留预览。"
                )
            else:
                collage_ready_text = f"已整理 {cover_count} 张封面，按 {applied_mode} 模式生成 {collage_count} 张九宫格，开始检查整体风格与构图。"
            collage_ready_tone = "info"
            if download_failure_count > 0:
                if reviewed_collage_count > 0 and reviewed_collage_count < collage_count:
                    collage_ready_text = (
                        f"已整理 {cover_count}/{requested_cover_count} 张可用封面，共生成 {collage_count} 张九宫格；"
                        f"{download_failure_count} 张加载失败，本轮按 {applied_mode} 模式送审 {reviewed_collage_count} 张，其余 {unused_collage_count} 张保留预览。"
                    )
                else:
                    collage_ready_text = (
                        f"已整理 {cover_count}/{requested_cover_count} 张可用封面，"
                        f"按 {applied_mode} 模式生成 {collage_count} 张九宫格，{download_failure_count} 张加载失败，继续检查整体风格与构图。"
                    )
                collage_ready_tone = "warning"
            if downgrade_reason:
                collage_ready_text = f"{collage_ready_text} {downgrade_reason}"
                collage_ready_tone = "warning"

            publish_live_review(
                collage_ready_text,
                tone=collage_ready_tone,
                step="collage_ready",
                preview_url=preview_url,
                preview_urls=available_preview_urls,
                cover_count=cover_count,
                requested_cover_count=requested_cover_count,
                failed_cover_count=download_failure_count,
                current_cover_index=requested_cover_count,
                current_cover_total=requested_cover_count,
                min_required_cover_count=min_required_cover_count,
                collage_count=collage_count,
                reviewed_collage_count=reviewed_collage_count,
                reviewed_collage_urls=reviewed_preview_urls,
                unused_collage_count=unused_collage_count,
                collage_error_count=collage_error_count,
                target_collage_count=target_collage_count,
                requested_mode=normalized_review_mode,
                recommended_mode=recommended_mode,
                applied_mode=applied_mode,
                downgrade_reason=downgrade_reason,
            )

            # 根据平台显示不同的检查步骤文案
            if platform == "instagram":
                publish_live_review(
                    "正在检查多人互动/Speaking/真实生活场景。",
                    step="policy_scan",
                    preview_url=preview_url,
                    preview_urls=available_preview_urls,
                    cover_count=cover_count,
                )
                publish_live_review(
                    "正在检查受众年龄与种族匹配。",
                    step="style_scan",
                    preview_url=preview_url,
                    preview_urls=available_preview_urls,
                    cover_count=cover_count,
                )
                publish_live_review(
                    "正在检查跳舞/单人POV/绿幕排除项。",
                    step="risk_scan",
                    preview_url=preview_url,
                    preview_urls=available_preview_urls,
                    cover_count=cover_count,
                )
            elif platform == "tiktok":
                publish_live_review(
                    "正在检查家庭/宠物/户外场景匹配。",
                    step="policy_scan",
                    preview_url=preview_url,
                    preview_urls=available_preview_urls,
                    cover_count=cover_count,
                )
                publish_live_review(
                    "正在检查产品展示与生活场景。",
                    step="style_scan",
                    preview_url=preview_url,
                    preview_urls=available_preview_urls,
                    cover_count=cover_count,
                )
                publish_live_review(
                    "正在检查自拍/情侣占比排除项。",
                    step="risk_scan",
                    preview_url=preview_url,
                    preview_urls=available_preview_urls,
                    cover_count=cover_count,
                )
            else:  # youtube or default (Ulike)
                publish_live_review(
                    "正在检查竞品/低价平台合作痕迹。",
                    step="policy_scan",
                    preview_url=preview_url,
                    preview_urls=available_preview_urls,
                    cover_count=cover_count,
                )
                publish_live_review(
                    "正在检查暴露程度、纹身与画面生活质感。",
                    step="style_scan",
                    preview_url=preview_url,
                    preview_urls=available_preview_urls,
                    cover_count=cover_count,
                )
                publish_live_review(
                    "正在检查母婴倾向与过度商业化摆拍感。",
                    step="risk_scan",
                    preview_url=preview_url,
                    preview_urls=available_preview_urls,
                    cover_count=cover_count,
                )

            publish_live_review(
                "已提交给视觉模型，等待最终判定。",
                step="model_wait",
                preview_url=preview_url,
                preview_urls=available_preview_urls,
                cover_count=cover_count,
                reviewed_collage_count=reviewed_collage_count,
                reviewed_collage_urls=reviewed_preview_urls,
                unused_collage_count=unused_collage_count,
                collage_error_count=collage_error_count,
                applied_mode=applied_mode,
                downgrade_reason=downgrade_reason,
            )

            review = evaluate_cover_collage(username, collage_assets=effective_collage_assets, platform=platform)
            review["success"] = True
            results[username] = review
            if review.get("decision") == "Reject":
                rejected += 1
            else:
                passed += 1

            signal_text = "；".join(
                [str(item).strip() for item in (review.get("signals") or []) if str(item).strip()]
            )
            final_line = f"判定完成：{review.get('decision') or 'Pass'}。{review.get('reason') or '已完成视觉复核。'}"
            if signal_text:
                final_line = f"{final_line} 命中信号：{signal_text}"

            publish_live_review(
                final_line,
                tone="warning" if review.get("decision") == "Reject" else "success",
                step="completed",
                done=index,
                preview_url=preview_url,
                preview_urls=available_preview_urls,
                cover_count=cover_count,
                collage_count=collage_count,
                reviewed_collage_count=review.get("collage_count") or reviewed_collage_count,
                reviewed_collage_urls=reviewed_preview_urls,
                unused_collage_count=unused_collage_count,
                collage_error_count=collage_error_count,
                target_collage_count=target_collage_count,
                requested_mode=normalized_review_mode,
                recommended_mode=recommended_mode,
                applied_mode=review.get("applied_mode") or applied_mode,
                downgrade_reason=review.get("downgrade_reason") or downgrade_reason,
                provider=review.get("provider"),
                decision=review.get("decision"),
                reason=review.get("reason"),
                signals=review.get("signals") or [],
            )
            history_item = build_visual_review_history_item(current_live_review, success=True)
            if history_item is not None:
                review_history.append(history_item)
        except Exception as exc:
            failed += 1
            error_text = str(exc)
            results[username] = {
                "success": False,
                "username": username,
                "error": error_text
            }

            is_collage_failure = (
                str(current_live_review.get("step") or "").strip() in {"preparing", "collage_loading", "collage_progress"}
                or "封面图" in error_text
            )
            failure_step = "collage_failed" if is_collage_failure else "failed"
            failure_message = (
                error_text
                if is_collage_failure
                else f"判定失败：{error_text}"
            )

            publish_live_review(
                failure_message,
                tone="error",
                step=failure_step,
                done=index,
                decision="Error",
                reason=error_text,
            )
            history_item = build_visual_review_history_item(current_live_review, success=False)
            if history_item is not None:
                review_history.append(history_item)

    if progress_callback:
        progress_callback(
            "completed",
            f"视觉复核完成：通过 {passed}，拒绝 {rejected}，失败 {failed}",
            done=total,
            total=total,
            passed_count=passed,
            rejected_count=rejected,
            failed_count=failed,
            partial_result=build_visual_review_partial(
                results,
                total,
                passed,
                rejected,
                failed,
                current_live_review,
                review_history,
            ),
        )
    result = {
        "visual_results": results,
        "review_history": review_history,
        "summary": {
            "total": total,
            "passed": passed,
            "rejected": rejected,
            "failed": failed,
        },
        "live_review": current_live_review,
    }
    visual_artifact = save_visual_review_artifacts(
        platform,
        result,
        metadata=merge_saved_artifact_metadata(
            load_profile_review_artifact_metadata(platform),
            {
                "cached": False,
                "stale_result": False,
                "used_fallback": False,
                "raw_data_source": load_profile_review_artifact_metadata(platform).get("raw_data_source"),
                "source_path": get_visual_results_path(platform),
                "updated_at": iso_now(),
            },
        ),
    )
    result.update(build_saved_final_review_artifact_status(platform, visual_artifact=visual_artifact))
    return result


def start_background_job(job, runner):
    def target():
        progress_callback = build_job_progress_callback(job["id"])
        cancel_check = lambda: is_job_cancelled(job["id"])
        try:
            if cancel_check():
                update_job(
                    job["id"],
                    status="cancelled",
                    stage="cancelled",
                    message="任务已取消",
                )
                return
            update_job(job["id"], status="running", stage="starting", message="任务开始执行")
            result = runner(progress_callback, cancel_check)
            if cancel_check() or (isinstance(result, dict) and result.get("cancelled")):
                existing_job = get_job(job["id"]) or {}
                update_job(
                    job["id"],
                    status="cancelled",
                    stage="cancelled",
                    message=(result or {}).get("message", "用户取消"),
                    result=existing_job.get("result"),
                    error=None,
                )
                return
            if not isinstance(result, dict) or result.get("success", True):
                update_job(
                    job["id"],
                    status="completed",
                    stage="completed",
                    message=result.get("message") if isinstance(result, dict) else "任务执行完成",
                    result=result,
                    error=None,
                )
            else:
                update_job(
                    job["id"],
                    status="failed",
                    error=result.get("error") or "任务执行失败",
                    result=result,
                    stage="failed",
                    message=result.get("error") or "任务执行失败",
                )
        except Exception as exc:
            if cancel_check():
                update_job(
                    job["id"],
                    status="cancelled",
                    stage="cancelled",
                    message="任务已取消",
                    error=None,
                )
                return
            update_job(
                job["id"],
                status="failed",
                error=str(exc),
                stage="failed",
                message=str(exc),
            )

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread

@app.route('/api/templates/generate', methods=['POST'])
def generate_screening_templates_api():
    payload = request.get_json(silent=True) or {}
    sop_text = str(payload.get("sop_text") or "").strip()
    persist = payload.get("persist", True)

    if not sop_text:
        return jsonify({"success": False, "error": "sop_text 不能为空"}), 400

    if not isinstance(persist, bool):
        persist = str(persist).strip().lower() not in {"0", "false", "no"}

    try:
        template_generator = load_template_generator_module()
        output_dir = build_template_generation_output_dir() if persist else None
        generation = template_generator.generate_templates_from_text(sop_text, output_dir=output_dir)
        return jsonify({
            "success": True,
            "output_dir": generation.get("output_dir"),
            "parsed_sop": generation.get("parsed_sop") or {},
            "templates": generation.get("templates") or {},
            "summary_markdown": generation.get("summary_markdown") or "",
        })
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": f"审核模板生成失败：{exc}"}), 500


@app.route('/api/rulespec/compile', methods=['POST'])
def compile_rulespec_api():
    payload = request.get_json(silent=True) or {}
    sop_text = str(payload.get("sop_text") or "").strip()
    persist = payload.get("persist", True)

    if not sop_text:
        return jsonify({"success": False, "error": "sop_text 不能为空"}), 400

    if not isinstance(persist, bool):
        persist = str(persist).strip().lower() not in {"0", "false", "no"}

    try:
        compiler = load_rulespec_compiler_module()
        output_dir = build_rulespec_compile_output_dir() if persist else None
        compiled = compiler.compile_rulespec_from_text(sop_text, output_dir=output_dir)
        return jsonify({
            "success": True,
            "output_dir": compiled.get("output_dir"),
            "parsed_sop": compiled.get("parsed_sop") or {},
            "rule_spec": compiled.get("rule_spec") or {},
            "field_match_report": compiled.get("field_match_report") or {},
            "missing_capabilities": compiled.get("missing_capabilities") or {},
            "review_notes_markdown": compiled.get("review_notes_markdown") or "",
            "compiled_at": compiled.get("compiled_at"),
        })
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": f"RuleSpec 编译失败：{exc}"}), 500


@app.route('/api/jobs/scrape', methods=['POST'])
def start_scrape_job():
    payload = request.get_json(silent=True) or {}
    platform = str(payload.get("platform") or "").strip().lower()
    data = payload["payload"] if "payload" in payload else {}

    if platform not in {"tiktok", "instagram", "youtube"}:
        return jsonify({"success": False, "error": "平台参数无效"}), 400
    if not isinstance(data, dict):
        return jsonify({"success": False, "error": "payload 必须是对象"}), 400

    apify_config_error = validate_apify_runtime_config()
    if apify_config_error:
        return apify_config_error

    payload_signature = build_job_payload_signature("scrape", platform, data)
    duplicate_job = find_active_job("scrape", platform=platform, payload_signature=payload_signature)
    if duplicate_job:
        duplicate_job["message"] = duplicate_job.get("message") or "已有相同采集任务正在执行"
        return jsonify({
            "success": True,
            "duplicate_request": True,
            "job": duplicate_job,
        })

    conflicting_job = find_active_job("scrape", platform=platform)
    if conflicting_job:
        platform_label = {"tiktok": "TikTok", "instagram": "Instagram", "youtube": "YouTube"}.get(platform, platform)
        return jsonify({
            "success": False,
            "error_code": "SCRAPE_JOB_ALREADY_RUNNING",
            "error": (
                f"{platform_label} 当前已有采集任务在执行。"
                f"为避免重复扣费与覆盖同平台结果，请等待当前任务完成或先取消后再发起新的请求。"
            ),
            "job": conflicting_job,
        }), 409

    job = create_job(
        "scrape",
        platform=platform,
        message="采集任务已创建",
        payload_signature=payload_signature,
    )
    start_background_job(job, lambda progress_callback, cancel_check: perform_scrape(platform, data, progress_callback, cancel_check))
    return jsonify({"success": True, "job": get_job(job["id"])})


@app.route('/api/jobs/visual-review', methods=['POST'])
def start_visual_review_job():
    payload = request.get_json(silent=True) or {}
    profiles = payload.get("profiles") or []
    platform = payload.get("platform") or "tiktok"
    review_mode = normalize_visual_review_mode(payload.get("reviewMode"))

    if not isinstance(profiles, list) or len(profiles) == 0:
        return jsonify({"success": False, "error": "profiles 必须是非空数组"}), 400

    vision_config_error = validate_vision_runtime_config()
    if vision_config_error:
        return vision_config_error

    job = create_job("visual_review", message="视觉复核任务已创建")
    start_background_job(
        job,
        lambda progress_callback, cancel_check: perform_visual_review(
            job["id"],
            profiles,
            platform,
            review_mode,
            progress_callback,
            cancel_check,
        ),
    )
    return jsonify({"success": True, "job": get_job(job["id"])})


@app.route('/api/visual-review-preview/<preview_id>', methods=['GET'])
def get_visual_review_preview(preview_id):
    with VISUAL_PREVIEW_CACHE_LOCK:
        preview = VISUAL_PREVIEW_CACHE.get(preview_id)

    if not preview:
        return jsonify({"success": False, "error": "未找到视觉复核预览图"}), 404

    return send_file(
        BytesIO(preview["bytes"]),
        mimetype="image/jpeg",
        download_name=f"{preview_id}.jpg",
    )


@app.route('/api/jobs/<job_id>', methods=['GET'])
def get_job_status(job_id):
    job = get_job(job_id)
    if not job:
        return jsonify({"success": False, "error": "未找到任务"}), 404
    return jsonify({"success": True, "job": job})


@app.route('/api/jobs/<job_id>/cancel', methods=['POST'])
def cancel_job(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"success": False, "error": "未找到任务"}), 404
        if job["status"] in ("completed", "failed", "cancelled"):
            return jsonify({"success": False, "error": "任务已结束，无法取消"}), 400
        if job["status"] == "cancelling":
            return jsonify({"success": True, "job": dict(job)})

        job["status"] = "cancelling"
        job["stage"] = "cancelling"
        job["message"] = "正在取消任务"
        job["cancel_requested_at"] = job.get("cancel_requested_at") or iso_now()
        job["updated_at"] = iso_now()

    return jsonify({"success": True, "job": get_job(job_id)})

@app.route('/api/scrape/tiktok', methods=['POST'])
def scrape_tiktok():
    data = request.json
    result = perform_scrape("tiktok", data)
    return jsonify(result)

@app.route('/api/scrape/instagram', methods=['POST'])
def scrape_instagram():
    data = request.json
    result = perform_scrape("instagram", data)
    return jsonify(result)

@app.route('/api/scrape/youtube', methods=['POST'])
def scrape_youtube():
    data = request.json
    result = perform_scrape("youtube", data)
    return jsonify(result)

@app.route('/api/results/<platform>', methods=['GET'])
def get_results(platform):
    file_path = os.path.join(get_platform_dir(platform), f"{platform}_data.json")
    if not os.path.exists(file_path):
        return jsonify([])
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            raw_text = f.read().strip()
        if not raw_text:
            return jsonify([])

        start_idx = -1
        for i, char in enumerate(raw_text):
            if char in ['[', '{']:
                start_idx = i
                break
        if start_idx == -1:
            return jsonify([])

        data = json.loads(raw_text[start_idx:])
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/artifacts/<platform>/status', methods=['GET'])
def get_artifact_status(platform):
    if platform not in {"tiktok", "instagram", "youtube"}:
        return jsonify({"error": "Invalid platform"}), 400

    profile_review_artifact = load_latest_usable_profile_review_artifact(platform)
    visual_artifact = load_saved_visual_review_artifact(platform)
    payload = {
        "platform": platform,
        "profile_reviews_path": profile_review_artifact.get("path"),
        "profile_reviews_updated_at": profile_review_artifact.get("updated_at"),
        "visual_results_path": visual_artifact.get("visual_results_path"),
        "visual_results_updated_at": visual_artifact.get("updated_at"),
    }
    payload.update(build_saved_final_review_artifact_status(
        platform,
        profile_review_artifact=profile_review_artifact,
        visual_artifact=visual_artifact,
    ))
    return jsonify(payload)

@app.route('/api/download/<platform>/test-info', methods=['GET'])
def download_test_info(platform):
    import pandas as pd

    if platform not in {"tiktok", "instagram", "youtube"}:
        return jsonify({"error": "Invalid platform"}), 400

    raw_export_meta = load_raw_items_for_test_export(platform)
    raw_items = raw_export_meta.get("items") or []
    profile_reviews = load_profile_reviews(platform)
    metadata_lookup = load_upload_metadata(platform)

    if len(raw_items) == 0 and len(profile_reviews) == 0:
        return jsonify({"error": "No test data available to export"}), 404

    try:
        summary_rows = build_test_info_summary_rows(platform, profile_reviews, raw_items, metadata_lookup)
        raw_rows = build_test_info_raw_rows(
            platform,
            raw_items,
            profile_reviews,
            metadata_lookup,
            raw_export_meta=raw_export_meta,
        )

        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            pd.DataFrame(summary_rows).to_excel(writer, index=False, sheet_name='Account Review')
            pd.json_normalize(raw_rows, sep='.').to_excel(writer, index=False, sheet_name='Raw Apify Data')
        output.seek(0)

        return send_file(
            output,
            as_attachment=True,
            download_name=f"{platform}_test_info.xlsx",
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/download/<platform>/test-info-json', methods=['GET'])
def download_test_info_json(platform):
    if platform not in {"tiktok", "instagram", "youtube"}:
        return jsonify({"error": "Invalid platform"}), 400

    raw_export_meta = load_raw_items_for_test_export(platform)
    raw_items = raw_export_meta.get("items") or []
    profile_reviews = load_profile_reviews(platform)
    metadata_lookup = load_upload_metadata(platform)

    if len(raw_items) == 0 and len(profile_reviews) == 0 and len(metadata_lookup) == 0:
        return jsonify({"error": "No test data available to export"}), 404

    payload = build_test_info_json_payload(
        platform,
        profile_reviews,
        raw_items,
        metadata_lookup,
        raw_export_meta=raw_export_meta,
    )

    return app.response_class(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        mimetype='application/json',
        headers={
            'Content-Disposition': f'attachment; filename={platform}_test_info.json'
        },
    )


@app.route('/api/download/<platform>/<format>', methods=['GET'])
def download_results(platform, format):
    if platform not in {"tiktok", "instagram", "youtube"}:
        return "Invalid platform", 400

    platform_dir = get_platform_dir(platform)
    json_path = os.path.join(platform_dir, f"{platform}_data.json")
    raw_artifact = load_latest_usable_scrape_artifact(platform, json_path)
    raw_items = raw_artifact.get("items") or []
    if not raw_items:
        return "File not found", 404
        
    if format == "json":
        return app.response_class(
            json.dumps(raw_items, ensure_ascii=False, indent=2, allow_nan=False),
            mimetype='application/json',
            headers={
                'Content-Disposition': f'attachment; filename={platform}_data.json'
            },
        )
    elif format == "excel":
        import pandas as pd

        try:
            df = pd.json_normalize(raw_items)
            excel_path = os.path.join(platform_dir, f"{platform}_data.xlsx")
            df.to_excel(excel_path, index=False)
            return send_file(excel_path, as_attachment=True)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    return "Invalid format", 400

@app.route('/api/download/<platform>/image-review', methods=['GET'])
def download_image_review(platform):
    import pandas as pd

    try:
        artifact = load_latest_usable_profile_review_artifact(platform)
        profile_reviews = artifact.get("profile_reviews") or []

        if not isinstance(profile_reviews, list) or len(profile_reviews) == 0:
            return jsonify({"error": "Profile review data is empty"}), 400

        rows = build_image_review_rows(platform, profile_reviews, artifact_metadata=artifact)
        df = pd.DataFrame(rows)
        platform_dir = get_platform_dir(platform)
        excel_path = os.path.join(platform_dir, f"{platform}_image_review.xlsx")
        df.to_excel(excel_path, index=False)
        return send_file(excel_path, as_attachment=True)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/download/<platform>/prescreen-review', methods=['GET'])
def download_prescreen_review(platform):
    import pandas as pd

    try:
        artifact = load_latest_usable_profile_review_artifact(platform)
        profile_reviews = artifact.get("profile_reviews") or []

        if not isinstance(profile_reviews, list) or len(profile_reviews) == 0:
            return jsonify({"error": "Profile review data is empty"}), 400

        rows = build_prescreen_review_rows(platform, profile_reviews, artifact_metadata=artifact)
        df = pd.DataFrame(rows)
        platform_dir = get_platform_dir(platform)
        excel_path = os.path.join(platform_dir, f"{platform}_prescreen_review.xlsx")
        df.to_excel(excel_path, index=False)
        return send_file(excel_path, as_attachment=True)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/download/<platform>/final-review', methods=['POST'])
def download_final_review(platform):
    import pandas as pd

    if platform not in {"tiktok", "instagram", "youtube"}:
        return jsonify({"error": "Invalid platform"}), 400

    payload = request.get_json(silent=True) or {}

    try:
        resolved_payload = resolve_final_review_export_payload(platform, payload)
        profile_reviews = resolved_payload.get("profile_reviews") or []
        visual_results = resolved_payload.get("visual_results") or {}
        if len(profile_reviews) == 0:
            return jsonify({"error": "No profile review data available to export"}), 400

        rows = build_final_review_rows(
            platform,
            profile_reviews,
            visual_results,
            artifact_metadata=resolved_payload.get("artifact_metadata"),
        )
        if len(rows) == 0:
            return jsonify({"error": "No final review rows available to export"}), 400

        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            pd.DataFrame(rows).to_excel(writer, index=False, sheet_name='Final Review')
        output.seek(0)

        return send_file(
            output,
            as_attachment=True,
            download_name=f"{platform}_final_review.xlsx",
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    debug_enabled = os.getenv("FLASK_DEBUG", "1") == "1"
    use_reloader = os.getenv("FLASK_USE_RELOADER", "1") == "1"
    app.run(debug=debug_enabled, use_reloader=use_reloader, host=BACKEND_BIND_HOST, port=BACKEND_PORT)
