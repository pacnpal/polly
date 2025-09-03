"""
Polly Web Application
FastAPI application setup and core web functionality.
"""

import os
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
import pytz

from fastapi import FastAPI, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse

from .auth import (
    get_discord_oauth_url, exchange_code_for_token, get_discord_user,
    create_access_token, require_auth, save_user_to_db, DiscordUser
)
from .database import get_db_session, UserPreference
from .discord_utils import get_user_guilds_with_channels
from .error_handler import setup_automatic_bot_owner_notifications

logger = logging.getLogger(__name__)

# Create directories
os.makedirs("static/uploads", exist_ok=True)
os.makedirs("templates", exist_ok=True)

# Templates setup
templates = Jinja2Templates(directory="templates")


def get_user_preferences(user_id: str) -> dict:
    """Get user preferences for poll creation"""
    db = get_db_session()
    try:
        prefs = db.query(UserPreference).filter(
            UserPreference.user_id == user_id).first()
        if prefs:
            return {
                "last_server_id": prefs.last_server_id,
                "last_channel_id": prefs.last_channel_id,
                "default_timezone": prefs.default_timezone or "US/Eastern",
                "timezone_explicitly_set": bool(prefs.timezone_explicitly_set)
            }
        return {
            "last_server_id": None,
            "last_channel_id": None,
            "default_timezone": "US/Eastern",
            "timezone_explicitly_set": False
        }
    except Exception as e:
        logger.error(f"Error getting user preferences for {user_id}: {e}")
        return {
            "last_server_id": None,
            "last_channel_id": None,
            "default_timezone": "US/Eastern",
            "timezone_explicitly_set": False
        }
    finally:
        db.close()


def save_user_preferences(user_id: str, server_id: str = None, channel_id: str = None, timezone: str = None):
    """Save user preferences for poll creation"""
    db = get_db_session()
    try:
        prefs = db.query(UserPreference).filter(
            UserPreference.user_id == user_id).first()

        if prefs:
            # Update existing preferences
            if server_id:
                setattr(prefs, 'last_server_id', server_id)
            if channel_id:
                setattr(prefs, 'last_channel_id', channel_id)
            if timezone:
                setattr(prefs, 'default_timezone', timezone)
                setattr(prefs, 'timezone_explicitly_set', True)
            setattr(prefs, 'updated_at', datetime.now(pytz.UTC))
        else:
            # Create new preferences
            prefs = UserPreference(
                user_id=user_id,
                last_server_id=server_id,
                last_channel_id=channel_id,
                default_timezone=timezone or "US/Eastern",
                timezone_explicitly_set=bool(timezone)
            )
            db.add(prefs)

        db.commit()
        logger.debug(
            f"Saved preferences for user {user_id}: server={server_id}, channel={channel_id}, timezone={timezone}")
    except Exception as e:
        logger.error(f"Error saving user preferences for {user_id}: {e}")
        db.rollback()
    finally:
        db.close()


async def start_background_tasks():
    """Start all background tasks"""
    from .background_tasks import start_scheduler, start_reaction_safeguard
    from .discord_bot import start_bot

    # Start background tasks
    # Note: Automatic bot owner notifications are initialized in discord_bot.py after bot is ready
    asyncio.create_task(start_scheduler())
    asyncio.create_task(start_bot())
    asyncio.create_task(start_reaction_safeguard())


async def shutdown_background_tasks():
    """Shutdown all background tasks"""
    from .background_tasks import shutdown_scheduler
    from .discord_bot import shutdown_bot

    # Shutdown tasks
    await shutdown_scheduler()
    await shutdown_bot()


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
    app = FastAPI(
        title="Polly - Discord Poll Bot",
        version="0.2.0",
        lifespan=lifespan
    )

    # Mount static files
    app.mount("/static", StaticFiles(directory="static"), name="static")

    # Add core routes
    add_core_routes(app)

    return app


def add_core_routes(app: FastAPI):
    """Add core web routes to the application"""

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        """Home page"""
        return templates.TemplateResponse("index.html", {"request": request})

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
            response.set_cookie(key="access_token", value=jwt_token,
                                httponly=True, secure=True, samesite="lax")
            return response

        except Exception as e:
            logger.error(f"Auth callback error: {e}")
            return HTMLResponse("Authentication failed", status_code=400)

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard(request: Request, current_user: DiscordUser = Depends(require_auth)):
        """User dashboard with HTMX"""
        from .discord_bot import get_bot_instance

        # Check if user has timezone preference set
        user_prefs = get_user_preferences(current_user.id)

        # Get user's guilds with channels with error handling
        try:
            bot = get_bot_instance()
            user_guilds = await get_user_guilds_with_channels(bot, current_user.id)
            # Ensure user_guilds is always a valid list
            if user_guilds is None:
                user_guilds = []
        except Exception as e:
            logger.error(
                f"Error getting user guilds for {current_user.id}: {e}")
            user_guilds = []

        return templates.TemplateResponse("dashboard_htmx.html", {
            "request": request,
            "user": current_user,
            "guilds": user_guilds,
            "show_timezone_prompt": user_prefs.get("last_server_id") is None and not user_prefs.get("timezone_explicitly_set", False)
        })

    # Add HTMX endpoints
    add_htmx_routes(app)


def add_htmx_routes(app: FastAPI):
    """Add HTMX endpoints to the application"""
    from .htmx_endpoints import (
        get_polls_htmx, get_stats_htmx, get_create_form_htmx, get_channels_htmx,
        add_option_htmx, remove_option_htmx, upload_image_htmx, remove_image_htmx,
        get_servers_htmx, get_settings_htmx, save_settings_htmx, get_polls_realtime_htmx,
        create_poll_htmx, get_poll_edit_form, get_poll_details_htmx,
        get_poll_results_realtime_htmx, close_poll_htmx, delete_poll_htmx,
        get_guild_emojis_htmx, get_roles_htmx
    )
    from .discord_bot import get_bot_instance
    from .background_tasks import get_scheduler

    @app.get("/htmx/polls", response_class=HTMLResponse)
    async def htmx_polls(request: Request, filter: str = None, current_user: DiscordUser = Depends(require_auth)):
        return await get_polls_htmx(request, filter, current_user)

    @app.get("/htmx/stats", response_class=HTMLResponse)
    async def htmx_stats(request: Request, current_user: DiscordUser = Depends(require_auth)):
        return await get_stats_htmx(request, current_user)

    @app.get("/htmx/create-form", response_class=HTMLResponse)
    async def htmx_create_form(request: Request, current_user: DiscordUser = Depends(require_auth)):
        bot = get_bot_instance()
        return await get_create_form_htmx(request, bot, current_user)

    @app.get("/htmx/create-form-template/{poll_id}", response_class=HTMLResponse)
    async def htmx_create_form_template(poll_id: int, request: Request, current_user: DiscordUser = Depends(require_auth)):
        from .htmx_endpoints import get_create_form_template_htmx
        bot = get_bot_instance()
        return await get_create_form_template_htmx(poll_id, request, bot, current_user)

    @app.get("/htmx/channels", response_class=HTMLResponse)
    async def htmx_channels(server_id: str, preselect_last_channel: bool = False, current_user: DiscordUser = Depends(require_auth)):
        bot = get_bot_instance()
        return await get_channels_htmx(server_id, bot, current_user, preselect_last_channel)

    @app.get("/htmx/roles", response_class=HTMLResponse)
    async def htmx_roles(server_id: str, current_user: DiscordUser = Depends(require_auth)):
        bot = get_bot_instance()
        return await get_roles_htmx(server_id, bot, current_user)

    @app.post("/htmx/add-option", response_class=HTMLResponse)
    async def htmx_add_option(request: Request):
        return await add_option_htmx(request)

    @app.delete("/htmx/remove-option", response_class=HTMLResponse)
    async def htmx_remove_option():
        return await remove_option_htmx()

    @app.post("/htmx/upload-image")
    async def htmx_upload_image(request: Request, current_user: DiscordUser = Depends(require_auth)):
        return await upload_image_htmx(request, current_user)

    @app.delete("/htmx/remove-image")
    async def htmx_remove_image(request: Request, current_user: DiscordUser = Depends(require_auth)):
        return await remove_image_htmx(request, current_user)

    @app.get("/htmx/servers", response_class=HTMLResponse)
    async def htmx_servers(request: Request, current_user: DiscordUser = Depends(require_auth)):
        bot = get_bot_instance()
        return await get_servers_htmx(request, bot, current_user)

    @app.get("/htmx/settings", response_class=HTMLResponse)
    async def htmx_settings(request: Request, current_user: DiscordUser = Depends(require_auth)):
        return await get_settings_htmx(request, current_user)

    @app.post("/htmx/settings", response_class=HTMLResponse)
    async def htmx_save_settings(request: Request, current_user: DiscordUser = Depends(require_auth)):
        return await save_settings_htmx(request, current_user)

    @app.get("/htmx/polls-realtime", response_class=HTMLResponse)
    async def htmx_polls_realtime(request: Request, filter: str = None, current_user: DiscordUser = Depends(require_auth)):
        return await get_polls_realtime_htmx(request, filter, current_user)

    @app.post("/htmx/create-poll", response_class=HTMLResponse)
    async def htmx_create_poll(request: Request, current_user: DiscordUser = Depends(require_auth)):
        bot = get_bot_instance()
        scheduler = get_scheduler()
        return await create_poll_htmx(request, bot, scheduler, current_user)

    @app.get("/htmx/poll/{poll_id}/edit", response_class=HTMLResponse)
    async def htmx_poll_edit(poll_id: int, request: Request, current_user: DiscordUser = Depends(require_auth)):
        bot = get_bot_instance()
        return await get_poll_edit_form(poll_id, request, bot, current_user)

    @app.post("/htmx/poll/{poll_id}/edit", response_class=HTMLResponse)
    async def htmx_poll_update(poll_id: int, request: Request, current_user: DiscordUser = Depends(require_auth)):
        from .htmx_endpoints import update_poll_htmx
        bot = get_bot_instance()
        scheduler = get_scheduler()
        return await update_poll_htmx(poll_id, request, bot, scheduler, current_user)

    @app.get("/htmx/poll/{poll_id}/details", response_class=HTMLResponse)
    async def htmx_poll_details(poll_id: int, request: Request, current_user: DiscordUser = Depends(require_auth)):
        return await get_poll_details_htmx(poll_id, request, current_user)

    @app.get("/htmx/poll/{poll_id}/results-realtime", response_class=HTMLResponse)
    async def htmx_poll_results_realtime(poll_id: int, request: Request, current_user: DiscordUser = Depends(require_auth)):
        return await get_poll_results_realtime_htmx(poll_id, request, current_user)

    @app.post("/htmx/poll/{poll_id}/close", response_class=HTMLResponse)
    async def htmx_close_poll(poll_id: int, request: Request, current_user: DiscordUser = Depends(require_auth)):
        return await close_poll_htmx(poll_id, request, current_user)

    @app.delete("/htmx/poll/{poll_id}", response_class=HTMLResponse)
    async def htmx_delete_poll(poll_id: int, request: Request, current_user: DiscordUser = Depends(require_auth)):
        return await delete_poll_htmx(poll_id, request, current_user)

    @app.get("/htmx/guild-emojis/{server_id}")
    async def htmx_guild_emojis(server_id: str, current_user: DiscordUser = Depends(require_auth)):
        bot = get_bot_instance()
        return await get_guild_emojis_htmx(server_id, bot, current_user)

    @app.post("/htmx/import-json", response_class=HTMLResponse)
    async def htmx_import_json(request: Request, current_user: DiscordUser = Depends(require_auth)):
        from .htmx_endpoints import import_json_htmx
        return await import_json_htmx(request, current_user)

    @app.get("/htmx/create-form-json-import", response_class=HTMLResponse)
    async def htmx_create_form_json_import(request: Request, current_user: DiscordUser = Depends(require_auth)):
        from .htmx_endpoints import get_create_form_json_import_htmx
        bot = get_bot_instance()
        return await get_create_form_json_import_htmx(request, bot, current_user)

    @app.get("/htmx/poll/{poll_id}/export-json")
    async def htmx_export_poll_json(poll_id: int, request: Request, current_user: DiscordUser = Depends(require_auth)):
        from .htmx_endpoints import export_poll_json_htmx
        return await export_poll_json_htmx(poll_id, request, current_user)

    @app.get("/htmx/poll/{poll_id}/dashboard", response_class=HTMLResponse)
    async def htmx_poll_dashboard(poll_id: int, request: Request, current_user: DiscordUser = Depends(require_auth)):
        from .htmx_endpoints import get_poll_dashboard_htmx
        bot = get_bot_instance()
        return await get_poll_dashboard_htmx(poll_id, request, bot, current_user)

    @app.get("/htmx/poll/{poll_id}/export-csv")
    async def htmx_export_poll_csv(poll_id: int, request: Request, current_user: DiscordUser = Depends(require_auth)):
        from .htmx_endpoints import export_poll_csv
        bot = get_bot_instance()
        return await export_poll_csv(poll_id, request, bot, current_user)


# Create the app instance
app = create_app()
