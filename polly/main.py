"""
Polly Main Application
Discord bot + FastAPI web server with admin-only poll creation.
"""
# Load environment variables FIRST before importing other modules
from .discord_utils import (
    get_user_guilds_with_channels, create_poll_embed, post_poll_to_channel,
    update_poll_message, user_has_admin_permissions
)
from .auth import (
    save_user_to_db, get_discord_oauth_url, exchange_code_for_token,
    get_discord_user, create_access_token, require_auth, DiscordUser
)
from .database import init_database, get_db_session, Poll, Vote, POLL_EMOJIS, UserPreference
from .bulletproof_operations import BulletproofPollOperations
from .error_handler import PollErrorHandler
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
        # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
        from .error_handler import notify_error
        notify_error(e, "Image Cleanup", image_path=image_path)
    return False


async def cleanup_poll_images(poll_id: int) -> None:
    """Clean up images associated with a poll when it's closed"""
    db = get_db_session()
    try:
        poll = db.query(Poll).filter(Poll.id == poll_id).first()
        if poll and poll.image_path is not None:
            await cleanup_image(str(poll.image_path))
    except Exception as e:
        logger.error(f"Error cleaning up poll {poll_id} images: {e}")
        # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
        from .error_handler import notify_error
        notify_error(e, "Poll Image Cleanup", poll_id=poll_id)
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
        # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
        from .error_handler import notify_error
        notify_error(e, "Form Data Extraction", key=key, default=default)
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
        # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
        from .error_handler import notify_error
        notify_error(e, "Timezone Validation", timezone_str=timezone_str)
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
            # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
            from .error_handler import notify_error
            notify_error(fallback_error, "Fallback Datetime Parsing",
                         datetime_str=datetime_str, timezone_str=timezone_str)
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
        # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
        from .error_handler import notify_error_async
        await notify_error_async(e, "Image File Validation")
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
        # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
        from .error_handler import notify_error_async
        await notify_error_async(e, "Image File Saving", filename=filename)
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
        # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
        from .error_handler import notify_error
        notify_error(e, "User Preferences Retrieval", user_id=user_id)
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
        # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
        from .error_handler import notify_error
        notify_error(e, "Datetime Formatting", dt=str(
            dt), user_timezone=user_timezone)
        # Fallback to UTC
        return dt.strftime('%b %d, %I:%M %p UTC')


def get_common_timezones() -> list:
    """Get comprehensive list of timezones with display names"""
    common_timezones = [
        # North America
        "US/Eastern", "US/Central", "US/Mountain", "US/Pacific", "US/Alaska", "US/Hawaii",
        "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles",
        "America/Anchorage", "America/Honolulu", "America/Toronto", "America/Vancouver",
        "America/Mexico_City", "America/Sao_Paulo", "America/Argentina/Buenos_Aires",

        # Europe
        "UTC", "Europe/London", "Europe/Paris", "Europe/Berlin", "Europe/Rome",
        "Europe/Madrid", "Europe/Amsterdam", "Europe/Brussels", "Europe/Vienna",
        "Europe/Prague", "Europe/Warsaw", "Europe/Stockholm", "Europe/Helsinki",
        "Europe/Oslo", "Europe/Copenhagen", "Europe/Zurich", "Europe/Athens",
        "Europe/Istanbul", "Europe/Moscow",

        # Asia Pacific
        "Asia/Tokyo", "Asia/Seoul", "Asia/Shanghai", "Asia/Hong_Kong", "Asia/Singapore",
        "Asia/Bangkok", "Asia/Jakarta", "Asia/Manila", "Asia/Kuala_Lumpur",
        "Asia/Mumbai", "Asia/Kolkata", "Asia/Dubai", "Asia/Tehran", "Asia/Jerusalem",
        "Australia/Sydney", "Australia/Melbourne", "Australia/Perth", "Australia/Brisbane",
        "Pacific/Auckland", "Pacific/Fiji", "Pacific/Honolulu",

        # Africa
        "Africa/Cairo", "Africa/Johannesburg", "Africa/Lagos", "Africa/Nairobi",
        "Africa/Casablanca", "Africa/Tunis", "Africa/Algiers",

        # South America
        "America/Lima", "America/Bogota", "America/Santiago", "America/Caracas",

        # Other
        "GMT", "EST", "CST", "MST", "PST"
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

            # Create a more readable display name
            display_name = tz_name.replace('_', ' ').replace('/', ' / ')
            timezones.append({
                "name": tz_name,
                "display": f"{display_name} ({offset_formatted})"
            })
        except (pytz.UnknownTimeZoneError, ValueError, AttributeError) as e:
            logger.warning(f"Error formatting timezone {tz_name}: {e}")
            timezones.append({
                "name": tz_name,
                "display": tz_name
            })

    # Sort by offset for better UX
    timezones.sort(key=lambda x: x['display'])
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
        # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
        from .error_handler import notify_error
        notify_error(e, "User Preferences Saving", user_id=user_id,
                     server_id=server_id, channel_id=channel_id, timezone=timezone)
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
        # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
        from .error_handler import notify_error
        notify_error(e, "Discord Command Sync")


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
            args=[int(poll.id)],
            id=f"close_poll_{int(poll.id)}"
        )

    except Exception as e:
        logger.error(f"Error creating poll: {e}")
        # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
        from .error_handler import notify_error_async
        await notify_error_async(e, "Quick Poll Creation", question=question, user_id=str(interaction.user.id))
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Error creating poll. Please try again.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Error creating poll. Please try again.", ephemeral=True)
    finally:
        db.close()


@bot.event
async def on_reaction_add(reaction, user):
    """Handle poll voting via reactions using bulletproof operations"""
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

        # Get poll ID as integer for use throughout
        poll_id = int(poll.id)

        # CRITICAL: Vote MUST be counted FIRST, reaction removed ONLY if vote succeeds
        # Use bulletproof vote collection
        bulletproof_ops = BulletproofPollOperations(bot)
        result = await bulletproof_ops.bulletproof_vote_collection(
            poll_id, str(user.id), option_index
        )

        if result["success"]:
            # Vote was successfully recorded - handle reaction based on poll type and anonymity
            vote_action = result.get("action", "unknown")

            # Check poll properties safely - handle potential None values
            is_anonymous = getattr(poll, 'anonymous', False)
            is_multiple_choice = getattr(poll, 'multiple_choice', False)

            # Convert to boolean if needed (SQLAlchemy columns might return special types)
            if is_anonymous is not None:
                is_anonymous = bool(is_anonymous)
            else:
                is_anonymous = False

            if is_multiple_choice is not None:
                is_multiple_choice = bool(is_multiple_choice)
            else:
                is_multiple_choice = False

            # Always remove reactions for anonymous polls (to maintain anonymity)
            # Always remove reactions for single choice polls (traditional behavior)
            # For multiple choice non-anonymous polls: keep reactions to show selections
            should_remove_reaction = (
                is_anonymous or  # Anonymous polls: always remove
                not is_multiple_choice or  # Single choice polls: always remove
                vote_action == "removed"  # Multiple choice: remove if vote was toggled off
            )

            if should_remove_reaction:
                try:
                    await reaction.remove(user)
                    logger.debug(
                        f"✅ Vote {vote_action} and reaction removed for user {user.id} on poll {poll_id} "
                        f"(anonymous={is_anonymous}, multiple_choice={is_multiple_choice})")
                except Exception as remove_error:
                    logger.warning(
                        f"⚠️ Vote recorded but failed to remove reaction from user {user.id}: {remove_error}")
                    # Vote is still counted even if reaction removal fails
            else:
                # Multiple choice non-anonymous: keep reaction to show user's selection
                logger.debug(
                    f"✅ Multiple choice non-anonymous vote {vote_action}, keeping reaction for user {user.id} on poll {poll_id}")

            # Always update poll embed for live updates (key requirement)
            try:
                await update_poll_message(bot, poll)
                logger.debug(f"✅ Poll message updated for poll {poll_id}")
            except Exception as update_error:
                logger.error(
                    f"❌ Failed to update poll message for poll {poll_id}: {update_error}")
        else:
            # Vote failed - do NOT remove reaction, log the error
            error_msg = await PollErrorHandler.handle_vote_error(
                Exception(result["error"]), poll_id, str(user.id), bot
            )
            logger.error(
                f"❌ Vote FAILED for user {user.id} on poll {poll_id}: {error_msg}")
            # Reaction stays so user can try again

    except Exception as e:
        # Handle unexpected voting errors with bot owner notification
        try:
            poll_id_for_error = int(poll.id) if 'poll' in locals(
            ) and poll and hasattr(poll, 'id') else 0
            error_msg = await PollErrorHandler.handle_vote_error(
                e, poll_id_for_error, str(user.id), bot
            )
            logger.error(f"Error handling vote: {error_msg}")
            # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
            from .error_handler import notify_error_async
            await notify_error_async(e, "Reaction Vote Handling Critical Error",
                                     poll_id=poll_id_for_error, user_id=str(user.id))
        except Exception as error_handling_error:
            logger.error(
                f"Critical error in vote error handling: {error_handling_error}")
            # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
            from .error_handler import notify_error_async
            await notify_error_async(error_handling_error, "Vote Error Handler Failure",
                                     user_id=str(user.id))
    finally:
        db.close()


async def close_poll(poll_id: int):
    """Close a poll using bulletproof operations"""
    try:
        # Use bulletproof poll closure
        bulletproof_ops = BulletproofPollOperations(bot)
        result = await bulletproof_ops.bulletproof_poll_closure(poll_id)

        if not result["success"]:
            # Handle closure error with bot owner notification
            error_msg = await PollErrorHandler.handle_poll_closure_error(
                Exception(result["error"]), poll_id, bot
            )
            logger.error(
                f"Bulletproof poll closure failed for poll {poll_id}: {error_msg}")
        else:
            logger.info(
                f"Successfully closed poll {poll_id} using bulletproof operations")

    except Exception as e:
        # Handle unexpected closure errors with bot owner notification
        error_msg = await PollErrorHandler.handle_poll_closure_error(
            e, poll_id, bot
        )
        logger.error(f"Error in close_poll function: {error_msg}")


async def start_bot():
    """Start the Discord bot"""
    if DISCORD_TOKEN:
        await bot.start(DISCORD_TOKEN)


async def restore_scheduled_jobs():
    """
    Restore scheduled jobs from database on startup with comprehensive debugging.

    This function queries the database for all polls with status 'scheduled' and restores their scheduled jobs in the APScheduler.
    - If a poll's open time is overdue (in the past), it is posted immediately to Discord and activated.
    - Future polls are scheduled to open at their designated time.
    - All polls (active or scheduled) have their closing jobs scheduled if their close time is in the future.
    - If a poll's close time is overdue, it is closed immediately.
    Side effects:
    - Overdue polls are posted and/or closed immediately, which may result in multiple polls being posted or closed at startup.
    - Scheduler jobs are created for both opening and closing polls, ensuring no scheduled poll is missed after a restart.
    - Errors during restoration are logged but do not halt the restoration process for other polls.
    """
    logger.info("🔄 SCHEDULER RESTORE - Starting restore_scheduled_jobs")

    # Debug scheduler status
    if not scheduler:
        logger.error("❌ SCHEDULER RESTORE - Scheduler instance is None")
        return

    if not scheduler.running:
        logger.error("❌ SCHEDULER RESTORE - Scheduler is not running")
        return

    logger.debug(
        f"✅ SCHEDULER RESTORE - Scheduler is running, state: {scheduler.state}")

    # Debug bot status
    if not bot:
        logger.error("❌ SCHEDULER RESTORE - Bot instance is None")
        return

    if not bot.is_ready():
        logger.warning(
            "⚠️ SCHEDULER RESTORE - Bot is not ready yet, jobs may fail")
    else:
        logger.debug(f"✅ SCHEDULER RESTORE - Bot is ready: {bot.user}")

    db = get_db_session()
    try:
        # Get all scheduled polls with debugging
        logger.debug(
            "🔍 SCHEDULER RESTORE - Querying database for scheduled polls")
        scheduled_polls = db.query(Poll).filter(
            Poll.status == "scheduled").all()
        logger.info(
            f"📊 SCHEDULER RESTORE - Found {len(scheduled_polls)} scheduled polls to restore")

        if not scheduled_polls:
            logger.info(
                "✅ SCHEDULER RESTORE - No scheduled polls found, restoration complete")
            return

        # Get current time for comparison
        now = datetime.now(pytz.UTC)
        logger.debug(f"⏰ SCHEDULER RESTORE - Current time: {now}")

        # Process each scheduled poll
        restored_count = 0
        immediate_posts = 0
        immediate_closes = 0

        for poll in scheduled_polls:
            try:
                logger.info(
                    f"🔄 SCHEDULER RESTORE - Processing poll {int(poll.id)}: '{poll.name}'")
                logger.debug(
                    f"Poll {int(poll.id)} details: open_time={poll.open_time}, close_time={poll.close_time}, status={poll.status}")

                # Check if poll should have already opened
                if poll.open_time <= now:
                    # Poll should be active now, post it immediately
                    time_overdue = (now - poll.open_time).total_seconds()
                    logger.warning(
                        f"⏰ SCHEDULER RESTORE - Poll {int(poll.id)} is {time_overdue:.0f} seconds overdue, posting immediately")

                    try:
                        success = await post_poll_to_channel(bot, poll)
                        if success:
                            immediate_posts += 1
                            logger.info(
                                f"✅ SCHEDULER RESTORE - Successfully posted overdue poll {int(poll.id)}")
                        else:
                            logger.error(
                                f"❌ SCHEDULER RESTORE - Failed to post overdue poll {int(poll.id)}")
                    except Exception as post_exc:
                        logger.error(
                            f"❌ SCHEDULER RESTORE - Exception posting poll {int(poll.id)}: {post_exc}")
                        logger.exception(
                            f"Full traceback for poll {int(poll.id)} posting:")
                else:
                    # Schedule poll to open
                    time_until_open = (poll.open_time - now).total_seconds()
                    logger.info(
                        f"📅 SCHEDULER RESTORE - Scheduling poll {int(poll.id)} to open in {time_until_open:.0f} seconds at {poll.open_time}")

                    try:
                        scheduler.add_job(
                            post_poll_to_channel,
                            DateTrigger(run_date=poll.open_time),
                            args=[bot, poll],
                            id=f"open_poll_{int(poll.id)}",
                            replace_existing=True
                        )
                        logger.debug(
                            f"✅ SCHEDULER RESTORE - Scheduled opening job for poll {int(poll.id)}")
                    except Exception as schedule_exc:
                        logger.error(
                            f"❌ SCHEDULER RESTORE - Failed to schedule opening for poll {int(poll.id)}: {schedule_exc}")

                # Always schedule poll to close (whether it's active or scheduled)
                if poll.close_time > now:
                    time_until_close = (poll.close_time - now).total_seconds()
                    logger.debug(
                        f"📅 SCHEDULER RESTORE - Scheduling poll {int(poll.id)} to close in {time_until_close:.0f} seconds at {poll.close_time}")

                    try:
                        scheduler.add_job(
                            close_poll,
                            DateTrigger(run_date=poll.close_time),
                            args=[int(poll.id)],
                            id=f"close_poll_{int(poll.id)}",
                            replace_existing=True
                        )
                        logger.debug(
                            f"✅ SCHEDULER RESTORE - Scheduled closing job for poll {int(poll.id)}")
                    except Exception as schedule_exc:
                        logger.error(
                            f"❌ SCHEDULER RESTORE - Failed to schedule closing for poll {int(poll.id)}: {schedule_exc}")
                else:
                    # Poll should have already closed
                    time_overdue = (now - poll.close_time).total_seconds()
                    logger.warning(
                        f"⏰ SCHEDULER RESTORE - Poll {int(poll.id)} close time is {time_overdue:.0f} seconds overdue, closing now")

                    try:
                        await close_poll(int(poll.id))
                        immediate_closes += 1
                        logger.info(
                            f"✅ SCHEDULER RESTORE - Successfully closed overdue poll {int(poll.id)}")
                    except Exception as close_exc:
                        logger.error(
                            f"❌ SCHEDULER RESTORE - Exception closing poll {int(poll.id)}: {close_exc}")
                        logger.exception(
                            f"Full traceback for poll {int(poll.id)} closing:")

                restored_count += 1
                logger.debug(
                    f"✅ SCHEDULER RESTORE - Completed processing poll {int(poll.id)}")

            except Exception as e:
                logger.error(
                    f"❌ SCHEDULER RESTORE - Error processing poll {int(poll.id) if poll and hasattr(poll, 'id') else 'unknown'}: {e}")
                logger.exception(
                    f"Full traceback for poll {int(poll.id) if poll and hasattr(poll, 'id') else 'unknown'} restoration error:")

        # Log final restoration summary
        logger.info("🎉 SCHEDULER RESTORE - Restoration complete!")
        logger.info(
            f"📊 SCHEDULER RESTORE - Summary: {restored_count}/{len(scheduled_polls)} polls processed")
        logger.info(
            f"📊 SCHEDULER RESTORE - Immediate actions: {immediate_posts} posted, {immediate_closes} closed")

        # Debug current scheduler jobs
        current_jobs = scheduler.get_jobs()
        logger.info(
            f"📊 SCHEDULER RESTORE - Total active jobs after restoration: {len(current_jobs)}")
        for job in current_jobs:
            logger.debug(
                f"Active job: {job.id} - next run: {job.next_run_time}")

    except Exception as e:
        logger.error(
            f"❌ SCHEDULER RESTORE - Critical error during restoration: {e}")
        logger.exception("Full traceback for scheduler restoration error:")
    finally:
        db.close()
        logger.debug("🔄 SCHEDULER RESTORE - Database connection closed")


async def start_scheduler():
    """Start the job scheduler"""
    scheduler.start()
    logger.info("Scheduler started")

    # Restore scheduled jobs from database
    await restore_scheduled_jobs()


async def reaction_safeguard_task():
    """
    Safeguard task that runs every 5 seconds to check for unprocessed reactions
    on active polls and handle them to ensure no votes are lost.
    """
    while True:
        try:
            await asyncio.sleep(5)  # Run every 5 seconds

            if not bot or not bot.is_ready():
                continue

            # Get all active polls
            db = get_db_session()
            try:
                active_polls = db.query(Poll).filter(
                    Poll.status == "active").all()

                for poll in active_polls:
                    try:
                        if not poll.message_id:
                            continue

                        # Get the Discord message
                        try:
                            channel = bot.get_channel(int(poll.channel_id))
                            if not channel:
                                continue
                        except Exception as channel_error:
                            logger.error(
                                f"❌ Safeguard: Error getting channel {str(poll.channel_id)} for poll {int(poll.id)}: {channel_error}")
                            # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
                            from .error_handler import notify_error_async
                            await notify_error_async(channel_error, "Safeguard Channel Access",
                                                     poll_id=int(poll.id), channel_id=str(poll.channel_id))
                            continue

                        try:
                            message = await channel.fetch_message(int(poll.message_id))
                        except (discord.NotFound, discord.Forbidden):
                            logger.debug(
                                f"🔍 Safeguard: Message {str(poll.message_id)} not found or forbidden for poll {int(poll.id)}")
                            continue
                        except Exception as fetch_error:
                            logger.error(
                                f"❌ Safeguard: Error fetching message {str(poll.message_id)} for poll {int(poll.id)}: {fetch_error}")
                            # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
                            from .error_handler import notify_error_async
                            await notify_error_async(fetch_error, "Safeguard Message Fetch",
                                                     poll_id=int(poll.id), message_id=str(poll.message_id))
                            continue

                        # Check each reaction on the message
                        for reaction in message.reactions:
                            try:
                                if str(reaction.emoji) not in POLL_EMOJIS:
                                    continue

                                option_index = POLL_EMOJIS.index(
                                    str(reaction.emoji))
                                if option_index >= len(poll.options):
                                    continue

                                # Get users who reacted (excluding the bot)
                                try:
                                    async for user in reaction.users():
                                        if user.bot:
                                            continue

                                        try:
                                            # Check if this user's vote is already recorded
                                            existing_vote = db.query(Vote).filter(
                                                Vote.poll_id == int(poll.id),
                                                Vote.user_id == str(user.id)
                                            ).first()

                                            if existing_vote:
                                                # Vote exists, remove the reaction (cleanup)
                                                try:
                                                    await reaction.remove(user)
                                                    logger.debug(
                                                        f"🧹 Safeguard: Cleaned up reaction from user {user.id} on poll {int(poll.id)} (vote already recorded)")
                                                except Exception as remove_error:
                                                    logger.debug(
                                                        f"⚠️ Safeguard: Failed to remove reaction from user {user.id}: {remove_error}")
                                            else:
                                                # No vote recorded, process the vote
                                                logger.info(
                                                    f"🛡️ Safeguard: Processing missed reaction from user {user.id} on poll {int(poll.id)}")

                                                try:
                                                    # Use bulletproof vote collection
                                                    bulletproof_ops = BulletproofPollOperations(
                                                        bot)
                                                    result = await bulletproof_ops.bulletproof_vote_collection(
                                                        int(poll.id), str(
                                                            user.id), option_index
                                                    )

                                                    if result["success"]:
                                                        # Vote was successfully recorded - NOW remove the reaction
                                                        try:
                                                            await reaction.remove(user)
                                                            logger.info(
                                                                f"✅ Safeguard: Vote recorded and reaction removed for user {user.id} on poll {poll.id}")
                                                        except Exception as remove_error:
                                                            logger.warning(
                                                                f"⚠️ Safeguard: Vote recorded but failed to remove reaction from user {user.id}: {remove_error}")

                                                        # Update poll embed for live updates
                                                        try:
                                                            await update_poll_message(bot, poll)
                                                            logger.debug(
                                                                f"✅ Safeguard: Poll message updated for poll {int(poll.id)}")
                                                        except Exception as update_error:
                                                            logger.error(
                                                                f"❌ Safeguard: Failed to update poll message for poll {int(poll.id)}: {update_error}")
                                                            # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
                                                            from .error_handler import notify_error_async
                                                            await notify_error_async(update_error, "Safeguard Poll Message Update",
                                                                                     poll_id=int(poll.id), user_id=str(user.id))
                                                    else:
                                                        # Vote failed - leave reaction for user to try again
                                                        logger.error(
                                                            f"❌ Safeguard: Vote FAILED for user {user.id} on poll {int(poll.id)}: {result['error']}")
                                                        # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
                                                        from .error_handler import notify_error_async
                                                        await notify_error_async(Exception(result['error']), "Safeguard Vote Processing Failed",
                                                                                 poll_id=int(poll.id), user_id=str(user.id), option_index=option_index)

                                                except Exception as vote_error:
                                                    logger.error(
                                                        f"❌ Safeguard: Critical error processing vote for user {user.id} on poll {int(poll.id)}: {vote_error}")
                                                    # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
                                                    from .error_handler import notify_error_async
                                                    await notify_error_async(vote_error, "Safeguard Vote Processing Critical Error",
                                                                             poll_id=int(poll.id), user_id=str(user.id), option_index=option_index)

                                        except Exception as user_error:
                                            logger.error(
                                                f"❌ Safeguard: Error processing user {user.id} reaction on poll {int(poll.id)}: {user_error}")
                                            # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
                                            from .error_handler import notify_error_async
                                            await notify_error_async(user_error, "Safeguard User Processing Error",
                                                                     poll_id=int(poll.id), user_id=str(user.id))
                                            continue

                                except Exception as users_error:
                                    logger.error(
                                        f"❌ Safeguard: Error iterating reaction users for poll {int(poll.id)}: {users_error}")
                                    # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
                                    from .error_handler import notify_error_async
                                    await notify_error_async(users_error, "Safeguard Reaction Users Iteration",
                                                             poll_id=int(poll.id), emoji=str(reaction.emoji))
                                    continue

                            except Exception as reaction_error:
                                logger.error(
                                    f"❌ Safeguard: Error processing reaction {reaction.emoji} on poll {int(poll.id)}: {reaction_error}")
                                # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
                                from .error_handler import notify_error_async
                                await notify_error_async(reaction_error, "Safeguard Reaction Processing",
                                                         poll_id=int(poll.id), emoji=str(reaction.emoji))
                                continue

                    except Exception as poll_error:
                        logger.error(
                            f"❌ Safeguard: Error processing poll {int(poll.id)}: {poll_error}")
                        # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
                        from .error_handler import notify_error_async
                        await notify_error_async(poll_error, "Safeguard Poll Processing", poll_id=int(poll.id))
                        continue

            except Exception as db_error:
                logger.error(f"❌ Safeguard: Database error: {db_error}")
                # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
                from .error_handler import notify_error_async
                await notify_error_async(db_error, "Safeguard Database Error")
            finally:
                try:
                    db.close()
                except Exception as close_error:
                    logger.error(
                        f"❌ Safeguard: Error closing database: {close_error}")
                    # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
                    from .error_handler import notify_error_async
                    await notify_error_async(close_error, "Safeguard Database Close Error")

        except Exception as e:
            logger.error(
                f"❌ Safeguard: Critical error in reaction safeguard task: {e}")
            # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
            from .error_handler import notify_error_async
            await notify_error_async(e, "Safeguard Task Critical Error")
            # Continue running even if there's an error
            continue


async def start_reaction_safeguard():
    """Start the reaction safeguard background task"""
    try:
        logger.info("🛡️ Starting reaction safeguard task")
        asyncio.create_task(reaction_safeguard_task())
        logger.info("✅ Reaction safeguard task started successfully")
    except Exception as e:
        logger.error(f"❌ Failed to start reaction safeguard task: {e}")
        # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
        from .error_handler import notify_error_async
        await notify_error_async(e, "Safeguard Task Startup Error")
        raise e  # Re-raise to ensure the application knows the safeguard failed to start


# Lifespan manager for background tasks
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    asyncio.create_task(start_scheduler())
    asyncio.create_task(start_bot())
    asyncio.create_task(start_reaction_safeguard())
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
        # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
        from .error_handler import notify_error_async
        await notify_error_async(e, "Discord OAuth Callback", code=code)
        return HTMLResponse("Authentication failed", status_code=400)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, current_user: DiscordUser = Depends(require_auth)):
    """User dashboard with HTMX"""
    # Check if user has timezone preference set
    user_prefs = get_user_preferences(current_user.id)

    # Get user's guilds with channels with error handling
    try:
        user_guilds = await get_user_guilds_with_channels(bot, current_user.id)
        # Ensure user_guilds is always a valid list
        if user_guilds is None:
            user_guilds = []
    except Exception as e:
        logger.error(f"Error getting user guilds for {current_user.id}: {e}")
        from .error_handler import notify_error_async
        await notify_error_async(e, "Dashboard Guild Retrieval", user_id=current_user.id)
        user_guilds = []

    return templates.TemplateResponse("dashboard_htmx.html", {
        "request": request,
        "user": current_user,
        "guilds": user_guilds,
        "show_timezone_prompt": user_prefs.get("last_server_id") is None
    })


# HTMX endpoints for dynamic content without JavaScript
@app.get("/htmx/polls", response_class=HTMLResponse)
async def get_polls_htmx(request: Request, filter: str = None, current_user: DiscordUser = Depends(require_auth)):
    """Get user's polls as HTML for HTMX with bulletproof error handling"""
    db = get_db_session()
    try:
        logger.debug(
            f"Getting polls for user {current_user.id} with filter: {filter}")

        # Query polls with error handling
        try:
            query = db.query(Poll).filter(Poll.creator_id == current_user.id)

            # Apply filter if specified with validation
            if filter and filter in ['active', 'scheduled', 'closed']:
                query = query.filter(Poll.status == filter)
                logger.debug(f"Applied filter: {filter}")

            polls = query.order_by(Poll.created_at.desc()).all()
            logger.debug(
                f"Found {len(polls)} polls for user {current_user.id}")

        except Exception as e:
            logger.error(
                f"Database error querying polls for user {current_user.id}: {e}")
            logger.exception("Full traceback for polls query error:")

            # Return error template with empty polls list
            return templates.TemplateResponse("htmx/polls.html", {
                "request": request,
                "polls": [],
                "current_filter": filter,
                "user_timezone": "US/Eastern",
                "format_datetime_for_user": format_datetime_for_user,
                "error": "Database error loading polls"
            })

        # Process polls with individual error handling
        processed_polls = []
        for poll in polls:
            try:
                # Add status_class to each poll for template
                poll.status_class = {
                    'active': 'bg-success',
                    'scheduled': 'bg-warning',
                    'closed': 'bg-danger'
                }.get(poll.status, 'bg-secondary')

                processed_polls.append(poll)
                logger.debug(
                    f"Processed poll {poll.id} with status {poll.status}")

            except Exception as e:
                logger.error(f"Error processing poll {poll.id}: {e}")
                # Continue with other polls, skip this one

        # Get user's timezone preference with error handling
        try:
            user_prefs = get_user_preferences(current_user.id)
            user_timezone = user_prefs.get("default_timezone", "US/Eastern")
            logger.debug(f"User timezone: {user_timezone}")
        except Exception as e:
            logger.error(
                f"Error getting user preferences for {current_user.id}: {e}")
            user_timezone = "US/Eastern"

        logger.debug(f"Returning {len(processed_polls)} processed polls")

        return templates.TemplateResponse("htmx/polls.html", {
            "request": request,
            "polls": processed_polls,
            "current_filter": filter,
            "user_timezone": user_timezone,
            "format_datetime_for_user": format_datetime_for_user
        })

    except Exception as e:
        logger.error(
            f"Critical error in get_polls_htmx for user {current_user.id}: {e}")
        logger.exception("Full traceback for polls endpoint error:")

        # Return error-safe template
        return templates.TemplateResponse("htmx/polls.html", {
            "request": request,
            "polls": [],
            "current_filter": filter,
            "user_timezone": "US/Eastern",
            "format_datetime_for_user": format_datetime_for_user,
            "error": f"Error loading polls: {str(e)}"
        })
    finally:
        try:
            db.close()
        except Exception as e:
            logger.error(f"Error closing database connection: {e}")


@app.get("/htmx/stats", response_class=HTMLResponse)
async def get_stats_htmx(request: Request, current_user: DiscordUser = Depends(require_auth)):
    """Get dashboard stats as HTML for HTMX with bulletproof error handling"""
    db = get_db_session()
    try:
        logger.debug(f"Getting stats for user {current_user.id}")

        # Query polls with error handling
        try:
            polls = db.query(Poll).filter(
                Poll.creator_id == current_user.id).all()
            logger.debug(
                f"Found {len(polls)} polls for user {current_user.id}")
        except Exception as e:
            logger.error(
                f"Database error querying polls for user {current_user.id}: {e}")
            return templates.TemplateResponse("htmx/stats.html", {
                "request": request,
                "total_polls": 0,
                "active_polls": 0,
                "total_votes": 0,
                "error": "Database error loading polls"
            })

        # Calculate stats with individual error handling
        total_polls = len(polls)

        # Count active polls safely
        try:
            active_polls = len([p for p in polls if p.status == 'active'])
            logger.debug(f"Found {active_polls} active polls")
        except Exception as e:
            logger.error(f"Error counting active polls: {e}")
            active_polls = 0

        # Calculate total votes with bulletproof handling
        total_votes = 0
        for poll in polls:
            try:
                # Use the Poll model's get_total_votes method
                poll_votes = poll.get_total_votes()
                if isinstance(poll_votes, int):
                    total_votes += poll_votes
                    logger.debug(f"Poll {poll.id} has {poll_votes} votes")
                else:
                    logger.warning(
                        f"Poll {poll.id} get_total_votes returned non-int: {type(poll_votes)}")
            except Exception as e:
                logger.error(f"Error getting votes for poll {poll.id}: {e}")
                # Try alternative method - direct vote count
                try:
                    vote_count = db.query(Vote).filter(
                        Vote.poll_id == poll.id).count()
                    if isinstance(vote_count, int):
                        total_votes += vote_count
                        logger.debug(
                            f"Poll {poll.id} fallback vote count: {vote_count}")
                except Exception as fallback_e:
                    logger.error(
                        f"Fallback vote count failed for poll {poll.id}: {fallback_e}")
                    # Continue without adding votes for this poll

        logger.debug(
            f"Stats calculated: polls={total_polls}, active={active_polls}, votes={total_votes}")

        return templates.TemplateResponse("htmx/stats.html", {
            "request": request,
            "total_polls": total_polls,
            "active_polls": active_polls,
            "total_votes": total_votes
        })

    except Exception as e:
        logger.error(
            f"Critical error in get_stats_htmx for user {current_user.id}: {e}")
        logger.exception("Full traceback for stats error:")

        # Return error-safe template
        return templates.TemplateResponse("htmx/stats.html", {
            "request": request,
            "total_polls": 0,
            "active_polls": 0,
            "total_votes": 0,
            "error": f"Error loading stats: {str(e)}"
        })
    finally:
        try:
            db.close()
        except Exception as e:
            logger.error(f"Error closing database connection: {e}")


@app.get("/htmx/create-form", response_class=HTMLResponse)
async def get_create_form_htmx(request: Request, current_user: DiscordUser = Depends(require_auth)):
    """Get create poll form as HTML for HTMX"""
    # Get user's guilds with channels with error handling
    try:
        user_guilds = await get_user_guilds_with_channels(bot, current_user.id)
        # Ensure user_guilds is always a valid list
        if user_guilds is None:
            user_guilds = []
    except Exception as e:
        logger.error(
            f"Error getting user guilds for create form for {current_user.id}: {e}")
        from .error_handler import notify_error_async
        await notify_error_async(e, "Create Form Guild Retrieval", user_id=current_user.id)
        user_guilds = []

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
        # HTML escape the channel name to prevent JavaScript syntax errors
        from html import escape
        escaped_channel_name = escape(channel["name"])
        options += f'<option value="{channel["id"]}">#{escaped_channel_name}</option>'

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
        image_file = form_data.get("image")

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
        # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
        from .error_handler import notify_error_async
        await notify_error_async(e, "FilePond Image Upload", user_id=current_user.id)
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
        # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
        from .error_handler import notify_error_async
        await notify_error_async(e, "FilePond Image Removal", user_id=current_user.id)
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
        # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
        from .error_handler import notify_error_async
        await notify_error_async(e, "User Settings Save", user_id=current_user.id)
        return f"""
        <div class="alert alert-danger">
            <i class="fas fa-exclamation-triangle me-2"></i>Error saving settings: {str(e)}
        </div>
        """


@app.post("/htmx/create-poll", response_class=HTMLResponse)
async def create_poll_htmx(request: Request, current_user: DiscordUser = Depends(require_auth)):
    """Create a new poll via HTMX using bulletproof operations"""
    logger.info(f"User {current_user.id} creating new poll")

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
        multiple_choice = form_data.get("multiple_choice") == "true"
        image_message_text = safe_get_form_data(
            form_data, "image_message_text", "")

        # Get options and emojis
        options = []
        emojis = []
        for i in range(1, 11):
            option = form_data.get(f"option{i}")
            if option:
                options.append(str(option).strip())
                # Extract emoji from form data, fallback to default if not provided
                emoji = safe_get_form_data(form_data, f"emoji{i}")
                if emoji:
                    emojis.append(emoji)
                else:
                    # Fallback to default emojis if not provided
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
        timezone_str = validate_and_normalize_timezone(timezone_str)

        # Validate times
        now = datetime.now(pytz.UTC)
        next_minute = now.replace(
            second=0, microsecond=0) + timedelta(minutes=1)

        if open_dt < next_minute:
            user_tz = pytz.timezone(timezone_str)
            next_minute_local = next_minute.astimezone(user_tz)
            suggested_time = next_minute_local.strftime('%I:%M %p')
            return f"""
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>Poll open time must be scheduled for the next minute or later. Try {suggested_time} or later.
            </div>
            """

        if close_dt <= open_dt:
            return """
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>Close time must be after open time
            </div>
            """

        # Prepare poll data for bulletproof operations
        poll_data = {
            "name": name,
            "question": question,
            "options": options,
            "emojis": emojis,  # Include emojis in poll data
            "server_id": server_id,
            "channel_id": channel_id,
            "open_time": open_dt,
            "close_time": close_dt,
            "timezone": timezone_str,
            "anonymous": anonymous,
            "multiple_choice": multiple_choice,
            "creator_id": current_user.id
        }

        # Handle image file
        image_file_data = None
        image_filename = None
        image_file = form_data.get("image")
        if image_file and hasattr(image_file, 'filename') and hasattr(image_file, 'read') and getattr(image_file, 'filename', None):
            try:
                image_file_data = await image_file.read()
                image_filename = str(getattr(image_file, 'filename', ''))
            except Exception as e:
                logger.error(f"Error reading image file: {e}")
                return """
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-triangle me-2"></i>Error reading image file
                </div>
                """

        # Use bulletproof poll operations for creation
        bulletproof_ops = BulletproofPollOperations(bot)

        result = await bulletproof_ops.create_bulletproof_poll(
            poll_data=poll_data,
            user_id=current_user.id,
            image_file=image_file_data,
            image_filename=image_filename,
            image_message_text=image_message_text if image_file_data else None
        )

        if not result["success"]:
            logger.warning(
                f"Bulletproof poll creation failed: {result['error']}")
            # Use error handler for user-friendly messages
            error_msg = await PollErrorHandler.handle_poll_creation_error(
                Exception(result["error"]), poll_data, bot
            )
            return f"""
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>{error_msg}
            </div>
            """

        poll_id = result["poll_id"]
        logger.info(f"Created poll {poll_id} for user {current_user.id}")

        # Use bulletproof scheduling operations
        try:
            # Always schedule polls - never post immediately to respect scheduling
            # Schedule opening with bulletproof error handling
            try:
                # Get the poll object for scheduling
                db = get_db_session()
                try:
                    poll_obj = db.query(Poll).filter(
                        Poll.id == poll_id).first()
                    if poll_obj:
                        scheduler.add_job(
                            post_poll_to_channel,
                            DateTrigger(run_date=open_dt),
                            args=[bot, poll_obj],
                            id=f"open_poll_{poll_id}",
                            replace_existing=True
                        )
                        logger.info(
                            f"Scheduled poll {poll_id} to open at {open_dt}")
                    else:
                        logger.error(
                            f"Poll {poll_id} not found for scheduling")
                finally:
                    db.close()
            except Exception as schedule_error:
                logger.error(
                    f"Failed to schedule poll opening: {schedule_error}")
                await PollErrorHandler.handle_scheduler_error(
                    schedule_error, poll_id, "poll_opening", bot
                )

            # Schedule poll to close with bulletproof error handling
            try:
                scheduler.add_job(
                    close_poll,
                    DateTrigger(run_date=close_dt),
                    args=[poll_id],
                    id=f"close_poll_{poll_id}",
                    replace_existing=True
                )
                logger.info(f"Scheduled poll {poll_id} to close at {close_dt}")
            except Exception as schedule_error:
                logger.error(
                    f"Failed to schedule poll closure: {schedule_error}")
                await PollErrorHandler.handle_scheduler_error(
                    schedule_error, poll_id, "poll_closure", bot
                )

        except Exception as scheduling_error:
            logger.error(
                f"Critical scheduling error for poll {poll_id}: {scheduling_error}")
            await PollErrorHandler.handle_scheduler_error(
                scheduling_error, poll_id, "poll_scheduling", bot
            )

        # Save user preferences for next time
        save_user_preferences(current_user.id, server_id,
                              channel_id, timezone_str)

        # Return success message and redirect to polls view
        return """
        <div class="alert alert-success">
            <i class="fas fa-check-circle me-2"></i>Poll created successfully! Redirecting to polls...
        </div>
        <div hx-get="/htmx/polls" hx-target="#main-content" hx-trigger="load delay:2s"></div>
        """

    except Exception as e:
        logger.error(f"Error creating poll for user {current_user.id}: {e}")
        logger.exception("Full traceback for poll creation error:")

        # Use error handler for comprehensive error handling
        poll_name = locals().get('name', 'Unknown')
        error_msg = await PollErrorHandler.handle_poll_creation_error(
            e, {"name": poll_name, "user_id": current_user.id}, bot
        )
        return f"""
        <div class="alert alert-danger">
            <i class="fas fa-exclamation-triangle me-2"></i>{error_msg}
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

        if str(getattr(poll, 'status', '')) != "scheduled":
            logger.warning(
                f"Attempt to edit non-scheduled poll {poll_id} (status: {getattr(poll, 'status', '')})")
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
        poll_timezone = str(getattr(poll, 'timezone', 'UTC'))
        tz = pytz.timezone(poll_timezone)

        # Ensure the stored times have timezone info (they should be UTC)
        open_time_value = getattr(poll, 'open_time')
        close_time_value = getattr(poll, 'close_time')

        if open_time_value.tzinfo is None:
            open_time_utc = pytz.UTC.localize(open_time_value)
        else:
            open_time_utc = open_time_value.astimezone(pytz.UTC)

        if close_time_value.tzinfo is None:
            close_time_utc = pytz.UTC.localize(close_time_value)
        else:
            close_time_utc = close_time_value.astimezone(pytz.UTC)

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
                # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
                from .error_handler import notify_error
                notify_error(e, "Timezone Formatting", tz_name=tz_name)
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

        if str(getattr(poll, 'status', '')) != "scheduled":
            logger.warning(
                f"Attempt to edit non-scheduled poll {poll_id} (status: {getattr(poll, 'status', '')})")
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
        image_message_text = safe_get_form_data(
            form_data, "image_message_text", "")

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
        new_image_path = getattr(poll, 'image_path', None)
        if content and hasattr(image_file, 'filename') and getattr(image_file, 'filename', None):
            new_image_path = await save_image_file(content, str(getattr(image_file, 'filename', '')))
            if not new_image_path:
                logger.error(f"Failed to save new image for poll {poll_id}")
                return """
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-triangle me-2"></i>Failed to save image file
                </div>
                """
            # Clean up old image
            old_image_path = getattr(poll, 'image_path', None)
            if old_image_path:
                await cleanup_image(str(old_image_path))

        # Get options and emojis
        options = []
        emojis = []
        for i in range(1, 11):
            option = form_data.get(f"option{i}")
            if option:
                options.append(str(option).strip())
                # Extract emoji from form data, fallback to default if not provided
                emoji = safe_get_form_data(form_data, f"emoji{i}")
                if emoji:
                    emojis.append(emoji)
                else:
                    # Fallback to default emojis if not provided
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

        # Update poll using setattr to avoid SQLAlchemy Column type issues
        setattr(poll, 'name', name)
        setattr(poll, 'question', question)
        poll.options = options
        poll.emojis = emojis  # Set emojis properly
        setattr(poll, 'image_path', new_image_path)
        setattr(poll, 'image_message_text',
                image_message_text if new_image_path else None)
        setattr(poll, 'server_id', server_id)
        setattr(poll, 'server_name', guild.name)
        setattr(poll, 'channel_id', channel_id)
        setattr(poll, 'channel_name', getattr(channel, 'name', 'Unknown'))
        setattr(poll, 'open_time', open_dt)
        setattr(poll, 'close_time', close_dt)
        setattr(poll, 'timezone', timezone_str)
        setattr(poll, 'anonymous', anonymous)

        db.commit()

        # Update scheduled jobs
        try:
            scheduler.remove_job(f"open_poll_{int(poll.id)}")
        except Exception as e:
            logger.debug(
                f"Job open_poll_{int(poll.id)} not found or already removed: {e}")
        try:
            scheduler.remove_job(f"close_poll_{int(poll.id)}")
        except Exception as e:
            logger.debug(
                f"Job close_poll_{int(poll.id)} not found or already removed: {e}")

        # Reschedule jobs
        if open_dt > datetime.now(pytz.UTC):
            scheduler.add_job(
                post_poll_to_channel,
                DateTrigger(run_date=open_dt),
                args=[bot, poll],
                id=f"open_poll_{int(getattr(poll, 'id'))}"
            )

        scheduler.add_job(
            close_poll,
            DateTrigger(run_date=close_dt),
            args=[int(getattr(poll, 'id'))],
            id=f"close_poll_{int(getattr(poll, 'id'))}"
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
        # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
        from .error_handler import notify_error_async
        await notify_error_async(e, "Poll Update", poll_id=poll_id, user_id=current_user.id)
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

        if str(getattr(poll, 'status', '')) != "active":
            logger.warning(
                f"Attempt to close non-active poll {poll_id} (status: {getattr(poll, 'status', '')})")
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
        # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
        from .error_handler import notify_error_async
        await notify_error_async(e, "Manual Poll Closure", poll_id=poll_id, user_id=current_user.id)
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

        if str(getattr(poll, 'status', '')) == "active":
            logger.warning(f"Attempt to delete active poll {poll_id}")
            return """
            <div class="alert alert-warning">
                <i class="fas fa-info-circle me-2"></i>Active polls cannot be deleted. Close the poll first.
            </div>
            """

        # Clean up image
        image_path = getattr(poll, 'image_path', None)
        if image_path:
            await cleanup_image(str(image_path))

        # Remove scheduled jobs with improved error handling
        jobs_removed = 0
        for job_type in ["open", "close"]:
            job_id = f"{job_type}_poll_{int(poll.id)}"
            try:
                if scheduler.get_job(job_id):
                    scheduler.remove_job(job_id)
                    jobs_removed += 1
                    logger.debug(f"Removed scheduled job: {job_id}")
            except Exception as e:
                # Only log if it's an unexpected error (not "job not found")
                if "No job by the id" not in str(e):
                    logger.warning(
                        f"Unexpected error removing job {job_id}: {e}")

        if jobs_removed > 0:
            logger.info(
                f"Removed {jobs_removed} scheduled jobs for poll {int(getattr(poll, 'id'))}")

        # Delete poll and associated votes with detailed logging
        logger.info(f"Starting database deletion for poll {poll_id}")

        try:
            # Delete associated votes first
            vote_count = db.query(Vote).filter(Vote.poll_id == poll_id).count()
            logger.info(
                f"Found {vote_count} votes to delete for poll {poll_id}")

            deleted_votes = db.query(Vote).filter(
                Vote.poll_id == poll_id).delete()
            logger.info(f"Deleted {deleted_votes} votes for poll {poll_id}")

            # Delete the poll
            logger.info(f"Deleting poll {poll_id} from database")
            db.delete(poll)

            # Commit the transaction
            logger.info(f"Committing deletion transaction for poll {poll_id}")
            db.commit()

            logger.info(f"Successfully deleted poll {poll_id}")

        except Exception as db_error:
            logger.error(
                f"Database error during poll {poll_id} deletion: {db_error}")
            logger.exception("Full traceback for database deletion error:")
            db.rollback()
            raise db_error

        return """
        <div class="alert alert-success">
            <i class="fas fa-check-circle me-2"></i>Poll deleted successfully! Redirecting to polls...
        </div>
        <div hx-get="/htmx/polls" hx-target="#main-content" hx-trigger="load delay:2s"></div>
        """

    except Exception as e:
        logger.error(f"Error deleting poll {poll_id}: {e}")
        # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
        from .error_handler import notify_error_async
        await notify_error_async(e, "Poll Deletion", poll_id=poll_id, user_id=current_user.id)
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
