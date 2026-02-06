# -*- coding: utf-8 -*-
"""
API Normalizer - Maps vendor-specific APIs to CloudFuze standard operations

Uses terminology mappings and LLM-powered normalization to map cloud provider
APIs to CloudFuze standard operations.
"""

from typing import Dict, List, Optional, Tuple
import logging
import re
from app.models.cloud_contract import (
    VENDOR_TERMINOLOGY_MAPPINGS,
    get_operation_details,
    get_all_operations,
    normalize_vendor_term
)

logger = logging.getLogger(__name__)


class APIOperationNormalizer:
    """Normalizes vendor-specific API operations to CloudFuze standard"""
    
    def __init__(self, llm=None):
        """
        Initialize normalizer.
        
        Args:
            llm: Language model for LLM-powered normalization (optional)
        """
        self.llm = llm
        self.terminology_map = VENDOR_TERMINOLOGY_MAPPINGS
    
    def normalize_operation(
        self,
        vendor_operation: str,
        endpoint: str,
        method: str,
        description: str = ""
    ) -> Tuple[Optional[str], float]:
        """
        Normalize a vendor operation to CloudFuze standard.
        
        Args:
            vendor_operation: Vendor's operation name (e.g., "users.list", "admin.users.invite")
            endpoint: API endpoint path (e.g., "/api/v1/users")
            method: HTTP method (GET, POST, etc.)
            description: Operation description
            
        Returns:
            Tuple of (cloudfuze_operation, confidence_score)
        """
        # Step 1: Try direct terminology mapping
        cloudfuze_op, confidence = self._try_terminology_mapping(
            vendor_operation, endpoint, method, description
        )
        
        if cloudfuze_op and confidence > 0.8:
            return cloudfuze_op, confidence
        
        # Step 2: Try pattern matching on endpoint and method
        pattern_op, pattern_confidence = self._try_pattern_matching(endpoint, method)
        
        if pattern_op and pattern_confidence > confidence:
            cloudfuze_op = pattern_op
            confidence = pattern_confidence
        
        # Step 3: LLM-powered normalization DISABLED.
        # Cloud API Research output must be evidence-based (docs/OpenAPI only).
        # LLM-derived operation mappings are not permitted as capability evidence.
        return cloudfuze_op, confidence
    
    def _try_terminology_mapping(
        self, vendor_operation: str, endpoint: str, method: str, description: str
    ) -> Tuple[Optional[str], float]:
        """Try to map using terminology dictionary"""
        # Clean vendor operation name
        vendor_op_lower = vendor_operation.lower().strip()
        
        # Try direct lookup
        cloudfuze_op = normalize_vendor_term(vendor_op_lower)
        if cloudfuze_op and get_operation_details(cloudfuze_op):
            logger.debug(f"[NORMALIZE] Direct mapping: {vendor_operation} → {cloudfuze_op}")
            return cloudfuze_op, 0.95
        
        # Try extracting key terms from vendor operation
        key_terms = self._extract_key_terms(vendor_operation)
        for term in key_terms:
            cloudfuze_op = normalize_vendor_term(term)
            if cloudfuze_op and get_operation_details(cloudfuze_op):
                logger.debug(f"[NORMALIZE] Term mapping: {term} → {cloudfuze_op}")
                return cloudfuze_op, 0.85
        
        # Try mapping based on description
        if description:
            desc_lower = description.lower()
            for vendor_term, cf_op in self.terminology_map.items():
                if vendor_term in desc_lower:
                    if not get_operation_details(cf_op):
                        # Ignore non-operation terminology mappings (e.g., entity nouns)
                        continue
                    logger.debug(f"[NORMALIZE] Description mapping: {vendor_term} → {cf_op}")
                    return cf_op, 0.75
        
        return None, 0.0
    
    def _canonicalize_path_for_rest_matching(self, path: str) -> str:
        """
        Strip version/API prefix for canonical REST pattern matching (vendor-agnostic).
        E.g. /2.0/users -> /users, /api/1/users -> /users, /v1/users -> /users.
        """
        if not path:
            return ""
        p = path.strip().lower()
        # Remove leading /api, /api/1, /v1, /v2, /2.0, /1, etc.
        p = re.sub(r"^/(?:api(?:/\d+)?|v?\d+(?:\.\d+)?)/", "/", p)
        return p or "/"

    def _try_pattern_matching(self, endpoint: str, method: str) -> Tuple[Optional[str], float]:
        """Match operation based on endpoint pattern and HTTP method (canonical REST lifecycle mapping)."""
        endpoint_lower = endpoint.lower()
        method_upper = method.upper()
        canonical_path = self._canonicalize_path_for_rest_matching(endpoint)
        # Try matching against canonical path first (version-agnostic)
        path_to_match = canonical_path if canonical_path != endpoint_lower else endpoint_lower

        # INTENT-AWARE BLOCKING: These are NOT admin CRUD operations
        non_crud_patterns = [
            r'/search', r'/query', r'/picker', r'/lookup',  # Search/query endpoints
            r'/invite', r'/send',  # Invite endpoints (not create)
            r'/me$', r'/profile', r'/self',  # Self-service endpoints
            r'/export', r'/import', r'/sync',  # Bulk operations
        ]
        
        for blocked_pattern in non_crud_patterns:
            if re.search(blocked_pattern, path_to_match):
                logger.debug(f"[NORMALIZE] BLOCKED: {endpoint} matches non-CRUD pattern {blocked_pattern}")
                return None, 0.0

        # Canonical REST lifecycle mapping (vendor-agnostic): method + path pattern -> capability.
        # Applied to canonical path so /2.0/users, /api/1/users, /v1/users all match /users patterns.
        patterns = {
            # Users - Standard REST patterns
            (r'/users?$', 'GET'): ('getUsers', 0.9),
            (r'/users?/\{?[\w-]+\}?$', 'GET'): ('getUser', 0.9),
            (r'/user/\{?[\w-]+\}?$', 'GET'): ('getUser', 0.85),
            (r'/users?$', 'POST'): ('createUser', 0.9),
            (r'/users?/\{?[\w-]+\}?$', 'PUT|PATCH'): ('updateUser', 0.85),
            (r'/users?/\{?[\w-]+\}?$', 'DELETE'): ('deleteUser', 0.85),
            (r'/users?/\{?[\w-]+\}?/suspend', 'POST'): ('suspendUser', 0.95),
            (r'/users?/\{?[\w-]+\}?/unsuspend', 'POST'): ('restoreUser', 0.95),
            (r'/users?/\{?[\w-]+\}?/restore', 'POST'): ('restoreUser', 0.95),
            (r'/users?/\{?[\w-]+\}?/deactivate', 'POST'): ('deleteUser', 0.9),
            (r'/users?/\{?[\w-]+\}?/reactivate', 'POST'): ('restoreUser', 0.9),
            
            # Users - Slack method-based patterns
            (r'/users\.list', 'GET|POST'): ('getUsers', 0.9),
            (r'/users\.info', 'GET|POST'): ('getUser', 0.9),
            (r'/admin\.users\.list', 'GET|POST'): ('getUsers', 0.9),
            # REMOVED: admin.users.invite → createUser (invite ≠ native create)
            (r'/admin\.users\.remove', 'POST'): ('deleteUser', 0.9),
            (r'/admin\.users\.setAdmin', 'POST'): ('updateUser', 0.8),
            (r'/admin\.users\.setInactive', 'POST'): ('suspendUser', 0.9),
            
            # Groups - Standard REST patterns
            (r'/groups?$', 'GET'): ('getGroups', 0.9),
            (r'/teams?$', 'GET'): ('getGroups', 0.9),
            (r'/team$', 'GET'): ('getGroups', 0.85),
            (r'/usergroups?$', 'GET'): ('getGroups', 0.9),
            (r'/groups?/\{?[\w-]+\}?$', 'GET'): ('getGroup', 0.9),
            (r'/teams?/\{?[\w-]+\}?$', 'GET'): ('getGroup', 0.9),
            (r'/team/\{?[\w-]+\}?$', 'GET'): ('getGroup', 0.85),
            (r'/groups?$', 'POST'): ('createGroup', 0.9),
            (r'/teams?$', 'POST'): ('createGroup', 0.9),
            (r'/team$', 'POST'): ('createGroup', 0.85),
            (r'/groups?/\{?[\w-]+\}?$', 'PUT|PATCH'): ('updateGroup', 0.85),
            (r'/groups?/\{?[\w-]+\}?$', 'DELETE'): ('deleteGroup', 0.85),
            (r'/groups?/\{?[\w-]+\}?/members', 'GET'): ('getGroupMembers', 0.9),
            (r'/groups?/\{?[\w-]+\}?/users', 'GET'): ('getGroupMembers', 0.9),
            (r'/teams?/\{?[\w-]+\}?/members', 'GET'): ('getGroupMembers', 0.9),
            (r'/team/\{?[\w-]+\}?/users', 'GET'): ('getGroupMembers', 0.85),
            (r'/team/\{?[\w-]+\}?/members', 'GET'): ('getGroupMembers', 0.85),
            (r'/team/members', 'GET'): ('getGroupMembers', 0.85),
            (r'/team/users', 'GET'): ('getGroupMembers', 0.85),
            (r'/groups?/\{?[\w-]+\}?/members/\{?[\w-]+\}?', 'PUT|POST'): ('addUserToGroup', 0.85),
            (r'/groups?/\{?[\w-]+\}?/members/\{?[\w-]+\}?', 'DELETE'): ('removeUserFromGroup', 0.85),
            (r'/team/\{?[\w-]+\}?/user/\{?[\w-]+\}?', 'PUT|POST'): ('addUserToGroup', 0.85),
            (r'/team/\{?[\w-]+\}?/user/\{?[\w-]+\}?', 'DELETE'): ('removeUserFromGroup', 0.85),
            
            # Groups - Slack method-based patterns
            (r'/usergroups\.list', 'GET|POST'): ('getGroups', 0.9),
            (r'/usergroups\.create', 'POST'): ('createGroup', 0.9),
            (r'/usergroups\.update', 'POST'): ('updateGroup', 0.85),
            (r'/usergroups\.disable', 'POST'): ('deleteGroup', 0.8),
            (r'/usergroups\.users\.list', 'GET|POST'): ('getGroupMembers', 0.9),
            (r'/usergroups\.users\.update', 'POST'): ('addUserToGroup', 0.85),
            (r'/conversations\.members', 'GET|POST'): ('getGroupMembers', 0.8),
            (r'/conversations\.invite', 'POST'): ('addUserToGroup', 0.8),
            (r'/conversations\.kick', 'POST'): ('removeUserFromGroup', 0.8),
            
            # Auth
            (r'/oauth.*/token', 'POST'): ('getAccessToken', 0.9),
            (r'/token', 'POST'): ('getAccessToken', 0.8),
            (r'/auth/token', 'POST'): ('getAccessToken', 0.85),
            (r'/oauth\.v2\.access', 'POST'): ('getAccessToken', 0.9),

            # Audit / logs (extended governance evidence)
            (r'/audit', 'GET'): ('getAuditLogs', 0.8),
            (r'/audit-logs', 'GET'): ('getAuditLogs', 0.85),
            (r'/logs', 'GET'): ('getAuditLogs', 0.75),
            (r'/security/events', 'GET'): ('getSecurityEvents', 0.8),
        }
        
        # Try to match patterns against canonical path (version-agnostic)
        for (pattern, methods), (operation, confidence) in patterns.items():
            if re.search(pattern, path_to_match) and re.search(methods, method_upper):
                logger.debug(f"[NORMALIZE] Pattern match: {method} {endpoint} → {operation} (canonical: {path_to_match})")
                return operation, confidence

        return None, 0.0
    
    def _extract_key_terms(self, vendor_operation: str) -> List[str]:
        """Extract key terms from vendor operation name"""
        # Split on common delimiters
        parts = re.split(r'[._\-/]', vendor_operation.lower())
        
        # Build combinations
        terms = []
        for i in range(len(parts)):
            for j in range(i + 1, len(parts) + 1):
                term = " ".join(parts[i:j])
                if term:
                    terms.append(term)
        
        return terms
    
    def _try_llm_normalization(
        self, vendor_operation: str, endpoint: str, method: str, description: str
    ) -> Tuple[Optional[str], float]:
        """Use LLM to normalize operation when rule-based methods fail"""
        if not self.llm:
            return None, 0.0
        
        try:
            # Get all CloudFuze operations for context with examples
            all_ops = get_all_operations()
            core_ops_list = []
            for category in all_ops["core_operations"].values():
                core_ops_list.extend(category.keys())
            
            # Build a more structured prompt with examples
            prompt = f"""You are an API mapping expert. Map this vendor API endpoint to the correct CloudFuze standard operation.

VENDOR API ENDPOINT:
Method: {method if method and method != "UNKNOWN" else "Not specified"}
Path: {endpoint}
Description: {description if description else "Not provided"}
Operation Hint: {vendor_operation if vendor_operation else "Not provided"}

CLOUDFUZE STANDARD OPERATIONS:
User Management: getUsers, getUser, createUser, updateUser, deleteUser, suspendUser, restoreUser
Group Management: getGroups, getGroup, createGroup, updateGroup, deleteGroup, getGroupMembers, addUserToGroup, removeUserFromGroup
Authentication: getAccessToken, refreshToken

MAPPING RULES:
- GET /users → getUsers (list all)
- GET /users/{{id}} → getUser (get one)
- POST /users → createUser
- PUT/PATCH /users/{{id}} → updateUser
- DELETE /users/{{id}} → deleteUser
- POST /users/{{id}}/suspend → suspendUser
- POST /users/{{id}}/unsuspend or /restore → restoreUser

- GET /groups → getGroups
- GET /groups/{{id}}/members → getGroupMembers
- PUT /groups/{{id}}/members/{{uid}} → addUserToGroup
- DELETE /groups/{{id}}/members/{{uid}} → removeUserFromGroup

INSTRUCTIONS:
1. Match the HTTP method and path pattern FIRST
2. Consider the description as secondary hint
3. Return ONLY ONE of the CloudFuze operations listed above
4. If unsure, return "UNKNOWN"
5. No explanation, just the operation name

RESPONSE (one word only):"""
            
            from langchain_core.messages import HumanMessage
            
            response = self.llm.invoke([HumanMessage(content=prompt)])
            operation = response.content.strip().strip('"').strip("'")
            
            # Clean up response
            operation = operation.split()[0] if ' ' in operation else operation
            operation = operation.rstrip('.')
            
            # Validate response is a known operation
            if operation in core_ops_list:
                logger.info(f"[NORMALIZE] LLM mapping: {method} {endpoint} → {operation}")
                return operation, 0.75  # LLM confidence
            elif operation == "UNKNOWN":
                logger.debug(f"[NORMALIZE] LLM could not map: {method} {endpoint}")
                return None, 0.0
            else:
                logger.warning(f"[NORMALIZE] LLM returned invalid operation: {operation}")
                return None, 0.0
                
        except Exception as e:
            logger.error(f"[ERROR] LLM normalization failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None, 0.0
    
    def categorize_endpoints(self, endpoints: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Categorize endpoints by function (users, groups, apps, etc.).
        
        Args:
            endpoints: List of endpoint dicts with path, method, description
            
        Returns:
            Dict with categories as keys and endpoint lists as values
        """
        categories = {
            "users": [],
            "groups": [],
            "auth": [],
            "applications": [],
            "licenses": [],
            "roles": [],
            "security": [],
            "audit": [],
            "settings": [],
            "other": []
        }
        
        for endpoint in endpoints:
            path = endpoint.get("path", "").lower()
            method = endpoint.get("method", "").upper()
            description = endpoint.get("description", "").lower()
            
            # Categorize based on path keywords
            if any(term in path for term in ["/users", "/user", "/people", "/members"]):
                category = "users"
            elif any(term in path for term in ["/groups", "/teams", "/usergroups"]):
                category = "groups"
            elif any(term in path for term in ["/auth", "/oauth", "/token", "/login"]):
                category = "auth"
            elif any(term in path for term in ["/apps", "/applications", "/services"]):
                category = "applications"
            elif any(term in path for term in ["/licenses", "/subscriptions", "/sku"]):
                category = "licenses"
            elif any(term in path for term in ["/roles", "/permissions", "/scopes"]):
                category = "roles"
            elif any(term in path for term in ["/security", "/mfa", "/conditional"]):
                category = "security"
            elif any(term in path for term in ["/audit", "/logs", "/activities"]):
                category = "audit"
            elif any(term in path for term in ["/settings", "/config", "/domains"]):
                category = "settings"
            else:
                # Check description for keywords
                if any(term in description for term in ["user", "people", "member"]):
                    category = "users"
                elif any(term in description for term in ["group", "team"]):
                    category = "groups"
                elif any(term in description for term in ["auth", "token", "login"]):
                    category = "auth"
                else:
                    category = "other"
            
            categories[category].append(endpoint)
        
        # Remove empty categories
        categories = {k: v for k, v in categories.items() if v}
        
        logger.info(f"[CATEGORIZE] Categorized {len(endpoints)} endpoints into {len(categories)} categories")
        return categories


# Helper function
def normalize_cloud_operations(
    vendor_operations: List[Dict],
    llm=None
) -> Dict[str, List[Dict]]:
    """
    Normalize a list of vendor operations to CloudFuze standard.
    
    Args:
        vendor_operations: List of dicts with vendor_operation, endpoint, method, description
        llm: Optional LLM for intelligent normalization
        
    Returns:
        Dict with normalized operations grouped by CloudFuze operation name
    """
    normalizer = APIOperationNormalizer(llm)
    
    normalized = {}
    unmapped = []
    
    for op in vendor_operations:
        cloudfuze_op, confidence = normalizer.normalize_operation(
            vendor_operation=op.get("vendor_operation", ""),
            endpoint=op.get("endpoint", ""),
            method=op.get("method", ""),
            description=op.get("description", "")
        )
        
        if cloudfuze_op and confidence >= 0.6:
            if cloudfuze_op not in normalized:
                normalized[cloudfuze_op] = []
            
            normalized[cloudfuze_op].append({
                **op,
                "cloudfuze_operation": cloudfuze_op,
                "normalization_confidence": confidence
            })
        else:
            unmapped.append(op)
    
    if unmapped:
        logger.info(f"[NORMALIZE] {len(unmapped)} operations could not be mapped")
    
    return {
        "normalized": normalized,
        "unmapped": unmapped
    }
