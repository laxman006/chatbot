# -*- coding: utf-8 -*-
"""
LLM Helpers for Cloud API Research

Provides LLM-powered validation and extraction for universal cloud support.
"""

from typing import Dict, List, Optional
import logging
import json
from app.llm_factory import get_llm

logger = logging.getLogger(__name__)


class CloudAPILLMHelper:
    """
    LLM-powered helper for cloud API research.
    Provides intelligent validation and extraction across all cloud providers.
    """
    
    def __init__(self):
        """Initialize LLM helper with low-temperature model for accurate extraction"""
        try:
            self.llm = get_llm(temperature=0.1, max_tokens=1000)
            logger.info("[LLM HELPER] Initialized LLM helper for cloud API research")
        except Exception as e:
            logger.warning(f"[LLM HELPER] Failed to initialize LLM: {e}")
            self.llm = None
    
    def validate_base_url(self, cloud_name: str, extracted_url: str, context_text: str) -> Optional[str]:
        """
        Validate and correct base URL using LLM intelligence.
        Rejects placeholder URLs and extracts real production URLs.
        
        Args:
            cloud_name: Name of the cloud (e.g., "GitLab", "Box")
            extracted_url: URL extracted by regex
            context_text: Documentation text for context
            
        Returns:
            Validated base URL or None if invalid
        """
        if not self.llm:
            return extracted_url
        
        # Quick check: reject obvious placeholders
        if any(placeholder in extracted_url.lower() for placeholder in ['example.com', 'yoursite.com', 'sample.com', 'placeholder', 'your-domain']):
            logger.info(f"[LLM HELPER] Rejected placeholder URL: {extracted_url}")
            extracted_url = None
        
        try:
            prompt = f"""You are a technical API documentation analyst. Extract the REAL production API base URL for {cloud_name}.

Documentation excerpt:
{context_text[:2000]}

Current extracted URL: {extracted_url or "None"}

Rules:
1. Reject URLs containing: example.com, yoursite.com, sample.com, placeholder, your-domain
2. Look for official API endpoints in code examples
3. Common patterns:
   - GitLab: https://gitlab.com/api/v4
   - Box: https://api.box.com/2.0 or https://api.box.com
   - GitHub: https://api.github.com
   - Slack: https://slack.com/api
   - Google: https://www.googleapis.com

Return ONLY the base URL (no trailing slash) or "NOT_FOUND" if unclear.
Examples:
- https://api.box.com
- https://gitlab.com/api/v4
- NOT_FOUND
"""
            
            response = self.llm.invoke(prompt)
            validated_url = response.content.strip().strip('"\'')
            
            if validated_url == "NOT_FOUND" or not validated_url.startswith('http'):
                logger.warning(f"[LLM HELPER] Could not validate base URL for {cloud_name}")
                return extracted_url  # Return original if LLM can't help
            
            logger.info(f"[LLM HELPER] Validated base URL for {cloud_name}: {validated_url}")
            return validated_url
            
        except Exception as e:
            logger.error(f"[LLM HELPER] Base URL validation failed: {e}")
            return extracted_url
    
    def validate_oauth_scopes(self, cloud_name: str, extracted_scopes: List[str], context_text: str) -> List[str]:
        """
        Validate OAuth scopes using LLM to filter garbage.
        
        Args:
            cloud_name: Name of the cloud
            extracted_scopes: List of scopes extracted by regex
            context_text: Documentation text for context
            
        Returns:
            Filtered list of valid OAuth scopes
        """
        if not self.llm or not extracted_scopes:
            return extracted_scopes
        
        try:
            prompt = f"""You are an OAuth 2.0 security expert. Validate these OAuth scopes for {cloud_name}.

Extracted scopes:
{json.dumps(extracted_scopes)}

Documentation context:
{context_text[:2000]}

Valid OAuth scope patterns:
- api, read_api, write_api
- read_user, write_user, read_users, write_users
- manage_users, manage_groups, admin
- read_repository, write_repository
- openid, profile, email

INVALID examples to REJECT:
- Single generic words: "Keys", "query", "enabled", "type"
- Fragments with trailing dots: "project_type.", "group_type."
- Non-scope terminology: "instance_type", "job_token_scope"
- Random words from documentation

Return ONLY valid OAuth scopes as JSON array: ["scope1", "scope2"]
If none are valid, return: []
"""
            
            response = self.llm.invoke(prompt)
            content = response.content.strip()
            
            # Extract JSON from response (robust parsing)
            try:
                if '[' in content and ']' in content:
                    start = content.index('[')
                    end = content.rindex(']') + 1
                    json_str = content[start:end]
                    validated_scopes = json.loads(json_str)
                    
                    # Ensure it's a list
                    if not isinstance(validated_scopes, list):
                        validated_scopes = []
                    
                    logger.info(f"[LLM HELPER] Validated scopes for {cloud_name}: {len(extracted_scopes)} → {len(validated_scopes)}")
                    return validated_scopes
                else:
                    logger.warning(f"[LLM HELPER] No JSON array found in response: {content[:100]}")
                    return []  # Return empty list, not original scopes
            except json.JSONDecodeError as e:
                logger.error(f"[LLM HELPER] JSON decode error: {e}")
                logger.error(f"[LLM HELPER] Attempted to parse: {content[:200]}")
                return []  # Return empty list to filter garbage
                
        except Exception as e:
            logger.error(f"[LLM HELPER] Scope validation failed: {e}")
            return extracted_scopes
    
    def detect_oauth_endpoints(self, cloud_name: str, context_text: str) -> Dict[str, Optional[str]]:
        """
        Detect OAuth token and authorization endpoints using LLM.
        
        Args:
            cloud_name: Name of the cloud
            context_text: Documentation text
            
        Returns:
            Dict with token_endpoint and authorization_endpoint (or None)
        """
        if not self.llm:
            return {"token_endpoint": None, "authorization_endpoint": None}
        
        try:
            prompt = f"""You are an OAuth 2.0 integration specialist. Extract OAuth endpoints for {cloud_name}.

Documentation:
{context_text[:3000]}

Find:
1. Token Endpoint - where to POST to exchange codes/credentials for access tokens
2. Authorization Endpoint - where users authorize the application

Common patterns:
- GitLab: https://gitlab.com/oauth/token, https://gitlab.com/oauth/authorize
- Box: https://api.box.com/oauth2/token, https://account.box.com/api/oauth2/authorize
- GitHub: https://github.com/login/oauth/access_token, https://github.com/login/oauth/authorize
- Slack: https://slack.com/api/oauth.v2.access, https://slack.com/oauth/v2/authorize

Return as JSON (use null if not found):
{{
  "token_endpoint": "https://...",
  "authorization_endpoint": "https://..."
}}
"""
            
            response = self.llm.invoke(prompt)
            content = response.content.strip()
            
            # Extract JSON from response (robust parsing)
            try:
                if '{' in content and '}' in content:
                    start = content.index('{')
                    end = content.rindex('}') + 1
                    json_str = content[start:end]
                    endpoints = json.loads(json_str)
                    
                    # Ensure it's a dict with expected keys
                    if not isinstance(endpoints, dict):
                        endpoints = {"token_endpoint": None, "authorization_endpoint": None}
                    
                    logger.info(f"[LLM HELPER] Detected OAuth endpoints for {cloud_name}: {endpoints}")
                    return endpoints
                else:
                    logger.warning(f"[LLM HELPER] No JSON object found in response: {content[:100]}")
                    return {"token_endpoint": None, "authorization_endpoint": None}
            except json.JSONDecodeError as e:
                logger.error(f"[LLM HELPER] JSON decode error in OAuth detection: {e}")
                logger.error(f"[LLM HELPER] Attempted to parse: {content[:200]}")
                return {"token_endpoint": None, "authorization_endpoint": None}
                
        except Exception as e:
            logger.error(f"[LLM HELPER] OAuth endpoint detection failed: {e}")
            return {"token_endpoint": None, "authorization_endpoint": None}
    
    def normalize_endpoint_paths(self, cloud_name: str, base_url: str, endpoints: List[Dict]) -> List[Dict]:
        """
        Normalize endpoint paths to include correct API version prefixes.
        
        Args:
            cloud_name: Name of the cloud
            base_url: Detected base URL
            endpoints: List of endpoint dicts with 'method' and 'path'
            
        Returns:
            List of endpoints with normalized paths
        """
        if not endpoints:
            return endpoints
        
        # FALLBACK: If base URL contains version pattern, extract and apply it
        # This ensures normalization even if LLM fails
        fallback_prefix = None
        if base_url:
            # Extract version prefix from base URL
            # GitLab: https://gitlab.com/api/v4 → /api/v4
            # Box: https://api.box.com/2.0 → /2.0
            import re
            match = re.search(r'/(api/v\d+|v\d+\.\d+|\d+\.\d+)$', base_url)
            if match:
                fallback_prefix = '/' + match.group(1)
                logger.debug(f"[LLM HELPER] Detected fallback prefix from base URL: {fallback_prefix}")
        
        if not self.llm:
            # No LLM available, use fallback
            if fallback_prefix:
                for endpoint in endpoints:
                    path = endpoint.get("path", "")
                    if path and not path.startswith(fallback_prefix) and not path.startswith('/api/v'):
                        endpoint["path"] = f"{fallback_prefix}{path}"
                logger.info(f"[LLM HELPER] Normalized endpoints using fallback prefix: {fallback_prefix}")
            return endpoints
        
        try:
            # Sample a few endpoints for LLM analysis
            sample_endpoints = endpoints[:10]
            sample_json = json.dumps([{"method": ep.get("method"), "path": ep.get("path")} for ep in sample_endpoints], indent=2)
            
            prompt = f"""You are an API integration engineer. Normalize these {cloud_name} endpoint paths.

Base URL: {base_url}

Sample endpoints:
{sample_json}

Instructions:
1. Add correct API version prefix if missing
   - GitLab: /api/v4 prefix (e.g., /users → /api/v4/users)
   - Box: /2.0 prefix (e.g., /users → /2.0/users)
   - GitHub: /api prefix or version prefix
   - Some APIs don't need prefix (Slack: /api/users.list)

2. If base URL already contains version (like /api/v4), paths should start with /

3. Keep parameter placeholders like {{id}} or :id

Return JSON with normalization rule:
{{
  "add_prefix": "/api/v4" OR null,
  "examples": [
    {{"original": "/users", "normalized": "/api/v4/users"}},
    {{"original": "/groups", "normalized": "/api/v4/groups"}}
  ]
}}
"""
            
            response = self.llm.invoke(prompt)
            content = response.content.strip()
            
            # Extract JSON from response (robust parsing)
            try:
                if '{' in content and '}' in content:
                    start = content.index('{')
                    end = content.rindex('}') + 1
                    json_str = content[start:end]
                    result = json.loads(json_str)
                    
                    # Ensure it's a dict
                    if not isinstance(result, dict):
                        logger.warning(f"[LLM HELPER] Expected dict, got {type(result)}")
                        return endpoints
                    
                    add_prefix = result.get("add_prefix")
                    
                    # Ensure add_prefix is properly formatted
                    if add_prefix and add_prefix != "null":
                        # Clean up prefix
                        add_prefix = add_prefix.strip().rstrip('/')
                        if not add_prefix.startswith('/'):
                            add_prefix = '/' + add_prefix
                        
                        # Apply prefix to all endpoints that don't have it
                        normalized_count = 0
                        for endpoint in endpoints:
                            path = endpoint.get("path", "")
                            if path and not path.startswith(add_prefix) and not path.startswith('/api/v'):
                                endpoint["path"] = f"{add_prefix}{path}"
                                normalized_count += 1
                        
                        logger.info(f"[LLM HELPER] Normalized {normalized_count}/{len(endpoints)} endpoints for {cloud_name} (added prefix: {add_prefix})")
                    elif fallback_prefix:
                        # LLM said no prefix needed, but we have a fallback from base URL
                        # Apply fallback to endpoints without any version prefix
                        normalized_count = 0
                        for endpoint in endpoints:
                            path = endpoint.get("path", "")
                            if path and not path.startswith('/api/v') and not path.startswith(fallback_prefix):
                                endpoint["path"] = f"{fallback_prefix}{path}"
                                normalized_count += 1
                        
                        if normalized_count > 0:
                            logger.info(f"[LLM HELPER] Applied fallback prefix to {normalized_count} endpoints: {fallback_prefix}")
                    else:
                        logger.info(f"[LLM HELPER] No normalization needed for {cloud_name} endpoints")
                    
                    return endpoints
                else:
                    logger.warning(f"[LLM HELPER] No JSON object found in response: {content[:100]}")
                    return endpoints
            except json.JSONDecodeError as e:
                logger.error(f"[LLM HELPER] JSON decode error in normalization: {e}")
                logger.error(f"[LLM HELPER] Attempted to parse: {content[:200]}")
                return endpoints
                
        except Exception as e:
            logger.error(f"[LLM HELPER] Endpoint normalization failed: {e}")
            return endpoints
    
    def semantic_operation_mapping(self, cloud_name: str, endpoints: List[Dict]) -> Dict[str, str]:
        """
        Map vendor-specific endpoints to CloudFuze standard operations using semantic understanding.
        
        Args:
            cloud_name: Name of the cloud
            endpoints: List of endpoint dicts with 'method', 'path', 'description'
            
        Returns:
            Dict mapping endpoint keys to CloudFuze operation names
        """
        if not self.llm or not endpoints:
            return {}
        
        try:
            # Prepare endpoint summary for LLM
            endpoint_summary = []
            for ep in endpoints[:20]:  # Limit to 20 for token efficiency
                method = ep.get("method", "")
                path = ep.get("path", "")
                desc = ep.get("description", "")[:100]  # Limit description length
                endpoint_summary.append(f"{method} {path} - {desc}" if desc else f"{method} {path}")
            
            endpoint_list = "\n".join(endpoint_summary)
            
            prompt = f"""You are an API integration specialist. Map these {cloud_name} endpoints to CloudFuze standard operations.

{cloud_name} Endpoints:
{endpoint_list}

CloudFuze Standard Operations:
- getUsers: List all users
- createUser: Create new user
- updateUser: Update existing user
- deleteUser: Delete/remove user permanently
- suspendUser: Deactivate/block/suspend user temporarily
- restoreUser: Reactivate/unblock/restore suspended user
- getGroups: List all groups/teams
- createGroup: Create new group/team
- getGroupMembers: Get members of a group
- addUserToGroup: Add user to group/team
- removeUserFromGroup: Remove user from group/team

Semantic mapping rules:
- block = suspend, unblock = restore
- deactivate = suspend, activate/reactivate = restore
- list users = getUsers, get single user = getUser
- members list = getGroupMembers

Return JSON mapping (use "unmapped" if no match):
{{
  "GET /api/v4/users": "getUsers",
  "POST /api/v4/users/:id/block": "suspendUser",
  "GET /api/v4/groups/:id/members": "getGroupMembers",
  ...
}}
"""
            
            response = self.llm.invoke(prompt)
            content = response.content.strip()
            
            # Extract JSON from response (robust parsing)
            try:
                if '{' in content and '}' in content:
                    start = content.index('{')
                    end = content.rindex('}') + 1
                    json_str = content[start:end]
                    mappings = json.loads(json_str)
                    
                    # Ensure it's a dict
                    if not isinstance(mappings, dict):
                        logger.warning(f"[LLM HELPER] Expected dict, got {type(mappings)}")
                        return {}
                    
                    # Filter out "unmapped" entries
                    valid_mappings = {k: v for k, v in mappings.items() if v != "unmapped"}
                    
                    logger.info(f"[LLM HELPER] Semantic mapping for {cloud_name}: {len(valid_mappings)} endpoints mapped")
                    return valid_mappings
                else:
                    logger.warning(f"[LLM HELPER] No JSON object found in response: {content[:100]}")
                    return {}
            except json.JSONDecodeError as e:
                logger.error(f"[LLM HELPER] JSON decode error in semantic mapping: {e}")
                logger.error(f"[LLM HELPER] Attempted to parse: {content[:200]}")
                return {}
                
        except Exception as e:
            logger.error(f"[LLM HELPER] Semantic operation mapping failed: {e}")
            return {}
    
    def extract_endpoints_from_text(
        self,
        cloud_name: str,
        page_url: str,
        page_text: str,
        page_title: str = ""
    ) -> List[Dict]:
        """
        Extract API endpoints from documentation text when regex fails.
        Uses LLM to semantically understand the page and extract endpoint details.
        
        Args:
            cloud_name: Name of the cloud
            page_url: URL of the documentation page
            page_text: Text content of the page
            page_title: Title of the page
            
        Returns:
            List of endpoint dictionaries with method, path, description
        """
        if not self.llm:
            return []

    def generate_fallback_endpoints(
        self,
        cloud_name: str,
        documentation_urls: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        LLM fallback to generate likely endpoints when no extraction is possible.
        This is used as a last resort to provide candidate endpoints for integration.
        """
        if not self.llm:
            return []

        try:
            urls_text = "\n".join(documentation_urls or [])
            prompt = f"""You are a cloud API integration expert. We could not extract endpoints from docs for {cloud_name}.

Known documentation URLs:
{urls_text or "None"}

Generate the most likely API endpoints for Manage Team operations and authentication.
Include only endpoints you are confident are real for {cloud_name}. If uncertain, return [].

Required operations (if supported):
- getUsers
- createUser
- updateUser
- deleteUser
- getGroups
- getGroupMembers
- addUserToGroup
- removeUserFromGroup
- access token / authentication

Return JSON array with method, path, description:
[
  {{
    "method": "GET",
    "path": "/api/v1/users",
    "description": "List all users"
  }}
]

Return ONLY JSON array.
"""

            response = self.llm.invoke(prompt)
            content = response.content.strip()

            if '[' in content and ']' in content:
                start = content.index('[')
                end = content.rindex(']') + 1
                json_str = content[start:end]
                endpoints = json.loads(json_str)

                if not isinstance(endpoints, list):
                    logger.warning(f"[LLM HELPER] Expected list, got {type(endpoints)}")
                    return []

                formatted = []
                for ep in endpoints:
                    if isinstance(ep, dict) and 'method' in ep and 'path' in ep:
                        formatted.append({
                            'method': ep.get('method', '').upper(),
                            'path': ep.get('path', ''),
                            'description': ep.get('description', ''),
                            'base_url': None,
                            'source': 'llm_fallback_generated'
                        })

                prioritized = self._prioritize_endpoints(formatted)
                logger.info(f"[LLM HELPER] LLM fallback generated {len(prioritized)} endpoints for {cloud_name}")
                return prioritized

            logger.warning(f"[LLM HELPER] No JSON array found in LLM fallback response: {content[:100]}")
            return []

        except Exception as e:
            logger.error(f"[LLM HELPER] Fallback endpoint generation failed: {e}")
            return []
        
        try:
            # Log text length for debugging
            logger.info(f"[LLM HELPER] Extracting endpoints from {len(page_text)} characters of text for {cloud_name}")
            
            # Extract ALL endpoints first, prioritize user/group/admin operations
            prompt = f"""Extract ALL API endpoints from this {cloud_name} documentation page.

Page URL: {page_url}
Page Title: {page_title}

Documentation text:
{page_text}

PRIORITY: Extract ALL endpoints, but prioritize these operations:
1. **User Management**: list users, get users, get user list, create user, delete user, update user
2. **Admin Operations**: get admins, list admins, admin management
3. **Group Management**: list groups, get groups, create group, delete group
4. **Group Members**: get group members, list group members, add user to group, remove user from group
5. **Authentication**: access token, OAuth token, authentication, login, auth

For each endpoint found, extract:
1. HTTP method (GET, POST, PUT, DELETE, PATCH)
2. Endpoint path (e.g., /api/v2/users, /users/{{userId}}, /auth/token)
3. Brief description

Return as JSON array with ALL endpoints found (prioritize user/group/admin/auth endpoints first):
[
  {{
    "method": "GET",
    "path": "/api/v2/users",
    "description": "List all users"
  }},
  {{
    "method": "POST",
    "path": "/auth/token",
    "description": "Get access token"
  }}
]

IMPORTANT:
- Extract ALL endpoints visible on the page (not just user/group)
- Prioritize user, admin, group, and authentication endpoints
- Include the full path with version prefix if visible
- Use {{placeholder}} or :id for path parameters
- Include authentication/token endpoints
- Return empty array [] only if NO endpoints are found at all
"""
            
            response = self.llm.invoke(prompt)
            content = response.content.strip()
            
            # Extract JSON from response (robust parsing)
            try:
                if '[' in content and ']' in content:
                    start = content.index('[')
                    end = content.rindex(']') + 1
                    json_str = content[start:end]
                    endpoints = json.loads(json_str)
                    
                    # Ensure it's a list
                    if not isinstance(endpoints, list):
                        logger.warning(f"[LLM HELPER] Expected list, got {type(endpoints)}")
                        return []
                    
                    # Convert to our endpoint format
                    formatted_endpoints = []
                    for ep in endpoints:
                        if isinstance(ep, dict) and 'method' in ep and 'path' in ep:
                            formatted_endpoints.append({
                                'method': ep.get('method', '').upper(),
                                'path': ep.get('path', ''),
                                'description': ep.get('description', ''),
                                'base_url': None  # Will be detected separately
                            })
                    
                    # Prioritize endpoints: user list, admin, group list, group members, create/delete user, add/remove from group, access token
                    prioritized_endpoints = self._prioritize_endpoints(formatted_endpoints)
                    
                    logger.info(f"[LLM HELPER] Extracted {len(formatted_endpoints)} endpoints from text for {cloud_name} (prioritized: {len(prioritized_endpoints)})")
                    return prioritized_endpoints
                else:
                    logger.warning(f"[LLM HELPER] No JSON array found in response: {content[:100]}")
                    return []
            except json.JSONDecodeError as e:
                logger.error(f"[LLM HELPER] JSON decode error in text extraction: {e}")
                logger.error(f"[LLM HELPER] Attempted to parse: {content[:200]}")
                return []
                
        except Exception as e:
            logger.error(f"[LLM HELPER] Text-based endpoint extraction failed: {e}")
            return []
    
    def _prioritize_endpoints(self, endpoints: List[Dict]) -> List[Dict]:
        """
        Prioritize endpoints based on CloudFuze Manage requirements.
        Priority order:
        1. Access token / authentication endpoints
        2. User list (getUsers)
        3. Admin operations
        4. Group list (getGroups)
        5. Group members (getGroupMembers)
        6. Create user
        7. Delete user
        8. Add user to group
        9. Remove user from group
        10. Other endpoints
        """
        if not endpoints:
            return endpoints
        
        priority_keywords = {
            'high': [
                # Authentication (highest priority)
                'token', 'auth', 'oauth', 'login', 'authenticate', 'access',
                # User list
                'user', 'users', 'list', 'get', 'retrieve', 'fetch',
                # Admin
                'admin', 'administrator', 'admins',
                # Group list
                'group', 'groups', 'team', 'teams',
                # Group members
                'member', 'members', 'group.*member', 'team.*member',
                # Create user
                'create.*user', 'add.*user', 'invite.*user', 'new.*user',
                # Delete user
                'delete.*user', 'remove.*user', 'deactivate.*user',
                # Add to group
                'add.*group', 'add.*member', 'assign.*group',
                # Remove from group
                'remove.*group', 'remove.*member', 'unassign.*group'
            ]
        }
        
        import re
        
        prioritized = []
        others = []
        
        for ep in endpoints:
            path_lower = ep.get('path', '').lower()
            desc_lower = (ep.get('description', '') or '').lower()
            method = ep.get('method', '').upper()
            combined = f"{path_lower} {desc_lower}"
            
            priority_score = 0
            
            # Authentication endpoints (highest priority)
            if any(kw in combined for kw in ['token', 'auth', 'oauth', 'login', 'authenticate', 'access']):
                priority_score = 100
            
            # User list endpoints
            elif method == 'GET' and any(kw in combined for kw in ['user', 'users']) and ('list' in combined or 'get' in combined):
                priority_score = 90
            
            # Admin endpoints
            elif 'admin' in combined:
                priority_score = 85
            
            # Group list endpoints
            elif method == 'GET' and any(kw in combined for kw in ['group', 'groups', 'team', 'teams']) and ('list' in combined or 'get' in combined):
                priority_score = 80
            
            # Group members endpoints
            elif any(kw in combined for kw in ['member', 'members']) and ('group' in combined or 'team' in combined):
                priority_score = 75
            
            # Create user
            elif method == 'POST' and any(kw in combined for kw in ['user', 'users']) and any(kw in combined for kw in ['create', 'add', 'invite', 'new']):
                priority_score = 70
            
            # Delete user
            elif method == 'DELETE' and any(kw in combined for kw in ['user', 'users']):
                priority_score = 65
            
            # Add user to group
            elif method in ['POST', 'PUT'] and ('group' in combined or 'member' in combined) and any(kw in combined for kw in ['add', 'assign']):
                priority_score = 60
            
            # Remove user from group
            elif method == 'DELETE' and ('group' in combined or 'member' in combined):
                priority_score = 55
            
            # Other endpoints
            else:
                priority_score = 10
            
            ep['_priority_score'] = priority_score
            
            if priority_score >= 50:
                prioritized.append(ep)
            else:
                others.append(ep)
        
        # Sort prioritized by score (highest first)
        prioritized.sort(key=lambda x: x.get('_priority_score', 0), reverse=True)
        
        # Combine: prioritized first, then others
        result = prioritized + others
        
        # Remove priority score before returning
        for ep in result:
            ep.pop('_priority_score', None)
        
        logger.info(f"[LLM HELPER] Prioritized {len(prioritized)} high-priority endpoints, {len(others)} others")
        
        return result


    def discover_documentation_urls(self, cloud_name: str, official_domain: Optional[str] = None) -> List[Dict]:
        """
        Use LLM to intelligently discover API documentation URLs for a cloud provider.
        
        Args:
            cloud_name: Name of the cloud provider (e.g., "Pax8", "Box", "GitLab")
            official_domain: Official domain if known (e.g., "pax8.com")
            
        Returns:
            List of documentation URL dictionaries with title, url, snippet, source
        """
        if not self.llm:
            logger.warning("[LLM HELPER] LLM not available for URL discovery")
            return []
        
        try:
            domain_context = f"Official domain: {official_domain}" if official_domain else "Official domain: unknown"
            
            prompt = f"""You are a technical API documentation researcher. Discover the correct API documentation URLs for {cloud_name}.

{domain_context}

Based on common API documentation patterns, suggest the most likely official API documentation URLs for {cloud_name}.

Common patterns:
- Developer portals: https://developers.{domain}, https://developer.{domain}, https://dev.{domain}
- Documentation sites: https://docs.{domain}/api, https://docs.{domain}/reference, https://docs.{domain}/api-reference
- API references: https://api.{domain}/docs, https://{domain}/api-docs, https://{domain}/api/reference
- Versioned docs: https://docs.{domain}/api/v1, https://docs.{domain}/api/v2

For {cloud_name}:
1. Generate 5-10 most likely documentation URLs
2. Prioritize API reference pages over guides/tutorials
3. Include common subdomains: developers, developer, devx, docs, api
4. Include common paths: /api, /reference, /api-reference, /docs/api

Return JSON array of URLs:
[
  {{"url": "https://docs.{domain}/api/reference", "title": "{cloud_name} API Reference", "snippet": "Official API reference documentation"}},
  {{"url": "https://developers.{domain}/docs", "title": "{cloud_name} Developer Docs", "snippet": "Developer documentation portal"}}
]

Use the actual domain if provided, otherwise use common patterns. Return ONLY valid JSON array."""
            
            response = self.llm.invoke(prompt)
            content = response.content.strip()
            
            # Extract JSON from response
            try:
                # Find JSON array in response
                import re
                json_match = re.search(r'\[[\s\S]*\]', content)
                if json_match:
                    urls_data = json.loads(json_match.group(0))
                    
                    if isinstance(urls_data, list):
                        results = []
                        for item in urls_data:
                            if isinstance(item, dict) and "url" in item:
                                results.append({
                                    "title": item.get("title", f"{cloud_name} API Documentation"),
                                    "url": item.get("url", ""),
                                    "snippet": item.get("snippet", f"LLM-discovered documentation URL for {cloud_name}"),
                                    "source": "llm_discovery"
                                })
                        
                        logger.info(f"[LLM HELPER] Discovered {len(results)} documentation URLs for {cloud_name}")
                        return results
                    else:
                        logger.warning(f"[LLM HELPER] LLM returned non-list: {type(urls_data)}")
                else:
                    logger.warning(f"[LLM HELPER] No JSON array found in LLM response")
                    
            except json.JSONDecodeError as e:
                logger.error(f"[LLM HELPER] JSON decode error in URL discovery: {e}")
                logger.error(f"[LLM HELPER] Response: {content[:300]}")
            
            # Fallback: Generate URLs based on common patterns
            if official_domain:
                logger.info(f"[LLM HELPER] Using pattern-based fallback for {cloud_name} with domain {official_domain}")
                return self._generate_pattern_based_urls(cloud_name, official_domain)
            
            return []
            
        except Exception as e:
            logger.error(f"[LLM HELPER] URL discovery failed: {e}")
            import traceback
            logger.error(f"[LLM HELPER] Traceback: {traceback.format_exc()}")
            
            # Fallback: Generate URLs based on common patterns
            if official_domain:
                return self._generate_pattern_based_urls(cloud_name, official_domain)
            
            return []
    
    def _generate_pattern_based_urls(self, cloud_name: str, official_domain: str) -> List[Dict]:
        """Generate documentation URLs based on common patterns"""
        domain = official_domain.replace("www.", "")
        results = []
        
        # Common documentation URL patterns
        patterns = [
            f"https://docs.{domain}/api/reference",
            f"https://docs.{domain}/reference",
            f"https://docs.{domain}/api",
            f"https://developers.{domain}/docs",
            f"https://developer.{domain}/docs",
            f"https://devx.{domain}/docs",
            f"https://devx.{domain}/reference",
            f"https://api.{domain}/docs",
            f"https://api.{domain}/reference",
            f"https://{domain}/api-docs",
            f"https://{domain}/api/reference",
            f"https://{domain}/docs/api",
        ]
        
        for url in patterns:
            results.append({
                "title": f"{cloud_name} API Documentation",
                "url": url,
                "snippet": f"Pattern-based documentation URL for {cloud_name}",
                "source": "pattern_fallback"
            })
        
        logger.info(f"[LLM HELPER] Generated {len(results)} pattern-based URLs for {cloud_name}")
        return results
    
    def ask_for_official_doc_url(self, cloud_name: str, official_domain: Optional[str] = None) -> List[Dict]:
        """
        Directly ask LLM (like ChatGPT) for the official API documentation URL.
        This mimics asking: "What is the official API documentation URL for {cloud_name}?"
        
        Args:
            cloud_name: Name of the cloud provider (e.g., "Pax8", "Box", "GitLab")
            official_domain: Official domain if known (e.g., "pax8.com")
            
        Returns:
            List of documentation URL dictionaries with title, url, snippet, source
        """
        if not self.llm:
            logger.warning("[LLM HELPER] LLM not available for direct URL query")
            return []
        
        try:
            domain_context = f"Official domain: {official_domain}" if official_domain else ""
            
            prompt = f"""What is the official API documentation URL for {cloud_name}?

{domain_context}

Please provide the actual, real API documentation URL(s) for {cloud_name}. This should be:
1. The official API reference/documentation page (not guides or tutorials)
2. The URL where developers can find API endpoints, methods, and parameters
3. Usually something like:
   - https://docs.{{domain}}/api/reference
   - https://developers.{{domain}}/docs
   - https://devx.{{domain}}/reference
   - https://api.{{domain}}/docs

If you know multiple relevant URLs, list them all. Return ONLY a JSON array of URLs:
[
  {{"url": "https://actual-real-url.com/api/reference", "title": "{cloud_name} API Reference", "snippet": "Official API reference documentation"}},
  {{"url": "https://another-real-url.com/docs", "title": "{cloud_name} Developer Docs", "snippet": "Developer documentation"}}
]

Return ONLY the JSON array, nothing else. Use real URLs that actually exist."""
            
            response = self.llm.invoke(prompt)
            content = response.content.strip()
            
            # Extract JSON from response
            try:
                # Find JSON array in response
                import re
                json_match = re.search(r'\[[\s\S]*\]', content)
                if json_match:
                    urls_data = json.loads(json_match.group(0))
                    
                    if isinstance(urls_data, list):
                        results = []
                        for item in urls_data:
                            if isinstance(item, dict) and "url" in item:
                                url = item.get("url", "").strip()
                                # Basic URL validation
                                if url and url.startswith("http"):
                                    results.append({
                                        "title": item.get("title", f"{cloud_name} API Documentation"),
                                        "url": url,
                                        "snippet": item.get("snippet", f"LLM-provided documentation URL for {cloud_name}"),
                                        "source": "llm_direct_query"
                                    })
                        
                        if results:
                            logger.info(f"[LLM HELPER] LLM directly provided {len(results)} documentation URLs for {cloud_name}")
                            return results
                    else:
                        logger.warning(f"[LLM HELPER] LLM returned non-list: {type(urls_data)}")
                else:
                    # Try to extract URL from plain text response
                    url_pattern = r'https?://[^\s\)]+'
                    urls_found = re.findall(url_pattern, content)
                    if urls_found:
                        results = []
                        for url in urls_found[:5]:  # Limit to 5 URLs
                            if any(domain in url.lower() for domain in ["docs", "api", "developer", "reference"]):
                                results.append({
                                    "title": f"{cloud_name} API Documentation",
                                    "url": url,
                                    "snippet": f"LLM-provided documentation URL for {cloud_name}",
                                    "source": "llm_direct_query"
                                })
                        if results:
                            logger.info(f"[LLM HELPER] Extracted {len(results)} URLs from LLM text response")
                            return results
                    else:
                        logger.warning(f"[LLM HELPER] No JSON array or URLs found in LLM response")
                        
            except json.JSONDecodeError as e:
                logger.error(f"[LLM HELPER] JSON decode error in direct URL query: {e}")
                logger.error(f"[LLM HELPER] Response: {content[:300]}")
            
            return []
            
        except Exception as e:
            logger.error(f"[LLM HELPER] Direct URL query failed: {e}")
            import traceback
            logger.error(f"[LLM HELPER] Traceback: {traceback.format_exc()}")
            return []


# Global instance (singleton pattern)
_llm_helper_instance = None

def get_llm_helper() -> CloudAPILLMHelper:
    """Get global LLM helper instance (singleton)"""
    global _llm_helper_instance
    if _llm_helper_instance is None:
        _llm_helper_instance = CloudAPILLMHelper()
    return _llm_helper_instance
