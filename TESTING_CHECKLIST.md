# AGRA Testing Checklist — Phase G Verification

## Environment Setup
- [ ] Backend running on `AGRA_API_PORT` (default 8005)
- [ ] Frontend running on `AGRA_UI_PORT` (default 7860)
- [ ] Vector store initialised and accessible
- [ ] LLM inference endpoint responsive

---

## Phase A — Backend Hardening

### A1: documents.py Logger Fix
- [ ] Upload any document via Dashboard or Chat
- [ ] Verify no `NameError` on `logger` in backend logs
- [ ] Check `api/documents.py` uses `logger = logging.getLogger(...)` consistently

### A2: Quiz JSON Parsing
- [ ] In Chat, request: "Generate a quiz about ship safety"
- [ ] Verify quiz renders as `InlineQuiz` component (not raw JSON)
- [ ] Test with malformed LLM output (e.g. truncated JSON) — verify repair pass handles it
- [ ] Confirm depth-counting bracket matcher works with nested quotes/brackets

### A3: Text Sanitization
- [ ] Ask LLM a question that might trigger mojibake (e.g. queries with special chars)
- [ ] Verify `clean_llm_output` strips LaTeX commands and fixes common encoding issues
- [ ] Check streamed tokens do not contain garbled Unicode

---

## Phase B — Concurrent SSE & Session Management

### B1: Backend SessionManager
- [ ] Trigger a long-running background job (PPT generation or compliance check)
- [ ] Verify job status endpoint returns `pending` → `running` → `completed`
- [ ] Confirm jobs are isolated per session (job ID scoped to session)

### B2: Chat.jsx Concurrent SSE
- [ ] Open multiple chat tabs/sessions
- [ ] Start streaming in Session A, then switch to Session B and start another stream
- [ ] Verify both sessions stream simultaneously without cross-contamination
- [ ] Confirm aborting one session does not kill the other session's stream
- [ ] Check session list shows streaming indicator (spinning dot) only on active sessions
- [ ] Verify `streamRefs` is keyed by session ID (inspect React DevTools or console)

---

## Phase C — Upload & Metadata

### C1: Upload Endpoint
- [ ] `POST /api/agent/upload` with `document_type=bid`, `bidder_key=Bidder-A`, `problem_statement=Tender-123`
- [ ] Verify SSE stream stages: `saved` → `metadata_extraction` → `chunking` → `embedding` → `done`
- [ ] Confirm response includes `doc_id`, `filename`, `chunks`, `pages`
- [ ] Test `auto_extract=true` — verify backend extracts metadata automatically

### C2: Chat Upload Wizard
- [ ] In Chat, click upload and select multiple files
- [ ] Verify per-file metadata capture form appears
- [ ] Fill in `document_type`, `bidder_key`, `problem_statement` for each file
- [ ] Confirm upload progress updates via SSE in the wizard UI
- [ ] After upload, verify documents appear in chat context selector

---

## Phase D — Bid Comparison

### D1: Intent Detection
- [ ] In Chat, type: "Compare bids for Tender-123"
- [ ] Verify backend detects `bid_compare` intent and extracts `problem_statement`
- [ ] Test without problem statement: "Compare the bids" → should return `available: false` or prompt for clarification

### D2/D3: Branch-Isolated Comparison
- [ ] Upload at least 2 bid documents with the **same** `problem_statement`
- [ ] In Chat, request comparison → verify `runBranchComparison` calls `/api/agent/compare/bids/branch`
- [ ] Check SSE progress events: `evaluating` per bidder/standard pair
- [ ] Confirm final response contains `executive_summary`, `recommendation`, `standards_table`, `findings_by_bidder`

### D4: ComparisonCard UI
- [ ] After branch comparison completes, verify `ComparisonCard` renders in Chat
- [ ] Check branch badges show correct bidder keys with colored pills
- [ ] Expand per-bidder findings — verify standard IDs, verdicts, severity dots
- [ ] Confirm standards compliance matrix is collapsible
- [ ] Verify recommendation winner is highlighted with trophy icon
- [ ] Test download report button (if `download_url` present)

---

## Phase E — Compliance Wizard

### E: 3-Step Wizard with Inline Upload
- [ ] Navigate to `/compliance`
- [ ] **Step 1**: Select subject document(s); verify inline upload button works
- [ ] Upload a new document inline in Step 1 — confirm it appears and is auto-selected
- [ ] **Step 2**: Select standard document(s); verify inline upload button works
- [ ] Upload a new standard inline in Step 2 — confirm it appears and is auto-selected
- [ ] **Step 3**: Click "Run Compliance Check"
- [ ] Verify SSE streaming findings appear grouped by topic
- [ ] Confirm summary bar shows counts for Compliant / Non-Compliant / Partial / Missing / Contradiction / Unverifiable
- [ ] Download compliance report `.docx` and verify contents

---

## Phase F — PPT Generation

### F1: Exact Slide Count
- [ ] Request PPT with `num_slides=5` — verify output has exactly 5 slides
- [ ] Request PPT with `num_slides=15` — verify output has exactly 15 slides
- [ ] Test edge case: LLM returns fewer slides → verify padding with `section_header` slides
- [ ] Test edge case: LLM returns more slides → verify trimming from middle preserves title + thank_you

### F2: Matplotlib Charts
- [ ] Upload a document with numerical data (tables, statistics)
- [ ] Request PPT including charts — verify `chart` layout slides render bar/line/pie charts
- [ ] Check charts use ICG dark theme (navy background, gold/teal accents)
- [ ] Confirm chart images are embedded correctly and not truncated

### F3: Sources Slide
- [ ] Generate PPT using uploaded documents
- [ ] Verify second-to-last slide is "Sources & References"
- [ ] Confirm source slide lists all referenced document filenames
- [ ] Check that total slide count still equals requested `num_slides`

---

## Regression Tests
- [ ] Normal Q&A chat still works (no intent detected)
- [ ] Summary generation works (`/generate/summary`)
- [ ] PPT revision flow works (`revision_prompt` + `previous_slides_json`)
- [ ] Drawing extraction and parameter display works
- [ ] Authentication / logout / protected routes still functional

---

## Notes
- Run backend with `LOG_LEVEL=DEBUG` for detailed SSE and intent detection logs.
- Use browser DevTools Network tab to inspect SSE streams for upload, compliance, and chat.
- For frontend issues, check React console for state mutation warnings (should be none).
