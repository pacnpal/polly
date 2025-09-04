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
