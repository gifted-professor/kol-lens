#!/usr/bin/env python3
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import backend.app as backend_app


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


def test_partial_retry_preserves_successful_items():
    originals = {
        "DATA_DIR": backend_app.DATA_DIR,
        "run_apify_rest_command": backend_app.run_apify_rest_command,
        "rotate_apify_token": backend_app.rotate_apify_token,
        "finalize_apify_output": backend_app.finalize_apify_output,
        "build_cached_scrape_response": backend_app.build_cached_scrape_response,
        "build_preserved_failure_response": backend_app.build_preserved_failure_response,
        "log_apify_run_summary": backend_app.log_apify_run_summary,
        "get_apify_batch_size": backend_app.get_apify_batch_size,
        "get_apify_attempt_budget": backend_app.get_apify_attempt_budget,
        "ensure_apify_budget_for_request": backend_app.ensure_apify_budget_for_request,
    }

    with tempfile.TemporaryDirectory() as temp_dir:
        calls = []

        def fake_run_apify_rest_command(
            actor_id,
            input_data,
            output_filename,
            force_refresh=False,
            progress_callback=None,
            cancel_check=None,
            preferred_tokens=None,
        ):
            requested = list(input_data.get("profiles") or [])
            calls.append(requested)
            if len(calls) == 1:
                return {
                    "success": True,
                    "raw_items": [build_tiktok_item("alpha", "video-alpha-1")],
                }
            if len(calls) == 2:
                return {
                    "success": True,
                    "raw_items": [build_tiktok_item("beta", "video-beta-1")],
                }
            raise AssertionError(f"Unexpected extra retry: {calls}")

        def fake_finalize_apify_output(output_filename, output_file_path, identifiers, skipped_count, progress_callback=None, apify_summary=None, requested_identifiers=None):
            return {
                "success": True,
                "requested_total": len(requested_identifiers or identifiers),
                "successful_identifiers": ["alpha", "beta"],
                "profile_reviews": [],
                "count": 2,
            }

        backend_app.DATA_DIR = temp_dir
        backend_app.run_apify_rest_command = fake_run_apify_rest_command
        backend_app.rotate_apify_token = lambda tried_tokens=None: None
        backend_app.finalize_apify_output = fake_finalize_apify_output
        backend_app.build_cached_scrape_response = lambda *args, **kwargs: None
        backend_app.build_preserved_failure_response = lambda *args, **kwargs: None
        backend_app.log_apify_run_summary = lambda *args, **kwargs: None
        backend_app.get_apify_batch_size = lambda platform, input_data=None: 2
        backend_app.get_apify_attempt_budget = lambda: 2
        backend_app.ensure_apify_budget_for_request = lambda *args, **kwargs: {"success": True}

        try:
            result = backend_app.perform_batched_rest_scrape(
                "tiktok",
                "clockworks/tiktok-profile-scraper",
                {
                    "profiles": ["alpha", "beta"],
                    "resultsPerPage": 20,
                },
                ["alpha", "beta"],
                "tiktok",
                force_refresh=True,
            )
        finally:
            for name, value in originals.items():
                setattr(backend_app, name, value)

    assert result["success"] is True, result
    assert result["failed_batches"] == [], result
    assert result["batch_summary"]["failed"] == 0, result
    assert calls == [["alpha", "beta"], ["beta"]], calls


def main():
    test_partial_retry_preserves_successful_items()
    print("Apify batch retry checks passed.")


if __name__ == "__main__":
    main()
