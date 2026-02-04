#!/usr/bin/env python3
"""
Slack API Validation Check
Tests the endpoint validator with realistic Slack endpoints
"""

import sys
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s'
)

from app.endpoint_validator import EndpointValidator
from app.api_normalizer import APIOperationNormalizer

def check_slack_endpoints():
    """Test validation with real Slack endpoint structures"""
    
    print("=" * 80)
    print("SLACK ENDPOINT VALIDATION CHECK")
    print("=" * 80)
    
    # Simulate endpoints exactly as OpenAPI parser creates them
    slack_endpoints = [
        {
            "method": "POST",
            "path": "/users.list",
            "operation_name": "users.list",
            "description": "Lists all users in a Slack team",
            "tags": ["users"],
            "category": "users",
            "source": "openapi"
        },
        {
            "method": "POST",
            "path": "/users.info",
            "operation_name": "users.info",
            "description": "Gets information about a user",
            "tags": ["users"],
            "category": "users",
            "source": "openapi"
        },
        {
            "method": "POST",
            "path": "/admin.users.invite",
            "operation_name": "admin.users.invite",
            "description": "Invite a user to a Workspace",
            "tags": ["admin", "admin.users"],
            "category": "users",
            "source": "openapi"
        },
        {
            "method": "POST",
            "path": "/admin.users.remove",
            "operation_name": "admin.users.remove",
            "description": "Remove a user from a workspace",
            "tags": ["admin", "admin.users"],
            "category": "users",
            "source": "openapi"
        },
        {
            "method": "POST",
            "path": "/usergroups.list",
            "operation_name": "usergroups.list",
            "description": "List all User Groups for a team",
            "tags": ["usergroups"],
            "category": "groups",
            "source": "openapi"
        },
        {
            "method": "POST",
            "path": "/usergroups.users.list",
            "operation_name": "usergroups.users.list",
            "description": "List all users in a User Group",
            "tags": ["usergroups"],
            "category": "groups",
            "source": "openapi"
        },
        {
            "method": "POST",
            "path": "/usergroups.users.update",
            "operation_name": "usergroups.users.update",
            "description": "Update the list of users for a User Group",
            "tags": ["usergroups"],
            "category": "groups",
            "source": "openapi"
        },
        {
            "method": "POST",
            "path": "/conversations.invite",
            "operation_name": "conversations.invite",
            "description": "Invites users to a channel",
            "tags": ["conversations"],
            "category": "groups",
            "source": "openapi"
        },
        {
            "method": "POST",
            "path": "/conversations.kick",
            "operation_name": "conversations.kick",
            "description": "Removes a user from a conversation",
            "tags": ["conversations"],
            "category": "groups",
            "source": "openapi"
        },
        {
            "method": "POST",
            "path": "/oauth.v2.access",
            "operation_name": "oauth.v2.access",
            "description": "Exchanges a temporary OAuth verifier code for an access token",
            "tags": ["oauth"],
            "category": "authentication",
            "source": "openapi"
        }
    ]
    
    print(f"\nTesting {len(slack_endpoints)} Slack endpoints\n")
    
    # Test 1: Endpoint Validation
    print("=" * 80)
    print("TEST 1: ENDPOINT VALIDATION")
    print("=" * 80)
    
    validator = EndpointValidator()
    validated_count = 0
    rejected_count = 0
    
    for idx, ep in enumerate(slack_endpoints, 1):
        is_valid, reason, penalty = validator.validate_endpoint(ep)
        
        status = "[PASS]" if is_valid else "[FAIL]"
        print(f"\n{idx}. {status} - {ep['method']} {ep['path']}")
        print(f"   Operation: {ep['operation_name']}")
        print(f"   Reason: {reason}")
        if not is_valid:
            print(f"   Penalty: {penalty}")
            rejected_count += 1
        else:
            validated_count += 1
    
    print("\n" + "=" * 80)
    print(f"VALIDATION RESULTS: {validated_count}/{len(slack_endpoints)} passed")
    print("=" * 80)
    
    # Test 2: Pattern Matching / Normalization
    print("\n" + "=" * 80)
    print("TEST 2: OPERATION NORMALIZATION")
    print("=" * 80)
    
    normalizer = APIOperationNormalizer()
    mapped_operations = {}
    
    for idx, ep in enumerate(slack_endpoints, 1):
        # Only check if it passed validation
        is_valid, _, _ = validator.validate_endpoint(ep)
        if not is_valid:
            continue
            
        vendor_op = ep.get("operation_name", "")
        endpoint_path = ep.get("path", "")
        
        cloudfuze_op, confidence = normalizer.normalize_operation(
            vendor_operation=vendor_op,
            endpoint=endpoint_path,
            method=ep["method"],
            description=ep.get("description", "")
        )
        
        if cloudfuze_op and confidence >= 0.5:
            print(f"\n{idx}. [MAPPED]: {ep['method']} {ep['path']}")
            print(f"   {vendor_op} -> {cloudfuze_op}")
            print(f"   Confidence: {confidence:.2f}")
            
            if cloudfuze_op not in mapped_operations:
                mapped_operations[cloudfuze_op] = []
            mapped_operations[cloudfuze_op].append(ep)
        else:
            print(f"\n{idx}. [UNMAPPED]: {ep['method']} {ep['path']}")
            print(f"   Operation: {vendor_op}")
            print(f"   Confidence: {confidence:.2f}")
    
    print("\n" + "=" * 80)
    print(f"NORMALIZATION RESULTS: {len(mapped_operations)} operations mapped")
    print("=" * 80)
    
    # Test 3: Summary
    print("\n" + "=" * 80)
    print("TEST 3: MAPPED OPERATIONS SUMMARY")
    print("=" * 80)
    
    essential_ops = [
        'getUsers', 'getAdmins', 'createUser', 'deleteUser',
        'getGroups', 'getGroupMembers', 'addUserToGroup', 'removeUserFromGroup'
    ]
    
    print("\nEssential Operations (8 required):")
    found_count = 0
    for op in essential_ops:
        if op in mapped_operations:
            endpoints = mapped_operations[op]
            print(f"  [OK] {op}: {len(endpoints)} endpoint(s)")
            for ep in endpoints:
                print(f"     - {ep['method']} {ep['path']}")
            found_count += 1
        else:
            print(f"  [NOT FOUND] {op}")
    
    coverage = (found_count / len(essential_ops)) * 100
    
    print("\n" + "=" * 80)
    print(f"FINAL RESULTS")
    print("=" * 80)
    print(f"[OK] Validated: {validated_count}/{len(slack_endpoints)} endpoints")
    print(f"[OK] Mapped: {len(mapped_operations)} CloudFuze operations")
    print(f"[OK] Essential Coverage: {found_count}/{len(essential_ops)} ({coverage:.1f}%)")
    print("=" * 80)
    
    # Return results
    return {
        "validated": validated_count,
        "rejected": rejected_count,
        "mapped": len(mapped_operations),
        "essential_coverage": found_count,
        "success": validated_count > 0 and found_count >= 5
    }


if __name__ == "__main__":
    try:
        results = check_slack_endpoints()
        
        print("\n" + "=" * 80)
        if results["success"]:
            print("[SUCCESS] CHECK PASSED - Validation is working!")
            sys.exit(0)
        else:
            print("[FAILED] CHECK FAILED - Validation needs fixing")
            sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR]: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
