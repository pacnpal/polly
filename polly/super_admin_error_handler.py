"""
Enhanced Super Admin Error Handling System
Provides comprehensive error categorization, standardized responses, and improved user experience.
"""

import logging
import traceback
import uuid
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List, Callable
from functools import wraps
from dataclasses import dataclass, asdict
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse

logger = logging.getLogger(__name__)


class SuperAdminErrorType(Enum):
    """Error categorization for super admin operations"""
    VALIDATION = "validation"
    PERMISSION = "permission"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    DEPENDENCY = "dependency"
    SYSTEM = "system"
    RATE_LIMIT = "rate_limit"
    MAINTENANCE = "maintenance"


class ErrorSeverity(Enum):
    """Error severity levels for proper handling and user feedback"""
    LOW = "low"           # Informational, user can continue
    MEDIUM = "medium"     # Warning, operation failed but recoverable
    HIGH = "high"         # Error, operation failed, needs attention
    CRITICAL = "critical" # Critical system error, requires immediate action


@dataclass
class SuperAdminErrorDetails:
    """Detailed error information for specific error context"""
    field: Optional[str] = None
    value: Optional[Any] = None
    expected: Optional[str] = None
    constraints: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None


@dataclass
class SuperAdminError(Exception):
    """Structured super admin error with comprehensive information"""
    error_type: SuperAdminErrorType
    code: str
    message: str
    severity: ErrorSeverity = ErrorSeverity.MEDIUM
    details: Optional[SuperAdminErrorDetails] = None
    suggestions: Optional[List[str]] = None
    retry_after: Optional[int] = None
    correlation_id: Optional[str] = None
    original_error: Optional[str] = None
    
    def __post_init__(self):
        if self.correlation_id is None:
            self.correlation_id = str(uuid.uuid4())
        super().__init__(self.message)


@dataclass
class SuperAdminResponseMeta:
    """Metadata for super admin responses"""
    timestamp: str
    request_id: str
    processing_time_ms: Optional[int] = None
    version: str = "1.0"


class SuperAdminErrorHandler:
    """Central error handling utility for super admin operations"""
    
    def __init__(self):
        self.error_count = 0
        self.error_history = []
    
    def create_error(
        self,
        error_type: SuperAdminErrorType,
        code: str,
        message: str,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        details: Optional[Dict[str, Any]] = None,
        suggestions: Optional[List[str]] = None,
        retry_after: Optional[int] = None,
        original_error: Optional[Exception] = None
    ) -> SuperAdminError:
        """Create a structured super admin error"""
        
        error_details = None
        if details:
            error_details = SuperAdminErrorDetails(**details)
        
        original_error_str = None
        if original_error:
            original_error_str = str(original_error)
        
        error = SuperAdminError(
            error_type=error_type,
            code=code,
            message=message,
            severity=severity,
            details=error_details,
            suggestions=suggestions,
            retry_after=retry_after,
            original_error=original_error_str
        )
        
        self.error_count += 1
        self.error_history.append(error)
        
        return error
    
    def format_success_response(
        self,
        data: Any,
        request_id: str,
        processing_time_ms: Optional[int] = None
    ) -> Dict[str, Any]:
        """Format a standardized success response"""
        meta = SuperAdminResponseMeta(
            timestamp=datetime.utcnow().isoformat() + "Z",
            request_id=request_id,
            processing_time_ms=processing_time_ms
        )
        
        return {
            "success": True,
            "data": data,
            "meta": asdict(meta)
        }
    
    def format_error_response(
        self,
        error: SuperAdminError,
        request_id: str,
        processing_time_ms: Optional[int] = None
    ) -> Dict[str, Any]:
        """Format a standardized error response"""
        meta = SuperAdminResponseMeta(
            timestamp=datetime.utcnow().isoformat() + "Z",
            request_id=request_id,
            processing_time_ms=processing_time_ms
        )
        
        error_data = {
            "type": error.error_type.value,
            "severity": error.severity.value,
            "code": error.code,
            "message": error.message,
            "correlation_id": error.correlation_id
        }
        
        # Add optional fields
        if error.details:
            error_data["details"] = asdict(error.details)
        if error.suggestions:
            error_data["suggestions"] = error.suggestions
        if error.retry_after:
            error_data["retry_after"] = error.retry_after
        
        return {
            "success": False,
            "error": error_data,
            "meta": asdict(meta)
        }
    
    def get_http_status_code(self, error: SuperAdminError) -> int:
        """Get appropriate HTTP status code for error type"""
        status_map = {
            SuperAdminErrorType.VALIDATION: 400,
            SuperAdminErrorType.PERMISSION: 403,
            SuperAdminErrorType.NOT_FOUND: 404,
            SuperAdminErrorType.CONFLICT: 409,
            SuperAdminErrorType.RATE_LIMIT: 429,
            SuperAdminErrorType.DEPENDENCY: 502,
            SuperAdminErrorType.MAINTENANCE: 503,
            SuperAdminErrorType.SYSTEM: 500
        }
        return status_map.get(error.error_type, 500)
    
    def log_error(
        self,
        error: SuperAdminError,
        request: Optional[Request] = None,
        admin_user_id: Optional[str] = None,
        operation: Optional[str] = None
    ):
        """Log error with structured context"""
        log_context = {
            "error_type": error.error_type.value,
            "error_code": error.code,
            "severity": error.severity.value,
            "correlation_id": error.correlation_id,
            "admin_user_id": admin_user_id,
            "operation": operation
        }
        
        if request:
            log_context.update({
                "endpoint": str(request.url.path),
                "method": request.method,
                "user_agent": request.headers.get("user-agent"),
                "ip_address": request.client.host if request.client else None
            })
        
        if error.details:
            log_context["error_details"] = asdict(error.details)
        
        # Log with appropriate level based on severity
        if error.severity == ErrorSeverity.CRITICAL:
            logger.critical(error.message, extra=log_context)
        elif error.severity == ErrorSeverity.HIGH:
            logger.error(error.message, extra=log_context)
        elif error.severity == ErrorSeverity.MEDIUM:
            logger.warning(error.message, extra=log_context)
        else:
            logger.info(error.message, extra=log_context)


# Global error handler instance
super_admin_error_handler = SuperAdminErrorHandler()


# Validation utilities
class SuperAdminValidator:
    """Input validation utilities for super admin operations"""
    
    @staticmethod
    def validate_poll_id(poll_id: Any) -> Optional[SuperAdminError]:
        """Validate poll ID format and value"""
        if not isinstance(poll_id, int):
            try:
                poll_id = int(poll_id)
            except (ValueError, TypeError):
                return super_admin_error_handler.create_error(
                    error_type=SuperAdminErrorType.VALIDATION,
                    code="INVALID_POLL_ID_FORMAT",
                    message="Poll ID must be a valid integer",
                    details={
                        "field": "poll_id",
                        "value": poll_id,
                        "expected": "positive integer"
                    },
                    suggestions=["Provide a valid poll ID as an integer"]
                )
        
        if poll_id <= 0:
            return super_admin_error_handler.create_error(
                error_type=SuperAdminErrorType.VALIDATION,
                code="INVALID_POLL_ID_VALUE",
                message="Poll ID must be a positive integer",
                details={
                    "field": "poll_id",
                    "value": poll_id,
                    "expected": "positive integer greater than 0"
                },
                suggestions=["Provide a poll ID greater than 0"]
            )
        
        return None
    
    @staticmethod
    def validate_poll_ids_list(poll_ids: Any) -> Optional[SuperAdminError]:
        """Validate list of poll IDs for bulk operations"""
        if not isinstance(poll_ids, list):
            return super_admin_error_handler.create_error(
                error_type=SuperAdminErrorType.VALIDATION,
                code="INVALID_POLL_IDS_FORMAT",
                message="Poll IDs must be provided as a list",
                details={
                    "field": "poll_ids",
                    "value": type(poll_ids).__name__,
                    "expected": "list of integers"
                },
                suggestions=["Provide poll IDs as a list: [1, 2, 3, ...]"]
            )
        
        if not poll_ids:
            return super_admin_error_handler.create_error(
                error_type=SuperAdminErrorType.VALIDATION,
                code="EMPTY_POLL_IDS_LIST",
                message="At least one poll ID must be provided",
                details={
                    "field": "poll_ids",
                    "value": poll_ids,
                    "expected": "non-empty list of integers"
                },
                suggestions=["Provide at least one valid poll ID"]
            )
        
        if len(poll_ids) > 1000:  # Bulk operation limit
            return super_admin_error_handler.create_error(
                error_type=SuperAdminErrorType.VALIDATION,
                code="TOO_MANY_POLL_IDS",
                message=f"Too many poll IDs provided. Maximum allowed: 1000, received: {len(poll_ids)}",
                details={
                    "field": "poll_ids",
                    "value": len(poll_ids),
                    "expected": "maximum 1000 poll IDs"
                },
                suggestions=["Split the operation into smaller batches", "Use filters to reduce the selection"]
            )
        
        # Validate individual poll IDs
        for i, poll_id in enumerate(poll_ids):
            error = SuperAdminValidator.validate_poll_id(poll_id)
            if error:
                if error.details:
                    error.details.field = f"poll_ids[{i}]"
                error.code = f"INVALID_POLL_ID_IN_LIST_{i}"
                error.message = f"Invalid poll ID at position {i}: {error.message}"
                return error
        
        return None
    
    @staticmethod
    def validate_pagination_params(limit: Any, offset: Any) -> Optional[SuperAdminError]:
        """Validate pagination parameters"""
        # Validate limit
        if not isinstance(limit, int):
            try:
                limit = int(limit)
            except (ValueError, TypeError):
                return super_admin_error_handler.create_error(
                    error_type=SuperAdminErrorType.VALIDATION,
                    code="INVALID_LIMIT_FORMAT",
                    message="Limit must be a valid integer",
                    details={
                        "field": "limit",
                        "value": limit,
                        "expected": "integer between 1 and 200"
                    }
                )
        
        if not (1 <= limit <= 200):
            return super_admin_error_handler.create_error(
                error_type=SuperAdminErrorType.VALIDATION,
                code="INVALID_LIMIT_VALUE",
                message="Limit must be between 1 and 200",
                details={
                    "field": "limit",
                    "value": limit,
                    "expected": "integer between 1 and 200"
                }
            )
        
        # Validate offset
        if not isinstance(offset, int):
            try:
                offset = int(offset)
            except (ValueError, TypeError):
                return super_admin_error_handler.create_error(
                    error_type=SuperAdminErrorType.VALIDATION,
                    code="INVALID_OFFSET_FORMAT",
                    message="Offset must be a valid integer",
                    details={
                        "field": "offset",
                        "value": offset,
                        "expected": "non-negative integer"
                    }
                )
        
        if offset < 0:
            return super_admin_error_handler.create_error(
                error_type=SuperAdminErrorType.VALIDATION,
                code="INVALID_OFFSET_VALUE",
                message="Offset must be non-negative",
                details={
                    "field": "offset",
                    "value": offset,
                    "expected": "integer >= 0"
                }
            )
        
        return None


# Decorator for automatic error handling
def handle_super_admin_errors(
    operation_name: Optional[str] = None,
    return_html: bool = False
):
    """Decorator for automatic super admin error handling with standardized responses"""
    
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = datetime.now()
            request_id = str(uuid.uuid4())
            
            # Extract request and user info from args/kwargs
            request = None
            admin_user_id = None
            
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if 'current_user' in kwargs and hasattr(kwargs['current_user'], 'id'):
                admin_user_id = kwargs['current_user'].id
            
            try:
                result = await func(*args, **kwargs)
                
                # Calculate processing time
                processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
                
                # If result is already a Response object, return as-is
                if isinstance(result, (JSONResponse, HTMLResponse)):
                    return result
                
                # Format success response for JSON endpoints
                if not return_html:
                    formatted_result = super_admin_error_handler.format_success_response(
                        data=result,
                        request_id=request_id,
                        processing_time_ms=processing_time
                    )
                    return JSONResponse(content=formatted_result)
                
                return result
                
            except SuperAdminError as e:
                # Handle our custom errors
                processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
                
                super_admin_error_handler.log_error(
                    error=e,
                    request=request,
                    admin_user_id=admin_user_id,
                    operation=operation_name or func.__name__
                )
                
                if return_html:
                    # Return HTML error for HTMX endpoints
                    error_html = f"""
                    <div class='alert alert-{e.severity.value}' role='alert'>
                        <strong>{e.code}:</strong> {e.message}
                        {f"<br><small>Correlation ID: {e.correlation_id}</small>" if e.correlation_id else ""}
                    </div>
                    """
                    return HTMLResponse(
                        content=error_html,
                        status_code=super_admin_error_handler.get_http_status_code(e)
                    )
                
                # Return JSON error for API endpoints
                error_response = super_admin_error_handler.format_error_response(
                    error=e,
                    request_id=request_id,
                    processing_time_ms=processing_time
                )
                
                return JSONResponse(
                    content=error_response,
                    status_code=super_admin_error_handler.get_http_status_code(e)
                )
                
            except HTTPException as e:
                # Handle FastAPI HTTP exceptions
                processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
                
                super_admin_error = super_admin_error_handler.create_error(
                    error_type=SuperAdminErrorType.SYSTEM,
                    code="HTTP_EXCEPTION",
                    message=e.detail,
                    severity=ErrorSeverity.MEDIUM,
                    original_error=e
                )
                
                super_admin_error_handler.log_error(
                    error=super_admin_error,
                    request=request,
                    admin_user_id=admin_user_id,
                    operation=operation_name or func.__name__
                )
                
                if return_html:
                    error_html = f"""
                    <div class='alert alert-danger' role='alert'>
                        <strong>Error:</strong> {e.detail}
                    </div>
                    """
                    return HTMLResponse(content=error_html, status_code=e.status_code)
                
                error_response = super_admin_error_handler.format_error_response(
                    error=super_admin_error,
                    request_id=request_id,
                    processing_time_ms=processing_time
                )
                
                return JSONResponse(content=error_response, status_code=e.status_code)
                
            except Exception as e:
                # Handle unexpected errors
                processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
                
                super_admin_error = super_admin_error_handler.create_error(
                    error_type=SuperAdminErrorType.SYSTEM,
                    code="UNEXPECTED_ERROR",
                    message="An unexpected error occurred during the operation",
                    severity=ErrorSeverity.HIGH,
                    original_error=e,
                    suggestions=[
                        "Try the operation again",
                        "Contact support if the problem persists"
                    ]
                )
                
                # Log full traceback for unexpected errors
                logger.error(
                    f"Unexpected error in {operation_name or func.__name__}: {str(e)}",
                    extra={
                        "correlation_id": super_admin_error.correlation_id,
                        "admin_user_id": admin_user_id,
                        "operation": operation_name or func.__name__,
                        "traceback": traceback.format_exc()
                    }
                )
                
                if return_html:
                    error_html = f"""
                    <div class='alert alert-danger' role='alert'>
                        <strong>System Error:</strong> An unexpected error occurred
                        <br><small>Correlation ID: {super_admin_error.correlation_id}</small>
                    </div>
                    """
                    return HTMLResponse(content=error_html, status_code=500)
                
                error_response = super_admin_error_handler.format_error_response(
                    error=super_admin_error,
                    request_id=request_id,
                    processing_time_ms=processing_time
                )
                
                return JSONResponse(content=error_response, status_code=500)
        
        return wrapper
    return decorator


# Custom exception class for raising structured errors
class SuperAdminException(Exception):
    """Exception class for raising SuperAdminError objects"""
    
    def __init__(self, error: SuperAdminError):
        self.error = error
        super().__init__(error.message)