# Architecture

## Pattern Overview

- The project is a local-first operator tool built as a thin React frontend over a single Flask service plus one script-based business-rules engine.
- `backend/app.py` acts as controller, job runner, integration client, cache layer, file-storage adapter, and export service in one module.
- `scripts/data_cleaner.py` is the real domain-rules boundary: it converts raw scraper output into per-profile decisions and review metadata.
- `frontend/src/App.jsx` is a single-screen workflow UI that owns upload, scrape kickoff, polling, visual-review orchestration, and export actions.
- The dominant architecture is file-based pipeline processing rather than request-per-request CRUD.

## Layers

- Presentation layer: `frontend/src/App.jsx`, `frontend/src/main.jsx`, and `frontend/src/index.css`.
- API and orchestration layer: Flask routes plus helper functions in `backend/app.py`.
- Domain rules layer: platform-specific screening logic in `scripts/data_cleaner.py`.
- Integration layer: Apify REST and CLI paths, OpenAI-compatible vision calls, remote image downloads in `backend/app.py`.
- Persistence layer: JSON, XLSX, and uploaded files under `data/` plus temporary artifacts under `temp/`.
- Documentation/config layer: `README.md`, `docs/prd/*.md`, `docs/field_dictionary.md`, and `config/field_mapping.json`.

## Data Flow

- Upload flow:
  `frontend/src/App.jsx` posts a file to `POST /api/upload` in `backend/app.py`.
  The backend classifies rows by platform, normalizes upload metadata, and writes platform metadata files under `data/<platform>/`.
- Scrape flow:
  `frontend/src/App.jsx` creates a background scrape job through `POST /api/jobs/scrape`.
  `perform_scrape()` in `backend/app.py` routes by platform, calls Apify, saves raw JSON, and then runs `scripts/data_cleaner.py -> filter_and_save_dataset()`.
- Review output flow:
  `filter_and_save_dataset()` writes `profile_reviews`, which become the main operator-facing result set loaded by `GET /api/results/<platform>` and export endpoints.
- Visual review flow:
  `frontend/src/App.jsx` sends only passed profiles with covers to `POST /api/jobs/visual-review`.
  `perform_visual_review()` builds cover collages, calls the vision model, streams partial state through the job record, and returns final `visual_results`.
- Export flow:
  `backend/app.py` converts raw or reviewed data into XLSX or JSON downloads via `/api/download/...` endpoints.

## Key Abstractions

- Job abstraction:
  `create_job()`, `update_job()`, `get_job()`, and `start_background_job()` in `backend/app.py` provide lightweight async orchestration using in-memory state plus background threads.
- Profile review abstraction:
  `profile_reviews` is the main business object. It contains `username`, `profile_url`, status, reason, covers, stats, latest-post metadata, soft flags, and upload metadata.
- Upload metadata abstraction:
  upload rows are normalized once in `backend/app.py` and then merged back into screening results later.
- Platform branching abstraction:
  `perform_scrape()` and `filter_and_save_dataset()` branch on `tiktok`, `instagram`, and `youtube`, but each branch still writes to the same file contracts.
- Live visual-review abstraction:
  `perform_visual_review()` emits `live_review`, `review_history`, and `visual_results` snapshots that the frontend can render incrementally.

## Entry Points

- Frontend bootstraps at `frontend/src/main.jsx`.
- The only top-level React screen is `frontend/src/App.jsx`.
- Backend bootstraps at the `if __name__ == '__main__'` block in `backend/app.py`.
- Operator-visible backend entry routes include:
  `POST /api/upload`
  `POST /api/jobs/scrape`
  `POST /api/jobs/visual-review`
  `GET /api/jobs/<job_id>`
  `GET /api/results/<platform>`
  `GET|POST /api/download/...`
- Script entry points include `scripts/data_cleaner.py`, `scripts/build_field_dictionary.py`, `scripts/test_apify_api.py`, and `scripts/test_openai_vision.py`.

## Error Handling

- Route handlers mostly validate inputs early and return JSON errors with 4xx/5xx status codes from `backend/app.py`.
- Background jobs convert exceptions into `failed` or `cancelled` job states rather than crashing the request thread.
- The frontend normalizes failures into local `error` and `visualError` state in `frontend/src/App.jsx`.
- Partial scrape results and retry loops are used to salvage incomplete Apify batches instead of failing everything immediately.
- JSON parsing is defensive in several places because saved files may contain leading noise or partial content.

## Cross-Cutting Concerns

- File naming and persistence contracts are cross-cutting and stable across every platform-specific path in `backend/app.py`.
- Platform business rules are tightly coupled to PRD/docs sync requirements noted in `scripts/data_cleaner.py` and `docs/prd/*.md`.
- Caching and resumability are implemented through `data/scrape_history.json`, last-non-empty snapshots, and in-memory caches in `backend/app.py`.
- The system is bilingual in practice: code identifiers are English, while many user-facing messages and business rules are Chinese.
- Because core logic is concentrated in `backend/app.py` and `frontend/src/App.jsx`, most changes have a high chance of touching shared state or shared helper functions.
