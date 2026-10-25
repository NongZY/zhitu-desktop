# Desktop AI, textbook practice and backup implementation plan

> **For agentic workers:** Use superpowers:executing-plans. User already chose direct implementation with one independent final review, and on 2026-10-26 explicitly requested completion of these remaining features. Preserve the separate desktop checkout and the test.2 tag; do not reopen the approved product choices.

**Goal:** Let learners optionally connect their own AI, generate and confirm source-linked textbook practice, and back up/restore their local learning space from the desktop settings.

**Architecture:** Add a desktop-only protected AI service, immutable evidence-bound practice jobs/candidates, and validated SQLite-plus-originals backup archives. Restore stages a separate space and activates it on restart; the previous space remains available. Existing Vue/FastAPI/Python desktop architecture continues.

**Tech Stack:** Vue 3/Element Plus, FastAPI, SQLAlchemy/SQLite, httpx, Windows DPAPI, standard ZIP/hash/SQLite backup APIs.

**Spec:** `docs/superpowers/specs/2026-10-20-windows-local-app-design.md` sections 9–13 and `docs/superpowers/specs/2026-10-20-textbook-question-fill-design.md`.

## Global Constraints

- Work only in `E:\项目\学习系统应用版`; never test against real learning data or mutate the preserved web checkout.
- AI defaults off, has separate Q&A/practice switches, no environment credential inheritance, no silent paid retries. Tests use synthetic documents and a fake HTTP transport, not real keys/providers.
- Remote URLs require HTTPS; explicit loopback endpoints may use HTTP. No redirects or inherited proxies. Keys use current-user DPAPI and never appear in read responses, logs or backups.
- Questions come from selected actual textbook content. Five types, reference locators owned by the server, preview/edit/confirm before practice. Rules are limited by explicit concepts in body text, not titles.
- Preserve questions/history, additive idempotent schema upgrades, snapshots for newly created exam papers. Legacy histories without snapshots are not certified as original versions.
- Consistent SQLite backup includes managed originals and integrity manifest, excludes API configuration/secrets/logs. Restore validates in a separate directory and switches only on restart, preserving current data.
- This implementation is desktop-only; shared fill design remains the contract for a future separately authorized web port. No genuine user data migration or clean-machine compatibility claims.

## Review Focus

1. Settings changed/disabled while paid calls run: cancel best-effort, discard late results, never leak error bodies or keys (Task 1).
2. Same-titled chapters with different actual content, replaced files and deleted chapters: no guessed topic or stale candidate confirmation (Task 2).
3. Repeated clicks, partial/bad AI output, false answers and cancelled batches: stable jobs, no duplicate saved questions or false completion (Task 2).
4. ZIP traversal/bombs, missing/tampered originals, SQLite WAL and interrupted restore: reject safely, preserve the current space (Task 3).
5. Packaged desktop file saving and restore restart: user can operate with buttons, no source Python/Node required; earlier records remain intact (Task 4).

### Task 1: Protected AI settings and grounded Q&A

**Files:** create `backend/app/desktop/secrets.py`, `backend/app/services/ai_connection.py`, `backend/app/api/desktop_settings.py`, `backend/tests/test_ai_connection.py`; modify `api/rag.py`, `schemas.py`, `main.py`.
**Interfaces:** `AIConnection(root: Path, transport=None)` exposes `public()`, `save(payload: dict)`, `async complete(purpose, messages, *, consent=False) -> dict(status, text, model, notice)`. `connection_for(root)` caches live cancellation state. Desktop GET/PUT `/settings/ai`, POST `/settings/ai/test`; test requires explicit cost acknowledgment. Q&A has an explicit `use_ai` request flag and returns mode/status/notice while retaining local citations.

- [ ] Write tests: default-off no network; DPAPI round trip/secret-free reads; per-use permission and test consent; status 401/429/quota/timeout/malformed; no redirects; disable cancels pending call.
- [ ] Run `python -m pytest tests/test_ai_connection.py -q -o addopts=`; expect missing service failures.
- [ ] Implement bounded OpenAI-compatible Chat Completions, atomic config, protected key storage and safe status mapping. Retrieve only up to 5 snippets/500 chars for AI; unresolved formulas stay local.
- [ ] Run tests and desktop isolation regressions; expect pass. Commit.

### Task 2: Evidence-bound textbook practice and history

**Files:** new `services/textbook_practice.py`, `api/textbook_practice.py`, `services/question_snapshots.py`, `tests/test_textbook_practice.py`; modify models/schema upgrades/questions/exams/learning/basic_practice.
**Interfaces:** GET `/textbooks/{id}/practice/coverage`; POST `/textbooks/{id}/practice/jobs` takes stable request_id, chapter_id, mode rules/ai/extract, count per chapter, question_types and external-call acknowledgment. GET job, POST cancel, PATCH candidate, POST confirm with candidate IDs. `PracticeJob` binds owner/book/source/rendition and immutable evidence units; `PracticeCandidate` stores validated typed content, evidence/provenance, saved question ID. `ExamPaperQuestion.snapshot` freezes new paper contents and grading.

- [ ] Write tests for source-based rules on body-only materials, title-only refusal, five answer structures, reference ownership, unconfirmed exclusion, edit/confirm idempotency, stale source/chapter rejection, chapter batching beyond 1000 chunks and cancellation/partial output.
- [ ] Run focused tests; expect missing interfaces/behavior failures.
- [ ] Implement bounded per-chapter candidates, limited deterministic templates, AI structured JSON validation and finite explicit-answer extraction; no answer guessing. Persist task/candidate states, startup interruption recovery, no automatic paid retry.
- [ ] Snapshot newly created exams and use snapshots for grading/results; prevent deleting questions required by existing papers. Test edits cannot rewrite old scores/answers.
- [ ] Run practice/history/migration regressions and commit.

### Task 3: Consistent backup and staged restore

**Files:** new `desktop/maintenance.py`, `api/desktop_maintenance.py`, `tests/test_desktop_maintenance.py`; modify desktop profile/service/security/window as needed.
**Interfaces:** POST `/maintenance/backups`, GET download by server ID; POST `/maintenance/restores` accepts archive, returns verified counts/token; POST confirm stages next-start activation, DELETE cancels pending activation. Root owns a validated active-space pointer; `resolve_active_space(root)` runs before profile/config initialization. Settings exposes fixed open-data-folder action, never arbitrary path execution.

- [ ] Write WAL-inclusive round-trip, omitted secrets, all source paths rebased, tamper/traversal/duplicate/oversize rejection, failed restore leaves original and startup activation tests.
- [ ] Run tests; expect missing maintenance service.
- [ ] Use SQLite backup API and immutable originals; reject busy imports/generation. Validate manifest/database/schema/owner/paths and stage all files. Confirm switches at next startup only; block further writes while scheduled. Preserve previous root and pointer for rollback.
- [ ] Run maintenance/startup/security regressions and commit.

### Task 4: Learner UI, integration and test.3 package

**Files:** new `frontend/src/views/SettingsView.vue`, `PracticeFillView.vue`, API adapters/tests; modify routes/layout/RagView/textbook links/native bridge; update packaging and delivery docs.
**Interfaces:** Settings contains AI purpose toggles, endpoint/model/key entry, save/clear/test and explained data export/import. Practice page selects book/chapter/types, shows proposed outbound scope/provider, job progress and candidates with source links/edit/confirm. Q&A defaults local with explicit AI choice/status. Native download uses same-origin authorization and a real save dialog.

- [ ] Write user-visible tests for secret clearing/masking, local fallback, candidate preview/confirmation, pending restore and disabled actions.
- [ ] Run UI tests RED, implement, rerun GREEN; build production UI.
- [ ] Run full backend/frontend suites and real desktop service flow using temporary data. One independent whole-branch review; important findings get one tested fix pass.
- [ ] Build `0.2.0-test.3`, run packaged flows, commit evidence and retain test.2. Deliver installer and exact limitations; no automatic install or live API call.

## Execution decisions

2026-10-26: Current user instruction authorizes implementing the remaining AI/fill/backup features, not another approval cycle. Native/direct execution method retained. Rooted restoration is chosen over overwriting a live SQLite database; extra disk space and a restart are the costs. Windows DPAPI is chosen without a third-party keyring dependency. Original web version remains untouched as explicitly requested; its future feature port is outside this desktop batch. Full Office rendering/local LLM weights/OCR/clean Windows distribution remain outside these three features. Source-linked Markdown images and minor reading/installer issues from D2 remain separately recorded; do not imply they are fixed by AI settings.
