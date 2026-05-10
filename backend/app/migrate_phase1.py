"""
AGRA — Database Migration: Add Phase 1 columns to documents table
Run this once to add new columns to existing SQLite database.

Usage: python -m app.migrate_phase1
"""

import sqlite3
import os
from pathlib import Path

_WORKSPACE = Path(os.getenv("AGRA_DATA_DIR", "/workspace/agra_data"))
if not _WORKSPACE.exists():
    _WORKSPACE = Path(__file__).resolve().parent.parent / "agra_data"

_DB_PATH = _WORKSPACE / "agra.db"


def migrate():
    if not _DB_PATH.exists():
        print(f"Database not found at {_DB_PATH} — skipping migration (will be created fresh).")
        return

    conn = sqlite3.connect(str(_DB_PATH))
    cursor = conn.cursor()

    # Get existing columns
    cursor.execute("PRAGMA table_info(documents)")
    existing_cols = {row[1] for row in cursor.fetchall()}

    new_columns = [
        ("sub_category", "VARCHAR(100)"),
        ("sha256_hash", "VARCHAR(64)"),
        ("source", "VARCHAR(30) DEFAULT 'admin_upload'"),
        ("classification_confidence", "FLOAT DEFAULT 0.0"),
        ("qdrant_doc_id", "VARCHAR(100)"),
    ]

    added = 0
    for col_name, col_type in new_columns:
        if col_name not in existing_cols:
            sql = f"ALTER TABLE documents ADD COLUMN {col_name} {col_type}"
            print(f"  Adding column: {col_name} ({col_type})")
            cursor.execute(sql)
            added += 1
        else:
            print(f"  Column already exists: {col_name}")

    # Create indexes for new columns
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_documents_sha256_hash ON documents(sha256_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_documents_qdrant_doc_id ON documents(qdrant_doc_id)")
    except Exception as e:
        print(f"  Index creation note: {e}")

    conn.commit()
    conn.close()
    print(f"\nMigration complete: {added} columns added to documents table.")


if __name__ == "__main__":
    migrate()
