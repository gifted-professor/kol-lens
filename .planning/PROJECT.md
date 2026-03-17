# 网红筛选项目 (Wanghong Screening Ops)

## What This Is

This is a brownfield internal operations tool for screening influencer lists across TikTok, Instagram, and YouTube. Operators upload spreadsheet-based creator lists, run scraper-backed intake, apply rule-based prescreening, trigger visual review for eligible accounts, and export audit-ready review files. The current project scope is not to invent a new product line, but to harden, simplify, and make the existing workflow safer to maintain.

## Core Value

An operator can turn a raw creator list into a trustworthy, reviewable screening output quickly and with minimal manual reconciliation.

## Requirements

### Validated

- ✓ Operators can upload creator lists and route rows to TikTok, Instagram, and YouTube inputs — existing
- ✓ Operators can run scrape jobs with progress polling, caching behavior, and cancellation support — existing
- ✓ Operators can generate per-profile prescreen decisions and launch visual review for eligible profiles — existing
- ✓ Operators can export raw, prescreen, image-review, test-info, and final-review outputs — existing

### Active

- [ ] Harden runtime configuration, secret handling, and local access controls so the tool is safe to operate and share internally
- [ ] Make upload, scrape, prescreen, visual-review, and export workflows more predictable across partial failures and edge-case inputs
- [ ] Add repeatable verification and reduce monolithic frontend/backend hotspots without breaking operator-facing behavior

### Out of Scope

- Public creator marketplace or creator-facing portal — this repo is an internal operator workflow, not a consumer product
- Multi-tenant SaaS collaboration, billing, or account management — not needed for the current internal-tool scope
- Mobile app clients — desktop browser workflow is the current delivery target
- New social-platform integrations beyond TikTok, Instagram, and YouTube — stabilize the existing platform set first

## Context

- The product intent is documented in `README.md`, `docs/prd/master_vetting_sop.md`, and platform-specific PRD mapping files under `docs/prd/`.
- The current implementation is a React + Vite frontend in `frontend/src/App.jsx`, a Flask backend in `backend/app.py`, and a rule engine in `scripts/data_cleaner.py`.
- Runtime persistence is file-based under `data/` and `temp/`; there is no database or queue.
- The repo already has a brownfield codebase map in `.planning/codebase/`, which identifies monolithic hotspots, tracked runtime artifacts, and current security concerns.
- Current business logic depends on synchronized updates across code, `config/field_mapping.json`, generated field docs, and PRD files.

## Constraints

- **Tech stack**: Keep the existing React/Vite frontend and Flask/Python backend — the repo is already operating in this stack and a rewrite would delay stabilization work
- **Brownfield**: Preserve existing operator-facing workflows while improving them — this is a hardening and maintainability initiative, not a greenfield redesign
- **Runtime environment**: The tool depends on Apify access, OpenAI-compatible vision providers, remote image downloads, and writable local `data/` directories — core workflows must continue to function in that environment
- **Security**: Secrets must move out of tracked source and local access defaults must be safer — current checked-in fallbacks and wildcard CORS are not acceptable long term
- **Auditability**: Review outputs must remain explainable and traceable to uploaded identifiers, screening reasons, and exported files — manual reconciliation is expensive for operators

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Treat this initialization as brownfield hardening, not greenfield feature ideation | The repo already contains a live multi-platform screening workflow with documented SOPs and generated outputs | — Pending |
| Keep file-based storage for the current milestone | Existing workflows, exports, and debugging habits all depend on `data/<platform>/` artifacts; storage migration is not the first bottleneck | — Pending |
| Prioritize safety, determinism, and verification before new platform scope | The codebase map shows security, testing, and monolith risks that can compromise every future feature | — Pending |

---
*Last updated: 2026-03-17 after initialization*
