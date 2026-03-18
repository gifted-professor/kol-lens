import os
import sys
from contextlib import contextmanager
from pathlib import Path

ENV_KEYS = ["BACKEND_ALLOWED_ORIGINS", "BACKEND_BIND_HOST", "BACKEND_PORT"]
ORIGINAL_ENV = {key: os.environ.get(key) for key in ENV_KEYS}
for key in ENV_KEYS:
    os.environ.pop(key, None)

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import backend.app as backend_app


@contextmanager
def restored_env():
    try:
        yield
    finally:
        for key, value in ORIGINAL_ENV.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def assert_allowed_origin(client, origin):
    response = client.get("/api/health", headers={"Origin": origin})
    payload = response.get_json()
    assert response.status_code == 200, payload
    assert response.headers.get("Access-Control-Allow-Origin") == origin, response.headers
    assert response.headers.get("Access-Control-Allow-Origin") != "*", response.headers
    return payload


def main():
    with restored_env():
        client = backend_app.app.test_client()

        payload = assert_allowed_origin(client, "http://127.0.0.1:5173")
        assert payload["status"] == "ok", payload
        assert payload["smoke_ready"] is True, payload
        assert payload["checks"]["origins"] == [
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ], payload

        assert_allowed_origin(client, "http://localhost:5173")

        lan_response = client.get("/api/health", headers={"Origin": "http://192.168.1.8:5173"})
        lan_payload = lan_response.get_json()
        assert lan_response.status_code == 200, lan_payload
        assert lan_response.headers.get("Access-Control-Allow-Origin") is None, lan_response.headers
        assert lan_payload["checks"]["origins"] == [
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ], lan_payload

    print("Local access checks passed.")


if __name__ == "__main__":
    main()
