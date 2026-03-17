# Coding Conventions

## Naming Patterns

- Backend helpers and routes use `snake_case`, for example `perform_scrape()`, `build_visual_review_partial()`, and `download_final_review()` in `backend/app.py`.
- Frontend state and event handlers use `camelCase`, for example `setVisualReviewHistory`, `handleScrape`, and `downloadFinalReview` in `frontend/src/App.jsx`.
- Platform names are normalized as lowercase strings (`tiktok`, `instagram`, `youtube`) for branching and file naming.
- Output artifacts are named by platform and purpose rather than by opaque IDs, which keeps operator-facing files predictable.

## Code Style

- Python follows 4-space indentation across `backend/app.py` and `scripts/*.py`.
- Frontend JSX and CSS follow 2-space indentation in the existing files under `frontend/src/`.
- The frontend favors long Tailwind utility strings stored in top-level constants such as `bentoCardClassName` and `formFieldClassName` in `frontend/src/App.jsx`.
- The backend favors many small helper functions, but they all live in one module rather than separate packages.
- Business messages returned to users are often Chinese even when code structure and identifiers are English.

## Import Organization

- Python files generally group stdlib imports first, then third-party imports, as seen in `backend/app.py`.
- Some backend dependencies are imported inside functions or routes, for example `import pandas as pd` inside export and upload routes.
- `backend/app.py` also imports `data_cleaner` lazily inside scrape-finalization paths instead of at module import time.
- Frontend imports are shallow: React, motion/icon libraries, then local files in `frontend/src/main.jsx` and `frontend/src/App.jsx`.

## Error Handling

- Backend routes validate payload shape early and return JSON objects with `success` or `error` fields from `backend/app.py`.
- Long-running backend work converts failures into job-state transitions instead of surfacing exceptions directly to the browser.
- The frontend keeps separate error channels for scrape and visual-review flows via `error` and `visualError` state in `frontend/src/App.jsx`.
- Retry behavior is implemented explicitly for job polling and Apify/network access rather than through a shared resilience layer.

## Logging

- Logging is mostly `print()` output in backend and script code.
- Operator-facing progress logging is embedded into job messages and live-review log lines in `backend/app.py`.
- There is no centralized logger, log level policy, or structured log schema.

## Comments

- Comments are sparse and practical. They tend to explain operator intent, performance rationale, or business-rule caveats.
- `scripts/data_cleaner.py` contains maintenance comments that explicitly tie code changes to required doc/config updates.
- The frontend uses very few explanatory comments outside of form-state or workflow markers.

## Function Design

- Utility formatting and normalization helpers are defined near the top of `frontend/src/App.jsx` and reused inside the main `App()` component.
- Backend functions frequently return plain dictionaries rather than custom objects or dataclasses.
- Cross-platform behavior is often encoded as `if platform == ...` branches rather than polymorphic classes.
- Partial-result payloads are shaped to be JSON-serializable because they are returned through job polling.

## Module Design

- `backend/app.py` is a monolith that mixes routing, storage, integration clients, caching, export generation, and background-job logic.
- `frontend/src/App.jsx` is similarly monolithic, containing both domain workflow logic and almost all rendering.
- `scripts/data_cleaner.py` is the main exception: it is a focused domain module with platform-specific screening functions and one orchestration entry point.
- Documentation and config are part of the working convention. When field usage or screening rules change, matching files in `docs/prd/`, `config/field_mapping.json`, and generated docs are expected to move with the code.
