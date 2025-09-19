"""
Memory Optimization Module
Provides memory management utilities and optimizations for Polly.
"""

import logging
import psutil
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from functools import wraps

logger = logging.getLogger(__name__)


class MemoryMonitor:
    """Memory monitoring and optimization utilities"""
    
    def __init__(self):
        self.process = psutil.Process(os.getpid())
        self.memory_checkpoints = {}
        
    def get_memory_usage(self) -> Dict[str, float]:
        """Get current memory usage statistics"""
        try:
            memory_info = self.process.memory_info()
            return {
                "rss": memory_info.rss / 1024 / 1024,  # MB
                "vms": memory_info.vms / 1024 / 1024,  # MB
                "percent": self.process.memory_percent(),
                "available": psutil.virtual_memory().available / 1024 / 1024  # MB
            }
        except Exception as e:
            logger.error(f"Error getting memory usage: {e}")
            return {"rss": 0, "vms": 0, "percent": 0, "available": 0}
    
    def log_memory_checkpoint(self, checkpoint_name: str):
        """Log memory usage at a specific checkpoint"""
        usage = self.get_memory_usage()
        self.memory_checkpoints[checkpoint_name] = {
            "timestamp": datetime.now(),
            "usage": usage
        }
        logger.info(f"🧠 MEMORY CHECKPOINT [{checkpoint_name}] - RSS: {usage['rss']:.1f}MB, "
                   f"VMS: {usage['vms']:.1f}MB, %: {usage['percent']:.1f}%")
    
    def compare_checkpoints(self, start: str, end: str) -> Optional[Dict[str, float]]:
        """Compare memory usage between two checkpoints"""
        if start not in self.memory_checkpoints or end not in self.memory_checkpoints:
            return None
            
        start_usage = self.memory_checkpoints[start]["usage"]
        end_usage = self.memory_checkpoints[end]["usage"]
        
        diff = {
            "rss_diff": end_usage["rss"] - start_usage["rss"],
            "vms_diff": end_usage["vms"] - start_usage["vms"],
            "percent_diff": end_usage["percent"] - start_usage["percent"]
        }
        
        logger.info(f"🔍 MEMORY ANALYSIS [{start} → {end}] - "
                   f"RSS: {diff['rss_diff']:+.1f}MB, "
                   f"VMS: {diff['vms_diff']:+.1f}MB, "
                   f"%: {diff['percent_diff']:+.1f}%")
        
        return diff


# Global memory monitor instance
memory_monitor = MemoryMonitor()


def memory_profile(func):
    """Decorator to profile memory usage of functions"""
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        func_name = f"{func.__module__}.{func.__name__}"
        memory_monitor.log_memory_checkpoint(f"{func_name}_start")
        
        try:
            result = await func(*args, **kwargs)
            memory_monitor.log_memory_checkpoint(f"{func_name}_end")
            memory_monitor.compare_checkpoints(f"{func_name}_start", f"{func_name}_end")
            return result
        except Exception as e:
            memory_monitor.log_memory_checkpoint(f"{func_name}_error")
            memory_monitor.compare_checkpoints(f"{func_name}_start", f"{func_name}_error")
            raise
    
    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        func_name = f"{func.__module__}.{func.__name__}"
        memory_monitor.log_memory_checkpoint(f"{func_name}_start")
        
        try:
            result = func(*args, **kwargs)
            memory_monitor.log_memory_checkpoint(f"{func_name}_end")
            memory_monitor.compare_checkpoints(f"{func_name}_start", f"{func_name}_end")
            return result
        except Exception as e:
            memory_monitor.log_memory_checkpoint(f"{func_name}_error")
            memory_monitor.compare_checkpoints(f"{func_name}_start", f"{func_name}_error")
            raise
    
    # Return appropriate wrapper based on function type
    if hasattr(func, '__code__') and func.__code__.co_flags & 0x80:  # CO_COROUTINE
        return async_wrapper
    else:
        return sync_wrapper


class GlobalDictCleaner:
    """Utility class for managing global dictionary memory"""
    
    @staticmethod
    def cleanup_dict_by_size(target_dict: Dict, max_size: int, 
                           key_func=None, reverse=True) -> int:
        """
        Clean up a dictionary to keep only the most recent entries
        
        Args:
            target_dict: Dictionary to clean
            max_size: Maximum number of entries to keep
            key_func: Function to extract sort key from dict items
            reverse: Sort order (True for newest first)
            
        Returns:
            Number of entries removed
        """
        if len(target_dict) <= max_size:
            return 0
            
        original_size = len(target_dict)
        
        # Convert to list of items for sorting
        items = list(target_dict.items())
        
        # Sort by key function or just keep original order
        if key_func:
            items.sort(key=key_func, reverse=reverse)
        
        # Keep only the desired number of entries
        kept_items = items[:max_size]
        target_dict.clear()
        target_dict.update(kept_items)
        
        removed_count = original_size - len(target_dict)
        logger.info(f"🧹 DICT CLEANUP - Removed {removed_count} entries, kept {len(target_dict)}")
        
        return removed_count
    
    @staticmethod
    def cleanup_dict_by_age(target_dict: Dict, max_age_minutes: int,
                           timestamp_func=None) -> int:
        """
        Clean up dictionary entries older than specified age
        
        Args:
            target_dict: Dictionary to clean
            max_age_minutes: Maximum age in minutes
            timestamp_func: Function to extract timestamp from dict values
            
        Returns:
            Number of entries removed
        """
        if not target_dict:
            return 0
            
        cutoff_time = datetime.now() - timedelta(minutes=max_age_minutes)
        original_size = len(target_dict)
        
        # Remove old entries
        keys_to_remove = []
        for key, value in target_dict.items():
            try:
                if timestamp_func:
                    timestamp = timestamp_func(value)
                else:
                    # Assume value has 'timestamp' or 'last_attempt' attribute
                    timestamp = getattr(value, 'timestamp', 
                                      getattr(value, 'last_attempt', datetime.now()))
                
                if timestamp < cutoff_time:
                    keys_to_remove.append(key)
            except Exception as e:
                logger.debug(f"Error checking timestamp for key {key}: {e}")
                # If we can't determine age, remove it to be safe
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del target_dict[key]
        
        removed_count = len(keys_to_remove)
        if removed_count > 0:
            logger.info(f"🧹 AGE CLEANUP - Removed {removed_count} old entries, kept {len(target_dict)}")
        
        return removed_count


def optimize_memory_usage():
    """Perform general memory optimization tasks"""
    try:
        # Log current memory usage
        memory_monitor.log_memory_checkpoint("memory_optimization_start")
        
        # Force garbage collection
        import gc
        collected = gc.collect()
        logger.info(f"🗑️ GARBAGE COLLECTION - Collected {collected} objects")
        
        # Log memory after cleanup
        memory_monitor.log_memory_checkpoint("memory_optimization_end")
        memory_monitor.compare_checkpoints("memory_optimization_start", "memory_optimization_end")
        
    except Exception as e:
        logger.error(f"❌ MEMORY OPTIMIZATION - Error during optimization: {e}")


def get_memory_stats() -> Dict[str, Any]:
    """Get comprehensive memory statistics"""
    try:
        stats = memory_monitor.get_memory_usage()
        
        # Add system memory info
        vm = psutil.virtual_memory()
        stats.update({
            "system_total": vm.total / 1024 / 1024,  # MB
            "system_used": vm.used / 1024 / 1024,   # MB
            "system_percent": vm.percent,
            "checkpoints_count": len(memory_monitor.memory_checkpoints)
        })
        
        return stats
    except Exception as e:
        logger.error(f"Error getting memory stats: {e}")
        return {}