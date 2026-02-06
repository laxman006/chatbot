# -*- coding: utf-8 -*-
"""
Response Formatter for Cloud API Research

Formats research results into comprehensive markdown responses with documentation links.
"""

from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


def format_cloud_research_markdown(research_data: Dict, cloud_name: str) -> str:
    """
    Format cloud research data into the REQUIRED Cloud API Research contract.
    
    Args:
        research_data: Complete research results
        cloud_name: Name of the cloud
        
    Returns:
        Formatted markdown string
    """
    confidence = float(research_data.get("confidence_score") or 0.0)
    integration_mode = research_data.get("integration_mode") or "NOT_SUPPORTED"

    core_ops = research_data.get("core_operations") or {}
    extended_ops = research_data.get("extended_operations") or {}
    auth_info = research_data.get("authentication") or {}
    doc_links = research_data.get("documentation") or {}

    # Confidence gates (suppress content, not structure)
    suppress_examples_and_checklists = confidence < 0.7
    suppress_endpoint_tables = confidence < 0.6
    minimal_sections_only = confidence < 0.55

    # Contract: capability-first, no "Unknown"
    capabilities = _compute_supported_capabilities(core_ops, extended_ops, integration_mode)
    out_of_scope = _compute_out_of_scope(core_ops, extended_ops, integration_mode, confidence)

    # INVARIANT: NOT_SUPPORTED → no endpoints rendered, no capability may be "Supported"
    if integration_mode == "NOT_SUPPORTED":
        capabilities = _capabilities_for_not_supported()

    sections: List[str] = []
    sections.append(f"# Cloud API Integration Assessment: {cloud_name}")
    sections.append("")

    # 1. Overview
    sections.append("## Overview")
    sections.append("")
    sections.extend(_render_overview(cloud_name, integration_mode, capabilities, confidence))
    sections.append("")

    # 2. Problems Solved
    sections.append("## Problems Solved")
    sections.append("")
    if minimal_sections_only:
        sections.append("Out of scope.")
    else:
        sections.extend(_render_problems_solved(capabilities))
    sections.append("")

    # 3. Supported Capabilities
    sections.append("## Supported Capabilities")
    sections.append("")
    sections.extend(_render_capabilities(capabilities))
    sections.append("")

    # 4. Out of Scope
    sections.append("## Out of Scope")
    sections.append("")
    sections.extend(_render_out_of_scope(out_of_scope))
    sections.append("")

    # 5. Authentication
    sections.append("## Authentication")
    sections.append("")
    if minimal_sections_only:
        sections.append("Out of scope.")
    else:
        sections.extend(_render_authentication(auth_info, doc_links, cloud_name))
    sections.append("")

    # 6. Explicit Endpoints (evidence only)
    sections.append("## Explicit Endpoints")
    sections.append("")
    # INVARIANT: NOT_SUPPORTED → no explicit endpoints may be rendered
    if integration_mode == "NOT_SUPPORTED":
        sections.append("Not supported.")
    elif minimal_sections_only or suppress_endpoint_tables:
        sections.append("Out of scope.")
    else:
        sections.extend(_render_explicit_endpoints(core_ops, extended_ops))
    sections.append("")

    # 7. Governance Workflows
    sections.append("## Governance Workflows")
    sections.append("")
    if minimal_sections_only or suppress_examples_and_checklists:
        sections.append("Out of scope.")
    else:
        sections.extend(_render_governance_workflows(capabilities, integration_mode))
    sections.append("")

    # 8. Recommendation
    sections.append("## Recommendation")
    sections.append("")
    if minimal_sections_only:
        sections.append(_render_recommendation_summary(integration_mode))
    else:
        sections.extend(_render_recommendation(integration_mode, capabilities))
    sections.append("")

    # 9. Authoritative Documentation (Informational)
    sections.append("## Authoritative Documentation (Informational)")
    sections.append("")
    authoritative_docs = research_data.get("authoritative_docs") or []
    sections.extend(_render_authoritative_documentation(authoritative_docs, cloud_name))
    sections.append("")

    markdown = "\n".join(sections).strip() + "\n"
    _contract_safety_assertions(markdown, core_ops, extended_ops, integration_mode, capabilities)
    return markdown


def _capabilities_for_not_supported() -> Dict[str, str]:
    """Invariant: NOT_SUPPORTED → no capability may be marked Supported."""
    return {
        "Integration Mode": "NOT_SUPPORTED",
        "User lifecycle (create/update/delete/suspend/restore)": "Not supported.",
        "User visibility (list/get)": "Not supported.",
        "Team/Group lifecycle (create/update/delete)": "Not supported.",
        "Team/Group visibility (list/get)": "Not supported.",
        "Membership management (add/remove members)": "Not supported.",
        "Membership visibility (list members)": "Not supported.",
        "Audit / activity logs": "Not supported.",
    }


def _contract_safety_assertions(
    markdown: str,
    core_ops: Dict,
    extended_ops: Dict,
    integration_mode: str = "",
    capabilities: Optional[Dict[str, str]] = None,
) -> None:
    """
    Final safety assertions (contract-enforced):
    - No rendered output may contain the string "Unknown"
    - No endpoint evidence with LLM provenance may be rendered
    - NOT_SUPPORTED → no endpoints rendered, no capability Supported
    - Any rendered endpoint must have vendor_docs_url provenance
    """
    if "Unknown" in markdown:
        raise AssertionError('Contract violation: rendered output contains "Unknown"')

    # NOT_SUPPORTED → no endpoint table may be present
    if integration_mode == "NOT_SUPPORTED" and "| Capability | Method | Endpoint | Docs |" in markdown:
        raise AssertionError("Contract violation: NOT_SUPPORTED must not render explicit endpoints table")

    # If any capability is Supported, integration_mode must NOT be NOT_SUPPORTED
    if capabilities:
        for key, val in capabilities.items():
            if key != "Integration Mode" and val == "Supported":
                if integration_mode == "NOT_SUPPORTED":
                    raise AssertionError(
                        "Contract violation: capability marked Supported but integration_mode is NOT_SUPPORTED"
                    )
                break

    # If endpoint table is present, no LLM provenance (iter_evidence already filters these and vendor_docs_url)
    if "| Capability | Method | Endpoint | Docs |" in markdown:
        evidence = _iter_evidence_operations(core_ops, extended_ops)
        for rec in evidence:
            validation_status = (rec.get("validation_status") or "").lower()
            evidence_source = (rec.get("evidence_source") or "").lower()
            page_source = (rec.get("page_source") or "").lower()
            if "llm" in validation_status or "llm" in evidence_source or "llm" in page_source:
                raise AssertionError("Contract violation: endpoint evidence with LLM provenance is renderable")
            if not (rec.get("vendor_docs_url") or rec.get("source_url")):
                raise AssertionError("Contract violation: rendered endpoint must have vendor_docs_url provenance")


def _compute_supported_capabilities(core_ops: Dict, extended_ops: Dict, integration_mode: str) -> Dict[str, str]:
    """
    Compute capability statuses (Supported / Limited / Not supported) without inference.
    Endpoints are evidence only; if operation not present, it is Not supported.
    """
    def _has(op: str) -> bool:
        return op in (core_ops or {}) and bool(core_ops[op])

    def _has_ext(op: str) -> bool:
        return op in (extended_ops or {}) and bool(extended_ops[op])

    # Identity lifecycle
    user_read = _has("getUsers") or _has("getUser")
    user_lifecycle = any(_has(op) for op in ["createUser", "updateUser", "deleteUser", "suspendUser", "restoreUser"])

    # Teams/groups + memberships
    group_read = _has("getGroups") or _has("getGroup")
    group_lifecycle = any(_has(op) for op in ["createGroup", "updateGroup", "deleteGroup"])
    membership_read = _has("getGroupMembers")
    membership_write = any(_has(op) for op in ["addUserToGroup", "removeUserFromGroup"])

    # Governance/audit (extended)
    audit = _has_ext("getAuditLogs") or _has_ext("getSecurityEvents")

    # Status values per docs/capability-contract.md
    def _status_supported() -> str:
        return "Supported"

    def _status_limited() -> str:
        return "Limited"

    def _status_not_supported() -> str:
        return "Not supported"

    caps: Dict[str, str] = {}

    # Integration mode as top-level capability signal
    caps["Integration Mode"] = integration_mode

    # User lifecycle
    if user_lifecycle:
        caps["User lifecycle (create/update/delete/suspend/restore)"] = _status_supported()
    elif user_read:
        caps["User lifecycle (create/update/delete/suspend/restore)"] = _status_not_supported()
        caps["User visibility (list/get)"] = _status_supported()
    else:
        caps["User lifecycle (create/update/delete/suspend/restore)"] = _status_not_supported()
        caps["User visibility (list/get)"] = _status_not_supported()

    # Teams / groups
    if group_lifecycle:
        caps["Team/Group lifecycle (create/update/delete)"] = _status_supported()
    elif group_read:
        caps["Team/Group lifecycle (create/update/delete)"] = _status_not_supported()
        caps["Team/Group visibility (list/get)"] = _status_supported()
    else:
        caps["Team/Group lifecycle (create/update/delete)"] = _status_not_supported()
        caps["Team/Group visibility (list/get)"] = _status_not_supported()

    # Memberships
    if membership_write:
        caps["Membership management (add/remove members)"] = _status_supported()
    elif membership_read:
        caps["Membership management (add/remove members)"] = _status_not_supported()
        caps["Membership visibility (list members)"] = _status_supported()
    else:
        caps["Membership management (add/remove members)"] = _status_not_supported()
        caps["Membership visibility (list members)"] = _status_not_supported()

    # Audit
    caps["Audit / activity logs"] = _status_supported() if audit else _status_not_supported()

    # Guardrail: if no identity or team-management APIs explicitly documented, mode must be NOT_SUPPORTED or VISIBILITY_ONLY
    has_identity_or_team = user_read or user_lifecycle or group_read or group_lifecycle or membership_read or membership_write
    if not has_identity_or_team and integration_mode not in ("NOT_SUPPORTED", "VISIBILITY_ONLY"):
        caps["Integration Mode"] = "NOT_SUPPORTED"

    return caps


def _compute_out_of_scope(core_ops: Dict, extended_ops: Dict, integration_mode: str, confidence: float) -> List[str]:
    """
    Out-of-scope items are explicit. No 'Unknown' allowed.
    """
    items: List[str] = []

    # If NOT_SUPPORTED or VISIBILITY_ONLY, user lifecycle is out of scope by definition
    if integration_mode in ("NOT_SUPPORTED", "VISIBILITY_ONLY"):
        items.append("User lifecycle automation (create/update/delete/suspend/restore): Not supported.")
        items.append("Team/Group lifecycle automation (create/update/delete): Not supported.")
        items.append("Membership automation (add/remove members): Not supported.")

    # Confidence-based suppression (content only; structure remains)
    if confidence < 0.7:
        items.append("Integration examples and checklists: Out of scope (confidence < 0.7).")
    if confidence < 0.6:
        items.append("Endpoint tables: Out of scope (confidence < 0.6).")

    # Always state evidence policy
    items.append("LLM-generated endpoints: Not supported (forbidden).")

    # If nothing else, keep at least one line
    if not items:
        items.append("No additional out-of-scope items identified.")

    return items


def _render_overview(cloud_name: str, integration_mode: str, capabilities: Dict[str, str], confidence: float) -> List[str]:
    lines: List[str] = []
    # Short, capability-first overview aligned to example intent.
    # Do not claim support beyond the computed capability statuses.
    supports_team = any(
        capabilities.get(k) == "Supported"
        for k in [
            "Team/Group visibility (list/get)",
            "Team/Group lifecycle (create/update/delete)",
            "Membership visibility (list members)",
            "Membership management (add/remove members)",
        ]
    )
    supports_user_lifecycle = capabilities.get("User lifecycle (create/update/delete/suspend/restore)") == "Supported"
    supports_audit = capabilities.get("Audit / activity logs") == "Supported"

    if integration_mode == "NOT_SUPPORTED":
        lines.append("Not supported.")
        return lines

    if supports_team and supports_audit and not supports_user_lifecycle:
        lines.append("Supports team governance and audit.")
        lines.append("Does not support user lifecycle.")
        return lines

    # Generic overview without new assumptions
    if supports_user_lifecycle:
        lines.append("Supports identity governance.")
    elif supports_team:
        lines.append("Supports team governance.")
    else:
        lines.append("Not supported.")

    if supports_audit:
        lines.append("Supports audit visibility.")

    return lines


def _render_problems_solved(capabilities: Dict[str, str]) -> List[str]:
    lines: List[str] = []
    # Keep minimal and non-assumptive
    if capabilities.get("Team/Group visibility (list/get)") == "Supported":
        lines.append("- Inventory teams/groups.")
    if capabilities.get("Membership visibility (list members)") == "Supported":
        lines.append("- Review group membership for governance.")
    if capabilities.get("Audit / activity logs") == "Supported":
        lines.append("- Support audit visibility for compliance.")
    if not lines:
        lines.append("Not supported.")
    return lines


def _render_capabilities(capabilities: Dict[str, str]) -> List[str]:
    lines: List[str] = []
    for name, status in capabilities.items():
        if name == "Integration Mode":
            lines.append(f"- **Integration Mode**: `{status}`")
        else:
            lines.append(f"- **{name}**: {status}")
    return lines


def _render_out_of_scope(items: List[str]) -> List[str]:
    return [f"- {item}" for item in items] if items else ["- Out of scope."]


def _render_authentication(auth_info: Dict, doc_links: Dict, cloud_name: str) -> List[str]:
    lines: List[str] = []
    auth_type = (auth_info.get("type") or "").strip()
    if auth_type.lower() == "unknown":
        auth_type = ""

    if auth_type:
        lines.append(f"- **Type**: {auth_type}")
    else:
        lines.append("- **Type**: Not supported (not explicitly documented).")

    doc_url = auth_info.get("documentation_url") or doc_links.get("authentication_guide") or doc_links.get("docs_home")
    if doc_url:
        lines.append(f"- **Docs**: [{cloud_name} authentication]({doc_url})")

    return lines


def _iter_evidence_operations(core_ops: Dict, extended_ops: Dict) -> List[Dict]:
    """
    Flatten operation evidence records and filter out anything that indicates LLM-derived evidence.
    """
    records: List[Dict] = []
    for op_name, op_list in (core_ops or {}).items():
        if isinstance(op_list, list):
            for rec in op_list:
                rec2 = dict(rec or {})
                rec2["_cloudfuze_operation"] = op_name
                records.append(rec2)
        elif isinstance(op_list, dict):
            rec2 = dict(op_list)
            rec2["_cloudfuze_operation"] = op_name
            records.append(rec2)

    for op_name, op_list in (extended_ops or {}).items():
        if isinstance(op_list, list):
            for rec in op_list:
                rec2 = dict(rec or {})
                rec2["_cloudfuze_operation"] = op_name
                records.append(rec2)
        elif isinstance(op_list, dict):
            rec2 = dict(op_list)
            rec2["_cloudfuze_operation"] = op_name
            records.append(rec2)

    filtered: List[Dict] = []
    for rec in records:
        validation_status = (rec.get("validation_status") or "").lower()
        evidence_source = (rec.get("evidence_source") or "").lower()
        page_source = (rec.get("page_source") or "").lower()

        # Hard filter: never render LLM-derived evidence
        if "llm" in validation_status or "llm" in evidence_source or "llm" in page_source:
            continue
        # Hard filter: only render endpoints with vendor_docs_url (or source_url) provenance
        if not (rec.get("vendor_docs_url") or rec.get("source_url")):
            continue

        filtered.append(rec)

    return filtered


def _render_explicit_endpoints(core_ops: Dict, extended_ops: Dict) -> List[str]:
    evidence = _iter_evidence_operations(core_ops, extended_ops)
    if not evidence:
        return ["Not supported."]

    lines: List[str] = []
    lines.append("| Capability | Method | Endpoint | Docs |")
    lines.append("|-----------|--------|----------|------|")
    for rec in evidence:
        cap = rec.get("_cloudfuze_operation", "")
        method = rec.get("method", "") or ""
        endpoint = rec.get("endpoint", "") or ""
        docs = rec.get("vendor_docs_url") or rec.get("source_url") or ""
        docs_cell = f"[link]({docs})" if docs else "Not supported."
        lines.append(f"| `{cap}` | `{method}` | `{endpoint}` | {docs_cell} |")

    return lines


def _render_governance_workflows(capabilities: Dict[str, str], integration_mode: str) -> List[str]:
    # No checklists; only brief statements about what is supported.
    if integration_mode in ("NOT_SUPPORTED",):
        return ["Not supported."]
    if integration_mode in ("VISIBILITY_ONLY",):
        return ["Read-only visibility workflows only."]
    if integration_mode in ("PARTIAL_GOVERNANCE",):
        return ["Team governance workflows are partially supported (no full user lifecycle)."]
    if integration_mode in ("FULL_IDENTITY_GOVERNANCE",):
        return ["Identity governance workflows are supported."]
    return ["Not supported."]


def _render_recommendation_summary(integration_mode: str) -> str:
    if integration_mode == "NOT_SUPPORTED":
        return "Not supported."
    if integration_mode == "VISIBILITY_ONLY":
        return "Visibility-only integration recommended."
    if integration_mode == "PARTIAL_GOVERNANCE":
        return "Partial governance integration recommended."
    if integration_mode == "FULL_IDENTITY_GOVERNANCE":
        return "Full identity governance integration recommended."
    return "Not supported."


def _render_recommendation(integration_mode: str, capabilities: Dict[str, str]) -> List[str]:
    return [_render_recommendation_summary(integration_mode)]


def _render_authoritative_documentation(authoritative_docs: List[str], cloud_name: str) -> List[str]:
    """
    Render authoritative documentation links (informational only).
    These links are provided for reference and do NOT imply verified API support.
    Works uniformly for ALL clouds, including NOT_SUPPORTED cases.
    """
    lines: List[str] = []
    
    # Disclaimer (mandatory)
    lines.append("The following links point to official vendor documentation.")
    lines.append("They are provided for reference only and do not imply verified")
    lines.append("API support under this assessment.")
    lines.append("")
    
    if not authoritative_docs:
        lines.append("No official documentation URLs were discovered for this cloud.")
        return lines
    
    lines.append("**Official Documentation Links:**")
    lines.append("")
    for url in authoritative_docs:
        if url and url.strip():
            # Extract a readable title from URL if possible
            title = url
            try:
                from urllib.parse import urlparse
                parsed = urlparse(url)
                if parsed.path:
                    # Use path segment as title hint
                    path_parts = [p for p in parsed.path.split("/") if p]
                    if path_parts:
                        title = path_parts[-1].replace("-", " ").replace("_", " ").title()
                    else:
                        title = f"{cloud_name} API Documentation"
                else:
                    title = f"{cloud_name} API Documentation"
            except Exception:
                title = f"{cloud_name} API Documentation"
            lines.append(f"- [{title}]({url})")
    
    return lines


def _format_integration_quickstart(research_data: Dict, cloud_name: str) -> List[str]:
    """Format Integration Quickstart section with base URL and essential details"""
    lines = []
    
    lines.append("## Integration Quickstart")
    lines.append("")
    
    # Base URL
    base_url = research_data.get("base_url")
    if base_url:
        lines.append(f"**Base URL:** `{base_url}`")
        lines.append("")
    else:
        # Handle missing base URL gracefully with explanation
        lines.append("**Base URL:** ⚠️ *Requires tenant-specific identifier*")
        lines.append("")
        lines.append("This cloud uses tenant-specific base URLs. Check documentation for:")
        lines.append("- Workspace ID")
        lines.append("- Tenant ID")
        lines.append("- Organization domain")
        lines.append("- Region-specific endpoint")
        lines.append("")
        lines.append("**Status:** Partial - Base URL configuration required for integration")
        lines.append("")
    
    # Authentication Type
    auth_info = research_data.get("authentication", {})
    auth_type = auth_info.get("type", "Unknown")
    
    if auth_type != "Unknown":
        lines.append(f"**Authentication:** {auth_type}")
    else:
        lines.append("**Authentication:** *(Check documentation)*")
    lines.append("")
    
    # Required Headers
    lines.append("**Required Headers:**")
    if "oauth" in auth_type.lower():
        lines.append("```")
        lines.append("Authorization: Bearer {access_token}")
        lines.append("Content-Type: application/json")
        lines.append("```")
    elif "api" in auth_type.lower() and "key" in auth_type.lower():
        lines.append("```")
        lines.append("Authorization: Bearer {api_key}")
        lines.append("Content-Type: application/json")
        lines.append("```")
    else:
        lines.append("```")
        lines.append("Authorization: (See authentication section)")
        lines.append("Content-Type: application/json")
        lines.append("```")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    
    return lines


def _format_authentication_setup(research_data: Dict, cloud_name: str) -> List[str]:
    """Format detailed authentication setup section with OAuth examples"""
    lines = []
    
    auth_info = research_data.get("authentication", {})
    auth_type = auth_info.get("type", "Unknown")
    doc_links = research_data.get("documentation", {})
    
    lines.append("## Authentication Setup")
    lines.append("")
    
    if "oauth" in auth_type.lower():
        lines.append("### OAuth 2.0 Configuration")
        lines.append("")
        
        # OAuth Endpoints
        token_endpoint = auth_info.get("token_endpoint")
        auth_endpoint = auth_info.get("authorization_endpoint")
        
        if token_endpoint:
            lines.append(f"**Token Endpoint:**")
            lines.append(f"```")
            lines.append(f"{token_endpoint}")
            lines.append(f"```")
            lines.append("")
        
        if auth_endpoint:
            lines.append(f"**Authorization Endpoint:**")
            lines.append(f"```")
            lines.append(f"{auth_endpoint}")
            lines.append(f"```")
            lines.append("")
        
        # Grant Types
        grant_types = auth_info.get("grant_types", [])
        if grant_types:
            lines.append(f"**Grant Types:** {', '.join(grant_types)}")
            lines.append("")
        
        # Scopes
        scopes = auth_info.get("scopes", [])
        if scopes:
            lines.append("**Required Scopes:**")
            for scope in scopes[:10]:  # Show first 10 scopes
                lines.append(f"- `{scope}`")
            if len(scopes) > 10:
                lines.append(f"- ... and {len(scopes) - 10} more")
            lines.append("")
        
        # Admin Consent
        admin_consent = auth_info.get("admin_consent_required", False)
        lines.append(f"**Admin Consent Required:** {'Yes' if admin_consent else 'No'}")
        lines.append("")
        
        # Example: Get Access Token (Client Credentials)
        if token_endpoint:
            lines.append("### Example: Get Access Token (Client Credentials)")
            lines.append("")
            lines.append("```bash")
            lines.append(f"curl -X POST {token_endpoint} \\")
            lines.append("  -H \"Content-Type: application/x-www-form-urlencoded\" \\")
            lines.append("  -d \"grant_type=client_credentials\" \\")
            lines.append("  -d \"client_id=YOUR_CLIENT_ID\" \\")
            lines.append("  -d \"client_secret=YOUR_CLIENT_SECRET\"")
            if scopes:
                lines.append(f"  -d \"scope={' '.join(scopes[:3])}\"")
            lines.append("```")
            lines.append("")
            
            lines.append("**Response:**")
            lines.append("```json")
            lines.append("{")
            lines.append("  \"access_token\": \"eyJhbGc...\",")
            lines.append("  \"token_type\": \"Bearer\",")
            lines.append("  \"expires_in\": 3600")
            lines.append("}")
            lines.append("```")
            lines.append("")
        
        # Documentation link
        if doc_links.get("authentication_guide"):
            lines.append(f"**Full Documentation:** [Authentication Guide]({doc_links['authentication_guide']})")
            lines.append("")
    
    elif auth_type != "Unknown":
        lines.append(f"**Authentication Type:** {auth_type}")
        lines.append("")
        lines.append(f"*(Note: {cloud_name} uses {auth_type} instead of OAuth 2.0)*")
        lines.append("")
        if doc_links.get("authentication_guide"):
            lines.append(f"**Documentation:** [Authentication Guide]({doc_links['authentication_guide']})")
            lines.append("")
    else:
        lines.append("**Authentication method not automatically determined.**")
        lines.append("")
        if doc_links.get("authentication_guide") or doc_links.get("docs_home"):
            lines.append(f"Please check the [official documentation]({doc_links.get('authentication_guide', doc_links.get('docs_home', ''))}) for authentication details.")
            lines.append("")
    
    lines.append("---")
    lines.append("")
    
    return lines


def _format_operation(operation_name: str, operation_data: Dict, base_url: str = "") -> List[str]:
    """
    Format a single operation into markdown with comprehensive integration details.
    
    Args:
        operation_name: CloudFuze operation name
        operation_data: Operation details
        base_url: API base URL
        
    Returns:
        List of markdown lines
    """
    lines = []
    
    # Operation header
    lines.append(f"#### {operation_name}")
    lines.append("")
    
    # Method and endpoint
    method = operation_data.get("method", "")
    endpoint = operation_data.get("endpoint", "")
    
    if method and endpoint:
        lines.append(f"**Method:** `{method}`")
        lines.append(f"**Endpoint:** `{endpoint}`")
        
        # Show full URL if base URL available
        if base_url:
            full_url = f"{base_url.rstrip('/')}{endpoint}"
            lines.append(f"**Full URL:** `{full_url}`")
        
        lines.append("")
    
    # Description
    description = operation_data.get("description", "")
    if description:
        lines.append(f"**Description:** {description}")
        lines.append("")
    
    # Example curl command
    if method and endpoint:
        lines.append("**Example Request:**")
        lines.append("```bash")
        
        if base_url:
            full_url = f"{base_url.rstrip('/')}{endpoint}"
        else:
            full_url = f"{{BASE_URL}}{endpoint}"
        
        lines.append(f"curl -X {method} {full_url} \\")
        lines.append("  -H \"Authorization: Bearer {{access_token}}\" \\")
        lines.append("  -H \"Content-Type: application/json\"")
        
        # Add request body for POST/PUT/PATCH
        if method in ["POST", "PUT", "PATCH"]:
            lines.append("  -d '{")
            if "user" in operation_name.lower():
                lines.append("    \"email\": \"user@example.com\",")
                lines.append("    \"name\": \"John Doe\"")
            elif "group" in operation_name.lower():
                lines.append("    \"name\": \"Team Name\"")
            lines.append("  }'")
        
        lines.append("```")
        lines.append("")
        
        # Add response body examples
        lines.append("**Example Response:**")
        lines.append("```json")
        
        # Generate appropriate response based on operation type
        if "getUsers" in operation_name or "listUsers" in operation_name:
            # List users response
            lines.append("{")
            lines.append("  \"entries\": [")
            lines.append("    {")
            lines.append("      \"id\": \"12345\",")
            lines.append("      \"type\": \"user\",")
            lines.append("      \"name\": \"John Doe\",")
            lines.append("      \"email\": \"john.doe@example.com\",")
            lines.append("      \"status\": \"active\"")
            lines.append("    },")
            lines.append("    {")
            lines.append("      \"id\": \"67890\",")
            lines.append("      \"type\": \"user\",")
            lines.append("      \"name\": \"Jane Smith\",")
            lines.append("      \"email\": \"jane.smith@example.com\",")
            lines.append("      \"status\": \"active\"")
            lines.append("    }")
            lines.append("  ],")
            lines.append("  \"total_count\": 2")
            lines.append("}")
        
        elif "getUser" in operation_name and "getUsers" not in operation_name:
            # Single user response
            lines.append("{")
            lines.append("  \"id\": \"12345\",")
            lines.append("  \"type\": \"user\",")
            lines.append("  \"name\": \"John Doe\",")
            lines.append("  \"email\": \"john.doe@example.com\",")
            lines.append("  \"status\": \"active\",")
            lines.append("  \"created_at\": \"2023-01-15T10:30:00Z\",")
            lines.append("  \"modified_at\": \"2023-12-20T14:45:00Z\"")
            lines.append("}")
        
        elif "createUser" in operation_name:
            # Create user response (returns created user)
            lines.append("{")
            lines.append("  \"id\": \"12345\",")
            lines.append("  \"type\": \"user\",")
            lines.append("  \"name\": \"John Doe\",")
            lines.append("  \"email\": \"user@example.com\",")
            lines.append("  \"status\": \"active\",")
            lines.append("  \"created_at\": \"2024-01-30T10:30:00Z\"")
            lines.append("}")
        
        elif "updateUser" in operation_name:
            # Update user response (returns updated user)
            lines.append("{")
            lines.append("  \"id\": \"12345\",")
            lines.append("  \"type\": \"user\",")
            lines.append("  \"name\": \"John Doe\",")
            lines.append("  \"email\": \"user@example.com\",")
            lines.append("  \"status\": \"active\",")
            lines.append("  \"modified_at\": \"2024-01-30T15:20:00Z\"")
            lines.append("}")
        
        elif "deleteUser" in operation_name or "removeUser" in operation_name:
            # Delete user response (typically 204 No Content or success message)
            lines.append("{")
            lines.append("  \"message\": \"User successfully deleted\",")
            lines.append("  \"id\": \"12345\"")
            lines.append("}")
        
        elif "getGroups" in operation_name or "listGroups" in operation_name:
            # List groups response
            lines.append("{")
            lines.append("  \"entries\": [")
            lines.append("    {")
            lines.append("      \"id\": \"57645\",")
            lines.append("      \"type\": \"group\",")
            lines.append("      \"name\": \"Engineering Team\",")
            lines.append("      \"created_at\": \"2023-05-10T09:00:00Z\"")
            lines.append("    },")
            lines.append("    {")
            lines.append("      \"id\": \"78901\",")
            lines.append("      \"type\": \"group\",")
            lines.append("      \"name\": \"Marketing Team\",")
            lines.append("      \"created_at\": \"2023-06-15T11:30:00Z\"")
            lines.append("    }")
            lines.append("  ],")
            lines.append("  \"total_count\": 2")
            lines.append("}")
        
        elif "getGroupMembers" in operation_name or "listGroupMembers" in operation_name:
            # List group members response
            lines.append("{")
            lines.append("  \"entries\": [")
            lines.append("    {")
            lines.append("      \"id\": \"434534\",")
            lines.append("      \"type\": \"group_membership\",")
            lines.append("      \"user\": {")
            lines.append("        \"id\": \"12345\",")
            lines.append("        \"name\": \"John Doe\",")
            lines.append("        \"email\": \"john.doe@example.com\"")
            lines.append("      },")
            lines.append("      \"group\": {")
            lines.append("        \"id\": \"57645\",")
            lines.append("        \"name\": \"Engineering Team\"")
            lines.append("      },")
            lines.append("      \"role\": \"member\"")
            lines.append("    }")
            lines.append("  ],")
            lines.append("  \"total_count\": 1")
            lines.append("}")
        
        elif "addUserToGroup" in operation_name or "addMember" in operation_name:
            # Add user to group response
            lines.append("{")
            lines.append("  \"id\": \"434534\",")
            lines.append("  \"type\": \"group_membership\",")
            lines.append("  \"user\": {")
            lines.append("    \"id\": \"12345\",")
            lines.append("    \"name\": \"John Doe\"")
            lines.append("  },")
            lines.append("  \"group\": {")
            lines.append("    \"id\": \"57645\",")
            lines.append("    \"name\": \"Engineering Team\"")
            lines.append("  },")
            lines.append("  \"role\": \"member\",")
            lines.append("  \"created_at\": \"2024-01-30T16:00:00Z\"")
            lines.append("}")
        
        elif "removeUserFromGroup" in operation_name or "removeMember" in operation_name:
            # Remove user from group response
            lines.append("{")
            lines.append("  \"message\": \"User successfully removed from group\"")
            lines.append("}")
        
        elif "createGroup" in operation_name:
            # Create group response
            lines.append("{")
            lines.append("  \"id\": \"57645\",")
            lines.append("  \"type\": \"group\",")
            lines.append("  \"name\": \"Team Name\",")
            lines.append("  \"created_at\": \"2024-01-30T10:30:00Z\"")
            lines.append("}")
        
        else:
            # Generic success response
            lines.append("{")
            lines.append("  \"success\": true,")
            lines.append("  \"data\": {")
            lines.append("    \"id\": \"12345\",")
            lines.append("    \"status\": \"completed\"")
            lines.append("  }")
            lines.append("}")
        
        lines.append("```")
        lines.append("")
    
    # Documentation link
    docs_url = operation_data.get("vendor_docs_url", "")
    if docs_url:
        lines.append(f"**Documentation:** [View Official Docs]({docs_url})")
        lines.append("")
    
    lines.append("---")
    lines.append("")
    
    return lines


def _format_all_endpoints_table(all_endpoints: List[Dict], base_url: str = "") -> List[str]:
    """
    Format complete table of ALL discovered endpoints (not just mapped ones).
    Provides comprehensive reference for integration.
    """
    lines = []
    
    lines.append("## All Discovered Endpoints")
    lines.append("")
    lines.append(f"*Complete list of {len(all_endpoints)} API endpoints discovered (for reference)*")
    lines.append("")
    
    if not all_endpoints:
        lines.append("No endpoints discovered.")
        lines.append("")
        lines.append("---")
        lines.append("")
        return lines
    
    # Create table
    lines.append("| Method | Endpoint | Description |")
    lines.append("|--------|----------|-------------|")
    
    for ep in all_endpoints[:50]:  # Show first 50 endpoints
        method = ep.get("method", "")
        path = ep.get("path", "")
        desc = ep.get("description", "")[:60]  # Limit description length
        
        # Clean up description
        if desc:
            desc = desc.replace("|", "\\|").replace("\n", " ")
        else:
            desc = "-"
        
        lines.append(f"| `{method}` | `{path}` | {desc} |")
    
    if len(all_endpoints) > 50:
        lines.append(f"| ... | ... | *{len(all_endpoints) - 50} more endpoints not shown* |")
    
    lines.append("")
    
    # Add note about full list
    lines.append("")
    lines.append("---")
    lines.append("")
    
    return lines


def _format_integration_checklist(research_data: Dict, cloud_name: str) -> List[str]:
    """
    Format step-by-step integration checklist.
    """
    lines = []
    
    lines.append("## Integration Checklist")
    lines.append("")
    lines.append(f"*Step-by-step guide to integrate {cloud_name} into CloudFuze Manage*")
    lines.append("")
    
    auth_info = research_data.get("authentication", {})
    auth_type = auth_info.get("type", "Unknown")
    doc_links = research_data.get("documentation", {})
    base_url = research_data.get("base_url")
    core_ops = research_data.get("core_operations", {})
    
    step = 1
    
    # Step 1: Register OAuth app (if OAuth)
    if "oauth" in auth_type.lower():
        lines.append(f"### {step}. Register OAuth Application")
        lines.append("")
        if doc_links.get("docs_home"):
            lines.append(f"- Visit the [{cloud_name} Developer Console]({doc_links['docs_home']})")
        else:
            lines.append(f"- Visit the {cloud_name} Developer Console")
        lines.append("- Create a new OAuth application")
        lines.append("- Note your `client_id` and `client_secret`")
        lines.append("- Set redirect URI (for authorization code flow)")
        lines.append("")
        step += 1
    
    # Step 2: Request required scopes
    scopes = auth_info.get("scopes", [])
    if "oauth" in auth_type.lower() and scopes:
        lines.append(f"### {step}. Configure Required Scopes")
        lines.append("")
        lines.append("Request access to these scopes:")
        for scope in scopes[:5]:
            lines.append(f"- `{scope}`")
        if len(scopes) > 5:
            lines.append(f"- ... and {len(scopes) - 5} more (see Authentication section)")
        lines.append("")
        step += 1
    
    # Step 3: Implement authentication
    lines.append(f"### {step}. Implement Authentication")
    lines.append("")
    if "oauth" in auth_type.lower():
        lines.append("- Implement OAuth 2.0 flow (see Authentication Setup section)")
        lines.append("- Store and refresh access tokens")
        lines.append("- Handle token expiration")
    else:
        lines.append(f"- Implement {auth_type} authentication")
        if doc_links.get("authentication_guide"):
            lines.append(f"- See [Authentication Guide]({doc_links['authentication_guide']})")
    lines.append("")
    step += 1
    
    # Step 4: Test base URL
    if base_url:
        lines.append(f"### {step}. Verify Base URL Access")
        lines.append("")
        lines.append(f"Test connectivity to: `{base_url}`")
        lines.append("")
        step += 1
    
    # Step 5: Test each endpoint
    if core_ops:
        lines.append(f"### {step}. Test API Endpoints")
        lines.append("")
        lines.append("Test each operation using the curl examples above:")
        for op_name in list(core_ops.keys())[:5]:
            lines.append(f"- [ ] Test `{op_name}` operation")
        if len(core_ops) > 5:
            lines.append(f"- [ ] Test remaining {len(core_ops) - 5} operations")
        lines.append("")
        step += 1
    
    # Step 6: Implement error handling
    lines.append(f"### {step}. Implement Error Handling")
    lines.append("")
    lines.append("Handle common API errors:")
    lines.append("- 401 Unauthorized - Token expired or invalid")
    lines.append("- 403 Forbidden - Insufficient permissions")
    lines.append("- 429 Too Many Requests - Rate limit exceeded")
    lines.append("- 500 Server Error - Retry with exponential backoff")
    lines.append("")
    
    lines.append("---")
    lines.append("")
    
    return lines


# Helper function for non-available operations
def format_operation_not_available(operation_name: str, alternative: str = "") -> List[str]:
    """Format a non-available operation notice"""
    lines = [
        f"#### {operation_name} (Not Available)",
        f"- ❌ {operation_name} is not supported via API"
    ]
    
    if alternative:
        lines.append(f"- **Alternative:** {alternative}")
    
    lines.append("")
    
    return lines
