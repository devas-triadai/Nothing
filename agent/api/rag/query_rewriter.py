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

_REWRITE_PROMPT = """You are a search query optimizer for a maritime compliance knowledge base.

Your task: Rewrite the user's question into an optimal search query.

RULES:
1. Output STRICTLY ONLY the rewritten query. 
2. NO preamble, NO explanations, NO scratchpad, NO "Thinking" process.
3. Fix typos and expand abbreviations.
4. Output should be a single, keyword-rich sentence.

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

    # Add feedback hint if retrying
    feedback_hint = ""
    if feedback == "low_relevance":
        feedback_hint = " The initial search returned low-relevance results; try broader or alternative terms."

    _SYSTEM_REWRITE = (
        "You rewrite user questions into concise keyword-rich search queries for a "
        "maritime compliance knowledge base. Reply with ONLY the rewritten query as a single "
        "plain sentence. No quotes, no labels (like 'Query:' or 'User Input:'), no preamble, "
        "no explanations, no markdown, no bullets, no context echo. Just the raw search query."
        + feedback_hint
    )

    messages = [
        {"role": "system", "content": _SYSTEM_REWRITE},
        {"role": "user", "content": question},
    ]

    try:
        rewritten = llm_engine.generate(
            messages,
            max_tokens=64,
            temperature=0.2,
        )
        rewritten = rewritten.strip().strip('"').strip("'")

        # Strip common hallucinated prefixes
        for prefix in (
            "rewritten search query:", "search query:", "query:",
            "user input:", "user question:", "current question:", "question:",
            "context:", "rewritten:", "current:", "input:",
        ):
            if rewritten.lower().startswith(prefix):
                rewritten = rewritten[len(prefix):].strip().strip('"').strip("'")

        # Take only the first non-empty line (drop "Context: ..." follow-ups)
        rewritten = next((ln.strip() for ln in rewritten.splitlines() if ln.strip()), "")

        # Sanity check — if rewritten is empty or too short, fall back
        if len(rewritten) < 5:
            logger.warning("Rewritten query too short (%r), using original.", rewritten)
            return question

        logger.info("Query rewrite: %r → %r", question, rewritten)
        return rewritten

    except Exception as e:
        logger.warning("Query rewrite failed (%s), using original question.", e)
        return question
