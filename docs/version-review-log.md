# Version Review Log

Use this file to record each meaningful repository update so the next operator can quickly audit what changed, why it changed, and how it was verified.

## Entry Template

### YYYY-MM-DD - Short Title
- Owner:
- Scope:
- Related files:
- Summary:
- Backend changes:
- Frontend changes:
- Data or docs changes:
- Verification:
- Known issues / follow-up:

## 2026-03-14 - Visual Review Baseline
- Owner: Codex
- Scope: Restore backend environment, add collage-based visual review, document repository workflow.
- Related files: `backend/app.py`, `backend/requirements.txt`, `frontend/src/App.jsx`, `scripts/test_openai_vision.py`, `AGENTS.md`
- Summary: Added `/api/evaluate_influencer` to evaluate up to 9 covers as a 3x3 collage through the proxy model endpoint and exposed a frontend button to run visual review after scraping.
- Backend changes: Added SSE-compatible OpenAI response parsing, remote image download, collage generation with Pillow, and structured JSON output for `success`, `username`, `decision`, `reason`, and `signals`.
- Frontend changes: Added visual review trigger, per-profile progress, and result display in the scrape success panel.
- Data or docs changes: Rebuilt `backend/venv` for x86_64 compatibility, added `AGENTS.md`, and created this review log.
- Verification: Confirmed Excel upload/export routes return `200`; confirmed `/api/evaluate_influencer` returns `200` with `Pass` output for sample TikTok review data.
- Known issues / follow-up: `signals` are returned but not yet rendered separately in the UI; urllib3 emits a LibreSSL warning but requests currently succeed.
