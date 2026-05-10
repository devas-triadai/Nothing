"""
AGRA Phase 2 — RAG: Semantic Cache
Caches query responses using BGE-M3 embeddings.
If a new query is semantically similar to a cached query (cosine sim > 0.95),
returns the cached response immediately, saving LLM tokens and time.
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any

import numpy as np

logger = logging.getLogger("agra.semantic_cache")

_CACHE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "agra_data"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_DB_PATH = _CACHE_DIR / "semantic_cache.db"

_SIMILARITY_THRESHOLD = 0.95


class SemanticCache:
    def __init__(self):
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    response TEXT NOT NULL,
                    sources TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        if not v1 or not v2: return 0.0
        v1_arr = np.array(v1)
        v2_arr = np.array(v2)
        norm = np.linalg.norm(v1_arr) * np.linalg.norm(v2_arr)
        return np.dot(v1_arr, v2_arr) / norm if norm else 0.0

    def check_cache(self, query: str, query_embedding: List[float]) -> Optional[Dict[str, Any]]:
        """Check if a semantically equivalent query exists in cache."""
        try:
            with sqlite3.connect(_DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT query, embedding, response, sources FROM cache ORDER BY created_at DESC LIMIT 100")
                rows = cursor.fetchall()

                best_sim = 0.0
                best_match = None

                for row in rows:
                    cached_query, emb_blob, response, sources_json = row
                    cached_emb = np.frombuffer(emb_blob, dtype=np.float32).tolist()
                    sim = self._cosine_similarity(query_embedding, cached_emb)
                    
                    if sim > best_sim:
                        best_sim = sim
                        if sim >= _SIMILARITY_THRESHOLD:
                            best_match = {
                                "response": response,
                                "sources": json.loads(sources_json),
                                "similarity": sim,
                                "cached_query": cached_query
                            }

                if best_match:
                    logger.info("Semantic cache HIT (sim=%.3f) for query: %s", best_match["similarity"], query[:50])
                    return best_match
                
                return None
        except Exception as e:
            logger.warning("Cache check failed: %s", e)
            return None

    def add_to_cache(self, query: str, query_embedding: List[float], response: str, sources: List[Dict[str, Any]]):
        """Add a new query and response to the semantic cache."""
        try:
            emb_blob = np.array(query_embedding, dtype=np.float32).tobytes()
            with sqlite3.connect(_DB_PATH) as conn:
                conn.execute(
                    "INSERT INTO cache (query, embedding, response, sources) VALUES (?, ?, ?, ?)",
                    (query, emb_blob, response, json.dumps(sources))
                )
                conn.commit()
                logger.debug("Added to semantic cache: %s", query[:50])
        except Exception as e:
            logger.warning("Cache write failed: %s", e)

semantic_cache = SemanticCache()
