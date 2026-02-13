"""
Cache Invalidation Utilities
Shared utilities for invalidating poll-related caches across services.
"""

import logging

logger = logging.getLogger(__name__)


async def invalidate_poll_cache_safely(poll_id: int, operation_name: str = "OPERATION") -> int:
    """
    Safely invalidate poll-related caches with error handling.
    
    This is a common pattern used across poll services to invalidate caches
    without failing the operation if cache invalidation fails.
    
    Args:
        poll_id: ID of the poll whose cache should be invalidated
        operation_name: Name of the operation for logging (e.g., "UNIFIED OPEN", "UNIFIED EDIT")
        
    Returns:
        Number of cache entries invalidated (0 if cache service unavailable or error occurs)
    """
    try:
        from .enhanced_cache_service import get_enhanced_cache_service
        
        enhanced_cache = get_enhanced_cache_service()
        if enhanced_cache:
            invalidated = await enhanced_cache.invalidate_poll_related_cache(poll_id)
            logger.info(f"✅ {operation_name} {poll_id} - Invalidated {invalidated} stale cache entries")
            return invalidated
        else:
            logger.debug(f"ℹ️ {operation_name} {poll_id} - Enhanced cache service not available")
            return 0
            
    except Exception as cache_error:
        logger.error(f"❌ {operation_name} {poll_id} - Error invalidating caches: {cache_error}")
        # Don't fail the operation if cache invalidation fails
        return 0
