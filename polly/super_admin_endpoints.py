"""
Super Admin Endpoints
API endpoints for super admin dashboard functionality.
"""

import logging
import json
from datetime import datetime
from fastapi import Request, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from typing import Optional

from .super_admin import require_super_admin, super_admin_service, DiscordUser
from .database import get_db_session

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="templates")


async def get_super_admin_dashboard(
    request: Request, current_user: DiscordUser = Depends(require_super_admin)
) -> HTMLResponse:
    """Super admin dashboard page - ULTRA OPTIMIZED"""
    try:
        # PERFORMANCE OPTIMIZATION: Use async context manager for DB
        from contextlib import asynccontextmanager
        
        @asynccontextmanager
        async def get_db_async():
            db = get_db_session()
            try:
                yield db
            finally:
                db.close()
        
        async with get_db_async() as db:
            # PERFORMANCE OPTIMIZATION: Check cache first
            from .redis_client import get_redis_client
            redis_client = await get_redis_client()
            
            stats = None
            if redis_client and redis_client.is_connected:
                try:
                    cached_stats = await redis_client.get("super_admin:dashboard_stats")
                    if cached_stats:
                        import json
                        # Handle both string and dict returns from Redis
                        if isinstance(cached_stats, str):
                            stats = json.loads(cached_stats)
                        elif isinstance(cached_stats, dict):
                            stats = cached_stats
                        else:
                            # Try to decode if it's bytes
                            if isinstance(cached_stats, bytes):
                                stats = json.loads(cached_stats.decode('utf-8'))
                            else:
                                logger.warning(f"Unexpected cache data type: {type(cached_stats)}")
                except Exception as e:
                    logger.warning(f"Cache read failed: {e}")
            
            # Get fresh stats if not cached
            if not stats:
                stats = super_admin_service.get_system_stats(db)
                
                # Cache for 60 seconds
                if redis_client and redis_client.is_connected:
                    try:
                        import json
                        await redis_client.set(
                            "super_admin:dashboard_stats", 
                            json.dumps(stats, default=str), 
                            ttl=60
                        )
                    except Exception as e:
                        logger.warning(f"Cache write failed: {e}")
            
            return templates.TemplateResponse(
                "super_admin_dashboard_enhanced.html",
                {
                    "request": request,
                    "user": current_user,
                    "stats": stats,
                    "is_super_admin": True
                }
            )
            
    except Exception as e:
        logger.error(f"Error loading super admin dashboard: {e}")
        raise HTTPException(status_code=500, detail="Error loading dashboard")


async def get_all_polls_api(
    request: Request,
    status: Optional[str] = Query(None, description="Filter by poll status"),
    server: Optional[str] = Query(None, description="Filter by server ID"),
    creator: Optional[str] = Query(None, description="Filter by creator ID"),
    limit: int = Query(50, ge=1, le=200, description="Number of polls to return"),
    offset: int = Query(0, ge=0, description="Number of polls to skip"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order (asc/desc)"),
    current_user: DiscordUser = Depends(require_super_admin)
) -> JSONResponse:
    """Get all polls with filtering and pagination"""
    try:
        db = get_db_session()
        try:
            result = super_admin_service.get_all_polls(
                db,
                status_filter=status,
                server_filter=server,
                creator_filter=creator,
                limit=limit,
                offset=offset,
                sort_by=sort_by,
                sort_order=sort_order
            )
            
            return JSONResponse(content=result)
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error getting all polls: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving polls")


async def get_system_stats_api(
    request: Request, current_user: DiscordUser = Depends(require_super_admin)
) -> JSONResponse:
    """Get system-wide statistics"""
    try:
        db = get_db_session()
        try:
            stats = super_admin_service.get_system_stats(db)
            return JSONResponse(content={"success": True, "stats": stats})
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error getting system stats: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving statistics")


async def get_poll_details_api(
    poll_id: int,
    request: Request,
    current_user: DiscordUser = Depends(require_super_admin)
) -> JSONResponse:
    """Get detailed information about a specific poll"""
    try:
        db = get_db_session()
        try:
            poll_details = super_admin_service.get_poll_details(db, poll_id)
            
            if not poll_details:
                raise HTTPException(status_code=404, detail="Poll not found")
            
            return JSONResponse(content={"success": True, "data": poll_details})
            
        finally:
            db.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting poll details for {poll_id}: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving poll details")


async def force_close_poll_api(
    poll_id: int,
    request: Request,
    current_user: DiscordUser = Depends(require_super_admin)
) -> JSONResponse:
    """Force close a poll (super admin only)"""
    try:
        db = get_db_session()
        try:
            result = await super_admin_service.force_close_poll(db, poll_id, current_user.id)
            
            if result["success"]:
                logger.info(f"Super admin {current_user.username} force closed poll {poll_id}")
                return JSONResponse(content=result)
            else:
                return JSONResponse(content=result, status_code=400)
                
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error force closing poll {poll_id}: {e}")
        raise HTTPException(status_code=500, detail="Error closing poll")


async def reopen_poll_api(
    poll_id: int,
    request: Request,
    current_user: DiscordUser = Depends(require_super_admin)
) -> JSONResponse:
    """Reopen a closed poll with comprehensive options (super admin only)"""
    try:
        # Parse form data or JSON body
        content_type = request.headers.get("content-type", "")
        
        if "application/json" in content_type:
            # Handle JSON request with proper error handling
            try:
                # Check if request body is empty first
                body_bytes = await request.body()
                if not body_bytes or body_bytes.strip() == b'':
                    logger.warning(f"Empty JSON request body in reopen_poll_api for poll {poll_id}, using defaults")
                    extend_hours = None
                    reset_votes = False
                    new_close_time_str = None
                else:
                    # Parse the body as JSON
                    import json
                    body = json.loads(body_bytes.decode('utf-8'))
                    extend_hours = body.get("extend_hours")
                    reset_votes = body.get("reset_votes", False)
                    new_close_time_str = body.get("new_close_time")
            except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as e:
                logger.error(f"JSON parsing error in reopen_poll_api for poll {poll_id}: {e}")
                return JSONResponse(
                    content={"success": False, "error": "Invalid JSON format in request body"},
                    status_code=400
                )
            except Exception as e:
                logger.error(f"Unexpected error parsing JSON in reopen_poll_api for poll {poll_id}: {e}")
                return JSONResponse(
                    content={"success": False, "error": "Failed to parse request body"},
                    status_code=400
                )
        else:
            # Handle form data
            try:
                form_data = await request.form()
                extend_hours = form_data.get("extend_hours")
                reset_votes = form_data.get("reset_votes") == "true"
                new_close_time_str = form_data.get("new_close_time")
            except Exception as e:
                logger.error(f"Form data parsing error in reopen_poll_api for poll {poll_id}: {e}")
                return JSONResponse(
                    content={"success": False, "error": "Failed to parse form data"},
                    status_code=400
                )
        
        # Parse extend_hours if provided
        if extend_hours:
            try:
                extend_hours = int(extend_hours)
            except (ValueError, TypeError):
                return JSONResponse(
                    content={"success": False, "error": "Invalid extend_hours value"},
                    status_code=400
                )
        
        # Parse new_close_time if provided
        new_close_time = None
        if new_close_time_str:
            try:
                from datetime import datetime
                import pytz
                # Parse ISO format datetime
                new_close_time = datetime.fromisoformat(new_close_time_str.replace('Z', '+00:00'))
                # Ensure timezone-aware
                if new_close_time.tzinfo is None:
                    new_close_time = pytz.UTC.localize(new_close_time)
            except (ValueError, TypeError) as e:
                return JSONResponse(
                    content={"success": False, "error": f"Invalid new_close_time format: {str(e)}"},
                    status_code=400
                )
        
        db = get_db_session()
        try:
            result = await super_admin_service.reopen_poll(
                db, 
                poll_id, 
                current_user.id,
                new_close_time=new_close_time,
                extend_hours=extend_hours,
                reset_votes=reset_votes
            )
            
            if result["success"]:
                logger.info(f"Super admin {current_user.username} reopened poll {poll_id}")
                return JSONResponse(content=result)
            else:
                return JSONResponse(content=result, status_code=400)
                
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error reopening poll {poll_id}: {e}")
        raise HTTPException(status_code=500, detail="Error reopening poll")


async def delete_poll_api(
    poll_id: int,
    request: Request,
    current_user: DiscordUser = Depends(require_super_admin)
) -> JSONResponse:
    """Delete a poll and all its votes (super admin only)"""
    try:
        db = get_db_session()
        try:
            result = super_admin_service.delete_poll(db, poll_id, current_user.id)
            
            if result["success"]:
                logger.info(f"Super admin {current_user.username} deleted poll {poll_id}")
                return JSONResponse(content=result)
            else:
                return JSONResponse(content=result, status_code=400)
                
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error deleting poll {poll_id}: {e}")
        raise HTTPException(status_code=500, detail="Error deleting poll")


async def get_all_polls_htmx(
    request: Request,
    status: Optional[str] = Query(None),
    server: Optional[str] = Query(None),
    creator: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    current_user: DiscordUser = Depends(require_super_admin)
) -> HTMLResponse:
    """HTMX endpoint for polls table - PERFORMANCE OPTIMIZED"""
    try:
        db = get_db_session()
        try:
            limit = 25
            offset = (page - 1) * limit
            
            result = super_admin_service.get_all_polls(
                db,
                status_filter=status,
                server_filter=server,
                creator_filter=creator,
                limit=limit,
                offset=offset,
                sort_by="created_at",
                sort_order="desc"
            )
            
            # PERFORMANCE OPTIMIZATION: Skip Discord API calls - use cached usernames or fallback
            for poll in result["polls"]:
                # Use truncated creator ID as fallback - no Discord API calls
                poll["creator_username"] = f"User {poll['creator_id'][:8]}..." if poll["creator_id"] else "Unknown"
            
            return templates.TemplateResponse(
                "htmx/super_admin_polls_table.html",
                {
                    "request": request,
                    "polls": result["polls"],
                    "total_count": result["total_count"],
                    "current_page": page,
                    "has_more": result["has_more"],
                    "filters": {
                        "status": status,
                        "server": server,
                        "creator": creator
                    }
                }
            )
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error getting polls HTMX: {e}")
        return HTMLResponse(
            content="<div class='alert alert-danger'>Error loading polls</div>",
            status_code=500
        )


async def get_poll_details_htmx(
    poll_id: int,
    request: Request,
    current_user: DiscordUser = Depends(require_super_admin)
) -> HTMLResponse:
    """HTMX endpoint for poll details modal - PERFORMANCE OPTIMIZED"""
    try:
        db = get_db_session()
        try:
            poll_details = super_admin_service.get_poll_details(db, poll_id)
            
            if not poll_details:
                return HTMLResponse(
                    content="<div class='alert alert-danger'>Poll not found</div>",
                    status_code=404
                )
            
            # PERFORMANCE OPTIMIZATION: Skip Discord API calls - use fallback usernames
            for vote in poll_details["votes"]:
                vote["username"] = f"User {vote['user_id'][:8]}..." if vote["user_id"] else "Unknown"
                vote["avatar_url"] = None
            
            # PERFORMANCE OPTIMIZATION: Skip Discord API call for creator
            creator_id = poll_details["poll"]["creator_id"]
            poll_details["poll"]["creator_username"] = f"User {creator_id[:8]}..." if creator_id else "Unknown"
            
            return templates.TemplateResponse(
                "htmx/super_admin_poll_details.html",
                {
                    "request": request,
                    "poll_details": poll_details
                }
            )
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error getting poll details HTMX for {poll_id}: {e}")
        return HTMLResponse(
            content="<div class='alert alert-danger'>Error loading poll details</div>",
            status_code=500
        )


# Old manual log parsing functions removed - now using pandas_log_analyzer


async def get_system_logs_htmx(
    request: Request,
    level: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    time_range: str = Query("24h"),
    current_user: DiscordUser = Depends(require_super_admin)
) -> HTMLResponse:
    """HTMX endpoint for system logs using pandas analyzer (async to prevent Discord bot blocking)"""
    try:
        from .pandas_log_analyzer import pandas_log_analyzer
        
        # Use async pandas analyzer to prevent blocking Discord bot heartbeat
        log_entries, analytics = await pandas_log_analyzer.get_filtered_logs_async(
            level_filter=level,
            search_filter=search,
            time_range=time_range,
            limit=500
        )
        
        return templates.TemplateResponse(
            "htmx/super_admin_logs.html",
            {
                "request": request,
                "log_entries": log_entries,
                "analytics": analytics,
                "filters": {
                    "level": level,
                    "search": search,
                    "time_range": time_range
                }
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting system logs with pandas analyzer: {e}")
        return HTMLResponse(
            content="<div class='alert alert-danger'>Error loading system logs</div>",
            status_code=500
        )


async def download_logs_api(
    request: Request,
    level: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    time_range: str = Query("24h"),
    current_user: DiscordUser = Depends(require_super_admin)
) -> StreamingResponse:
    """Download filtered logs as text file using pandas analyzer (async to prevent Discord bot blocking)"""
    try:
        from .pandas_log_analyzer import pandas_log_analyzer
        
        # Use async pandas analyzer to prevent blocking Discord bot heartbeat
        log_entries, analytics = await pandas_log_analyzer.get_filtered_logs_async(
            level_filter=level,
            search_filter=search,
            time_range=time_range,
            limit=10000  # Higher limit for downloads
        )
        
        # Generate log content with analytics header
        def generate_log_content():
            yield "# Polly System Logs Export (Pandas-Powered)\n"
            yield f"# Generated: {datetime.now().isoformat()}\n"
            yield f"# Filters: Level={level or 'All'}, Search={search or 'None'}, Time Range={time_range}\n"
            yield f"# Total Entries: {len(log_entries)}\n"
            yield "# Analytics Summary:\n"
            yield f"#   - Error Rate: {analytics.get('error_rate', 0):.2f}%\n"
            yield f"#   - Time Range: {analytics.get('time_range', {}).get('start', 'N/A')} to {analytics.get('time_range', {}).get('end', 'N/A')}\n"
            yield f"#   - Level Distribution: {analytics.get('level_distribution', {})}\n"
            yield f"#   - Poll Events: {analytics.get('poll_activity', {}).get('total_poll_events', 0)}\n"
            yield "\n"
            
            for entry in log_entries:
                metadata = entry.get('metadata', {})
                metadata_str = ""
                if metadata.get('poll_id'):
                    metadata_str += f" [Poll:{metadata['poll_id']}]"
                if metadata.get('user_id'):
                    metadata_str += f" [User:{metadata['user_id']}]"
                if metadata.get('endpoint'):
                    metadata_str += f" [API:{metadata['endpoint']}]"
                if metadata.get('response_time'):
                    metadata_str += f" [RT:{metadata['response_time']}ms]"
                
                yield f"{entry['timestamp']} - {entry['level']} - {entry['message']}{metadata_str}\n"
        
        filename = f"polly_logs_pandas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        
        return StreamingResponse(
            generate_log_content(),
            media_type="text/plain",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        logger.error(f"Error downloading logs with pandas analyzer: {e}")
        raise HTTPException(status_code=500, detail="Error generating log download")


async def get_redis_status_htmx(
    request: Request,
    current_user: DiscordUser = Depends(require_super_admin)
) -> HTMLResponse:
    """HTMX endpoint for Redis status"""
    try:
        from .redis_client import get_redis_client
        
        redis_client = await get_redis_client()
        status_data = {
            "connected": False,
            "info": {},
            "error": None
        }
        
        if redis_client and redis_client.is_connected:
            try:
                # Test connection using the async client's internal client
                if redis_client._client:
                    await redis_client._client.ping()
                    status_data["connected"] = True
                    
                    # Get Redis info
                    info = await redis_client._client.info()
                    status_data["info"] = {
                        "version": info.get("redis_version", "Unknown"),
                        "uptime": info.get("uptime_in_seconds", 0),
                        "connected_clients": info.get("connected_clients", 0),
                        "used_memory": info.get("used_memory_human", "Unknown"),
                        "total_commands_processed": info.get("total_commands_processed", 0),
                        "keyspace_hits": info.get("keyspace_hits", 0),
                        "keyspace_misses": info.get("keyspace_misses", 0)
                    }
                else:
                    status_data["error"] = "Redis client not connected"
                
            except Exception as e:
                status_data["error"] = str(e)
        else:
            status_data["error"] = "Redis client not initialized or not connected"
        
        return templates.TemplateResponse(
            "htmx/super_admin_redis_status.html",
            {
                "request": request,
                "redis_status": status_data
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting Redis status: {e}")
        return HTMLResponse(
            content="<div class='alert alert-danger'>Error loading Redis status</div>",
            status_code=500
        )


async def get_redis_stats_htmx(
    request: Request,
    current_user: DiscordUser = Depends(require_super_admin)
) -> HTMLResponse:
    """HTMX endpoint for Redis cache statistics"""
    try:
        from .redis_client import get_redis_client
        
        redis_client = await get_redis_client()
        stats_data = {
            "cache_keys": 0,
            "poll_cache_keys": 0,
            "user_cache_keys": 0,
            "session_keys": 0,
            "total_memory": "0B",
            "hit_rate": 0.0,
            "error": None
        }
        
        if redis_client and redis_client.is_connected and redis_client._client:
            try:
                # Get all keys with patterns using scan_iter for better performance
                all_keys = []
                poll_keys = []
                user_keys = []
                session_keys = []
                
                async for key in redis_client._client.scan_iter(match="*"):
                    all_keys.append(key)
                    if key.startswith("poll:"):
                        poll_keys.append(key)
                    elif key.startswith("user:"):
                        user_keys.append(key)
                    elif key.startswith("session:"):
                        session_keys.append(key)
                
                stats_data["cache_keys"] = len(all_keys)
                stats_data["poll_cache_keys"] = len(poll_keys)
                stats_data["user_cache_keys"] = len(user_keys)
                stats_data["session_keys"] = len(session_keys)
                
                # Get memory info
                memory_info = await redis_client._client.info("memory")
                stats_data["total_memory"] = memory_info.get("used_memory_human", "0B")
                
                # Calculate hit rate
                server_info = await redis_client._client.info()
                keyspace_hits = server_info.get("keyspace_hits", 0)
                keyspace_misses = server_info.get("keyspace_misses", 0)
                total_requests = keyspace_hits + keyspace_misses
                
                if total_requests > 0:
                    stats_data["hit_rate"] = (keyspace_hits / total_requests) * 100
                
            except Exception as e:
                stats_data["error"] = str(e)
        else:
            stats_data["error"] = "Redis client not initialized or not connected"
        
        return templates.TemplateResponse(
            "htmx/super_admin_redis_stats.html",
            {
                "request": request,
                "redis_stats": stats_data
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting Redis stats: {e}")
        return HTMLResponse(
            content="<div class='alert alert-danger'>Error loading Redis stats</div>",
            status_code=500
        )


async def export_system_data_api(
    request: Request,
    current_user: DiscordUser = Depends(require_super_admin)
) -> StreamingResponse:
    """Export comprehensive system data"""
    try:
        db = get_db_session()
        try:
            # Get all system data
            stats = super_admin_service.get_system_stats(db)
            all_polls = super_admin_service.get_all_polls(db, limit=10000)
            
            export_data = {
                "export_info": {
                    "generated_at": datetime.now().isoformat(),
                    "generated_by": current_user.username,
                    "version": "1.0"
                },
                "system_stats": stats,
                "polls_summary": {
                    "total_count": all_polls["total_count"],
                    "polls": all_polls["polls"]
                }
            }
            
            def generate_export():
                yield json.dumps(export_data, indent=2, default=str)
            
            filename = f"polly_system_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            return StreamingResponse(
                generate_export(),
                media_type="application/json",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error exporting system data: {e}")
        raise HTTPException(status_code=500, detail="Error generating system export")


async def get_poll_edit_form_htmx(
    poll_id: int,
    request: Request,
    current_user: DiscordUser = Depends(require_super_admin)
) -> HTMLResponse:
    """HTMX endpoint for poll edit form - PERFORMANCE OPTIMIZED"""
    try:
        db = get_db_session()
        try:
            poll_details = super_admin_service.get_poll_details(db, poll_id)
            
            if not poll_details:
                return HTMLResponse(
                    content="<div class='alert alert-danger'>Poll not found</div>",
                    status_code=404
                )
            
            poll = poll_details["poll"]
            
            # PERFORMANCE OPTIMIZATION: Skip Discord API calls - use static guild list or cache
            guilds = [
                {'id': poll["server_id"], 'name': poll["server_name"] or "Current Server"}
            ] if poll["server_id"] else []
            
            # PERFORMANCE OPTIMIZATION: Use pre-computed timezone list
            common_timezones = [
                {'name': 'UTC', 'display': 'UTC'},
                {'name': 'US/Eastern', 'display': 'US Eastern'},
                {'name': 'US/Central', 'display': 'US Central'},
                {'name': 'US/Mountain', 'display': 'US Mountain'},
                {'name': 'US/Pacific', 'display': 'US Pacific'},
                {'name': 'Europe/London', 'display': 'Europe London'},
                {'name': 'Europe/Paris', 'display': 'Europe Paris'},
                {'name': 'Asia/Tokyo', 'display': 'Asia Tokyo'},
                {'name': 'Australia/Sydney', 'display': 'Australia Sydney'}
            ]
            
            # Format datetime fields for HTML input
            open_time = ""
            close_time = ""
            
            if poll["open_time"]:
                try:
                    open_time = poll["open_time"].strftime('%Y-%m-%dT%H:%M')
                except:
                    pass
            
            if poll["close_time"]:
                try:
                    close_time = poll["close_time"].strftime('%Y-%m-%dT%H:%M')
                except:
                    pass
            
            # Default emojis for new options
            default_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
            
            return templates.TemplateResponse(
                "htmx/super_admin_edit_poll.html",
                {
                    "request": request,
                    "poll": poll,
                    "guilds": guilds,
                    "timezones": common_timezones,
                    "open_time": open_time,
                    "close_time": close_time,
                    "default_emojis": default_emojis,
                    "is_super_admin": True
                }
            )
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error getting poll edit form for {poll_id}: {e}")
        return HTMLResponse(
            content="<div class='alert alert-danger'>Error loading edit form</div>",
            status_code=500
        )


async def update_poll_api(
    poll_id: int,
    request: Request,
    current_user: DiscordUser = Depends(require_super_admin)
) -> JSONResponse:
    """Update poll via API (super admin only)"""
    try:
        # Parse form data
        form_data = await request.form()
        
        # Extract and validate poll data
        poll_data = {}
        
        # Basic fields
        if "name" in form_data:
            poll_data["name"] = str(form_data["name"]).strip()
        
        if "question" in form_data:
            poll_data["question"] = str(form_data["question"]).strip()
        
        # Options and emojis
        options = []
        emojis = []
        
        for i in range(1, 11):  # Support up to 10 options
            option_key = f"option{i}"
            emoji_key = f"emoji{i}"
            
            if option_key in form_data:
                option_text = str(form_data[option_key]).strip()
                if option_text:
                    options.append(option_text)
                    emoji_value = str(form_data.get(emoji_key, "")).strip()
                    emojis.append(emoji_value if emoji_value else f"{i}️⃣")
        
        if options:
            poll_data["options"] = options
            poll_data["emojis"] = emojis
        
        # Boolean fields
        poll_data["anonymous"] = "anonymous" in form_data
        poll_data["multiple_choice"] = "multiple_choice" in form_data
        poll_data["ping_role_enabled"] = "ping_role_enabled" in form_data
        poll_data["ping_role_on_close"] = "ping_role_on_close" in form_data
        poll_data["ping_role_on_update"] = "ping_role_on_update" in form_data
        
        # Numeric fields
        if "max_choices" in form_data and form_data["max_choices"]:
            try:
                poll_data["max_choices"] = int(form_data["max_choices"])
            except ValueError:
                poll_data["max_choices"] = None
        
        # DateTime fields
        if "open_time" in form_data and form_data["open_time"]:
            try:
                from datetime import datetime
                poll_data["open_time"] = datetime.fromisoformat(str(form_data["open_time"]))
            except ValueError:
                pass
        
        if "close_time" in form_data and form_data["close_time"]:
            try:
                from datetime import datetime
                poll_data["close_time"] = datetime.fromisoformat(str(form_data["close_time"]))
            except ValueError:
                pass
        
        # String fields
        string_fields = ["timezone", "image_path", "image_message_text", "ping_role_name", "ping_role_id"]
        for field in string_fields:
            if field in form_data:
                value = str(form_data[field]).strip()
                poll_data[field] = value if value else None
        
        # Update the poll
        db = get_db_session()
        try:
            result = super_admin_service.update_poll(db, poll_id, poll_data, current_user.id)
            
            if result["success"]:
                logger.info(f"Super admin {current_user.username} updated poll {poll_id}")
                return JSONResponse(content=result)
            else:
                return JSONResponse(content=result, status_code=400)
                
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error updating poll {poll_id}: {e}")
        raise HTTPException(status_code=500, detail="Error updating poll")


def add_super_admin_routes(app):
    """Add super admin routes to the FastAPI app"""

    @app.get("/super-admin", response_class=HTMLResponse)
    async def super_admin_dashboard(
        request: Request, current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await get_super_admin_dashboard(request, current_user)

    @app.get("/super-admin/api/polls")
    async def super_admin_polls_api(
        request: Request,
        status: Optional[str] = Query(None),
        server: Optional[str] = Query(None),
        creator: Optional[str] = Query(None),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        sort_by: str = Query("created_at"),
        sort_order: str = Query("desc"),
        current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await get_all_polls_api(
            request, status, server, creator, limit, offset, sort_by, sort_order, current_user
        )

    @app.get("/super-admin/api/stats")
    async def super_admin_stats_api(
        request: Request, current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await get_system_stats_api(request, current_user)

    @app.get("/super-admin/api/poll/{poll_id}")
    async def super_admin_poll_details_api(
        poll_id: int, request: Request, current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await get_poll_details_api(poll_id, request, current_user)

    @app.post("/super-admin/api/poll/{poll_id}/force-close")
    async def super_admin_force_close_poll(
        poll_id: int, request: Request, current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await force_close_poll_api(poll_id, request, current_user)

    @app.post("/super-admin/api/poll/{poll_id}/reopen")
    async def super_admin_reopen_poll(
        poll_id: int, request: Request, current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await reopen_poll_api(poll_id, request, current_user)

    @app.delete("/super-admin/api/poll/{poll_id}")
    async def super_admin_delete_poll(
        poll_id: int, request: Request, current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await delete_poll_api(poll_id, request, current_user)

    @app.get("/super-admin/htmx/polls", response_class=HTMLResponse)
    async def super_admin_polls_htmx(
        request: Request,
        status: Optional[str] = Query(None),
        server: Optional[str] = Query(None),
        creator: Optional[str] = Query(None),
        page: int = Query(1, ge=1),
        current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await get_all_polls_htmx(request, status, server, creator, page, current_user)

    @app.get("/super-admin/htmx/poll/{poll_id}/details", response_class=HTMLResponse)
    async def super_admin_poll_details_htmx(
        poll_id: int, request: Request, current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await get_poll_details_htmx(poll_id, request, current_user)

    @app.get("/super-admin/htmx/logs", response_class=HTMLResponse)
    async def super_admin_logs_htmx(
        request: Request,
        level: Optional[str] = Query(None),
        search: Optional[str] = Query(None),
        time_range: str = Query("24h"),
        current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await get_system_logs_htmx(request, level, search, time_range, current_user)

    @app.get("/super-admin/api/logs/download")
    async def super_admin_download_logs(
        request: Request,
        level: Optional[str] = Query(None),
        search: Optional[str] = Query(None),
        time_range: str = Query("24h"),
        current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await download_logs_api(request, level, search, time_range, current_user)

    @app.get("/super-admin/htmx/redis/status", response_class=HTMLResponse)
    async def super_admin_redis_status_htmx(
        request: Request, current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await get_redis_status_htmx(request, current_user)

    @app.get("/super-admin/htmx/redis/stats", response_class=HTMLResponse)
    async def super_admin_redis_stats_htmx(
        request: Request, current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await get_redis_stats_htmx(request, current_user)

    @app.get("/super-admin/api/export/system-data")
    async def super_admin_export_system_data(
        request: Request, current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await export_system_data_api(request, current_user)

    @app.get("/super-admin/htmx/poll/{poll_id}/edit", response_class=HTMLResponse)
    async def super_admin_poll_edit_form_htmx(
        poll_id: int, request: Request, current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await get_poll_edit_form_htmx(poll_id, request, current_user)

    @app.put("/super-admin/api/poll/{poll_id}")
    async def super_admin_update_poll(
        poll_id: int, request: Request, current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await update_poll_api(poll_id, request, current_user)
