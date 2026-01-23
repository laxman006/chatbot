# -*- coding: utf-8 -*-
"""
Jira Sync API Endpoints
"""
from fastapi import APIRouter, HTTPException, Depends, Body
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

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
        
        # Get pre-sync count
        vectorstore = load_jira_vectorstore()
        pre_count = vectorstore._collection.count() if vectorstore else 0
        
        # Run incremental sync
        result = add_jira_tickets_incrementally()
        
        if result:
            post_count = result._collection.count()
            new_tickets = post_count - pre_count
            
            stats = get_sync_stats()
            
            return SyncResponse(
                status="success",
                message=f"Successfully synced {new_tickets} new/updated tickets",
                last_sync=stats.get('last_sync_readable'),
                total_documents=post_count,
                new_tickets=new_tickets
            )
        else:
            stats = get_sync_stats()
            return SyncResponse(
                status="no_updates",
                message="No new tickets to sync",
                last_sync=stats.get('last_sync_readable'),
                total_documents=pre_count,
                new_tickets=0
            )
            
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Sync failed: {str(e)}"
        )


@router.get("/sync/status")
async def get_sync_status(
    current_user: dict = Depends(require_admin)
):
    """Get Jira sync status and statistics with alerts."""
    try:
        stats = get_sync_stats()
        vectorstore = load_jira_vectorstore()
        total_docs = vectorstore._collection.count() if vectorstore else 0
        
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
            "alerts": alerts
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get status: {str(e)}"
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
