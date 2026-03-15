# Repository Guidelines

## Project Structure & Module Organization
`frontend/` contains the React + Vite UI. Main app code lives in `frontend/src/`, with `App.jsx` as the primary screen and `main.jsx` as the entrypoint. `backend/` contains the Flask API in `backend/app.py` plus Python dependencies in `backend/requirements.txt`. `scripts/` holds helper and validation scripts such as `data_cleaner.py`, `apify_token_manager.py`, and `test_openai_vision.py`. Business rules and platform-specific screening notes live under `docs/prd/`. Runtime data, exports, and uploaded files are stored in `data/` and `temp/`; treat these as generated artifacts unless a task explicitly requires updating sample data.

## Build, Test, and Development Commands
- `cd frontend && npm run dev -- --host 127.0.0.1 --port 5173`: start the frontend locally.
- `backend/venv/bin/python backend/app.py`: start the Flask backend on port `5001`.
- `cd frontend && npm run build`: produce a production build in `frontend/dist/`.
- `cd frontend && npm run lint`: run ESLint on the frontend codebase.
- `backend/venv/bin/python scripts/test_openai_vision.py`: verify the proxy vision API connection.

## Coding Style & Naming Conventions
Use 4 spaces in Python and 2 spaces in JSX/CSS when editing existing frontend files. Prefer descriptive snake_case for Python functions and camelCase for React state, handlers, and props. Keep Flask routes small and move reusable logic into helper functions. Frontend follows the existing inline-style-heavy pattern in `App.jsx`; do not introduce a new styling system unless requested. ESLint is configured in `frontend/eslint.config.js`; fix lint warnings before handing off.

## Testing Guidelines
There is no full automated test suite yet. Validate changes with focused checks:
- frontend: `npm run lint` and `npm run build`
- backend: run the relevant Flask route through a small script or Flask `test_client`
- integrations: use sample files like `test_upload.xlsx` and existing `data/*_profile_reviews.json`
Name ad hoc validation scripts with a `test_*.py` prefix in `scripts/`.

## Commit & Pull Request Guidelines
Git history is not available in this workspace, so use clear imperative commit messages such as `feat: add influencer visual review endpoint` or `fix: rebuild backend venv for x86_64`. PRs should include a short summary, affected paths, manual verification steps, and screenshots for UI changes. Mention any data files, API keys, or local environment assumptions explicitly.

## Security & Configuration Tips
Do not commit real API keys. Prefer `OPENAI_API_KEY` or other environment variables over hardcoded secrets. Keep generated virtual environments (`backend/venv`, backups) and large exports out of reviews unless the task is environment repair.
