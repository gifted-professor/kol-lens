# Technology Stack

## Languages

- Python drives the backend API and the rule-based prescreen pipeline in `backend/app.py` and `scripts/data_cleaner.py`.
- JavaScript with JSX drives the frontend in `frontend/src/App.jsx` and `frontend/src/main.jsx`.
- JSON is a first-class storage and interchange format across `data/<platform>/*.json`, `config/field_mapping.json`, and upload metadata snapshots.
- Markdown is used for product rules and operator documentation in `README.md` and `docs/prd/*.md`.

## Runtime

- The frontend expects a local Node.js runtime for `vite`, `eslint`, and the custom dev launcher in `frontend/dev.mjs`.
- The backend runs on Flask under Python from `backend/venv/bin/python`; there is also a separate `backend/.venv/`.
- `frontend/dev.mjs` explicitly launches the backend via `/usr/bin/arch -x86_64`, so local development currently assumes macOS with Rosetta available.
- There is no container, Procfile, or deployment descriptor in the repo. The current workflow is local-process based.

## Frameworks

- `Flask` provides the HTTP API in `backend/app.py`.
- `flask-cors` enables browser access during local development in `backend/app.py`.
- `React 19` renders the single-screen UI in `frontend/src/App.jsx`.
- `Vite 8` handles frontend development and builds via `frontend/package.json` and `frontend/vite.config.js`.
- `@tailwindcss/vite` and Tailwind CSS v4 are used through utility classes in `frontend/src/App.jsx` and `frontend/src/index.css`.
- `framer-motion` is used for transitions and animated card reveal behavior in `frontend/src/App.jsx`.

## Key Dependencies

- Backend data handling depends on `pandas`, `openpyxl`, and `xlrd` for Excel parsing and exports in `backend/app.py`.
- Vision review depends on `openai`, `requests`, and `Pillow` in `backend/app.py`.
- Scrape orchestration depends on `requests` plus local token state files referenced by `backend/app.py` and `scripts/apify_token_manager.py`.
- Frontend UI dependencies are intentionally small: `react`, `react-dom`, `lucide-react`, and `framer-motion` in `frontend/package.json`.
- Linting is configured with `eslint`, `@eslint/js`, `globals`, `eslint-plugin-react-hooks`, and `eslint-plugin-react-refresh` in `frontend/eslint.config.js`.

## Configuration

- Runtime configuration is mainly environment-variable based inside `backend/app.py`, especially for vision providers, Apify retry behavior, batch sizing, and timeouts.
- `frontend/dev.mjs` injects development defaults for vision-provider connectivity and launches frontend plus backend together.
- `config/field_mapping.json` is a machine-readable business-config document that describes upload and scraper field usage.
- `scripts/build_field_dictionary.py` regenerates `docs/field_dictionary.md` from `config/field_mapping.json`.
- Platform-specific runtime outputs follow stable filenames such as `data/tiktok/tiktok_data.json` and `data/instagram/instagram_profile_reviews.json`.

## Platform Requirements

- Local writes to `data/` and `temp/` are required for uploads, raw scrape snapshots, exports, and temporary visual-review artifacts.
- Apify access expects `~/.apify/auth.json` and optionally `~/.apify/token_manager_state.json`, as referenced in `backend/app.py`.
- Vision review expects either `OPENAI_API_KEY` or provider-specific env vars such as `VISION_QUAN2GO_API_KEY`.
- The codebase assumes direct access to the public internet for Apify, image downloads, and OpenAI-compatible providers.
- The repo currently carries generated artifacts such as `frontend/dist/`, `frontend/node_modules/`, and Python virtualenv directories, so local workspace state is part of the practical runtime footprint.
