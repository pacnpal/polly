"""
HTMX Endpoints Module
Handles all HTMX-related endpoints for dynamic web content without JavaScript.
"""

import logging
from datetime import datetime, timedelta
from html import escape
import pytz
import random
import uuid
import aiofiles
import os

from fastapi import Request, Depends
from fastapi.templating import Jinja2Templates
from apscheduler.triggers.date import DateTrigger

from .auth import require_auth, DiscordUser
from .database import get_db_session, Poll, Vote, UserPreference, TypeSafeColumn
from .discord_utils import get_user_guilds_with_channels
from .poll_operations import BulletproofPollOperations
from .error_handler import PollErrorHandler
from .timezone_scheduler_fix import TimezoneAwareScheduler
from .discord_emoji_handler import DiscordEmojiHandler

logger = logging.getLogger(__name__)

# Templates setup
templates = Jinja2Templates(directory="templates")


def safe_get_form_data(form_data, key: str, default: str = "") -> str:
    """Safely extract form data with proper error handling"""
    try:
        value = form_data.get(key)
        if value is None:
            return default
        return str(value).strip()
    except Exception as e:
        logger.warning(f"Error extracting form data for key '{key}': {e}")
        from .error_handler import notify_error
        notify_error(e, "Form Data Extraction", key=key, default=default)
        return default


def process_custom_emoji_with_fallbacks(emoji_text: str) -> tuple[bool, str]:
    """Process custom emoji with multiple fallback attempts before using default emojis

    Args:
        emoji_text: The text to process as an emoji

    Returns:
        Tuple of (is_valid, processed_emoji_or_error_message)
    """
    if not emoji_text or not emoji_text.strip():
        return False, "Empty emoji"

    import unicodedata
    import re

    # FALLBACK 1: Basic cleanup - remove extra whitespace and common issues
    cleaned_emoji = emoji_text.strip()

    # FALLBACK 2: Remove common text artifacts that might be mixed with emojis
    # Remove things like ":smile:" or "smile" if they're mixed with actual emojis
    emoji_pattern = re.compile(
        r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U0002600-\U0002B55\U0001F900-\U0001F9FF]+')
    emoji_matches = emoji_pattern.findall(cleaned_emoji)

    if emoji_matches:
        # If we found actual emoji characters, use the first one
        cleaned_emoji = emoji_matches[0]
        print(
            f"🔧 EMOJI FALLBACK 2 - Extracted emoji '{cleaned_emoji}' from text '{emoji_text.strip()}'")
        logger.info(
            f"🔧 EMOJI FALLBACK 2 - Extracted emoji '{cleaned_emoji}' from text '{emoji_text.strip()}'")

    # FALLBACK 3: Handle common emoji shortcodes and convert them
    emoji_shortcodes = {
        'smile': '😀', 'smiley': '😀', 'grinning': '😀',
        'heart': '❤️', 'love': '❤️',
        'thumbsup': '👍', '+1': '👍', 'like': '👍',
        'thumbsdown': '👎', '-1': '👎', 'dislike': '👎',
        'fire': '🔥', 'flame': '🔥',
        'star': '⭐', 'star2': '⭐',
        'check': '✅', 'checkmark': '✅', 'tick': '✅',
        'x': '❌', 'cross': '❌', 'no': '❌',
        'warning': '⚠️', 'warn': '⚠️',
        'question': '❓', '?': '❓',
        'exclamation': '❗', '!': '❗',
        'pizza': '🍕',
        'burger': '🍔', 'hamburger': '🍔',
        'beer': '🍺', 'drink': '🍺',
        'coffee': '☕',
        'cake': '🎂',
        'party': '🎉', 'celebration': '🎉',
        'music': '🎵', 'musical_note': '🎵',
        'car': '🚗', 'automobile': '🚗',
        'house': '🏠', 'home': '🏠',
        'sun': '☀️', 'sunny': '☀️',
        'moon': '🌙',
        'tree': '🌳',
        'flower': '🌸',
        'dog': '🐶', 'puppy': '🐶',
        'cat': '🐱', 'kitty': '🐱',
    }

    # Check if the cleaned text matches any shortcode
    lower_cleaned = cleaned_emoji.lower().strip(':')
    if lower_cleaned in emoji_shortcodes:
        emoji = emoji_shortcodes[lower_cleaned]
        print(
            f"🔧 EMOJI FALLBACK 3 - Converted shortcode '{cleaned_emoji}' to emoji '{emoji}'")
        logger.info(
            f"🔧 EMOJI FALLBACK 3 - Converted shortcode '{cleaned_emoji}' to emoji '{emoji}'")
        cleaned_emoji = emoji

    # FALLBACK 4: Try to extract single emoji character if mixed with text
    if len(cleaned_emoji) > 1:
        for char in cleaned_emoji:
            if _is_emoji_character(char):
                print(
                    f"🔧 EMOJI FALLBACK 4 - Extracted single emoji '{char}' from '{cleaned_emoji}'")
                logger.info(
                    f"🔧 EMOJI FALLBACK 4 - Extracted single emoji '{char}' from '{cleaned_emoji}'")
                cleaned_emoji = char
                break

    # FALLBACK 5: Final validation
    if _validate_emoji_strict(cleaned_emoji):
        return True, cleaned_emoji
    else:
        return False, f"Could not process '{emoji_text.strip()}' into valid emoji after all fallback attempts"


def _is_emoji_character(char: str) -> bool:
    """Check if a single character is an emoji"""
    import unicodedata

    category = unicodedata.category(char)
    return (category.startswith('So') or  # Other symbols (most emojis)
            category.startswith('Sm') or  # Math symbols (some emojis)
            category.startswith('Mn') or  # Nonspacing marks (emoji modifiers)
            category.startswith('Sk') or  # Modifier symbols
            ord(char) in range(0x1F000, 0x1FAFF) or  # Emoji blocks
            ord(char) in range(0x2600, 0x27BF) or   # Miscellaneous symbols
            ord(char) in range(0x1F300, 0x1F9FF) or  # Emoji ranges
            ord(char) in range(0x1F600, 0x1F64F) or  # Emoticons
            ord(char) in range(0x1F680, 0x1F6FF) or  # Transport symbols
            ord(char) in range(0x2700, 0x27BF) or   # Dingbats
            ord(char) in range(0xFE00, 0xFE0F))     # Variation selectors


def _validate_emoji_strict(emoji_text: str) -> bool:
    """Strict validation for final emoji"""
    import unicodedata

    if not emoji_text or len(emoji_text) > 10:
        return False

    # Check if all characters are emoji-related
    for char in emoji_text:
        if not _is_emoji_character(char):
            return False

    # Additional check: try to encode/decode to ensure it's valid Unicode
    try:
        emoji_text.encode('utf-8').decode('utf-8')
    except UnicodeError:
        return False

    return True


def validate_emoji(emoji_text: str) -> tuple[bool, str]:
    """Legacy function for backward compatibility - now uses the enhanced processor"""
    return process_custom_emoji_with_fallbacks(emoji_text)


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
        from .error_handler import notify_error_async
        await notify_error_async(e, "Image File Saving", filename=filename)
        return None


async def cleanup_image(image_path: str) -> bool:
    """Safely delete an image file"""
    try:
        if image_path and os.path.exists(image_path):
            os.remove(image_path)
            logger.info(f"Cleaned up image: {image_path}")
            return True
    except Exception as e:
        logger.error(f"Failed to cleanup image {image_path}: {e}")
        from .error_handler import notify_error
        notify_error(e, "Image Cleanup", image_path=image_path)
    return False


def get_user_preferences(user_id: str) -> dict:
    """Get user preferences for poll creation"""
    db = get_db_session()
    try:
        prefs = db.query(UserPreference).filter(
            UserPreference.user_id == user_id).first()
        if prefs:
            return {
                "last_server_id": TypeSafeColumn.get_string(prefs, 'last_server_id') or None,
                "last_channel_id": TypeSafeColumn.get_string(prefs, 'last_channel_id') or None,
                "default_timezone": TypeSafeColumn.get_string(prefs, 'default_timezone', 'US/Eastern')
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
            # Update existing preferences using setattr for SQLAlchemy compatibility
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


# HTMX endpoint functions that will be registered with the FastAPI app
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
                }.get(TypeSafeColumn.get_string(poll, 'status'), 'bg-secondary')

                processed_polls.append(poll)
                logger.debug(
                    f"Processed poll {TypeSafeColumn.get_int(poll, 'id')} with status {TypeSafeColumn.get_string(poll, 'status')}")

            except Exception as e:
                logger.error(
                    f"Error processing poll {TypeSafeColumn.get_int(poll, 'id', 0)}: {e}")
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
            active_polls = len(
                [p for p in polls if TypeSafeColumn.get_string(p, 'status') == 'active'])
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
                    logger.debug(
                        f"Poll {TypeSafeColumn.get_int(poll, 'id')} has {poll_votes} votes")
                else:
                    logger.warning(
                        f"Poll {TypeSafeColumn.get_int(poll, 'id')} get_total_votes returned non-int: {type(poll_votes)}")
            except Exception as e:
                logger.error(
                    f"Error getting votes for poll {TypeSafeColumn.get_int(poll, 'id', 0)}: {e}")
                # Try alternative method - direct vote count
                try:
                    vote_count = db.query(Vote).filter(
                        Vote.poll_id == TypeSafeColumn.get_int(poll, 'id')).count()
                    if isinstance(vote_count, int):
                        total_votes += vote_count
                        logger.debug(
                            f"Poll {TypeSafeColumn.get_int(poll, 'id')} fallback vote count: {vote_count}")
                except Exception as fallback_e:
                    logger.error(
                        f"Fallback vote count failed for poll {TypeSafeColumn.get_int(poll, 'id', 0)}: {fallback_e}")
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


async def get_create_form_htmx(request: Request, bot, current_user: DiscordUser = Depends(require_auth)):
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


async def get_channels_htmx(server_id: str, bot, current_user: DiscordUser = Depends(require_auth)):
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
        escaped_channel_name = escape(channel["name"])
        options += f'<option value="{channel["id"]}">#{escaped_channel_name}</option>'

    return options


async def add_option_htmx(request: Request):
    """Add a new poll option input for HTMX"""
    option_num = random.randint(3, 10)  # Simple way to get next option number
    emojis = ['🇦', '🇧', '🇨', '🇩', '🇪', '🇫', '🇬', '🇭', '🇮', '🇯']
    emoji = emojis[min(option_num - 1, len(emojis) - 1)]

    return templates.TemplateResponse("htmx/components/poll_option.html", {
        "request": request,
        "emoji": emoji,
        "option_num": option_num
    })


async def remove_option_htmx():
    """Remove a poll option for HTMX"""
    return ""  # Empty response removes the element


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
        from .error_handler import notify_error_async
        await notify_error_async(e, "FilePond Image Upload", user_id=current_user.id)
        return {"error": "Server error processing image"}, 500


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
        from .error_handler import notify_error_async
        await notify_error_async(e, "FilePond Image Removal", user_id=current_user.id)
        return {"error": "Server error removing image"}, 500


async def get_servers_htmx(request: Request, bot, current_user: DiscordUser = Depends(require_auth)):
    """Get user's servers as HTML for HTMX"""
    user_guilds = await get_user_guilds_with_channels(bot, current_user.id)

    return templates.TemplateResponse("htmx/servers.html", {
        "request": request,
        "guilds": user_guilds
    })


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

        return templates.TemplateResponse("htmx/components/alert_success.html", {
            "request": request,
            "message": "Settings saved successfully! Your timezone preference has been updated.",
            "redirect_url": "/htmx/settings"
        })

    except Exception as e:
        logger.error(f"Error saving settings for user {current_user.id}: {e}")
        from .error_handler import notify_error_async
        await notify_error_async(e, "User Settings Save", user_id=current_user.id)

        return templates.TemplateResponse("htmx/components/alert_error.html", {
            "request": request,
            "message": f"Error saving settings: {str(e)}"
        })


async def get_polls_realtime_htmx(request: Request, filter: str = None, current_user: DiscordUser = Depends(require_auth)):
    """Get real-time poll data for HTMX polling updates - returns only poll cards content"""
    db = get_db_session()
    try:
        # Query polls with error handling
        try:
            query = db.query(Poll).filter(Poll.creator_id == current_user.id)

            # Apply filter if specified with validation
            if filter and filter in ['active', 'scheduled', 'closed']:
                query = query.filter(Poll.status == filter)

            polls = query.order_by(Poll.created_at.desc()).all()

        except Exception as e:
            logger.error(
                f"Database error in realtime polls for user {current_user.id}: {e}")
            return ""  # Return empty for real-time updates on error

        # Process polls with individual error handling (same as get_polls_htmx)
        processed_polls = []
        for poll in polls:
            try:
                # Add status_class to each poll for template
                poll.status_class = {
                    'active': 'bg-success',
                    'scheduled': 'bg-warning',
                    'closed': 'bg-danger'
                }.get(TypeSafeColumn.get_string(poll, 'status'), 'bg-secondary')

                processed_polls.append(poll)

            except Exception as e:
                logger.error(
                    f"Error processing poll {TypeSafeColumn.get_int(poll, 'id', 0)} for realtime: {e}")
                # Continue with other polls, skip this one

        # Get user's timezone preference with error handling
        try:
            user_prefs = get_user_preferences(current_user.id)
            user_timezone = user_prefs.get("default_timezone", "US/Eastern")
        except Exception as e:
            logger.error(
                f"Error getting user preferences for {current_user.id}: {e}")
            user_timezone = "US/Eastern"

        # Use the dedicated poll cards content component for real-time updates
        return templates.TemplateResponse("htmx/components/poll_cards_content.html", {
            "request": request,
            "polls": processed_polls,
            "current_filter": filter,
            "user_timezone": user_timezone,
            "format_datetime_for_user": format_datetime_for_user
        })

    except Exception as e:
        logger.error(
            f"Critical error in realtime polls for user {current_user.id}: {e}")
        return ""  # Return empty on error for real-time updates
    finally:
        try:
            db.close()
        except Exception as e:
            logger.error(f"Error closing database connection in realtime: {e}")


async def get_guild_emojis_htmx(server_id: str, bot, current_user: DiscordUser = Depends(require_auth)):
    """Get custom emojis for a guild as JSON for HTMX"""
    try:
        if not server_id:
            return {"emojis": []}

        # Create emoji handler
        emoji_handler = DiscordEmojiHandler(bot)

        # Get guild emojis
        emoji_list = await emoji_handler.get_guild_emoji_list(int(server_id))

        return {"emojis": emoji_list}

    except Exception as e:
        logger.error(f"Error getting guild emojis for server {server_id}: {e}")
        return {"emojis": [], "error": str(e)}


async def create_poll_htmx(request: Request, bot, scheduler, current_user: DiscordUser = Depends(require_auth)):
    """Create a new poll via HTMX using bulletproof operations with Discord native emoji handling"""
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

        # Create Discord emoji handler
        emoji_handler = DiscordEmojiHandler(bot)

        # Get options and emojis using Discord native processing
        options = []
        emoji_inputs = []
        print(
            f"🔍 POLL CREATION DEBUG - Processing poll options for user {current_user.id}")
        logger.info(
            f"🔍 POLL CREATION DEBUG - Processing poll options for user {current_user.id}")

        for i in range(1, 11):
            option = form_data.get(f"option{i}")
            if option:
                option_text = str(option).strip()
                options.append(option_text)
                # Extract emoji from form data
                emoji_input = safe_get_form_data(form_data, f"emoji{i}")
                emoji_inputs.append(emoji_input)
                print(
                    f"🔍 POLL CREATION DEBUG - Option {i}: '{option_text}' with emoji input '{emoji_input}'")
                logger.info(
                    f"🔍 POLL CREATION DEBUG - Option {i}: '{option_text}' with emoji input '{emoji_input}'")

        # Process all emojis using Discord native handler
        emojis = await emoji_handler.process_poll_emojis(emoji_inputs, int(server_id) if server_id else 0)

        print(f"📊 POLL CREATION DEBUG - Final options: {options}")
        print(f"😀 POLL CREATION DEBUG - Final emojis: {emojis}")
        logger.info(f"📊 POLL CREATION DEBUG - Final options: {options}")
        logger.info(f" POLL CREATION DEBUG - Final emojis: {emojis}")

        if len(options) < 2:
            logger.warning(f"Insufficient options provided: {len(options)}")
            return templates.TemplateResponse("htmx/components/alert_error.html", {
                "request": request,
                "message": "At least 2 options required"
            })

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
            return templates.TemplateResponse("htmx/components/alert_error.html", {
                "request": request,
                "message": f"Poll open time must be scheduled for the next minute or later. Try {suggested_time} or later."
            })

        if close_dt <= open_dt:
            return templates.TemplateResponse("htmx/components/alert_error.html", {
                "request": request,
                "message": "Close time must be after open time"
            })

        # Prepare poll data for bulletproof operations
        poll_data = {
            "name": name,
            "question": question,
            "options": options,
            "emojis": emojis,
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
                # Ensure image_file has read method before calling it
                if callable(getattr(image_file, 'read', None)):
                    image_file_data = await image_file.read()
                    image_filename = str(getattr(image_file, 'filename', ''))
                else:
                    logger.warning(
                        "Image file object does not have a callable read method")
                    image_file_data = None
                    image_filename = None
            except Exception as e:
                logger.error(f"Error reading image file: {e}")
                return templates.TemplateResponse("htmx/components/alert_error.html", {
                    "request": request,
                    "message": "Error reading image file"
                })

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
            return templates.TemplateResponse("htmx/components/alert_error.html", {
                "request": request,
                "message": error_msg
            })

        poll_id = result["poll_id"]
        logger.info(f"Created poll {poll_id} for user {current_user.id}")

        # Schedule poll opening and closing using timezone-aware scheduler
        try:
            from .discord_utils import post_poll_to_channel
            from .background_tasks import close_poll

            # Use the timezone-aware scheduler wrapper
            tz_scheduler = TimezoneAwareScheduler(scheduler)

            # Schedule poll to open at the specified time
            success_open = tz_scheduler.schedule_poll_opening(
                poll_id, open_dt, timezone_str, post_poll_to_channel, bot
            )
            if not success_open:
                logger.error(f"Failed to schedule poll {poll_id} opening")
                await PollErrorHandler.handle_scheduler_error(
                    Exception(
                        "Failed to schedule poll opening"), poll_id, "poll_opening", bot
                )

            # Schedule poll to close
            success_close = tz_scheduler.schedule_poll_closing(
                poll_id, close_dt, timezone_str, close_poll
            )
            if not success_close:
                logger.error(f"Failed to schedule poll {poll_id} closing")
                await PollErrorHandler.handle_scheduler_error(
                    Exception(
                        "Failed to schedule poll closing"), poll_id, "poll_closure", bot
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
        return templates.TemplateResponse("htmx/components/alert_success.html", {
            "request": request,
            "message": "Poll created successfully! Redirecting to polls...",
            "redirect_url": "/htmx/polls"
        })

    except Exception as e:
        logger.error(f"Error creating poll for user {current_user.id}: {e}")
        logger.exception("Full traceback for poll creation error:")

        # Use error handler for comprehensive error handling
        poll_name = locals().get('name', 'Unknown')
        error_msg = await PollErrorHandler.handle_poll_creation_error(
            e, {"name": poll_name, "user_id": current_user.id}, bot
        )
        return templates.TemplateResponse("htmx/components/alert_error.html", {
            "request": request,
            "message": error_msg
        })


async def get_poll_details_htmx(poll_id: int, request: Request, current_user: DiscordUser = Depends(require_auth)):
    """Get poll details view as HTML for HTMX"""
    logger.info(
        f"User {current_user.id} requesting details for poll {poll_id}")
    db = get_db_session()
    try:
        poll = db.query(Poll).filter(Poll.id == poll_id,
                                     Poll.creator_id == current_user.id).first()
        if not poll:
            logger.warning(
                f"Poll {poll_id} not found or not owned by user {current_user.id}")
            return templates.TemplateResponse("htmx/components/alert_error.html", {
                "request": request,
                "message": "Poll not found or access denied"
            })

        return templates.TemplateResponse("htmx/poll_details.html", {
            "request": request,
            "poll": poll,
            "format_datetime_for_user": format_datetime_for_user
        })
    except Exception as e:
        logger.error(f"Error getting poll details for poll {poll_id}: {e}")
        from .error_handler import notify_error_async
        await notify_error_async(e, "Poll Details Retrieval", poll_id=poll_id, user_id=current_user.id)
        return templates.TemplateResponse("htmx/components/alert_error.html", {
            "request": request,
            "message": f"Error loading poll details: {str(e)}"
        })
    finally:
        db.close()


async def get_poll_results_realtime_htmx(poll_id: int, request: Request, current_user: DiscordUser = Depends(require_auth)):
    """Get real-time poll results as HTML for HTMX"""
    db = get_db_session()
    try:
        poll = db.query(Poll).filter(Poll.id == poll_id,
                                     Poll.creator_id == current_user.id).first()
        if not poll:
            return '<div class="alert alert-danger">Poll not found or access denied</div>'

        # Get poll results
        total_votes = poll.get_total_votes()
        results = poll.get_results()

        # Get poll data safely
        options = poll.options  # Use the property method from Poll model
        emojis = poll.emojis    # Use the property method from Poll model
        is_anonymous = TypeSafeColumn.get_bool(poll, 'anonymous', False)

        # Generate HTML for results
        html_parts = []

        for i in range(len(options)):
            option_votes = results.get(i, 0)
            percentage = (option_votes / total_votes *
                          100) if total_votes > 0 else 0
            emoji = emojis[i] if i < len(emojis) else "🇦"
            option_text = options[i]

            html_parts.append(f'''
            <div class="mb-3">
                <div class="d-flex justify-content-between align-items-center mb-1">
                    <span>{emoji} {escape(option_text)}</span>
                    <span class="text-muted">{option_votes} votes ({percentage:.1f}%)</span>
                </div>
                <div class="progress" style="height: 20px;">
                    <div class="progress-bar" role="progressbar" style="width: {percentage}%;" 
                         aria-valuenow="{percentage}" aria-valuemin="0" aria-valuemax="100">
                    </div>
                </div>
            </div>
            ''')

        # Add total votes and anonymous badge
        anonymous_badge = '<span class="badge bg-info ms-2">Anonymous</span>' if is_anonymous else ""
        html_parts.append(f'''
        <div class="mt-3">
            <strong>Total Votes: {total_votes}</strong>
            {anonymous_badge}
        </div>
        ''')

        return ''.join(html_parts)

    except Exception as e:
        logger.error(
            f"Error getting real-time results for poll {poll_id}: {e}")
        return '<div class="alert alert-danger">Error loading poll results</div>'
    finally:
        db.close()


async def close_poll_htmx(poll_id: int, request: Request, current_user: DiscordUser = Depends(require_auth)):
    """Close an active poll via HTMX"""
    logger.info(f"User {current_user.id} requesting to close poll {poll_id}")
    db = get_db_session()
    try:
        poll = db.query(Poll).filter(Poll.id == poll_id,
                                     Poll.creator_id == current_user.id).first()
        if not poll:
            return templates.TemplateResponse("htmx/components/alert_error.html", {
                "request": request,
                "message": "Poll not found or access denied"
            })

        if TypeSafeColumn.get_string(poll, 'status') != "active":
            return templates.TemplateResponse("htmx/components/alert_error.html", {
                "request": request,
                "message": "Only active polls can be closed"
            })

        # Update poll status to closed
        setattr(poll, 'status', 'closed')
        setattr(poll, 'updated_at', datetime.now(pytz.UTC))
        db.commit()

        logger.info(f"Poll {poll_id} closed by user {current_user.id}")

        return templates.TemplateResponse("htmx/components/alert_success.html", {
            "request": request,
            "message": "Poll closed successfully! Redirecting to polls...",
            "redirect_url": "/htmx/polls"
        })

    except Exception as e:
        logger.error(f"Error closing poll {poll_id}: {e}")
        from .error_handler import notify_error_async
        await notify_error_async(e, "Poll Closure", poll_id=poll_id, user_id=current_user.id)
        db.rollback()
        return templates.TemplateResponse("htmx/components/alert_error.html", {
            "request": request,
            "message": f"Error closing poll: {str(e)}"
        })
    finally:
        db.close()


async def delete_poll_htmx(poll_id: int, request: Request, current_user: DiscordUser = Depends(require_auth)):
    """Delete a scheduled or closed poll via HTMX"""
    logger.info(f"User {current_user.id} requesting to delete poll {poll_id}")
    db = get_db_session()
    try:
        poll = db.query(Poll).filter(Poll.id == poll_id,
                                     Poll.creator_id == current_user.id).first()
        if not poll:
            return templates.TemplateResponse("htmx/components/alert_error.html", {
                "request": request,
                "message": "Poll not found or access denied"
            })

        poll_status = TypeSafeColumn.get_string(poll, 'status')
        if poll_status not in ['scheduled', 'closed']:
            return templates.TemplateResponse("htmx/components/alert_error.html", {
                "request": request,
                "message": "Only scheduled or closed polls can be deleted"
            })

        # Clean up image file if exists
        image_path = TypeSafeColumn.get_string(poll, 'image_path')
        if image_path:
            await cleanup_image(image_path)

        # Delete associated votes first
        db.query(Vote).filter(Vote.poll_id == poll_id).delete()

        # Delete the poll
        db.delete(poll)
        db.commit()

        logger.info(f"Poll {poll_id} deleted by user {current_user.id}")

        return templates.TemplateResponse("htmx/components/alert_success.html", {
            "request": request,
            "message": "Poll deleted successfully! Redirecting to polls...",
            "redirect_url": "/htmx/polls"
        })

    except Exception as e:
        logger.error(f"Error deleting poll {poll_id}: {e}")
        from .error_handler import notify_error_async
        await notify_error_async(e, "Poll Deletion", poll_id=poll_id, user_id=current_user.id)
        db.rollback()
        return templates.TemplateResponse("htmx/components/alert_error.html", {
            "request": request,
            "message": f"Error deleting poll: {str(e)}"
        })
    finally:
        db.close()


async def get_poll_edit_form(poll_id: int, request: Request, bot, current_user: DiscordUser = Depends(require_auth)):
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
            return templates.TemplateResponse("htmx/components/alert_error.html", {
                "request": request,
                "message": "Poll not found or access denied"
            })

        if TypeSafeColumn.get_string(poll, 'status') != "scheduled":
            logger.warning(
                f"Attempt to edit non-scheduled poll {poll_id} (status: {TypeSafeColumn.get_string(poll, 'status')})")
            return templates.TemplateResponse("htmx/components/alert_error.html", {
                "request": request,
                "message": "Only scheduled polls can be edited"
            })

        # Get user's guilds with channels
        user_guilds = await get_user_guilds_with_channels(bot, current_user.id)

        # Get timezones - US/Eastern first as default
        common_timezones = [
            "US/Eastern", "UTC", "US/Central", "US/Mountain", "US/Pacific",
            "Europe/London", "Europe/Paris", "Europe/Berlin", "Asia/Tokyo", "Asia/Shanghai", "Australia/Sydney"
        ]

        # Convert times to local timezone for editing
        poll_timezone = TypeSafeColumn.get_string(poll, 'timezone', 'UTC')
        tz = pytz.timezone(poll_timezone)

        # Ensure the stored times have timezone info (they should be UTC)
        # Use TypeSafeColumn to get datetime values safely
        open_time_value = TypeSafeColumn.get_datetime(poll, 'open_time')
        close_time_value = TypeSafeColumn.get_datetime(poll, 'close_time')

        # Ensure we have valid datetime objects before processing
        if not isinstance(open_time_value, datetime) or not isinstance(close_time_value, datetime):
            logger.error(f"Invalid datetime values for poll {poll_id}")
            return templates.TemplateResponse("htmx/components/alert_error.html", {
                "request": request,
                "message": "Error processing poll times"
            })

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

        open_time = open_time_local.strftime('%Y-%m-%dT%H:%M')
        close_time = close_time_local.strftime('%Y-%m-%dT%H:%M')

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


async def update_poll_htmx(poll_id: int, request: Request, bot, scheduler, current_user: DiscordUser = Depends(require_auth)):
    """Update a scheduled poll"""
    logger.info(f"User {current_user.id} updating poll {poll_id}")
    db = get_db_session()
    try:
        poll = db.query(Poll).filter(Poll.id == poll_id,
                                     Poll.creator_id == current_user.id).first()
        if not poll:
            logger.warning(
                f"Poll {poll_id} not found or not owned by user {current_user.id}")
            return templates.TemplateResponse("htmx/components/alert_error.html", {
                "request": request,
                "message": "Poll not found or access denied"
            })

        if TypeSafeColumn.get_string(poll, 'status') != "scheduled":
            logger.warning(
                f"Attempt to edit non-scheduled poll {poll_id} (status: {TypeSafeColumn.get_string(poll, 'status')})")
            return templates.TemplateResponse("htmx/components/alert_error.html", {
                "request": request,
                "message": "Only scheduled polls can be edited"
            })

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
        multiple_choice = form_data.get("multiple_choice") == "true"
        image_message_text = safe_get_form_data(
            form_data, "image_message_text", "")

        # Validate required fields
        if not all([name, question, server_id, channel_id, open_time, close_time]):
            logger.warning(
                f"Missing required fields for poll {poll_id} update")
            return templates.TemplateResponse("htmx/components/alert_error.html", {
                "request": request,
                "message": "All required fields must be filled"
            })

        # Handle image upload
        image_file = form_data.get("image")
        is_valid, error_msg, content = await validate_image_file(image_file)

        if not is_valid:
            logger.warning(
                f"Image validation failed for poll {poll_id}: {error_msg}")
            return templates.TemplateResponse("htmx/components/alert_error.html", {
                "request": request,
                "message": error_msg
            })

        # Save new image if provided
        new_image_path = TypeSafeColumn.get_string(poll, 'image_path')
        if content and hasattr(image_file, 'filename') and getattr(image_file, 'filename', None):
            new_image_path = await save_image_file(content, str(getattr(image_file, 'filename', '')))
            if not new_image_path:
                logger.error(f"Failed to save new image for poll {poll_id}")
                return templates.TemplateResponse("htmx/components/alert_error.html", {
                    "request": request,
                    "message": "Failed to save image file"
                })
            # Clean up old image
            old_image_path = TypeSafeColumn.get_string(poll, 'image_path')
            if old_image_path:
                await cleanup_image(str(old_image_path))

        # Create Discord emoji handler
        emoji_handler = DiscordEmojiHandler(bot)

        # Get options and emojis using Discord native processing
        options = []
        emoji_inputs = []
        print(
            f"🔍 POLL EDIT DEBUG - Processing poll options for poll {poll_id} update by user {current_user.id}")
        logger.info(
            f"🔍 POLL EDIT DEBUG - Processing poll options for poll {poll_id} update by user {current_user.id}")

        for i in range(1, 11):
            option = form_data.get(f"option{i}")
            if option:
                option_text = str(option).strip()
                options.append(option_text)
                # Extract emoji from form data
                emoji_input = safe_get_form_data(form_data, f"emoji{i}")
                emoji_inputs.append(emoji_input)
                print(
                    f"🔍 POLL EDIT DEBUG - Option {i}: '{option_text}' with emoji input '{emoji_input}'")
                logger.info(
                    f"🔍 POLL EDIT DEBUG - Option {i}: '{option_text}' with emoji input '{emoji_input}'")

        # Process all emojis using Discord native handler
        emojis = await emoji_handler.process_poll_emojis(emoji_inputs, int(server_id) if server_id else 0)

        print(f"📊 POLL EDIT DEBUG - Final options: {options}")
        print(f"😀 POLL EDIT DEBUG - Final emojis: {emojis}")
        logger.info(f"📊 POLL EDIT DEBUG - Final options: {options}")
        logger.info(f"😀 POLL EDIT DEBUG - Final emojis: {emojis}")

        if len(options) < 2:
            logger.warning(
                f"Insufficient options for poll {poll_id}: {len(options)}")
            return templates.TemplateResponse("htmx/components/alert_error.html", {
                "request": request,
                "message": "At least 2 options required"
            })

        # Parse times with timezone using safe parsing
        open_dt = safe_parse_datetime_with_timezone(open_time, timezone_str)
        close_dt = safe_parse_datetime_with_timezone(close_time, timezone_str)

        # Normalize timezone for storage
        timezone_str = validate_and_normalize_timezone(timezone_str)

        # Validate times
        now = datetime.now(pytz.UTC)
        next_minute = now.replace(
            second=0, microsecond=0) + timedelta(minutes=1)

        if open_dt < next_minute:
            # Convert next_minute to user's timezone for display
            user_tz = pytz.timezone(timezone_str)
            next_minute_local = next_minute.astimezone(user_tz)
            suggested_time = next_minute_local.strftime('%I:%M %p')

            logger.warning(
                f"Attempt to schedule poll in the past: {open_dt} < {next_minute}")
            return templates.TemplateResponse("htmx/components/alert_error.html", {
                "request": request,
                "message": f"Poll open time must be scheduled for the next minute or later. Try {suggested_time} or later."
            })

        if close_dt <= open_dt:
            logger.warning(
                f"Invalid time range for poll {poll_id}: open={open_dt}, close={close_dt}")
            return templates.TemplateResponse("htmx/components/alert_error.html", {
                "request": request,
                "message": "Close time must be after open time"
            })

        # Get server and channel names
        guild = bot.get_guild(int(server_id))
        channel = bot.get_channel(int(channel_id))

        if not guild or not channel:
            logger.error(
                f"Invalid guild or channel for poll {poll_id}: guild={guild}, channel={channel}")
            return templates.TemplateResponse("htmx/components/alert_error.html", {
                "request": request,
                "message": "Invalid server or channel"
            })

        # Update poll using setattr to avoid SQLAlchemy Column type issues
        setattr(poll, 'name', name)
        setattr(poll, 'question', question)
        poll.options = options
        poll.emojis = emojis
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
        setattr(poll, 'multiple_choice', multiple_choice)

        db.commit()

        # Update scheduled jobs
        try:
            scheduler.remove_job(f"open_poll_{poll_id}")
        except Exception as e:
            logger.debug(
                f"Job open_poll_{poll_id} not found or already removed: {e}")
        try:
            scheduler.remove_job(f"close_poll_{poll_id}")
        except Exception as e:
            logger.debug(
                f"Job close_poll_{poll_id} not found or already removed: {e}")

        # Reschedule jobs
        from .discord_utils import post_poll_to_channel
        from .background_tasks import close_poll

        if open_dt > datetime.now(pytz.UTC):
            scheduler.add_job(
                post_poll_to_channel,
                DateTrigger(run_date=open_dt),
                args=[bot, poll_id],
                id=f"open_poll_{poll_id}"
            )

        scheduler.add_job(
            close_poll,
            DateTrigger(run_date=close_dt),
            args=[poll_id],
            id=f"close_poll_{poll_id}"
        )

        logger.info(f"Successfully updated poll {poll_id}")

        return templates.TemplateResponse("htmx/components/alert_success.html", {
            "request": request,
            "message": "Poll updated successfully! Redirecting to polls...",
            "redirect_url": "/htmx/polls"
        })

    except Exception as e:
        logger.error(f"Error updating poll {poll_id}: {e}")
        from .error_handler import notify_error_async
        await notify_error_async(e, "Poll Update", poll_id=poll_id, user_id=current_user.id)
        db.rollback()
        return templates.TemplateResponse("htmx/components/alert_error.html", {
            "request": request,
            "message": f"Error updating poll: {str(e)}"
        })
    finally:
        db.close()
