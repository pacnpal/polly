"""
Enhanced Security Middleware
Consolidated security measures for blocking attack patterns and input validation.
"""

import logging
import re
from typing import Set
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class EnhancedSecurityMiddleware(BaseHTTPMiddleware):
    """
    Consolidated security middleware that combines attack blocking and input validation.
    This replaces the separate AttackBlockingMiddleware and enhances InputSanitizationMiddleware.
    """
    
    # Known malicious paths that should be blocked immediately
    BLOCKED_PATHS: Set[str] = {
        # PHPUnit RCE paths
        "/vendor/phpunit/phpunit/src/Util/PHP/eval-stdin.php",
        "/vendor/phpunit/phpunit/Util/PHP/eval-stdin.php",
        "/vendor/phpunit/src/Util/PHP/eval-stdin.php",
        "/vendor/phpunit/Util/PHP/eval-stdin.php",
        "/phpunit/phpunit/src/Util/PHP/eval-stdin.php",
        "/phpunit/phpunit/Util/PHP/eval-stdin.php",
        "/phpunit/src/Util/PHP/eval-stdin.php",
        "/phpunit/Util/PHP/eval-stdin.php",
        "/lib/phpunit/phpunit/src/Util/PHP/eval-stdin.php",
        "/lib/phpunit/phpunit/Util/PHP/eval-stdin.php",
        "/lib/phpunit/src/Util/PHP/eval-stdin.php",
        "/lib/phpunit/Util/PHP/eval-stdin.php",
        "/lib/vendor/phpunit/phpunit/src/Util/PHP/eval-stdin.php",
        "/laravel/vendor/phpunit/phpunit/src/Util/PHP/eval-stdin.php",
        "/www/vendor/phpunit/phpunit/src/Util/PHP/eval-stdin.php",
        "/ws/vendor/phpunit/phpunit/src/Util/PHP/eval-stdin.php",
        "/yii/vendor/phpunit/phpunit/src/Util/PHP/eval-stdin.php",
        "/zend/vendor/phpunit/phpunit/src/Util/PHP/eval-stdin.php",
        "/ws/ec/vendor/phpunit/phpunit/src/Util/PHP/eval-stdin.php",
        "/V2/vendor/phpunit/phpunit/src/Util/PHP/eval-stdin.php",
        "/tests/vendor/phpunit/phpunit/src/Util/PHP/eval-stdin.php",
        "/test/vendor/phpunit/phpunit/src/Util/PHP/eval-stdin.php",
        
        # Common attack paths
        "/hello.world",
        "/.env",
        "/wp-admin/",
        "/wp-login.php",
        "/admin/",
        "/phpmyadmin/",
        "/mysql/",
        "/config.php",
        "/wp-config.php",
        "/xmlrpc.php",
    }
    
    # Malicious patterns for comprehensive detection
    MALICIOUS_PATTERNS = [
        # PHP RFI/LFI patterns
        r"allow_url_include\s*=\s*1",
        r"auto_prepend_file\s*=\s*php://",
        r"php://input",
        r"php://filter",
        r"data://",
        r"expect://",
        
        # SQL injection patterns
        r"(?i)(union\s+select|drop\s+table|delete\s+from|insert\s+into)",
        r"(?i)(update\s+.*\s+set)",
        
        # XSS patterns
        r"(?i)(<script[^>]*>|javascript:|on\w+\s*=)",
        r"(?i)(eval\s*\()",
        
        # Command injection patterns
        r"(?i)(;|\||&|`|\$\(|\${)",
        r";\s*(cat|ls|pwd|whoami|id|uname)",
        r"\|\s*(cat|ls|pwd|whoami|id|uname)",
        r"&&\s*(cat|ls|pwd|whoami|id|uname)",
        
        # Path traversal patterns
        r"(\.\.\/|\.\.\\|%2e%2e%2f|%2e%2e%5c)",
    ]
    
    def __init__(self, app):
        super().__init__(app)
        self.compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self.MALICIOUS_PATTERNS]
    
    def get_client_ip(self, request: Request) -> str:
        """Get client IP address, handling proxies"""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        return request.client.host if request.client else "unknown"
    
    def analyze_request(self, request: Request) -> tuple[bool, str, str]:
        """
        Analyze request for malicious patterns.
        Returns: (is_malicious, severity, reason)
        """
        
        # Check for blocked paths (highest priority)
        if request.url.path in self.BLOCKED_PATHS:
            return True, "HIGH", f"Known malicious path: {request.url.path}"
        
        # Check for PHPUnit RCE attacks with any path prefix
        if "vendor/phpunit/phpunit/src/Util/PHP/eval-stdin.php" in request.url.path:
            return True, "HIGH", f"PHPUnit RCE attack detected: {request.url.path}"
        
        # Check for other PHPUnit variations with path prefixes
        phpunit_patterns = [
            "vendor/phpunit/phpunit/Util/PHP/eval-stdin.php",
            "vendor/phpunit/src/Util/PHP/eval-stdin.php", 
            "vendor/phpunit/Util/PHP/eval-stdin.php",
            "phpunit/phpunit/src/Util/PHP/eval-stdin.php",
            "phpunit/src/Util/PHP/eval-stdin.php",
            "lib/phpunit/phpunit/src/Util/PHP/eval-stdin.php"
        ]
        
        for pattern in phpunit_patterns:
            if pattern in request.url.path:
                return True, "HIGH", f"PHPUnit RCE attack detected: {request.url.path}"
        
        # Check for WordPress attacks with path prefixes
        wordpress_patterns = [
            "wp-admin/",
            "wp-login.php",
            "wp-config.php",
            "xmlrpc.php"
        ]
        
        for pattern in wordpress_patterns:
            if pattern in request.url.path:
                return True, "HIGH", f"WordPress attack detected: {request.url.path}"
        
        # Check for common admin/config file attacks with path prefixes
        admin_patterns = [
            "phpmyadmin/",
            "admin/",
            "panel/",
            ".env"
        ]
        
        for pattern in admin_patterns:
            if pattern in request.url.path:
                return True, "MEDIUM", f"Admin/config file attack detected: {request.url.path}"
        
        # Check for PHP file extensions (we're a Python app)
        if request.url.path.endswith('.php'):
            return True, "HIGH", f"PHP file request blocked: {request.url.path}"
        
        # Check query parameters for malicious patterns
        query_string = str(request.url.query)
        if query_string:
            for pattern in self.compiled_patterns:
                if pattern.search(query_string):
                    # Determine severity based on pattern type
                    if any(keyword in pattern.pattern.lower() for keyword in ['php://', 'allow_url_include', 'union select']):
                        severity = "HIGH"
                    elif any(keyword in pattern.pattern.lower() for keyword in ['script', 'javascript']):
                        severity = "MEDIUM"
                    else:
                        severity = "LOW"
                    
                    return True, severity, f"Malicious query pattern detected: {query_string[:100]}"
        
        # Check for URL-encoded malicious patterns in path
        path_decoded = request.url.path.replace('%2e', '.').replace('%2f', '/').replace('%5c', '\\')
        for pattern in self.compiled_patterns:
            if pattern.search(path_decoded):
                return True, "MEDIUM", f"Malicious pattern in path: {request.url.path}"
        
        return False, "NONE", ""
    
    async def dispatch(self, request: Request, call_next):
        """Process request with enhanced security checks"""
        
        try:
            # Skip checks for static files and health checks
            if (request.url.path.startswith("/static/") or 
                request.url.path == "/health"):
                return await call_next(request)
            
            client_ip = self.get_client_ip(request)
            
            # Check if IP is already blocked
            from .ip_blocker import get_ip_blocker
            ip_blocker = get_ip_blocker()
            
            if ip_blocker.is_blocked(client_ip):
                logger.warning(f"BLOCKED IP attempted access: {client_ip} -> {request.url.path}")
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Access denied"}
                )
            
            # Analyze request for threats
            is_malicious, severity, reason = self.analyze_request(request)
            
            if is_malicious:
                # Log with appropriate level - WARNING will trigger your notification system
                logger.warning(f"SECURITY BLOCK [{severity}] from {client_ip}: {reason}")
                
                # Record violation and potentially block IP
                should_block = ip_blocker.record_violation(client_ip, severity)
                if should_block:
                    logger.critical(f"IP {client_ip} has been BLOCKED due to repeated violations")
                
                # Return 403 Forbidden for blocked requests
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Access denied"}
                )
            
            return await call_next(request)
            
        except Exception as e:
            # Catch any unexpected errors in security middleware to prevent crashes
            client_ip = self.get_client_ip(request)
            logger.error(f"Security middleware error from {client_ip}: {e}")
            
            # Continue processing the request rather than crashing
            return await call_next(request)
