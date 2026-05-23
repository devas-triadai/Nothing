"""
AGRA Module 2 — Evaluation Metrics Calculator
Implements Precision@k, Recall@k, NDCG@k, MRR for RAG evaluation.
"""

import math
from typing import List, Dict, Any
from datetime import datetime, timedelta
import logging

logger = logging.getLogger("agra.metrics")


def precision_at_k(relevant_items: set, retrieved_items: List[str], k: int) -> float:
    """
    Precision@k = (# relevant items in top-k) / k
    
    Args:
        relevant_items: Set of ground-truth relevant item IDs
        retrieved_items: List of retrieved item IDs (ordered by rank)
        k: Number of top results to consider
    
    Returns:
        Precision@k score (0.0 to 1.0)
    """
    if k <= 0:
        return 0.0
    
    top_k = retrieved_items[:k]
    relevant_in_top_k = sum(1 for item in top_k if item in relevant_items)
    return relevant_in_top_k / k


def recall_at_k(relevant_items: set, retrieved_items: List[str], k: int) -> float:
    """
    Recall@k = (# relevant items in top-k) / (# total relevant items)
    
    Args:
        relevant_items: Set of ground-truth relevant item IDs
        retrieved_items: List of retrieved item IDs (ordered by rank)
        k: Number of top results to consider
    
    Returns:
        Recall@k score (0.0 to 1.0)
    """
    if not relevant_items:
        return 0.0
    
    top_k = retrieved_items[:k]
    relevant_in_top_k = sum(1 for item in top_k if item in relevant_items)
    return relevant_in_top_k / len(relevant_items)


def dcg_at_k(relevance_scores: List[float], k: int) -> float:
    """
    Discounted Cumulative Gain at k.
    DCG = sum(rel_i / log2(i + 1)) for i = 1 to k
    
    Args:
        relevance_scores: List of relevance scores (0, 1, or 2) ordered by rank
        k: Number of top results to consider
    
    Returns:
        DCG score
    """
    dcg = 0.0
    for i, rel in enumerate(relevance_scores[:k], start=1):
        # Add 1 to position because log2(1) = 0, but we need log2(2) for first position
        dcg += rel / math.log2(i + 1)
    return dcg


def ndcg_at_k(relevance_scores: List[float], k: int) -> float:
    """
    Normalized Discounted Cumulative Gain at k.
    NDCG = DCG / IDCG where IDCG is ideal DCG (perfect ranking)
    
    Args:
        relevance_scores: List of relevance scores (0, 1, or 2) ordered by rank
        k: Number of top results to consider
    
    Returns:
        NDCG@k score (0.0 to 1.0)
    """
    if not relevance_scores:
        return 0.0
    
    actual_dcg = dcg_at_k(relevance_scores, k)
    
    # Ideal DCG: sort by relevance descending
    ideal_scores = sorted(relevance_scores, reverse=True)
    ideal_dcg = dcg_at_k(ideal_scores, k)
    
    if ideal_dcg == 0:
        return 0.0
    
    return actual_dcg / ideal_dcg


def mean_reciprocal_rank(relevance_ranks: List[int]) -> float:
    """
    Mean Reciprocal Rank (MRR).
    MRR = mean(1 / rank_of_first_relevant) across all queries
    
    Args:
        relevance_ranks: List of ranks where first relevant item appears
                        (empty if no relevant items found)
    
    Returns:
        MRR score (0.0 to 1.0)
    """
    if not relevance_ranks:
        return 0.0
    
    reciprocal_ranks = [1.0 / rank for rank in relevance_ranks]
    return sum(reciprocal_ranks) / len(reciprocal_ranks)


def calculate_citation_accuracy(total_citations: int, valid_citations: int) -> float:
    """
    Citation accuracy = valid_citations / total_citations
    
    Args:
        total_citations: Total number of citations in response
        valid_citations: Number of citations that match sources
    
    Returns:
        Accuracy as percentage (0.0 to 100.0)
    """
    if total_citations == 0:
        return 100.0  # No citations = vacuously accurate
    return (valid_citations / total_citations) * 100.0


def calculate_hallucination_rate(total_claims: int, unsupported_claims: int) -> float:
    """
    Hallucination rate = unsupported_claims / total_claims
    
    Args:
        total_claims: Total number of factual claims
        unsupported_claims: Number of claims not supported by sources
    
    Returns:
        Hallucination rate as percentage (0.0 to 100.0)
    """
    if total_claims == 0:
        return 0.0
    return (unsupported_claims / total_claims) * 100.0


def aggregate_metrics_from_logs(query_logs: List[Dict], 
                                chunk_logs: List[Dict],
                                feedback_logs: List[Dict]) -> Dict[str, Any]:
    """
    Calculate aggregated metrics from query and feedback logs.
    
    Args:
        query_logs: List of query log dictionaries
        chunk_logs: List of retrieved chunk log dictionaries  
        feedback_logs: List of user feedback dictionaries
    
    Returns:
        Dictionary with aggregated metrics
    """
    if not query_logs:
        return {
            "precision_at_5": 0.0,
            "precision_at_10": 0.0,
            "recall_at_5": 0.0,
            "recall_at_10": 0.0,
            "ndcg_at_10": 0.0,
            "mrr": 0.0,
        }
    
    # Group by query
    query_chunks = {}
    query_feedback = {}
    
    for chunk in chunk_logs:
        qid = chunk["query_id"]
        if qid not in query_chunks:
            query_chunks[qid] = []
        query_chunks[qid].append(chunk)
    
    for fb in feedback_logs:
        qid = fb["query_id"]
        if qid not in query_feedback:
            query_feedback[qid] = {}
        query_feedback[qid][fb["chunk_id"]] = fb["relevance_score"]
    
    # Calculate metrics per query
    precisions_5 = []
    precisions_10 = []
    recalls_5 = []
    recalls_10 = []
    ndcgs_10 = []
    first_relevant_ranks = []
    
    for query in query_logs:
        qid = query.get("id")
        if qid not in query_feedback:
            continue  # Skip queries without feedback
        
        chunks = query_chunks.get(qid, [])
        feedback = query_feedback[qid]
        
        # Build relevance map
        chunk_ids = [c["chunk_id"] for c in sorted(chunks, key=lambda x: x["rank"])]
        relevance_scores = [feedback.get(cid, 0) for cid in chunk_ids]
        
        # Consider items with score >= 1 as relevant
        relevant_items = {cid for cid, score in zip(chunk_ids, relevance_scores) if score >= 1}
        
        # Precision
        precisions_5.append(precision_at_k(relevant_items, chunk_ids, 5))
        precisions_10.append(precision_at_k(relevant_items, chunk_ids, 10))
        
        # Recall (need total relevant count from ground truth)
        total_relevant = sum(1 for score in feedback.values() if score >= 1)
        if total_relevant > 0:
            recalls_5.append(recall_at_k(set(relevant_items), chunk_ids, 5))
            recalls_10.append(recall_at_k(set(relevant_items), chunk_ids, 10))
        
        # NDCG
        ndcgs_10.append(ndcg_at_k(relevance_scores, 10))
        
        # MRR: find first relevant
        for i, cid in enumerate(chunk_ids, start=1):
            if cid in relevant_items:
                first_relevant_ranks.append(i)
                break
    
    # Aggregate
    def safe_mean(values):
        return sum(values) / len(values) if values else 0.0
    
    return {
        "precision_at_5": safe_mean(precisions_5),
        "precision_at_10": safe_mean(precisions_10),
        "recall_at_5": safe_mean(recalls_5),
        "recall_at_10": safe_mean(recalls_10),
        "ndcg_at_10": safe_mean(ndcgs_10),
        "mrr": mean_reciprocal_rank(first_relevant_ranks),
        "queries_evaluated": len(precisions_5),
    }
