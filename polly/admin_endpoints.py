"""
Admin Endpoints
Administrative endpoints for managing security and system status.
"""

import logging
from fastapi import Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from .auth import require_auth, DiscordUser
from .ip_blocker import get_ip_blocker

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="templates")


async def get_security_status(
    request: Request, current_user: DiscordUser = Depends(require_auth)
) -> JSONResponse:
    """Get current security status including blocked IPs"""

    # For now, allow any authenticated user to view security status
    # In production, you might want to restrict this to specific admin users

    ip_blocker = get_ip_blocker()
    blocked_ips = ip_blocker.get_blocked_ips()

    # Get violation counts for blocked IPs
    ip_details = []
    for ip in blocked_ips:
        ip_details.append(
            {"ip": ip, "violation_count": ip_blocker.get_violation_count(ip)}
        )

    return JSONResponse(
        {
            "blocked_ips": len(blocked_ips),
            "ip_details": ip_details,
            "timestamp": request.headers.get("X-Request-Time", "unknown"),
        }
    )


async def unblock_ip(
    request: Request, current_user: DiscordUser = Depends(require_auth)
) -> JSONResponse:
    """Unblock a specific IP address"""

    # For now, allow any authenticated user to unblock IPs
    # In production, you might want to restrict this to specific admin users

    try:
        body = await request.json()
        ip_to_unblock = body.get("ip")

        if not ip_to_unblock:
            raise HTTPException(status_code=400, detail="IP address is required")

        ip_blocker = get_ip_blocker()
        success = ip_blocker.unblock_ip(ip_to_unblock)

        if success:
            logger.info(f"IP {ip_to_unblock} unblocked by user {current_user.username}")
            return JSONResponse(
                {"success": True, "message": f"IP {ip_to_unblock} has been unblocked"}
            )
        else:
            return JSONResponse(
                {"success": False, "message": f"IP {ip_to_unblock} was not blocked"}
            )

    except Exception as e:
        logger.error(f"Error unblocking IP: {e}")
        raise HTTPException(status_code=500, detail="Failed to unblock IP")


async def get_system_health(
    request: Request, current_user: DiscordUser = Depends(require_auth)
) -> JSONResponse:
    """Get system health information"""

    try:
        from .cache_service import get_cache_service
        from .discord_bot import get_bot_instance

        cache_service = get_cache_service()
        redis_health = await cache_service.health_check()

        # Check Discord bot status
        bot = get_bot_instance()
        bot_status = "connected" if bot and bot.is_ready() else "disconnected"

        ip_blocker = get_ip_blocker()
        blocked_ips_count = len(ip_blocker.get_blocked_ips())

        return JSONResponse(
            {
                "status": "healthy",
                "components": {
                    "redis": redis_health,
                    "discord_bot": bot_status,
                    "blocked_ips": blocked_ips_count,
                },
                "timestamp": request.headers.get("X-Request-Time", "unknown"),
            }
        )

    except Exception as e:
        logger.error(f"Error getting system health: {e}")
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)


async def manual_full_recovery(
    request: Request, current_user: DiscordUser = Depends(require_auth)
) -> JSONResponse:
    """Manual full recovery endpoint for administrators"""
    try:
        from .discord_bot import get_bot_instance
        from .recovery_manager import perform_startup_recovery
        
        bot = get_bot_instance()
        if not bot or not bot.is_ready():
            return JSONResponse(
                status_code=503,
                content={"error": "Discord bot is not ready", "success": False}
            )
        
        logger.info(f"Manual full recovery initiated by user {current_user.username}")
        recovery_result = await perform_startup_recovery(bot)
        
        if recovery_result["success"]:
            logger.info(f"Manual recovery completed successfully by {current_user.username}")
            return JSONResponse(content=recovery_result)
        else:
            logger.error(f"Manual recovery failed for {current_user.username}: {recovery_result.get('error')}")
            return JSONResponse(status_code=500, content=recovery_result)
            
    except Exception as e:
        logger.error(f"Manual recovery endpoint error: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "success": False}
        )


async def recover_specific_poll(
    poll_id: int, request: Request, current_user: DiscordUser = Depends(require_auth)
) -> JSONResponse:
    """Recover a specific poll by ID"""
    try:
        from .discord_bot import get_bot_instance
        from .recovery_manager import recover_poll
        
        bot = get_bot_instance()
        if not bot or not bot.is_ready():
            return JSONResponse(
                status_code=503,
                content={"error": "Discord bot is not ready", "success": False}
            )
        
        logger.info(f"Manual poll recovery for poll {poll_id} initiated by user {current_user.username}")
        recovery_result = await recover_poll(bot, poll_id)
        
        if recovery_result["success"]:
            logger.info(f"Poll {poll_id} recovery completed successfully by {current_user.username}")
            return JSONResponse(content=recovery_result)
        else:
            logger.error(f"Poll {poll_id} recovery failed for {current_user.username}: {recovery_result.get('error')}")
            return JSONResponse(status_code=500, content=recovery_result)
            
    except Exception as e:
        logger.error(f"Poll recovery endpoint error: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "success": False}
        )


async def get_recovery_stats(
    request: Request, current_user: DiscordUser = Depends(require_auth)
) -> JSONResponse:
    """Get current recovery statistics"""
    try:
        from .recovery_manager import get_recovery_manager
        
        recovery_manager = get_recovery_manager()
        if recovery_manager:
            stats = recovery_manager.get_recovery_stats()
            return JSONResponse(content={"success": True, "stats": stats})
        else:
            return JSONResponse(content={"success": True, "stats": {}, "message": "Recovery manager not initialized"})
            
    except Exception as e:
        logger.error(f"Recovery stats endpoint error: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "success": False}
        )


async def regenerate_static_content(
    request: Request, current_user: DiscordUser = Depends(require_auth)
) -> JSONResponse:
    """Regenerate all static content for closed polls"""
    try:
        from .static_recovery import StaticContentRecovery
        
        recovery = StaticContentRecovery()
        result = await recovery.regenerate_all_static_content()
        
        logger.info(f"Static content regeneration initiated by user {current_user.username}")
        return JSONResponse(content=result)
            
    except Exception as e:
        logger.error(f"Static content regeneration error: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "success": False}
        )


async def get_static_content_stats(
    request: Request, current_user: DiscordUser = Depends(require_auth)
) -> JSONResponse:
    """Get static content statistics"""
    try:
        from .static_recovery import StaticContentRecovery
        
        recovery = StaticContentRecovery()
        stats = await recovery.get_static_content_stats()
        
        return JSONResponse(content={"success": True, "stats": stats})
            
    except Exception as e:
        logger.error(f"Static content stats error: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "success": False}
        )


def add_admin_routes(app):
    """Add admin routes to the FastAPI app"""

    @app.get("/admin/security/status")
    async def admin_security_status(
        request: Request, current_user: DiscordUser = Depends(require_auth)
    ):
        return await get_security_status(request, current_user)

    @app.post("/admin/security/unblock")
    async def admin_unblock_ip(
        request: Request, current_user: DiscordUser = Depends(require_auth)
    ):
        return await unblock_ip(request, current_user)

    @app.get("/admin/health")
    async def admin_system_health(
        request: Request, current_user: DiscordUser = Depends(require_auth)
    ):
        return await get_system_health(request, current_user)

    @app.post("/admin/recovery/full")
    async def admin_manual_full_recovery(
        request: Request, current_user: DiscordUser = Depends(require_auth)
    ):
        return await manual_full_recovery(request, current_user)

    @app.post("/admin/recovery/poll/{poll_id}")
    async def admin_recover_specific_poll(
        poll_id: int, request: Request, current_user: DiscordUser = Depends(require_auth)
    ):
        return await recover_specific_poll(poll_id, request, current_user)

    @app.get("/admin/recovery/stats")
    async def admin_recovery_stats(
        request: Request, current_user: DiscordUser = Depends(require_auth)
    ):
        return await get_recovery_stats(request, current_user)

    @app.post("/admin/static/regenerate")
    async def admin_regenerate_static_content(
        request: Request, current_user: DiscordUser = Depends(require_auth)
    ):
        return await regenerate_static_content(request, current_user)

    @app.get("/admin/static/stats")
    async def admin_static_content_stats(
        request: Request, current_user: DiscordUser = Depends(require_auth)
    ):
        return await get_static_content_stats(request, current_user)
