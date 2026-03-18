#!/usr/bin/env python3
import sys
from contextlib import contextmanager
from pathlib import Path


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


def build_identifiers(count, prefix="profile"):
    return [f"{prefix}-{index}" for index in range(1, count + 1)]


def test_paid_first_token_pool_prefers_paid_capacity():
    batches = [
        build_identifiers(10, prefix="paid"),
        build_identifiers(10, prefix="fallback"),
    ]

    with patched_backend_attrs(
        collect_apify_budget_snapshots=lambda cancel_check=None, preferred_tokens=None: ([
            {
                "token": "tok-paid",
                "masked": "...paid",
                "tier": "paid",
                "priority": 0,
                "hard_limit_usd": None,
                "remaining_monthly_usage_usd": 1.0,
                "max_monthly_usage_usd": 5.0,
                "monthly_usage_usd": 4.0,
                "monthly_usage_cycle_end_at": "2026-04-18T00:00:00.000Z",
            },
            {
                "token": "tok-free",
                "masked": "...free",
                "tier": "free",
                "priority": 1,
                "hard_limit_usd": 5.0,
                "remaining_monthly_usage_usd": 10.0,
                "max_monthly_usage_usd": 10.0,
                "monthly_usage_usd": 0.0,
                "monthly_usage_cycle_end_at": "2026-04-18T00:00:00.000Z",
            },
        ], []),
    ):
        plan = backend_app.plan_apify_token_batches(
            "tiktok",
            {"resultsPerPage": 20},
            batches,
        )

    assert plan["success"] is True, plan
    assert [item["token"] for item in plan["planned_batches"]] == ["tok-paid", "tok-free"], plan


def test_free_token_hard_limit_blocks_overallocation():
    with patched_backend_attrs(
        collect_apify_budget_snapshots=lambda cancel_check=None, preferred_tokens=None: ([
            {
                "token": "tok-free",
                "masked": "...free",
                "tier": "free",
                "priority": 0,
                "hard_limit_usd": 5.0,
                "remaining_monthly_usage_usd": 20.0,
                "max_monthly_usage_usd": 20.0,
                "monthly_usage_usd": 0.0,
                "monthly_usage_cycle_end_at": "2026-04-18T00:00:00.000Z",
            }
        ], []),
    ):
        blocked = backend_app.ensure_apify_budget_for_run(
            "tiktok",
            {"resultsPerPage": 50},
            build_identifiers(25, prefix="hard-limit"),
        )

    assert blocked["success"] is False, blocked
    assert blocked["error_code"] == "APIFY_MONTHLY_BUDGET_EXCEEDED", blocked
    assert blocked["budget"]["tokens"][0]["hard_limit_usd"] == 5.0, blocked
    assert blocked["budget"]["tokens"][0]["hard_limit_remaining_usd"] == 5.0, blocked


def main():
    test_paid_first_token_pool_prefers_paid_capacity()
    test_free_token_hard_limit_blocks_overallocation()

    tiktok_identifiers = build_identifiers(25)
    estimated_cost = backend_app.estimate_apify_request_cost_usd(
        "tiktok",
        {"resultsPerPage": 50},
        tiktok_identifiers,
    )
    required_budget = backend_app.apply_apify_budget_guard_band(estimated_cost)
    assert estimated_cost == 5.0, estimated_cost
    assert required_budget == 5.6, required_budget

    with patched_backend_attrs(
        collect_apify_budget_snapshots=lambda cancel_check=None, preferred_tokens=None: ([
            {
                "token": "tok-free",
                "masked": "...free",
                "remaining_monthly_usage_usd": 5.0,
                "max_monthly_usage_usd": 5.0,
                "monthly_usage_usd": 0.0,
                "monthly_usage_cycle_end_at": "2026-04-18T00:00:00.000Z",
            }
        ], []),
    ):
        blocked = backend_app.ensure_apify_budget_for_request(
            "tiktok",
            {"resultsPerPage": 50},
            tiktok_identifiers,
        )

    assert blocked["success"] is False, blocked
    assert blocked["error_code"] == "APIFY_MONTHLY_BUDGET_EXCEEDED", blocked
    assert "预计消耗约 5.000 USD" in blocked["error"], blocked
    assert "5.600 USD" in blocked["error"], blocked

    with patched_backend_attrs(
        collect_apify_budget_snapshots=lambda cancel_check=None, preferred_tokens=None: ([
            {
                "token": "tok-a",
                "masked": "...tok-a",
                "remaining_monthly_usage_usd": 0.4,
                "max_monthly_usage_usd": 5.0,
                "monthly_usage_usd": 4.6,
                "monthly_usage_cycle_end_at": "2026-04-18T00:00:00.000Z",
            },
            {
                "token": "tok-b",
                "masked": "...tok-b",
                "remaining_monthly_usage_usd": 8.0,
                "max_monthly_usage_usd": 10.0,
                "monthly_usage_usd": 2.0,
                "monthly_usage_cycle_end_at": "2026-04-18T00:00:00.000Z",
            },
        ], []),
    ):
        allowed = backend_app.ensure_apify_budget_for_run(
            "tiktok",
            {"resultsPerPage": 50},
            build_identifiers(5),
        )

    assert allowed["success"] is True, allowed
    assert allowed["token"] == "tok-b", allowed
    assert allowed["required_budget_usd"] == 1.2, allowed

    print("Apify budget guard checks passed.")


if __name__ == "__main__":
    main()
