"""
Memory Monitoring Endpoints
Provides HTTP endpoints for monitoring memory usage and optimization status.
"""

import gc
import psutil
import os
from typing import Dict, Any
from datetime import datetime

try:
    from .memory_utils import cleanup_global_dict, force_garbage_collection
    from .memory_optimizer import get_memory_stats as get_advanced_memory_stats
except ImportError:
    from memory_utils import cleanup_global_dict, force_garbage_collection  # type: ignore


def get_system_memory_info() -> Dict[str, Any]:
    """Get comprehensive system memory information."""
    # Process memory info
    process = psutil.Process(os.getpid())
    memory_info = process.memory_info()
    memory_percent = process.memory_percent()
    
    # System memory info
    virtual_memory = psutil.virtual_memory()
    
    return {
        "process": {
            "rss_mb": round(memory_info.rss / 1024 / 1024, 2),
            "vms_mb": round(memory_info.vms / 1024 / 1024, 2),
            "percent": round(memory_percent, 2),
            "pid": process.pid,
            "create_time": datetime.fromtimestamp(process.create_time()).isoformat()
        },
        "system": {
            "total_mb": round(virtual_memory.total / 1024 / 1024, 2),
            "available_mb": round(virtual_memory.available / 1024 / 1024, 2),
            "used_mb": round(virtual_memory.used / 1024 / 1024, 2),
            "percent": virtual_memory.percent
        },
        "garbage_collection": {
            "counts": gc.get_count(),
            "stats": gc.get_stats() if hasattr(gc, 'get_stats') else None
        }
    }


def get_background_tasks_memory_status() -> Dict[str, Any]:
    """Get memory status of background tasks global dictionaries."""
    try:
        from . import background_tasks
        
        return {
            "message_fetch_failures": {
                "size": len(background_tasks.message_fetch_failures),
                "sample_keys": list(background_tasks.message_fetch_failures.keys())[:5]
            },
            "startup_warning_counts": {
                "size": len(background_tasks.startup_warning_counts),
                "current_values": dict(background_tasks.startup_warning_counts)
            }
        }
    except ImportError:
        return {"error": "Background tasks module not available"}


def perform_memory_cleanup() -> Dict[str, Any]:
    """Perform immediate memory cleanup and return results."""
    try:
        from . import background_tasks
        
        # Get initial counts
        initial_failures = len(background_tasks.message_fetch_failures)
        initial_warnings = len(background_tasks.startup_warning_counts)
        
        # Perform cleanup
        failures_removed = cleanup_global_dict(
            background_tasks.message_fetch_failures,
            max_size=1000,
            max_age_minutes=60
        )
        
        # Force garbage collection
        collected = force_garbage_collection()
        
        return {
            "cleanup_performed": True,
            "failures_dict": {
                "initial_size": initial_failures,
                "current_size": len(background_tasks.message_fetch_failures),
                "entries_removed": failures_removed
            },
            "garbage_collection": {
                "objects_collected": collected
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "cleanup_performed": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


def get_database_connection_stats() -> Dict[str, Any]:
    """Get database connection pool statistics."""
    try:
        from .database import engine
        
        if hasattr(engine, 'pool'):
            pool = engine.pool
            return {
                "pool_size": pool.size(),
                "checked_in": pool.checkedin(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow() if hasattr(pool, 'overflow') else None,
                "invalid": pool.invalid() if hasattr(pool, 'invalid') else None
            }
        else:
            return {"error": "No connection pool available"}
    except Exception as e:
        return {"error": f"Database stats unavailable: {str(e)}"}


def get_comprehensive_memory_report() -> Dict[str, Any]:
    """Get a comprehensive memory report combining all sources."""
    return {
        "timestamp": datetime.now().isoformat(),
        "system_memory": get_system_memory_info(),
        "background_tasks": get_background_tasks_memory_status(),
        "database_connections": get_database_connection_stats(),
        "process_info": {
            "python_version": f"{psutil.version_info[0]}.{psutil.version_info[1]}.{psutil.version_info[2]}" if hasattr(psutil, 'version_info') else "unknown",
            "platform": "python-psutil"
        }
    }


# FastAPI endpoint functions (if using FastAPI)
async def memory_health_endpoint():
    """Health check endpoint for memory monitoring."""
    memory_info = get_system_memory_info()
    
    # Determine health status
    is_healthy = (
        memory_info["process"]["percent"] < 80 and
        memory_info["system"]["percent"] < 90
    )
    
    return {
        "status": "healthy" if is_healthy else "warning",
        "memory_percent": memory_info["process"]["percent"],
        "system_percent": memory_info["system"]["percent"],
        "timestamp": datetime.now().isoformat()
    }


async def memory_stats_endpoint():
    """Detailed memory statistics endpoint."""
    return get_comprehensive_memory_report()


async def memory_cleanup_endpoint():
    """Manual memory cleanup endpoint."""
    return perform_memory_cleanup()


# Flask endpoint functions (if using Flask)
def flask_memory_health():
    """Flask health check endpoint for memory monitoring."""
    import asyncio
    return asyncio.run(memory_health_endpoint())


def flask_memory_stats():
    """Flask detailed memory statistics endpoint."""
    return get_comprehensive_memory_report()


def flask_memory_cleanup():
    """Flask manual memory cleanup endpoint."""
    return perform_memory_cleanup()