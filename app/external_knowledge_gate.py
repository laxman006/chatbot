"""
External Knowledge Gate for Rule 3B Enforcement

This module implements the gate logic for controlled use of external platform documentation
as defined in SYSTEM_PROMPT Rule 3B. It ensures that external knowledge is only used when
all conditions are met, maintaining CloudFuze's authority boundary.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)

# ============================================================================
# SUPPORTED PLATFORMS CONFIGURATION
# ============================================================================

# Explicit list of platforms supported by CloudFuze
# If a platform is not in this list, it is treated as unsupported
CLOUDFUZE_SUPPORTED_PLATFORMS = [
    "google workspace",
    "google",
    "gmail",
    "google drive",
    "google chat",
    "google meet",
    "microsoft 365",
    "microsoft",
    "office 365",
    "outlook",
    "sharepoint",
    "onedrive",
    "teams",
    "microsoft teams",
    "slack",
    "box",
    "dropbox",
]

# Competitor tools that should NEVER be discussed
COMPETITOR_TOOLS = [
    "bittitan",
    "bit titan",
    "quest",
    "skykick",
    "sky kick",
    "mover",
    "sharegate",
    "share gate",
]

# Official documentation domains removed - not currently enforced

# Migration-relevant keywords that indicate Rule 3B might apply
MIGRATION_KEYWORDS = [
    "migration",
    "migrate",
    "prerequisite",
    "admin console",
    "admin setting",
    "oauth",
    "scope",
    "permission",
    "api limit",
    "api access",
    "data retention",
    "history rule",
    "migration error",
    "migration issue",
    "platform limit",
    "platform requirement",
]

# Platform-owned knowledge topics (allowed)
PLATFORM_OWNED_TOPICS = [
    "admin console",
    "admin setting",
    "permission scope",
    "oauth scope",
    "api access",
    "api limit",
    "platform limitation",
    "platform requirement",
]

# Topics that should be blocked (general usage, tutorials, UI walkthroughs)
BLOCKED_TOPICS = [
    "how to use",
    "how to log in",
    "step by step",
    "click here",
    "navigate to",
    "tutorial",
    "walkthrough",
    "user guide",
    "getting started",
    "personal use",
    "individual use",
]


class ExternalKnowledgeDecision(Enum):
    """Decision result from the external knowledge gate"""
    ALLOWED = "allowed"
    DENIED_UNSUPPORTED_PLATFORM = "denied_unsupported_platform"
    DENIED_NOT_MIGRATION_RELEVANT = "denied_not_migration_relevant"
    DENIED_COMPETITOR = "denied_competitor"
    DENIED_GENERAL_USAGE = "denied_general_usage"
    DENIED_UNCERTAINTY = "denied_uncertainty"
    DENIED_OUT_OF_SCOPE = "denied_out_of_scope"


def check_migration_relevance(query: str) -> bool:
    """
    Check if query is migration-relevant (Condition A).
    
    Returns True if query relates to:
    - migration prerequisites
    - admin console settings
    - API permissions or OAuth scopes
    - platform-imposed limits
    - data retention or history rules
    - errors returned during migration
    """
    query_lower = query.lower()
    
    # Check for migration-related keywords
    for keyword in MIGRATION_KEYWORDS:
        if keyword in query_lower:
            return True
    
    # Check for specific patterns
    patterns = [
        r"what.*scope.*need",
        r"what.*permission.*require",
        r"admin.*setting.*migration",
        r"platform.*limit.*migration",
        r"error.*migration",
        r"migration.*fail",
        r"migration.*error",
    ]
    
    for pattern in patterns:
        if re.search(pattern, query_lower):
            return True
    
    return False


def check_supported_platform(query: str, migration_relevant: bool = False) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Check if query mentions a supported platform (Condition B).
    Also handles competitor detection (consolidated here).
    
    Args:
        query: User's query string
        migration_relevant: Whether the query is migration-relevant (from Condition A)
    
    Returns:
        (is_supported, platform_name, denial_reason)
        - is_supported: True if platform is supported or implicit
        - platform_name: Name of platform or "implicit" if no platform mentioned but migration-relevant
        - denial_reason: "competitor" if competitor detected, None otherwise
    """
    query_lower = query.lower()
    
    # Check for competitor tools first (explicit deny)
    for competitor in COMPETITOR_TOOLS:
        if competitor in query_lower:
            return (False, competitor, "competitor")
    
    # Check for supported platforms
    for platform in CLOUDFUZE_SUPPORTED_PLATFORMS:
        if platform in query_lower:
            return (True, platform, None)
    
    # If no platform is mentioned:
    # - If migration-relevant and no competitor: treat as implicit supported
    # - Otherwise: unsupported
    if migration_relevant:
        return (True, "implicit", None)
    else:
        return (False, None, None)


def check_platform_owned_knowledge(query: str) -> bool:
    """
    Check if query is about platform-owned knowledge (Condition C).
    
    Returns True if query is about:
    - Admin console requirements
    - Permission scopes
    - API access rules
    - Platform limitations that affect migration
    
    Returns False if query is about:
    - General platform usage
    - End-user features
    """
    query_lower = query.lower()
    
    # Check for blocked topics (general usage, tutorials)
    for blocked in BLOCKED_TOPICS:
        if blocked in query_lower:
            return False
    
    # Check for allowed platform-owned topics
    for topic in PLATFORM_OWNED_TOPICS:
        if topic in query_lower:
            return True
    
    # If query mentions admin/scope/permission/API in migration context, allow
    admin_patterns = [
        r"admin.*(setting|console|config)",
        r"(oauth|permission).*scope",
        r"api.*(access|limit|permission)",
        r"platform.*limit",
    ]
    
    for pattern in admin_patterns:
        if re.search(pattern, query_lower) and check_migration_relevance(query):
            return True
    
    return False


def evaluate_external_knowledge_gate(query: str) -> Tuple[ExternalKnowledgeDecision, Dict]:
    """
    Main gate function that evaluates all Rule 3B conditions.
    
    Args:
        query: User's query string
        
    Returns:
        (decision, metadata)
        - decision: ExternalKnowledgeDecision enum
        - metadata: Dict with details about the evaluation
    """
    metadata = {
        "query": query,
        "migration_relevant": False,
        "platform_detected": None,
        "platform_supported": False,
        "platform_owned": False,
        "uncertainty": False,
        "rule_3b_evaluated": True,
        "decision": None,
    }
    
    # Condition A: Migration Relevance
    migration_relevant = check_migration_relevance(query)
    metadata["migration_relevant"] = migration_relevant
    
    if not migration_relevant:
        decision = ExternalKnowledgeDecision.DENIED_NOT_MIGRATION_RELEVANT
        metadata["decision"] = decision.value
        logger.info(f"[3B GATE] Denied: Not migration-relevant. Query: {query[:100]}")
        return (decision, metadata)
    
    # Condition B: Supported Platforms (includes competitor detection)
    platform_supported, platform_name, denial_reason = check_supported_platform(query, migration_relevant=migration_relevant)
    metadata["platform_detected"] = platform_name
    metadata["platform_supported"] = platform_supported
    
    # Handle competitor denial (consolidated in check_supported_platform)
    if denial_reason == "competitor":
        decision = ExternalKnowledgeDecision.DENIED_COMPETITOR
        metadata["decision"] = decision.value
        logger.warning(f"[3B GATE] Denied: Competitor tool detected. Query: {query[:100]}")
        return (decision, metadata)
    
    if not platform_supported:
        decision = ExternalKnowledgeDecision.DENIED_UNSUPPORTED_PLATFORM
        metadata["decision"] = decision.value
        logger.info(f"[3B GATE] Denied: Unsupported platform or no platform detected. Query: {query[:100]}")
        return (decision, metadata)
    
    # Condition C: Platform-Owned Knowledge
    platform_owned = check_platform_owned_knowledge(query)
    metadata["platform_owned"] = platform_owned
    
    if not platform_owned:
        decision = ExternalKnowledgeDecision.DENIED_GENERAL_USAGE
        metadata["decision"] = decision.value
        logger.info(f"[3B GATE] Denied: Not platform-owned knowledge (likely general usage). Query: {query[:100]}")
        return (decision, metadata)
    
    # Conditions D, E, F are enforced by the LLM via SYSTEM_PROMPT
    # But we can do a final uncertainty check here
    
    # Uncertainty check: If query is ambiguous or unclear, default-deny
    if len(query.strip()) < 10 or query.count("?") > 2:
        metadata["uncertainty"] = True
        decision = ExternalKnowledgeDecision.DENIED_UNCERTAINTY
        metadata["decision"] = decision.value
        logger.info(f"[3B GATE] Denied: Uncertainty detected (query too short/ambiguous). Query: {query[:100]}")
        return (decision, metadata)
    
    # All conditions met - allow external knowledge
    decision = ExternalKnowledgeDecision.ALLOWED
    metadata["decision"] = decision.value
    
    # Classify the topic for template routing
    topic_classified = classify_external_topic(query)
    metadata["topic_classified"] = topic_classified
    
    logger.info(f"[3B GATE] ALLOWED: All conditions met. Platform: {platform_name}, Topic: {topic_classified}, Query: {query[:100]}")
    return (decision, metadata)


def classify_external_topic(query: str) -> str:
    """
    Classify the type of external knowledge topic for template routing.
    
    Returns:
        - "oauth_scope": OAuth scopes/permissions
        - "admin_setting": Admin console settings
        - "api_limit": API limits/quotas
        - "retention_rule": Data retention/history rules
        - "migration_error": Migration errors/issues
        - "generic": Other external knowledge
    """
    query_lower = query.lower()
    
    # OAuth scope patterns
    oauth_patterns = [
        r"oauth.*scope",
        r"scope.*oauth",
        r"permission.*scope",
        r"scope.*permission",
        r"api.*scope",
        r"scope.*required",
        r"grant.*permission",
        r"authorization.*scope",
    ]
    for pattern in oauth_patterns:
        if re.search(pattern, query_lower):
            return "oauth_scope"
    
    # Admin setting patterns
    admin_patterns = [
        r"admin.*setting",
        r"admin.*console",
        r"admin.*config",
        r"enable.*admin",
        r"admin.*enable",
        r"setting.*admin",
        r"console.*setting",
    ]
    for pattern in admin_patterns:
        if re.search(pattern, query_lower):
            return "admin_setting"
    
    # API limit patterns
    api_limit_patterns = [
        r"api.*limit",
        r"limit.*api",
        r"api.*quota",
        r"quota.*api",
        r"rate.*limit",
        r"throttle",
        r"api.*throttle",
    ]
    for pattern in api_limit_patterns:
        if re.search(pattern, query_lower):
            return "api_limit"
    
    # Retention rule patterns
    retention_patterns = [
        r"retention",
        r"history.*rule",
        r"data.*retention",
        r"retention.*policy",
        r"message.*history",
        r"chat.*history",
    ]
    for pattern in retention_patterns:
        if re.search(pattern, query_lower):
            return "retention_rule"
    
    # Migration error patterns
    error_patterns = [
        r"migration.*error",
        r"error.*migration",
        r"migration.*fail",
        r"fail.*migration",
        r"migration.*issue",
        r"issue.*migration",
        r"migration.*problem",
    ]
    for pattern in error_patterns:
        if re.search(pattern, query_lower):
            return "migration_error"
    
    # Default to generic
    return "generic"


def build_rule_3b_metadata(
    decision: ExternalKnowledgeDecision,
    gate_metadata: Dict,
    prompt_mode: str,
    endpoint: str
) -> Dict:
    """
    Build normalized Rule 3B metadata for Langfuse logging.
    
    Args:
        decision: The Rule 3B decision
        gate_metadata: Metadata from evaluate_external_knowledge_gate()
        prompt_mode: One of "cf_only", "cf_external", "refusal"
        endpoint: The API endpoint ("/chat" or "/chat/stream")
    
    Returns:
        Normalized metadata dict with required keys
    """
    return {
        "rule_3b_decision": decision.value if decision else None,
        "prompt_mode": prompt_mode,
        "platform_detected": gate_metadata.get("platform_detected"),
        "topic_classified": gate_metadata.get("topic_classified"),
        "endpoint": endpoint,
    }


def get_refusal_message(decision: ExternalKnowledgeDecision) -> str:
    """
    Get a consistent refusal message based on the decision.
    
    This ensures consistent UX when external knowledge is denied.
    Messages are scope-based and non-explanatory.
    """
    if decision == ExternalKnowledgeDecision.DENIED_COMPETITOR:
        return "I can help with CloudFuze migration prerequisites and supported platform configurations, but this topic is outside that scope."
    
    if decision == ExternalKnowledgeDecision.DENIED_UNSUPPORTED_PLATFORM:
        return "I can help with CloudFuze migration prerequisites and supported platform configurations, but this platform is not supported."
    
    if decision == ExternalKnowledgeDecision.DENIED_NOT_MIGRATION_RELEVANT:
        return "I can help with CloudFuze migration prerequisites and supported platform configurations, but this topic is not migration-related."
    
    if decision == ExternalKnowledgeDecision.DENIED_GENERAL_USAGE:
        return "I can help with CloudFuze migration prerequisites and supported platform configurations, but this topic is outside that scope."
    
    if decision == ExternalKnowledgeDecision.DENIED_UNCERTAINTY:
        return "I can help with CloudFuze migration prerequisites and supported platform configurations, but this topic is outside that scope."
    
    # Default refusal
    return "I can help with CloudFuze migration prerequisites and supported platform configurations, but this topic is outside that scope."

