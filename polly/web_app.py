"""
Polly Web Application
FastAPI application setup and core web functionality.
"""

import os
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
import pytz

# Import debug configuration
from .debug_config import get_debug_logger, get_debug_context

from fastapi import FastAPI, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException

from .auth import (
    get_discord_oauth_url,
    exchange_code_for_token,
    get_discord_user,
    create_access_token,
    require_auth,
    save_user_to_db,
    DiscordUser,
)
from .security_middleware import RateLimitMiddleware, SecurityHeadersMiddleware
from .turnstile_middleware import TurnstileSecurityMiddleware
from .auth_middleware import AuthenticationMiddleware
from .database import get_db_session, UserPreference
from .discord_utils import get_user_guilds_with_channels
from .admin_endpoints import add_admin_routes

logger = get_debug_logger(__name__)

# Create directories
os.makedirs("static/uploads", exist_ok=True)
os.makedirs("templates", exist_ok=True)

# Templates setup
templates = Jinja2Templates(directory="templates")
# Add global template variable for debug
_debug_ctx = get_debug_context()
templates.env.globals["POLLY_DEBUG"] = _debug_ctx.get("debug_mode", False)


async def get_user_preferences(user_id: str) -> dict:
    """Get user preferences for poll creation with Redis caching"""
    from .cache_service import get_cache_service

    cache_service = get_cache_service()

    # Try to get from cache first
    cached_prefs = await cache_service.get_cached_user_preferences(user_id)
    if cached_prefs:
        logger.debug(f"Retrieved user preferences from cache for {user_id}")
        return cached_prefs

    # If not in cache, get from database
    db = get_db_session()
    try:
        prefs = (
            db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
        )
        if prefs:
            user_prefs = {
                "last_server_id": prefs.last_server_id,
                "last_channel_id": prefs.last_channel_id,
                "default_timezone": prefs.default_timezone or "US/Eastern",
                "timezone_explicitly_set": bool(prefs.timezone_explicitly_set),
            }
        else:
            user_prefs = {
                "last_server_id": None,
                "last_channel_id": None,
                "default_timezone": "US/Eastern",
                "timezone_explicitly_set": False,
            }

        # Cache the result
        await cache_service.cache_user_preferences(user_id, user_prefs)
        logger.debug(f"Cached user preferences for {user_id}")

        return user_prefs

    except Exception as e:
        logger.error(f"Error getting user preferences for {user_id}: {e}")
        return {
            "last_server_id": None,
            "last_channel_id": None,
            "default_timezone": "US/Eastern",
            "timezone_explicitly_set": False,
        }
    finally:
        db.close()


async def save_user_preferences(
    user_id: str, server_id: str = None, channel_id: str = None, timezone: str = None
):
    """Save user preferences for poll creation with cache invalidation"""
    from .cache_service import get_cache_service

    cache_service = get_cache_service()

    db = get_db_session()
    try:
        prefs = (
            db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
        )

        if prefs:
            # Update existing preferences
            if server_id:
                setattr(prefs, "last_server_id", server_id)
            if channel_id:
                setattr(prefs, "last_channel_id", channel_id)
            if timezone:
                setattr(prefs, "default_timezone", timezone)
                setattr(prefs, "timezone_explicitly_set", True)
            setattr(prefs, "updated_at", datetime.now(pytz.UTC))
        else:
            # Create new preferences
            prefs = UserPreference(
                user_id=user_id,
                last_server_id=server_id,
                last_channel_id=channel_id,
                default_timezone=timezone or "US/Eastern",
                timezone_explicitly_set=bool(timezone),
            )
            db.add(prefs)

        db.commit()

        # Invalidate cache after successful database update
        await cache_service.invalidate_user_preferences(user_id)

        logger.debug(
            f"Saved preferences for user {user_id}: server={server_id}, channel={channel_id}, timezone={timezone}"
        )
    except Exception as e:
        logger.error(f"Error saving user preferences for {user_id}: {e}")
        db.rollback()
    finally:
        db.close()


async def start_background_tasks():
    """Start all background tasks"""
    from .background_tasks import start_scheduler, start_reaction_safeguard
    from .discord_bot import start_bot
    from .redis_client import get_redis_client

    # Initialize Redis connection
    try:
        redis_client = await get_redis_client()
        if redis_client.is_connected:
            logger.info("Redis client initialized successfully")
        else:
            logger.warning("Redis client failed to connect - continuing without Redis")
    except Exception as e:
        logger.error(f"Redis initialization error: {e} - continuing without Redis")

    # Start background tasks
    # Note: Automatic bot owner notifications are initialized in discord_bot.py after bot is ready
    asyncio.create_task(start_scheduler())
    bot_task = asyncio.create_task(start_bot())
    asyncio.create_task(start_reaction_safeguard())
    
    # Start comprehensive recovery after bot is ready
    asyncio.create_task(start_recovery_process(bot_task))


async def start_recovery_process(bot_task):
    """Start the recovery process after bot is ready"""
    try:
        # Wait for bot to start
        await bot_task
        
        # Give bot a moment to fully initialize
        await asyncio.sleep(3)
        
        # Get bot instance and perform recovery
        from .discord_bot import get_bot_instance
        bot = get_bot_instance()
        
        if bot and bot.is_ready():
            logger.info("🔄 Starting comprehensive recovery process")
            
            # Import here to avoid circular imports
            from .recovery_manager import perform_startup_recovery
            recovery_result = await perform_startup_recovery(bot)
            
            if recovery_result["success"]:
                logger.info(f"✅ Recovery completed successfully: {recovery_result['message']}")
                logger.info(f"📊 Recovery stats: {recovery_result['stats']}")
            else:
                logger.error(f"❌ Recovery failed: {recovery_result.get('message', 'Unknown error')}")
        else:
            logger.warning("⚠️ Bot not ready for recovery process")
            
    except Exception as e:
        logger.error(f"❌ Recovery process failed: {e}")


async def shutdown_background_tasks():
    """Shutdown all background tasks"""
    from .background_tasks import shutdown_scheduler
    from .discord_bot import shutdown_bot
    from .redis_client import close_redis_client

    # Shutdown tasks
    await shutdown_scheduler()
    await shutdown_bot()

    # Close Redis connection
    try:
        await close_redis_client()
        logger.info("Redis client closed")
    except Exception as e:
        logger.error(f"Error closing Redis client: {e}")


# Lifespan manager for background tasks
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Polly application...")

    # Initialize database if needed
    from .migrations import initialize_database_if_missing

    try:
        success = initialize_database_if_missing()
        if success:
            logger.info("Database initialization completed successfully")
        else:
            logger.error("Database initialization failed")
            raise RuntimeError("Failed to initialize database")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        raise

    await start_background_tasks()
    yield
    # Shutdown
    await shutdown_background_tasks()


def create_app() -> FastAPI:
    """Create and configure FastAPI application"""
    app = FastAPI(title="Polly - Discord Poll Bot", version="0.2.0", lifespan=lifespan)

    # Add global exception handlers to prevent crashes
    add_exception_handlers(app)

    # Add security middleware (order matters - add in reverse order of execution)
    app.add_middleware(TurnstileSecurityMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        RateLimitMiddleware, requests_per_minute=60, requests_per_hour=1000
    )
    app.add_middleware(AuthenticationMiddleware)

    # Mount static files
    app.mount("/static", StaticFiles(directory="static"), name="static")

    # Add core routes
    add_core_routes(app)

    # Add admin routes
    add_admin_routes(app)

    return app


def add_exception_handlers(app: FastAPI):
    """Add global exception handlers to prevent application crashes"""

    @app.exception_handler(StarletteHTTPException)
    async def custom_http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ):
        """Handle HTTP exceptions gracefully"""
        # Log security-related exceptions
        if exc.status_code in [403, 429]:
            client_ip = (
                request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                or request.headers.get("X-Real-IP", "")
                or (request.client.host if request.client else "unknown")
            )
            # Log rate limiting (429) as info, security blocks (403) as warning
            if exc.status_code == 429:
                logger.info(
                    f"HTTP {exc.status_code} blocked request from {client_ip}: {request.url.path}"
                )
            else:
                logger.warning(
                    f"HTTP {exc.status_code} blocked request from {client_ip}: {request.url.path}"
                )

        # Return JSON response for API endpoints, HTML for web pages
        if request.url.path.startswith("/htmx/") or request.url.path.startswith(
            "/api/"
        ):
            return JSONResponse(
                status_code=exc.status_code, content={"detail": exc.detail}
            )
        else:
            # For web pages, use the default handler
            return await http_exception_handler(request, exc)

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Handle all other exceptions to prevent crashes"""
        client_ip = (
            request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or request.headers.get("X-Real-IP", "")
            or (request.client.host if request.client else "unknown")
        )

        logger.error(
            f"Unhandled exception from {client_ip} on {request.url.path}: {exc}",
            exc_info=True,
        )

        # Return appropriate error response
        if request.url.path.startswith("/htmx/") or request.url.path.startswith(
            "/api/"
        ):
            return JSONResponse(
                status_code=500, content={"detail": "Internal server error"}
            )
        else:
            return HTMLResponse(
                content="<h1>Internal Server Error</h1><p>Something went wrong. Please try again later.</p>",
                status_code=500,
            )


def add_core_routes(app: FastAPI):
    """Add core web routes to the application"""

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        """Home page"""
        return templates.TemplateResponse("index.html", {"request": request, "POLLY_DEBUG": _debug_ctx.get("debug_mode", False)})

    @app.get("/health")
    async def health_check():
        """Health check endpoint including Redis status"""
        from .cache_service import get_cache_service

        cache_service = get_cache_service()
        redis_health = await cache_service.health_check()

        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "redis": redis_health,
        }

    @app.get("/login")
    async def login():
        """Redirect to Discord OAuth"""
        oauth_url = get_discord_oauth_url()
        return RedirectResponse(url=oauth_url)

    @app.get("/auth/callback")
    async def auth_callback(code: str):
        """Handle Discord OAuth callback"""
        try:
            # Exchange code for token
            token_data = await exchange_code_for_token(code)
            access_token = token_data["access_token"]

            # Get user info
            discord_user = await get_discord_user(access_token)

            # Save user to database
            save_user_to_db(discord_user)

            # Create JWT token
            jwt_token = create_access_token(discord_user)

            # Redirect to dashboard with token
            response = RedirectResponse(url="/dashboard")
            response.set_cookie(
                key="access_token",
                value=jwt_token,
                httponly=True,
                secure=True,
                samesite="lax",
            )
            return response

        except Exception as e:
            logger.error(f"Auth callback error: {e}")
            return HTMLResponse("Authentication failed", status_code=400)

    @app.post("/logout")
    async def logout():
        """Logout endpoint - clears authentication cookie"""
        response = RedirectResponse(url="/", status_code=302)
        response.delete_cookie(
            key="access_token", httponly=True, secure=True, samesite="lax"
        )
        return response

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard(
        request: Request, current_user: DiscordUser = Depends(require_auth)
    ):
        """User dashboard with HTMX"""
        from .discord_bot import get_bot_instance
        from decouple import config

        # Check if user has timezone preference set
        user_prefs = await get_user_preferences(current_user.id)

        # Get user's guilds with channels with error handling
        try:
            bot = get_bot_instance()
            user_guilds = await get_user_guilds_with_channels(bot, current_user.id)
            # Ensure user_guilds is always a valid list
            if user_guilds is None:
                user_guilds = []
        except Exception as e:
            logger.error(f"Error getting user guilds for {current_user.id}: {e}")
            user_guilds = []

        # Get Turnstile configuration
        turnstile_enabled = config("TURNSTILE_ENABLED", default=True, cast=bool)
        turnstile_site_key = config(
            "TURNSTILE_SITE_KEY", default="1x00000000000000000000AA"
        )

        return templates.TemplateResponse(
            "dashboard_htmx.html",
            {
                "request": request,
                "user": current_user,
                "guilds": user_guilds,
                "show_timezone_prompt": user_prefs.get("last_server_id") is None
                and not user_prefs.get("timezone_explicitly_set", False),
                "turnstile_enabled": turnstile_enabled,
                "turnstile_site_key": turnstile_site_key,
                "POLLY_DEBUG": _debug_ctx.get("debug_mode", False),
            },
        )

    # Add HTMX endpoints
    add_htmx_routes(app)
    
    # Add static poll routes
    add_static_poll_routes(app)


def add_static_poll_routes(app: FastAPI):
    """Add static poll page routes to serve cached content for closed polls"""
    from .static_page_generator import get_static_page_generator
    from fastapi.responses import FileResponse
    
    @app.get("/poll/{poll_id}/static", response_class=HTMLResponse)
    async def serve_static_poll_details(poll_id: int):
        """Serve static poll details page for closed polls using proper template"""
        try:
            from .database import Poll, Vote, TypeSafeColumn
            from datetime import datetime
            
            # Get poll data directly from database since we need the full poll object
            db = get_db_session()
            try:
                poll = db.query(Poll).filter(Poll.id == poll_id).first()
                if not poll:
                    from fastapi import HTTPException
                    raise HTTPException(status_code=404, detail="Poll not found")
                
                # Check if poll is closed
                poll_status = TypeSafeColumn.get_string(poll, "status")
                if poll_status != "closed":
                    from fastapi import HTTPException
                    raise HTTPException(status_code=404, detail="Static page only available for closed polls")
                
                # Get votes for the poll
                votes = db.query(Vote).filter(Vote.poll_id == poll_id).order_by(Vote.voted_at.desc()).all()
                
                # Prepare vote data (anonymized for static pages)
                vote_data = []
                unique_users = set()
                
                for vote in votes:
                    try:
                        user_id = TypeSafeColumn.get_string(vote, "user_id")
                        option_index = TypeSafeColumn.get_int(vote, "option_index")
                        voted_at = TypeSafeColumn.get_datetime(vote, "voted_at")
                        
                        # For static pages, always anonymize usernames for privacy
                        if user_id not in unique_users:
                            username = f"User {len(unique_users) + 1}"
                        else:
                            username = f"User {list(unique_users).index(user_id) + 1}"
                        
                        # Get option details
                        options = poll.options
                        emojis = poll.emojis
                        option_text = options[option_index] if option_index < len(options) else "Unknown Option"
                        emoji = emojis[option_index] if option_index < len(emojis) else "📊"
                        
                        vote_data.append({
                            "username": username,
                            "option_index": option_index,
                            "option_text": option_text,
                            "emoji": emoji,
                            "voted_at": voted_at,
                            "is_unique": user_id not in unique_users
                        })
                        
                        unique_users.add(user_id)
                        
                    except Exception as e:
                        logger.error(f"Error processing vote data: {e}")
                        continue
                
                # Get poll data
                options = poll.options
                emojis = poll.emojis
                is_anonymous = TypeSafeColumn.get_bool(poll, "anonymous", False)
                total_votes = len(votes)
                unique_voters = len(unique_users)
                results = poll.get_results()
                
                # Use proper template instead of embedded HTML
                response = templates.TemplateResponse(
                    "static/poll_details_static_wrapper.html",
                    {
                        "poll": poll,
                        "vote_data": vote_data,
                        "total_votes": total_votes,
                        "unique_voters": unique_voters,
                        "results": results,
                        "options": options,
                        "emojis": emojis,
                        "is_anonymous": is_anonymous,
                        "generated_at": datetime.now(),
                        "is_static": True
                    }
                )
                response.headers["Cache-Control"] = "public, max-age=86400"
                response.headers["X-Static-Content"] = "true"
                return response
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error serving static poll {poll_id}: {e}")
            from fastapi import HTTPException
            raise HTTPException(status_code=500, detail="Error loading static poll page")
    
    @app.get("/poll/{poll_id}/data.json")
    async def serve_static_poll_data(poll_id: int):
        """Serve static poll data JSON for closed polls"""
        try:
            generator = get_static_page_generator()
            
            # Check if static data exists
            data_path = generator._get_static_data_path(poll_id)
            if data_path.exists():
                return FileResponse(
                    path=str(data_path),
                    media_type="application/json",
                    headers={
                        "Cache-Control": "public, max-age=86400",  # Cache for 24 hours
                        "X-Static-Content": "true"
                    }
                )
            else:
                # Static data doesn't exist, return 404
                from fastapi import HTTPException
                raise HTTPException(status_code=404, detail="Static poll data not found")
                
        except Exception as e:
            logger.error(f"Error serving static poll data {poll_id}: {e}")
            from fastapi import HTTPException
            raise HTTPException(status_code=500, detail="Error loading static poll data")


def add_htmx_routes(app: FastAPI):
    """Add HTMX endpoints to the application"""
    from .htmx_endpoints import (
        get_polls_htmx,
        get_stats_htmx,
        get_create_form_htmx,
        get_channels_htmx,
        add_option_htmx,
        remove_option_htmx,
        upload_image_htmx,
        remove_image_htmx,
        get_servers_htmx,
        get_settings_htmx,
        save_settings_htmx,
        get_polls_realtime_htmx,
        create_poll_htmx,
        get_poll_edit_form,
        get_poll_details_htmx,
        get_poll_results_realtime_htmx,
        close_poll_htmx,
        delete_poll_htmx,
        get_guild_emojis_htmx,
        get_roles_htmx,
        open_poll_now_htmx,
    )
    from .discord_bot import get_bot_instance
    from .background_tasks import get_scheduler

    @app.get("/htmx/polls", response_class=HTMLResponse)
    async def htmx_polls(
        request: Request,
        filter: str = None,
        current_user: DiscordUser = Depends(require_auth),
    ):
        return await get_polls_htmx(request, filter, current_user)

    @app.get("/htmx/stats", response_class=HTMLResponse)
    async def htmx_stats(
        request: Request, current_user: DiscordUser = Depends(require_auth)
    ):
        return await get_stats_htmx(request, current_user)

    @app.get("/htmx/create-form", response_class=HTMLResponse)
    async def htmx_create_form(
        request: Request, current_user: DiscordUser = Depends(require_auth)
    ):
        bot = get_bot_instance()
        return await get_create_form_htmx(request, bot, current_user)

    @app.get("/htmx/create-form-template/{poll_id}", response_class=HTMLResponse)
    async def htmx_create_form_template(
        poll_id: int,
        request: Request,
        current_user: DiscordUser = Depends(require_auth),
    ):
        from .htmx_endpoints import get_create_form_template_htmx

        bot = get_bot_instance()
        return await get_create_form_template_htmx(poll_id, request, bot, current_user)

    @app.get("/htmx/channels", response_class=HTMLResponse)
    async def htmx_channels(
        server_id: str,
        preselect_last_channel: bool = True,
        current_user: DiscordUser = Depends(require_auth),
    ):
        bot = get_bot_instance()
        return await get_channels_htmx(
            server_id, bot, current_user, preselect_last_channel
        )

    @app.get("/htmx/roles", response_class=HTMLResponse)
    async def htmx_roles(
        server_id: str, current_user: DiscordUser = Depends(require_auth)
    ):
        bot = get_bot_instance()
        return await get_roles_htmx(server_id, bot, current_user)

    @app.post("/htmx/add-option", response_class=HTMLResponse)
    async def htmx_add_option(
        request: Request, current_user: DiscordUser = Depends(require_auth)
    ):
        return await add_option_htmx(request)

    @app.delete("/htmx/remove-option", response_class=HTMLResponse)
    async def htmx_remove_option(current_user: DiscordUser = Depends(require_auth)):
        return await remove_option_htmx()

    @app.post("/htmx/upload-image")
    async def htmx_upload_image(
        request: Request, current_user: DiscordUser = Depends(require_auth)
    ):
        return await upload_image_htmx(request, current_user)

    @app.delete("/htmx/remove-image")
    async def htmx_remove_image(
        request: Request, current_user: DiscordUser = Depends(require_auth)
    ):
        return await remove_image_htmx(request, current_user)

    @app.get("/htmx/servers", response_class=HTMLResponse)
    async def htmx_servers(
        request: Request, current_user: DiscordUser = Depends(require_auth)
    ):
        bot = get_bot_instance()
        return await get_servers_htmx(request, bot, current_user)

    @app.get("/htmx/settings", response_class=HTMLResponse)
    async def htmx_settings(
        request: Request, current_user: DiscordUser = Depends(require_auth)
    ):
        return await get_settings_htmx(request, current_user)

    @app.post("/htmx/settings", response_class=HTMLResponse)
    async def htmx_save_settings(
        request: Request, current_user: DiscordUser = Depends(require_auth)
    ):
        return await save_settings_htmx(request, current_user)

    @app.get("/htmx/polls-realtime", response_class=HTMLResponse)
    async def htmx_polls_realtime(
        request: Request,
        filter: str = None,
        current_user: DiscordUser = Depends(require_auth),
    ):
        return await get_polls_realtime_htmx(request, filter, current_user)

    @app.post("/htmx/create-poll", response_class=HTMLResponse)
    async def htmx_create_poll(
        request: Request, current_user: DiscordUser = Depends(require_auth)
    ):
        bot = get_bot_instance()
        scheduler = get_scheduler()
        return await create_poll_htmx(request, bot, scheduler, current_user)

    @app.get("/htmx/poll/{poll_id}/edit", response_class=HTMLResponse)
    async def htmx_poll_edit(
        poll_id: int,
        request: Request,
        current_user: DiscordUser = Depends(require_auth),
    ):
        bot = get_bot_instance()
        return await get_poll_edit_form(poll_id, request, bot, current_user)

    @app.post("/htmx/poll/{poll_id}/edit", response_class=HTMLResponse)
    async def htmx_poll_update(
        poll_id: int,
        request: Request,
        current_user: DiscordUser = Depends(require_auth),
    ):
        from .htmx_endpoints import update_poll_htmx

        bot = get_bot_instance()
        scheduler = get_scheduler()
        return await update_poll_htmx(poll_id, request, bot, scheduler, current_user)

    @app.get("/htmx/poll/{poll_id}/details", response_class=HTMLResponse)
    async def htmx_poll_details(
        poll_id: int,
        request: Request,
        current_user: DiscordUser = Depends(require_auth),
    ):
        return await get_poll_details_htmx(poll_id, request, current_user)

    @app.get("/htmx/poll/{poll_id}/results-realtime", response_class=HTMLResponse)
    async def htmx_poll_results_realtime(
        poll_id: int,
        request: Request,
        current_user: DiscordUser = Depends(require_auth),
    ):
        return await get_poll_results_realtime_htmx(poll_id, request, current_user)

    @app.post("/htmx/poll/{poll_id}/open-now", response_class=HTMLResponse)
    async def htmx_open_poll_now(
        poll_id: int,
        request: Request,
        current_user: DiscordUser = Depends(require_auth),
    ):
        bot = get_bot_instance()
        scheduler = get_scheduler()
        return await open_poll_now_htmx(poll_id, request, bot, scheduler, current_user)

    @app.post("/htmx/poll/{poll_id}/close", response_class=HTMLResponse)
    async def htmx_close_poll(
        poll_id: int,
        request: Request,
        current_user: DiscordUser = Depends(require_auth),
    ):
        bot = get_bot_instance()
        return await close_poll_htmx(poll_id, request, bot, current_user)

    @app.delete("/htmx/poll/{poll_id}", response_class=HTMLResponse)
    async def htmx_delete_poll(
        poll_id: int,
        request: Request,
        current_user: DiscordUser = Depends(require_auth),
    ):
        return await delete_poll_htmx(poll_id, request, current_user)

    @app.get("/htmx/guild-emojis/{server_id}")
    async def htmx_guild_emojis(
        server_id: str, current_user: DiscordUser = Depends(require_auth)
    ):
        bot = get_bot_instance()
        return await get_guild_emojis_htmx(server_id, bot, current_user)

    @app.post("/htmx/import-json", response_class=HTMLResponse)
    async def htmx_import_json(
        request: Request, current_user: DiscordUser = Depends(require_auth)
    ):
        from .htmx_endpoints import import_json_htmx

        bot = get_bot_instance()
        return await import_json_htmx(request, bot, current_user)

    @app.get("/htmx/create-form-json-import", response_class=HTMLResponse)
    async def htmx_create_form_json_import(
        request: Request, current_user: DiscordUser = Depends(require_auth)
    ):
        from .htmx_endpoints import get_create_form_json_import_htmx

        bot = get_bot_instance()
        return await get_create_form_json_import_htmx(request, bot, current_user)

    @app.get("/htmx/poll/{poll_id}/export-json")
    async def htmx_export_poll_json(
        poll_id: int,
        request: Request,
        current_user: DiscordUser = Depends(require_auth),
    ):
        from .htmx_endpoints import export_poll_json_htmx

        return await export_poll_json_htmx(poll_id, request, current_user)

    @app.get("/htmx/poll/{poll_id}/dashboard", response_class=HTMLResponse)
    async def htmx_poll_dashboard(
        poll_id: int,
        request: Request,
        current_user: DiscordUser = Depends(require_auth),
    ):
        from .htmx_endpoints import get_poll_dashboard_htmx

        bot = get_bot_instance()
        return await get_poll_dashboard_htmx(poll_id, request, bot, current_user)

    @app.get("/htmx/poll/{poll_id}/export-csv")
    async def htmx_export_poll_csv(
        poll_id: int,
        request: Request,
        current_user: DiscordUser = Depends(require_auth),
    ):
        logger.info(f"🔍 CSV Export Route Called - poll_id: {poll_id}, user: {current_user.username}")
        logger.info(f"🔍 Request URL: {request.url}")
        logger.info(f"🔍 Request method: {request.method}")
        
        try:
            from .htmx_endpoints import export_poll_csv
            logger.info("🔍 Successfully imported export_poll_csv function")
            
            bot = get_bot_instance()
            logger.info(f"🔍 Bot instance obtained: {bot is not None}")
            
            logger.info("🔍 Calling export_poll_csv function...")
            result = await export_poll_csv(poll_id, request, bot, current_user)
            logger.info("🔍 CSV export function completed successfully")
            return result
            
        except Exception as e:
            logger.error(f"❌ CSV Export Route Error: {e}", exc_info=True)
            raise


# Create the app instance
app = create_app()
