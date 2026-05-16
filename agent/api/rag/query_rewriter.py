"""
AGRA — Query Rewriter (RAG Priority 1)
Uses the local LLM to reformulate user queries into keyword-rich
search queries before embedding. This improves retrieval for vague,
conversational, or typo-laden questions.

Adds ~200-400ms latency but dramatically improves recall.
"""

import logging
import re
from typing import Dict, List, Optional

from api.rag import llm as llm_engine

logger = logging.getLogger("agra.query_rewriter")


def _strip_scratchpad(text: str) -> str:
    """
    Workstream G: Remove all chain-of-thought / scratchpad artifacts from LLM output.
    Handles: <scratchpad>...</scratchpad>, <thinking>...</thinking>, <think>...</think>,
    **Thinking:** blocks, numbered reasoning steps, and stray XML tags.
    """
    # 1. Remove XML-style block tags with their content (greedy across newlines)
    text = re.sub(
        r'<(scratchpad|thinking|think|reasoning|reflection|internal)>.*?</\1>',
        '', text, flags=re.DOTALL | re.IGNORECASE,
    )
    # 2. Remove unclosed XML tags (model truncated mid-scratchpad)
    text = re.sub(
        r'<(scratchpad|thinking|think|reasoning|reflection|internal)>.*',
        '', text, flags=re.DOTALL | re.IGNORECASE,
    )
    # 3. Remove stray closing tags
    text = re.sub(r'</(scratchpad|thinking|think|reasoning|reflection|internal)>', '', text, flags=re.IGNORECASE)
    # 4. Remove **Thinking:** or **Reasoning:** markdown-bold preambles (everything until a newline or end)
    text = re.sub(r'\*\*(Thinking|Reasoning|Internal|Scratchpad)\*\*[:\s].*?(\n|$)', '', text, flags=re.IGNORECASE)
    # 5. Remove numbered reasoning lines like "1. The user is asking about..."
    text = re.sub(r'^\d+\.\s+(The user|First|Let me|I need|This question|We should).*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
    # 6. Clean up multiple blank lines / leading whitespace
    text = re.sub(r'\n{2,}', '\n', text).strip()
    return text

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
    # Build history context (last 2 Q&A pairs)
    # Workstream I: Filter to only clean user/assistant messages, truncate tighter
    history_str = "None"
    if session_history and len(session_history) > 0:
        clean = [
            m for m in session_history
            if m.get("role") in ("user", "assistant")
            and m.get("content", "").strip()
            and len(m.get("content", "").strip()) > 2
        ]
        recent = clean[-4:]  # Last 2 Q&A pairs
        parts = []
        for msg in recent:
            role = msg.get("role", "user").capitalize()
            content = msg.get("content", "")[:150]  # Truncate for speed
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
        # Workstream G: Strip scratchpad/thinking artifacts BEFORE any other cleaning
        rewritten = _strip_scratchpad(rewritten)
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
