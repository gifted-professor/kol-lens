# Requirements: 网红筛选项目 (Wanghong Screening Ops)

**Defined:** 2026-03-17
**Core Value:** An operator can turn a raw creator list into a trustworthy, reviewable screening output quickly and with minimal manual reconciliation.

## v1 Requirements

### Runtime & Access

- [ ] **RUNT-01**: Operator can start the frontend and backend using documented local commands without editing source files for credentials
- [ ] **RUNT-02**: System validates required runtime credentials and provider settings with actionable errors before critical scrape or review actions fail
- [ ] **RUNT-03**: Backend only accepts intended local or explicitly configured browser origins instead of unrestricted wildcard access
- [ ] **RUNT-04**: Vision and Apify secrets are loaded from environment variables or local auth files outside tracked source

### Intake & Scraping

- [ ] **INTK-01**: Operator can upload the approved canonical creator workbook, get clear validation errors for missing or invalid columns, and have rows routed to TikTok, Instagram, or YouTube deterministically
- [ ] **INTK-02**: Operator can start, monitor, and cancel scrape jobs from the UI for each supported platform
- [ ] **INTK-03**: Scrape runs preserve upload metadata and cache behavior consistently across cached, refreshed, and partial-result flows
- [ ] **INTK-04**: Partial or failed Apify batches show clear operator-facing error summaries without discarding successful results

### Screening & Review

- [ ] **SCRN-01**: System produces a per-profile review record with status, reason, and platform context for all scraped profiles
- [ ] **SCRN-02**: Visual review only runs on eligible passed profiles with usable covers and returns decision, reason, and signals
- [ ] **SCRN-03**: Operator can follow live visual-review progress, history, and preview assets during a running review job
- [ ] **SCRN-04**: Upload metadata used by active screening logic is merged back into review outputs and available to downstream exports

### Exports & Operator Audit

- [ ] **EXPT-01**: Operator can download raw/test/prescreen/image/final review outputs for supported platforms from the UI
- [ ] **EXPT-02**: Exported files include enough identifiers, reasons, and metadata for manual audit and follow-up
- [ ] **EXPT-03**: System preserves latest usable scrape snapshots and review JSON artifacts for later re-export or debugging
- [x] **OPER-01**: Operator can understand current scrape or visual-review job state, partial-result status, and next available actions directly from the UI
- [x] **OPER-02**: Maintainer can trace active field usage and screening logic from docs/config without reverse-engineering the whole codebase

### Verification & Maintainability

- [ ] **QUAL-01**: Maintainer can run repeatable backend verification for upload parsing, scrape finalization, and export generation against sample data
- [ ] **QUAL-02**: Maintainer can run repeatable validation for vision-review integration and frontend static checks before shipping changes
- [ ] **QUAL-03**: Core frontend and backend workflow logic are decomposed into smaller modules without changing operator-facing behavior

## v2 Requirements

### Internal Platform Expansion

- **PLAT-01**: Team can add new social-platform connectors through a reusable integration interface instead of per-platform branching in one file
- **PLAT-02**: System stores historical runs and exports in a queryable database instead of only local files

### Collaboration & Governance

- **GOV-01**: Internal users authenticate with role-based permissions before running screening workflows
- **GOV-02**: System records who uploaded, reviewed, exported, or changed screening configuration for each run

## Out of Scope

| Feature | Reason |
|---------|--------|
| Creator-facing portal or outreach CRM | Not part of the current internal screening workflow |
| Mobile application | Browser workflow is sufficient for the current operators |
| Public multi-tenant SaaS deployment | Current scope is internal-tool reliability, not hosted productization |
| Additional platform connectors | Existing three-platform workflow needs stabilization first |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| RUNT-01 | Phase 1 | Pending |
| RUNT-02 | Phase 1 | Pending |
| RUNT-03 | Phase 1 | Pending |
| RUNT-04 | Phase 1 | Pending |
| INTK-01 | Phase 2 | Pending |
| INTK-02 | Phase 2 | Pending |
| INTK-03 | Phase 2 | Pending |
| INTK-04 | Phase 2 | Pending |
| SCRN-01 | Phase 3 | Pending |
| SCRN-02 | Phase 3 | Pending |
| SCRN-03 | Phase 3 | Pending |
| SCRN-04 | Phase 3 | Pending |
| EXPT-01 | Phase 4 | Pending |
| EXPT-02 | Phase 4 | Pending |
| EXPT-03 | Phase 4 | Pending |
| OPER-01 | Phase 4 | Complete |
| OPER-02 | Phase 4 | Complete |
| QUAL-01 | Phase 5 | Pending |
| QUAL-02 | Phase 5 | Pending |
| QUAL-03 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 20 total
- Mapped to phases: 20
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-17*
*Last updated: 2026-03-18 after Phase 4 plan 03 completion*
