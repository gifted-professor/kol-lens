import json
import os
import time
import traceback

from openai import OpenAI


API_KEY = (
    os.getenv("VISION_SMOKE_API_KEY")
    or os.getenv("VISION_LEMONAPI_API_KEY")
    or os.getenv("OPENAI_API_KEY")
)
BASE_URL = (
    os.getenv("VISION_SMOKE_BASE_URL")
    or os.getenv("VISION_LEMONAPI_BASE_URL")
    or os.getenv("VISION_AUTO_CODE_BASE_URL", "https://gpt.auto-code.net/rust/openai/v1")
)
MODEL = (
    os.getenv("VISION_SMOKE_MODEL")
    or os.getenv("VISION_LEMONAPI_MODEL")
    or os.getenv("VISION_MODEL")
    or "gpt-5.4"
)
API_STYLE = (os.getenv("VISION_SMOKE_API_STYLE") or "responses").strip().lower()
TIMEOUT = float(os.getenv("VISION_SMOKE_TIMEOUT") or "30")
IMAGE_URL = "https://raw.githubusercontent.com/github/explore/main/topics/python/python.png"
PROMPT = "请用一句话描述这张图里有没有人"


def extract_text_from_sse(raw_text: str) -> str:
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


def extract_response_text(response) -> str:
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
        dumped = response.model_dump()
        if isinstance(dumped, dict):
            return json.dumps(dumped, ensure_ascii=False, indent=2)

    return str(response)


def extract_chat_completion_text(response) -> str:
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
        dumped = response.model_dump()
        if isinstance(dumped, dict):
            return json.dumps(dumped, ensure_ascii=False, indent=2)

    if isinstance(response, dict):
        return json.dumps(response, ensure_ascii=False, indent=2)

    return str(response)


def main() -> None:
    if not API_KEY:
        print("Missing smoke-test API key. Set VISION_SMOKE_API_KEY, VISION_LEMONAPI_API_KEY, or OPENAI_API_KEY.")
        raise SystemExit(1)

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL, timeout=TIMEOUT)

    started_at = time.perf_counter()
    try:
        if API_STYLE == "chat_completions":
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": PROMPT},
                            {"type": "image_url", "image_url": {"url": IMAGE_URL}},
                        ],
                    }
                ],
            )
            result_text = extract_chat_completion_text(response)
        else:
            response = client.responses.create(
                model=MODEL,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": PROMPT},
                            {"type": "input_image", "image_url": IMAGE_URL},
                        ],
                    }
                ],
            )
            result_text = extract_response_text(response)
        elapsed = time.perf_counter() - started_at
        print(f"Elapsed: {elapsed:.2f}s")
        print(f"API style: {API_STYLE}")
        print(f"Model: {MODEL}")
        print(f"Timeout: {TIMEOUT}")
        print("Result:")
        print(result_text)
    except Exception as exc:
        elapsed = time.perf_counter() - started_at
        print(f"Elapsed before error: {elapsed:.2f}s")
        print(f"API style: {API_STYLE}")
        print(f"Model: {MODEL}")
        print(f"Timeout: {TIMEOUT}")
        print(f"Error type: {type(exc).__name__}")
        print(f"Error detail: {exc}")
        print("Traceback:")
        print(traceback.format_exc())


if __name__ == "__main__":
    main()
