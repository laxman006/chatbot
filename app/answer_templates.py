"""
Answer Templates for External Knowledge Responses

This module provides structured templates for responses that use external platform
documentation, ensuring consistency and policy compliance (Rule 3B).
"""

from typing import Dict, Optional


def format_admin_setting_response(
    setting_name: str,
    platform_name: str,
    why_required: str,
    cloudfuze_impact: str,
    customer_configurable: bool = True
) -> str:
    """
    Template for admin console setting responses.
    
    Args:
        setting_name: Name of the admin setting
        platform_name: Platform name (e.g., "Google Workspace")
        why_required: Why the platform requires this setting
        cloudfuze_impact: How this affects CloudFuze migration
        customer_configurable: Whether customer must configure this (default: True)
    """
    customer_note = ""
    if customer_configurable:
        customer_note = "\n\n**Note:** This is a customer-side configuration that must be enabled in the platform admin console. CloudFuze cannot override this requirement."
    
    return f"""This is based on official platform documentation and applies only in the context of CloudFuze migrations.

**Required Setting:** {setting_name}

**Platform Requirement:** {platform_name} requires this setting because {why_required}.

**Impact on CloudFuze Migration:** {cloudfuze_impact}{customer_note}"""


def format_oauth_scope_response(
    scope_name: str,
    platform_name: str,
    why_required: str,
    cloudfuze_impact: str,
    customer_configurable: bool = True
) -> str:
    """
    Template for OAuth scope/permission responses.
    
    Args:
        scope_name: Name of the OAuth scope or permission
        platform_name: Platform name
        why_required: Why the platform requires this scope
        cloudfuze_impact: How this affects CloudFuze migration
        customer_configurable: Whether customer must grant this permission
    """
    customer_note = ""
    if customer_configurable:
        customer_note = "\n\n**Note:** This permission must be granted by the customer during the OAuth authorization process. CloudFuze cannot bypass this requirement."
    
    return f"""This is based on official platform documentation and applies only in the context of CloudFuze migrations.

**Required Scope/Permission:** {scope_name}

**Platform Requirement:** {platform_name} requires this scope because {why_required}.

**Impact on CloudFuze Migration:** {cloudfuze_impact}{customer_note}"""


def format_api_limit_response(
    limit_description: str,
    platform_name: str,
    limit_value: Optional[str],
    why_exists: str,
    cloudfuze_impact: str,
    workaround: Optional[str] = None
) -> str:
    """
    Template for API limit responses.
    
    Args:
        limit_description: Description of the API limit
        platform_name: Platform name
        limit_value: Specific limit value if known (e.g., "1000 requests/hour")
        why_exists: Why the platform enforces this limit
        cloudfuze_impact: How this affects CloudFuze migration
        workaround: Optional workaround if available
    """
    limit_info = f"**Limit:** {limit_value}\n\n" if limit_value else ""
    workaround_note = f"\n\n**Workaround:** {workaround}" if workaround else ""
    
    return f"""This is based on official platform documentation and applies only in the context of CloudFuze migrations.

**API Limit:** {limit_description}
{limit_info}**Platform Enforcement:** {platform_name} enforces this limit because {why_exists}.

**Impact on CloudFuze Migration:** {cloudfuze_impact}{workaround_note}

**Note:** This is a platform-imposed limitation that CloudFuze must work within. Migration timing or batching may be adjusted to accommodate this limit."""


def format_data_retention_response(
    retention_rule: str,
    platform_name: str,
    why_exists: str,
    cloudfuze_impact: str,
    migration_implication: str
) -> str:
    """
    Template for data retention/history rule responses.
    
    Args:
        retention_rule: Description of the retention rule
        platform_name: Platform name
        why_exists: Why the platform has this rule
        cloudfuze_impact: How this affects CloudFuze migration
        migration_implication: Specific implication for migration
    """
    return f"""This is based on official platform documentation and applies only in the context of CloudFuze migrations.

**Retention Rule:** {retention_rule}

**Platform Policy:** {platform_name} enforces this rule because {why_exists}.

**Impact on CloudFuze Migration:** {cloudfuze_impact}

**Migration Implication:** {migration_implication}

**Note:** This is a platform policy that cannot be overridden. CloudFuze migrations will respect these retention rules."""


def format_migration_error_response(
    error_description: str,
    platform_name: str,
    root_cause: str,
    cloudfuze_impact: str,
    resolution: str
) -> str:
    """
    Template for migration error responses based on platform documentation.
    
    Args:
        error_description: Description of the error
        platform_name: Platform name
        root_cause: Root cause from platform documentation
        cloudfuze_impact: How this affects CloudFuze migration
        resolution: Recommended resolution
    """
    return f"""This is based on official platform documentation and applies only in the context of CloudFuze migrations.

**Error:** {error_description}

**Platform Root Cause:** According to {platform_name} documentation, this error occurs because {root_cause}.

**Impact on CloudFuze Migration:** {cloudfuze_impact}

**Resolution:** {resolution}"""


def format_generic_external_knowledge_response(
    topic: str,
    platform_name: str,
    information: str,
    cloudfuze_impact: str
) -> str:
    """
    Generic template for other external knowledge responses.
    
    Args:
        topic: Topic being discussed
        platform_name: Platform name
        information: Information from official documentation
        cloudfuze_impact: How this affects CloudFuze migration
    """
    return f"""This is based on official platform documentation and applies only in the context of CloudFuze migrations.

**Topic:** {topic}

**Platform Information:** According to {platform_name} documentation, {information}.

**Impact on CloudFuze Migration:** {cloudfuze_impact}"""

