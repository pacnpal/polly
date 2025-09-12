"""
Authentication Middleware
Handles token validation and graceful redirects for expired sessions.
"""

import logging
from fastapi import Request
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from .auth import verify_token

logger = logging.getLogger(__name__)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """
    Middleware to handle token validation and provide graceful redirects
    for expired/invalid tokens instead of showing error messages.
    """

    def __init__(self, app):
        super().__init__(app)

    def is_protected_route(self, path: str) -> bool:
        """Check if the route requires authentication"""
        protected_patterns = ["/dashboard", "/htmx/"]
        return any(path.startswith(pattern) for pattern in protected_patterns)

    def is_htmx_request(self, request: Request) -> bool:
        """Check if request is an HTMX request"""
        return request.headers.get("HX-Request") == "true"

    def is_api_request(self, path: str) -> bool:
        """Check if request is an API request"""
        return path.startswith("/api/") or path.startswith("/htmx/")

    async def dispatch(self, request: Request, call_next):
        """Process request with authentication checking"""
        try:
            # Skip authentication check for non-protected routes
            if not self.is_protected_route(request.url.path):
                return await call_next(request)

            # Skip for static files and health checks
            if (
                request.url.path.startswith("/static/")
                or request.url.path == "/health"
                or request.url.path == "/login"
                or request.url.path.startswith("/auth/")
            ):
                return await call_next(request)

            # Get token from cookie
            token = request.cookies.get("access_token")

            if not token:
                path = request.url.path
                logger.info(f"No token found for protected route: {path}")
                return self._handle_unauthenticated(request)

            # Verify token
            payload = verify_token(token)
            if not payload:
                path = request.url.path
                logger.info(f"Invalid/expired token for route: {path}")
                return self._handle_unauthenticated(request)

            # Token is valid, continue with request
            return await call_next(request)

        except Exception as e:
            try:
                # Safely extract error message, avoiding problematic characters
                err_msg = repr(str(e)[:200])  # Limit length and use repr for safety
            except Exception:
                err_msg = "unprintable_exception"
            logger.error(f"Authentication middleware error: {err_msg}")
            # Continue processing rather than crashing
            return await call_next(request)

    def _handle_unauthenticated(self, request: Request):
        """Handle unauthenticated requests with appropriate response"""
        path = request.url.path

        # For HTMX requests, return an HX-Redirect header
        if self.is_htmx_request(request):
            response = JSONResponse(
                status_code=401, content={"detail": "Session expired"}
            )
            response.headers["HX-Redirect"] = "/login"
            return response

        # For API requests, return JSON error
        elif self.is_api_request(path):
            return JSONResponse(
                status_code=401, content={"detail": "Authentication required"}
            )

        # For regular web requests, redirect to login
        else:
            return RedirectResponse(url="/login", status_code=302)
