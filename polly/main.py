"""
Polly Main Application
Discord bot + FastAPI web server with admin-only poll creation.
"""
# Load environment variables FIRST before importing other modules
from .discord_utils import (
    get_user_guilds_with_channels, create_poll_embed, post_poll_to_channel,
    update_poll_message, post_poll_results, user_has_admin_permissions
)
from .auth import (
    save_user_to_db, get_discord_oauth_url, exchange_code_for_token,
    get_discord_user, create_access_token, require_auth, DiscordUser
)
from .database import init_database, get_db_session, Poll, Vote, POLL_EMOJIS, UserPreference
import uvicorn
from apscheduler.triggers.date import DateTrigger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi import FastAPI, Request, Depends
from discord.ext import commands
import discord
import pytz
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import logging
import asyncio
import os
import uuid
import aiofiles
from dotenv import load_dotenv
load_dotenv()


# Configuration
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN environment variable is required")

# Setup comprehensive logging
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/polly.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize database
init_database()

# Create directories
os.makedirs("static/uploads", exist_ok=True)
os.makedirs("templates", exist_ok=True)

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.reactions = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Scheduler for poll timing
scheduler = AsyncIOScheduler()


# Utility functions for error handling and image management
async def cleanup_image(image_path: str) -> bool:
    """Safely delete an image file"""
    try:
        if image_path and os.path.exists(image_path):
            os.remove(image_path)
            logger.info(f"Cleaned up image: {image_path}")
            return True
    except Exception as e:
        logger.error(f"Failed to cleanup image {image_path}: {e}")
    return False


async def cleanup_poll_images(poll_id: int) -> None:
    """Clean up images associated with a poll when it's closed"""
    db = get_db_session()
    try:
        poll = db.query(Poll).filter(Poll.id == poll_id).first()
        if poll and poll.image_path:
            await cleanup_image(poll.image_path)
    except Exception as e:
        logger.error(f"Error cleaning up poll {poll_id} images: {e}")
    finally:
        db.close()


def safe_get_form_data(form_data, key: str, default: str = "") -> str:
    """Safely extract form data with proper error handling"""
    try:
        value = form_data.get(key)
        if value is None:
            return default
        return str(value).strip()
    except Exception as e:
        logger.warning(f"Error extracting form data for key '{key}': {e}")
        return default


def validate_and_normalize_timezone(timezone_str: str) -> str:
    """Validate and normalize timezone string, handling EDT/EST issues"""
    if not timezone_str:
        return "UTC"

    # Handle common timezone aliases and server timezone issues
    timezone_mapping = {
        "EDT": "US/Eastern",
        "EST": "US/Eastern",
        "CDT": "US/Central",
        "CST": "US/Central",
        "MDT": "US/Mountain",
        "MST": "US/Mountain",
        "PDT": "US/Pacific",
        "PST": "US/Pacific",
        "Eastern": "US/Eastern",
        "Central": "US/Central",
        "Mountain": "US/Mountain",
        "Pacific": "US/Pacific"
    }

    # Check if it's a mapped timezone
    if timezone_str in timezone_mapping:
        timezone_str = timezone_mapping[timezone_str]

    # Validate the timezone
    try:
        pytz.timezone(timezone_str)
        return timezone_str
    except pytz.UnknownTimeZoneError:
        logger.warning(f"Unknown timezone '{timezone_str}', defaulting to UTC")
        return "UTC"
    except Exception as e:
        logger.error(f"Error validating timezone '{timezone_str}': {e}")
        return "UTC"


def safe_parse_datetime_with_timezone(datetime_str: str, timezone_str: str) -> datetime:
    """Safely parse datetime string with timezone, handling server timezone issues"""
    try:
        # Validate and normalize timezone
        normalized_tz = validate_and_normalize_timezone(timezone_str)
        tz = pytz.timezone(normalized_tz)

        # Parse the datetime string
        dt = datetime.fromisoformat(datetime_str)

        # HTML datetime-local inputs are always naive and represent local time
        # in the user's selected timezone, so we always localize to the specified timezone
        if dt.tzinfo is None:
            localized_dt = tz.localize(dt)
        else:
            # If it already has timezone info, convert to the specified timezone
            localized_dt = dt.astimezone(tz)

        # Convert to UTC for storage
        utc_dt = localized_dt.astimezone(pytz.UTC)

        # Debug logging to help troubleshoot timezone issues
        logger.debug(
            f"Timezone parsing: '{datetime_str}' in '{timezone_str}' -> {localized_dt} -> {utc_dt}")

        return utc_dt

    except Exception as e:
        logger.error(
            f"Error parsing datetime '{datetime_str}' with timezone '{timezone_str}': {e}")
        # Fallback: parse as UTC
        try:
            dt = datetime.fromisoformat(datetime_str)
            if dt.tzinfo is None:
                return pytz.UTC.localize(dt)
            return dt.astimezone(pytz.UTC)
        except Exception as fallback_error:
            logger.error(f"Fallback datetime parsing failed: {fallback_error}")
            # Last resort: return current time
            return datetime.now(pytz.UTC)


async def validate_image_file(image_file) -> tuple[bool, str, bytes | None]:
    """Validate uploaded image file and return validation result"""
    try:
        if not image_file or not hasattr(image_file, 'filename') or not image_file.filename:
            return True, "", None

        # Read file content
        content = await image_file.read()

        # Validate file size (8MB limit)
        if len(content) > 8 * 1024 * 1024:
            return False, "Image file too large (max 8MB)", None

        # Validate file type
        allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
        if hasattr(image_file, 'content_type') and image_file.content_type not in allowed_types:
            return False, "Invalid image format (JPEG, PNG, GIF, WebP only)", None

        return True, "", content
    except Exception as e:
        logger.error(f"Error validating image file: {e}")
        return False, "Error processing image file", None


async def save_image_file(content: bytes, filename: str) -> str | None:
    """Save image file with proper error handling"""
    try:
        file_extension = filename.split('.')[-1].lower()
        unique_filename = f"{uuid.uuid4()}.{file_extension}"
        image_path = f"static/uploads/{unique_filename}"

        # Ensure uploads directory exists
        os.makedirs("static/uploads", exist_ok=True)

        # Save file
        async with aiofiles.open(image_path, "wb") as f:
            await f.write(content)

        logger.info(f"Saved image: {image_path}")
        return image_path
    except Exception as e:
        logger.error(f"Error saving image file: {e}")
        return None


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
        return {
            "last_server_id": None,
            "last_channel_id": None,
            "default_timezone": "US/Eastern"
        }
    finally:
        db.close()


def format_datetime_for_user(dt: datetime, user_timezone: str) -> str:
    """Format datetime in user's timezone for display"""
    try:
        if dt.tzinfo is None:
            # Assume UTC if no timezone info
            dt = pytz.UTC.localize(dt)

        # Convert to user's timezone
        user_tz = pytz.timezone(validate_and_normalize_timezone(user_timezone))
        local_dt = dt.astimezone(user_tz)

        return local_dt.strftime('%b %d, %I:%M %p')
    except Exception as e:
        logger.error(
            f"Error formatting datetime {dt} for timezone {user_timezone}: {e}")
        # Fallback to UTC
        return dt.strftime('%b %d, %I:%M %p UTC')


def get_common_timezones() -> list:
    """Get list of common timezones with display names"""
    common_timezones = [
        "US/Eastern", "US/Central", "US/Mountain", "US/Pacific", "UTC",
        "Europe/London", "Europe/Paris", "Europe/Berlin", "Asia/Tokyo",
        "Asia/Shanghai", "Australia/Sydney", "America/New_York",
        "America/Chicago", "America/Denver", "America/Los_Angeles"
    ]

    timezones = []
    for tz_name in common_timezones:
        try:
            tz_obj = pytz.timezone(tz_name)
            offset = datetime.now(tz_obj).strftime('%z')
            # Format offset nicely
            if offset:
                offset_formatted = f"UTC{offset[:3]}:{offset[3:]}"
            else:
                offset_formatted = "UTC"
            timezones.append({
                "name": tz_name,
                "display": f"{tz_name} ({offset_formatted})"
            })
        except (pytz.UnknownTimeZoneError, ValueError, AttributeError) as e:
            logger.warning(f"Error formatting timezone {tz_name}: {e}")
            timezones.append({
                "name": tz_name,
                "display": tz_name
            })

    return timezones


def save_user_preferences(user_id: str, server_id: str = None, channel_id: str = None, timezone: str = None):
    """Save user preferences for poll creation"""
    db = get_db_session()
    try:
        prefs = db.query(UserPreference).filter(
            UserPreference.user_id == user_id).first()

        if prefs:
            # Update existing preferences
            if server_id:
                prefs.last_server_id = server_id
            if channel_id:
                prefs.last_channel_id = channel_id
            if timezone:
                prefs.default_timezone = timezone
            prefs.updated_at = datetime.now(pytz.UTC)
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
        db.rollback()
    finally:
        db.close()


@bot.event
async def on_ready():
    """Bot ready event"""
    logger.info(f'{bot.user} has connected to Discord!')

    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} command(s)")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")


@bot.tree.command(name="quickpoll", description="Create a quick poll in the current channel")
async def create_quick_poll_command(
    interaction: discord.Interaction,
    question: str,
    option1: str,
    option2: str,
    option3: str = None,
    option4: str = None,
    option5: str = None,
    anonymous: bool = False
):
    """Create a quick poll via Discord slash command"""
    # Check if user has admin permissions
    if not user_has_admin_permissions(interaction.user):
        await interaction.response.send_message(
            "❌ You need Administrator or Manage Server permissions to create polls.",
            ephemeral=True
        )
        return

    # Collect options
    options = [option1, option2]
    emojis = ["🇦", "🇧", "🇨", "🇩", "🇪"][:len(options)]
    for opt in [option3, option4, option5]:
        if opt:
            options.append(opt)

    if len(options) > 10:
        await interaction.response.send_message(
            "❌ Maximum 10 poll options allowed.",
            ephemeral=True
        )
        return

    # Create poll in database
    db = get_db_session()
    try:
        poll = Poll(
            name=f"Quick Poll - {question[:50]}",
            question=question,
            options=options,
            emojis=emojis,
            server_id=str(interaction.guild_id),
            server_name=interaction.guild.name if interaction.guild else "Unknown",
            channel_id=str(interaction.channel_id),
            channel_name=getattr(interaction.channel, 'name', 'Unknown'),
            creator_id=str(interaction.user.id),
            open_time=datetime.now(pytz.UTC),
            close_time=datetime.now(pytz.UTC) + timedelta(hours=24),
            anonymous=anonymous,
            status="active"
        )
        db.add(poll)
        db.commit()
        db.refresh(poll)

        # Create embed
        embed = await create_poll_embed(poll, show_results=bool(poll.should_show_results()))

        await interaction.response.send_message(embed=embed)

        # Get the message and add reactions
        message = await interaction.original_response()
        poll.message_id = str(message.id)
        db.commit()

        # Add reaction emojis
        for i in range(len(options)):
            await message.add_reaction(POLL_EMOJIS[i])

        # Schedule poll closure
        scheduler.add_job(
            close_poll,
            DateTrigger(run_date=poll.close_time),
            args=[poll.id],
            id=f"close_poll_{poll.id}"
        )

    except Exception as e:
        logger.error(f"Error creating poll: {e}")
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Error creating poll. Please try again.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Error creating poll. Please try again.", ephemeral=True)
    finally:
        db.close()


@bot.event
async def on_reaction_add(reaction, user):
    """Handle poll voting via reactions"""
    if user.bot:
        return

    # Check if this is a poll message
    db = get_db_session()
    try:
        poll = db.query(Poll).filter(Poll.message_id ==
                                     str(reaction.message.id)).first()
        if not poll or poll.status != "active":
            return

        # Check if emoji is valid poll option
        if str(reaction.emoji) not in POLL_EMOJIS:
            return

        option_index = POLL_EMOJIS.index(str(reaction.emoji))
        if option_index >= len(poll.options):
            return

        # Check if user already voted
        existing_vote = db.query(Vote).filter(
            Vote.poll_id == poll.id,
            Vote.user_id == str(user.id)
        ).first()

        if existing_vote:
            # Update existing vote
            existing_vote.option_index = option_index
            existing_vote.voted_at = datetime.now(pytz.UTC)
        else:
            # Create new vote
            vote = Vote(
                poll_id=poll.id,
                user_id=str(user.id),
                option_index=option_index
            )
            db.add(vote)

        db.commit()

        # Always update poll embed for live updates (key requirement)
        await update_poll_message(bot, poll)

    except Exception as e:
        logger.error(f"Error handling vote: {e}")
    finally:
        db.close()


async def close_poll(poll_id: int):
    """Close a poll and update the message"""
    db = get_db_session()
    try:
        poll = db.query(Poll).filter(Poll.id == poll_id).first()
        if poll:
            poll.status = "closed"
            db.commit()

            # Post final results to the same channel (key requirement)
            await post_poll_results(bot, poll)

            # Update original message
            await update_poll_message(bot, poll)

            # Clean up poll images after closing
            await cleanup_poll_images(poll_id)

            logger.info(f"Closed poll {poll_id}")
    except Exception as e:
        logger.error(f"Error closing poll {poll_id}: {e}")
    finally:
        db.close()


async def start_bot():
    """Start the Discord bot"""
    if DISCORD_TOKEN:
        await bot.start(DISCORD_TOKEN)


async def start_scheduler():
    """Start the job scheduler"""
    scheduler.start()
    logger.info("Scheduler started")


# Lifespan manager for background tasks
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    asyncio.create_task(start_scheduler())
    asyncio.create_task(start_bot())
    yield
    # Shutdown
    scheduler.shutdown()
    await bot.close()


# FastAPI setup with lifespan
app = FastAPI(
    title="Polly - Discord Poll Bot",
    version="0.2.0",
    lifespan=lifespan
)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# Web routes
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
    # Check if user has timezone preference set
    user_prefs = get_user_preferences(current_user.id)

    # Get user's guilds with channels
    user_guilds = await get_user_guilds_with_channels(bot, current_user.id)

    return templates.TemplateResponse("dashboard_htmx.html", {
        "request": request,
        "user": current_user,
        "guilds": user_guilds,
        "show_timezone_prompt": user_prefs.get("last_server_id") is None
    })


# HTMX endpoints for dynamic content without JavaScript
@app.get("/htmx/polls", response_class=HTMLResponse)
async def get_polls_htmx(request: Request, filter: str = None, current_user: DiscordUser = Depends(require_auth)):
    """Get user's polls as HTML for HTMX with optional filtering"""
    db = get_db_session()
    try:
        query = db.query(Poll).filter(Poll.creator_id == current_user.id)

        # Apply filter if specified
        if filter and filter in ['active', 'scheduled', 'closed']:
            query = query.filter(Poll.status == filter)

        polls = query.order_by(Poll.created_at.desc()).all()

        # Add status_class to each poll for template
        for poll in polls:
            poll.status_class = {
                'active': 'bg-success',
                'scheduled': 'bg-warning',
                'closed': 'bg-danger'
            }.get(poll.status, 'bg-secondary')

        # Get user's timezone preference
        user_prefs = get_user_preferences(current_user.id)
        user_timezone = user_prefs.get("default_timezone", "US/Eastern")

        return templates.TemplateResponse("htmx/polls.html", {
            "request": request,
            "polls": polls,
            "current_filter": filter,
            "user_timezone": user_timezone,
            "format_datetime_for_user": format_datetime_for_user
        })
    finally:
        db.close()


@app.get("/htmx/stats", response_class=HTMLResponse)
async def get_stats_htmx(request: Request, current_user: DiscordUser = Depends(require_auth)):
    """Get dashboard stats as HTML for HTMX"""
    db = get_db_session()
    try:
        polls = db.query(Poll).filter(Poll.creator_id == current_user.id).all()
        total_polls = len(polls)
        active_polls = len([p for p in polls if p.status == 'active'])
        total_votes = sum(p.get_total_votes() for p in polls)

        return templates.TemplateResponse("htmx/stats.html", {
            "request": request,
            "total_polls": total_polls,
            "active_polls": active_polls,
            "total_votes": total_votes
        })
    finally:
        db.close()


@app.get("/htmx/create-form", response_class=HTMLResponse)
async def get_create_form_htmx(request: Request, current_user: DiscordUser = Depends(require_auth)):
    """Get create poll form as HTML for HTMX"""
    # Get user's guilds with channels
    user_guilds = await get_user_guilds_with_channels(bot, current_user.id)

    # Get user preferences
    user_prefs = get_user_preferences(current_user.id)

    # Get timezones - user's default first
    common_timezones = [
        user_prefs["default_timezone"], "US/Eastern", "UTC", "US/Central", "US/Mountain", "US/Pacific",
        "Europe/London", "Europe/Paris", "Europe/Berlin", "Asia/Tokyo", "Asia/Shanghai", "Australia/Sydney"
    ]
    # Remove duplicates while preserving order
    seen = set()
    common_timezones = [tz for tz in common_timezones if not (
        tz in seen or seen.add(tz))]

    # Set default times in user's timezone
    user_tz = pytz.timezone(user_prefs["default_timezone"])
    now = datetime.now(user_tz)
    open_time = (now + timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M')
    close_time = (now + timedelta(hours=24)).strftime('%Y-%m-%dT%H:%M')

    # Prepare timezone data for template
    timezones = []
    for tz in common_timezones:
        try:
            tz_obj = pytz.timezone(tz)
            offset = datetime.now(tz_obj).strftime('%z')
            timezones.append({
                "name": tz,
                "display": f"{tz} (UTC{offset})"
            })
        except (pytz.UnknownTimeZoneError, ValueError, AttributeError) as e:
            logger.warning(f"Error formatting timezone {tz}: {e}")
            timezones.append({
                "name": tz,
                "display": tz
            })

    return templates.TemplateResponse("htmx/create_form_filepond.html", {
        "request": request,
        "guilds": user_guilds,
        "timezones": timezones,
        "open_time": open_time,
        "close_time": close_time,
        "user_preferences": user_prefs
    })


@app.get("/htmx/channels", response_class=HTMLResponse)
async def get_channels_htmx(server_id: str, current_user: DiscordUser = Depends(require_auth)):
    """Get channels for a server as HTML options for HTMX"""
    if not server_id:
        return '<option value="">Select a server first...</option>'

    user_guilds = await get_user_guilds_with_channels(bot, current_user.id)
    guild = next((g for g in user_guilds if g["id"] == server_id), None)

    if not guild:
        return '<option value="">Server not found...</option>'

    options = '<option value="">Select a channel...</option>'
    for channel in guild["channels"]:
        options += f'<option value="{channel["id"]}">#{channel["name"]}</option>'

    return options


@app.post("/htmx/add-option", response_class=HTMLResponse)
async def add_option_htmx():
    """Add a new poll option input for HTMX"""
    import random
    option_num = random.randint(3, 10)  # Simple way to get next option number
    emojis = ['🇦', '🇧', '🇨', '🇩', '🇪', '🇫', '🇬', '🇭', '🇮', '🇯']
    emoji = emojis[min(option_num - 1, len(emojis) - 1)]

    return f"""
    <div class="input-group mb-2">
        <span class="input-group-text">{emoji}</span>
        <input type="text" class="form-control" name="option{option_num}" placeholder="Option {option_num}">
        <button type="button" class="btn btn-outline-danger"
                hx-delete="/htmx/remove-option" hx-target="closest .input-group" hx-swap="outerHTML">
            <i class="fas fa-times"></i>
        </button>
    </div>
    """


@app.delete("/htmx/remove-option", response_class=HTMLResponse)
async def remove_option_htmx():
    """Remove a poll option for HTMX"""
    return ""  # Empty response removes the element


@app.post("/htmx/upload-image")
async def upload_image_htmx(request: Request, current_user: DiscordUser = Depends(require_auth)):
    """Handle FilePond image upload via HTMX"""
    try:
        form_data = await request.form()
        image_file = form_data.get("filepond")

        if not image_file or not hasattr(image_file, 'filename') or not image_file.filename:
            return {"error": "No image file provided"}, 400

        # Validate image file
        is_valid, error_msg, content = await validate_image_file(image_file)

        if not is_valid:
            return {"error": error_msg}, 400

        if content and image_file.filename:
            image_path = await save_image_file(content, str(image_file.filename))
            if image_path:
                # Return the file path for FilePond to track
                return {"success": True, "path": image_path}
            else:
                return {"error": "Failed to save image file"}, 500

        return {"error": "No valid image content"}, 400

    except Exception as e:
        logger.error(f"Error in FilePond image upload: {e}")
        return {"error": "Server error processing image"}, 500


@app.delete("/htmx/remove-image")
async def remove_image_htmx(request: Request, current_user: DiscordUser = Depends(require_auth)):
    """Handle FilePond image removal via HTMX"""
    try:
        form_data = await request.form()
        image_path = form_data.get("path")

        if image_path and await cleanup_image(image_path):
            return {"success": True}
        else:
            return {"error": "Failed to remove image"}, 400

    except Exception as e:
        logger.error(f"Error removing image: {e}")
        return {"error": "Server error removing image"}, 500


@app.get("/htmx/servers", response_class=HTMLResponse)
async def get_servers_htmx(request: Request, current_user: DiscordUser = Depends(require_auth)):
    """Get user's servers as HTML for HTMX"""
    user_guilds = await get_user_guilds_with_channels(bot, current_user.id)

    return templates.TemplateResponse("htmx/servers.html", {
        "request": request,
        "guilds": user_guilds
    })


@app.get("/htmx/settings", response_class=HTMLResponse)
async def get_settings_htmx(request: Request, current_user: DiscordUser = Depends(require_auth)):
    """Get user settings form as HTML for HTMX"""
    # Get user preferences
    user_prefs = get_user_preferences(current_user.id)

    # Get common timezones
    timezones = get_common_timezones()

    return templates.TemplateResponse("htmx/settings.html", {
        "request": request,
        "user_prefs": user_prefs,
        "timezones": timezones
    })


@app.post("/htmx/settings", response_class=HTMLResponse)
async def save_settings_htmx(request: Request, current_user: DiscordUser = Depends(require_auth)):
    """Save user settings via HTMX"""
    try:
        form_data = await request.form()
        timezone = safe_get_form_data(form_data, "timezone", "US/Eastern")

        # Validate and normalize timezone
        normalized_timezone = validate_and_normalize_timezone(timezone)

        # Save user preferences
        save_user_preferences(current_user.id, timezone=normalized_timezone)

        logger.info(
            f"Updated timezone preference for user {current_user.id} to {normalized_timezone}")

        return """
        <div class="alert alert-success">
            <i class="fas fa-check-circle me-2"></i>Settings saved successfully! Your timezone preference has been updated.
        </div>
        <div hx-get="/htmx/settings" hx-target="#main-content" hx-trigger="load delay:2s"></div>
        """

    except Exception as e:
        logger.error(f"Error saving settings for user {current_user.id}: {e}")
        return f"""
        <div class="alert alert-danger">
            <i class="fas fa-exclamation-triangle me-2"></i>Error saving settings: {str(e)}
        </div>
        """


@app.post("/htmx/create-poll", response_class=HTMLResponse)
async def create_poll_htmx(request: Request, current_user: DiscordUser = Depends(require_auth)):
    """Create a new poll via HTMX"""
    logger.info(f"User {current_user.id} creating new poll")
    image_path = None
    try:
        form_data = await request.form()

        # Extract form data with proper error handling
        name = safe_get_form_data(form_data, "name")
        question = safe_get_form_data(form_data, "question")
        server_id = safe_get_form_data(form_data, "server_id")
        channel_id = safe_get_form_data(form_data, "channel_id")
        open_time = safe_get_form_data(form_data, "open_time")
        close_time = safe_get_form_data(form_data, "close_time")
        timezone_str = safe_get_form_data(form_data, "timezone", "UTC")
        anonymous = form_data.get("anonymous") == "true"

        logger.debug(
            f"Poll creation data: name={name}, question={question}, server_id={server_id}")

        # Validate required fields
        if not all([name, question, server_id, channel_id, open_time, close_time]):
            logger.warning(
                f"Missing required fields for poll creation by user {current_user.id}")
            return """
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>All required fields must be filled
            </div>
            """

        # Handle image upload with improved error handling
        image_file = form_data.get("image")
        is_valid, error_msg, content = await validate_image_file(image_file)

        if not is_valid:
            logger.warning(f"Image validation failed: {error_msg}")
            return f"""
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>{error_msg}
            </div>
            """

        if content and hasattr(image_file, 'filename') and image_file.filename:
            image_path = await save_image_file(content, str(image_file.filename))
            if not image_path:
                logger.error("Failed to save image file")
                return """
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-triangle me-2"></i>Failed to save image file
                </div>
                """

        # Get options
        options = []
        emojis = []
        for i in range(1, 11):
            option = form_data.get(f"option{i}")
            if option:
                options.append(str(option).strip())
                default_emojis = ["🇦", "🇧", "🇨", "🇩",
                                  "🇪", "🇫", "🇬", "🇭", "🇮", "🇯"]
                emojis.append(default_emojis[len(emojis)] if len(
                    emojis) < 10 else "⭐")

        if len(options) < 2:
            logger.warning(f"Insufficient options provided: {len(options)}")
            return """
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>At least 2 options required
            </div>
            """

        # Parse times with timezone using safe parsing
        open_dt = safe_parse_datetime_with_timezone(open_time, timezone_str)
        close_dt = safe_parse_datetime_with_timezone(close_time, timezone_str)

        # Normalize timezone for storage
        timezone_str = validate_and_normalize_timezone(timezone_str)

        # Validate times
        now = datetime.now(pytz.UTC)

        # Debug: Show system time vs Python time
        import time
        system_timestamp = time.time()
        system_utc = datetime.fromtimestamp(system_timestamp, tz=pytz.UTC)
        logger.debug("System time comparison:")
        logger.debug(f"  Python datetime.now(UTC): {now}")
        logger.debug(f"  System time.time() UTC: {system_utc}")
        logger.debug(
            f"  Difference: {(now - system_utc).total_seconds()} seconds")

        # Don't allow scheduling polls in the past - require next minute boundary
        # Since polls are scheduled at 00:00:00, we need the next full minute
        next_minute = now.replace(
            second=0, microsecond=0) + timedelta(minutes=1)

        if open_dt < next_minute:
            # Convert times to user's timezone for display and debugging
            user_tz = pytz.timezone(timezone_str)
            now_local = now.astimezone(user_tz)
            next_minute_local = next_minute.astimezone(user_tz)
            requested_time_local = open_dt.astimezone(user_tz)
            suggested_time = next_minute_local.strftime('%I:%M %p')

            logger.warning(
                f"Attempt to schedule poll in the past: {open_dt} < {next_minute}")
            logger.debug("Time validation details:")
            logger.debug(f"  Current time UTC: {now}")
            logger.debug(f"  Current time local ({user_tz}): {now_local}")
            logger.debug(f"  Requested time UTC: {open_dt}")
            logger.debug(
                f"  Requested time local ({user_tz}): {requested_time_local}")
            logger.debug(f"  Next minute boundary UTC: {next_minute}")
            logger.debug(
                f"  Next minute boundary local ({user_tz}): {next_minute_local}")
            logger.debug(f"  Suggested time: {suggested_time}")

            return f"""
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>Poll open time must be scheduled for the next minute or later. Try {suggested_time} or later.
            </div>
            """

        if close_dt <= open_dt:
            logger.warning(
                f"Invalid time range: open={open_dt}, close={close_dt}")
            return """
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>Close time must be after open time
            </div>
            """

        # Get server and channel names
        guild = bot.get_guild(int(server_id))
        channel = bot.get_channel(int(channel_id))

        if not guild or not channel:
            logger.error(
                f"Invalid guild or channel: guild={guild}, channel={channel}")
            return """
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>Invalid server or channel
            </div>
            """

        # Check user permissions
        try:
            member = await guild.fetch_member(int(current_user.id))
        except discord.NotFound:
            logger.warning(
                f"User {current_user.id} not found in guild {guild.id}")
            return """
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>User not found in server
            </div>
            """

        if not member or not user_has_admin_permissions(member):
            logger.warning(
                f"User {current_user.id} lacks permissions in guild {guild.id}")
            return """
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>No permission to create polls in this server
            </div>
            """

        # Create poll in database
        db = get_db_session()
        try:
            poll = Poll(
                name=name,
                question=question,
                options=options,
                emojis=emojis,
                image_path=image_path,
                server_id=server_id,
                server_name=guild.name,
                channel_id=channel_id,
                channel_name=getattr(channel, 'name', 'Unknown'),
                creator_id=current_user.id,
                open_time=open_dt,
                close_time=close_dt,
                timezone=timezone_str,
                anonymous=anonymous,
                status="scheduled"
            )
            db.add(poll)
            db.commit()
            db.refresh(poll)

            logger.info(f"Created poll {poll.id} for user {current_user.id}")

            # Schedule poll to open
            if open_dt <= datetime.now(pytz.UTC):
                # Open immediately
                try:
                    await post_poll_to_channel(bot, poll)
                    logger.info(
                        f"Posted poll {poll.id} to Discord immediately")
                except Exception as discord_error:
                    logger.warning(
                        f"Failed to post poll {poll.id} to Discord immediately: {discord_error}")
            else:
                # Schedule opening
                scheduler.add_job(
                    post_poll_to_channel,
                    DateTrigger(run_date=open_dt),
                    args=[bot, poll],
                    id=f"open_poll_{poll.id}"
                )
                logger.info(f"Scheduled poll {poll.id} to open at {open_dt}")

            # Schedule poll to close
            scheduler.add_job(
                close_poll,
                DateTrigger(run_date=close_dt),
                args=[poll.id],
                id=f"close_poll_{poll.id}"
            )
            logger.info(f"Scheduled poll {poll.id} to close at {close_dt}")

            # Save user preferences for next time
            save_user_preferences(
                current_user.id, server_id, channel_id, timezone_str)

            # Return success message and redirect to polls view
            return """
            <div class="alert alert-success">
                <i class="fas fa-check-circle me-2"></i>Poll created successfully! Redirecting to polls...
            </div>
            <div hx-get="/htmx/polls" hx-target="#main-content" hx-trigger="load delay:2s"></div>
            """

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error creating poll for user {current_user.id}: {e}")
        return f"""
        <div class="alert alert-danger">
            <i class="fas fa-exclamation-triangle me-2"></i>Error creating poll: {str(e)}
        </div>
        """


# Poll management endpoints
@app.get("/htmx/poll/{poll_id}/edit", response_class=HTMLResponse)
async def get_poll_edit_form(poll_id: int, request: Request, current_user: DiscordUser = Depends(require_auth)):
    """Get edit form for a scheduled poll"""
    logger.info(
        f"User {current_user.id} requesting edit form for poll {poll_id}")
    db = get_db_session()
    try:
        poll = db.query(Poll).filter(Poll.id == poll_id,
                                     Poll.creator_id == current_user.id).first()
        if not poll:
            logger.warning(
                f"Poll {poll_id} not found or not owned by user {current_user.id}")
            return """
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>Poll not found or access denied
            </div>
            """

        if poll.status != "scheduled":
            logger.warning(
                f"Attempt to edit non-scheduled poll {poll_id} (status: {poll.status})")
            return """
            <div class="alert alert-warning">
                <i class="fas fa-info-circle me-2"></i>Only scheduled polls can be edited
            </div>
            """

        # Get user's guilds with channels
        user_guilds = await get_user_guilds_with_channels(bot, current_user.id)

        # Get timezones - US/Eastern first as default
        common_timezones = [
            "US/Eastern", "UTC", "US/Central", "US/Mountain", "US/Pacific",
            "Europe/London", "Europe/Paris", "Europe/Berlin", "Asia/Tokyo", "Asia/Shanghai", "Australia/Sydney"
        ]

        # Convert times to local timezone for editing
        poll_timezone = poll.timezone or "UTC"
        tz = pytz.timezone(poll_timezone)

        # Ensure the stored times have timezone info (they should be UTC)
        if poll.open_time.tzinfo is None:
            open_time_utc = pytz.UTC.localize(poll.open_time)
        else:
            open_time_utc = poll.open_time.astimezone(pytz.UTC)

        if poll.close_time.tzinfo is None:
            close_time_utc = pytz.UTC.localize(poll.close_time)
        else:
            close_time_utc = poll.close_time.astimezone(pytz.UTC)

        # Convert from UTC to the poll's timezone
        open_time_local = open_time_utc.astimezone(tz)
        close_time_local = close_time_utc.astimezone(tz)

        # Debug logging for edit form time conversion
        logger.debug(f"Edit form for poll {poll_id}:")
        logger.debug(f"  Stored timezone: {poll.timezone}")
        logger.debug(f"  Open time UTC: {poll.open_time}")
        logger.debug(f"  Close time UTC: {poll.close_time}")
        logger.debug(f"  Open time local ({tz}): {open_time_local}")
        logger.debug(f"  Close time local ({tz}): {close_time_local}")

        open_time = open_time_local.strftime('%Y-%m-%dT%H:%M')
        close_time = close_time_local.strftime('%Y-%m-%dT%H:%M')

        logger.debug(f"  Form open time: {open_time}")
        logger.debug(f"  Form close time: {close_time}")

        # Prepare timezone data for template
        timezones = []
        for tz_name in common_timezones:
            try:
                tz_obj = pytz.timezone(tz_name)
                offset = datetime.now(tz_obj).strftime('%z')
                timezones.append({
                    "name": tz_name,
                    "display": f"{tz_name} (UTC{offset})"
                })
            except (pytz.UnknownTimeZoneError, ValueError, AttributeError) as e:
                logger.warning(f"Error formatting timezone {tz_name}: {e}")
                timezones.append({
                    "name": tz_name,
                    "display": tz_name
                })

        return templates.TemplateResponse("htmx/edit_form_filepond.html", {
            "request": request,
            "poll": poll,
            "guilds": user_guilds,
            "timezones": timezones,
            "open_time": open_time,
            "close_time": close_time
        })
    finally:
        db.close()


@app.post("/htmx/poll/{poll_id}/edit", response_class=HTMLResponse)
async def update_poll(poll_id: int, request: Request, current_user: DiscordUser = Depends(require_auth)):
    """Update a scheduled poll"""
    logger.info(f"User {current_user.id} updating poll {poll_id}")
    db = get_db_session()
    try:
        poll = db.query(Poll).filter(Poll.id == poll_id,
                                     Poll.creator_id == current_user.id).first()
        if not poll:
            logger.warning(
                f"Poll {poll_id} not found or not owned by user {current_user.id}")
            return """
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>Poll not found or access denied
            </div>
            """

        if poll.status != "scheduled":
            logger.warning(
                f"Attempt to edit non-scheduled poll {poll_id} (status: {poll.status})")
            return """
            <div class="alert alert-warning">
                <i class="fas fa-info-circle me-2"></i>Only scheduled polls can be edited
            </div>
            """

        form_data = await request.form()

        # Extract form data
        name = safe_get_form_data(form_data, "name")
        question = safe_get_form_data(form_data, "question")
        server_id = safe_get_form_data(form_data, "server_id")
        channel_id = safe_get_form_data(form_data, "channel_id")
        open_time = safe_get_form_data(form_data, "open_time")
        close_time = safe_get_form_data(form_data, "close_time")
        timezone_str = safe_get_form_data(form_data, "timezone", "UTC")
        anonymous = form_data.get("anonymous") == "true"

        # Validate required fields
        if not all([name, question, server_id, channel_id, open_time, close_time]):
            logger.warning(
                f"Missing required fields for poll {poll_id} update")
            return """
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>All required fields must be filled
            </div>
            """

        # Handle image upload
        image_file = form_data.get("image")
        is_valid, error_msg, content = await validate_image_file(image_file)

        if not is_valid:
            logger.warning(
                f"Image validation failed for poll {poll_id}: {error_msg}")
            return f"""
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>{error_msg}
            </div>
            """

        # Save new image if provided
        new_image_path = poll.image_path
        if content and hasattr(image_file, 'filename') and image_file.filename:
            new_image_path = await save_image_file(content, str(image_file.filename))
            if not new_image_path:
                logger.error(f"Failed to save new image for poll {poll_id}")
                return """
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-triangle me-2"></i>Failed to save image file
                </div>
                """
            # Clean up old image
            if poll.image_path:
                await cleanup_image(poll.image_path)

        # Get options
        options = []
        emojis = []
        for i in range(1, 11):
            option = form_data.get(f"option{i}")
            if option:
                options.append(str(option).strip())
                default_emojis = ["🇦", "🇧", "🇨", "🇩",
                                  "🇪", "🇫", "🇬", "🇭", "🇮", "🇯"]
                emojis.append(default_emojis[len(emojis)] if len(
                    emojis) < 10 else "⭐")

        if len(options) < 2:
            logger.warning(
                f"Insufficient options for poll {poll_id}: {len(options)}")
            return """
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>At least 2 options required
            </div>
            """

        # Parse times with timezone using safe parsing
        open_dt = safe_parse_datetime_with_timezone(open_time, timezone_str)
        close_dt = safe_parse_datetime_with_timezone(close_time, timezone_str)

        # Normalize timezone for storage
        timezone_str = validate_and_normalize_timezone(timezone_str)

        # Validate times
        now = datetime.now(pytz.UTC)

        # Debug: Show system time vs Python time
        import time
        system_timestamp = time.time()
        system_utc = datetime.fromtimestamp(system_timestamp, tz=pytz.UTC)
        logger.debug("System time comparison (edit):")
        logger.debug(f"  Python datetime.now(UTC): {now}")
        logger.debug(f"  System time.time() UTC: {system_utc}")
        logger.debug(
            f"  Difference: {(now - system_utc).total_seconds()} seconds")

        # Don't allow scheduling polls in the past - require next minute boundary
        # Since polls are scheduled at 00:00:00, we need the next full minute
        next_minute = now.replace(
            second=0, microsecond=0) + timedelta(minutes=1)

        if open_dt < next_minute:
            # Convert next_minute to user's timezone for display
            user_tz = pytz.timezone(timezone_str)
            next_minute_local = next_minute.astimezone(user_tz)
            suggested_time = next_minute_local.strftime('%I:%M %p')

            logger.warning(
                f"Attempt to schedule poll in the past: {open_dt} < {next_minute}")
            return f"""
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>Poll open time must be scheduled for the next minute or later. Try {suggested_time} or later.
            </div>
            """

        if close_dt <= open_dt:
            logger.warning(
                f"Invalid time range for poll {poll_id}: open={open_dt}, close={close_dt}")
            return """
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>Close time must be after open time
            </div>
            """

        # Get server and channel names
        guild = bot.get_guild(int(server_id))
        channel = bot.get_channel(int(channel_id))

        if not guild or not channel:
            logger.error(
                f"Invalid guild or channel for poll {poll_id}: guild={guild}, channel={channel}")
            return """
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>Invalid server or channel
            </div>
            """

        # Update poll
        poll.name = name
        poll.question = question
        poll.options = options
        poll.emojis = emojis
        poll.image_path = new_image_path
        poll.server_id = server_id
        poll.server_name = guild.name
        poll.channel_id = channel_id
        poll.channel_name = getattr(channel, 'name', 'Unknown')
        poll.open_time = open_dt
        poll.close_time = close_dt
        poll.timezone = timezone_str
        poll.anonymous = anonymous

        db.commit()

        # Update scheduled jobs
        try:
            scheduler.remove_job(f"open_poll_{poll.id}")
        except Exception as e:
            logger.debug(
                f"Job open_poll_{poll.id} not found or already removed: {e}")
        try:
            scheduler.remove_job(f"close_poll_{poll.id}")
        except Exception as e:
            logger.debug(
                f"Job close_poll_{poll.id} not found or already removed: {e}")

        # Reschedule jobs
        if open_dt > datetime.now(pytz.UTC):
            scheduler.add_job(
                post_poll_to_channel,
                DateTrigger(run_date=open_dt),
                args=[bot, poll],
                id=f"open_poll_{poll.id}"
            )

        scheduler.add_job(
            close_poll,
            DateTrigger(run_date=close_dt),
            args=[poll.id],
            id=f"close_poll_{poll.id}"
        )

        logger.info(f"Successfully updated poll {poll_id}")

        return """
        <div class="alert alert-success">
            <i class="fas fa-check-circle me-2"></i>Poll updated successfully! Redirecting to polls...
        </div>
        <div hx-get="/htmx/polls" hx-target="#main-content" hx-trigger="load delay:2s"></div>
        """

    except Exception as e:
        logger.error(f"Error updating poll {poll_id}: {e}")
        return f"""
        <div class="alert alert-danger">
            <i class="fas fa-exclamation-triangle me-2"></i>Error updating poll: {str(e)}
        </div>
        """
    finally:
        db.close()


@app.get("/htmx/poll/{poll_id}/details", response_class=HTMLResponse)
async def get_poll_details(poll_id: int, request: Request, current_user: DiscordUser = Depends(require_auth)):
    """Get detailed view of a poll"""
    logger.info(f"User {current_user.id} viewing details for poll {poll_id}")
    db = get_db_session()
    try:
        poll = db.query(Poll).filter(Poll.id == poll_id,
                                     Poll.creator_id == current_user.id).first()
        if not poll:
            logger.warning(
                f"Poll {poll_id} not found or not owned by user {current_user.id}")
            return """
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>Poll not found or access denied
            </div>
            """

        return templates.TemplateResponse("htmx/poll_details.html", {
            "request": request,
            "poll": poll
        })
    finally:
        db.close()


@app.post("/htmx/poll/{poll_id}/close", response_class=HTMLResponse)
async def close_poll_manually(poll_id: int, current_user: DiscordUser = Depends(require_auth)):
    """Manually close an active poll"""
    logger.info(f"User {current_user.id} manually closing poll {poll_id}")
    db = get_db_session()
    try:
        poll = db.query(Poll).filter(Poll.id == poll_id,
                                     Poll.creator_id == current_user.id).first()
        if not poll:
            logger.warning(
                f"Poll {poll_id} not found or not owned by user {current_user.id}")
            return """
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>Poll not found or access denied
            </div>
            """

        if poll.status != "active":
            logger.warning(
                f"Attempt to close non-active poll {poll_id} (status: {poll.status})")
            return """
            <div class="alert alert-warning">
                <i class="fas fa-info-circle me-2"></i>Only active polls can be closed
            </div>
            """

        # Close the poll
        await close_poll(poll_id)
        logger.info(f"Successfully closed poll {poll_id}")

        return """
        <div class="alert alert-success">
            <i class="fas fa-check-circle me-2"></i>Poll closed successfully! Redirecting to polls...
        </div>
        <div hx-get="/htmx/polls" hx-target="#main-content" hx-trigger="load delay:2s"></div>
        """

    except Exception as e:
        logger.error(f"Error closing poll {poll_id}: {e}")
        return f"""
        <div class="alert alert-danger">
            <i class="fas fa-exclamation-triangle me-2"></i>Error closing poll: {str(e)}
        </div>
        """
    finally:
        db.close()


@app.delete("/htmx/poll/{poll_id}", response_class=HTMLResponse)
async def delete_poll(poll_id: int, current_user: DiscordUser = Depends(require_auth)):
    """Delete a poll (scheduled or closed only)"""
    logger.info(f"User {current_user.id} deleting poll {poll_id}")
    db = get_db_session()
    try:
        poll = db.query(Poll).filter(Poll.id == poll_id,
                                     Poll.creator_id == current_user.id).first()
        if not poll:
            logger.warning(
                f"Poll {poll_id} not found or not owned by user {current_user.id}")
            return """
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>Poll not found or access denied
            </div>
            """

        if poll.status == "active":
            logger.warning(f"Attempt to delete active poll {poll_id}")
            return """
            <div class="alert alert-warning">
                <i class="fas fa-info-circle me-2"></i>Active polls cannot be deleted. Close the poll first.
            </div>
            """

        # Clean up image
        if poll.image_path:
            await cleanup_image(poll.image_path)

        # Remove scheduled jobs
        try:
            scheduler.remove_job(f"open_poll_{poll.id}")
        except Exception as e:
            logger.debug(
                f"Job open_poll_{poll.id} not found or already removed: {e}")
        try:
            scheduler.remove_job(f"close_poll_{poll.id}")
        except Exception as e:
            logger.debug(
                f"Job close_poll_{poll.id} not found or already removed: {e}")

        # Delete poll and associated votes
        db.query(Vote).filter(Vote.poll_id == poll_id).delete()
        db.delete(poll)
        db.commit()

        logger.info(f"Successfully deleted poll {poll_id}")

        return """
        <div class="alert alert-success">
            <i class="fas fa-check-circle me-2"></i>Poll deleted successfully! Redirecting to polls...
        </div>
        <div hx-get="/htmx/polls" hx-target="#main-content" hx-trigger="load delay:2s"></div>
        """

    except Exception as e:
        logger.error(f"Error deleting poll {poll_id}: {e}")
        return f"""
        <div class="alert alert-danger">
            <i class="fas fa-exclamation-triangle me-2"></i>Error deleting poll: {str(e)}
        </div>
        """
    finally:
        db.close()


def run_app():
    """Run the application"""
    # Run FastAPI server - background tasks will be started via lifespan
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run_app()
