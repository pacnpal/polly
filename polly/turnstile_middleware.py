"""
Cloudflare Turnstile Security Middleware
Replaces aggressive IP blocking with smart bot detection using Cloudflare Turnstile.
"""

import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import httpx
from decouple import config

logger = logging.getLogger(__name__)


class TurnstileSecurityMiddleware(BaseHTTPMiddleware):
    """
    Security middleware using Cloudflare Turnstile for bot protection.
    Much more user-friendly than IP blocking - only challenges suspicious behavior.
    """

    def __init__(self, app):
        super().__init__(app)
        self.enabled = config("TURNSTILE_ENABLED", default=True, cast=bool)
        self.site_key = config(
            "TURNSTILE_SITE_KEY", default="1x00000000000000000000AA"
        )  # Test key
        self.secret_key = config(
            "TURNSTILE_SECRET_KEY", default="1x0000000000000000000000000000000AA"
        )  # Test key

        # Endpoints that require Turnstile verification
        self.protected_endpoints = {
            "/htmx/create-poll",
            "/htmx/edit-poll",
            "/htmx/delete-poll",
            "/admin/",
        }

        # Endpoints that are always allowed (no verification needed)
        self.allowed_endpoints = {
            "/static/",
            "/health",
            "/htmx/polls-realtime",  # Your frequent polling endpoint
            "/htmx/polls",
            "/htmx/servers",
            "/htmx/stats",
            "/",
        }

    def get_client_ip(self, request: Request) -> str:
        """Get client IP address, handling proxies"""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        return request.client.host if request.client else "unknown"

    async def verify_turnstile_token(self, token: str, client_ip: str) -> bool:
        """
        Verify Turnstile token with Cloudflare's API
        """
        if not token:
            return False

        # Use test keys for development - these always pass
        if self.secret_key == "1x0000000000000000000000000000000AA":
            logger.info(
                f"Using Turnstile test key - auto-passing verification for {client_ip}"
            )
            return True

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                    data={
                        "secret": self.secret_key,
                        "response": token,
                        "remoteip": client_ip,
                    },
                )

                if response.status_code == 200:
                    result = response.json()
                    success = result.get("success", False)

                    if success:
                        logger.info(
                            f"Turnstile verification successful for {client_ip}"
                        )
                    else:
                        error_codes = result.get("error-codes", [])
                        logger.warning(
                            f"Turnstile verification failed for {client_ip}: {error_codes}"
                        )

                    return success
                else:
                    logger.error(f"Turnstile API error: {response.status_code}")
                    return False

        except Exception as e:
            logger.error(f"Turnstile verification error: {e}")
            return False

    def needs_verification(self, request: Request) -> bool:
        """
        Determine if this request needs Turnstile verification
        """
        path = request.url.path

        # Always allow certain endpoints
        for allowed in self.allowed_endpoints:
            if path.startswith(allowed):
                return False

        # Require verification for protected endpoints
        for protected in self.protected_endpoints:
            if path.startswith(protected):
                return True

        # For POST requests to forms, require verification
        if request.method == "POST" and not path.startswith("/static/"):
            return True

        return False

    async def dispatch(self, request: Request, call_next):
        """Process request with Turnstile security checks"""

        try:
            # If Turnstile is disabled, allow all requests through
            if not self.enabled:
                logger.debug("Turnstile middleware disabled - allowing all requests")
                return await call_next(request)

            client_ip = self.get_client_ip(request)

            # Skip verification for allowed endpoints
            if not self.needs_verification(request):
                return await call_next(request)

            # Check for Turnstile token in form data or headers
            turnstile_token = None

            if request.method == "POST":
                # Try to get token from form data
                try:
                    form_data = await request.form()
                    turnstile_token = form_data.get("cf-turnstile-response")
                except:
                    pass

            # Also check headers (for AJAX requests and passive tokens)
            if not turnstile_token:
                turnstile_token = request.headers.get("cf-turnstile-response")

            # Check for passive token from non-interactive widget
            if not turnstile_token:
                turnstile_token = request.headers.get("x-turnstile-token")

            # Verify the token if present
            if turnstile_token:
                is_valid = await self.verify_turnstile_token(turnstile_token, client_ip)
                if is_valid:
                    logger.debug(
                        f"Valid Turnstile token from {client_ip} for {request.url.path}"
                    )
                    return await call_next(request)
                else:
                    logger.warning(
                        f"Invalid Turnstile token from {client_ip} for {request.url.path}"
                    )
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Bot verification failed - invalid token"},
                    )
            else:
                # STRICT MODE: Block requests without tokens to protected endpoints
                logger.warning(
                    f"No Turnstile token provided from {client_ip} for protected endpoint {request.url.path} - BLOCKING"
                )
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Bot verification required - no token provided"},
                )

        except Exception as e:
            # Don't crash on security middleware errors
            logger.error(f"Turnstile middleware error: {e}")
            return await call_next(request)
