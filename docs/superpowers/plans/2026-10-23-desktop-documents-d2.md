# Desktop document learning implementation plan

> **For agentic workers:** Use superpowers:executing-plans. Preserve the separate desktop checkout. Implement directly with test-first verification and one independent final review.

**Goal:** Import, read, search and resume PDF, DOCX, PPTX, TXT and Markdown locally without Office or Docker.

**Architecture:** Keep the proven PDF reader. Add an immutable document source/rendition service and a structured reader for non-PDF sources. Persist source-bound imports and versioned positions in additive tables; never repurpose PDF page numbers for blocks.

**Tech Stack:** Existing FastAPI, SQLAlchemy/SQLite, Python standard OOXML/ZIP parsing, Vue 3 and Element Plus.

**Spec:** `docs/superpowers/specs/2026-10-20-windows-local-app-design.md`, sections 6–8, V3–V8; subsequent AI/fill and backup work remains tracked separately.

## Global Constraints

- Work only in `E:\项目\学习系统应用版`; original web checkout and real learning data are not test fixtures.
- No external document resources, executable HTML, Office dependency, or invented formula corrections.
- Preserve all existing PDF reading and progress contracts, questions and learning history.
- New tables use explicit, idempotent schema migration. Failed imports do not replace published reading content.
- Structured content and locations belong to a particular immutable source and rendition.

## Review Focus

1. Malformed OOXML, traversal, entities, enormous expanded archives: reject before content publication (Task 1).
2. Repeated or failed uploads must not mix old/new content or remove manual questions (Task 2).
3. Chinese content after block 1000 and unsafe Markdown: searchable, no remote execution (Tasks 1, 3).
4. Old reading location after source replacement: retain the old version; never silently jump (Tasks 2, 3).
5. Stale UI responses and failed position saves: don't overwrite a newer selected book or pretend saved (Task 4).

### Task 1: Safe structured parsers

**Files:** create `backend/app/services/document_parser.py`, `backend/tests/test_document_parser.py`.

**Interfaces:** `parse_document(data: bytes, filename: str, encoding: str = 'auto') -> dict` returns format, ordered blocks, warnings; blocks have id, kind, text, optional level/slide/cells/image. Strict size/ZIP limits; OOXML relationships never fetched. PNG/JPEG/GIF/WebP only for embedded pictures. UTF-8/BOM default; explicit GB18030 selection when decoding is ambiguous.

- [ ] Add tests for literal Chinese Markdown headings/table/code, DOCX heading/table/image, PPTX slide order, encoding error, unsafe archives and unknown formulas.
- [ ] Run `.venv/Scripts/python.exe -m pytest tests/test_document_parser.py -q -o addopts=''`; expect missing parser failures.
- [ ] Implement parser and bounded validation.
- [ ] Run same tests; expect pass.
- [ ] Commit parser and tests after verification.

### Task 2: Immutable import and migration

**Files:** `models.py`, `services/schema_upgrades.py`, new `services/documents.py`, `api/documents.py`, `api/imports.py`, `services/import_dispatch.py`, `main.py`; test `tests/test_documents.py`.

**Interfaces:** additive `DocumentSource`, `DocumentRendition`, `DocumentImport`, `DocumentPosition`. `process_document_import(task_id: str) -> None`. `GET /textbooks/{id}/document` returns current rendition or null. `GET /textbooks/{id}/document/versions/{revision}` retrieves retained content. `POST /textbooks/{id}/document/retry` retries latest failed source without replacing book. Upload continues returning `ImportTaskRead`.

- [ ] Write API tests: upload/chapters/content/search, failed retry retains content, ownership, immutable versions and repeat upgrade.
- [ ] Run tests, expect unsupported-format/route failures.
- [ ] Implement immutable file storage, source-bound jobs, transactional publish and safe retries. Keep manual chunks/questions.
- [ ] Run document and existing PDF/import/upgrade tests; expect pass.
- [ ] Commit validated backend change.

### Task 3: Search and versioned positions

**Files:** `api/documents.py`, `services/documents.py`, `api/rag.py`, `schemas.py`; test `tests/test_documents.py`.

**Interfaces:** `GET /textbooks/{id}/document/search?q=...`; `GET/PUT /textbooks/{id}/document/position` with source_id/source_revision/rendition_revision/kind/unit_id/expected_revision; `GET /documents/recent`; citations carry an optional authoritative locator.

- [ ] Add tail-block search, source/position mismatch, optimistic conflict, old version and RAG locator tests.
- [ ] Run tests and observe failures.
- [ ] Implement bounded streaming retrieval (no 1000-chunk cutoff), position validation and retained versions.
- [ ] Run tests; expect pass.
- [ ] Commit validated search/position change.

### Task 4: Learner UI and integration

**Files:** new `frontend/src/api/documents.ts`, `components/StructuredDocumentReader.vue`, `views/DocumentStudyView.vue`, `views/TextbookEntryView.vue`; modify `router/index.ts`, `views/TextbooksView.vue`, `views/DashboardView.vue`, `views/RagView.vue`; new component/API tests.

**Interfaces:** entry view routes legacy PDF to existing view and published structured material to new view. Reader renders Vue-escaped text and validated embedded images; accepts source/rendition/unit query for source links.

- [ ] Write UI tests for safe rendering, directory jump, source mismatch and progress failure/retry.
- [ ] Run frontend tests and observe expected missing components/behavior.
- [ ] Implement upload format/encoding selection, directory/search/reading/position, import retry and source navigation.
- [ ] Run full backend/frontend tests and production build; expect green, report existing fixture skips.
- [ ] Independent review, fix important findings with regression tests, then commit and update delivery evidence.

## Execution ledger

2026-10-23: User requests core functionality and repeated continuation. Continue the already chosen desktop architecture and direct execution approach; no new product-choice interview. Current checkout clean at aa78d08. D2 first because AI/fill need authoritative source content. AI settings, textbook fill, backup/restore and revised installer are still required, not claimed complete by this plan.

2026-10-26 completion record: Tasks 1–4 implemented at fae23b4, b35e574, 2623216 and da40752. One independent review found five Important issues; all reproduced and fixed with regression tests. Final verification: frontend 125 passed and production build passed; backend 191 passed / 4 optional real-PDF skips, including three tests against the rebuilt test.2 executable. Additive active-rendition and source-chapter mappings support retry and source-isolated directories. Markdown companion images remain deferred as documented, so the full product spec V5 is not claimed. Test installer, hashes, decisions, compatibility limits and deferred minors are recorded in docs/DESKTOP_DOCUMENTS_D2.md. Keep the user-requested independent desktop branch; no merge to the web checkout and no remote push. AI settings, content-based question fill and backup/restore remain subsequent approved batches, not completed by D2.
