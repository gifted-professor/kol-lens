# Testing Patterns

## Test Framework

- There is no formal automated test suite directory and no `pytest` configuration in the repo root.
- Frontend validation is currently command-based: `npm run lint` and `npm run build` from `frontend/package.json`.
- Backend validation is mostly manual or script-driven.
- Integration smoke tests live in `scripts/test_apify_api.py` and `scripts/test_openai_vision.py`.

## Test File Organization

- Repeatable validation scripts live in `scripts/` and use a `test_*.py` naming pattern.
- There is no dedicated `tests/` package for backend unit tests.
- There are no frontend component test files, browser tests, or snapshot tests under `frontend/src/`.
- Sample inputs and previously generated outputs live under `data/` and are used as operator fixtures rather than formal test fixtures.

## Test Structure

- Current tests are executable scripts with a `main()` flow or top-level procedure rather than test functions collected by a runner.
- `scripts/test_apify_api.py` performs a live Apify run, polls status, and downloads dataset items.
- `scripts/test_openai_vision.py` performs a live request against an OpenAI-compatible endpoint and prints the result.
- Manual route validation is expected through local browser usage or small ad hoc scripts against the Flask API.

## Mocking

- There is no mocking layer around Apify, OpenAI, image downloads, filesystem writes, or time-based job polling.
- External integrations are exercised live in the existing scripts.
- Backend code is structured in a way that could support `Flask.test_client()` based tests, but none are checked in.
- Frontend code uses `fetch()` directly in `frontend/src/App.jsx`, with no test doubles or service abstraction in place.

## Fixtures and Factories

- Representative upload files live under `data/uploads/`, including `data/uploads/test_upload.xlsx`.
- Platform snapshots such as `data/instagram/instagram_profile_reviews.json` and `data/tiktok/tiktok_data.json` act as practical fixtures.
- `config/field_mapping.json` and generated docs can be used as fixture-like reference data when changing upload-field behavior.
- No fixture factory utilities or factory modules are present.

## Coverage

- There is no coverage tooling configured for Python or JavaScript.
- High-risk paths with no automated coverage include upload parsing, Apify batch retries, token rotation, visual-review collage generation, and export builders in `backend/app.py`.
- The large render and state-management surface in `frontend/src/App.jsx` has no component-level or interaction-level automated coverage.

## Test Types

- Frontend static checks:
  `cd frontend && npm run lint`
  `cd frontend && npm run build`
- Backend manual smoke tests:
  run `backend/venv/bin/python backend/app.py` and hit the relevant API route or UI flow.
- External integration checks:
  `backend/venv/bin/python scripts/test_openai_vision.py`
  `backend/venv/bin/python scripts/test_apify_api.py`
- Data/regression checks:
  inspect generated files under `data/<platform>/` after running a scrape or review job.

## Common Patterns

- Validate from the top of the workflow first: upload a known Excel file, run scrape, inspect `profile_reviews`, then run visual review and exports.
- Prefer sample files already in `data/uploads/` when checking upload normalization behavior.
- When screening rules change, compare output JSON or XLSX files before and after the change because the app is file-contract driven.
- When field mappings change, regenerate `docs/field_dictionary.md` from `scripts/build_field_dictionary.py` and verify the generated diff.
