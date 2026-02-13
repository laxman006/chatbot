# -*- coding: utf-8 -*-
"""
Authentication and Authorization Module

Implements session-based authentication using backend session storage.
Microsoft Graph API is called ONLY during login, not on every request.

This solves the "random expiration" issue by:
1. Creating a session ONCE during login (Graph API called only here)
2. Validating sessions from MongoDB on every request (no Graph API calls)
3. Refreshing tokens in the background without user interruption
"""

from fastapi import Depends, HTTPException, status, Request, Cookie
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict
import logging
from typing import Set
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)

# OAuth2 Bearer token security scheme (for backward compatibility during migration)
security = HTTPBearer()

# Restricted admin allowlist (lowercase for consistent comparison)
ADMIN_EMAILS: Set[str] = {
    "chaitanya.malle@cloudfuze.com",
}

# Developer emails to exclude from dashboard statistics
# Can be overridden via EXCLUDED_DEVELOPER_EMAILS environment variable (comma-separated)
import os
_excluded_devs_env = os.getenv("EXCLUDED_DEVELOPER_EMAILS", "")
if _excluded_devs_env:
    EXCLUDED_DEVELOPER_EMAILS: Set[str] = {
        email.strip().lower() for email in _excluded_devs_env.split(",") if email.strip()
    }
else:
    # Default to admin emails if not specified
    EXCLUDED_DEVELOPER_EMAILS: Set[str] = ADMIN_EMAILS.copy()


def _normalize_email(email: str) -> str:
    """Normalize email for case-insensitive comparisons."""
    return (email or "").strip().lower()


async def get_current_user(
    request: Request,
    session_id: Optional[str] = Cookie(None, alias="session_id"),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
) -> Dict[str, str]:
    """
    Get authenticated user from session (NEW: session-based auth).
    Falls back to token-based auth for backward compatibility during migration.
    
    Priority:
    1. Session cookie (preferred - no Graph API call)
    2. Bearer token (legacy - calls Graph API)
    
    Args:
        request: FastAPI request object
        session_id: Session ID from cookie
        credentials: Optional Bearer token (for backward compatibility)
        
    Returns:
        Dictionary containing user_id, email, and name
        
    Raises:
        HTTPException: 401 if session/token is invalid or expired
    """
    from app.session_store import session_store
    
    # PRIORITY 1: Try session-based auth (no Graph API call)
    if session_id:
        try:
            await session_store.connect()
            session = await session_store.get_session(session_id)
            
            if session:
                # ✅ STRICT IDENTITY: Validate session has required fields
                user_email = session.get("user_email", "")
                user_id = session.get("user_id", "")
                user_name = session.get("user_name", "")
                
                if not user_email or not user_email.strip():
                    logger.error(f"[AUTH] Session {session_id[:8]}... has invalid email, rejecting")
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid session: missing user email"
                    )
                
                # ✅ IDENTITY RULE: Ensure user_id is email (migrate old sessions)
                if user_id != user_email.lower().strip():
                    logger.warning(f"[AUTH] Session user_id mismatch: {user_id} != {user_email}, using email")
                    user_id = user_email.lower().strip()
                
                # Check if token needs refresh (but don't block request)
                token_expires_at = session.get("token_expires_at")
                if token_expires_at and isinstance(token_expires_at, datetime):
                    from datetime import timedelta
                    now = datetime.utcnow()
                    margin = timedelta(minutes=5)
                    
                    if token_expires_at - now < margin:
                        # Token expiring soon - refresh in background (non-blocking)
                        logger.info(f"[AUTH] Token expiring soon for session {session_id[:8]}..., refreshing in background")
                        # Background refresh will be handled by token refresh endpoint
                
                logger.debug(f"[AUTH] User authenticated via session: {user_email}")
                return {
                    "id": user_id,  # ✅ Always email
                    "email": user_email,
                    "name": user_name if user_name else user_email.split("@")[0]
                }
        except Exception as e:
            logger.warning(f"[AUTH] Session validation failed: {e}, falling back to token auth")
    
    # PRIORITY 2: Fallback to token-based auth (for backward compatibility)
    if credentials:
        logger.warning("[AUTH] Using legacy token-based auth (should migrate to sessions)")
        return await _get_current_user_from_token(credentials.credentials)
    
    # No valid session or token
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized: No valid session or token. Please log in.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _get_current_user_from_token(access_token: str) -> Dict[str, str]:
    """
    Legacy token-based authentication (calls Microsoft Graph API).
    Used only as fallback during migration to session-based auth.
    
    This function will be removed once all clients use session cookies.
    """
    import httpx
    
    try:
        # Verify token with Microsoft Graph API
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10.0
            )
            
            if response.status_code == 401:
                logger.warning("Invalid or expired access token")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired access token",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            if response.status_code != 200:
                logger.error(f"Microsoft Graph API error: {response.status_code}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Failed to verify access token",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            user_info = response.json()
            
            # ✅ STRICT IDENTITY: Email is mandatory - fail fast if missing
            user_email = user_info.get("mail") or user_info.get("userPrincipalName", "")
            if not user_email or not user_email.strip():
                logger.error("[AUTH] Token auth failed: No email in Microsoft Graph response")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication failed: email missing",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            # Validate CloudFuze email domain
            if not user_email.endswith("@cloudfuze.com"):
                logger.warning(f"Access denied for non-CloudFuze email: {user_email}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied. Only CloudFuze company accounts are allowed.",
                )
            
            # ✅ IDENTITY RULE: Use email as user_id (stable, consistent)
            user_id = user_email.lower().strip()
            user_name = user_info.get("displayName", "")
            if not user_name or not user_name.strip():
                user_name = user_email.split("@")[0].replace(".", " ").title()
            
            logger.info(f"User authenticated successfully via token: {user_id} ({user_email})")
            
            return {
                "id": user_id,  # ✅ Always email
                "email": user_email,
                "name": user_name
            }
            
    except httpx.RequestError as e:
        logger.error(f"Network error during token verification: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable",
        )
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Unexpected error during authentication: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed",
        )


async def verify_user_access(
    user_id: str,
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    Verify that the authenticated user has access to the requested user resource.
    Prevents IDOR by ensuring user_id matches the authenticated user's ID.
    
    Args:
        user_id: The user_id from the URL path parameter
        current_user: The authenticated user from get_current_user dependency
        
    Returns:
        The current_user dictionary if access is allowed
        
    Raises:
        HTTPException: 403 if the user tries to access another user's resources
    """
    if current_user["id"] != user_id:
        logger.warning(
            f"Access denied: User {current_user['id']} attempted to access "
            f"resources belonging to user {user_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You can only access your own resources.",
        )
    
    return current_user


async def require_admin(
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    Verify that the authenticated user has administrative privileges.
    Currently, all CloudFuze email users are considered admins for internal tools.
    
    Args:
        current_user: The authenticated user from get_current_user dependency
        
    Returns:
        The current_user dictionary if user is an admin
        
    Raises:
        HTTPException: 403 if the user is not an admin
    """
    # For now, all CloudFuze users have admin access to these endpoints
    # In the future, you could check a specific admin list or database
    if not current_user["email"].endswith("@cloudfuze.com"):
        logger.warning(
            f"Admin access denied for user {current_user['id']} ({current_user['email']})"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required",
        )
    
    logger.info(f"Admin access granted to {current_user['id']} ({current_user['email']})")
    return current_user


async def require_restricted_admin(
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    Verify that the authenticated user is in the explicit admin allowlist.
    
    Admins: laxman.kadari@cloudfuze.com, chaitanya.malle@cloudfuze.com, nirosh.reddy@cloudfuze.com
    """
    email = _normalize_email(current_user.get("email", ""))
    
    if email not in ADMIN_EMAILS:
        logger.warning(
            f"Restricted admin access denied for user {current_user.get('id')} ({current_user.get('email')})"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative access required (restricted allowlist).",
        )
    
    logger.info(f"Restricted admin access granted to {current_user.get('id')} ({current_user.get('email')})")
    return current_user


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
) -> Optional[Dict[str, str]]:
    """
    Optional authentication - returns user if token is provided, None otherwise.
    Useful for endpoints that work with or without authentication.
    
    Args:
        credentials: Optional bearer token from Authorization header
        
    Returns:
        User dictionary if authenticated, None otherwise
    """
    if credentials is None:
        return None
    
    try:
        # Create a new credentials object to pass to get_current_user
        return await get_current_user(credentials)
    except HTTPException:
        # If authentication fails, return None instead of raising exception
        return None


def is_admin_email(email: str) -> bool:
    """
    Check if email is in the admin allowlist.
    
    Args:
        email: User's email address
        
    Returns:
        True if user is an admin
    """
    normalized = _normalize_email(email)
    return normalized in ADMIN_EMAILS


def is_cloudfuze_manage_team(user_email: str) -> bool:
    """
    Check if user is in CloudFuze Manage team.
    
    Args:
        user_email: User's email address
        
    Returns:
        True if user is in CloudFuze Manage team
    """
    from app.models.teams import get_team_by_member_email
    
    team = get_team_by_member_email(user_email)
    return team == "CloudFuze Manage"


def can_access_api_research(user_email: str) -> bool:
    """
    Check if user can access Cloud API Research feature.
    
    Access is granted to:
    - CloudFuze Manage team members
    - Admin users (from ADMIN_EMAILS allowlist)
    
    Args:
        user_email: User's email address
        
    Returns:
        True if user has access to API research feature
    """
    # Check if admin
    if is_admin_email(user_email):
        logger.debug(f"[API RESEARCH ACCESS] Admin access granted: {user_email}")
        return True
    
    # Check if CloudFuze Manage team member
    if is_cloudfuze_manage_team(user_email):
        logger.debug(f"[API RESEARCH ACCESS] Manage team access granted: {user_email}")
        return True
    
    logger.debug(f"[API RESEARCH ACCESS] Access denied: {user_email}")
    return False

