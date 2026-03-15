from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import base64
from io import BytesIO
import json
import os
import re
import subprocess
import tempfile
import threading
import time
from datetime import datetime
import uuid

from openai import OpenAI
from PIL import Image, ImageOps
import requests
from werkzeug.utils import secure_filename

app = Flask(__name__)
# Enable CORS for all routes and origins to fix "Failed to fetch" issues during development
CORS(app, resources={r"/*": {"origins": "*"}})

OPENAI_BASE_URL = "https://gpt.auto-code.net/rust/openai/v1"
OPENAI_MODEL = os.getenv("VISION_MODEL", "gpt-5.4")
OPENAI_API_KEY_PLACEHOLDER = "YOUR_API_KEY_HERE"
VISION_REQUEST_TIMEOUT = 30
COLLAGE_TILE_SIZE = 256
COLLAGE_GAP = 8
APIFY_API_BASE = "https://api.apify.com/v2"
APIFY_REQUEST_TIMEOUT = 60
APIFY_POLL_INTERVAL_SECONDS = 5
APIFY_MIN_WAIT_SECONDS = 180
APIFY_MAX_WAIT_SECONDS = 900
APIFY_COMMAND_TIMEOUT_SECONDS = 900
ALLOWED_APIFY_ACTORS = {
    "clockworks/tiktok-profile-scraper",
    "apify/instagram-profile-scraper",
    "streamers/youtube-scraper",
}
VISION_PROMPT = """你是 Ulike 达人初筛流程中的视觉复核员。输入图片是一位博主最近最多 9 张封面拼成的 3x3 九宫格。

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

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

UPLOAD_FOLDER = os.path.join(DATA_DIR, 'uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

JOBS = {}
JOBS_LOCK = threading.Lock()


def iso_now():
    return datetime.utcnow().isoformat() + "Z"


def create_job(job_type, platform=None, message="任务已创建"):
    job_id = str(uuid.uuid4())
    job = {
        "id": job_id,
        "type": job_type,
        "platform": platform,
        "status": "queued",
        "stage": "queued",
        "message": message,
        "progress": {"done": 0, "total": None},
        "result": None,
        "error": None,
        "created_at": iso_now(),
        "updated_at": iso_now(),
    }
    with JOBS_LOCK:
        JOBS[job_id] = job
    return job


def update_job(job_id, **fields):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return None
        progress = fields.pop("progress", None)
        if progress is not None:
            job["progress"] = {
                "done": progress.get("done", job.get("progress", {}).get("done", 0)),
                "total": progress.get("total", job.get("progress", {}).get("total")),
            }
        job.update(fields)
        job["updated_at"] = iso_now()
        return dict(job)


def get_job(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        return dict(job) if job else None


def is_job_cancelled(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        return bool(job and job.get("status") == "cancelled")


def build_cancelled_result(message="用户取消"):
    return {
        "success": False,
        "cancelled": True,
        "error": message,
        "message": message,
    }


def build_job_progress_callback(job_id):
    def callback(stage, message=None, done=None, total=None, **extra):
        if is_job_cancelled(job_id):
            return get_job(job_id)
        payload = {
            "status": "running",
            "stage": stage,
            "message": message or stage,
        }
        if done is not None or total is not None:
            current_progress = get_job(job_id).get("progress", {}) if get_job(job_id) else {}
            payload["progress"] = {
                "done": done if done is not None else current_progress.get("done", 0),
                "total": total if total is not None else current_progress.get("total"),
            }
        if extra:
            payload.update(extra)
        update_job(job_id, **payload)
    return callback


def get_openai_api_key():
    env_key = os.getenv("OPENAI_API_KEY")
    if env_key:
        return env_key

    script_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scripts",
        "test_openai_vision.py",
    )
    if os.path.exists(script_path):
        try:
            with open(script_path, "r", encoding="utf-8") as f:
                text = f.read()
            match = re.search(r'API_KEY\s*=\s*"([^"]+)"', text)
            if match:
                script_key = match.group(1).strip()
                if script_key and script_key != OPENAI_API_KEY_PLACEHOLDER:
                    return script_key
        except Exception:
            pass

    return OPENAI_API_KEY_PLACEHOLDER


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


def download_image_bytes(url):
    response = requests.get(
        url,
        timeout=VISION_REQUEST_TIMEOUT,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    response.raise_for_status()
    return response.content


def load_remote_image(url):
    image_bytes = download_image_bytes(url)
    with Image.open(BytesIO(image_bytes)) as image:
        return image.convert("RGB")


def build_cover_collage(cover_urls):
    valid_urls = [str(url).strip() for url in cover_urls if str(url).strip()][:9]
    if not valid_urls:
        raise ValueError("No cover URLs provided")

    canvas_size = COLLAGE_TILE_SIZE * 3 + COLLAGE_GAP * 4
    collage = Image.new("RGB", (canvas_size, canvas_size), (245, 245, 245))

    for idx, url in enumerate(valid_urls):
        image = load_remote_image(url)
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

    return collage, len(valid_urls)


def collage_to_data_url(collage):
    buffer = BytesIO()
    collage.save(buffer, format="JPEG", quality=88)
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{encoded}"


def evaluate_cover_collage(username, cover_urls):
    api_key = get_openai_api_key()
    if not api_key or api_key == OPENAI_API_KEY_PLACEHOLDER:
        raise ValueError("OPENAI_API_KEY is not configured")

    collage, cover_count = build_cover_collage(cover_urls)
    image_data_url = collage_to_data_url(collage)
    client = OpenAI(api_key=api_key, base_url=OPENAI_BASE_URL)
    response = client.responses.create(
        model=OPENAI_MODEL,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": f"博主用户名：{username}\n{VISION_PROMPT}"},
                    {"type": "input_image", "image_url": image_data_url},
                ],
            }
        ],
    )
    raw_text = extract_response_text(response)
    parsed = parse_visual_review_result(raw_text)
    parsed["raw_text"] = raw_text
    parsed["cover_count"] = cover_count
    return parsed

# Helper to get platform data directory
def get_platform_dir(platform):
    path = os.path.join(DATA_DIR, platform)
    if not os.path.exists(path):
        os.makedirs(path)
    return path

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
    return str(value).strip().lower().lstrip('@')

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

def build_image_review_rows(platform, profile_reviews):
    rows = []
    for item in profile_reviews:
        covers = item.get('covers') or []
        row = {
            'platform': platform,
            'username': item.get('username'),
            'profile_url': item.get('profile_url'),
            'stage_status': get_review_stage_label(item.get('status'), item.get('reason')),
            'stage_reason': item.get('reason'),
            'latest_post_time': item.get('latest_post_time'),
            'soft_flags': format_soft_flags_for_export(item.get('soft_flags')),
            'cover_count': len(covers),
        }
        for idx in range(9):
            row[f'cover_{idx + 1}'] = covers[idx] if idx < len(covers) else ''
        rows.append(row)
    return rows


def load_profile_reviews(platform):
    profile_reviews_path = os.path.join(get_platform_dir(platform), f"{platform}_profile_reviews.json")
    if not os.path.exists(profile_reviews_path):
        return []

    try:
        with open(profile_reviews_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


@app.route('/api/evaluate_influencer', methods=['POST'])
def evaluate_influencer():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username") or "").strip()
    cover_urls = payload.get("cover_urls") or []

    if not username:
        return jsonify({"success": False, "error": "username is required"}), 400
    if not isinstance(cover_urls, list) or len(cover_urls) == 0:
        return jsonify({"success": False, "error": "cover_urls must be a non-empty array"}), 400

    started_at = time.perf_counter()
    try:
        review = evaluate_cover_collage(username, cover_urls)
        elapsed = time.perf_counter() - started_at
        return jsonify({
            "success": True,
            "username": username,
            "model": OPENAI_MODEL,
            "elapsed_seconds": round(elapsed, 2),
            "decision": review["decision"],
            "reason": review["reason"],
            "signals": review["signals"],
            "raw_text": review["raw_text"],
            "cover_count": review["cover_count"],
        })
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except requests.RequestException as exc:
        return jsonify({"success": False, "error": f"Failed to download cover images: {exc}"}), 502
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500

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
            # Check if header exists by reading first few rows
            # If the first row looks like a URL, then no header
            temp_df = pd.read_excel(filepath, header=None, nrows=5)
            first_cell = str(temp_df.iloc[0, 0]).strip()
            
            if first_cell.startswith('http'):
                # No header, treat first row as data
                df = pd.read_excel(filepath, header=None)
                df.columns = ['content']
            else:
                # Has header
                df = pd.read_excel(filepath)
                # Ensure we have a content column
                if 'content' not in df.columns:
                    # Fallback: use the first column as content
                    df.rename(columns={df.columns[0]: 'content'}, inplace=True)

            # Define classification function
            def get_platform(url):
                if not isinstance(url, str):
                    return 'Unknown'
                u = url.lower()
                if 'tiktok.com' in u:
                    return 'TikTok'
                elif 'instagram.com' in u:
                    return 'Instagram'
                elif 'youtube.com' in u or 'youtu.be' in u:
                    return 'YouTube'
                return 'Unknown'

            # Apply classification
            df['Platform'] = df['content'].apply(get_platform)
            
            # Save processed file
            # df.to_excel(processed_path, index=False) # REMOVED: Writing back to excel is extremely slow and not used by the frontend
            processed_filename = f"processed_{filename}"
            
            # Prepare response data
            stats = df['Platform'].value_counts().to_dict()
            preview = df.head(5).to_dict(orient='records')
            
            # Group URLs by platform
            grouped_data = {
                'tiktok': df[df['Platform'] == 'TikTok']['content'].tolist(),
                'instagram': df[df['Platform'] == 'Instagram']['content'].tolist(),
                'youtube': df[df['Platform'] == 'YouTube']['content'].tolist()
            }
            
            return jsonify({
                "success": True,
                "filename": processed_filename,
                "stats": stats,
                "preview": preview,
                "grouped_data": grouped_data
            })
            
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
    env_token = os.getenv("APIFY_TOKEN") or os.getenv("APIFY_API_TOKEN")
    if env_token:
        return env_token

    auth_file = os.path.expanduser("~/.apify/auth.json")
    try:
        with open(auth_file, 'r') as f:
            return json.load(f).get('token')
    except Exception:
        return None

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


def build_apify_cost_summary_text(cost_available, usage_total_usd, execution_method, note=None):
    if note:
        return note
    if cost_available and isinstance(usage_total_usd, (int, float)):
        return f"本次 Apify 预估费用：{round(float(usage_total_usd), 6)} 美元。"
    if execution_method == "cli":
        return "当前 CLI 执行路径暂未返回单次运行费用。"
    return "本次 Apify 运行已完成，但暂未返回费用数据。"


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

def finalize_apify_output(output_filename, output_file_path, identifiers, skipped_count, progress_callback=None, apify_summary=None):
    platform_dir = get_platform_dir(output_filename)

    if not os.path.exists(output_file_path):
        return {"success": False, "error": "Output file not found"}

    data = load_json_payload(output_file_path)
    if data is None:
        return {"success": False, "error": f"Output file is empty or invalid JSON: {output_file_path}"}
    if not isinstance(data, list):
        data = [data]

    import sys
    scripts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
    if scripts_dir not in sys.path:
        sys.path.append(scripts_dir)
    import data_cleaner

    if progress_callback:
        progress_callback("filtering", "正在执行初筛与结果整理", done=3, total=4)

    filter_result = data_cleaner.filter_and_save_dataset(output_file_path, output_filename, identifiers)
    profile_reviews = filter_result.get("profile_reviews", [])
    profile_reviews_path = os.path.join(platform_dir, f"{output_filename}_profile_reviews.json")
    with open(profile_reviews_path, 'w') as f:
        json.dump(profile_reviews, f, indent=2)

    returned_profile_keys = {
        normalize_identifier(profile)
        for profile in filter_result.get("returned_profiles", [])
        if normalize_identifier(profile)
    }
    successful_identifiers = [
        ident for ident in identifiers
        if normalize_identifier(ident) in returned_profile_keys
    ]
    if successful_identifiers:
        update_history(output_filename, successful_identifiers)

    result = {
        "success": True,
        "cached": False,
        "count": len(data),
        "file": output_file_path,
        "profile_reviews_file": profile_reviews_path,
        "profile_reviews": profile_reviews,
        "filter_stats": filter_result,
        "rejected_profiles": filter_result.get("rejected_profiles", []),
        "rejected_count": filter_result.get("rejected_profiles_count", 0),
        "message": f"抓取了 {len(identifiers)} 个新账号，跳过了 {skipped_count} 个命中缓存的账号。"
    }
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
        profile_reviews = filter_result.get("profile_reviews", [])
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

def run_apify_rest_command(actor_id, input_data, output_filename, force_refresh=False, progress_callback=None, cancel_check=None):
    if actor_id not in ALLOWED_APIFY_ACTORS:
        return {"success": False, "error": f"不允许调用该 Actor：{actor_id}"}

    platform_dir = get_platform_dir(output_filename)
    input_file_path = os.path.join(platform_dir, f"{output_filename}_input.json")
    output_file_path = os.path.join(platform_dir, f"{output_filename}_data.json")

    identifiers = get_scrape_identifiers(output_filename, input_data)
    original_identifiers = list(identifiers)

    if cancel_check and cancel_check():
        return build_cancelled_result()

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
        cached_data = load_json_payload(output_file_path)
        if cached_data is not None:
            if not isinstance(cached_data, list):
                cached_data = [cached_data]
            profile_reviews = load_profile_reviews(output_filename)
            if progress_callback:
                progress_callback("completed", "命中缓存，已返回最近结果", done=4, total=4)
            return {
                "success": True,
                "cached": True,
                "count": len(cached_data),
                "file": output_file_path,
                "profile_reviews": profile_reviews,
                "message": f"本次有 {skipped_count} 个账号命中缓存，当前展示的是最近一次采集结果。勾选“强制刷新缓存”可重新采集。"
            }

        print(f"缓存文件为空或无效，准备重新抓取：{output_file_path}")
        identifiers = list(original_identifiers)
        set_scrape_identifiers(output_filename, input_data, identifiers)
        skipped_count = 0

    with open(input_file_path, 'w') as f:
        json.dump(input_data, f, indent=2)

    token = get_apify_token()
    if not token:
        return {"success": False, "error": "未配置 Apify token"}

    actor_ref = actor_id.replace("/", "~")
    run_url = f"{APIFY_API_BASE}/acts/{actor_ref}/runs"

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
        start_resp = requests.post(
            run_url,
            params={"token": token},
            json=input_data,
            timeout=APIFY_REQUEST_TIMEOUT,
        )
        if start_resp.status_code not in (200, 201):
            return {"success": False, "error": f"启动 Apify 任务失败：{start_resp.text}"}

        run_info = (start_resp.json() or {}).get('data', {})
        run_id = run_info.get('id')
        dataset_id = run_info.get('defaultDatasetId')
        if not run_id or not dataset_id:
            return {"success": False, "error": "Apify API 未返回 run_id 或 dataset_id"}

        status_url = f"{APIFY_API_BASE}/actor-runs/{run_id}"
        final_status = None
        max_wait_seconds = max(APIFY_MIN_WAIT_SECONDS, min(APIFY_MAX_WAIT_SECONDS, len(identifiers) * 45))
        started_polling_at = time.monotonic()
        while (time.monotonic() - started_polling_at) < max_wait_seconds:
            if cancel_check and cancel_check():
                return build_cancelled_result()
            status_resp = requests.get(
                status_url,
                params={"token": token},
                timeout=APIFY_REQUEST_TIMEOUT,
            )
            if status_resp.status_code != 200:
                return {"success": False, "error": f"获取运行状态失败：{status_resp.text}"}

            final_run_data = (status_resp.json() or {}).get('data') or {}
            final_status = final_run_data.get('status')
            if final_status == 'SUCCEEDED':
                break
            if final_status in ('FAILED', 'ABORTED', 'TIMED-OUT'):
                return {"success": False, "error": f"Apify 运行失败：{translate_apify_status(final_status)}"}
            if progress_callback:
                progress_callback(
                    "apify_running",
                    f"Apify 运行中：{translate_apify_status(final_status)}",
                    done=1,
                    total=4,
                    **build_target_preview(identifiers),
                )
            time.sleep(APIFY_POLL_INTERVAL_SECONDS)
        else:
            waited_seconds = int(time.monotonic() - started_polling_at)
            return {
                "success": False,
                "error": f"API 本地运行超时，等待成功状态。已等待约 {waited_seconds} 秒，本次批量 {len(identifiers)} 个博主/链接。"
            }

        dataset_url = f"{APIFY_API_BASE}/datasets/{dataset_id}/items"
        if progress_callback:
            progress_callback(
                "downloading",
                "正在下载数据集结果",
                done=2,
                total=4,
                **build_target_preview(identifiers),
            )
        if cancel_check and cancel_check():
            return build_cancelled_result()
        dataset_resp = requests.get(
            dataset_url,
            params={"token": token},
            timeout=APIFY_REQUEST_TIMEOUT,
        )
        if dataset_resp.status_code != 200:
            return {"success": False, "error": f"下载数据集失败：{dataset_resp.text}"}

        items = dataset_resp.json()
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
        )
        if result.get("success"):
            result["raw_items"] = items
        return result
    except requests.RequestException as e:
        return {"success": False, "error": f"Apify REST 请求失败：{e}"}

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
        cached_data = load_json_payload(output_file_path)
        if cached_data is not None:
            if not isinstance(cached_data, list):
                cached_data = [cached_data]
            profile_reviews = load_profile_reviews(output_filename)
            if progress_callback:
                progress_callback("completed", "命中缓存，已返回最近结果", done=4, total=4)
            return {
                "success": True,
                "cached": True,
                "count": len(cached_data),
                "file": output_file_path,
                "profile_reviews": profile_reviews,
                "message": f"本次有 {skipped_count} 个账号命中缓存，当前展示的是最近一次采集结果。勾选“强制刷新缓存”可重新采集。"
            }

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
        )
            
    except subprocess.CalledProcessError as e:
        print(f"命令执行失败：{e.stderr}")
        return {"success": False, "error": f"命令执行失败：{e.stderr}"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"命令执行超时：已超过 {APIFY_COMMAND_TIMEOUT_SECONDS} 秒"}
    except Exception as e:
        print(f"发生异常：{str(e)}")
        return {"success": False, "error": str(e)}


def perform_scrape(platform, data, progress_callback=None, cancel_check=None):
    force_refresh = data.get("forceRefresh", False)

    if platform == 'tiktok':
        input_data = {
            "profiles": data.get("profiles", []),
            "resultsPerPage": int(data.get("limit", 20)),
            "excludePinnedPosts": data.get("excludePinnedPosts", False),
            "shouldDownloadVideos": data.get("downloadVideos", False),
            "shouldDownloadCovers": data.get("downloadCovers", False),
            "shouldDownloadAvatars": data.get("downloadAvatars", False),
            "shouldDownloadSlideshowImages": data.get("downloadSlideshow", False),
            "shouldDownloadSubtitles": data.get("downloadSubtitles", False)
        }
        return run_apify_command("clockworks/tiktok-profile-scraper", input_data, "tiktok", force_refresh, progress_callback, cancel_check=cancel_check)

    if platform == 'instagram':
        input_data = {
            "usernames": data.get("usernames", []),
            "includeAboutSection": data.get("includeAbout", False)
        }
        return run_apify_command("apify/instagram-profile-scraper", input_data, "instagram", force_refresh, progress_callback, cancel_check=cancel_check)

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

        if len(identifiers) <= 5:
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
            cached_data = load_json_payload(output_file_path)
            if cached_data is not None:
                if not isinstance(cached_data, list):
                    cached_data = [cached_data]
                profile_reviews = load_profile_reviews("youtube")
                message = f"本次有 {skipped_count} 个账号命中缓存，当前展示的是最近一次采集结果。勾选“强制刷新缓存”可重新采集。"
                if progress_callback:
                    progress_callback("completed", "命中缓存，已返回最近结果", done=4, total=4)
                return {
                    "success": True,
                    "cached": True,
                    "count": len(cached_data),
                    "file": output_file_path,
                    "profile_reviews": profile_reviews,
                    "message": message
                }

            identifiers = list(original_identifiers)
            skipped_count = 0

        batched_identifiers = chunk_list(identifiers, 5)
        aggregated_items = []
        aggregate_success_count = 0
        failed_batches = []
        successful_identifiers = []
        apify_runs = []
        apify_total_cost = 0.0
        has_apify_cost = False

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
                failed_batches.append({
                    "batch_index": batch_index,
                    "batch_total": len(batched_identifiers),
                    "identifiers": batch,
                    "error": batch_error,
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
                continue

            batch_items = batch_result.get("raw_items") or []
            if not isinstance(batch_items, list):
                batch_items = [batch_items]
            aggregated_items.extend(batch_items)
            aggregate_success_count += 1
            successful_identifiers.extend(batch)
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
                    f"第 {batch_index}/{len(batched_identifiers)} 批完成，已累计 {len(aggregated_items)} 条数据",
                    done=batch_index,
                    total=len(batched_identifiers),
                    batch_index=batch_index,
                    batch_total=len(batched_identifiers),
                    batch_size=len(batch),
                    **build_target_preview(batch),
                    partial_result=partial_result,
                )

        if aggregate_success_count == 0:
            error_message = failed_batches[0]["error"] if failed_batches else "YouTube batch scrape failed"
            return {
                "success": False,
                "error": error_message,
                "failed_batches": failed_batches,
            }

        with open(output_file_path, 'w', encoding='utf-8') as f:
            json.dump(aggregated_items, f, indent=2, ensure_ascii=False)

        result = finalize_apify_output("youtube", output_file_path, successful_identifiers, skipped_count, None)
        if not result.get("success"):
            return result

        result["failed_batches"] = failed_batches
        result["successful_batches"] = aggregate_success_count
        result["batch_summary"] = {
            "total": len(batched_identifiers),
            "successful": aggregate_success_count,
            "failed": len(failed_batches),
        }
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
                f"YouTube 分批采集完成，共 {aggregate_success_count}/{len(batched_identifiers)} 批成功；"
                f"{len(failed_batches)} 批失败，当前仅展示成功批次结果。"
            )
        else:
            result["message"] = f"YouTube 分批采集完成，共 {aggregate_success_count}/{len(batched_identifiers)} 批成功"
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


def perform_visual_review(profiles, progress_callback=None, cancel_check=None):
    total = len(profiles)
    results = {}
    passed = 0
    rejected = 0
    failed = 0

    for index, item in enumerate(profiles, start=1):
        if cancel_check and cancel_check():
            return build_cancelled_result()
        username = str(item.get("username") or f"profile-{index}").strip()
        cover_urls = item.get("covers") or item.get("cover_urls") or []
        if progress_callback:
            progress_callback(
                "visual_reviewing",
                f"正在复核 {username}（{index}/{total}）",
                done=index - 1,
                total=total,
                current_username=username,
            )
        try:
            review = evaluate_cover_collage(username, cover_urls)
            review["success"] = True
            results[username] = review
            if review.get("decision") == "Reject":
                rejected += 1
            else:
                passed += 1
        except Exception as exc:
            failed += 1
            results[username] = {
                "success": False,
                "username": username,
                "error": str(exc)
            }
        if progress_callback:
            progress_callback(
                "visual_reviewing",
                f"正在复核 {username}（{index}/{total}）",
                done=index,
                total=total,
                current_username=username,
                passed_count=passed,
                rejected_count=rejected,
                failed_count=failed,
            )

    if progress_callback:
        progress_callback(
            "completed",
            f"视觉复核完成：通过 {passed}，拒绝 {rejected}，失败 {failed}",
            done=total,
            total=total,
            passed_count=passed,
            rejected_count=rejected,
            failed_count=failed,
        )
    return {
        "visual_results": results,
        "summary": {
            "total": total,
            "passed": passed,
            "rejected": rejected,
            "failed": failed,
        }
    }


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
                    message="用户取消",
                    result=None,
                    error=None,
                )
                return
            update_job(job["id"], status="running", stage="starting", message="任务开始执行")
            result = runner(progress_callback, cancel_check)
            if cancel_check() or (isinstance(result, dict) and result.get("cancelled")):
                update_job(
                    job["id"],
                    status="cancelled",
                    stage="cancelled",
                    message=(result or {}).get("message", "用户取消"),
                    result=None,
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
                    message="用户取消",
                    result=None,
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

@app.route('/api/jobs/scrape', methods=['POST'])
def start_scrape_job():
    payload = request.get_json(silent=True) or {}
    platform = str(payload.get("platform") or "").strip().lower()
    data = payload.get("payload") or {}

    if platform not in {"tiktok", "instagram", "youtube"}:
        return jsonify({"success": False, "error": "平台参数无效"}), 400
    if not isinstance(data, dict):
        return jsonify({"success": False, "error": "payload 必须是对象"}), 400

    job = create_job("scrape", platform=platform, message="采集任务已创建")
    start_background_job(job, lambda progress_callback, cancel_check: perform_scrape(platform, data, progress_callback, cancel_check))
    return jsonify({"success": True, "job": get_job(job["id"])})


@app.route('/api/jobs/visual-review', methods=['POST'])
def start_visual_review_job():
    payload = request.get_json(silent=True) or {}
    profiles = payload.get("profiles") or []

    if not isinstance(profiles, list) or len(profiles) == 0:
        return jsonify({"success": False, "error": "profiles 必须是非空数组"}), 400

    job = create_job("visual_review", message="视觉复核任务已创建")
    start_background_job(job, lambda progress_callback, cancel_check: perform_visual_review(profiles, progress_callback, cancel_check))
    return jsonify({"success": True, "job": get_job(job["id"])})


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

        job["status"] = "cancelled"
        job["stage"] = "cancelled"
        job["message"] = "用户取消"
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

@app.route('/api/download/<platform>/<format>', methods=['GET'])
def download_results(platform, format):
    platform_dir = get_platform_dir(platform)
    json_path = os.path.join(platform_dir, f"{platform}_data.json")
    if not os.path.exists(json_path):
        return "File not found", 404
        
    if format == "json":
        return send_file(json_path, as_attachment=True)
    elif format == "excel":
        import pandas as pd

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                raw_text = f.read().strip()
            if not raw_text:
                return jsonify({"error": "No data available to export"}), 400

            start_idx = -1
            for i, char in enumerate(raw_text):
                if char in ['[', '{']:
                    start_idx = i
                    break

            if start_idx == -1:
                return jsonify({"error": "Invalid JSON content"}), 400

            data = json.loads(raw_text[start_idx:])
            if isinstance(data, dict):
                data = [data]
            elif not isinstance(data, list):
                data = [data]

            df = pd.json_normalize(data)
            excel_path = os.path.join(platform_dir, f"{platform}_data.xlsx")
            df.to_excel(excel_path, index=False)
            return send_file(excel_path, as_attachment=True)
        except json.JSONDecodeError as e:
            return jsonify({"error": f"Invalid JSON format: {str(e)}"}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    return "Invalid format", 400

@app.route('/api/download/<platform>/image-review', methods=['GET'])
def download_image_review(platform):
    import pandas as pd

    platform_dir = get_platform_dir(platform)
    profile_reviews_path = os.path.join(platform_dir, f"{platform}_profile_reviews.json")
    if not os.path.exists(profile_reviews_path):
        return jsonify({"error": "No profile review data available to export"}), 404

    try:
        with open(profile_reviews_path, 'r', encoding='utf-8') as f:
            profile_reviews = json.load(f)

        if not isinstance(profile_reviews, list) or len(profile_reviews) == 0:
            return jsonify({"error": "Profile review data is empty"}), 400

        rows = build_image_review_rows(platform, profile_reviews)
        df = pd.DataFrame(rows)
        excel_path = os.path.join(platform_dir, f"{platform}_image_review.xlsx")
        df.to_excel(excel_path, index=False)
        return send_file(excel_path, as_attachment=True)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    debug_enabled = os.getenv("FLASK_DEBUG", "1") == "1"
    use_reloader = os.getenv("FLASK_USE_RELOADER", "1") == "1"
    app.run(debug=debug_enabled, use_reloader=use_reloader, host='0.0.0.0', port=5001)
