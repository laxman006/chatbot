# -*- coding: utf-8 -*-
"""
CloudFuze SaaS Contract - Standard Operations for Cloud Integrations

Defines the canonical operations that all cloud providers should map to
for CloudFuze Manage integration.
"""

from typing import Dict, List, Optional
from enum import Enum


class OperationCategory(str, Enum):
    """Categories for cloud operations"""
    CORE = "core"
    EXTENDED = "extended"


class OperationType(str, Enum):
    """Types of operations"""
    USERS = "users"
    GROUPS = "groups"
    AUTHENTICATION = "authentication"
    APPLICATIONS = "applications"
    LICENSES = "licenses"
    ROLES = "roles"
    SECURITY = "security"
    AUDIT = "audit"
    SETTINGS = "settings"


class LifecycleType(str, Enum):
    """Lifecycle operation types - separates auth from capabilities"""
    READ = "read"  # Read-only: getUsers, getGroups
    CREATE = "create"  # User creation: createUser
    UPDATE = "update"  # Update: updateUser
    DELETE = "delete"  # Hard delete: deleteUser
    SUSPEND = "suspend"  # Soft delete: suspendUser
    RESTORE = "restore"  # Restore: restoreUser
    MEMBERSHIP = "membership"  # Group membership: addUserToGroup, removeUserFromGroup


# CloudFuze Standard Operations Contract
CLOUDFUZE_CONTRACT = {
    "core_operations": {
        "users": {
            "getUsers": {
                "cloudfuze_operation": "getUsers",
                "category": OperationCategory.CORE,
                "type": OperationType.USERS,
                "lifecycle_type": LifecycleType.READ,
                "description": "List all users in the organization",
                "http_methods": ["GET"],
                "required": True,
                "admin_required": False,
            },
            "getUser": {
                "cloudfuze_operation": "getUser",
                "category": OperationCategory.CORE,
                "type": OperationType.USERS,
                "description": "Get details of a single user",
                "http_methods": ["GET"],
                "required": True,
                "admin_required": False,
            },
            "getAdmins": {
                "cloudfuze_operation": "getAdmins",
                "category": OperationCategory.CORE,
                "type": OperationType.USERS,
                "description": "List all admin users",
                "http_methods": ["GET"],
                "required": False,
                "admin_required": True,
            },
            "createUser": {
                "cloudfuze_operation": "createUser",
                "category": OperationCategory.CORE,
                "type": OperationType.USERS,
                "lifecycle_type": LifecycleType.CREATE,
                "description": "Create a new user (NOT invite)",
                "http_methods": ["POST"],
                "required": True,
                "admin_required": True,
            },
            "updateUser": {
                "cloudfuze_operation": "updateUser",
                "category": OperationCategory.CORE,
                "type": OperationType.USERS,
                "description": "Update user information",
                "http_methods": ["PUT", "PATCH"],
                "required": True,
                "admin_required": True,
            },
            "deleteUser": {
                "cloudfuze_operation": "deleteUser",
                "category": OperationCategory.CORE,
                "type": OperationType.USERS,
                "lifecycle_type": LifecycleType.DELETE,
                "description": "Delete or deactivate a user (native API required)",
                "http_methods": ["DELETE", "POST"],
                "required": True,
                "admin_required": True,
            },
            "suspendUser": {
                "cloudfuze_operation": "suspendUser",
                "category": OperationCategory.CORE,
                "type": OperationType.USERS,
                "lifecycle_type": LifecycleType.SUSPEND,
                "description": "Suspend a user account (explicit suspend endpoint required)",
                "http_methods": ["POST", "PUT", "PATCH"],
                "required": False,
                "admin_required": True,
            },
            "restoreUser": {
                "cloudfuze_operation": "restoreUser",
                "category": OperationCategory.CORE,
                "type": OperationType.USERS,
                "lifecycle_type": LifecycleType.RESTORE,
                "description": "Restore a suspended or deleted user (explicit restore endpoint required)",
                "http_methods": ["POST", "PUT", "PATCH"],
                "required": False,
                "admin_required": True,
            },
        },
        "groups": {
            "getGroups": {
                "cloudfuze_operation": "getGroups",
                "category": OperationCategory.CORE,
                "type": OperationType.GROUPS,
                "description": "List all groups/teams",
                "http_methods": ["GET"],
                "required": True,
                "admin_required": False,
            },
            "getGroup": {
                "cloudfuze_operation": "getGroup",
                "category": OperationCategory.CORE,
                "type": OperationType.GROUPS,
                "description": "Get details of a single group",
                "http_methods": ["GET"],
                "required": True,
                "admin_required": False,
            },
            "createGroup": {
                "cloudfuze_operation": "createGroup",
                "category": OperationCategory.CORE,
                "type": OperationType.GROUPS,
                "description": "Create a new group",
                "http_methods": ["POST"],
                "required": True,
                "admin_required": True,
            },
            "updateGroup": {
                "cloudfuze_operation": "updateGroup",
                "category": OperationCategory.CORE,
                "type": OperationType.GROUPS,
                "description": "Update group information",
                "http_methods": ["PUT", "PATCH"],
                "required": False,
                "admin_required": True,
            },
            "deleteGroup": {
                "cloudfuze_operation": "deleteGroup",
                "category": OperationCategory.CORE,
                "type": OperationType.GROUPS,
                "description": "Delete a group",
                "http_methods": ["DELETE"],
                "required": False,
                "admin_required": True,
            },
            "getGroupMembers": {
                "cloudfuze_operation": "getGroupMembers",
                "category": OperationCategory.CORE,
                "type": OperationType.GROUPS,
                "description": "List all members of a group",
                "http_methods": ["GET"],
                "required": True,
                "admin_required": False,
            },
            "addUserToGroup": {
                "cloudfuze_operation": "addUserToGroup",
                "category": OperationCategory.CORE,
                "type": OperationType.GROUPS,
                "description": "Add a user to a group",
                "http_methods": ["POST", "PUT"],
                "required": True,
                "admin_required": True,
            },
            "removeUserFromGroup": {
                "cloudfuze_operation": "removeUserFromGroup",
                "category": OperationCategory.CORE,
                "type": OperationType.GROUPS,
                "description": "Remove a user from a group",
                "http_methods": ["DELETE", "POST"],
                "required": True,
                "admin_required": True,
            },
        },
        "authentication": {
            "getAccessToken": {
                "cloudfuze_operation": "getAccessToken",
                "category": OperationCategory.CORE,
                "type": OperationType.AUTHENTICATION,
                "description": "Obtain an OAuth/API access token",
                "http_methods": ["POST"],
                "required": True,
                "admin_required": False,
            },
            "refreshToken": {
                "cloudfuze_operation": "refreshToken",
                "category": OperationCategory.CORE,
                "type": OperationType.AUTHENTICATION,
                "description": "Refresh an expired access token",
                "http_methods": ["POST"],
                "required": False,
                "admin_required": False,
            },
        },
    },
    "extended_operations": {
        "applications": {
            "listApplications": {
                "cloudfuze_operation": "listApplications",
                "category": OperationCategory.EXTENDED,
                "type": OperationType.APPLICATIONS,
                "description": "List all applications/apps",
                "http_methods": ["GET"],
                "required": False,
            },
            "getUserApplications": {
                "cloudfuze_operation": "getUserApplications",
                "category": OperationCategory.EXTENDED,
                "type": OperationType.APPLICATIONS,
                "description": "List applications assigned to a user",
                "http_methods": ["GET"],
                "required": False,
            },
            "assignApplication": {
                "cloudfuze_operation": "assignApplication",
                "category": OperationCategory.EXTENDED,
                "type": OperationType.APPLICATIONS,
                "description": "Assign an application to a user",
                "http_methods": ["POST"],
                "required": False,
            },
            "unassignApplication": {
                "cloudfuze_operation": "unassignApplication",
                "category": OperationCategory.EXTENDED,
                "type": OperationType.APPLICATIONS,
                "description": "Remove an application from a user",
                "http_methods": ["DELETE", "POST"],
                "required": False,
            },
        },
        "licenses": {
            "listLicenses": {
                "cloudfuze_operation": "listLicenses",
                "category": OperationCategory.EXTENDED,
                "type": OperationType.LICENSES,
                "description": "List all available licenses",
                "http_methods": ["GET"],
                "required": False,
            },
            "getUserLicenses": {
                "cloudfuze_operation": "getUserLicenses",
                "category": OperationCategory.EXTENDED,
                "type": OperationType.LICENSES,
                "description": "Get licenses assigned to a user",
                "http_methods": ["GET"],
                "required": False,
            },
            "assignLicense": {
                "cloudfuze_operation": "assignLicense",
                "category": OperationCategory.EXTENDED,
                "type": OperationType.LICENSES,
                "description": "Assign a license to a user",
                "http_methods": ["POST"],
                "required": False,
            },
            "removeLicense": {
                "cloudfuze_operation": "removeLicense",
                "category": OperationCategory.EXTENDED,
                "type": OperationType.LICENSES,
                "description": "Remove a license from a user",
                "http_methods": ["DELETE", "POST"],
                "required": False,
            },
        },
        "roles": {
            "listRoles": {
                "cloudfuze_operation": "listRoles",
                "category": OperationCategory.EXTENDED,
                "type": OperationType.ROLES,
                "description": "List all roles",
                "http_methods": ["GET"],
                "required": False,
            },
            "getUserRoles": {
                "cloudfuze_operation": "getUserRoles",
                "category": OperationCategory.EXTENDED,
                "type": OperationType.ROLES,
                "description": "Get roles assigned to a user",
                "http_methods": ["GET"],
                "required": False,
            },
            "assignRole": {
                "cloudfuze_operation": "assignRole",
                "category": OperationCategory.EXTENDED,
                "type": OperationType.ROLES,
                "description": "Assign a role to a user",
                "http_methods": ["POST"],
                "required": False,
            },
            "removeRole": {
                "cloudfuze_operation": "removeRole",
                "category": OperationCategory.EXTENDED,
                "type": OperationType.ROLES,
                "description": "Remove a role from a user",
                "http_methods": ["DELETE", "POST"],
                "required": False,
            },
        },
        "security": {
            "getAuditLogs": {
                "cloudfuze_operation": "getAuditLogs",
                "category": OperationCategory.EXTENDED,
                "type": OperationType.AUDIT,
                "description": "Get audit logs for security and compliance",
                "http_methods": ["GET"],
                "required": False,
            },
            "getSecurityEvents": {
                "cloudfuze_operation": "getSecurityEvents",
                "category": OperationCategory.EXTENDED,
                "type": OperationType.SECURITY,
                "description": "Get security events and alerts",
                "http_methods": ["GET"],
                "required": False,
            },
            "getMFAStatus": {
                "cloudfuze_operation": "getMFAStatus",
                "category": OperationCategory.EXTENDED,
                "type": OperationType.SECURITY,
                "description": "Get MFA status for users",
                "http_methods": ["GET"],
                "required": False,
            },
        },
        "settings": {
            "getDomains": {
                "cloudfuze_operation": "getDomains",
                "category": OperationCategory.EXTENDED,
                "type": OperationType.SETTINGS,
                "description": "List verified domains",
                "http_methods": ["GET"],
                "required": False,
            },
            "getOrgSettings": {
                "cloudfuze_operation": "getOrgSettings",
                "category": OperationCategory.EXTENDED,
                "type": OperationType.SETTINGS,
                "description": "Get organization settings",
                "http_methods": ["GET"],
                "required": False,
            },
        },
    },
}


# Vendor-specific terminology mappings
VENDOR_TERMINOLOGY_MAPPINGS = {
    # User-related terms
    "deactivate": "deleteUser",
    "deactivate user": "deleteUser",
    "disable": "suspendUser",
    "disable user": "suspendUser",
    "suspend account": "suspendUser",
    "block user": "suspendUser",
    "remove user": "deleteUser",
    "archive user": "deleteUser",
    "unsuspend": "restoreUser",
    "unblock": "restoreUser",
    "reactivate": "restoreUser",
    "enable user": "restoreUser",
    "list users": "getUsers",
    "get users": "getUsers",
    "fetch users": "getUsers",
    "retrieve users": "getUsers",
    "invite user": "createUser",
    "add user": "createUser",
    "provision user": "createUser",
    "modify user": "updateUser",
    "edit user": "updateUser",
    "change user": "updateUser",
    
    # Group-related terms
    "team": "group",
    "teams": "groups",
    "organization": "group",
    "workspace": "group",
    "workspace member": "user",
    "organization admin": "admin",
    "list teams": "getGroups",
    "get teams": "getGroups",
    "list groups": "getGroups",
    "get groups": "getGroups",
    "create team": "createGroup",
    "add team": "createGroup",
    "remove from team": "removeUserFromGroup",
    "add to team": "addUserToGroup",
    "team members": "getGroupMembers",
    "group members": "getGroupMembers",
    
    # Authentication terms
    "oauth": "getAccessToken",
    "authorize": "getAccessToken",
    "login": "getAccessToken",
    "token": "getAccessToken",
    "access token": "getAccessToken",
    "bearer token": "getAccessToken",
    
    # License terms
    "subscription": "license",
    "subscriptions": "licenses",
    "sku": "license",
    
    # Application terms
    "app": "application",
    "apps": "applications",
    "service": "application",
}


def get_core_operations() -> Dict:
    """Get all core CloudFuze operations"""
    return CLOUDFUZE_CONTRACT["core_operations"]


def get_extended_operations() -> Dict:
    """Get all extended CloudFuze operations"""
    return CLOUDFUZE_CONTRACT["extended_operations"]


def get_all_operations() -> Dict:
    """Get all CloudFuze operations (core + extended)"""
    return CLOUDFUZE_CONTRACT


def get_required_operations() -> List[str]:
    """Get list of required operations for CloudFuze Manage integration"""
    required_ops = []
    
    for category, operations in get_core_operations().items():
        for op_name, op_details in operations.items():
            if op_details.get("required", False):
                required_ops.append(op_name)
    
    return required_ops


def normalize_vendor_term(vendor_term: str) -> Optional[str]:
    """
    Normalize vendor-specific terminology to CloudFuze standard operation.
    
    Args:
        vendor_term: Vendor-specific term (e.g., "deactivate user")
        
    Returns:
        CloudFuze operation name or None if not found
    """
    vendor_term_lower = vendor_term.lower().strip()
    return VENDOR_TERMINOLOGY_MAPPINGS.get(vendor_term_lower)


def get_operation_details(operation_name: str) -> Optional[Dict]:
    """
    Get details for a specific CloudFuze operation.
    
    Args:
        operation_name: CloudFuze operation name (e.g., "getUsers")
        
    Returns:
        Operation details dict or None if not found
    """
    # Search in core operations
    for category, operations in get_core_operations().items():
        if operation_name in operations:
            return operations[operation_name]
    
    # Search in extended operations
    for category, operations in get_extended_operations().items():
        if operation_name in operations:
            return operations[operation_name]
    
    return None


def calculate_coverage_score(supported_operations: List[str], expected_operations: Optional[List[str]] = None) -> Dict:
    """
    Calculate API coverage score based on supported operations.
    Uses DYNAMIC expectations based on cloud type (not fixed 8 operations).
    
    Args:
        supported_operations: List of CloudFuze operations that are supported
        expected_operations: List of operations expected for this cloud type (if None, uses all required ops)
        
    Returns:
        Dict with coverage metrics
    """
    # Use dynamic expectations if provided, otherwise fallback to all required ops
    if expected_operations:
        expected_ops = expected_operations
    else:
        expected_ops = get_required_operations()
    
    core_ops = []
    extended_ops = []
    
    # Categorize operations
    for op in supported_operations:
        op_details = get_operation_details(op)
        if op_details:
            if op_details["category"] == OperationCategory.CORE:
                core_ops.append(op)
            else:
                extended_ops.append(op)
    
    # Calculate scores based on DYNAMIC expectations (cloud-type aware)
    supported_expected = len([op for op in supported_operations if op in expected_ops])
    total_expected = len(expected_ops)
    
    return {
        "expected_operations": expected_ops,  # NEW: Show what's expected
        "supported_operations_count": supported_expected,
        "expected_operations_count": total_expected,
        "coverage_percentage": round((supported_expected / total_expected * 100), 2) if total_expected > 0 else 0,
        "core_operations_supported": len(core_ops),
        "extended_operations_supported": len(extended_ops),
        "total_operations_supported": len(supported_operations),
    }
