# Roadmap: 网红筛选项目 (Wanghong Screening Ops)

## Overview

This roadmap treats the current repository as a working but fragile brownfield system. The sequence starts by removing unsafe runtime assumptions, then stabilizes intake and screening behavior, makes outputs easier to trust and audit, and finishes by adding repeatable verification plus codebase decomposition so future phases can move faster without re-breaking core workflows.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Runtime Hardening** - Remove unsafe runtime assumptions and make local operation deterministic
- [ ] **Phase 2: Intake & Scrape Reliability** - Stabilize upload normalization, batch scrape behavior, and operator job control
- [ ] **Phase 3: Screening & Visual Review Consistency** - Make prescreen and visual-review outputs consistent across supported platforms
- [ ] **Phase 4: Audit-Ready Outputs** - Improve exports, artifact traceability, and operator clarity during active workflows
- [ ] **Phase 5: Verification & Modularization** - Add regression safety and split core monolith hotspots without changing workflow behavior

## Phase Details

### Phase 1: Runtime Hardening
**Goal**: Operators can run the system safely with documented configuration and without relying on checked-in secrets or unrestricted local access.
**Depends on**: Nothing (first phase)
**Requirements**: [RUNT-01, RUNT-02, RUNT-03, RUNT-04]
**Success Criteria** (what must be TRUE):
  1. Operator can boot the frontend and backend from documented commands using environment-driven credentials.
  2. Missing or invalid provider configuration surfaces actionable errors before a long-running job fails.
  3. Browser access is limited to intended local or configured origins instead of wildcard access.
  4. No checked-in runtime secret is required for local development or smoke testing.
**Plans**: 3 plans

Plans:
- [ ] 01-01: Audit and remove checked-in secret fallbacks, then document the supported runtime credential paths
- [ ] 01-02: Add backend runtime/config validation for scrape and vision providers with clear operator-facing failures
- [ ] 01-03: Tighten local access defaults and verify the frontend can still reach the backend in the supported dev setup

### Phase 2: Intake & Scrape Reliability
**Goal**: Operators can upload source spreadsheets and run scrape jobs with predictable platform routing, partial-result handling, and cancellation behavior.
**Depends on**: Phase 1
**Requirements**: [INTK-01, INTK-02, INTK-03, INTK-04]
**Success Criteria** (what must be TRUE):
  1. Operator can upload mixed or imperfect spreadsheet inputs and get correct platform routing and metadata capture.
  2. Operator can start, monitor, and cancel scrape jobs from the UI for each supported platform.
  3. Cached and force-refresh runs behave predictably and preserve successful results during partial failures.
  4. Batch-level scrape failures show clear summaries without hiding successfully returned profiles.
**Plans**: 3 plans

Plans:
- [ ] 02-01: Harden upload parsing and platform-routing logic with sample-file coverage for header/no-header variants
- [ ] 02-02: Normalize scrape job state, progress payloads, and cancellation behavior across platforms
- [ ] 02-03: Stabilize Apify batch retry, cache, and partial-result handling so successful data is preserved and surfaced clearly

### Phase 3: Screening & Visual Review Consistency
**Goal**: Operators can trust that prescreen and visual-review decisions are generated consistently and carry the context needed for manual review.
**Depends on**: Phase 2
**Requirements**: [SCRN-01, SCRN-02, SCRN-03, SCRN-04]
**Success Criteria** (what must be TRUE):
  1. Every scraped profile yields a review record with a stable status and reason schema.
  2. Visual review only runs on eligible profiles with usable cover candidates and returns decision, reason, and signals.
  3. Operator can observe live visual-review progress, current preview, and completed history without losing context.
  4. Upload metadata used by screening rules remains available in downstream review outputs.
**Plans**: 3 plans

Plans:
- [ ] 03-01: Normalize prescreen output contracts across TikTok, Instagram, and YouTube review records
- [ ] 03-02: Harden cover-candidate, collage, and live visual-review state handling for error cases and partial progress
- [ ] 03-03: Verify upload-metadata merge paths so active screening rules and exports read the same source of truth

### Phase 4: Audit-Ready Outputs
**Goal**: Operators can export trustworthy review artifacts and understand workflow status and follow-up context directly from the tool.
**Depends on**: Phase 3
**Requirements**: [EXPT-01, EXPT-02, EXPT-03, OPER-01, OPER-02]
**Success Criteria** (what must be TRUE):
  1. Operator can download all supported raw and review outputs from the UI for each platform.
  2. Exported files contain identifiers, reasons, and metadata sufficient for manual audit and follow-up.
  3. Latest raw and review artifacts can be reused for re-export or debugging without rerunning the full scrape.
  4. Operator can tell whether the UI is showing live, partial, cached, or completed results and what action is available next.
  5. Maintainer can trace active field mappings and screening-rule dependencies from repo docs and config.
**Plans**: 3 plans

Plans:
- [ ] 04-01: Unify export row contracts and verify each export path includes the identifiers and metadata operators need
- [ ] 04-02: Improve artifact retention and raw/review snapshot reuse for debugging and re-export flows
- [ ] 04-03: Refresh UI status copy plus field/rule documentation so operator and maintainer expectations match the code

### Phase 5: Verification & Modularization
**Goal**: Maintainers can validate critical workflows quickly and evolve the codebase through smaller modules instead of one-file hotspots.
**Depends on**: Phase 4
**Requirements**: [QUAL-01, QUAL-02, QUAL-03]
**Success Criteria** (what must be TRUE):
  1. Maintainer can run repeatable backend verification for upload, scrape-finalization, and export flows against sample data.
  2. Maintainer can run frontend static checks and vision-review smoke validation before shipping changes.
  3. Core workflow logic is split into smaller modules while operator-visible behavior remains unchanged.
**Plans**: 2 plans

Plans:
- [ ] 05-01: Add repeatable validation scripts or tests for critical backend, frontend, and vision-integration paths
- [ ] 05-02: Extract the largest backend and frontend workflow hotspots into maintainable modules with parity verification

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 1.1 → 1.2 → 2 → 2.1 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Runtime Hardening | 0/3 | Not started | - |
| 2. Intake & Scrape Reliability | 0/3 | Not started | - |
| 3. Screening & Visual Review Consistency | 0/3 | Not started | - |
| 4. Audit-Ready Outputs | 0/3 | Not started | - |
| 5. Verification & Modularization | 0/2 | Not started | - |
