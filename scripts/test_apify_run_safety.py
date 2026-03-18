#!/usr/bin/env python3
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import requests


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import backend.app as backend_app


@contextmanager
def patched_backend_attrs(**patches):
    originals = {name: getattr(backend_app, name) for name in patches}
    try:
        for name, value in patches.items():
            setattr(backend_app, name, value)
        yield
    finally:
        for name, value in originals.items():
            setattr(backend_app, name, value)


def build_identifiers(count):
    return [f"profile-{index}" for index in range(1, count + 1)]


def build_tiktok_item(username, item_id):
    return {
        "id": item_id,
        "createTimeISO": "2026-03-18T10:00:00.000Z",
        "playCount": 20000,
        "text": "sample",
        "hashtags": [{"name": "sample"}],
        "authorMeta": {
            "name": username,
            "profileUrl": f"https://www.tiktok.com/@{username}",
        },
        "videoMeta": {
            "coverUrl": f"https://example.com/{username}.jpg",
        },
    }


def test_budget_reservations_isolate_tokens():
    snapshots = [
        {
            "token": "tok-a",
            "masked": "...tok-a",
            "tier": "paid",
            "priority": 0,
            "hard_limit_usd": None,
            "remaining_monthly_usage_usd": 1.0,
            "max_monthly_usage_usd": 5.0,
            "monthly_usage_usd": 4.0,
            "monthly_usage_cycle_end_at": "2026-04-18T00:00:00.000Z",
        },
        {
            "token": "tok-b",
            "masked": "...tok-b",
            "tier": "paid",
            "priority": 1,
            "hard_limit_usd": None,
            "remaining_monthly_usage_usd": 1.0,
            "max_monthly_usage_usd": 5.0,
            "monthly_usage_usd": 4.0,
            "monthly_usage_cycle_end_at": "2026-04-18T00:00:00.000Z",
        },
    ]

    with tempfile.TemporaryDirectory() as temp_dir:
        state_file = Path(temp_dir) / "token_state.json"
        with patched_backend_attrs(
            APIFY_TOKEN_STATE_FILE=str(state_file),
            collect_apify_budget_snapshots=lambda cancel_check=None, preferred_tokens=None: (list(snapshots), []),
        ):
            first = backend_app.ensure_apify_budget_for_run(
                "tiktok",
                {"resultsPerPage": 20},
                build_identifiers(10),
                reservation_key="reservation-1",
            )
            second = backend_app.ensure_apify_budget_for_run(
                "tiktok",
                {"resultsPerPage": 20},
                build_identifiers(10),
                reservation_key="reservation-2",
            )
            backend_app.release_apify_budget_reservation("reservation-1")
            third = backend_app.ensure_apify_budget_for_run(
                "tiktok",
                {"resultsPerPage": 20},
                build_identifiers(10),
                reservation_key="reservation-3",
            )
            backend_app.release_apify_budget_reservation("reservation-2")
            backend_app.release_apify_budget_reservation("reservation-3")

    assert first["success"] is True, first
    assert second["success"] is True, second
    assert third["success"] is True, third
    assert first["token"] == "tok-a", first
    assert second["token"] == "tok-b", second
    assert third["token"] == "tok-a", third


def test_guarded_run_recovery_reuses_existing_run():
    originals = {
        "DATA_DIR": backend_app.DATA_DIR,
        "APIFY_RUN_GUARD_STATE_FILE": backend_app.APIFY_RUN_GUARD_STATE_FILE,
        "apify_request": backend_app.apify_request,
        "finalize_apify_output": backend_app.finalize_apify_output,
        "log_apify_run_summary": backend_app.log_apify_run_summary,
    }

    with tempfile.TemporaryDirectory() as temp_dir:
        guard_file = Path(temp_dir) / "run_guard_state.json"
        request_counts = {"post": 0, "status": 0, "dataset": 0}

        def fake_apify_request(method, url, **kwargs):
            if method == "POST":
                request_counts["post"] += 1
                raise AssertionError("Recovery path should not submit a new run")
            if method == "GET" and "/actor-runs/" in url:
                request_counts["status"] += 1
                return SimpleNamespace(
                    status_code=200,
                    json=lambda: {
                        "data": {
                            "id": "run-existing-1",
                            "status": "SUCCEEDED",
                            "defaultDatasetId": "dataset-existing-1",
                        }
                    },
                )
            if method == "GET" and "/datasets/" in url:
                request_counts["dataset"] += 1
                return SimpleNamespace(
                    status_code=200,
                    json=lambda: [build_tiktok_item("alpha", "video-alpha-1")],
                )
            raise AssertionError(f"Unexpected request: {method} {url}")

        with patched_backend_attrs(
            DATA_DIR=temp_dir,
            APIFY_RUN_GUARD_STATE_FILE=str(guard_file),
            apify_request=fake_apify_request,
            finalize_apify_output=lambda *args, **kwargs: {
                "success": True,
                "profile_reviews": [],
                "requested_total": 1,
                "successful_identifiers": ["alpha"],
                "message": "recovered",
            },
            log_apify_run_summary=lambda *args, **kwargs: None,
        ):
            backend_app.remember_apify_run_guard(
                backend_app.build_apify_run_guard_key(
                    "clockworks/tiktok-profile-scraper",
                    "tiktok",
                    {"profiles": ["alpha"], "resultsPerPage": 20},
                ),
                actor_id="clockworks/tiktok-profile-scraper",
                output_filename="tiktok",
                input_data={"profiles": ["alpha"], "resultsPerPage": 20},
                reason="existing remote run",
                token="tok-a",
                run_id="run-existing-1",
                dataset_id="dataset-existing-1",
                status="RUNNING",
            )
            result = backend_app.run_apify_rest_command(
                "clockworks/tiktok-profile-scraper",
                {"profiles": ["alpha"], "resultsPerPage": 20},
                "tiktok",
                force_refresh=True,
            )
            guard_after = backend_app.get_apify_run_guard(
                backend_app.build_apify_run_guard_key(
                    "clockworks/tiktok-profile-scraper",
                    "tiktok",
                    {"profiles": ["alpha"], "resultsPerPage": 20},
                )
            )

        for name, value in originals.items():
            setattr(backend_app, name, value)

    assert result["success"] is True, result
    assert request_counts["post"] == 0, request_counts
    assert request_counts["status"] >= 1, request_counts
    assert request_counts["dataset"] >= 1, request_counts
    assert guard_after is None, guard_after


def test_non_retryable_batch_failure_stops_resubmission():
    originals = {
        "DATA_DIR": backend_app.DATA_DIR,
        "run_apify_rest_command": backend_app.run_apify_rest_command,
        "build_cached_scrape_response": backend_app.build_cached_scrape_response,
        "build_preserved_failure_response": backend_app.build_preserved_failure_response,
        "log_apify_run_summary": backend_app.log_apify_run_summary,
        "get_apify_batch_size": backend_app.get_apify_batch_size,
        "get_apify_attempt_budget": backend_app.get_apify_attempt_budget,
        "ensure_apify_budget_for_request": backend_app.ensure_apify_budget_for_request,
    }

    with tempfile.TemporaryDirectory() as temp_dir:
        calls = []

        def fake_run_apify_rest_command(actor_id, input_data, output_filename, force_refresh=False, progress_callback=None, cancel_check=None, preferred_tokens=None):
            calls.append(list(input_data.get("profiles") or []))
            return {
                "success": False,
                "safe_to_retry": False,
                "error_code": "APIFY_REMOTE_RUN_UNCERTAIN",
                "error": "remote run uncertain",
                "apify_run_id": "run-uncertain-1",
            }

        backend_app.DATA_DIR = temp_dir
        backend_app.run_apify_rest_command = fake_run_apify_rest_command
        backend_app.build_cached_scrape_response = lambda *args, **kwargs: None
        backend_app.build_preserved_failure_response = lambda *args, **kwargs: None
        backend_app.log_apify_run_summary = lambda *args, **kwargs: None
        backend_app.get_apify_batch_size = lambda platform, input_data=None: 2
        backend_app.get_apify_attempt_budget = lambda: 3
        backend_app.ensure_apify_budget_for_request = lambda *args, **kwargs: {"success": True}

        try:
            result = backend_app.perform_batched_rest_scrape(
                "tiktok",
                "clockworks/tiktok-profile-scraper",
                {
                    "profiles": ["alpha", "beta", "gamma", "delta"],
                    "resultsPerPage": 20,
                },
                ["alpha", "beta", "gamma", "delta"],
                "tiktok",
                force_refresh=True,
            )
        finally:
            for name, value in originals.items():
                setattr(backend_app, name, value)

    assert result["success"] is False, result
    assert calls == [["alpha", "beta"]], calls
    assert result["failed_batches"][0]["safe_to_retry"] is False, result
    assert result["failed_batches"][0]["apify_run_id"] == "run-uncertain-1", result


def test_scrape_job_is_idempotent_and_blocks_same_platform_parallel_runs():
    client = backend_app.app.test_client()
    backend_app.JOBS.clear()

    payload = {
        "platform": "tiktok",
        "payload": {
            "profiles": ["alpha", "beta"],
            "limit": 20,
            "forceRefresh": True,
        },
    }

    with patched_backend_attrs(
        validate_apify_runtime_config=lambda: None,
        start_background_job=lambda job, runner: None,
    ):
        first_response = client.post("/api/jobs/scrape", json=payload)
        first_data = first_response.get_json()
        duplicate_response = client.post("/api/jobs/scrape", json=payload)
        duplicate_data = duplicate_response.get_json()
        conflict_response = client.post(
            "/api/jobs/scrape",
            json={
                "platform": "tiktok",
                "payload": {
                    "profiles": ["gamma"],
                    "limit": 20,
                    "forceRefresh": True,
                },
            },
        )
        conflict_data = conflict_response.get_json()

    try:
        assert first_response.status_code == 200, first_data
        assert first_data["success"] is True, first_data
        assert duplicate_response.status_code == 200, duplicate_data
        assert duplicate_data["duplicate_request"] is True, duplicate_data
        assert duplicate_data["job"]["id"] == first_data["job"]["id"], duplicate_data
        assert conflict_response.status_code == 409, conflict_data
        assert conflict_data["error_code"] == "SCRAPE_JOB_ALREADY_RUNNING", conflict_data
    finally:
        backend_app.JOBS.clear()


def test_submission_uncertainty_creates_guard_and_blocks_repeat():
    originals = {
        "DATA_DIR": backend_app.DATA_DIR,
        "APIFY_RUN_GUARD_STATE_FILE": backend_app.APIFY_RUN_GUARD_STATE_FILE,
        "ensure_apify_budget_for_run": backend_app.ensure_apify_budget_for_run,
        "apify_request": backend_app.apify_request,
        "build_cached_scrape_response": backend_app.build_cached_scrape_response,
    }

    with tempfile.TemporaryDirectory() as temp_dir:
        guard_file = Path(temp_dir) / "run_guard_state.json"
        post_calls = {"count": 0}

        def fake_apify_request(method, url, **kwargs):
            if method == "POST":
                post_calls["count"] += 1
                raise requests.RequestException("connection reset during submit")
            raise AssertionError(f"Unexpected method: {method}")

        with patched_backend_attrs(
            DATA_DIR=temp_dir,
            APIFY_RUN_GUARD_STATE_FILE=str(guard_file),
            ensure_apify_budget_for_run=lambda *args, **kwargs: {
                "success": True,
                "token": "tok-a",
                "required_budget_usd": 1.0,
            },
            apify_request=fake_apify_request,
            build_cached_scrape_response=lambda *args, **kwargs: None,
        ):
            first = backend_app.run_apify_rest_command(
                "clockworks/tiktok-profile-scraper",
                {"profiles": ["alpha"], "resultsPerPage": 20},
                "tiktok",
                force_refresh=True,
            )
            second = backend_app.run_apify_rest_command(
                "clockworks/tiktok-profile-scraper",
                {"profiles": ["alpha"], "resultsPerPage": 20},
                "tiktok",
                force_refresh=True,
            )

    assert first["success"] is False, first
    assert first["safe_to_retry"] is False, first
    assert first["error_code"] == "APIFY_RUN_SUBMISSION_UNCERTAIN", first
    assert second["success"] is False, second
    assert second["error_code"] == "APIFY_SUBMISSION_LOCKED", second
    assert post_calls["count"] == 1, post_calls


def test_running_remote_run_keeps_job_non_terminal():
    backend_app.JOBS.clear()
    stage_seen = threading.Event()

    def runner(progress_callback, cancel_check):
        progress_callback(
            "waiting_remote_run",
            "远端 Apify run 仍在运行，继续等待",
            done=1,
            total=4,
            apify_run_id="run-remote-1",
            apify_status="RUNNING",
            safe_to_retry=False,
        )
        stage_seen.set()
        while not cancel_check():
            time.sleep(0.02)
        return backend_app.build_cancelled_result("test complete")

    job = backend_app.create_job("scrape", platform="tiktok", message="test")
    thread = backend_app.start_background_job(job, runner)

    try:
        assert stage_seen.wait(1), "Expected waiting_remote_run stage to be emitted"
        current = backend_app.get_job(job["id"])
        assert current["status"] == "running", current
        assert current["stage"] == "waiting_remote_run", current
        assert current["apify_run_id"] == "run-remote-1", current
        assert current["apify_status"] == "RUNNING", current
        assert current["safe_to_retry"] is False, current
    finally:
        backend_app.update_job(job["id"], status="cancelling", stage="cancelling")
        thread.join(timeout=1)
        backend_app.JOBS.clear()


def test_apify_request_does_not_retry_when_disabled():
    calls = {"count": 0}
    original_request = backend_app.requests.request

    def fake_request(method, url, timeout=None, **kwargs):
        calls["count"] += 1
        raise requests.RequestException("network down")

    backend_app.requests.request = fake_request
    try:
        try:
            backend_app.apify_request("POST", "https://example.com", allow_retries=False, retry_context="unit-test")
        except requests.RequestException:
            pass
    finally:
        backend_app.requests.request = original_request

    assert calls["count"] == 1, calls


def main():
    test_budget_reservations_isolate_tokens()
    test_guarded_run_recovery_reuses_existing_run()
    test_non_retryable_batch_failure_stops_resubmission()
    test_scrape_job_is_idempotent_and_blocks_same_platform_parallel_runs()
    test_submission_uncertainty_creates_guard_and_blocks_repeat()
    test_running_remote_run_keeps_job_non_terminal()
    test_apify_request_does_not_retry_when_disabled()
    print("Apify run safety checks passed.")


if __name__ == "__main__":
    main()
