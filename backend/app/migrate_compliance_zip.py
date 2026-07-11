"""
Migration: Add ZIP support columns to compliance_runs table.
Adds: vendor_commercial_zip_path, vendor_commercial_files, vendor_commercial_doc_ids
Also adds source_file_detail to clause_results table.
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import text
from app.database import engine, Base
from app.models.models import ComplianceRun, ClauseResult

# First ensure all tables exist (create new ones if any)
Base.metadata.create_all(bind=engine)

# Then add new columns to existing tables (SQLite ALTER TABLE ADD COLUMN)
ALTER_STATEMENTS = [
    # ComplianceRun new columns
    "ALTER TABLE compliance_runs ADD COLUMN vendor_commercial_zip_path VARCHAR(500)",
    "ALTER TABLE compliance_runs ADD COLUMN vendor_commercial_files JSON",
    "ALTER TABLE compliance_runs ADD COLUMN vendor_commercial_doc_ids JSON",
    # ClauseResult new column
    "ALTER TABLE clause_results ADD COLUMN source_file_detail VARCHAR(200)",
]

def run_migration():
    with engine.connect() as conn:
        for stmt in ALTER_STATEMENTS:
            try:
                conn.execute(text(stmt))
                conn.commit()
                print(f"  OK: {stmt}")
            except Exception as e:
                # Column already exists is fine
                if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                    print(f"  SKIP (already exists): {stmt}")
                else:
                    print(f"  WARN: {stmt} -> {e}")
        print("Migration complete.")

if __name__ == "__main__":
    print("Migrating: Compliance ZIP support columns")
    run_migration()
