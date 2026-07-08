# AGRA — SOTR Compliance Verification Engine: Rebuild Specification

## 0. Instructions to you (the coding assistant)

The current Compliance feature in this codebase produces incorrect output. Do not patch it
incrementally by guessing — first **audit the existing implementation** against the spec below,
identify every place it deviates, then refactor/rebuild the affected modules so the feature matches
this spec exactly. Do not change unrelated modules (ingestion pipeline internals, RAG query
pipeline, PPTX generation, genealogy graph) unless this spec explicitly requires it.

Before writing code, produce a short written diff of "current behavior vs. required behavior" for
my review. Then implement.

---

## 1. Feature Overview

The Compliance feature evaluates a vendor's bid submission against a buyer's requirement document
(the SOTR) and produces a clause-by-clause verdict report as a downloadable `.docx` file.

The workflow has exactly **two upload stages**, both required before the "Start Compliance" action
becomes available.

---

## 2. Stage 1 — SOTR Upload Block (UI)

Fields:

1. **Reference Name** (text input, required) — a free-text label the user types in. This value is
   used as:
   - The report's title / cover page heading
   - The generated file's name, e.g. `<reference_name>_Compliance_Report.docx` (sanitize for
     filesystem-safe characters: strip/replace `\ / : * ? " < > |` and trim to a safe length)
   - Stored alongside the compliance run record so past runs can be searched/filtered by this name
2. **SOTR Commercial file** (single file upload, required) — the buyer's commercial/bid document
   (contains eligibility, EMD, turnover, experience, certificates-required, ATC clauses, etc.)
3. **SOTR Technical file** (single file upload, required) — the buyer's technical requirements /
   specification document

Both SOTR files are tagged with `bundle_role = "SOTR"` on ingestion, but each retains its own
`doc_id`, `doc_name`, and `sub_role` (`"commercial"` or `"technical"`) so every extracted clause can
be traced back to which specific file it came from.

**Validation rule:** "Start Compliance" must NOT be enabled until Reference Name is non-empty AND
both SOTR files are uploaded AND both Vendor files (below) are uploaded. Show inline validation
errors per missing field, do not silently disable the button with no explanation.

---

## 3. Stage 2 — Vendor Submission Upload Block (UI)

Fields:

1. **Vendor Commercial file** (single file upload, required) — the vendor's GeM/commercial
   submission (certificates, EMD proof, turnover documents, declarations, etc.)
2. **Vendor DPR / Technical Response file** (single file upload, required) — the vendor's detailed
   technical response / project report that corresponds to the SOTR Technical file

Both vendor files are tagged `bundle_role = "SUBMISSION"`, with `sub_role` = `"commercial"` or
`"dpr"` respectively.

**Important — do not attempt to auto-fetch linked documents.** If a vendor's commercial file
contains a hyperlink/reference to another document (e.g., "see attached DPR"), the system must
NOT try to follow that link at runtime. The user is expected to have manually uploaded the actual
linked file as the "Vendor DPR" upload. If you detect the ingestion pipeline currently tries to
fetch URLs from within uploaded documents, remove that behavior — this system is air-gapped and
must never make outbound network calls during processing.

Total files per compliance run = **4** (SOTR Commercial, SOTR Technical, Vendor Commercial, Vendor
DPR). Do not design this as "2 files" or "N files" generically — the UI and backend contract should
be explicit about these four named slots, not a generic multi-file uploader. This matters for
correctness because the clause parser and evaluator need to know which file plays which role;
guessing roles from content is not acceptable.

---

## 4. House Rules / Standards Check

Before or alongside clause evaluation, the engine must check the SOTR + vendor submission against
a **House Rules / Standards repository** already indexed in the knowledge base (this is the
existing rules/standards corpus already ingested into AGRA — do not re-ingest it per compliance
run; query the existing index).

Requirements:

- Let the user pick, from a checklist populated from the existing knowledge base's `doc_type =
  "standard"` documents, which standards/house rules apply to this run (e.g., internal
  procurement rules, EMD policy, MSE/MII purchase preference rules, or whatever rule sets exist in
  the deployed instance). Do not hardcode a fixed list of standard names in code — read available
  standards dynamically from the metadata store.
- For every extracted SOTR clause, the RAG lookup step must retrieve relevant passages from **both**
  the selected house rules/standards AND the SOTR documents themselves, since a SOTR clause may
  reference or partially restate a house rule that then needs to be checked separately for internal
  consistency (e.g., SOTR says "EMD exemption per policy" — the engine should verify the actual
  house rule for EMD exemption and check if the vendor's supporting documents satisfy it).
- A clause can fail specifically on "house rule non-compliance" even if the SOTR wording itself is
  satisfied — surface this as a distinct annotation on the clause evaluation (see §6), not folded
  silently into the general finding text.

---

## 5. Processing Pipeline (what happens on "Start Compliance")

Implement as an explicit, observable pipeline (each stage should emit a status update the UI can
poll/stream, e.g. `"Parsing SOTR clauses (3/40)..."`):

1. **Ingest** all 4 files if not already ingested (reuse existing ingestion pipeline: format
   detection → chunking → embedding → indexing). Tag each chunk with `bundle_role`, `sub_role`,
   `doc_id`.
2. **Clause extraction** — run the clause parser over the **combined SOTR bundle** (both SOTR
   Commercial and SOTR Technical files together, not just one of them). Every extracted clause
   object must include:
   - `clause_id` (e.g., `SOTR-C-12` for a commercial-file clause, `SOTR-T-5` for a technical-file
     clause — prefix must indicate source file)
   - `source_doc_id` / `source_file` (which of the two SOTR files it came from)
   - `requirement_text`
   - `applicable_standards` (if the clause references a specific standard/policy)
   - `technical_parameters` (if quantitative)
   - `acceptance_criterion`
3. **House rules lookup** — for each clause, retrieve relevant passages from the selected house
   rules/standards per §4.
4. **Vendor evidence retrieval** — for each clause, retrieve the most relevant passages from the
   **combined vendor bundle** (both Vendor Commercial and Vendor DPR files) that address that
   clause. Do not restrict retrieval to only the "matching" vendor file by sub_role — a commercial
   SOTR clause (e.g., a technical certification requirement) may be answered in the DPR, and vice
   versa. Search across both.
5. **Clause evaluation (LLM)** — for each clause, submit a structured prompt containing: the clause
   requirement, the retrieved house-rule/standard passages, and the retrieved vendor evidence
   passages. Return a structured verdict object (schema in §6).
6. **Missing clause detection** — flag SOTR clauses for which no relevant vendor evidence was
   retrieved above a confidence threshold (configurable, default matches existing RAG confidence
   threshold in the codebase — reuse it, don't invent a new constant).
7. **Contradiction detection** — flag cases where the vendor bundle contains internally
   inconsistent statements relevant to the same clause (e.g., Vendor Commercial claims one
   certification status, Vendor DPR states something different).
8. **Historical feedback** — query prior compliance runs / prior SOTR versions in the lineage store
   for the same clause area or vendor, and attach historical notes where relevant (reuse existing
   Historical Feedback Module — do not reimplement).
9. **Aggregation** — compute:
   - Total clauses evaluated, broken down by verdict
   - Compliance score (% COMPLIANT of total evaluable clauses — exclude UNVERIFIABLE from the
     denominator, or state clearly in the report if included; be consistent and document the
     choice)
   - Prioritized list of Critical/Major non-compliances
   - List of missing clauses
   - List of detected contradictions
   - Overall recommendation: `APPROVE` / `APPROVE WITH CONDITIONS` / `REVISE AND RESUBMIT` / `REJECT`
10. **Report generation** — produce the `.docx` report (see §7).

---

## 6. Clause Evaluation Data Model (strict)

```json
{
  "clause_id": "SOTR-T-14",
  "source_file": "SOTR Technical",
  "requirement_text": "string",
  "verdict": "COMPLIANT | PARTIAL | NON_COMPLIANT | UNVERIFIABLE",
  "finding": "string — precise technical statement explaining the basis of the verdict",
  "house_rule_flag": {
    "violated": true,
    "rule_reference": "string, e.g. house rule / policy doc name + clause",
    "note": "string"
  },
  "recommendation": "string — required for PARTIAL and NON_COMPLIANT, null otherwise",
  "severity": "Critical | Major | Minor | null (null only if verdict is COMPLIANT)",
  "citations": [
    { "doc_name": "string", "version": "string", "page": 0, "excerpt": "string" }
  ]
}
```

Do not use any verdict values other than the four listed. Do not collapse `house_rule_flag` into
`finding` text — keep it as a separate structured field so the report can render a distinct "House
Rule Deviations" section.

---

## 7. Report Output

- Format: `.docx`, generated via the existing python-docx report module — reuse the existing
  template/sections (cover page, executive summary, clause-by-clause table, historical feedback,
  non-compliance register, standards reference appendix). Add a **new section**: "House Rule
  Deviations" listing every clause where `house_rule_flag.violated == true`.
- Cover page title and filename must use the **Reference Name** entered in Stage 1, not the SOTR
  file name or a generic default.
- If a PDF export is also required, confirm with me before implementing — the current design only
  specifies `.docx`. Do not silently add a PDF path without discussing conversion fidelity
  (tables/formatting) first.

---

## 8. API Contract (adjust to match existing backend conventions in this repo)

```
POST /api/compliance/runs
  form-data:
    reference_name: string
    sotr_commercial: file
    sotr_technical: file
    vendor_commercial: file
    vendor_dpr: file
    selected_standards: string[]   # ids of house rules/standards to check against
  -> { run_id: string, status: "queued" }

GET /api/compliance/runs/{run_id}/status
  -> { status: "ingesting|parsing_clauses|evaluating|aggregating|generating_report|complete|failed",
       progress: { current: int, total: int, message: string } }

GET /api/compliance/runs/{run_id}/report
  -> streams the .docx file, filename = "<sanitized_reference_name>_Compliance_Report.docx"

GET /api/compliance/runs/{run_id}/result
  -> full structured JSON result (clauses, aggregation, recommendation) for in-app review before download
```

---

## 9. Acceptance Criteria (write tests for these)

1. "Start Compliance" is disabled until reference name + all 4 files are present; enabling/disabling
   is reactive, not requiring a page reload.
2. Clause extraction pulls clauses from **both** SOTR files, and each clause's `clause_id` /
   `source_file` correctly identifies its origin file.
3. Vendor evidence retrieval searches **both** vendor files for every clause, not just the
   file with matching sub_role.
4. A clause with a house-rule violation shows up in the "House Rule Deviations" section even if its
   overall verdict is COMPLIANT against the raw SOTR wording.
5. No verdict other than `COMPLIANT`, `PARTIAL`, `NON_COMPLIANT`, `UNVERIFIABLE` appears anywhere
   in output.
6. The generated report's title and filename equal the user-entered Reference Name, sanitized for
   filesystem safety.
7. No network call is made to fetch any URL/link found inside an uploaded document, at any stage of
   the pipeline.
8. Re-running compliance on the same 4 files with a different Reference Name produces a new report
   with a new title/filename but identical clause verdicts (i.e., Reference Name only affects
   presentation/identity, never evaluation logic).

---

## 10. What to report back to me

After implementing, give me:
- The diff summary of what was wrong before vs. now
- Any place where the existing codebase's conventions forced a deviation from this spec, and why
- A list of any of the 8 acceptance criteria above you were not able to fully verify with automated
  tests, and why
