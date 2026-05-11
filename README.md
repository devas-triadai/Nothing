# AGRA - Air-Gapped Retrieval Agent
**Indian Coast Guard HQ**

AGRA is a fully secure, air-gapped, local AI-powered RAG (Retrieval-Augmented Generation) system and Super Admin Dashboard. It is designed to handle complex military documents, technical blueprints, standards, and operational reports entirely offline on dedicated GPU infrastructure.

---

## 🌟 Key Features & Recent Upgrades

### 1. Fully Air-Gapped Local AI Models
- **Local Model Routing:** Configured strictly for local execution. Replaced all external dependencies (like GPT-4) with robust local alternatives (e.g., Llama 3 70B for heavy reasoning, Gemma 2B for fast metadata extraction).
- **Global House Rules:** Superadmins can inject "House Rules" (global system prompts) to strictly govern the agent's behavior and formatting across all queries.

### 2. Multi-Functional Agent Chat Interface
- **Background PPT Generation:** Ask the AI to build a PowerPoint presentation. The job is sent to an asynchronous background worker, immediately returning a placeholder so you can keep chatting. Once finished, a downloadable PPT card appears with a **Refine** button to generate new versions based on feedback.
- **Strict Session Isolation:** Implemented flawless cross-chat state isolation. When switching between active chat sessions, any ongoing AI streams are aborted, and data is aggressively sandboxed to prevent any prompt leaking.
- **PDF Citation Highlighting:** Clickable citation pills instantly load the original document natively scrolled to the exact cited page, highlighting the exact phrase.
- **Inline Knowledge Quizzes:** Generate dynamic Multiple Choice and Short Answer quizzes from your uploaded documents directly in the chat interface.
- **Theme Support:** Fully optimized light/dark modes for high visibility across all components.

### 3. High-Scale Document Ingestion
- **Bulk Auto-Categorization:** Built for 1 Million+ documents. Features an asynchronous worker that scans uploaded files (Blueprints, SOPs, Imagery) and automatically tags and categorizes them, eliminating manual dropdown selection.
- **Version History:** Track the lineage of documents with a visual timeline modal, view previous versions, and manage updates.

### 4. Comprehensive Super Admin Dashboard
- **Agent Configuration:** Easily create, edit, and delete custom AI agents tailored for specific tasks.
- **Document Management:** Full CRUD operations on the knowledge base with instant download and view buttons.
- **Analytics & Reports:** Export usage analytics, active session data, and system health metrics directly to CSV.

### 5. Military-Grade Multimodal VLM + Hybrid OCR (Phase 4)
- **Hybrid 3-Model Vision Pipeline:** Engineering drawings and schematics are processed through OpenCV preprocessing → **Tesseract 5** (printed text, dimensions, labels) → **TrOCR** (handwritten annotations, stamps, signatures) → **Gemma 4 31B-IT VLM** (vision reasoning with OCR-grounded prompt).
- **OCR-Grounded Parameter Extraction:** The VLM receives both the image and the exact mechanically extracted text, eliminating hallucination on critical dimensions and tolerances.
- **Deterministic + Generative:** Tesseract/TrOCR guarantee exact text accuracy; Gemma 4 31B provides semantic understanding of the drawing structure. This hybrid exceeds the original report spec (which used LLaVA 1.5).

---

## 🏗️ Project Structure

```text
Nothing/
├── backend/                    # FastAPI Python backend
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py             # FastAPI entry point
│   │   ├── database.py         # SQLAlchemy DB connection
│   │   ├── seed.py             # Seed super admin user
│   │   ├── models/             # SQLAlchemy ORM models
│   │   ├── routers/            # API Endpoints (Auth, Users, Agents, Docs, Reports)
│   │   └── utils/              # JWT Security & Auth helpers
│   ├── .env                    # Environment variables
│   └── requirements.txt        # Python dependencies
│
├── frontend/                   # React + Vite Super Admin Dashboard
│   ├── src/
│   │   ├── components/         # Reusable UI elements (Layout, Spinner, etc.)
│   │   ├── pages/              # Dashboard, Users, Documents, Agents, Reports
│   │   └── utils/              # Axios API client & Auth helpers
│
└── agent/                      # Agent Chat UI Workspace
    └── ui/
        └── src/
            ├── pages/
            │   └── Chat.jsx    # Core unified chat, PPT, and Quiz interface
            └── index.css       # Theming and layout variables
```

---

## 🛠️ Tech Stack

| Layer     | Technology                        |
|-----------|-----------------------------------|
| **Frontend**  | React 18, Vite, React Router v6   |
| **Backend**   | FastAPI, SQLAlchemy, Uvicorn      |
| **Database**  | SQLite (dev) / PostgreSQL (prod)  |
| **Auth**      | JWT (access + refresh tokens)     |
| **Styling**   | Vanilla CSS with CSS Variables    |
| **VLM**     | Gemma 4 31B-IT (via llama-server) |
| **Printed OCR** | Tesseract 5 (pytesseract)       |
| **Handwriting OCR** | TrOCR (HuggingFace transformers) |
| **Vision Preprocess** | OpenCV (deskew, denoise, binarize) |

---

## 🚀 Getting Started

### Backend Setup

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # configure your secrets
uvicorn app.main:app --reload --port 8000
```
- The API will be available at `http://localhost:8000`
- Swagger docs at `http://localhost:8000/docs`

### Agent API Setup

```bash
cd agent
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8005
```
- The agent API will be available at `http://localhost:8005`

> **System Dependency:** Tesseract 5 must be installed at the OS level for printed-text OCR:
> ```bash
> # Ubuntu / Debian
> sudo apt-get install tesseract-ocr
> # macOS
> brew install tesseract
> ```
> TrOCR (handwriting) is downloaded automatically via HuggingFace on first use (~1.3 GB).

### Frontend Dashboard Setup

```bash
cd frontend
npm install
npm run dev
```
- The dashboard will be available at `http://localhost:3000`

---

## 🔐 Default Super Admin

On first run, a default super admin is seeded:
- **Username**: `admin`
- **Password**: Set via `ADMIN_PASSWORD` in `.env`

---

## 📜 License
Internal use only — Indian Coast Guard HQ / AGRA Project.
