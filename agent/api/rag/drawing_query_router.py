"""
AGRA Chat Enhancement Phase 2 — Drawing Query Intent Router
Classifies user queries and routes to appropriate processing strategy.

Offline/Local: Uses llama-server @ localhost:8080
"""

import logging
import re
from typing import Dict, List, Literal, Optional
from enum import Enum

from pydantic import BaseModel, Field

from api.rag import llm as llm_engine

logger = logging.getLogger("agra.drawing_query_router")


# ═══════════════════════════════════════════════════════════════
#  INTENT ENUMERATION
# ═══════════════════════════════════════════════════════════════

class QueryIntent(str, Enum):
    """Enumeration of supported query intents for drawing analysis."""
    EXTRACT = "extract"           # Extract dimensions, measurements
    IDENTIFY = "identify"         # Identify equipment, components
    COMPARE = "compare"           # Compare with specs/requirements
    SUGGEST = "suggest"           # Suggest usefulness, advancement
    VALIDATE = "validate"         # Validate correctness


# ═══════════════════════════════════════════════════════════════
#  QUERY PLAN MODELS
# ═══════════════════════════════════════════════════════════════

class ProcessingStep(BaseModel):
    """A single step in the query execution plan."""
    step_name: str
    required: bool = True
    weight_in_confidence: float = Field(..., ge=0.0, le=1.0)
    fallback_action: Optional[str] = None


class QueryPlan(BaseModel):
    """Execution plan for a drawing query."""
    intent: QueryIntent
    confidence: float = Field(..., ge=0.0, le=1.0)
    steps: List[ProcessingStep]
    requires_rag: bool
    requires_vlm: bool
    max_tokens_for_answer: int
    temperature: float
    priority: int = Field(..., ge=1, le=5, description="1=highest priority")


# ═══════════════════════════════════════════════════════════════
#  INTENT CLASSIFICATION PROMPTS
# ═══════════════════════════════════════════════════════════════

INTENT_PROMPT_V2 = """You are an intent classifier for engineering drawing queries in a maritime/ICG context.

Classify the user's question into EXACTLY ONE of these categories:

EXTRACT - User wants to pull specific data from drawing:
  "extract dimensions", "what are the measurements", "list the specs",
  "show all dimensions", "what is the length", "give me the tolerances"

IDENTIFY - User wants to know what something is:
  "what equipment is this", "identify the components", "what part is shown",
  "name this equipment", "what system does this belong to"

COMPARE - User wants to compare against standards:
  "does this meet specs", "compare with SOTR", "check compliance",
  "is this according to requirements", "verify against standards"

SUGGEST - User wants recommendations:
  "is this useful", "can we use this", "should we adopt",
  "advancement potential", "modernization value", "upgrade recommendation"

VALIDATE - User wants verification:
  "is this correct", "validate dimensions", "check measurements",
  "verify this drawing", "is this accurate"

Respond with ONLY the category name in UPPERCASE, nothing else.

User Query: {query}
Intent: """


# ═══════════════════════════════════════════════════════════════
#  KEYWORD-BASED FAST CLASSIFICATION
# ═══════════════════════════════════════════════════════════════

KEYWORD_PATTERNS: Dict[QueryIntent, List[str]] = {
    QueryIntent.EXTRACT: [
        r"extract\s+(?:all\s+)?(?:dimension|measurement|spec)",
        r"what\s+(?:are|is)\s+(?:the\s+)?(?:dimension|measurement|length|width|height|tolerance)",
        r"list\s+(?:all\s+)?(?:dimension|spec|measurement)",
        r"show\s+(?:me\s+)?(?:all\s+)?(?:dimension|measurement)",
        r"get\s+(?:the\s+)?(?:dimension|measurement|spec)",
        r"pull\s+(?:the\s+)?(?:dimension|measurement)"
    ],
    QueryIntent.IDENTIFY: [
        r"what\s+(?:equipment|component|part|system|item)",
        r"identify\s+(?:the\s+)?(?:equipment|component|part|system)",
        r"name\s+(?:the\s+)?(?:equipment|component|part)",
        r"what\s+is\s+(?:this|shown|displayed)",
        r"which\s+(?:equipment|part|component)"
    ],
    QueryIntent.COMPARE: [
        r"compare\s+(?:with|to|against)",
        r"does\s+this\s+(?:meet|satisfy|comply)",
        r"check\s+(?:compliance|against|versus)",
        r"is\s+this\s+(?:according|compliant|per)",
        r"verify\s+(?:against|with|compliance)"
    ],
    QueryIntent.SUGGEST: [
        r"is\s+this\s+(?:useful|valuable|beneficial)",
        r"can\s+we\s+(?:use|adopt|implement)",
        r"should\s+we\s+(?:use|adopt|consider)",
        r"advancement\s+(?:potential|value|opportunity)",
        r"modernization\s+(?:potential|value)",
        r"upgrade\s+(?:recommendation|potential|value)",
        r"recommend\s+(?:adoption|use|implementation)"
    ],
    QueryIntent.VALIDATE: [
        r"is\s+this\s+(?:correct|accurate|valid)",
        r"validate\s+(?:the\s+)?(?:dimension|measurement|drawing)",
        r"check\s+(?:if\s+)?(?:correct|accurate|valid)",
        r"verify\s+(?:the\s+)?(?:dimension|measurement|accuracy)"
    ]
}


def classify_intent_fast(query: str) -> Optional[QueryIntent]:
    """
    Fast keyword-based intent classification.
    Returns None if no clear match (fallback to LLM).
    """
    query_lower = query.lower()
    
    scores: Dict[QueryIntent, int] = {intent: 0 for intent in QueryIntent}
    
    for intent, patterns in KEYWORD_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, query_lower):
                scores[intent] += 1
    
    # Find intent with highest score
    max_score = max(scores.values())
    if max_score > 0:
        best_intent = max(scores, key=scores.get)
        return best_intent
    
    return None


def classify_intent_llm(query: str) -> QueryIntent:
    """
    LLM-based intent classification for complex queries.
    """
    try:
        prompt = INTENT_PROMPT_V2.format(query=query)
        response = llm_engine.llm_complete(
            prompt=prompt,
            max_tokens=15,
            temperature=0.1
        )
        
        intent_str = response.strip().upper()
        
        # Map to enum
        intent_map = {
            "EXTRACT": QueryIntent.EXTRACT,
            "IDENTIFY": QueryIntent.IDENTIFY,
            "COMPARE": QueryIntent.COMPARE,
            "SUGGEST": QueryIntent.SUGGEST,
            "VALIDATE": QueryIntent.VALIDATE
        }
        
        return intent_map.get(intent_str, QueryIntent.EXTRACT)
        
    except Exception as e:
        logger.warning(f"LLM intent classification failed: {e}")
        return QueryIntent.EXTRACT


def classify_intent(query: str, use_llm: bool = True) -> QueryIntent:
    """
    Two-tier intent classification:
    1. Fast keyword matching
    2. LLM fallback for complex queries
    
    Args:
        query: User's natural language query
        use_llm: Whether to use LLM fallback (True) or only keywords (False)
    
    Returns:
        Classified QueryIntent
    """
    # Try fast classification first
    fast_result = classify_intent_fast(query)
    
    if fast_result is not None:
        logger.debug(f"Fast intent classification: {fast_result.value} for query: {query[:50]}")
        return fast_result
    
    # Fall back to LLM if enabled
    if use_llm:
        llm_result = classify_intent_llm(query)
        logger.debug(f"LLM intent classification: {llm_result.value} for query: {query[:50]}")
        return llm_result
    
    # Default fallback
    return QueryIntent.EXTRACT


# ═══════════════════════════════════════════════════════════════
#  QUERY PLAN GENERATOR
# ═══════════════════════════════════════════════════════════════

QUERY_PLANS: Dict[QueryIntent, QueryPlan] = {
    QueryIntent.EXTRACT: QueryPlan(
        intent=QueryIntent.EXTRACT,
        confidence=0.9,
        steps=[
            ProcessingStep(
                step_name="vlm_analyze",
                required=True,
                weight_in_confidence=0.45,
                fallback_action="use_ocr_only"
            ),
            ProcessingStep(
                step_name="extract_structured",
                required=True,
                weight_in_confidence=0.35,
                fallback_action="return_raw_text"
            ),
            ProcessingStep(
                step_name="format_output",
                required=True,
                weight_in_confidence=0.20,
                fallback_action="return_json"
            )
        ],
        requires_rag=False,  # Extraction doesn't need RAG
        requires_vlm=True,
        max_tokens_for_answer=600,
        temperature=0.2,
        priority=1
    ),
    
    QueryIntent.IDENTIFY: QueryPlan(
        intent=QueryIntent.IDENTIFY,
        confidence=0.85,
        steps=[
            ProcessingStep(
                step_name="vlm_analyze",
                required=True,
                weight_in_confidence=0.40,
                fallback_action="use_ocr_only"
            ),
            ProcessingStep(
                step_name="rag_search_equipment",
                required=False,
                weight_in_confidence=0.25,
                fallback_action="skip_rag"
            ),
            ProcessingStep(
                step_name="cross_reference",
                required=False,
                weight_in_confidence=0.20,
                fallback_action="skip_cross_reference"
            ),
            ProcessingStep(
                step_name="generate_answer",
                required=True,
                weight_in_confidence=0.15,
                fallback_action="return_extracted_text"
            )
        ],
        requires_rag=True,  # Helpful for equipment identification
        requires_vlm=True,
        max_tokens_for_answer=500,
        temperature=0.3,
        priority=2
    ),
    
    QueryIntent.COMPARE: QueryPlan(
        intent=QueryIntent.COMPARE,
        confidence=0.80,
        steps=[
            ProcessingStep(
                step_name="vlm_analyze",
                required=True,
                weight_in_confidence=0.30,
                fallback_action="use_ocr_only"
            ),
            ProcessingStep(
                step_name="rag_search_specs",
                required=True,
                weight_in_confidence=0.40,
                fallback_action="return_no_comparison"
            ),
            ProcessingStep(
                step_name="comparison_analysis",
                required=True,
                weight_in_confidence=0.25,
                fallback_action="return_simple_diff"
            ),
            ProcessingStep(
                step_name="generate_answer",
                required=True,
                weight_in_confidence=0.05,
                fallback_action=None
            )
        ],
        requires_rag=True,  # Essential for comparison
        requires_vlm=True,
        max_tokens_for_answer=700,
        temperature=0.2,
        priority=3
    ),
    
    QueryIntent.SUGGEST: QueryPlan(
        intent=QueryIntent.SUGGEST,
        confidence=0.75,
        steps=[
            ProcessingStep(
                step_name="vlm_analyze",
                required=True,
                weight_in_confidence=0.25,
                fallback_action="use_ocr_only"
            ),
            ProcessingStep(
                step_name="rag_search_vessels",
                required=True,
                weight_in_confidence=0.45,
                fallback_action="return_generic_suggestion"
            ),
            ProcessingStep(
                step_name="cross_reference_matches",
                required=True,
                weight_in_confidence=0.20,
                fallback_action="return_vlm_summary"
            ),
            ProcessingStep(
                step_name="generate_suggestions",
                required=True,
                weight_in_confidence=0.10,
                fallback_action="return_rag_matches"
            )
        ],
        requires_rag=True,  # Critical for suggestions
        requires_vlm=True,
        max_tokens_for_answer=800,
        temperature=0.4,
        priority=4
    ),
    
    QueryIntent.VALIDATE: QueryPlan(
        intent=QueryIntent.VALIDATE,
        confidence=0.85,
        steps=[
            ProcessingStep(
                step_name="vlm_analyze",
                required=True,
                weight_in_confidence=0.30,
                fallback_action="use_ocr_only"
            ),
            ProcessingStep(
                step_name="rag_search_validation",
                required=False,
                weight_in_confidence=0.25,
                fallback_action="skip_validation_ref"
            ),
            ProcessingStep(
                step_name="measurement_validation",
                required=True,
                weight_in_confidence=0.35,
                fallback_action="flag_for_review"
            ),
            ProcessingStep(
                step_name="generate_answer",
                required=True,
                weight_in_confidence=0.10,
                fallback_action=None
            )
        ],
        requires_rag=False,  # Optional for validation
        requires_vlm=True,
        max_tokens_for_answer=500,
        temperature=0.2,
        priority=5
    )
}


def get_query_plan(intent: QueryIntent) -> QueryPlan:
    """
    Get the execution plan for a given intent.
    
    Args:
        intent: The classified query intent
    
    Returns:
        QueryPlan with execution steps and parameters
    """
    return QUERY_PLANS.get(intent, QUERY_PLANS[QueryIntent.EXTRACT])


def route_query(query: str) -> QueryPlan:
    """
    Full query routing: classify intent and return execution plan.
    
    Args:
        query: User's natural language query
    
    Returns:
        QueryPlan ready for execution
    """
    intent = classify_intent(query)
    plan = get_query_plan(intent)
    
    logger.info(f"Routed query to intent: {intent.value}, priority: {plan.priority}")
    
    return plan


# ═══════════════════════════════════════════════════════════════
#  QUERY METRICS
# ═══════════════════════════════════════════════════════════════

class QueryMetrics(BaseModel):
    """Metrics for query processing."""
    total_queries: int = 0
    intent_distribution: Dict[str, int] = {}
    avg_classification_time_ms: float = 0.0
    llm_fallback_rate: float = 0.0


class QueryMetricsCollector:
    """Collects metrics on query routing performance."""
    
    def __init__(self):
        self.metrics = QueryMetrics()
        self._classification_times: List[float] = []
        self._llm_fallbacks: int = 0
    
    def record_classification(self, intent: QueryIntent, time_ms: float, used_llm: bool):
        """Record a classification event."""
        self.metrics.total_queries += 1
        intent_str = intent.value
        self.metrics.intent_distribution[intent_str] = self.metrics.intent_distribution.get(intent_str, 0) + 1
        
        self._classification_times.append(time_ms)
        self.metrics.avg_classification_time_ms = sum(self._classification_times) / len(self._classification_times)
        
        if used_llm:
            self._llm_fallbacks += 1
        
        self.metrics.llm_fallback_rate = self._llm_fallbacks / self.metrics.total_queries
    
    def get_metrics(self) -> QueryMetrics:
        """Get current metrics."""
        return self.metrics


# Global metrics collector
_metrics = QueryMetricsCollector()


def get_router_metrics() -> QueryMetrics:
    """Get query routing metrics."""
    return _metrics.get_metrics()


# ═══════════════════════════════════════════════════════════════
#  TEST BLOCK
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Drawing Query Intent Router - Phase 2")
    print("=" * 50)
    
    test_queries = [
        "extract all dimensions from this drawing",
        "what equipment is shown in the blueprint",
        "does this meet SOTR requirements",
        "is this useful for ICGS Sarthi advancement",
        "validate the measurements in this drawing",
        "what is the length of the hull section",
        "compare these specs with our standards",
        "should we adopt this design"
    ]
    
    print("\nTesting Intent Classification:")
    for query in test_queries:
        # Test fast classification
        fast_intent = classify_intent_fast(query)
        fast_result = fast_intent.value if fast_intent else "(fallback to LLM)"
        
        print(f"  Query: '{query}'")
        print(f"  → Fast: {fast_result}")
        print()
    
    print("\nQuery Plans Available:")
    for intent in QueryIntent:
        plan = get_query_plan(intent)
        print(f"  {intent.value.upper()}:")
        print(f"    Steps: {len(plan.steps)}")
        print(f"    Requires RAG: {plan.requires_rag}")
        print(f"    Max Tokens: {plan.max_tokens_for_answer}")
        print(f"    Priority: {plan.priority}")
        print()
    
    print("=" * 50)
    print("Intent Router Ready")
