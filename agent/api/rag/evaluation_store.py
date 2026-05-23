"""
AGRA Module 2 — Evaluation Data Store
SQLite-based storage for query logs, feedback, and metrics.
"""

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import threading
import logging

logger = logging.getLogger("agra.evaluation_store")

# Persistent storage
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "agra_data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_DB_PATH = _DATA_DIR / "evaluation.db"


class EvaluationStore:
    """Thread-safe SQLite store for evaluation data."""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init_db()
        return cls._instance
    
    def _init_db(self):
        """Initialize database tables."""
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS query_logs (
                    id TEXT PRIMARY KEY,
                    query_text TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    session_id TEXT,
                    timestamp TEXT NOT NULL,
                    doc_filter TEXT,  -- JSON list
                    category_filter TEXT,
                    response_time_ms REAL,
                    final_confidence_score REAL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chunk_logs (
                    id TEXT PRIMARY KEY,
                    query_id TEXT NOT NULL,
                    chunk_id TEXT NOT NULL,
                    rank INTEGER NOT NULL,
                    dense_score REAL NOT NULL,
                    bm25_score REAL NOT NULL,
                    rerank_score REAL,
                    combined_score REAL NOT NULL,
                    text_excerpt TEXT NOT NULL,
                    metadata TEXT NOT NULL,  -- JSON
                    FOREIGN KEY (query_id) REFERENCES query_logs(id)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_feedback (
                    id TEXT PRIMARY KEY,
                    query_id TEXT NOT NULL,
                    chunk_id TEXT NOT NULL,
                    relevance_score INTEGER NOT NULL,
                    feedback_text TEXT,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (query_id) REFERENCES query_logs(id)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS citation_validation_logs (
                    id TEXT PRIMARY KEY,
                    query_id TEXT NOT NULL,
                    response_text TEXT NOT NULL,
                    total_citations INTEGER NOT NULL,
                    valid_citations INTEGER NOT NULL,
                    invalid_citations INTEGER NOT NULL,
                    unverified_claims INTEGER NOT NULL,
                    citation_accuracy REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (query_id) REFERENCES query_logs(id)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hallucination_logs (
                    id TEXT PRIMARY KEY,
                    query_id TEXT NOT NULL,
                    total_claims INTEGER NOT NULL,
                    supported_claims INTEGER NOT NULL,
                    unsupported_claims INTEGER NOT NULL,
                    contradicted_claims INTEGER NOT NULL,
                    hallucination_rate REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (query_id) REFERENCES query_logs(id)
                )
            """)
            
            # Create indexes for faster queries
            conn.execute("CREATE INDEX IF NOT EXISTS idx_query_logs_user ON query_logs(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_query_logs_time ON query_logs(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunk_logs_query ON chunk_logs(query_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_query ON user_feedback(query_id)")
            
            conn.commit()
        logger.info("Evaluation database initialized at %s", _DB_PATH)
    
    def log_query(self, query_text: str, user_id: int, session_id: Optional[str] = None,
                  doc_filter: Optional[List[str]] = None, category_filter: Optional[str] = None,
                  response_time_ms: Optional[float] = None, 
                  final_confidence_score: Optional[float] = None) -> str:
        """Log a query and return the query ID."""
        query_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()
        
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute("""
                INSERT INTO query_logs (id, query_text, user_id, session_id, timestamp,
                                        doc_filter, category_filter, response_time_ms,
                                        final_confidence_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (query_id, query_text, user_id, session_id, timestamp,
                  json.dumps(doc_filter) if doc_filter else None, category_filter,
                  response_time_ms, final_confidence_score))
            conn.commit()
        
        return query_id
    
    def log_chunks(self, query_id: str, chunks: List[Dict[str, Any]]):
        """Log retrieved chunks for a query."""
        timestamp = datetime.utcnow().isoformat()
        
        with sqlite3.connect(_DB_PATH) as conn:
            for i, chunk in enumerate(chunks, start=1):
                chunk_id = str(uuid.uuid4())
                conn.execute("""
                    INSERT INTO chunk_logs (id, query_id, chunk_id, rank, dense_score,
                                           bm25_score, rerank_score, combined_score,
                                           text_excerpt, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (chunk_id, query_id, chunk.get("pid", chunk.get("id")), i,
                      chunk.get("dense_score", 0.0), chunk.get("bm25_score", 0.0),
                      chunk.get("rerank_score"), chunk.get("combined_score", 0.0),
                      chunk.get("text", "")[:500],  # Truncate for storage
                      json.dumps(chunk.get("metadata", {}))))
            conn.commit()
    
    def add_feedback(self, query_id: str, chunk_id: str, relevance_score: int,
                     feedback_text: Optional[str] = None) -> str:
        """Add user feedback for a specific chunk."""
        feedback_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()
        
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute("""
                INSERT INTO user_feedback (id, query_id, chunk_id, relevance_score,
                                          feedback_text, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (feedback_id, query_id, chunk_id, relevance_score, feedback_text, timestamp))
            conn.commit()
        
        return feedback_id
    
    def log_citation_validation(self, query_id: str, response_text: str,
                                total_citations: int, valid_citations: int,
                                invalid_citations: int, unverified_claims: int,
                                citation_accuracy: float):
        """Log citation validation results."""
        log_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()
        
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute("""
                INSERT INTO citation_validation_logs 
                (id, query_id, response_text, total_citations, valid_citations,
                 invalid_citations, unverified_claims, citation_accuracy, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (log_id, query_id, response_text[:10000], total_citations, valid_citations,
                  invalid_citations, unverified_claims, citation_accuracy, timestamp))
            conn.commit()
    
    def log_hallucination_detection(self, query_id: str, total_claims: int,
                                     supported_claims: int, unsupported_claims: int,
                                     contradicted_claims: int, hallucination_rate: float):
        """Log hallucination detection results."""
        log_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()
        
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute("""
                INSERT INTO hallucination_logs 
                (id, query_id, total_claims, supported_claims, unsupported_claims,
                 contradicted_claims, hallucination_rate, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (log_id, query_id, total_claims, supported_claims, unsupported_claims,
                  contradicted_claims, hallucination_rate, timestamp))
            conn.commit()
    
    def get_metrics(self, days: int = 30) -> Dict[str, Any]:
        """Get aggregated metrics for the specified period."""
        cutoff = (datetime.utcnow() - __import__('datetime').timedelta(days=days)).isoformat()
        
        with sqlite3.connect(_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            
            # Query logs
            query_rows = conn.execute("""
                SELECT * FROM query_logs WHERE timestamp > ?
            """, (cutoff,)).fetchall()
            
            # Chunk logs for these queries
            query_ids = [r["id"] for r in query_rows]
            chunk_rows = []
            if query_ids:
                placeholders = ','.join('?' * len(query_ids))
                chunk_rows = conn.execute(f"""
                    SELECT * FROM chunk_logs WHERE query_id IN ({placeholders})
                """, query_ids).fetchall()
            
            # Feedback
            feedback_rows = []
            if query_ids:
                placeholders = ','.join('?' * len(query_ids))
                feedback_rows = conn.execute(f"""
                    SELECT * FROM user_feedback WHERE query_id IN ({placeholders})
                """, query_ids).fetchall()
            
            # Citation validation
            citation_rows = conn.execute("""
                SELECT AVG(citation_accuracy) as avg_accuracy
                FROM citation_validation_logs WHERE timestamp > ?
            """, (cutoff,)).fetchone()
            
            # Hallucination detection
            hallucination_rows = conn.execute("""
                SELECT AVG(hallucination_rate) as avg_rate
                FROM hallucination_logs WHERE timestamp > ?
            """, (cutoff,)).fetchone()
            
            # Response time stats
            time_stats = conn.execute("""
                SELECT AVG(response_time_ms) as avg_time,
                       COUNT(*) as total
                FROM query_logs WHERE timestamp > ? AND response_time_ms IS NOT NULL
            """, (cutoff,)).fetchone()
            
            # Confidence distribution
            confidence_rows = conn.execute("""
                SELECT 
                    SUM(CASE WHEN final_confidence_score >= 0.7 THEN 1 ELSE 0 END) as high,
                    SUM(CASE WHEN final_confidence_score >= 0.4 AND final_confidence_score < 0.7 THEN 1 ELSE 0 END) as medium,
                    SUM(CASE WHEN final_confidence_score < 0.4 THEN 1 ELSE 0 END) as low,
                    COUNT(*) as total
                FROM query_logs WHERE timestamp > ? AND final_confidence_score IS NOT NULL
            """, (cutoff,)).fetchone()
        
        # Convert to dicts for metrics calculation
        from api.rag.metrics import aggregate_metrics_from_logs
        
        query_logs = [dict(r) for r in query_rows]
        chunk_logs = [dict(r) for r in chunk_rows]
        feedback_logs = [dict(r) for r in feedback_rows]
        
        metrics = aggregate_metrics_from_logs(query_logs, chunk_logs, feedback_logs)
        
        # Add additional stats
        total_with_confidence = confidence_rows["total"] or 0
        if total_with_confidence > 0:
            high_pct = (confidence_rows["high"] or 0) / total_with_confidence * 100
            medium_pct = (confidence_rows["medium"] or 0) / total_with_confidence * 100
            low_pct = (confidence_rows["low"] or 0) / total_with_confidence * 100
        else:
            high_pct = medium_pct = low_pct = 0.0
        
        return {
            "period_days": days,
            "total_queries": time_stats["total"] or 0,
            "avg_response_time_ms": time_stats["avg_time"] or 0.0,
            **metrics,
            "avg_citation_accuracy": citation_rows["avg_accuracy"] or 0.0,
            "avg_hallucination_rate": hallucination_rows["avg_rate"] or 0.0,
            "high_confidence_pct": high_pct,
            "medium_confidence_pct": medium_pct,
            "low_confidence_pct": low_pct,
        }
    
    def get_recent_queries(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent queries with their stats."""
        with sqlite3.connect(_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM query_logs ORDER BY timestamp DESC LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]


# Module-level singleton
_store = EvaluationStore()


def get_store() -> EvaluationStore:
    """Get evaluation store instance."""
    return _store
