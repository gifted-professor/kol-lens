# Codebase Structure

## Directory Layout

- `frontend/`
  React/Vite application, including source, local dev launcher, build output, and frontend dependencies.
- `backend/`
  Flask application plus Python dependency manifests and local virtualenv directories.
- `scripts/`
  Helper scripts for screening support, field-dictionary generation, token rotation, and manual integration tests.
- `docs/`
  Product-rule and operator documentation, especially under `docs/prd/`.
- `config/`
  Machine-readable field mapping and screening field metadata.
- `data/`
  Generated runtime data, uploads, scrape snapshots, review outputs, and exports.
- `temp/`
  Scratch files and temporary operator artifacts.
- `.codex/`
  GSD workflow assets, skills, templates, and agent instructions.

## Directory Purposes

- `frontend/src/App.jsx` is the main UI implementation and currently holds nearly all frontend behavior.
- `frontend/src/index.css` contains base Tailwind setup and global styles; `frontend/src/App.css` currently has no content.
- `backend/app.py` is the single backend source file and primary integration surface.
- `scripts/data_cleaner.py` is the canonical rule engine for first-pass screening.
- `docs/prd/master_vetting_sop.md` and platform-specific PRD mappings describe the intended screening behavior.
- `config/field_mapping.json` plus `docs/field_dictionary.md` define and document field usage contracts.
- `data/<platform>/` directories are effectively the app's file-backed state stores.

## Key File Locations

- Frontend entry: `frontend/src/main.jsx`
- Main UI screen: `frontend/src/App.jsx`
- Frontend dev launcher: `frontend/dev.mjs`
- Frontend build config: `frontend/vite.config.js`
- Frontend lint config: `frontend/eslint.config.js`
- Backend entry and API routes: `backend/app.py`
- Backend dependency manifest: `backend/requirements.txt`
- Prescreen engine: `scripts/data_cleaner.py`
- Apify token helper: `scripts/apify_token_manager.py`
- Field dictionary generator: `scripts/build_field_dictionary.py`
- Business docs: `docs/prd/master_vetting_sop.md`, `docs/prd/instagram_prd_mapping.md`, `docs/prd/tiktok_prd_mapping.md`, `docs/prd/youtube_prd_mapping.md`
- Machine-readable screening config: `config/field_mapping.json`
- Runtime uploads: `data/uploads/`

## Naming Conventions

- Python functions and helpers use `snake_case` in `backend/app.py` and `scripts/*.py`.
- React state, handlers, and utility variables use `camelCase` in `frontend/src/App.jsx`.
- Platform output files follow a predictable convention such as `data/<platform>/<platform>_data.json`, `..._input.json`, and `..._profile_reviews.json`.
- Export files also follow platform-based naming, for example `data/tiktok/tiktok_image_review.xlsx`.
- Docs and config names are descriptive rather than deeply nested; new process docs belong under `docs/` or `docs/prd/`.

## Where to Add New Code

- New frontend behavior currently goes into `frontend/src/App.jsx`. If the change introduces a reusable panel or card, create a new component under a future `frontend/src/components/` directory rather than extending the monolith further.
- New backend routes or orchestration helpers land in `backend/app.py` today. If a feature introduces a distinct subsystem, extract a dedicated module under `backend/` and keep the route thin.
- New prescreen rules belong in `scripts/data_cleaner.py`, with matching updates to `docs/prd/*.md`, `config/field_mapping.json`, and generated field docs.
- New manual validation scripts belong in `scripts/` with a `test_*.py` name if they are intended for repeatable checks.
- New generated samples or exports belong under `data/` or `temp/`, not alongside source files.

## Special Directories

- `data/` is generated-artifact heavy but currently tracked in git, so code review noise is common.
- `temp/` contains disposable and debug files, including non-code binaries and scratch Excel files.
- `frontend/dist/` and `frontend/node_modules/` exist in the workspace even though they are normally generated directories.
- `backend/venv/`, `backend/.venv/`, and `backend/venv_backup_20260314_vision_fix/` indicate environment state is co-located with source.
- `.planning/codebase/` is the derived codebase map created by this workflow and should be kept updated when structure or conventions materially change.
