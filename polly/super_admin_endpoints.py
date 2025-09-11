"""
Super Admin Endpoints
API endpoints for super admin dashboard functionality.
"""

import logging
from fastapi import Request, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Optional

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
                "super_admin_dashboard.html",
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
