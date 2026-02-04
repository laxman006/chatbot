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
    Format cloud research data into comprehensive markdown response.
    
    Args:
        research_data: Complete research results
        cloud_name: Name of the cloud
        
    Returns:
        Formatted markdown string
    """
    sections = []
    
    # Header
    sections.append(f"# Cloud API Integration Guide: {cloud_name}")
    sections.append("")
    
    if research_data.get("from_cache"):
        sections.append("*(Retrieved from cache)*")
        sections.append("")
    
    sections.append("")
    sections.append("---")
    sections.append("")
    
    # SECTION 1: Integration Quickstart (NEW - Most Important)
    sections.extend(_format_integration_quickstart(research_data, cloud_name))
    
    # SECTION 2: Authentication Setup (Enhanced)
    sections.extend(_format_authentication_setup(research_data, cloud_name))
    
    # Cloud Classification (context)
    classification = research_data.get("cloud_classification", {})
    if classification:
        category = classification.get("category", "Unknown")
        support = classification.get("manage_team_support", "unknown")
        expected = classification.get("expected_coverage", "Unknown")
        
        sections.append("## Cloud Classification")
        sections.append("")
        sections.append(f"**{category}**")
        sections.append("")
        sections.append(f"- **Manage Team Support:** {support.title()}")
        sections.append(f"- **Expected Coverage:** {expected}")
        sections.append("")
        sections.append("---")
        sections.append("")
    
    # Official Documentation Links
    doc_links = research_data.get("documentation", {})
    if doc_links:
        sections.append("## Official Documentation")
        sections.append("")
        
        if doc_links.get("docs_home"):
            sections.append(f"- **Developer Portal:** [{cloud_name} Developers]({doc_links['docs_home']})")
        if doc_links.get("api_reference"):
            sections.append(f"- **API Reference:** [API Reference]({doc_links['api_reference']})")
        if doc_links.get("getting_started"):
            sections.append(f"- **Getting Started:** [Quick Start]({doc_links['getting_started']})")
        if doc_links.get("authentication_guide"):
            sections.append(f"- **Authentication Guide:** [Auth Guide]({doc_links['authentication_guide']})")
        if doc_links.get("rate_limits"):
            sections.append(f"- **Rate Limits:** [Rate Limiting]({doc_links['rate_limits']})")
        
        sections.append("")
        sections.append("---")
        sections.append("")
    
    # Core Operations (Enhanced with full integration details)
    core_ops = research_data.get("core_operations", {})
    base_url = research_data.get("base_url", "")
    
    if core_ops:
        sections.append("## Available API Endpoints")
        sections.append("")
        sections.append("*Ready-to-use endpoints with complete integration examples*")
        sections.append("")
        
        # Users
        user_ops = ["getUsers", "getUser", "createUser", "updateUser", "deleteUser", "suspendUser", "restoreUser"]
        user_ops_found = [op for op in user_ops if op in core_ops]
        
        if user_ops_found:
            sections.append("### User Management APIs")
            sections.append("")
            
            for op in user_ops_found:
                op_data = core_ops[op][0] if isinstance(core_ops[op], list) and core_ops[op] else core_ops[op]
                sections.extend(_format_operation(op, op_data, base_url))
        
        # Groups
        group_ops = ["getGroups", "getGroup", "createGroup", "updateGroup", "deleteGroup", 
                     "getGroupMembers", "addUserToGroup", "removeUserFromGroup"]
        group_ops_found = [op for op in group_ops if op in core_ops]
        
        if group_ops_found:
            sections.append("### Group/Team Management APIs")
            sections.append("")
            
            for op in group_ops_found:
                op_data = core_ops[op][0] if isinstance(core_ops[op], list) and core_ops[op] else core_ops[op]
                sections.extend(_format_operation(op, op_data, base_url))
    
    # Extended Operations Summary
    extended_ops = research_data.get("extended_operations", {})
    if extended_ops:
        sections.append("## Extended Operations")
        sections.append("")
        sections.append(f"Found {len(extended_ops)} additional operations beyond core user/group management:")
        sections.append("")
        
        for op_name in list(extended_ops.keys())[:10]:  # Show first 10
            sections.append(f"- `{op_name}`")
        
        if len(extended_ops) > 10:
            sections.append(f"- ... and {len(extended_ops) - 10} more")
        
        sections.append("")
        sections.append("---")
        sections.append("")
    
    # Authentication (OAuth 2.0 - PRIMARY FOCUS)
    auth_info = research_data.get("authentication", {})
    if auth_info:
        sections.append("## Authentication")
        sections.append("")
        
        auth_type = auth_info.get("type", "Unknown")
        
        if "oauth" in auth_type.lower():
            sections.append(f"✅ **{cloud_name} supports OAuth 2.0**")
            sections.append("")
            
            grant_type = auth_info.get("grant_type", "")
            if grant_type:
                sections.append(f"- **Grant Type:** `{grant_type}`")
            
            token_endpoint = auth_info.get("token_endpoint", "")
            if token_endpoint:
                sections.append(f"- **Token Endpoint:** `{token_endpoint}`")
            
            auth_endpoint = auth_info.get("authorization_endpoint", "")
            if auth_endpoint:
                sections.append(f"- **Authorization Endpoint:** `{auth_endpoint}`")
            
            scopes = auth_info.get("scopes", [])
            if scopes:
                sections.append(f"- **Required Scopes:** {', '.join(scopes)}")
            
            admin_required = auth_info.get("admin_consent_required", False)
            sections.append(f"- **Admin Consent Required:** {'Yes' if admin_required else 'No'}")
            
            if auth_info.get("documentation_url"):
                sections.append(f"- **Auth Guide:** [OAuth Documentation]({auth_info['documentation_url']})")
        elif auth_type != "Unknown":
            sections.append(f"**Authentication Type:** {auth_type}")
            sections.append("")
            sections.append(f"*(Note: {cloud_name} uses {auth_type} instead of OAuth 2.0)*")
        else:
            sections.append("⚠️ **Authentication method not automatically determined**")
            sections.append("")
            sections.append(f"Please check the [official documentation]({doc_links.get('authentication_guide', doc_links.get('docs_home', ''))}) for authentication details.")
        
        sections.append("")
        sections.append("---")
        sections.append("")
    
    # SCIM is HARD BLOCKED - do not show SCIM support section
        sections.append("---")
        sections.append("")
    
    # SDKs & Tools
    sdks = doc_links.get("sdks", {})
    tools = doc_links.get("tools", {})
    
    if sdks or tools:
        sections.append("## Developer Resources")
        sections.append("")
        
        if sdks:
            sections.append("### Official SDKs")
            sections.append("")
            for lang, sdk_info in sdks.items():
                sections.append(f"- **{lang.title()}:** [{sdk_info['name']}]({sdk_info['url']})")
                sections.append(f"  - Install: `{sdk_info['install']}`")
            sections.append("")
        
        if tools:
            sections.append("### Tools")
            sections.append("")
            for tool_name, tool_url in tools.items():
                sections.append(f"- **{tool_name.replace('_', ' ').title()}:** [Link]({tool_url})")
            sections.append("")
        
        sections.append("---")
        sections.append("")
    
    # Coverage Summary
    coverage = research_data.get("coverage_metrics", {})
    if coverage:
        sections.append("## API Coverage Summary")
        sections.append("")

        # Determine if discovered endpoints look like Manage Team APIs
        all_endpoints = research_data.get("all_endpoints", [])
        manage_keywords = [
            "user", "users", "group", "groups", "member", "members", "admin", "admins",
            "team", "teams", "auth", "oauth", "token", "scim", "directory"
        ]
        def _is_manage_candidate(endpoint: Dict) -> bool:
            path = (endpoint.get("path") or "").lower()
            desc = (endpoint.get("description") or "").lower()
            combined = f"{path} {desc}"
            return any(k in combined for k in manage_keywords)

        has_manage_candidates = any(_is_manage_candidate(ep) for ep in all_endpoints)

        # Get cloud classification for context-aware status
        classification = research_data.get("cloud_classification", {})
        support_level = classification.get("manage_team_support", "unknown")

        # If we have endpoints but none look like Manage Team APIs, avoid showing all "Unknown"
        if not core_ops and all_endpoints and not has_manage_candidates:
            sections.append("No Manage Team endpoints detected in the discovered API surface.")
            sections.append("These endpoints appear unrelated to user/group/admin/auth management, so coverage is not applicable.")
            sections.append("")
            sections.append(f"**Core Coverage:** 0.0% (no Manage Team endpoints detected)")
            sections.append(f"**Confidence Score:** {research_data.get('confidence_score', 0):.2f}/1.0")
            sections.append("")
        else:
            sections.append("| CloudFuze Operation | Status |")
            sections.append("|---------------------|--------|")

            all_core_ops = ["getUsers", "createUser", "updateUser", "deleteUser", "suspendUser", "restoreUser",
                            "getGroups", "createGroup", "getGroupMembers", "addUserToGroup", "removeUserFromGroup"]

            for op in all_core_ops:
                if op in core_ops:
                    # Get the actual endpoint details to qualify the status
                    op_data = core_ops[op]
                    if isinstance(op_data, list) and len(op_data) > 0:
                        endpoint = op_data[0]
                        path = endpoint.get("path", "").lower()
                        method = endpoint.get("method", "")

                        # QUALIFIED STATUS based on intent
                        if "/search" in path or "/query" in path or "/picker" in path:
                            status = "✅ Search-based"
                        elif "/invite" in path or "/send" in path:
                            status = "✅ Invite-only"
                        elif "/me" in path or "/profile" in path or "/self" in path:
                            status = "✅ Self-service"
                        elif method == "GET" and op in ["getUsers", "getGroups", "getGroupMembers"]:
                            status = "✅ Read-only"
                        else:
                            status = "✅ Native API"
                    else:
                        status = "✅ Supported"
                else:
                    # Context-aware status based on cloud type
                    if support_level == "none":
                        # Business App with no expected support
                        status = "❌ Not Supported"
                    elif support_level == "full":
                        # IAM/Directory - should have it, extraction likely failed
                        status = "⚠️ Unknown (check docs manually)"
                    elif support_level in ["partial", "limited"]:
                        # Collaboration/Business - may or may not have it
                        status = "⚠️ Unknown"
                    else:
                        # Default: unknown
                        status = "⚠️ Unknown"
                sections.append(f"| {op} | {status} |")

            sections.append("")
            sections.append(f"**Core Coverage:** {coverage.get('core_coverage_percentage', 0):.1f}%")
            sections.append(f"**Confidence Score:** {research_data.get('confidence_score', 0):.2f}/1.0")
            sections.append("")

        # Add classification-based recommendation
        if classification:
            coverage_pct = coverage.get('core_coverage_percentage', 0)

            if support_level == "none":
                sections.append("")
                sections.append("### Recommendation")
                sections.append(f"❌ **{cloud_name} is not eligible for Manage Team automation**")
                sections.append(f"- This cloud does not provide organization-wide user/group lifecycle APIs")
                sections.append(f"- APIs are limited to application-specific data (posts, boards, tasks, etc.)")
            elif support_level == "full" and coverage_pct < 50:
                sections.append("")
                sections.append("### Recommendation")
                sections.append(f"⚠️ **Manual verification required**")
                sections.append(f"- {category} clouds typically have comprehensive Manage Team APIs")
                sections.append(f"- Low coverage ({coverage_pct:.0f}%) suggests extraction incomplete")
                sections.append(f"- Please check official documentation manually")
            elif support_level in ["partial", "limited"]:
                sections.append("")
                sections.append("### Recommendation")
                sections.append(f"⚠️ **Partial support - verify before implementation**")
                sections.append(f"- {category} clouds may have limited user/group management")
                sections.append(f"- Review mapped operations to confirm they meet requirements")

        sections.append("")
        sections.append("---")
        sections.append("")
    
    # All Discovered Endpoints (NEW - Complete list for reference)
    all_endpoints = research_data.get("all_endpoints", [])
    if all_endpoints:
        sections.extend(_format_all_endpoints_table(all_endpoints, base_url))
    
    # Integration Checklist (NEW - Step-by-step guide)
    sections.extend(_format_integration_checklist(research_data, cloud_name))
    
    # Footer
    last_researched = research_data.get("last_researched", "Unknown")
    created_by = research_data.get("created_by", "system")
    sections.append(f"*Research completed on {last_researched}*")
    sections.append(f"*Created by: {created_by}*")
    sections.append(f"*Confidence Score: {research_data.get('confidence_score', 0):.2f}*")
    
    return "\n".join(sections)


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
