"""
Simple Memory Utilities
Basic memory management utilities without external dependencies.
"""

import gc
import logging
from datetime import datetime, timedelta
from typing import Dict, Callable, Optional

logger = logging.getLogger(__name__)


def cleanup_global_dict(target_dict: Dict, max_size: int = 1000, 
                       max_age_minutes: int = 60, 
                       timestamp_key: str = "last_attempt") -> int:
    """
    Clean up a global dictionary to prevent memory leaks
    
    Args:
        target_dict: Dictionary to clean up
        max_size: Maximum number of entries to keep
        max_age_minutes: Maximum age of entries in minutes
        timestamp_key: Key to use for timestamp extraction
        
    Returns:
        Number of entries removed
    """
    if not target_dict:
        return 0
    
    original_size = len(target_dict)
    removed_count = 0
    
    try:
        # First, remove old entries
        cutoff_time = datetime.now() - timedelta(minutes=max_age_minutes)
        keys_to_remove = []
        
        for key, value in target_dict.items():
            try:
                # Handle different value types
                if isinstance(value, dict) and timestamp_key in value:
                    timestamp = value[timestamp_key]
                elif hasattr(value, timestamp_key):
                    timestamp = getattr(value, timestamp_key)
                else:
                    # If we can't determine age, consider it old
                    keys_to_remove.append(key)
                    continue
                
                if isinstance(timestamp, datetime) and timestamp < cutoff_time:
                    keys_to_remove.append(key)
                    
            except Exception:
                # If we can't process the entry, remove it to be safe
                keys_to_remove.append(key)
        
        # Remove old entries
        for key in keys_to_remove:
            del target_dict[key]
            removed_count += 1
        
        # If still too large, remove oldest entries
        if len(target_dict) > max_size:
            # Convert to list and sort by timestamp (if possible)
            items = list(target_dict.items())
            
            # Try to sort by timestamp, fall back to key sorting
            try:
                items.sort(key=lambda x: x[1].get(timestamp_key, datetime.min) 
                          if isinstance(x[1], dict) 
                          else getattr(x[1], timestamp_key, datetime.min))
            except Exception:
                # Fall back to simple key sorting
                items.sort(key=lambda x: str(x[0]))
            
            # Keep only the most recent entries
            items_to_keep = items[-max_size:]
            target_dict.clear()
            target_dict.update(items_to_keep)
            
            removed_count += original_size - max_size
        
        if removed_count > 0:
            logger.info(f"🧹 MEMORY CLEANUP - Removed {removed_count} entries from dict, "
                       f"kept {len(target_dict)} entries")
        
        return removed_count
        
    except Exception as e:
        logger.error(f"❌ MEMORY CLEANUP - Error cleaning dict: {e}")
        return 0


def force_garbage_collection() -> int:
    """Force garbage collection and return number of collected objects"""
    try:
        collected = gc.collect()
        if collected > 0:
            logger.info(f"🗑️ GARBAGE COLLECTION - Collected {collected} objects")
        return collected
    except Exception as e:
        logger.error(f"❌ GARBAGE COLLECTION - Error: {e}")
        return 0


def reset_counter_dict(counter_dict: Dict[str, int], keys: Optional[list] = None) -> None:
    """Reset counter dictionary to prevent accumulation"""
    try:
        if keys:
            for key in keys:
                counter_dict[key] = 0
        else:
            for key in counter_dict:
                counter_dict[key] = 0
        
        logger.debug("🔄 COUNTER RESET - Reset counter dictionary")
    except Exception as e:
        logger.error(f"❌ COUNTER RESET - Error: {e}")


def memory_cleanup_decorator(cleanup_func: Optional[Callable] = None):
    """Decorator to add memory cleanup to functions"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                # Run the function
                result = func(*args, **kwargs)
                
                # Perform cleanup if provided
                if cleanup_func:
                    cleanup_func()
                else:
                    force_garbage_collection()
                    
                return result
            except Exception as e:
                logger.error(f"Error in {func.__name__}: {e}")
                raise
        return wrapper
    return decorator


# Constants for background tasks cleanup
MAX_FAILURE_ENTRIES = 1000
FAILURE_CLEANUP_AGE_MINUTES = 60
STARTUP_WARNING_RESET_KEYS = [
    "message_not_found",
    "permission_denied", 
    "channel_not_found",
    "rate_limited",
    "message_fix_failed"
]


def cleanup_background_tasks_memory():
    """Specific cleanup function for background tasks module"""
    try:
        # Import here to avoid circular imports
        from . import background_tasks
        
        # Clean up message fetch failures
        removed = cleanup_global_dict(
            background_tasks.message_fetch_failures,
            max_size=MAX_FAILURE_ENTRIES,
            max_age_minutes=FAILURE_CLEANUP_AGE_MINUTES,
            timestamp_key="last_attempt"
        )
        
        # Reset startup warning counts
        reset_counter_dict(
            background_tasks.startup_warning_counts,
            keys=STARTUP_WARNING_RESET_KEYS
        )
        
        # Force garbage collection
        force_garbage_collection()
        
        logger.info(f"✅ BACKGROUND TASKS CLEANUP - Completed memory cleanup, removed {removed} entries")
        
    except ImportError:
        logger.debug("Background tasks module not available for cleanup")
    except Exception as e:
        logger.error(f"❌ BACKGROUND TASKS CLEANUP - Error: {e}")