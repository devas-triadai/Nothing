# TRIAD-AI — Detailed Project Report

**Presented to the Indian Coast Guard (ICG)**  
Headquarters, New Delhi — Ministry of Defence

## AI Based Document Assessment Software — Proposed Methodology

# Air-Gapped Retrieval Agent (AGRA)

Secure On-Premise RAG System for ICG Knowledge Operations

---

## Document Information

- **Submitted to:** Indian Coast Guard Headquarters, New Delhi
- **Classification:** RESTRICTED
- **System Name:** Air-Gapped Retrieval Agent (AGRA)
- **Core Technology:** On-Premise RAG + LLM (Llama-3.1 70B)
- **Deployment:** Air-Gapped, Docker, Ubuntu 22.04 LTS
- **LLM Inference:** Ollama + llama.cpp, fully offline
- **Vector DB:** FAISS with HNSW index
- **Compliance Engine:** Clause-by-clause SOTR evaluation + historical feedback
- **Project Duration:** 6 months from contract signing
- **Warranty:** 3 years from final acceptance

**Submitted by**  
Dr. T. Rajyalakshmi  
Ph.D. in Artificial Intelligence (LLMs)  
Email: rajisurendra@triad-ai.com

---

## Contents

1. Executive Summary  
2. Problem Statement and Operational Need  
3. System Architecture Overview  
4. Module 1 — Document Ingestion and Knowledge Base Construction  
5. Module 2 — Hybrid RAG Query Pipeline  
6. Module 3 — SOTR Compliance Verification Engine  
7. Module 4 — Multimodal Processing and Engineering Drawing Analysis  
8. Module 5 — Automated Content Generation  
9. Module 6 — Security Architecture  
10. Module 7 — Document Genealogy and Lineage Visualization  
11. Evaluation Methodology and Performance Metrics  
12. Implementation Plan  
13. Hardware and Infrastructure  
14. Deliverables  
15. Conclusion  

---

## 1. Executive Summary

This report describes the proposed end-to-end methodology for the Air-Gapped Retrieval Agent (AGRA), a fully on-premise, air-gapped Artificial Intelligence system designed for the Indian Coast Guard Headquarters. AGRA addresses the requirement for secure, intelligent document knowledge management through a Retrieval-Augmented Generation (RAG) architecture that operates entirely within ICG’s protected infrastructure, with zero external network dependency at any point during operation.

The proposed system is structured around four functional pillars:

1. **Intelligent Document Retrieval:** Natural language querying across the entire ICG document corpus — SOPs, technical manuals, SOTRs, inspection reports, engineering drawings — with every response grounded in and traceable to cited source documents.
2. **Automated SOTR Compliance Verification:** Clause-by-clause evaluation of bid submissions, procurement specifications, and technical documents against applicable standards (IMO, IRS, NES, NCD), generating structured compliance reports with historical feedback that tracks how specifications have evolved across past SOTRs.
3. **Automated Content Generation:** ICG-formatted PowerPoint briefings, executive summaries, and knowledge assessment quizzes, generated from document inputs through a governed AI pipeline.
4. **Document Genealogy and Lineage Visualization:** An interactive Directed Acyclic Graph (DAG) that maps the full version history and inter-document relationships of every SOP, directive, SOTR, inspection report, and incident report in the knowledge base, fulfilling SOTR Objective 5.

**Core Design Principle:** All model weights, databases, and inference pipelines reside entirely on ICG-owned hardware. No data — query, document, or response — ever leaves the ICG network. AGRA operates in a fully air-gapped environment, consistent with defence-grade data sovereignty requirements.

## 2. Problem Statement and Operational Need

### 2.1 Current Operational Challenges

The ICG Headquarters manages an extensive corpus of structured and unstructured documents: Standard Operating Procedures (SOPs), technical manuals, logistics data, intelligence briefs, SOTR documents, engineering drawings, and imagery. The current manual process of retrieving, cross-referencing, and summarising information from these sources imposes significant operational costs:

- Information retrieval from large document sets requires hours of manual search, reducing decision-making speed during time-sensitive operations.
- Generation of operational briefings and presentations demands 3–6 hours of staff effort per briefing, diverting personnel from higher-value tasks.
- Evaluation of bid submissions and technical documents against SOTRs is performed manually, with limited manpower reviewing hundreds of pages across multiple standards, making oversight errors likely.
- Historical institutional knowledge (past SOTR versions, previous evaluation findings, superseded specifications) is fragmented across repositories and rarely consulted during new procurement cycles.
- Engineering drawings and multimodal technical content cannot be processed by conventional keyword search systems.

### 2.2 Proposed Resolution

AGRA addresses each of these challenges through targeted AI-driven capabilities deployed in a defence-compliant, air-gapped architecture. The system transforms the ICG document corpus into a queryable, semantically searchable knowledge base, enabling personnel to obtain cited answers in seconds, generate structured reports in minutes, and conduct rigorous SOTR compliance checks automatically.

## 3. System Architecture Overview

### 3.1 High-Level Architecture

AGRA is designed as a two-server, fully containerised system. The Primary AI Server handles all computationally intensive tasks: LLM inference, embedding generation, vector search, OCR, and compliance analysis. The Secondary Application Server hosts the web-based user interface, REST API gateway, and session management. Both servers communicate exclusively over a dedicated 10 Gbps internal Ethernet link with no external network connectivity.

### 3.2 Software Stack

All components are open-source, fully locally deployable, and require no external API calls or cloud services.

| Layer | Technology | Role |
|---|---|---|
| LLM Inference | Ollama + llama.cpp | Serves Llama-3.1 70B (4-bit GGUF) locally on dual RTX 6000 Ada |
| Embedding Model | BGE-Large-EN (BAAI) | Generates 1024-dimensional semantic vectors for all document chunks |
| Vector Database | FAISS (HNSW index) | Sub-50 ms similarity search across millions of document chunks |
| Hybrid Retrieval | LangChain EnsembleRetriever | Combines FAISS semantic search with BM25 keyword search |
| Re-ranking | ms-marco-MiniLM cross-encoder | Re-scores top-k retrieved chunks for precision before LLM prompt |
| OCR Engine | Tesseract 5 + TrOCR | Rule-based + deep-learning OCR for digital and scanned documents |
| Vision AI | LLaVA (local) | Multimodal reasoning on images, diagrams, and engineering drawings |
| Document Parsing | pdfplumber, python-docx | Structured extraction from PDF and DOCX with table and layout preservation |
| Image Preprocessing | OpenCV | Deskew, denoise, binarize, and enhance scanned document quality |
| Backend API | FastAPI (Python) | Async RESTful API; handles 50+ concurrent sessions |
| Frontend UI | React + TailwindCSS | Secure web interface; runs on Secondary Server |
| Metadata Store | PostgreSQL | Stores document metadata, version history, lineage relationships |
| Containerisation | Docker Compose | Isolated, reproducible deployment of all services |
| Slide Generation | python-pptx | Maps AI content to ICG master .pptx template placeholders |
| Report Generation | python-docx | Generates evaluation and compliance reports in ICG .docx format |

## 4. Module 1 — Document Ingestion and Knowledge Base Construction

### 4.1 Overview

The document ingestion pipeline is the foundation of AGRA. Every document uploaded to the system passes through a multi-stage processing pipeline that converts raw files into semantically searchable vector representations while preserving full metadata, version history, and document lineage for traceability.

### 4.2 Ingestion Pipeline — Step by Step

#### 4.2.1 Stage 1 — Format Detection and Routing

The ingestion service accepts PDF (digital and scanned), DOCX, TXT, JPEG, PNG, and JPG files. The format detector routes each file to the appropriate processing path:

- **Digital PDF:** pdfplumber extracts text with table and layout structure preserved.
- **Scanned PDF / Image:** OpenCV preprocessing pipeline (deskew, denoise, binarise) followed by Tesseract 5 (rule-based OCR) or TrOCR (deep-learning OCR for complex layouts, handwriting, stamps).
- **DOCX:** python-docx extracts paragraphs, headings, and table content with heading hierarchy preserved.
- **Engineering Drawings (images):** LLaVA vision model extracts annotations, dimensions, and technical parameters; combined with OCR for text overlays.

#### 4.2.2 Stage 2 — Semantic Chunking

Raw extracted text is split into overlapping semantic chunks using a recursive character text splitter with a target chunk size of 512 tokens and 64-token overlap. Paragraph boundaries, section headings, and table boundaries are respected to avoid splitting mid-context. Each chunk is tagged with:

- Document name, version, and timestamp
- Page number and section heading path
- Chunk index within document
- Document type (SOP, SOTR, inspection report, drawing, etc.)

#### 4.2.3 Stage 3 — Embedding Generation

Each chunk is passed through the BGE-Large-EN embedding model (BAAI), which produces a 1024-dimensional dense vector representation. BGE-Large-EN is specifically trained on a broad corpus including technical and scientific text, making it effective for maritime and defence terminology. All embedding inference runs locally on the Primary Server GPU.

#### 4.2.4 Stage 4 — FAISS Indexing

Generated embeddings are inserted into a FAISS index using the HNSW (Hierarchical Navigable Small World) algorithm, which provides sub-50 ms approximate nearest-neighbour search across millions of vectors. The index is persisted to NVMe SSD. Incremental indexing is supported; new documents are added to the existing index without rebuilding from scratch.

#### 4.2.5 Stage 5 — Metadata and Version Storage

Full document metadata is written to PostgreSQL:

- Document ID, name, type, author, creation and ingestion timestamps
- Version number and hash (SHA-256 of file content for tamper detection)
- Parent document reference (for lineage tracking)
- Classification level

### 4.3 Document Version Control and Lineage

When a new version of an existing document is ingested, AGRA:

1. Assigns a new version number and retains all previous versions in the PostgreSQL store.
2. Re-indexes only the changed portions into FAISS (delta indexing).
3. Records the parent-child relationship in the lineage graph.
4. Tags all existing FAISS chunks with their version identifier so queries can be version-scoped.

The lineage graph is visualised in the UI as an interactive directed acyclic graph (DAG), showing how a current SOP evolved from its predecessors, which inspection reports derived from a given technical manual, or how a SOTR has been revised across procurement cycles.

## 5. Module 2 — Hybrid RAG Query Pipeline

### 5.1 Overview

When an ICG officer submits a natural language query, AGRA executes a multi-stage Retrieval-Augmented Generation pipeline that retrieves the most relevant document chunks, re-ranks them for precision, and generates a cited response using the locally deployed LLM.

### 5.2 Query Processing Pipeline

#### 5.2.1 Step 1 — Query Embedding

The user’s query is encoded using the same BGE-Large-EN model used during ingestion, producing a 1024-dimensional query vector. This ensures semantic consistency between the query and document embedding spaces.

#### 5.2.2 Step 2 — Hybrid Retrieval

AGRA employs a two-channel hybrid retrieval strategy using LangChain’s EnsembleRetriever:

- **Semantic channel:** FAISS HNSW index performs approximate nearest-neighbour search, returning the top-50 most semantically similar chunks. This channel excels at paraphrase and concept matching.
- **Keyword channel (BM25):** BM25Retriever performs classical inverted-index keyword search, returning top-50 matches. This channel captures exact clause numbers, part numbers, regulation codes, and acronyms.

The two result sets are merged using a Reciprocal Rank Fusion (RRF) algorithm, which combines rankings from both channels into a single ranked list of top-100 candidate chunks without requiring score normalisation.

#### 5.2.3 Step 3 — Cross-Encoder Re-ranking

The top-100 candidates from hybrid retrieval are passed through a cross-encoder re-ranking model (ms-marco-MiniLM-L-6-v2), which jointly encodes the query and each candidate chunk to produce a relevance score. The top-8 highest-scored chunks are selected for the LLM context window.

#### 5.2.4 Step 4 — Context Assembly and Prompt Construction

The 8 selected chunks, along with their metadata (document name, version, page number, section), are assembled into a structured prompt. The prompt includes:

- A system instruction enforcing ICG governance rules: respond only in English, cite all sources, refuse if information is not present in the context, avoid speculation.
- The retrieved context with source attribution tags for each chunk.
- Any conversation history from the current session.
- The user’s query.

#### 5.2.5 Step 5 — LLM Generation (Llama-3.1 70B)

The assembled prompt is submitted to Llama-3.1 70B Instruct, deployed via Ollama with 4-bit GGUF quantisation using llama.cpp. The model runs across two NVIDIA RTX 6000 Ada GPUs (96 GB total VRAM), providing:

- 128,000-token context window (4× the SOTR minimum of 32K)
- Average Time-to-First-Token (TTFT) less than or equal to 3 seconds for standard queries
- Complete response generation in less than or equal to 30 seconds for a 500-token answer

#### 5.2.6 Step 6 — Cited Response Delivery

The LLM response is post-processed to extract inline citation markers and pair them with the corresponding source metadata. The final response delivered to the user includes:

- The natural language answer with inline citation numbers
- A structured citation list: document name, version, page number, and the exact extracted excerpt
- A confidence indicator based on the re-ranker’s top score

### 5.3 Hallucination Mitigation

AGRA employs three complementary hallucination mitigation strategies:

1. **Context-grounded prompting:** The LLM is explicitly instructed to answer only from the provided context and respond with “Insufficient information in the knowledge base” if the query cannot be answered from retrieved chunks.
2. **Citation enforcement:** Every factual claim must reference a specific document and page. Post-processing validates that all cited sources exist in the metadata store.
3. **Confidence thresholding:** If the cross-encoder’s top re-ranking score falls below a configurable threshold (default: 0.4), the system flags the response as low-confidence and alerts the user.

## 6. Module 3 — SOTR Compliance Verification Engine

### 6.1 Overview

The SOTR Compliance Verification Engine is AGRA’s most operationally significant capability for the Materiel Directorate. It automates the process of evaluating bid submissions, procurement specifications, engineering drawings, and inspection reports against SOTR requirements and applicable standards including IMO SOLAS/MARPOL/LSA, IRS, Lloyd’s, BV, DNV, NES, and NCD.

The engine provides two outputs:

1. A clause-by-clause compliance evaluation table with verdict, citations, and recommendations for each SOTR clause.
2. A historical feedback narrative comparing the current submission against past SOTRs and past evaluation findings from the ICG knowledge base.

### 6.2 Compliance Engine Workflow

1. Upload SOTR + bid document
2. SOTR clause parser
3. RAG standards lookup
4. LLM clause evaluator
5. Historical feedback module
6. Report aggregator
7. ICG `.docx` evaluation report

### 6.3 Step-by-Step Technical Procedure

#### 6.3.1 Step 1 — Document Upload and Parsing

The officer uploads two documents via the AGRA web interface:

- The SOTR (reference requirements document)
- The submission document (bid, technical specification, inspection report, or drawing set)

The officer selects which standards to cross-check against from a configurable checklist. Both documents pass through the ingestion pipeline described earlier.

#### 6.3.2 Step 2 — SOTR Clause Extraction and Structuring

The Clause Parser uses the LLM with a specialised parsing prompt to extract each individual requirement from the SOTR as a structured clause object.

| Field | Description |
|---|---|
| `clause_id` | Unique identifier (e.g., SOTR-5.3.2) |
| `requirement_text` | Full text of the requirement |
| `applicable_standards` | Referenced standards (e.g., IMO SOLAS Ch. II-2) |
| `technical_parameters` | Quantitative thresholds (dimensions, ratings, grades) |
| `acceptance_criterion` | What constitutes compliance |

#### 6.3.3 Step 3 — Standards Lookup via RAG

For each clause, the hybrid RAG pipeline retrieves the most relevant passages from the ICG knowledge base, including the full text of IMO SOLAS, MARPOL, LSA, IRS Rules, BV and DNV classification society rules, NES, and NCD documents.

#### 6.3.4 Step 4 — LLM Clause-by-Clause Evaluation

Each clause is evaluated individually by submitting a structured evaluation prompt to the LLM containing:

- The SOTR clause requirement
- The corresponding text from the submission document
- The relevant standard passages

The LLM returns a structured evaluation for each clause with four possible verdicts:

| Verdict | Meaning |
|---|---|
| COMPLIANT | The submission fully satisfies the SOTR clause requirement and applicable standard |
| PARTIAL | The submission addresses the clause but with gaps or ambiguities |
| NON-COMPLIANT | The submission contradicts or fails to meet the SOTR clause requirement |
| UNVERIFIABLE | Insufficient information in the submission to make a determination |

Each evaluation entry contains:

- Verdict
- Finding: precise technical statement explaining the basis of the verdict
- Recommendation: specific corrective action required for NON-COMPLIANT and PARTIAL verdicts
- Severity: Critical / Major / Minor for non-compliances
- Citations: source document name, version, page, and excerpt for each claim

The engine additionally performs:

- Missing clause detection
- Contradiction detection across the submission document

#### 6.3.5 Step 5 — Historical Feedback Module

For each clause evaluation, the Historical Feedback Module queries the PostgreSQL lineage store and FAISS index for:

1. Past SOTR versions for the same ship class or procurement category
2. Past evaluation reports for the same vendor or document type
3. Standard version changes, including superseded editions

**Example narrative:**

> Historical Feedback — Clause SOTR-7.4.1 (Fire Detection System): In SOTR-2019 (OPV-7 procurement), this clause specified Type B addressable fire detectors. Following an operational incident review, SOTR-2022 (OPV-9 procurement) upgraded the requirement to Type A detectors per IMO SOLAS 2020 amendments. The current submission specifies Type B detectors — this represents a regression to a superseded specification. The same deviation was flagged as NON-COMPLIANT in the 2022 OPV-9 bid evaluation report. Immediate revision to Type A is required.

#### 6.3.6 Step 6 — Report Aggregation

All clause evaluations and historical feedback entries are aggregated into a complete evaluation dataset:

- Total clauses evaluated, broken down by verdict type
- Compliance score: percentage of COMPLIANT clauses out of total evaluable clauses
- Prioritised list of critical and major non-compliances
- List of missing clauses
- List of detected contradictions
- Overall recommendation: APPROVE / APPROVE WITH CONDITIONS / REVISE AND RESUBMIT / REJECT

#### 6.3.7 Step 7 — ICG-Format Evaluation Report Generation

The aggregated data is passed to the python-docx report generation module, which populates an ICG-approved evaluation report template producing a `.docx` file containing:

- Cover page
- Executive summary
- Clause-by-clause evaluation table
- Historical feedback section
- Non-compliance register
- Standards reference appendix

## 7. Module 4 — Multimodal Processing and Engineering Drawing Analysis

### 7.1 Vision AI Pipeline

Engineering drawings and image-based documents are processed through AGRA’s multimodal pipeline:

1. **High-resolution ingestion:** Drawings are ingested at full resolution. OpenCV preprocessing corrects skew, removes noise, and enhances contrast.
2. **OCR text extraction:** Tesseract 5 extracts text annotations, title block content, revision notes, and label text. TrOCR handles handwritten annotations and stamps.
3. **Vision AI parameter extraction:** LLaVA processes each drawing to extract dimensions, tolerances, material grades, equipment ratings, pipe schedules, cable specifications, and compliance notes.
4. **SOTR parameter comparison:** Extracted parameters are compared against the corresponding Build Specification and SOTR requirements using the compliance engine.
5. **Cross-modal retrieval:** Officers can query the system with an image and receive relevant text passages from manuals or SOPs, and vice versa, through CLIP-based cross-modal embeddings.

## 8. Module 5 — Automated Content Generation

### 8.1 PowerPoint Briefing Generation

Officers specify a topic or select a document set. AGRA:

1. Retrieves relevant passages from the knowledge base via the RAG pipeline.
2. Instructs the LLM to generate structured slide content: title, key points, and speaker notes, conforming to ICG’s approved 10-slide briefing format.
3. Uses `python-pptx` to map generated content into the ICG master `.pptx` template.
4. Produces a 10-slide briefing in under 15 minutes from query submission.

### 8.2 Executive Summary Generation

Multi-document executive summaries are generated by:

- Retrieving key passages from each selected document
- Applying a hierarchical summarisation prompt
- Citing all summary claims to source documents

### 8.3 Knowledge Quiz Generation

Training quizzes are generated from ingested SOPs and manuals:

- Multiple-choice questions (4 options, 1 correct answer) and short-answer questions
- Each question includes the source document reference for officer review
- Configurable number of questions, difficulty level, and topic scope

## 9. Module 6 — Security Architecture

### 9.1 Air-Gapped Deployment

AGRA is installed entirely from encrypted physical media (USB drives or encrypted hard drives). The installation package includes all Docker images, model weights, Python dependencies, and configuration files. No installation step requires internet connectivity. After initial setup, all outbound Docker network traffic is blocked at the OS level using `iptables` rules.

### 9.2 Encryption

- **Data at rest:** FAISS index, PostgreSQL database, and all stored documents are encrypted using AES-256-GCM. Encryption keys are stored in an ICG-controlled hardware key store.
- **Data in transit:** All communication between the Secondary Server and Primary Server uses TLS 1.3 with mutual certificate authentication over the internal 10 Gbps link.

### 9.3 Access Control

- Role-based access control (RBAC) with three default roles: End User, Analyst, Administrator
- JWT-based session authentication with configurable token expiry
- Administrators can create specialised Role-Based Agents with access restricted to specific document subsets

### 9.4 Audit Logging

An immutable, append-only audit log records all user queries, generated responses, document uploads, administrative configuration changes, and login/logout events. Logs are retained for a minimum of 24 months and stored in a tamper-evident format with SHA-256 hash chaining.

### 9.5 Media Controls

Physical USB ports on both servers are disabled at the OS level post-installation. New document ingestion is performed through the AGRA web interface by authorised personnel only. New model or software updates are introduced exclusively through a controlled update procedure requiring ICG administrator approval.

## 10. Module 7 — Document Genealogy and Lineage Visualization

### 10.1 Overview and Objective

In response to SOTR Objective 5, AGRA incorporates a dedicated Document Genealogy and Lineage Visualization module that maintains and presents the full version lineage and inter-document relationships for all key documents managed within the ICG knowledge base.

The objective of this module is to ensure that every user accessing a current document can trace how that document came to be in its current form: which earlier versions preceded it, what changes were made at each revision, which related documents informed it or were derived from it, and how entity-level relationships evolved over time.

### 10.2 Genealogy Data Model

AGRA models document genealogy as a Directed Acyclic Graph (DAG) stored in PostgreSQL. Each node in the graph represents a specific version of a document; each directed edge represents a relationship between documents.

#### 10.2.1 Node Attributes

| Attribute | Description |
|---|---|
| `doc_id` | Unique document identifier (UUID) |
| `doc_name` | Human-readable document title |
| `doc_type` | Category: SOP, SOTR, directive, inspection report, incident report, manual, drawing |
| `version` | Version number (e.g., v1.0, v2.3) |
| `sha256_hash` | SHA-256 hash of file content for tamper detection and deduplication |
| `ingestion_timestamp` | Date and time of ingestion into AGRA |
| `effective_date` | Date from which the document version was operationally effective |
| `superseded_date` | Date the version was superseded (null if current) |
| `author / authority` | Originating officer, unit, or authority |
| `classification` | Security classification level |
| `change_summary` | LLM-generated summary of key changes from the immediately preceding version |

#### 10.2.2 Edge (Relationship) Types

| Relationship Type | Meaning |
|---|---|
| `SUPERSEDES` | The source document version replaces the target version |
| `DERIVED_FROM` | The source document was substantially derived from or based on the target document |
| `INFORMED_BY` | The source document revision was triggered or influenced by the target document |
| `REFERENCES` | The source document cites or normatively references the target document |
| `AMENDS` | The source document is a formal amendment to the target document |
| `SUPERSEDED_BY` | Inverse of `SUPERSEDES`; automatically maintained for graph consistency |

### 10.3 Automated Genealogy Construction

Genealogy relationships are established through three complementary mechanisms:

#### 10.3.1 Mechanism 1 — Structured Metadata Extraction at Ingestion

During document ingestion, the LLM is prompted with a specialised metadata extraction prompt to identify:

- Explicit version references
- Explicit cross-references to other documents
- Amendment clauses

These structured references are parsed and translated into typed edges in the genealogy graph.

#### 10.3.2 Mechanism 2 — Semantic Similarity Lineage Detection

When a new document is ingested, AGRA computes its embedding and compares it against embeddings of all existing documents of the same `doc_type`. Documents with cosine similarity above a configurable threshold (default: 0.85) are flagged as potential lineage candidates.

#### 10.3.3 Mechanism 3 — Officer-Confirmed Manual Linkage

Officers with Analyst or Administrator role can manually declare relationships between documents through the AGRA web UI. All manually declared edges are flagged with a `manually_confirmed` attribute and the declaring officer’s identity for auditability.

### 10.4 Lineage Visualization Interface

The genealogy graph is accessible through a dedicated Lineage Explorer panel in the AGRA web interface. The visualization is rendered as an interactive DAG using a force-directed graph layout with the following capabilities:

1. Document-centred view
2. Edge-type filtering
3. Timeline mode
4. Node detail panel
5. Diff view for two versions of the same document
6. Entity lineage search

### 10.5 Integration with Other AGRA Modules

The Genealogy Module is integrated with the rest of AGRA as follows:

- **RAG Query Pipeline:** Includes a lineage note if the source document has been superseded or if a newer version exists.
- **SOTR Compliance Engine:** Historical feedback draws directly on the genealogy graph.
- **Content Generation:** Can optionally include provenance and revision history.
- **Audit Log:** All genealogy graph modifications are recorded in the immutable audit log.

### 10.6 Data Persistence and Export

The complete genealogy graph is stored in PostgreSQL using a standard adjacency-list schema with two tables: `doc_nodes` and `doc_edges`. The graph is additionally exported on demand as:

- A JSON-LD graph document
- A `.graphml` file
- A tabular lineage report (`.docx`)

## 11. Evaluation Methodology and Performance Metrics

### 11.1 Overview

System performance is evaluated across five dimensions: retrieval quality, response generation quality, latency and throughput, output generation, and system reliability. Actual performance values will be established through evaluation on ICG-representative test data during the User Acceptance Testing (UAT) phase.

### 11.2 Retrieval Quality Metrics

Retrieval quality measures how effectively AGRA surfaces the most relevant document chunks in response to a natural language query. Evaluation is performed on a curated test set of 100 representative queries.

#### 11.2.1 Precision@k

Definition: The proportion of retrieved documents in the top-k results that are genuinely relevant to the query.

#### 11.2.2 Recall@k

Definition: The proportion of all relevant documents in the corpus that appear in the top-k results.

#### 11.2.3 NDCG@10 (Normalized Discounted Cumulative Gain)

Definition: NDCG measures ranking quality by rewarding systems that place more relevant documents higher in the result list.

#### 11.2.4 Mean Reciprocal Rank (MRR)

Definition: MRR measures how highly the first relevant result is ranked, averaged across all queries.

### 11.3 Response Generation Quality Metrics

#### 11.3.1 Hallucination Rate

Definition: The percentage of factual claims in generated responses that are not supported by the retrieved source documents or are factually incorrect.

#### 11.3.2 BERTScore (F1)

Definition: BERTScore evaluates the semantic similarity between a generated response and a human-written reference answer using contextual embeddings from a pre-trained BERT model.

#### 11.3.3 Citation Accuracy

Definition: The proportion of inline citations in generated responses that correctly point to a source document, page, and excerpt that genuinely supports the cited claim.

### 11.4 Latency and Throughput Metrics

#### 11.4.1 Time-to-First-Token (TTFT)

Definition: The elapsed time from query submission to receipt of the first token in the LLM’s streamed response.

#### 11.4.2 End-to-End Query Latency

Definition: The total elapsed time from query submission to complete response delivery.

#### 11.4.3 FAISS Retrieval Latency

Definition: The time taken by the FAISS HNSW index to return approximate nearest-neighbour results for a 1024-dimensional query vector.

#### 11.4.4 Concurrent User Throughput

Definition: The number of simultaneous user sessions the system can serve while maintaining latency within acceptable operational bounds.

### 11.5 Output Generation Metrics

#### 11.5.1 Compliance Report Generation Time

Definition: The elapsed time from document upload (SOTR + submission document) to delivery of the completed `.docx` evaluation report.

#### 11.5.2 PowerPoint Briefing Generation Time

Definition: The elapsed time from topic or document selection to delivery of a completed 10-slide `.pptx` briefing file.

#### 11.5.3 OCR Character Error Rate (CER)

Definition: The proportion of characters incorrectly recognised by the OCR pipeline relative to the ground-truth text.

### 11.6 System Reliability Metrics

#### 11.6.1 System Uptime

Definition: The proportion of total scheduled operational time during which all AGRA services are available and responsive.

#### 11.6.2 Genealogy Graph Construction Time

Definition: The elapsed time from completion of document ingestion to the appearance of automatically detected lineage edges in the Lineage Explorer UI.

### 11.7 Evaluation Test Set Construction

The 100-query evaluation test set is constructed as follows:

- 30 queries targeting SOP and procedural content
- 25 queries targeting SOTR and compliance content
- 20 queries targeting technical manual and engineering content
- 15 queries targeting multi-document synthesis
- 10 adversarial queries designed to test hallucination resistance

Ground-truth relevance judgements are provided by ICG subject-matter experts independently of the system development team. Evaluators use a three-point relevance scale: 0 (not relevant), 1 (partially relevant), 2 (highly relevant).

## 12. Implementation Plan

### 12.1 Project Duration

The total project duration is six (6) months from the date of contract signing, as specified in SOTR Section 11.1.

### 12.2 Phase-wise Implementation

| Phase | Workstream | Duration | Key Activities | Deliverable |
|---|---|---|---|---|
| Phase 1 | Data Cleaning and Preparation | Weeks 1–4 | ICG document format analysis, metadata schema design, OCR pipeline setup, ingestion testing on sample corpus | Data Ingestion Schema Report; Validated OCR Module |
| Phase 2 | Model Training and Fine-Tuning | Weeks 5–10 | LLM fine-tuning (LoRA/PEFT on Llama-3.1 70B), quantisation benchmarking on target GPU hardware | Fine-tuned Model Weights; Benchmark Report |
| Phase 3 | Backend and RAG Development | Weeks 11–16 | FAISS vector DB construction, BM25 index, hybrid retrieval implementation, re-ranking integration, compliance engine development, historical feedback module | RAG Prototype; Compliance Engine (internal release) |
| Phase 4 | OCR and Multimodal Optimisation | Weeks 17–19 | LLaVA integration, engineering drawing parameter extraction, CLIP cross-modal retrieval | Optimised Multimodal Module |
| Phase 5 | Frontend, Content Generation | Weeks 20–22 | React UI development, FastAPI integration, python-pptx template mapping, quiz generation module, report generation module | Beta Software Version |
| Phase 6 | Testing, Deployment, Training | Weeks 23–25 | Air-gapped installation on ICG servers, UAT with ICG officers, performance benchmarking, training, documentation delivery | Final Accepted System; Training Completed |

### 12.3 Testing and Quality Assurance

TRIAD-AI will conduct the following test regimes before handover:

- Unit testing
- Integration testing
- Performance testing at 50 concurrent sessions
- Security testing
- User Acceptance Testing (UAT)
- Air-gap compliance verification during a 72-hour operational test

## 13. Hardware and Infrastructure

AGRA is designed to run on ICG-provided hardware as specified in SOTR Section 7.

| Component | ICG Specification (SOTR) | TRIAD-AI Deployment Note |
|---|---|---|
| Primary GPU | 2× NVIDIA RTX 6000 Ada (48 GB each, 96 GB total) | Required for Llama-3.1 70B at 4-bit quantisation; both GPUs utilised via tensor parallelism in llama.cpp |
| Primary CPU | Intel Xeon Silver 4410Y or AMD EPYC 8241P | Required for BM25 indexing and document preprocessing |
| System RAM | 256 GB DDR5 ECC | Required for FAISS index caching and multi-document ingestion |
| Primary Storage | 2 TB NVMe Gen4 SSD (Primary) + 4 TB NVMe (Secondary) | FAISS index: approximately 50 GB per 10 M chunks; document store scales with corpus size |
| Secondary Server | RTX 3060 12 GB, 64 GB DDR5 | Hosts FastAPI and React UI; RTX 3060 optionally used for LLaVA inference |
| Internal Network | 10 Gbps Ethernet (Primary to Secondary) | Critical for sub-20 s end-to-end latency |
| OS | Ubuntu 22.04 LTS | Docker Compose deployment; `nvidia-container-toolkit` required |

## 14. Deliverables

| Ref | Deliverable | Description |
|---|---|---|
| D-01 | Administrator Manual | User management, document upload, agent configuration, House Rules setup |
| D-02 | API Documentation | OpenAPI 3.0 specification for all REST endpoints |
| D-03 | Deployment and Operations Manual | Air-gapped installation guide, Docker configuration, backup and recovery procedures |
| D-04 | Training Materials | End-user and administrator training presentations, exercises, and printed handouts |
| D-05 | Test Reports | Unit test, integration test, performance benchmark, security test, and UAT results |

## 15. Conclusion

The Air-Gapped Retrieval Agent (AGRA) presents a technically comprehensive, end-to-end methodology for secure AI-driven document knowledge management within the Indian Coast Guard’s air-gapped infrastructure. The proposed architecture addresses the operational challenges identified in the SOTR through seven integrated modules: document ingestion and knowledge base construction, hybrid RAG query processing, SOTR compliance verification with historical feedback, multimodal processing of engineering drawings, automated content generation, security architecture, and document genealogy and lineage visualization.

The SOTR Compliance Verification Engine with its Historical Feedback Module is of particular operational significance, automating clause-by-clause evaluation of procurement documents with full citation traceability and institutional memory spanning past procurement cycles.

The Document Genealogy and Lineage Visualization Module directly fulfils SOTR Objective 5, providing a complete and auditable trail of how every SOP, directive, and procurement document in the knowledge base evolved through version succession, incident-driven revisions, and cross-document influences.

The Evaluation Methodology defines a rigorous, multi-dimensional assessment framework covering retrieval quality, generation quality, latency and throughput, output generation timing, and system reliability.

The entire system is designed for deployment from encrypted physical media, with no internet dependency at any stage of installation or operation, consistent with defence-grade data sovereignty requirements.

---

## End of Report

**Air-Gapped Retrieval Agent (AGRA)**  
AI Based Document Assessment Software — Indian Coast Guard HQ, New Delhi  
All components are open-source and fully on-premise. No data leaves the ICG network at any point.  
Submitted by TRIAD-AI
