# AGRA Super Admin Dashboard

**AGRA - Air-Gapped Retrieval Agent | Indian Coast Guard HQ**

A full-stack super admin dashboard for managing the AGRA system — users, documents, agents, usage analytics, audit logs, and reports.

---

## Project Structure

```
Nothing/
├── backend/                    # FastAPI Python backend
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py             # FastAPI entry point
│   │   ├── database.py         # SQLAlchemy DB connection
│   │   ├── seed.py             # Seed super admin user
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   └── models.py       # SQLAlchemy ORM models
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py         # Authentication (login/logout/refresh)
│   │   │   ├── users.py        # User management
│   │   │   ├── dashboard.py    # Dashboard stats
│   │   │   ├── documents.py    # Document management
│   │   │   ├── agents.py       # Agent configuration
│   │   │   ├── usage.py        # Usage analytics
│   │   │   ├── audit.py        # Audit logs
│   │   │   └── reports.py      # Reports & exports
│   │   └── utils/
│   │       ├── __init__.py
│   │       └── security.py     # JWT, password hashing
│   ├── .env                    # Environment variables
│   └── requirements.txt        # Python dependencies
│
└── frontend/                   # React + Vite frontend
    ├── src/
    │   ├── components/
    │   │   └── Layout.jsx      # App layout with sidebar nav
    │   ├── pages/
    │   │   ├── Login.jsx        # Login page
    │   │   ├── Dashboard.jsx    # Main dashboard
    │   │   ├── Users.jsx        # User management
    │   │   ├── Documents.jsx    # Document management
    │   │   ├── Agents.jsx       # Agent configuration
    │   │   ├── UsageAnalytics.jsx # Usage analytics
    │   │   ├── AuditLogs.jsx    # Audit log viewer
    │   │   ├── Reports.jsx      # Reports & exports
    │   │   └── Settings.jsx     # System settings
    │   ├── utils/
    │   │   ├── api.js           # Axios API client
    │   │   └── auth.js          # Auth helpers
    │   ├── App.jsx              # App routes
    │   ├── main.jsx             # Entry point
    │   └── index.css            # Global styles
    ├── index.html
    ├── package.json
    └── vite.config.js
```

---

## Tech Stack

| Layer     | Technology                        |
|-----------|-----------------------------------|
| Frontend  | React 18, Vite, React Router v6   |
| Backend   | FastAPI, SQLAlchemy, Uvicorn      |
| Database  | SQLite (dev) / PostgreSQL (prod)  |
| Auth      | JWT (access + refresh tokens)     |
| Styling   | CSS Variables, custom dark theme  |

---

## Getting Started

### Backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # configure your secrets
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`  
Swagger docs at `http://localhost:8000/docs`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The dashboard will be available at `http://localhost:3000`

---

## API Endpoints

| Module        | Prefix           | Description                        |
|---------------|------------------|------------------------------------|
| Auth          | `/api/auth`      | Login, logout, token refresh       |
| Users         | `/api/users`     | CRUD user management               |
| Dashboard     | `/api/dashboard` | System stats and activity feed     |
| Documents     | `/api/documents` | Document upload and management     |
| Agents        | `/api/agents`    | AI agent configuration             |
| Usage         | `/api/usage`     | Query usage analytics              |
| Audit         | `/api/audit`     | Audit log retrieval                |
| Reports       | `/api/reports`   | Reports, exports, system health    |

---

## Default Super Admin

On first run, a default super admin is seeded:

- **Username**: `admin`
- **Password**: Set via `ADMIN_PASSWORD` in `.env`

---

## Environment Variables

```env
DATABASE_URL=sqlite:///./agra.db
SECRET_KEY=your-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
ADMIN_PASSWORD=changeme
```

---

## License

Internal use only — Indian Coast Guard HQ / AGRA Project.
