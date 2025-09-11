"""
Super Admin Endpoints
API endpoints for super admin dashboard functionality.
"""

import logging
import os
import re
import json
from datetime import datetime, timedelta
from fastapi import Request, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from typing import Optional, List, Dict, Any

from .super_admin import require_super_admin, super_admin_service, DiscordUser
from .database import get_db_session

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="templates")


async def get_super_admin_dashboard(
    request: Request, current_user: DiscordUser = Depends(require_super_admin)
) -> HTMLResponse:
    """Super admin dashboard page"""
    try:
        db = get_db_session()
        try:
            # Get system statistics
            stats = super_admin_service.get_system_stats(db)
            
            return templates.TemplateResponse(
                "super_admin_dashboard_new.html",
                {
                    "request": request,
                    "user": current_user,
                    "stats": stats,
                    "is_super_admin": True
                }
            )
        finally:
            db.close()
            
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
            result = super_admin_service.force_close_poll(db, poll_id, current_user.id)
            
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
                logger.warning(f"Super admin {current_user.username} deleted poll {poll_id}")
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
    """HTMX endpoint for polls table"""
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
            
            # Get Discord usernames for creators
            from .discord_bot import get_bot_instance
            bot = get_bot_instance()
            
            # Enhance poll data with creator usernames
            for poll in result["polls"]:
                try:
                    if bot and poll["creator_id"]:
                        discord_user = await bot.fetch_user(int(poll["creator_id"]))
                        if discord_user:
                            poll["creator_username"] = discord_user.display_name or discord_user.name
                        else:
                            poll["creator_username"] = f"User {poll['creator_id'][:8]}..."
                    else:
                        poll["creator_username"] = f"User {poll['creator_id'][:8]}..."
                except Exception as e:
                    logger.warning(f"Could not fetch creator username for {poll['creator_id']}: {e}")
                    poll["creator_username"] = f"User {poll['creator_id'][:8]}..."
            
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
    """HTMX endpoint for poll details modal"""
    try:
        db = get_db_session()
        try:
            poll_details = super_admin_service.get_poll_details(db, poll_id)
            
            if not poll_details:
                return HTMLResponse(
                    content="<div class='alert alert-danger'>Poll not found</div>",
                    status_code=404
                )
            
            # Get Discord usernames for voters
            from .discord_bot import get_bot_instance
            bot = get_bot_instance()
            
            # Enhance vote data with usernames
            for vote in poll_details["votes"]:
                try:
                    if bot and vote["user_id"]:
                        discord_user = await bot.fetch_user(int(vote["user_id"]))
                        if discord_user:
                            vote["username"] = discord_user.display_name or discord_user.name
                            vote["avatar_url"] = discord_user.avatar.url if discord_user.avatar else None
                        else:
                            vote["username"] = f"User {vote['user_id'][:8]}..."
                            vote["avatar_url"] = None
                    else:
                        vote["username"] = f"User {vote['user_id'][:8]}..."
                        vote["avatar_url"] = None
                except Exception as e:
                    logger.warning(f"Could not fetch voter username for {vote['user_id']}: {e}")
                    vote["username"] = f"User {vote['user_id'][:8]}..."
                    vote["avatar_url"] = None
            
            # Get creator username
            try:
                if bot and poll_details["poll"]["creator_id"]:
                    discord_user = await bot.fetch_user(int(poll_details["poll"]["creator_id"]))
                    if discord_user:
                        poll_details["poll"]["creator_username"] = discord_user.display_name or discord_user.name
                    else:
                        poll_details["poll"]["creator_username"] = f"User {poll_details['poll']['creator_id'][:8]}..."
                else:
                    poll_details["poll"]["creator_username"] = f"User {poll_details['poll']['creator_id'][:8]}..."
            except Exception as e:
                logger.warning(f"Could not fetch creator username: {e}")
                poll_details["poll"]["creator_username"] = f"User {poll_details['poll']['creator_id'][:8]}..."
            
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


def parse_log_time_range(time_range: str) -> datetime:
    """Parse time range string and return cutoff datetime"""
    now = datetime.now()
    
    if time_range == "1h":
        return now - timedelta(hours=1)
    elif time_range == "6h":
        return now - timedelta(hours=6)
    elif time_range == "24h":
        return now - timedelta(hours=24)
    elif time_range == "7d":
        return now - timedelta(days=7)
    elif time_range == "30d":
        return now - timedelta(days=30)
    else:
        return now - timedelta(hours=24)  # Default to 24h


def parse_log_file(log_path: str, level_filter: Optional[str] = None, 
                  search_filter: Optional[str] = None, 
                  time_cutoff: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Parse log file and return filtered entries"""
    entries = []
    
    if not os.path.exists(log_path):
        return entries
    
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                try:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Parse log entry (assuming format: TIMESTAMP - LEVEL - MESSAGE)
                    log_match = re.match(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ - (\w+) - (.+)$', line)
                    
                    if log_match:
                        timestamp_str, level, message = log_match.groups()
                        
                        try:
                            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                        except ValueError:
                            timestamp = datetime.now()
                        
                        # Apply time filter
                        if time_cutoff and timestamp < time_cutoff:
                            continue
                        
                        # Apply level filter
                        if level_filter and level != level_filter:
                            continue
                        
                        # Apply search filter
                        if search_filter and search_filter.lower() not in message.lower():
                            continue
                        
                        entries.append({
                            'timestamp': timestamp.isoformat(),
                            'level': level,
                            'message': message,
                            'line_number': line_num
                        })
                    else:
                        # Handle multi-line entries or malformed entries - BULLETPROOF VERSION
                        try:
                            # Triple check: entries exists, has length, and last entry has message key
                            if (entries and 
                                len(entries) > 0 and 
                                isinstance(entries[-1], dict) and 
                                'message' in entries[-1]):
                                entries[-1]['message'] += '\n' + line
                            else:
                                # If no entries exist yet or last entry is malformed, create a basic entry
                                entries.append({
                                    'timestamp': datetime.now().isoformat(),
                                    'level': 'INFO',
                                    'message': line,
                                    'line_number': line_num
                                })
                        except (IndexError, KeyError, TypeError, AttributeError) as inner_e:
                            # If anything goes wrong with appending, just create a new entry
                            logger.warning(f"Error appending to log entry at line {line_num}, creating new entry: {inner_e}")
                            try:
                                entries.append({
                                    'timestamp': datetime.now().isoformat(),
                                    'level': 'INFO',
                                    'message': line,
                                    'line_number': line_num
                                })
                            except Exception as append_e:
                                # Ultimate fallback - skip this line entirely
                                logger.error(f"Critical error creating log entry at line {line_num}: {append_e}")
                                continue
                
                except Exception as line_e:
                    # Skip problematic lines entirely
                    logger.warning(f"Skipping problematic log line {line_num}: {line_e}")
                    continue
    
    except Exception as e:
        logger.error(f"Error parsing log file {log_path}: {e}")
        # Return a safe fallback entry
        return [{
            'timestamp': datetime.now().isoformat(),
            'level': 'ERROR',
            'message': f'Error parsing log file {log_path}: {str(e)}',
            'line_number': 1
        }]
    
    try:
        return sorted(entries, key=lambda x: x.get('timestamp', ''), reverse=True)
    except Exception as sort_e:
        logger.error(f"Error sorting log entries: {sort_e}")
        return entries  # Return unsorted if sorting fails


async def get_system_logs_htmx(
    request: Request,
    level: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    time_range: str = Query("24h"),
    current_user: DiscordUser = Depends(require_super_admin)
) -> HTMLResponse:
    """HTMX endpoint for system logs"""
    try:
        time_cutoff = parse_log_time_range(time_range)
        
        # Get logs from multiple sources
        log_files = [
            "polly.log",
            "logs/polly.log",
            "logs/dev.log"
        ]
        
        all_entries = []
        for log_file in log_files:
            if os.path.exists(log_file):
                entries = parse_log_file(log_file, level, search, time_cutoff)
                all_entries.extend(entries)
        
        # Sort all entries by timestamp
        all_entries = sorted(all_entries, key=lambda x: x['timestamp'], reverse=True)
        
        # Limit to 500 most recent entries
        all_entries = all_entries[:500]
        
        return templates.TemplateResponse(
            "htmx/super_admin_logs.html",
            {
                "request": request,
                "log_entries": all_entries,
                "filters": {
                    "level": level,
                    "search": search,
                    "time_range": time_range
                }
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting system logs: {e}")
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
    """Download filtered logs as text file"""
    try:
        time_cutoff = parse_log_time_range(time_range)
        
        log_files = [
            "polly.log",
            "logs/polly.log",
            "logs/dev.log"
        ]
        
        all_entries = []
        for log_file in log_files:
            if os.path.exists(log_file):
                entries = parse_log_file(log_file, level, search, time_cutoff)
                all_entries.extend(entries)
        
        # Sort all entries by timestamp
        all_entries = sorted(all_entries, key=lambda x: x['timestamp'], reverse=True)
        
        # Generate log content
        def generate_log_content():
            yield f"# Polly System Logs Export\n"
            yield f"# Generated: {datetime.now().isoformat()}\n"
            yield f"# Filters: Level={level or 'All'}, Search={search or 'None'}, Time Range={time_range}\n"
            yield f"# Total Entries: {len(all_entries)}\n\n"
            
            for entry in all_entries:
                yield f"{entry['timestamp']} - {entry['level']} - {entry['message']}\n"
        
        filename = f"polly_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        
        return StreamingResponse(
            generate_log_content(),
            media_type="text/plain",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        logger.error(f"Error downloading logs: {e}")
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
