# -*- coding: utf-8 -*-
"""
Global admin path guard middleware.

Rejects requests to /admin/* unless the session user is in the admin allowlist.
Use as defense-in-depth alongside require_admin / require_restricted_admin on each route.

To enable: in server.py after creating the FastAPI app, add:

    from app.admin_middleware import AdminPathMiddleware
    app.add_middleware(AdminPathMiddleware)
"""

import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class AdminPathMiddleware(BaseHTTPMiddleware):
    """Reject /admin/* requests if session user is not in admin allowlist."""

    # Explicit prefixes only (no substring "in path" to avoid bypass)
    ADMIN_PREFIXES = ("/admin", "/api/admin")

    async def dispatch(self, request: Request, call_next):
        path = request.scope.get("path") or ""
        if not any(path.startswith(prefix) for prefix in self.ADMIN_PREFIXES):
            return await call_next(request)

        session_id = request.cookies.get("session_id")
        if not session_id:
            logger.warning("[ADMIN_MIDDLEWARE] /admin request with no session_id cookie")
            return JSONResponse(
                status_code=403,
                content={"detail": "Administrative access required (no session)."},
            )

        try:
            from app.session_store import session_store
            from app.auth import is_admin_email

            await session_store.connect()
            session = await session_store.get_session(session_id)
            if not session:
                logger.warning("[ADMIN_MIDDLEWARE] /admin request with invalid session")
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Administrative access required (invalid session)."},
                )
            user_email = (session.get("user_email") or "").strip().lower()
            if not user_email:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Administrative access required (missing user)."},
                )
            if not is_admin_email(user_email):
                logger.warning(f"[ADMIN_MIDDLEWARE] /admin access denied for {user_email}")
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Administrative access required (restricted allowlist)."},
                )
        except Exception as e:
            logger.exception("[ADMIN_MIDDLEWARE] Error checking admin access: %s", e)
            return JSONResponse(
                status_code=503,
                content={"detail": "Authorization check failed."},
            )

        return await call_next(request)
