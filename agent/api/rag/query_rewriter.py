"""
AGRA — Query Rewriter (RAG Priority 1)
Uses the local LLM to reformulate user queries into keyword-rich
search queries before embedding. This improves retrieval for vague,
conversational, or typo-laden questions.

Adds ~200-400ms latency but dramatically improves recall.
"""

import logging
from typing import Dict, List, Optional

from api.rag import llm as llm_engine

logger = logging.getLogger("agra.query_rewriter")

_REWRITE_PROMPT = """You are a search query optimizer for a maritime compliance knowledge base containing IMO SOLAS, MARPOL, STCW regulations, and Indian Coast Guard Standard Operating Procedures.

Your task: Rewrite the user's question into an optimal search query that will retrieve the most relevant document chunks.

RULES:
1. Output ONLY the rewritten query — no explanations, no preamble.
2. Expand abbreviations (e.g., "OPV" → "Offshore Patrol Vessel OPV").
3. Add relevant technical keywords that would appear in the source documents.
4. Fix obvious typos and spelling errors.
5. If the question references previous conversation, incorporate that context.
6. Keep the rewritten query to 1-2 sentences maximum.
7. Preserve the original intent — do not change what is being asked.

CONVERSATION CONTEXT (last 2 turns):
{history}

USER QUESTION: {question}

REWRITTEN SEARCH QUERY:"""


def rewrite_query(
    question: str,
    session_history: Optional[List[Dict[str, str]]] = None,
    feedback: Optional[str] = None,
) -> str:
    """
    Rewrite a user question into an optimized search query.

    Args:
        question: Original user question.
        session_history: Recent conversation turns for context.
        feedback: Optional hint (e.g., "low_relevance") to guide rewriting.

    Returns:
        Rewritten search query string. Falls back to original on failure.
    """
    # Build history context (last 2 turns only)
    history_str = "None"
    if session_history and len(session_history) > 0:
        recent = session_history[-4:]  # Last 2 Q&A pairs
        parts = []
        for msg in recent:
            role = msg.get("role", "user").capitalize()
            content = msg.get("content", "")[:200]  # Truncate for speed
            parts.append(f"{role}: {content}")
        history_str = "\n".join(parts)

    prompt_text = _REWRITE_PROMPT.format(
        history=history_str,
        question=question,
    )

    # Add feedback hint if retrying
    if feedback == "low_relevance":
        prompt_text += "\n(Note: The initial search returned low-relevance results. Try broader or alternative terms.)"

    _SYSTEM_REWRITE = "You are a search query optimizer for a maritime compliance knowledge base. Rewrite the user's question into an optimal search query. Output ONLY the rewritten query — no explanations, no preamble. Fix typos and expand abbreviations."
    
    messages = [
        {"role": "system", "content": _SYSTEM_REWRITE},
        {"role": "user", "content": f"Context: {history_str}\n\nQuestion: {question}"},
    ]

    try:
        rewritten = llm_engine.generate(
            messages,
            max_tokens=512,
            temperature=0.2,
        )
        rewritten = rewritten.strip().strip('"').strip("'")

        # Sanity check — if rewritten is empty or too short, fall back
        if len(rewritten) < 5:
            logger.warning("Rewritten query too short (%r), using original.", rewritten)
            return question

        logger.info("Query rewrite: %r → %r", question, rewritten)
        return rewritten

    except Exception as e:
        logger.warning("Query rewrite failed (%s), using original question.", e)
        return question
