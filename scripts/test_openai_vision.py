import json
import time
import traceback

from openai import OpenAI


API_KEY = "cr_238a1f2878ded1ec5d09a0117811a3d6261087f5a1244262873fd359e8d2326a"
BASE_URL = "https://gpt.auto-code.net/rust/openai/v1"
MODEL = "gpt-5.4"
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


def main() -> None:
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    started_at = time.perf_counter()
    try:
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
        elapsed = time.perf_counter() - started_at
        print(f"Elapsed: {elapsed:.2f}s")
        print("Result:")
        print(extract_response_text(response))
    except Exception as exc:
        elapsed = time.perf_counter() - started_at
        print(f"Elapsed before error: {elapsed:.2f}s")
        print(f"Error type: {type(exc).__name__}")
        print(f"Error detail: {exc}")
        print("Traceback:")
        print(traceback.format_exc())


if __name__ == "__main__":
    main()
