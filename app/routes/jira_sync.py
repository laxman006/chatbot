# -*- coding: utf-8 -*-
"""
Jira Sync API Endpoints
"""
from fastapi import APIRouter, HTTPException, Depends, Body
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import traceback
import os
import time

from app.auth import require_admin
from app.jira_vectorstore import add_jira_tickets_incrementally, load_jira_vectorstore
from app.jira_sync_tracker import get_sync_stats, update_last_sync_time, has_sync_alerts, get_sync_alerts
from app.services.jira_config_service import JiraConfigService
from app.models.jira_config import JiraConfig, JiraConfigUpdate, JiraConfigResponse

router = APIRouter(prefix="/api/jira", tags=["jira-sync"])

# Initialize config service
config_service = JiraConfigService()


class SyncResponse(BaseModel):
    status: str
    message: str
    last_sync: Optional[str]
    total_documents: Optional[int]
    new_tickets: Optional[int]


@router.post("/sync", response_model=SyncResponse)
async def trigger_jira_sync(
    current_user: dict = Depends(require_admin)
):
    """
    Manually trigger incremental Jira ticket sync.
    Requires admin authentication.
    """
    try:
        print("[API] Manual Jira sync triggered by admin")
        
        # Check if sync is already running (lock file exists)
        lock_file = "./data/jira_sync.lock"
        if os.path.exists(lock_file):
            lock_age = time.time() - os.path.getmtime(lock_file)
            if lock_age < 300:  # Less than 5 minutes (lock timeout)
                error_msg = f"Sync is already running (lock age: {lock_age:.0f}s). Please wait for it to complete."
                print(f"[API] ERROR: {error_msg}")
                raise HTTPException(
                    status_code=409,  # Conflict
                    detail=error_msg
                )
            else:
                # Stale lock - remove it
                print(f"[API] WARN: Stale lock file detected (age: {lock_age:.0f}s), removing...")
                try:
                    os.remove(lock_file)
                except Exception as e:
                    print(f"[API] WARN: Could not remove stale lock: {e}")
        
        # Get pre-sync count
        vectorstore = load_jira_vectorstore()
        if not vectorstore:
            error_msg = "Jira vectorstore not found. Please build it first."
            print(f"[API] ERROR: {error_msg}")
            raise HTTPException(
                status_code=500,
                detail=error_msg
            )
        
        try:
            pre_count = vectorstore._collection.count()
            print(f"[API] Pre-sync document count: {pre_count}")
        except Exception as e:
            error_msg = f"Failed to count documents: {str(e)}"
            print(f"[API] ERROR: {error_msg}")
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=error_msg
            )
        
        # Run incremental sync
        print("[API] Starting incremental sync...")
        result = add_jira_tickets_incrementally()
        
        if result:
            try:
                post_count = result._collection.count()
                new_tickets = post_count - pre_count
            except Exception as e:
                error_msg = f"Failed to count post-sync documents: {str(e)}"
                print(f"[API] ERROR: {error_msg}")
                traceback.print_exc()
                raise HTTPException(
                    status_code=500,
                    detail=error_msg
                )
            
            stats = get_sync_stats()
            
            print(f"[API] Sync completed successfully: {new_tickets} new tickets added")
            
            return SyncResponse(
                status="success",
                message=f"Successfully synced {new_tickets} new/updated tickets",
                last_sync=stats.get('last_sync_readable'),
                total_documents=post_count,
                new_tickets=new_tickets
            )
        else:
            stats = get_sync_stats()
            print("[API] Sync returned no updates")
            return SyncResponse(
                status="no_updates",
                message="No new tickets to sync",
                last_sync=stats.get('last_sync_readable'),
                total_documents=pre_count,
                new_tickets=0
            )
            
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        print(f"[API] Sync error: {error_msg}")
        print(f"[API] Traceback:")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Sync failed: {error_msg}"
        )


@router.get("/sync/status")
async def get_sync_status(
    current_user: dict = Depends(require_admin)
):
    """Get Jira sync status and statistics with alerts."""
    try:
        stats = get_sync_stats()
        vectorstore = load_jira_vectorstore()
        
        if vectorstore:
            try:
                total_docs = vectorstore._collection.count()
            except Exception as e:
                print(f"[API] Error counting documents in status endpoint: {e}")
                traceback.print_exc()
                total_docs = 0
        else:
            total_docs = 0
        
        # Check for active lock
        lock_file = "./data/jira_sync.lock"
        sync_locked = False
        lock_age_seconds = None
        if os.path.exists(lock_file):
            lock_age_seconds = time.time() - os.path.getmtime(lock_file)
            sync_locked = lock_age_seconds < 300  # Active if less than 5 minutes old
        
        # Get alerts
        alerts = get_sync_alerts()
        has_alerts = has_sync_alerts()
        
        return {
            "status": "active" if vectorstore else "inactive",
            "last_sync": stats.get('last_sync_readable', 'Never'),
            "last_attempt": stats.get('last_attempt_readable'),
            "last_status": stats.get('last_status', 'unknown'),
            "total_documents": total_docs,
            "sync_history": stats.get('sync_history', []),
            "consecutive_failures": stats.get('consecutive_failures', 0),
            "has_alerts": has_alerts,
            "alerts": alerts,
            "sync_locked": sync_locked,
            "lock_age_seconds": lock_age_seconds
        }
    except Exception as e:
        error_msg = str(e)
        print(f"[API] Status endpoint error: {error_msg}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get status: {error_msg}"
        )


@router.post("/webhook")
async def jira_webhook_handler(payload: dict):
    """
    Webhook endpoint for Jira notifications.
    Configure in Jira: Administration > System > Webhooks
    
    Webhook URL: https://your-domain.com/api/jira/webhook
    Events: Issue Created, Issue Updated, Issue Resolved
    """
    try:
        # Extract issue information
        issue_event_type = payload.get('webhookEvent')
        issue_data = payload.get('issue', {})
        
        if not issue_data:
            return {"status": "ignored", "reason": "no_issue_data"}
        
        issue_key = issue_data.get('key')
        issue_status = issue_data.get('fields', {}).get('status', {}).get('name')
        
        print(f"[WEBHOOK] Received {issue_event_type} for {issue_key} (status: {issue_status})")
        
        # Only process resolved/closed tickets
        if issue_status in ['Resolved', 'Closed']:
            # Trigger sync for this specific ticket
            print(f"[WEBHOOK] Triggering sync for {issue_key}")
            
            # For now, trigger incremental sync
            # In production, you might fetch only this specific ticket
            add_jira_tickets_incrementally()
            
            return {
                "status": "processed",
                "ticket": issue_key,
                "action": "synced"
            }
        else:
            return {
                "status": "ignored",
                "ticket": issue_key,
                "reason": f"status_not_resolved ({issue_status})"
            }
            
    except Exception as e:
        print(f"[ERROR] Webhook processing failed: {e}")
        return {"status": "error", "message": str(e)}


# ============================================================================
# CONFIGURATION MANAGEMENT ENDPOINTS
# ============================================================================

@router.get("/config", response_model=JiraConfigResponse)
async def get_jira_config(
    current_user: dict = Depends(require_admin)
):
    """Get current Jira configuration (with masked token)."""
    try:
        config = config_service.get_masked_config()
        
        if not config:
            # Return default config if none exists
            return JiraConfigResponse(
                server="",
                email="",
                api_token_masked="****",
                project_keys=["PRI", "QAB"],
                max_issues=10000,
                date_filter="",
                is_configured=False,
                last_test=None,
                test_status=None
            )
        
        return JiraConfigResponse(
            server=config.get('server', ''),
            email=config.get('email', ''),
            api_token_masked=config.get('api_token_masked', '****'),
            project_keys=config.get('project_keys', ['PRI', 'QAB']),
            max_issues=config.get('max_issues', 10000),
            date_filter=config.get('date_filter', ''),
            is_configured=True,
            last_test=config.get('last_test'),
            test_status=config.get('test_status')
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get config: {str(e)}"
        )


@router.post("/config")
async def save_jira_config(
    config: JiraConfig = Body(...),
    current_user: dict = Depends(require_admin)
):
    """Save Jira configuration."""
    try:
        # Convert to dict
        config_data = {
            'server': config.server,
            'email': config.email,
            'api_token': config.api_token,
            'project_keys': config.project_keys,
            'max_issues': config.max_issues,
            'date_filter': config.date_filter or ""
        }
        
        # Test connection first
        test_result = config_service.test_connection(
            config.server,
            config.email,
            config.api_token
        )
        
        if not test_result['success']:
            raise HTTPException(
                status_code=400,
                detail=f"Connection test failed: {test_result['message']}"
            )
        
        # Save config
        config_data['last_test'] = datetime.now().isoformat()
        config_data['test_status'] = 'success'
        
        success = config_service.save_config(config_data)
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to save configuration"
            )
        
        return {
            "status": "success",
            "message": "Configuration saved successfully",
            "connection_test": test_result
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save config: {str(e)}"
        )


@router.post("/config/test")
async def test_jira_connection(
    config: JiraConfig = Body(...),
    current_user: dict = Depends(require_admin)
):
    """Test Jira connection without saving."""
    try:
        result = config_service.test_connection(
            config.server,
            config.email,
            config.api_token
        )
        
        if result['success']:
            return {
                "status": "success",
                "message": result['message'],
                "user": result.get('user'),
                "server": result.get('server')
            }
        else:
            return {
                "status": "error",
                "message": result['message'],
                "error": result.get('error')
            }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Connection test failed: {str(e)}"
        )


@router.patch("/config")
async def update_jira_config(
    config_update: JiraConfigUpdate = Body(...),
    current_user: dict = Depends(require_admin)
):
    """Partially update Jira configuration."""
    try:
        # Load existing config
        existing_config = config_service.load_config(decrypt_token=True)
        
        if not existing_config:
            raise HTTPException(
                status_code=404,
                detail="No existing configuration found. Use POST /config to create."
            )
        
        # Update only provided fields
        if config_update.server is not None:
            existing_config['server'] = config_update.server
        if config_update.email is not None:
            existing_config['email'] = config_update.email
        if config_update.api_token is not None:
            existing_config['api_token'] = config_update.api_token
        if config_update.project_keys is not None:
            existing_config['project_keys'] = config_update.project_keys
        if config_update.max_issues is not None:
            existing_config['max_issues'] = config_update.max_issues
        if config_update.date_filter is not None:
            existing_config['date_filter'] = config_update.date_filter
        
        # Save updated config
        success = config_service.save_config(existing_config)
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to update configuration"
            )
        
        return {
            "status": "success",
            "message": "Configuration updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update config: {str(e)}"
        )
