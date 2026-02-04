# -*- coding: utf-8 -*-
"""
Endpoint Validator - Semantic validation for extracted API endpoints

Ensures endpoints are semantically correct before mapping to CloudFuze operations.
This prevents false positives and wrong mappings across all clouds.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple
from config import ALLOW_SCIM

logger = logging.getLogger(__name__)


class EndpointValidator:
    """Validates extracted endpoints for semantic correctness"""
    
    # Valid base paths for REST APIs
    # Note: Slack uses method-based paths like /users.list, /users.info
    # These are valid and should NOT be rejected
    # NOTE: /scim/ removed - SCIM is HARD BLOCKED globally
    VALID_BASE_PATHS = [
        r'^/api/',
        r'^/v\d+/',
        r'^/rest/',
        r'^/oauth/',
        r'^/auth/',
        r'^/admin/',
        r'^/users',      # Slack: /users.list, /users.info
        r'^/conversations',  # Slack: /conversations.list
        r'^/groups',     # Various clouds
        r'^/team',       # Slack teams
        r'^/usergroups', # Slack usergroups
        r'^/admin\.',    # Slack admin API: /admin.users.list
    ]
    
    # Semantic exclusions - paths that should NOT map to certain operations
    SEMANTIC_EXCLUSIONS = {
        'users': [
            r'/owners',      # owners ≠ users
            r'/admins',      # admins endpoint ≠ user management
            r'/apps',        # apps ≠ users
            r'/applications',
            r'/roles',       # roles ≠ users
            r'/permissions',
            r'/policies',
        ],
        'groups': [
            r'/owners',      # owners ≠ group members
            r'/apps',        # apps ≠ groups
            r'/roles',       # roles ≠ groups
            r'/teams/\{id\}/apps',  # app assignments ≠ group membership
        ],
        'createUser': [
            r'/meta',        # metadata endpoints
            r'/schema',
            r'/bulk',        # bulk operations are different
        ],
        'updateUser': [
            r'/password',    # password ops are separate
            r'/credential',
            r'/token',
        ]
    }
    
    def validate_endpoint(self, endpoint: Dict) -> Tuple[bool, str, float]:
        """
        Validate an endpoint for semantic correctness.
        
        Args:
            endpoint: Endpoint dictionary with method, path, description
            
        Returns:
            Tuple of (is_valid, reason, confidence_penalty)
        """
        path = endpoint.get('path', '')
        method = endpoint.get('method', '')
        description = endpoint.get('description', '')
        
        # DEBUG: Log first few endpoints for troubleshooting
        if not hasattr(self, '_debug_logged'):
            logger.info(f"[VALIDATION DEBUG] Sample endpoint: method={method}, path={path}")
            self._debug_logged = True
        
        # HARD BLOCK: Reject SCIM endpoints (global requirement)
        if not ALLOW_SCIM and '/scim' in path.lower():
            logger.debug(f"[VALIDATION REJECT] {path} - SCIM endpoint (globally blocked)")
            return False, "SCIM endpoint (blocked)", 0.0
        
        # Check 1: Valid HTTP method
        if method == 'UNKNOWN':
            logger.info(f"[VALIDATION REJECT] {path} - Missing HTTP method")
            return False, "Missing HTTP method", 0.3
        
        if method not in ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']:
            logger.info(f"[VALIDATION REJECT] {path} - Invalid HTTP method: {method}")
            return False, f"Invalid HTTP method: {method}", 0.5
        
        # Check 2: Valid base path (relaxed for cloud-agnostic support)
        # Only reject obviously invalid paths, not enforce specific patterns
        if not self._has_reasonable_path_structure(path):
            logger.info(f"[VALIDATION REJECT] {method} {path} - Invalid path structure")
            return False, f"Invalid path structure", 0.4
        
        # Check 3: Not a malformed path
        if not path.startswith('/'):
            logger.info(f"[VALIDATION REJECT] {method} {path} - Must start with /")
            return False, "Path must start with /", 0.5
        
        # Check 4: Path should not be a full URL
        if path.startswith('http'):
            logger.info(f"[VALIDATION REJECT] {method} {path} - Full URL not allowed")
            return False, "Path should be relative, not full URL", 0.3
        
        # All checks passed
        return True, "Valid endpoint", 0.0
    
    def validate_operation_mapping(
        self, 
        endpoint: Dict, 
        cloudfuze_operation: str,
        confidence: float
    ) -> Tuple[bool, str, float]:
        """
        Validate that an endpoint semantically matches the CloudFuze operation.
        
        Args:
            endpoint: Endpoint dictionary
            cloudfuze_operation: Mapped CloudFuze operation name
            confidence: Current confidence score
            
        Returns:
            Tuple of (is_valid, reason, adjusted_confidence)
        """
        path = endpoint.get('path', '').lower()
        method = endpoint.get('method', '').upper()
        
        # Determine operation category
        if cloudfuze_operation in ['getUsers', 'getUser', 'createUser', 'updateUser', 'deleteUser', 'suspendUser', 'restoreUser']:
            category = 'users'
        elif cloudfuze_operation in ['getGroups', 'getGroup', 'createGroup', 'updateGroup', 'deleteGroup']:
            category = 'groups'
        elif cloudfuze_operation in ['getGroupMembers', 'addUserToGroup', 'removeUserFromGroup']:
            category = 'groups'
        else:
            category = None
        
        # Check semantic exclusions
        if category and category in self.SEMANTIC_EXCLUSIONS:
            for exclusion_pattern in self.SEMANTIC_EXCLUSIONS[category]:
                if re.search(exclusion_pattern, path):
                    return False, f"Path '{path}' semantically does not match {cloudfuze_operation}", 0.2
        
        # Check operation-specific exclusions
        if cloudfuze_operation in self.SEMANTIC_EXCLUSIONS:
            for exclusion_pattern in self.SEMANTIC_EXCLUSIONS[cloudfuze_operation]:
                if re.search(exclusion_pattern, path):
                    return False, f"Path contains '{exclusion_pattern}' which excludes {cloudfuze_operation}", 0.2
        
        # Validate method matches operation intent
        if not self._method_matches_operation(method, cloudfuze_operation):
            return False, f"HTTP method {method} does not match operation {cloudfuze_operation}", 0.3
        
        # Validate path structure matches operation
        if not self._path_matches_operation(path, cloudfuze_operation):
            return False, f"Path structure does not match {cloudfuze_operation}", 0.4
        
        return True, "Valid mapping", confidence
    
    def _has_valid_base_path(self, path: str) -> bool:
        """Check if path starts with a valid base (strict check)"""
        path_lower = path.lower()
        for pattern in self.VALID_BASE_PATHS:
            if re.match(pattern, path_lower):
                return True
        return False
    
    def _has_reasonable_path_structure(self, path: str) -> bool:
        """
        Check if path has reasonable structure (permissive check).
        
        This allows cloud-agnostic paths like:
        - /users.list (Slack)
        - /api/v1/users (Standard REST)
        - /admin.users.invite (Slack admin)
        
        Only rejects obviously broken paths.
        """
        path_lower = path.lower()
        
        # DEBUG: Log first few path checks
        if not hasattr(self, '_path_debug_count'):
            self._path_debug_count = 0
        
        if self._path_debug_count < 5:
            logger.info(f"[PATH CHECK] Validating: {path}")
            self._path_debug_count += 1
        
        # Must start with /
        if not path_lower.startswith('/'):
            if self._path_debug_count <= 5:
                logger.info(f"[PATH CHECK] REJECT: {path} - doesn't start with /")
            return False
        
        # Must have at least one character after /
        if len(path_lower) < 2:
            if self._path_debug_count <= 5:
                logger.info(f"[PATH CHECK] REJECT: {path} - too short")
            return False
        
        # Reject paths that are clearly placeholders or invalid
        invalid_patterns = [
            r'^/\{',  # Starts with placeholder like /{id}
            r'^/$',   # Just /
            r'^\s',   # Starts with whitespace
        ]
        
        for pattern in invalid_patterns:
            if re.match(pattern, path_lower):
                if self._path_debug_count <= 5:
                    logger.info(f"[PATH CHECK] REJECT: {path} - matches invalid pattern {pattern}")
                return False
        
        # If it matches known good patterns, definitely accept
        if self._has_valid_base_path(path):
            if self._path_debug_count <= 5:
                logger.info(f"[PATH CHECK] ACCEPT: {path} - matches valid base path")
            return True
        
        # For other paths, check if they contain operation-relevant keywords
        # This handles Slack-style /users.list, /conversations.list, etc.
        relevant_keywords = [
            'user', 'group', 'team', 'member', 'admin',
            'conversation', 'channel', 'workspace',
            'auth', 'token', 'oauth', 'scim'
        ]
        
        if any(keyword in path_lower for keyword in relevant_keywords):
            if self._path_debug_count <= 5:
                logger.info(f"[PATH CHECK] ACCEPT: {path} - contains relevant keyword")
            return True
        
        # Default: accept (permissive for cloud-agnostic support)
        # We'll let semantic validation catch real issues
        if self._path_debug_count <= 5:
            logger.info(f"[PATH CHECK] ACCEPT: {path} - permissive default")
        return True
    
    def _method_matches_operation(self, method: str, operation: str) -> bool:
        """Validate HTTP method matches operation intent"""
        
        # GET operations
        if operation in ['getUsers', 'getUser', 'getGroups', 'getGroup', 'getGroupMembers']:
            return method == 'GET'
        
        # POST operations (create)
        if operation in ['createUser', 'createGroup', 'addUserToGroup']:
            return method in ['POST', 'PUT']  # PUT for addUserToGroup
        
        # PUT/PATCH operations (update)
        if operation in ['updateUser', 'updateGroup']:
            return method in ['PUT', 'PATCH', 'POST']
        
        # DELETE operations
        if operation in ['deleteUser', 'deleteGroup', 'removeUserFromGroup']:
            return method == 'DELETE'
        
        # Special lifecycle operations
        if operation in ['suspendUser', 'restoreUser']:
            return method == 'POST'  # Lifecycle operations typically use POST
        
        return True  # Default to permissive for other operations
    
    def _path_matches_operation(self, path: str, operation: str) -> bool:
        """
        Validate path structure matches operation.
        
        Handles both REST-style (/api/v1/users) and method-based (Slack: /users.list)
        """
        path_lower = path.lower()
        
        # Users operations must contain 'user' (not 'owner', 'admin endpoint', etc.)
        if operation.startswith('getUser') or operation.startswith('createUser') or operation.startswith('updateUser') or operation.startswith('deleteUser') or operation.startswith('suspendUser') or operation.startswith('restoreUser'):
            if 'user' not in path_lower:
                return False
            
            # Exception: admin.users.X is valid for user operations
            # But /admin/roles is NOT
            if '/admin' in path_lower and 'user' not in path_lower:
                return False
        
        # Groups operations must contain 'group', 'team', 'conversation', or 'usergroup'
        if operation.startswith('getGroup') or operation.startswith('createGroup') or operation.startswith('updateGroup') or operation.startswith('deleteGroup'):
            if not any(keyword in path_lower for keyword in ['group', 'team', 'usergroup', 'conversation']):
                return False
        
        # Group membership operations
        if operation in ['getGroupMembers', 'addUserToGroup', 'removeUserFromGroup']:
            # Must reference groups AND either users/members
            has_group = any(keyword in path_lower for keyword in ['group', 'team', 'usergroup', 'conversation'])
            has_members = any(keyword in path_lower for keyword in ['member', 'user', 'invite', 'kick'])
            
            if not (has_group or has_members):
                return False
        
        # Single resource operations should have ID placeholder OR method-based indicator
        if operation in ['getUser', 'updateUser', 'deleteUser', 'suspendUser', 'restoreUser', 'getGroup', 'updateGroup', 'deleteGroup']:
            # REST style: should have {id}
            has_id = re.search(r'\{[\w-]+\}', path_lower)
            # Slack style: .info, .get (singular)
            is_singular_method = re.search(r'\.(info|get|delete|remove|update|set)', path_lower)
            # Exception: lifecycle actions
            is_lifecycle = any(action in path_lower for action in ['/suspend', '/unsuspend', '/restore', '/activate', '/deactivate', '/invite', '/remove'])
            
            if not (has_id or is_singular_method or is_lifecycle):
                # For singular operations, it's OK if it just doesn't end with list/all
                if not re.search(r'\.(list|all)$', path_lower):
                    pass  # Permissive
                else:
                    return False  # .list is for plural operations
        
        # List operations should NOT have specific ID (but .list is OK)
        if operation in ['getUsers', 'getGroups']:
            # Should not end with specific {id}
            if re.search(r'/\{[\w-]+\}$', path_lower):
                return False
            # Slack .list or .all is perfect
            if re.search(r'\.(list|all)', path_lower):
                return True
        
        return True
    
    def calculate_validation_confidence(
        self, 
        total_endpoints: int,
        valid_endpoints: int,
        invalid_endpoints: int
    ) -> float:
        """
        Calculate confidence penalty based on validation results.
        
        Args:
            total_endpoints: Total endpoints extracted
            valid_endpoints: Number of valid endpoints
            invalid_endpoints: Number of invalid endpoints
            
        Returns:
            Confidence multiplier (0.0 to 1.0)
        """
        if total_endpoints == 0:
            return 0.0
        
        valid_ratio = valid_endpoints / total_endpoints
        
        # High invalidity should severely penalize confidence
        if valid_ratio < 0.5:
            return 0.3  # Less than 50% valid = low confidence
        elif valid_ratio < 0.7:
            return 0.6  # 50-70% valid = moderate confidence
        elif valid_ratio < 0.9:
            return 0.8  # 70-90% valid = good confidence
        else:
            return 1.0  # 90%+ valid = full confidence
    
    def generate_validation_report(
        self,
        total_endpoints: int,
        valid_mappings: int,
        invalid_mappings: int,
        unknown_mappings: int
    ) -> str:
        """Generate human-readable validation report"""
        
        total_attempted = valid_mappings + invalid_mappings
        
        report = []
        report.append(f"Extracted {total_endpoints} endpoints")
        report.append(f"Successfully mapped {valid_mappings} operations")
        
        if invalid_mappings > 0:
            report.append(f"Rejected {invalid_mappings} semantically invalid mappings")
        
        if unknown_mappings > 0:
            report.append(f"{unknown_mappings} endpoints could not be automatically mapped")
        
        if total_attempted > 0:
            accuracy = (valid_mappings / total_attempted) * 100
            report.append(f"Mapping accuracy: {accuracy:.1f}%")
        
        return ". ".join(report) + "."


def validate_endpoints(endpoints: List[Dict]) -> List[Dict]:
    """
    Validate a list of endpoints and return only valid ones.
    
    Args:
        endpoints: List of endpoint dictionaries
        
    Returns:
        List of validated endpoints with validation metadata
    """
    validator = EndpointValidator()
    validated = []
    
    for ep in endpoints:
        is_valid, reason, confidence_penalty = validator.validate_endpoint(ep)
        
        ep['is_valid'] = is_valid
        ep['validation_reason'] = reason
        ep['confidence_penalty'] = confidence_penalty
        
        if is_valid:
            validated.append(ep)
        else:
            logger.warning(f"[VALIDATION] Rejected endpoint: {ep.get('method')} {ep.get('path')} - {reason}")
    
    logger.info(f"[VALIDATION] {len(validated)}/{len(endpoints)} endpoints passed validation")
    return validated


def validate_operation_mapping(
    endpoint: Dict,
    cloudfuze_operation: str,
    confidence: float
) -> Tuple[bool, str, float]:
    """
    Validate that an endpoint-to-operation mapping is semantically correct.
    
    Args:
        endpoint: Endpoint dictionary
        cloudfuze_operation: Mapped CloudFuze operation
        confidence: Current confidence
        
    Returns:
        Tuple of (is_valid, reason, adjusted_confidence)
    """
    validator = EndpointValidator()
    return validator.validate_operation_mapping(endpoint, cloudfuze_operation, confidence)
