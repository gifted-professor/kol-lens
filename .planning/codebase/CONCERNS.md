# Codebase Concerns

## Tech Debt

- `backend/app.py` is a 4.5k-line monolith that mixes unrelated concerns: routes, background jobs, Apify orchestration, collage generation, caching, exports, and persistence.
- `frontend/src/App.jsx` is a 2.4k-line single component that holds state management, polling logic, helper utilities, and most rendering.
- Generated artifacts and environment directories are mixed into the repo workspace, including `frontend/dist/`, `frontend/node_modules/`, `backend/venv/`, and `backend/.venv/`.
- The codebase keeps both a REST-first Apify path and a legacy CLI path in `backend/app.py`, increasing maintenance cost.

## Known Bugs

- No explicit bug tracker is present in the repo, so there is no authoritative list of confirmed defects.
- Observed behavior risk: the local dev launcher in `frontend/dev.mjs` hardcodes an x86_64 backend launch path, which can fail on non-macOS or non-Rosetta environments.
- Observed behavior risk: the backend depends on in-memory `JOBS` state in `backend/app.py`, so a process restart drops active job progress and history.
- Observed behavior risk: large exports in `backend/app.py` are synchronous and may block or time out for bigger datasets.

## Security Considerations

- `scripts/test_openai_vision.py` contains a hardcoded API key and should be treated as a credential leak until removed.
- `frontend/dev.mjs` contains a development fallback key for `VISION_QUAN2GO_API_KEY`.
- `backend/app.py` enables CORS for all origins with `origins: "*"`, and the app has no authentication or authorization layer.
- `run_apify_command()` in `backend/app.py` shells out with `shell=True`, which is riskier than structured subprocess argument passing.
- Uploads, metadata, and exported review files may contain PII and are stored directly under tracked local directories.

## Performance Bottlenecks

- Excel parsing and export use `pandas` and `openpyxl` synchronously inside request handlers in `backend/app.py`.
- Batch scrape flows rewrite aggregated JSON files repeatedly as batches complete in `backend/app.py`.
- Visual review downloads cover images, builds collages, and performs model calls serially per profile in `perform_visual_review()`.
- The frontend keeps extensive state and rendering logic in one component, increasing rerender cost and making UI performance harder to isolate.

## Fragile Areas

- Platform-specific field extraction depends on third-party payload shapes from Apify actors and on manually curated field mappings in `config/field_mapping.json`.
- `scripts/data_cleaner.py` couples business rules, thresholds, and output schema tightly; small rule changes can alter multiple exports.
- The upload parser in `backend/app.py` infers headers and content columns heuristically, which is convenient but easy to break with new spreadsheet formats.
- Partial job updates and live-review selection state in `frontend/src/App.jsx` are nontrivial and easy to regress without automated tests.

## Scaling Limits

- The system is single-process and file-backed. It is not designed for concurrent users or horizontally scaled workers.
- Job state, preview caches, and TikTok cache warmers are all in memory inside one Flask process.
- There is no database, queue, or object store to coordinate concurrent writes or resumable background work.
- Polling every 800 ms from the frontend is acceptable locally but would not scale well under many clients.

## Dependencies at Risk

- Apify actor output schemas can change outside the repo and would directly affect parsing in `backend/app.py` and `scripts/data_cleaner.py`.
- OpenAI-compatible providers configured in `backend/app.py` are operational dependencies with their own auth, timeout, and response-shape risks.
- The project relies on local auth files under `~/.apify/`, which makes environment portability weaker.
- The backend assumes reliable public image URLs during collage assembly; expired or throttled media hosts can degrade review quality.

## Missing Critical Features

- No automated backend or frontend test suite.
- No authentication, permissions, or audit trail for operator actions.
- No secret-management discipline beyond environment variables; development fallbacks are still checked into source.
- No deployment contract, CI pipeline, or environment bootstrap script beyond local conventions.
- No modular package boundaries around backend integrations or frontend screens.

## Test Coverage Gaps

- Upload parsing edge cases are untested: missing headers, mixed platforms, unexpected column names, and malformed Excel files.
- Batch retry and token-rotation logic in `backend/app.py` has no automated regression coverage.
- Visual-review parsing, preview caching, and cancellation flows have no repeatable automated checks.
- Export builders for `test-info`, `image-review`, `prescreen-review`, and `final-review` are only lightly protected by manual usage.
- The docs/config sync contract around `scripts/data_cleaner.py`, `config/field_mapping.json`, and `docs/prd/*.md` has no validation gate.
