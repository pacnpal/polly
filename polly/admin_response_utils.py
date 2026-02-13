"""
Admin Response Utilities
Shared utilities for sanitizing admin API responses to prevent sensitive error leakage.
"""

import logging

logger = logging.getLogger(__name__)


def sanitize_result_for_client(result: dict) -> dict:
    """
    Sanitize service result dict to prevent leaking sensitive error details to clients.
    
    This function ensures that internal error messages, stack traces, and other sensitive
    information are not exposed to the client. It provides a generic error message instead.
    
    Args:
        result: Dictionary containing operation result with 'success', 'error', and optional 'details' keys
        
    Returns:
        Sanitized dictionary safe for client consumption
    """
    # Always work on a copy so we don't accidentally mutate shared state
    sanitized = result.copy() if isinstance(result, dict) else {"raw_result": str(result)}

    error_value = sanitized.get("error")
    success_flag = sanitized.get("success")

    # Log the original error on the server only, for debugging
    if error_value is not None:
        logger.debug(f"Sanitizing error for client response: {error_value}")

    # Primary rule: if the operation was not successful and an error is present,
    # never pass the raw error message back to the client.
    if success_flag is False and error_value is not None:
        sanitized["error"] = "Operation failed. Please try again or contact support."
        
        # If there is a nested 'details' field that may contain further error info, sanitize that as well
        details = sanitized.get("details")
        if isinstance(details, dict) and "error" in details:
            details = details.copy()
            details["error"] = "Operation failed due to an internal error"
            sanitized["details"] = details
            
        return sanitized

    # Additional safeguard: if the error string looks like it may contain
    # stack-trace or multi-line internal details, replace it as well.
    if isinstance(error_value, str) and ("\n" in error_value or "Traceback" in error_value):
        sanitized["error"] = "Operation failed. Please try again or contact support."
        return sanitized

    return sanitized
