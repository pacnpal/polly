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
from .database import init_database, get_db_session, UserPreference
from .discord_utils import get_user_guilds_with_channels
from .error_handler import notify_error_async

logger = logging.getLogger(__name__)

# Initialize database
init_database()

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
                "default_timezone": prefs.default_timezone or "US/Eastern"
            }
        return {
            "last_server_id": None,
            "last_channel_id": None,
            "default_timezone": "US/Eastern"
        }
    except Exception as e:
        logger.error(f"Error getting user preferences for {user_id}: {e}")
        from .error_handler import notify_error
        notify_error(e, "User Preferences Retrieval", user_id=user_id)
        return {
            "last_server_id": None,
            "last_channel_id": None,
            "default_timezone": "US/Eastern"
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
            setattr(prefs, 'updated_at', datetime.now(pytz.UTC))
        else:
            # Create new preferences
            prefs = UserPreference(
                user_id=user_id,
                last_server_id=server_id,
                last_channel_id=channel_id,
                default_timezone=timezone or "US/Eastern"
            )
            db.add(prefs)

        db.commit()
        logger.debug(
            f"Saved preferences for user {user_id}: server={server_id}, channel={channel_id}")
    except Exception as e:
        logger.error(f"Error saving user preferences for {user_id}: {e}")
        from .error_handler import notify_error
        notify_error(e, "User Preferences Saving", user_id=user_id,
                     server_id=server_id, channel_id=channel_id, timezone=timezone)
        db.rollback()
    finally:
        db.close()


async def start_background_tasks():
    """Start all background tasks"""
    from .background_tasks import start_scheduler, start_reaction_safeguard
    from .discord_bot import start_bot

    # Start background tasks
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
            await notify_error_async(e, "Discord OAuth Callback", code=code)
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
            await notify_error_async(e, "Dashboard Guild Retrieval", user_id=current_user.id)
            user_guilds = []

        return templates.TemplateResponse("dashboard_htmx.html", {
            "request": request,
            "user": current_user,
            "guilds": user_guilds,
            "show_timezone_prompt": user_prefs.get("last_server_id") is None
        })

    # Add HTMX endpoints
    add_htmx_routes(app)


def add_htmx_routes(app: FastAPI):
    """Add HTMX endpoints to the application"""
    from .htmx_endpoints import (
        get_polls_htmx, get_stats_htmx, get_create_form_htmx, get_channels_htmx,
        add_option_htmx, remove_option_htmx, upload_image_htmx, remove_image_htmx,
        get_servers_htmx, get_settings_htmx, save_settings_htmx, get_polls_realtime_htmx,
        create_poll_htmx, get_poll_edit_form
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

    @app.get("/htmx/channels", response_class=HTMLResponse)
    async def htmx_channels(server_id: str, current_user: DiscordUser = Depends(require_auth)):
        bot = get_bot_instance()
        return await get_channels_htmx(server_id, bot, current_user)

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


# Create the app instance
app = create_app()
