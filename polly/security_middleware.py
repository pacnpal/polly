"""
Security Middleware
Additional security measures for the Polly application.
"""

import time
import logging
from collections import defaultdict, deque
from typing import Dict, Deque
from fastapi import Request, HTTPException
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware to prevent abuse"""
    
    def __init__(self, app, requests_per_minute: int = 60, requests_per_hour: int = 1000):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.minute_requests: Dict[str, Deque[float]] = defaultdict(deque)
        self.hour_requests: Dict[str, Deque[float]] = defaultdict(deque)
    
    def get_client_ip(self, request: Request) -> str:
        """Get client IP address, handling proxies"""
        # Check for forwarded headers (common in production)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fallback to direct client IP
        return request.client.host if request.client else "unknown"
    
    def is_rate_limited(self, client_ip: str) -> bool:
        """Check if client is rate limited"""
        current_time = time.time()
        
        # Clean old requests (older than 1 hour)
        minute_cutoff = current_time - 60
        hour_cutoff = current_time - 3600
        
        # Clean minute requests
        while (self.minute_requests[client_ip] and 
               self.minute_requests[client_ip][0] < minute_cutoff):
            self.minute_requests[client_ip].popleft()
        
        # Clean hour requests
        while (self.hour_requests[client_ip] and 
               self.hour_requests[client_ip][0] < hour_cutoff):
            self.hour_requests[client_ip].popleft()
        
        # Check limits
        minute_count = len(self.minute_requests[client_ip])
        hour_count = len(self.hour_requests[client_ip])
        
        if minute_count >= self.requests_per_minute:
            logger.info(f"Rate limit exceeded (per minute) for IP {client_ip}: {minute_count} requests")
            return True
        
        if hour_count >= self.requests_per_hour:
            logger.info(f"Rate limit exceeded (per hour) for IP {client_ip}: {hour_count} requests")
            return True
        
        # Add current request
        self.minute_requests[client_ip].append(current_time)
        self.hour_requests[client_ip].append(current_time)
        
        return False
    
    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting"""
        try:
            # Skip rate limiting for static files and health checks
            if (request.url.path.startswith("/static/") or 
                request.url.path == "/health"):
                return await call_next(request)
            
            client_ip = self.get_client_ip(request)
            
            if self.is_rate_limited(client_ip):
                logger.info(f"Rate limit exceeded for {client_ip} on {request.url.path}")
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Please try again later."}
                )
            
            return await call_next(request)
            
        except Exception as e:
            # Catch any unexpected errors in rate limiting to prevent crashes
            client_ip = self.get_client_ip(request) if hasattr(request, 'client') else "unknown"
            logger.error(f"Rate limiting middleware error from {client_ip}: {e}")
            
            # Continue processing the request rather than crashing
            return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses"""
    
    async def dispatch(self, request: Request, call_next):
        """Add security headers to response"""
        response = await call_next(request)
        
        # Content Security Policy
        csp_policy = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net https://challenges.cloudflare.com https://static.cloudflareinsights.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https://cdn.discordapp.com https://discord.com; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        
        # Security headers
        security_headers = {
            "Content-Security-Policy": csp_policy,
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains"
        }
        
        # Add headers to response
        for header, value in security_headers.items():
            response.headers[header] = value
        
        return response


# InputSanitizationMiddleware has been consolidated into EnhancedSecurityMiddleware
# in enhanced_security_middleware.py to avoid duplication and improve efficiency
