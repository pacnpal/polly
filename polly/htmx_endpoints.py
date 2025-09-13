"""
HTMX Endpoints Module
Handles all HTMX-related endpoints for dynamic web content without JavaScript.
"""

from datetime import datetime, timedelta
from html import escape
import pytz
import uuid
import aiofiles
import os

from fastapi import Request, Depends
from fastapi.templating import Jinja2Templates
from apscheduler.triggers.date import DateTrigger

try:
    from .auth import require_auth, DiscordUser
    from .database import (
        get_db_session,
        Poll,
        Vote,
        UserPreference,
        TypeSafeColumn,
        POLL_EMOJIS,
    )
    from .discord_utils import get_user_guilds_with_channels
    from .poll_operations import BulletproofPollOperations
    from .error_handler import PollErrorHandler
    from .timezone_scheduler_fix import TimezoneAwareScheduler
    from .discord_emoji_handler import DiscordEmojiHandler
    from .emoji_pipeline_fix import get_unified_emoji_processor
    from .json_import import PollJSONImporter, PollJSONExporter
    from .debug_config import get_debug_logger
    from .data_utils import sanitize_data_for_json
except ImportError:
    from auth import require_auth, DiscordUser  # type: ignore
    from database import (  # type: ignore
        get_db_session,
        Poll,
        Vote,
        UserPreference,
        TypeSafeColumn,
        POLL_EMOJIS,
    )
    from discord_utils import get_user_guilds_with_channels  # type: ignore
    from poll_operations import BulletproofPollOperations  # type: ignore
    from error_handler import PollErrorHandler  # type: ignore
    from timezone_scheduler_fix import TimezoneAwareScheduler  # type: ignore
    from discord_emoji_handler import DiscordEmojiHandler  # type: ignore
    from emoji_pipeline_fix import get_unified_emoji_processor  # type: ignore
    from json_import import PollJSONImporter, PollJSONExporter  # type: ignore
    from debug_config import get_debug_logger  # type: ignore
    from data_utils import sanitize_data_for_json  # type: ignore

logger = get_debug_logger(__name__)

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

    import re

    # FALLBACK 1: Basic cleanup - remove extra whitespace and common issues
    cleaned_emoji = emoji_text.strip()

    # FALLBACK 2: Remove common text artifacts that might be mixed with emojis
    # Remove things like ":smile:" or "smile" if they're mixed with actual emojis
    emoji_pattern = re.compile(
        r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U0002600-\U0002B55\U0001F900-\U0001F9FF]+"
    )
    emoji_matches = emoji_pattern.findall(cleaned_emoji)

    if emoji_matches:
        # If we found actual emoji characters, use the first one
        cleaned_emoji = emoji_matches[0]
        print(
            f"🔧 EMOJI FALLBACK 2 - Extracted emoji '{cleaned_emoji}' from text '{emoji_text.strip()}'"
        )
        logger.info(
            f"🔧 EMOJI FALLBACK 2 - Extracted emoji '{cleaned_emoji}' from text '{emoji_text.strip()}'"
        )

    # FALLBACK 3: Handle common emoji shortcodes and convert them
    emoji_shortcodes = {
        "smile": "😀",
        "smiley": "😀",
        "grinning": "😀",
        "heart": "❤️",
        "love": "❤️",
        "thumbsup": "👍",
        "+1": "👍",
        "like": "👍",
        "thumbsdown": "👎",
        "-1": "👎",
        "dislike": "👎",
        "fire": "🔥",
        "flame": "🔥",
        "star": "⭐",
        "star2": "⭐",
        "check": "✅",
        "checkmark": "✅",
        "tick": "✅",
        "x": "❌",
        "cross": "❌",
        "no": "❌",
        "warning": "⚠️",
        "warn": "⚠️",
        "question": "❓",
        "?": "❓",
        "exclamation": "❗",
        "!": "❗",
        "pizza": "🍕",
        "burger": "🍔",
        "hamburger": "🍔",
        "beer": "🍺",
        "drink": "🍺",
        "coffee": "☕",
        "cake": "🎂",
        "party": "🎉",
        "celebration": "🎉",
        "music": "🎵",
        "musical_note": "🎵",
        "car": "🚗",
        "automobile": "🚗",
        "house": "🏠",
        "home": "🏠",
        "sun": "☀️",
        "sunny": "☀️",
        "moon": "🌙",
        "tree": "🌳",
        "flower": "🌸",
        "dog": "🐶",
        "puppy": "🐶",
        "cat": "🐱",
        "kitty": "🐱",
    }

    # Check if the cleaned text matches any shortcode
    lower_cleaned = cleaned_emoji.lower().strip(":")
    if lower_cleaned in emoji_shortcodes:
        emoji = emoji_shortcodes[lower_cleaned]
        print(
            f"🔧 EMOJI FALLBACK 3 - Converted shortcode '{cleaned_emoji}' to emoji '{emoji}'"
        )
        logger.info(
            f"🔧 EMOJI FALLBACK 3 - Converted shortcode '{cleaned_emoji}' to emoji '{emoji}'"
        )
        cleaned_emoji = emoji

    # FALLBACK 4: Try to extract single emoji character if mixed with text
    if len(cleaned_emoji) > 1:
        for char in cleaned_emoji:
            if _is_emoji_character(char):
                print(
                    f"🔧 EMOJI FALLBACK 4 - Extracted single emoji '{char}' from '{cleaned_emoji}'"
                )
                logger.info(
                    f"🔧 EMOJI FALLBACK 4 - Extracted single emoji '{char}' from '{cleaned_emoji}'"
                )
                cleaned_emoji = char
                break

    # FALLBACK 5: Final validation
    if _validate_emoji_strict(cleaned_emoji):
        return True, cleaned_emoji
    else:
        return (
            False,
            f"Could not process '{emoji_text.strip()}' into valid emoji after all fallback attempts",
        )


def _is_emoji_character(char: str) -> bool:
    """Check if a single character is an emoji"""
    import unicodedata

    category = unicodedata.category(char)
    return (
        category.startswith("So")  # Other symbols (most emojis)
        or category.startswith("Sm")  # Math symbols (some emojis)
        or category.startswith("Mn")  # Nonspacing marks (emoji modifiers)
        or category.startswith("Sk")  # Modifier symbols
        or ord(char) in range(0x1F000, 0x1FAFF)  # Emoji blocks
        or ord(char) in range(0x2600, 0x27BF)  # Miscellaneous symbols
        or ord(char) in range(0x1F300, 0x1F9FF)  # Emoji ranges
        or ord(char) in range(0x1F600, 0x1F64F)  # Emoticons
        or ord(char) in range(0x1F680, 0x1F6FF)  # Transport symbols
        or ord(char) in range(0x2700, 0x27BF)  # Dingbats
        or ord(char) in range(0xFE00, 0xFE0F)
    )  # Variation selectors


def _validate_emoji_strict(emoji_text: str) -> bool:
    """Strict validation for final emoji"""

    if not emoji_text or len(emoji_text) > 10:
        return False

    # Check if all characters are emoji-related
    for char in emoji_text:
        if not _is_emoji_character(char):
            return False

    # Additional check: try to encode/decode to ensure it's valid Unicode
    try:
        emoji_text.encode("utf-8").decode("utf-8")
    except UnicodeError:
        return False

    return True


def validate_emoji(emoji_text: str) -> tuple[bool, str]:
    """Legacy function for backward compatibility - now uses the enhanced processor"""
    return process_custom_emoji_with_fallbacks(emoji_text)


def validate_and_normalize_timezone(timezone_str: str) -> str:
    """Validate and normalize timezone string, handling EDT/EST issues"""
    if not timezone_str:
        return "US/Eastern"  # Default to Eastern instead of UTC

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
        "Pacific": "US/Pacific",
    }

    # Check if it's a mapped timezone
    if timezone_str in timezone_mapping:
        timezone_str = timezone_mapping[timezone_str]

    # Validate the timezone
    try:
        pytz.timezone(timezone_str)
        return timezone_str
    except pytz.UnknownTimeZoneError:
        logger.warning(f"Unknown timezone '{timezone_str}', defaulting to US/Eastern")
        return "US/Eastern"  # Default to Eastern instead of UTC
    except Exception as e:
        logger.error(f"Error validating timezone '{timezone_str}': {e}")
        return "US/Eastern"  # Default to Eastern instead of UTC


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
            f"Timezone parsing: '{datetime_str}' in '{timezone_str}' -> {localized_dt} -> {utc_dt}"
        )

        return utc_dt

    except Exception as e:
        logger.error(
            f"Error parsing datetime '{datetime_str}' with timezone '{timezone_str}': {e}"
        )
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
    """Enhanced image file validation with comprehensive logging"""
    try:
        logger.info(f"🔍 HTMX IMAGE VALIDATION - Starting validation for image_file: {type(image_file)}")
        
        if not image_file:
            logger.info("🔍 HTMX IMAGE VALIDATION - No image file provided (None)")
            return True, "", None
            
        if not hasattr(image_file, "filename"):
            logger.error("🔍 HTMX IMAGE VALIDATION - Image file has no filename attribute")
            return False, "Invalid image file format", None
            
        filename = getattr(image_file, "filename", None)
        if not filename:
            logger.info("🔍 HTMX IMAGE VALIDATION - Image file has empty filename")
            return True, "", None

        logger.info(f"🔍 HTMX IMAGE VALIDATION - Processing file: {filename}")

        # Read file content with error handling
        try:
            content = await image_file.read()
            logger.info(f"🔍 HTMX IMAGE VALIDATION - File content read: {len(content)} bytes")
        except Exception as read_error:
            logger.error(f"🔍 HTMX IMAGE VALIDATION - Error reading file content: {read_error}")
            return False, "Error reading image file", None

        # Validate file size (8MB limit)
        if len(content) > 8 * 1024 * 1024:
            logger.error(f"🔍 HTMX IMAGE VALIDATION - File too large: {len(content)} bytes")
            return False, "Image file too large (max 8MB)", None

        # Validate file type
        allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
        content_type = getattr(image_file, "content_type", None)
        
        if content_type and content_type not in allowed_types:
            logger.error(f"🔍 HTMX IMAGE VALIDATION - Invalid content type: {content_type}")
            return False, "Invalid image format (JPEG, PNG, GIF, WebP only)", None

        logger.info(f"🔍 HTMX IMAGE VALIDATION - ✅ Validation passed for {filename}")
        return True, "", content
        
    except Exception as e:
        logger.error(f"🔍 HTMX IMAGE VALIDATION - ❌ Critical error: {e}")
        return False, "Error processing image file", None


async def save_image_file(content: bytes, filename: str) -> str | None:
    """Save image file with proper error handling"""
    try:
        file_extension = filename.split(".")[-1].lower()
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


async def cleanup_image(image_path: str) -> bool:
    """Safely delete an image file"""
    try:
        if image_path and isinstance(image_path, str) and os.path.exists(image_path):
            os.remove(image_path)
            logger.info(f"Cleaned up image: {image_path}")
            return True
    except Exception as e:
        logger.error(f"Failed to cleanup image {image_path}: {e}")
    return False


def get_user_preferences(user_id: str) -> dict:
    """Get user preferences for poll creation"""
    db = get_db_session()
    try:
        prefs = (
            db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
        )
        if prefs:
            return {
                "last_server_id": TypeSafeColumn.get_string(prefs, "last_server_id", ""),
                "last_channel_id": TypeSafeColumn.get_string(prefs, "last_channel_id", ""),
                "last_role_id": TypeSafeColumn.get_string(prefs, "last_role_id", ""),
                "default_timezone": TypeSafeColumn.get_string(
                    prefs, "default_timezone", "US/Eastern"
                ),
                "timezone_explicitly_set": TypeSafeColumn.get_bool(
                    prefs, "timezone_explicitly_set", False
                ),
            }
        return {
            "last_server_id": None,
            "last_channel_id": None,
            "last_role_id": None,
            "default_timezone": "US/Eastern",
            "timezone_explicitly_set": False,
        }
    except Exception as e:
        logger.error(f"Error getting user preferences for {user_id}: {e}")
        return {
            "last_server_id": None,
            "last_channel_id": None,
            "last_role_id": None,
            "default_timezone": "US/Eastern",
            "timezone_explicitly_set": False,
        }
    finally:
        db.close()


async def close_poll_htmx(
    poll_id: int,
    request: Request,
    bot,
    current_user: DiscordUser = Depends(require_auth),
):
    """Close an active poll via HTMX using unified closure service for consistent behavior"""
    logger.info(f"User {current_user.id} requesting to close poll {poll_id}")
    
    try:
        # Use unified poll closure service for consistent behavior
        from .poll_closure_service import get_poll_closure_service
        
        poll_closure_service = get_poll_closure_service()
        
        result = await poll_closure_service.close_poll_unified(
            poll_id=poll_id,
            reason="manual",
            admin_user_id=current_user.id,
            bot_instance=bot
        )
        
        if result["success"]:
            logger.info(f"User {current_user.id} successfully manually closed poll {poll_id}")
            
            # Invalidate user polls cache after successful closure
            await invalidate_user_polls_cache(current_user.id)
            
            return templates.TemplateResponse(
                "htmx/components/alert_success.html",
                {
                    "request": request,
                    "message": "Poll closed successfully! Redirecting to polls...",
                    "redirect_url": "/htmx/polls",
                },
            )
        else:
            logger.error(f"User {current_user.id} manual close failed for poll {poll_id}: {result.get('error')}")
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {"request": request, "message": result.get("error", "Error closing poll")},
            )
            
    except Exception as e:
        logger.error(f"Error in manual poll closure for poll {poll_id}: {e}")
        return templates.TemplateResponse(
            "htmx/components/inline_error.html",
            {"request": request, "message": f"Error closing poll: {str(e)}"},
        )


async def open_poll_now_htmx(
    poll_id: int,
    request: Request,
    bot,
    scheduler,
    current_user: DiscordUser = Depends(require_auth),
):
    """Open a scheduled poll immediately via HTMX"""
    logger.info(f"User {current_user.id} requesting to open poll {poll_id} immediately")
    db = get_db_session()
    try:
        poll = (
            db.query(Poll)
            .filter(Poll.id == poll_id, Poll.creator_id == current_user.id)
            .first()
        )
        if not poll:
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {"request": request, "message": "Poll not found or access denied"},
            )

        if TypeSafeColumn.get_string(poll, "status") != "scheduled":
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {
                    "request": request,
                    "message": "Only scheduled polls can be opened immediately",
                },
            )

        # Update poll status to active and set open time to now
        setattr(poll, "status", "active")
        setattr(poll, "open_time", datetime.now(pytz.UTC))
        setattr(poll, "updated_at", datetime.now(pytz.UTC))
        db.commit()

        # Remove the scheduled opening job
        try:
            scheduler.remove_job(f"open_poll_{poll_id}")
            logger.info(f"Removed scheduled opening job for poll {poll_id}")
        except Exception as e:
            logger.debug(f"Job open_poll_{poll_id} not found or already removed: {e}")

        # Post the poll to Discord immediately using unified opening service
        try:
            from .poll_open_service import poll_opening_service
            
            result = await poll_opening_service.open_poll_unified(
                poll_id=poll_id,
                reason="immediate",
                admin_user_id=current_user.id,
                bot_instance=bot
            )
            
            if not result["success"]:
                logger.error(f"Unified poll opening failed for poll {poll_id}: {result.get('error')}")
                # Revert status change if opening failed
                setattr(poll, "status", "scheduled")
                db.commit()
                return templates.TemplateResponse(
                    "htmx/components/inline_error.html",
                    {"request": request, "message": result.get("error", "Error opening poll")},
                )
            
            logger.info(f"Poll {poll_id} opened immediately by user {current_user.id} via unified service")
        except Exception as e:
            logger.error(f"Error posting poll {poll_id} to Discord: {e}")
            # Revert status change if posting failed
            setattr(poll, "status", "scheduled")
            db.commit()
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {"request": request, "message": "Error posting poll to Discord"},
            )

        return templates.TemplateResponse(
            "htmx/components/alert_success.html",
            {
                "request": request,
                "message": "Poll opened successfully! Redirecting to polls...",
                "redirect_url": "/htmx/polls",
            },
        )

    except Exception as e:
        logger.error(f"Error opening poll {poll_id} immediately: {e}")
        db.rollback()
        return templates.TemplateResponse(
            "htmx/components/inline_error.html",
            {"request": request, "message": f"Error opening poll: {str(e)}"},
        )
    finally:
        db.close()


def get_priority_timezone_for_user(user_id: str) -> str:
    """Get timezone for new poll creation based on priority system:
    1. Last poll preference (highest priority)
    2. Fallback to explicit set timezone
    3. Fallback to eastern time (lowest priority)
    """
    db = get_db_session()
    try:
        # Priority 1: Get timezone from user's most recent poll
        last_poll = (
            db.query(Poll)
            .filter(Poll.creator_id == user_id)
            .order_by(Poll.created_at.desc())
            .first()
        )

        if last_poll:
            last_poll_timezone = TypeSafeColumn.get_string(last_poll, "timezone")
            if last_poll_timezone and last_poll_timezone.strip():
                logger.debug(
                    f"Using last poll timezone for user {user_id}: {last_poll_timezone}"
                )
                return validate_and_normalize_timezone(last_poll_timezone)

        # Priority 2: Get explicitly set timezone from user preferences
        prefs = (
            db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
        )

        if prefs:
            timezone_explicitly_set = TypeSafeColumn.get_bool(
                prefs, "timezone_explicitly_set", False
            )
            if timezone_explicitly_set:
                explicit_timezone = TypeSafeColumn.get_string(
                    prefs, "default_timezone", "US/Eastern"
                )
                logger.debug(
                    f"Using explicitly set timezone for user {user_id}: {explicit_timezone}"
                )
                return validate_and_normalize_timezone(explicit_timezone)

        # Priority 3: Fallback to US/Eastern
        logger.debug(f"Using fallback timezone for user {user_id}: US/Eastern")
        return "US/Eastern"

    except Exception as e:
        logger.error(f"Error getting priority timezone for user {user_id}: {e}")
        return "US/Eastern"
    finally:
        db.close()


def save_user_preferences(
    user_id: str,
    server_id: str = None,
    channel_id: str = None,
    role_id: str = None,
    timezone: str = None,
):
    """Save user preferences for poll creation"""
    db = get_db_session()
    try:
        prefs = (
            db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
        )

        if prefs:
            # Update existing preferences using setattr for SQLAlchemy compatibility
            if server_id:
                setattr(prefs, "last_server_id", server_id)
            if channel_id:
                setattr(prefs, "last_channel_id", channel_id)
            if role_id:
                setattr(prefs, "last_role_id", role_id)
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
                last_role_id=role_id,
                default_timezone=timezone or "US/Eastern",
                timezone_explicitly_set=bool(timezone),
            )
            db.add(prefs)

        db.commit()
        logger.debug(
            f"Saved preferences for user {user_id}: server={server_id}, channel={channel_id}, role={role_id}, timezone={timezone}"
        )
    except Exception as e:
        logger.error(f"Error saving user preferences for {user_id}: {e}")
        db.rollback()
    finally:
        db.close()


def format_datetime_for_user(dt, user_timezone: str) -> str:
    """Format datetime in user's timezone for display"""
    try:
        # Handle string datetime values (from cache or other sources)
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            except (ValueError, AttributeError) as e:
                logger.warning(f"Error parsing datetime string {dt}: {e}")
                return "Unknown time"

        # Handle None values
        if dt is None:
            return "Unknown time"

        # Ensure we have a datetime object
        if not isinstance(dt, datetime):
            logger.warning(f"Invalid datetime type {type(dt)}: {dt}")
            return "Unknown time"

        if dt.tzinfo is None:
            # Assume UTC if no timezone info
            dt = pytz.UTC.localize(dt)

        # Convert to user's timezone
        user_tz = pytz.timezone(validate_and_normalize_timezone(user_timezone))
        local_dt = dt.astimezone(user_tz)

        return local_dt.strftime("%b %d, %I:%M %p")
    except Exception as e:
        logger.error(
            f"Error formatting datetime {dt} for timezone {user_timezone}: {e}"
        )
        # Fallback - try to return something useful
        try:
            if isinstance(dt, datetime):
                return dt.strftime("%b %d, %I:%M %p UTC")
            else:
                return str(dt) if dt else "Unknown time"
        except Exception:
            return "Unknown time"


def get_common_timezones() -> list:
    """Get comprehensive list of timezones with display names"""
    common_timezones = [
        # North America
        "US/Eastern",
        "US/Central",
        "US/Mountain",
        "US/Pacific",
        "US/Alaska",
        "US/Hawaii",
        "America/New_York",
        "America/Chicago",
        "America/Denver",
        "America/Los_Angeles",
        "America/Anchorage",
        "America/Honolulu",
        "America/Toronto",
        "America/Vancouver",
        "America/Mexico_City",
        "America/Sao_Paulo",
        "America/Argentina/Buenos_Aires",
        # Europe
        "UTC",
        "Europe/London",
        "Europe/Paris",
        "Europe/Berlin",
        "Europe/Rome",
        "Europe/Madrid",
        "Europe/Amsterdam",
        "Europe/Brussels",
        "Europe/Vienna",
        "Europe/Prague",
        "Europe/Warsaw",
        "Europe/Stockholm",
        "Europe/Helsinki",
        "Europe/Oslo",
        "Europe/Copenhagen",
        "Europe/Zurich",
        "Europe/Athens",
        "Europe/Istanbul",
        "Europe/Moscow",
        # Asia Pacific
        "Asia/Tokyo",
        "Asia/Seoul",
        "Asia/Shanghai",
        "Asia/Hong_Kong",
        "Asia/Singapore",
        "Asia/Bangkok",
        "Asia/Jakarta",
        "Asia/Manila",
        "Asia/Kuala_Lumpur",
        "Asia/Mumbai",
        "Asia/Kolkata",
        "Asia/Dubai",
        "Asia/Tehran",
        "Asia/Jerusalem",
        "Australia/Sydney",
        "Australia/Melbourne",
        "Australia/Perth",
        "Australia/Brisbane",
        "Pacific/Auckland",
        "Pacific/Fiji",
        "Pacific/Honolulu",
        # Africa
        "Africa/Cairo",
        "Africa/Johannesburg",
        "Africa/Lagos",
        "Africa/Nairobi",
        "Africa/Casablanca",
        "Africa/Tunis",
        "Africa/Algiers",
        # South America
        "America/Lima",
        "America/Bogota",
        "America/Santiago",
        "America/Caracas",
        # Other - Remove ambiguous timezone abbreviations that cause errors
        "GMT",
    ]

    timezones = []
    for tz_name in common_timezones:
        try:
            # Validate timezone exists first
            tz_obj = pytz.timezone(tz_name)

            # Get current offset safely
            try:
                current_time = datetime.now(tz_obj)
                offset = current_time.strftime("%z")

                # Format offset nicely
                if offset and len(offset) >= 5:
                    offset_formatted = f"UTC{offset[:3]}:{offset[3:]}"
                else:
                    offset_formatted = "UTC+00:00"
            except Exception as offset_error:
                logger.debug(
                    f"Could not get offset for timezone {tz_name}: {offset_error}"
                )
                offset_formatted = "UTC"

            # Create a more readable display name
            display_name = tz_name.replace("_", " ").replace("/", " / ")
            timezones.append(
                {"name": tz_name, "display": f"{display_name} ({offset_formatted})"}
            )

        except pytz.UnknownTimeZoneError:
            logger.debug(f"Unknown timezone skipped: {tz_name}")
            # Skip unknown timezones instead of adding them with errors
            continue
        except Exception as e:
            logger.debug(f"Error processing timezone {tz_name}: {e}")
            # Fallback: add timezone with just its name
            timezones.append({"name": tz_name, "display": tz_name})

    # Sort by display name for better UX
    timezones.sort(key=lambda x: x["display"])
    return timezones


async def import_json_htmx(
    request: Request, bot, current_user: DiscordUser = Depends(require_auth)
):
    """Import poll data from JSON file via HTMX"""
    logger.info(
        f"🔍 JSON IMPORT BACKEND - STEP 1: User {current_user.id} starting JSON import process"
    )
    print(
        f"🔍 JSON IMPORT BACKEND - STEP 1: User {current_user.id} starting JSON import process"
    )

    try:
        # Log request details
        logger.info(
            f"🔍 JSON IMPORT BACKEND - STEP 1: Request method: {request.method}"
        )
        logger.info(f"🔍 JSON IMPORT BACKEND - STEP 1: Request URL: {request.url}")
        logger.info(
            f"🔍 JSON IMPORT BACKEND - STEP 1: Request headers: {dict(request.headers)}"
        )
        print(f"🔍 JSON IMPORT BACKEND - STEP 1: Request method: {request.method}")
        print(f"🔍 JSON IMPORT BACKEND - STEP 1: Request URL: {request.url}")
        print(
            f"🔍 JSON IMPORT BACKEND - STEP 1: Content-Type: {request.headers.get('content-type', 'Not set')}"
        )

        # Try to get form data with better error handling
        logger.info("🔍 JSON IMPORT BACKEND - STEP 2: Attempting to parse form data")
        print("🔍 JSON IMPORT BACKEND - STEP 2: Attempting to parse form data")

        try:
            form_data = await request.form()
            logger.info(
                "🔍 JSON IMPORT BACKEND - STEP 2: Form data parsed successfully"
            )
            print("🔍 JSON IMPORT BACKEND - STEP 2: Form data parsed successfully")
        except Exception as form_error:
            logger.error(
                f"❌ JSON IMPORT BACKEND - STEP 2: User {current_user.id} form parsing error: {form_error}"
            )
            logger.error(
                f"❌ JSON IMPORT BACKEND - STEP 2: Form error type: {type(form_error)}"
            )
            logger.error(
                f"❌ JSON IMPORT BACKEND - STEP 2: Form error args: {form_error.args}"
            )
            print(
                f"❌ JSON IMPORT BACKEND - STEP 2: User {current_user.id} form parsing error: {form_error}"
            )
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {
                    "request": request,
                    "message": "Error parsing form data. Please try again.",
                },
            )

        # Debug: Log all form data keys to see what's actually being sent
        form_keys = list(form_data.keys())
        logger.info(
            f"🔍 JSON IMPORT BACKEND - STEP 3: User {current_user.id} form data keys: {form_keys}"
        )
        logger.info(
            f"🔍 JSON IMPORT BACKEND - STEP 3: Form data keys count: {len(form_keys)}"
        )
        print(
            f"🔍 JSON IMPORT BACKEND - STEP 3: User {current_user.id} form data keys: {form_keys}"
        )
        print(
            f"🔍 JSON IMPORT BACKEND - STEP 3: Form data keys count: {len(form_keys)}"
        )

        # Log form data values for debugging
        logger.info("🔍 JSON IMPORT BACKEND - STEP 3: Detailed form data analysis:")
        print("🔍 JSON IMPORT BACKEND - STEP 3: Detailed form data analysis:")
        for key, value in form_data.items():
            value_info = f"Type: {type(value)}"
            if hasattr(value, "filename"):
                value_info += f", Filename: {getattr(value, 'filename', 'None')}"
            if hasattr(value, "content_type"):
                value_info += (
                    f", Content-Type: {getattr(value, 'content_type', 'None')}"
                )
            if hasattr(value, "size"):
                value_info += f", Size: {getattr(value, 'size', 'Unknown')}"
            elif isinstance(value, str):
                value_info += (
                    f", Value: {value[:100]}{'...' if len(value) > 100 else ''}"
                )

            logger.info(f"🔍 JSON IMPORT BACKEND - STEP 3: {key}: {value_info}")
            print(f"🔍 JSON IMPORT BACKEND - STEP 3: {key}: {value_info}")

        logger.info(
            "🔍 JSON IMPORT BACKEND - STEP 4: Extracting json_file from form data"
        )
        print("🔍 JSON IMPORT BACKEND - STEP 4: Extracting json_file from form data")
        json_file = form_data.get("json_file")

        # Debug: Log the type and attributes of the json_file object
        logger.info(
            f"🔍 JSON IMPORT BACKEND - STEP 4: json_file type: {type(json_file)}"
        )
        logger.info(
            f"🔍 JSON IMPORT BACKEND - STEP 4: json_file is None: {json_file is None}"
        )
        print(f"🔍 JSON IMPORT BACKEND - STEP 4: json_file type: {type(json_file)}")
        print(
            f"🔍 JSON IMPORT BACKEND - STEP 4: json_file is None: {json_file is None}"
        )

        if json_file:
            logger.info(
                "🔍 JSON IMPORT BACKEND - STEP 4: json_file exists, analyzing attributes"
            )
            print(
                "🔍 JSON IMPORT BACKEND - STEP 4: json_file exists, analyzing attributes"
            )

            # Get all attributes (excluding private ones)
            json_file_attrs = [
                attr for attr in dir(json_file) if not attr.startswith("_")
            ]
            logger.info(
                f"🔍 JSON IMPORT BACKEND - STEP 4: json_file attributes: {json_file_attrs}"
            )
            print(
                f"🔍 JSON IMPORT BACKEND - STEP 4: json_file attributes: {json_file_attrs}"
            )

            # Log specific important attributes
            for attr in ["filename", "content_type", "size", "read", "file"]:
                if hasattr(json_file, attr):
                    attr_value = getattr(json_file, attr)
                    logger.info(
                        f"🔍 JSON IMPORT BACKEND - STEP 4: json_file.{attr}: {attr_value} (type: {type(attr_value)})"
                    )
                    print(
                        f"🔍 JSON IMPORT BACKEND - STEP 4: json_file.{attr}: {attr_value} (type: {type(attr_value)})"
                    )
                else:
                    logger.info(
                        f"🔍 JSON IMPORT BACKEND - STEP 4: json_file.{attr}: NOT FOUND"
                    )
                    print(
                        f"🔍 JSON IMPORT BACKEND - STEP 4: json_file.{attr}: NOT FOUND"
                    )

        # Enhanced file detection - check for file object and content
        logger.info("🔍 JSON IMPORT BACKEND - STEP 5: Validating json_file object")
        print("🔍 JSON IMPORT BACKEND - STEP 5: Validating json_file object")

        if not json_file:
            logger.warning(
                f"⚠️ JSON IMPORT BACKEND - STEP 5: User {current_user.id} attempted import without selecting file"
            )
            print(
                f"⚠️ JSON IMPORT BACKEND - STEP 5: User {current_user.id} attempted import without selecting file"
            )
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {"request": request, "message": "Please select a JSON file to import"},
            )

        logger.info(
            "🔍 JSON IMPORT BACKEND - STEP 5: json_file object exists, checking type"
        )
        print("🔍 JSON IMPORT BACKEND - STEP 5: json_file object exists, checking type")

        # Check if it's a proper file upload object (Starlette UploadFile)
        from starlette.datastructures import UploadFile

        logger.info(
            "🔍 JSON IMPORT BACKEND - STEP 5: Checking if json_file is UploadFile instance"
        )
        print(
            "🔍 JSON IMPORT BACKEND - STEP 5: Checking if json_file is UploadFile instance"
        )

        if not isinstance(json_file, UploadFile):
            logger.warning(
                f"⚠️ JSON IMPORT BACKEND - STEP 5: User {current_user.id} json_file is not an UploadFile: {type(json_file)}"
            )
            print(
                f"⚠️ JSON IMPORT BACKEND - STEP 5: User {current_user.id} json_file is not an UploadFile: {type(json_file)}"
            )
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {
                    "request": request,
                    "message": "Invalid file upload format. Please try selecting the file again.",
                },
            )

        logger.info(
            "🔍 JSON IMPORT BACKEND - STEP 5: json_file is valid UploadFile, extracting filename"
        )
        print(
            "🔍 JSON IMPORT BACKEND - STEP 5: json_file is valid UploadFile, extracting filename"
        )

        # Get filename - handle cases where filename might be None or empty
        filename = getattr(json_file, "filename", None)
        logger.info(
            f"🔍 JSON IMPORT BACKEND - STEP 5: Raw filename: {filename} (type: {type(filename)})"
        )
        print(
            f"🔍 JSON IMPORT BACKEND - STEP 5: Raw filename: {filename} (type: {type(filename)})"
        )

        if not filename or not filename.strip():
            logger.warning(
                f"⚠️ JSON IMPORT BACKEND - STEP 5: User {current_user.id} uploaded file with no filename"
            )
            print(
                f"⚠️ JSON IMPORT BACKEND - STEP 5: User {current_user.id} uploaded file with no filename"
            )
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {
                    "request": request,
                    "message": "Please select a valid JSON file with a filename",
                },
            )

        filename = str(filename).strip()
        logger.info(
            f"🔍 JSON IMPORT BACKEND - STEP 5: Processed filename: '{filename}'"
        )
        print(f"🔍 JSON IMPORT BACKEND - STEP 5: Processed filename: '{filename}'")

        # Validate file type
        logger.info("🔍 JSON IMPORT BACKEND - STEP 6: Validating file type")
        print("🔍 JSON IMPORT BACKEND - STEP 6: Validating file type")

        filename_lower = filename.lower()
        is_json_extension = filename_lower.endswith(".json")
        logger.info(
            f"🔍 JSON IMPORT BACKEND - STEP 6: Filename (lowercase): '{filename_lower}'"
        )
        logger.info(
            f"🔍 JSON IMPORT BACKEND - STEP 6: Has .json extension: {is_json_extension}"
        )
        print(
            f"🔍 JSON IMPORT BACKEND - STEP 6: Filename (lowercase): '{filename_lower}'"
        )
        print(
            f"🔍 JSON IMPORT BACKEND - STEP 6: Has .json extension: {is_json_extension}"
        )

        if not is_json_extension:
            logger.warning(
                f"⚠️ JSON IMPORT BACKEND - STEP 6: User {current_user.id} uploaded invalid file type: {filename}"
            )
            print(
                f"⚠️ JSON IMPORT BACKEND - STEP 6: User {current_user.id} uploaded invalid file type: {filename}"
            )
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {
                    "request": request,
                    "message": "Please upload a valid JSON file (.json extension required)",
                },
            )

        logger.info("🔍 JSON IMPORT BACKEND - STEP 6: File type validation PASSED")
        print("🔍 JSON IMPORT BACKEND - STEP 6: File type validation PASSED")

        # Check if file has content method
        logger.info("🔍 JSON IMPORT BACKEND - STEP 7: Checking file read capability")
        print("🔍 JSON IMPORT BACKEND - STEP 7: Checking file read capability")

        has_read_attr = hasattr(json_file, "read")
        read_attr = getattr(json_file, "read", None)
        is_read_callable = callable(read_attr)

        logger.info(
            f"🔍 JSON IMPORT BACKEND - STEP 7: Has 'read' attribute: {has_read_attr}"
        )
        logger.info(
            f"🔍 JSON IMPORT BACKEND - STEP 7: Read attribute type: {type(read_attr)}"
        )
        logger.info(
            f"🔍 JSON IMPORT BACKEND - STEP 7: Read attribute is callable: {is_read_callable}"
        )
        print(f"🔍 JSON IMPORT BACKEND - STEP 7: Has 'read' attribute: {has_read_attr}")
        print(
            f"🔍 JSON IMPORT BACKEND - STEP 7: Read attribute type: {type(read_attr)}"
        )
        print(
            f"🔍 JSON IMPORT BACKEND - STEP 7: Read attribute is callable: {is_read_callable}"
        )

        if not has_read_attr or not is_read_callable:
            logger.warning(
                f"⚠️ JSON IMPORT BACKEND - STEP 7: User {current_user.id} json_file does not have read method"
            )
            print(
                f"⚠️ JSON IMPORT BACKEND - STEP 7: User {current_user.id} json_file does not have read method"
            )
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {
                    "request": request,
                    "message": "Invalid file object. Please try selecting the file again.",
                },
            )

        logger.info(
            "🔍 JSON IMPORT BACKEND - STEP 7: File read capability validation PASSED"
        )
        print("🔍 JSON IMPORT BACKEND - STEP 7: File read capability validation PASSED")

        # Read file content with better error handling
        logger.info("🔍 JSON IMPORT BACKEND - STEP 8: Reading file content")
        print("🔍 JSON IMPORT BACKEND - STEP 8: Reading file content")

        try:
            logger.info("🔍 JSON IMPORT BACKEND - STEP 8: Calling json_file.read()")
            print("🔍 JSON IMPORT BACKEND - STEP 8: Calling json_file.read()")

            file_content = await json_file.read()
            file_size = len(file_content)

            logger.info(
                f"🔍 JSON IMPORT BACKEND - STEP 8: File read successfully: {file_size} bytes"
            )
            logger.info(
                f"🔍 JSON IMPORT BACKEND - STEP 8: Content type: {type(file_content)}"
            )
            print(
                f"🔍 JSON IMPORT BACKEND - STEP 8: File read successfully: {file_size} bytes"
            )
            print(
                f"🔍 JSON IMPORT BACKEND - STEP 8: Content type: {type(file_content)}"
            )

            # Log first 100 characters of content for debugging
            if isinstance(file_content, bytes):
                try:
                    content_preview = file_content.decode("utf-8")[:100]
                    logger.info(
                        f"🔍 JSON IMPORT BACKEND - STEP 8: Content preview (first 100 chars): {content_preview}"
                    )
                    print(
                        f"🔍 JSON IMPORT BACKEND - STEP 8: Content preview (first 100 chars): {content_preview}"
                    )
                except UnicodeDecodeError as decode_error:
                    logger.warning(
                        f"🔍 JSON IMPORT BACKEND - STEP 8: Could not decode content as UTF-8: {decode_error}"
                    )
                    print(
                        f"🔍 JSON IMPORT BACKEND - STEP 8: Could not decode content as UTF-8: {decode_error}"
                    )
            else:
                content_preview = str(file_content)[:100]
                logger.info(
                    f"🔍 JSON IMPORT BACKEND - STEP 8: Content preview (first 100 chars): {content_preview}"
                )
                print(
                    f"🔍 JSON IMPORT BACKEND - STEP 8: Content preview (first 100 chars): {content_preview}"
                )

            # Check if file is empty
            if file_size == 0:
                logger.warning(
                    f"⚠️ JSON IMPORT BACKEND - STEP 8: User {current_user.id} uploaded empty file"
                )
                print(
                    f"⚠️ JSON IMPORT BACKEND - STEP 8: User {current_user.id} uploaded empty file"
                )
                return templates.TemplateResponse(
                    "htmx/components/inline_error.html",
                    {
                        "request": request,
                        "message": "The uploaded file is empty. Please select a valid JSON file.",
                    },
                )

            logger.info(
                "🔍 JSON IMPORT BACKEND - STEP 8: File content validation PASSED"
            )
            print("🔍 JSON IMPORT BACKEND - STEP 8: File content validation PASSED")

        except Exception as e:
            logger.error(
                f"❌ JSON IMPORT BACKEND - STEP 8: User {current_user.id} file read error: {e}"
            )
            logger.error(f"❌ JSON IMPORT BACKEND - STEP 8: Error type: {type(e)}")
            logger.error(f"❌ JSON IMPORT BACKEND - STEP 8: Error args: {e.args}")
            print(
                f"❌ JSON IMPORT BACKEND - STEP 8: User {current_user.id} file read error: {e}"
            )
            print(f"❌ JSON IMPORT BACKEND - STEP 8: Error type: {type(e)}")
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {
                    "request": request,
                    "message": "Error reading the uploaded file. Please try again.",
                },
            )

        # Get user timezone for processing
        logger.info(
            "🔍 JSON IMPORT BACKEND - STEP 9: Getting user preferences and timezone"
        )
        print("🔍 JSON IMPORT BACKEND - STEP 9: Getting user preferences and timezone")

        user_prefs = get_user_preferences(current_user.id)
        user_timezone = user_prefs.get("default_timezone", "US/Eastern")

        logger.info(f"🔍 JSON IMPORT BACKEND - STEP 9: User preferences: {user_prefs}")
        logger.info(f"🔍 JSON IMPORT BACKEND - STEP 9: User timezone: {user_timezone}")
        print(f"🔍 JSON IMPORT BACKEND - STEP 9: User preferences: {user_prefs}")
        print(f"🔍 JSON IMPORT BACKEND - STEP 9: User timezone: {user_timezone}")

        # Import JSON data
        logger.info("🔍 JSON IMPORT BACKEND - STEP 10: Starting JSON data import")
        print("🔍 JSON IMPORT BACKEND - STEP 10: Starting JSON data import")

        success, poll_data, errors = await PollJSONImporter.import_from_json_file(
            file_content, user_timezone
        )

        logger.info("🔍 JSON IMPORT BACKEND - STEP 10: JSON import completed")
        logger.info(f"🔍 JSON IMPORT BACKEND - STEP 10: Success: {success}")
        logger.info(
            f"🔍 JSON IMPORT BACKEND - STEP 10: Errors count: {len(errors) if errors else 0}"
        )
        logger.info(
            f"🔍 JSON IMPORT BACKEND - STEP 10: Poll data keys: {list(poll_data.keys()) if poll_data else 'None'}"
        )
        print("🔍 JSON IMPORT BACKEND - STEP 10: JSON import completed")
        print(f"🔍 JSON IMPORT BACKEND - STEP 10: Success: {success}")
        print(
            f"🔍 JSON IMPORT BACKEND - STEP 10: Errors count: {len(errors) if errors else 0}"
        )
        print(
            f"🔍 JSON IMPORT BACKEND - STEP 10: Poll data keys: {list(poll_data.keys()) if poll_data else 'None'}"
        )

        if errors:
            logger.info("🔍 JSON IMPORT BACKEND - STEP 10: Errors details:")
            print("🔍 JSON IMPORT BACKEND - STEP 10: Errors details:")
            for i, error in enumerate(errors):
                logger.info(f"🔍 JSON IMPORT BACKEND - STEP 10: Error {i + 1}: {error}")
                print(f"🔍 JSON IMPORT BACKEND - STEP 10: Error {i + 1}: {error}")

        if poll_data:
            logger.info("🔍 JSON IMPORT BACKEND - STEP 10: Poll data details:")
            print("🔍 JSON IMPORT BACKEND - STEP 10: Poll data details:")
            for key, value in poll_data.items():
                value_preview = str(value)[:100] if value else "None"
                logger.info(f"🔍 JSON IMPORT BACKEND - STEP 10: {key}: {value_preview}")
                print(f"🔍 JSON IMPORT BACKEND - STEP 10: {key}: {value_preview}")

        if not success:
            logger.warning(
                f"⚠️ JSON IMPORT - User {current_user.id} validation failed: {len(errors)} errors"
            )
            for error in errors:
                logger.debug(f"🔍 JSON IMPORT - Validation error: {error}")

            # Create a detailed, user-friendly error message
            error_title = "❌ JSON Import Failed"

            # Categorize errors for better user understanding
            field_errors = []
            format_errors = []
            validation_errors = []

            for error in errors:
                error_lower = error.lower()
                if any(
                    field in error_lower for field in ["field", "missing", "required"]
                ):
                    field_errors.append(error)
                elif any(
                    fmt in error_lower
                    for fmt in ["json", "format", "encoding", "syntax"]
                ):
                    format_errors.append(error)
                else:
                    validation_errors.append(error)

            # Build comprehensive error message
            error_parts = [error_title, ""]

            if format_errors:
                error_parts.extend(
                    [
                        "📄 **File Format Issues:**",
                        *[f"• {error}" for error in format_errors],
                        "",
                    ]
                )

            if field_errors:
                error_parts.extend(
                    [
                        "📝 **Required Fields Missing:**",
                        *[f"• {error}" for error in field_errors],
                        "",
                    ]
                )

            if validation_errors:
                error_parts.extend(
                    [
                        "⚠️ **Validation Errors:**",
                        *[f"• {error}" for error in validation_errors],
                        "",
                    ]
                )

            # Add helpful suggestions
            error_parts.extend(
                [
                    "💡 **How to Fix:**",
                    "• Check that your JSON file uses the correct field names:",
                    "  - Use 'open_time' and 'close_time' (not 'scheduled_date'/'scheduled_time')",
                    "  - Use 'ping_role_enabled' and 'ping_role_id' (not 'role_ping')",
                    "• Ensure all required fields are present: 'name', 'question', 'options'",
                    "• Use ISO datetime format: '2025-01-20T09:00'",
                    "• Check the documentation for the complete format guide",
                    "",
                    f"📁 **Your file:** {filename}",
                ]
            )

            error_message = "\n".join(error_parts)

            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {"request": request, "message": error_message},
            )

        poll_name = poll_data.get("name", "Unknown Poll")
        logger.info(
            f"✅ JSON IMPORT - User {current_user.id} successfully imported: '{poll_name}' from {filename}"
        )

        # Instead of redirecting, directly return the create form with pre-filled data
        # Get user's guilds with channels with error handling
        try:
            user_guilds = await get_user_guilds_with_channels(bot, current_user.id)
            if user_guilds is None:
                user_guilds = []
        except Exception as e:
            logger.error(
                f"Error getting user guilds for JSON import form for {current_user.id}: {e}"
            )
            user_guilds = []

        # Get user preferences
        user_prefs = get_user_preferences(current_user.id)

        # Get priority timezone for new poll creation
        priority_timezone = get_priority_timezone_for_user(current_user.id)

        # Get timezones - priority timezone first
        common_timezones = [
            priority_timezone,
            "US/Eastern",
            "UTC",
            "US/Central",
            "US/Mountain",
            "US/Pacific",
            "Europe/London",
            "Europe/Paris",
            "Europe/Berlin",
            "Asia/Tokyo",
            "Asia/Shanghai",
            "Australia/Sydney",
        ]
        # Remove duplicates while preserving order
        seen = set()
        common_timezones = [
            tz for tz in common_timezones if not (tz in seen or seen.add(tz))
        ]

        # Set default times in priority timezone if not provided in JSON
        user_tz = pytz.timezone(priority_timezone)
        now = datetime.now(user_tz)

        # Check if JSON has times, otherwise use defaults
        if "open_time" in poll_data and poll_data["open_time"]:
            # JSON has times - convert them to local format for the form
            try:
                # Parse the datetime from JSON (should be in ISO format)
                if isinstance(poll_data["open_time"], str):
                    open_time_dt = datetime.fromisoformat(
                        poll_data["open_time"].replace("Z", "+00:00")
                    )
                else:
                    open_time_dt = poll_data["open_time"]

                # Convert to user timezone for display
                if open_time_dt.tzinfo is None:
                    open_time_dt = pytz.UTC.localize(open_time_dt)
                open_time_local = open_time_dt.astimezone(user_tz)
                default_open_time = open_time_local.strftime("%Y-%m-%dT%H:%M")
            except Exception as e:
                logger.warning(f"Error parsing JSON open_time: {e}, using default")
                # Fallback to default
                next_day = now.date() + timedelta(days=1)
                open_time_dt = datetime.combine(next_day, datetime.min.time())
                open_time_dt = user_tz.localize(open_time_dt)
                default_open_time = open_time_dt.strftime("%Y-%m-%dT%H:%M")
        else:
            # Default start time should be next day at 12:00AM (midnight)
            next_day = now.date() + timedelta(days=1)
            open_time_dt = datetime.combine(next_day, datetime.min.time())
            open_time_dt = user_tz.localize(open_time_dt)
            default_open_time = open_time_dt.strftime("%Y-%m-%dT%H:%M")

        # Handle close time similarly
        if "close_time" in poll_data and poll_data["close_time"]:
            try:
                if isinstance(poll_data["close_time"], str):
                    close_time_dt = datetime.fromisoformat(
                        poll_data["close_time"].replace("Z", "+00:00")
                    )
                else:
                    close_time_dt = poll_data["close_time"]

                if close_time_dt.tzinfo is None:
                    close_time_dt = pytz.UTC.localize(close_time_dt)
                close_time_local = close_time_dt.astimezone(user_tz)
                default_close_time = close_time_local.strftime("%Y-%m-%dT%H:%M")
            except Exception as e:
                logger.warning(f"Error parsing JSON close_time: {e}, using default")
                # Fallback: 24 hours after open time
                close_time_dt = open_time_dt + timedelta(hours=24)
                default_close_time = close_time_dt.strftime("%Y-%m-%dT%H:%M")
        else:
            # Close time should be 24 hours after open time
            close_time_dt = open_time_dt + timedelta(hours=24)
            default_close_time = close_time_dt.strftime("%Y-%m-%dT%H:%M")

        # Prepare timezone data for template
        timezones = []
        for tz in common_timezones:
            try:
                tz_obj = pytz.timezone(tz)
                offset = datetime.now(tz_obj).strftime("%z")
                if offset and len(offset) >= 5:
                    offset_formatted = f"UTC{offset[:3]}:{offset[3:]}"
                else:
                    offset_formatted = "UTC+00:00"
                timezones.append({"name": tz, "display": f"{tz} ({offset_formatted})"})
            except (pytz.UnknownTimeZoneError, ValueError, AttributeError) as e:
                logger.warning(f"Error formatting timezone {tz}: {e}")
                timezones.append({"name": tz, "display": tz})

        # RUN THROUGH THE SAME SERVER/CHANNEL/ROLE VALIDATION ROUTINE AS NEW FORM
        # This ensures JSON import behaves exactly like creating a new form
        imported_server_id = poll_data.get("server_id", "")
        imported_channel_id = poll_data.get("channel_id", "")
        imported_ping_role_id = poll_data.get("ping_role_id", "")
        validation_warnings = []

        logger.info("🔍 JSON IMPORT VALIDATION - Running new form validation routine")
        logger.info(
            f"🔍 JSON IMPORT VALIDATION - Imported server_id: {imported_server_id}"
        )
        logger.info(
            f"🔍 JSON IMPORT VALIDATION - Imported channel_id: {imported_channel_id}"
        )
        logger.info(
            f"🔍 JSON IMPORT VALIDATION - Imported ping_role_id: {imported_ping_role_id}"
        )
        print("🔍 JSON IMPORT VALIDATION - Running new form validation routine")
        print(f"🔍 JSON IMPORT VALIDATION - Imported server_id: {imported_server_id}")
        print(f"🔍 JSON IMPORT VALIDATION - Imported channel_id: {imported_channel_id}")
        print(
            f"🔍 JSON IMPORT VALIDATION - Imported ping_role_id: {imported_ping_role_id}"
        )

        # Step 1: Validate server access using the same logic as new form
        valid_server = False
        if imported_server_id:
            # Check if the imported server exists in user's accessible guilds
            for guild in user_guilds:
                if str(guild["id"]) == str(imported_server_id):
                    valid_server = True
                    logger.info(
                        f"🔍 JSON IMPORT VALIDATION - ✅ Server {imported_server_id} is accessible"
                    )
                    print(
                        f"🔍 JSON IMPORT VALIDATION - ✅ Server {imported_server_id} is accessible"
                    )
                    break

        if not valid_server and imported_server_id:
            logger.warning(
                f"🔍 JSON IMPORT VALIDATION - ❌ Server {imported_server_id} not accessible"
            )
            print(
                f"🔍 JSON IMPORT VALIDATION - ❌ Server {imported_server_id} not accessible"
            )
            validation_warnings.append(
                "Server from JSON not accessible - please select a server you have access to"
            )

        # Step 2: Apply new form reset logic for invalid server
        if not valid_server:
            # Reset to new form defaults exactly like get_create_form_htmx does
            poll_data["server_id"] = (
                ""  # Same as new form: no server pre-selected unless valid
            )
            poll_data["channel_id"] = (
                ""  # Same as new form: no channel until server selected
            )
            poll_data["ping_role_enabled"] = (
                False  # Same as new form: no role ping without valid server
            )
            poll_data["ping_role_id"] = ""
            logger.info(
                "🔍 JSON IMPORT VALIDATION - Reset to new form defaults (no valid server)"
            )
            print(
                "🔍 JSON IMPORT VALIDATION - Reset to new form defaults (no valid server)"
            )
        else:
            # Step 3: Validate channel access (only if server is valid)
            valid_channel = False
            if imported_channel_id:
                # Find the valid server in user_guilds
                for guild in user_guilds:
                    if str(guild["id"]) == str(imported_server_id):
                        # Check if channel exists in this server
                        for channel in guild["channels"]:
                            if str(channel["id"]) == str(imported_channel_id):
                                valid_channel = True
                                logger.info(
                                    f"🔍 JSON IMPORT VALIDATION - ✅ Channel {imported_channel_id} is accessible"
                                )
                                print(
                                    f"🔍 JSON IMPORT VALIDATION - ✅ Channel {imported_channel_id} is accessible"
                                )
                                break
                        break

            if not valid_channel and imported_channel_id:
                logger.warning(
                    f"🔍 JSON IMPORT VALIDATION - ❌ Channel {imported_channel_id} not accessible"
                )
                print(
                    f"🔍 JSON IMPORT VALIDATION - ❌ Channel {imported_channel_id} not accessible"
                )
                validation_warnings.append(
                    "Channel from JSON not found in selected server - please select a new channel"
                )
                # Reset channel but keep valid server (same as new form when server changes)
                poll_data["channel_id"] = ""

            # Step 4: Validate role access (only if server is valid and role ping enabled)
            if poll_data.get("ping_role_enabled") and imported_ping_role_id:
                valid_role = False
                try:
                    # Use the same role validation as the form
                    from .discord_utils import get_guild_roles

                    roles = await get_guild_roles(bot, imported_server_id)
                    if roles:
                        for role in roles:
                            if str(role["id"]) == str(imported_ping_role_id):
                                valid_role = True
                                logger.info(
                                    f"🔍 JSON IMPORT VALIDATION - ✅ Role {imported_ping_role_id} is accessible"
                                )
                                print(
                                    f"🔍 JSON IMPORT VALIDATION - ✅ Role {imported_ping_role_id} is accessible"
                                )
                                break

                    if not valid_role:
                        logger.warning(
                            f"🔍 JSON IMPORT VALIDATION - ❌ Role {imported_ping_role_id} not accessible"
                        )
                        print(
                            f"🔍 JSON IMPORT VALIDATION - ❌ Role {imported_ping_role_id} not accessible"
                        )
                        validation_warnings.append(
                            "Role from JSON not found in selected server - please select a new role"
                        )
                        # Reset role but keep server and channel (same as new form when server changes)
                        poll_data["ping_role_id"] = ""

                except Exception as e:
                    logger.warning(
                        f"🔍 JSON IMPORT VALIDATION - Error validating role: {e}"
                    )
                    print(f"🔍 JSON IMPORT VALIDATION - Error validating role: {e}")
                    validation_warnings.append(
                        "Could not validate role from JSON - please select a new role"
                    )
                    poll_data["ping_role_id"] = ""

        logger.info(
            f"🔍 JSON IMPORT VALIDATION - Validation complete, warnings: {len(validation_warnings)}"
        )
        print(
            f"🔍 JSON IMPORT VALIDATION - Validation complete, warnings: {len(validation_warnings)}"
        )
        for i, warning in enumerate(validation_warnings):
            logger.info(f"🔍 JSON IMPORT VALIDATION - Warning {i + 1}: {warning}")
            print(f"🔍 JSON IMPORT VALIDATION - Warning {i + 1}: {warning}")

        # GRACEFUL EMOJI VALIDATION
        # Check if imported emojis are valid/accessible
        imported_emojis = poll_data.get("emojis", [])
        if imported_emojis and len(imported_emojis) > 0:
            try:
                # Quick validation of emojis - check for Discord custom emoji format
                invalid_emojis = []
                for i, emoji in enumerate(imported_emojis):
                    if emoji and isinstance(emoji, str):
                        # Check if it's a Discord custom emoji format <:name:id> or <a:name:id>
                        if emoji.startswith("<:") or emoji.startswith("<a:"):
                            # This is a Discord custom emoji - it might not be accessible
                            # We'll let the unified emoji processor handle validation later
                            # but warn the user that custom emojis might not work
                            if not valid_server:
                                invalid_emojis.append(f"option {i + 1}")

                if invalid_emojis and not valid_server:
                    validation_warnings.append(
                        "Custom emojis from JSON may not work without a valid server - default emojis will be used if needed"
                    )
                elif invalid_emojis and valid_server:
                    validation_warnings.append(
                        "Some custom emojis from JSON may not be accessible in the selected server - they will fall back to defaults if needed"
                    )

            except Exception as e:
                logger.warning(f"Error validating imported emojis: {e}")
                validation_warnings.append(
                    "Emoji validation encountered issues - default emojis will be used if needed"
                )

        # Create success message with warnings if any
        success_message = f"JSON imported successfully! Poll '{poll_name}' data has been loaded into the form."
        if validation_warnings:
            success_message += (
                "\n\n⚠️ Some settings need your attention:\n• "
                + "\n• ".join(validation_warnings)
            )

        logger.info(
            f"🔍 JSON IMPORT - Returning create form with imported data for poll '{poll_name}' (warnings: {len(validation_warnings)})"
        )

        # Return the create form directly with the imported JSON data pre-filled
        return templates.TemplateResponse(
            "htmx/create_form_filepond.html",
            {
                "request": request,
                "guilds": user_guilds,
                "timezones": timezones,
                "open_time": default_open_time,
                "close_time": default_close_time,
                "user_preferences": user_prefs,
                "priority_timezone": priority_timezone,
                "default_emojis": POLL_EMOJIS,
                "template_data": poll_data,  # Pass the imported JSON data to pre-fill form
                "is_template": False,
                "is_json_import": True,  # Flag to indicate this is from JSON import
                "success_message": success_message,
                "validation_warnings": validation_warnings,  # Pass warnings to template
            },
        )

    except Exception as e:
        logger.error(f"❌ JSON IMPORT - Critical error for user {current_user.id}: {e}")
        logger.exception("Full traceback for JSON import error:")
        return templates.TemplateResponse(
            "htmx/components/inline_error.html",
            {
                "request": request,
                "message": f"Unexpected error importing JSON: {str(e)}",
            },
        )


async def get_create_form_json_import_htmx(
    request: Request, bot, current_user: DiscordUser = Depends(require_auth)
):
    """Get create poll form pre-filled with JSON import data"""
    # This endpoint will be called after successful JSON import
    # For now, we'll get the JSON data from the session or request parameters
    # In a real implementation, you might store this temporarily in Redis or similar

    # Get user's guilds with channels with error handling
    try:
        user_guilds = await get_user_guilds_with_channels(bot, current_user.id)
        if user_guilds is None:
            user_guilds = []
    except Exception as e:
        logger.error(
            f"Error getting user guilds for JSON import form for {current_user.id}: {e}"
        )
        user_guilds = []

    # Get user preferences
    user_prefs = get_user_preferences(current_user.id)

    # Get priority timezone for new poll creation
    priority_timezone = get_priority_timezone_for_user(current_user.id)

    # Get timezones - priority timezone first
    common_timezones = [
        priority_timezone,
        "US/Eastern",
        "UTC",
        "US/Central",
        "US/Mountain",
        "US/Pacific",
        "Europe/London",
        "Europe/Paris",
        "Europe/Berlin",
        "Asia/Tokyo",
        "Asia/Shanghai",
        "Australia/Sydney",
    ]
    # Remove duplicates while preserving order
    seen = set()
    common_timezones = [
        tz for tz in common_timezones if not (tz in seen or seen.add(tz))
    ]

    # Set default times in priority timezone if not provided in JSON
    user_tz = pytz.timezone(priority_timezone)
    now = datetime.now(user_tz)

    # Default start time should be next day at 12:00AM (midnight)
    next_day = now.date() + timedelta(days=1)
    open_time_dt = datetime.combine(next_day, datetime.min.time())
    open_time_dt = user_tz.localize(open_time_dt)
    default_open_time = open_time_dt.strftime("%Y-%m-%dT%H:%M")

    # Close time should be 24 hours after open time
    close_time_dt = open_time_dt + timedelta(hours=24)
    default_close_time = close_time_dt.strftime("%Y-%m-%dT%H:%M")

    # Prepare timezone data for template
    timezones = []
    for tz in common_timezones:
        try:
            tz_obj = pytz.timezone(tz)
            offset = datetime.now(tz_obj).strftime("%z")
            timezones.append({"name": tz, "display": f"{tz} (UTC{offset})"})
        except (pytz.UnknownTimeZoneError, ValueError, AttributeError) as e:
            logger.warning(f"Error formatting timezone {tz}: {e}")
            timezones.append({"name": tz, "display": tz})

    # For now, return the regular create form
    # In a full implementation, you'd pass the JSON data here
    return templates.TemplateResponse(
        "htmx/create_form_filepond.html",
        {
            "request": request,
            "guilds": user_guilds,
            "timezones": timezones,
            "open_time": default_open_time,
            "close_time": default_close_time,
            "user_preferences": user_prefs,
            "priority_timezone": priority_timezone,
            "default_emojis": POLL_EMOJIS,
            "template_data": None,  # JSON data would go here
            "is_template": False,
            "is_json_import": True,  # Flag to indicate this is from JSON import
        },
    )


# Helper functions for Redis caching
def _serialize_polls_for_cache(polls: list) -> list:
    """Convert Poll objects to JSON-serializable dictionaries with pre-calculated expensive operations"""
    serialized_polls = []
    
    for poll in polls:
        try:
            # Pre-calculate expensive operations during serialization
            total_votes = poll.get_total_votes()
            
            # Extract all poll data safely using TypeSafeColumn
            poll_data = {
                "id": TypeSafeColumn.get_int(poll, "id"),
                "name": TypeSafeColumn.get_string(poll, "name"),
                "question": TypeSafeColumn.get_string(poll, "question"),
                "status": TypeSafeColumn.get_string(poll, "status"),
                "creator_id": TypeSafeColumn.get_string(poll, "creator_id"),
                "server_id": TypeSafeColumn.get_string(poll, "server_id"),
                "server_name": TypeSafeColumn.get_string(poll, "server_name"),
                "channel_id": TypeSafeColumn.get_string(poll, "channel_id"),
                "channel_name": TypeSafeColumn.get_string(poll, "channel_name"),
                "options": poll.options,  # Use property method
                "emojis": poll.emojis,    # Use property method
                "anonymous": TypeSafeColumn.get_bool(poll, "anonymous", False),
                "multiple_choice": TypeSafeColumn.get_bool(poll, "multiple_choice", False),
                "max_choices": TypeSafeColumn.get_int(poll, "max_choices"),
                "ping_role_enabled": TypeSafeColumn.get_bool(poll, "ping_role_enabled", False),
                "ping_role_id": TypeSafeColumn.get_string(poll, "ping_role_id"),
                "ping_role_name": TypeSafeColumn.get_string(poll, "ping_role_name"),
                "ping_role_on_close": TypeSafeColumn.get_bool(poll, "ping_role_on_close", False),
                "ping_role_on_update": TypeSafeColumn.get_bool(poll, "ping_role_on_update", False),
                "image_path": TypeSafeColumn.get_string(poll, "image_path"),
                "image_message_text": TypeSafeColumn.get_string(poll, "image_message_text"),
                "timezone": TypeSafeColumn.get_string(poll, "timezone"),
                "created_at": TypeSafeColumn.get_datetime(poll, "created_at").isoformat() if TypeSafeColumn.get_datetime(poll, "created_at") else None,
                "updated_at": TypeSafeColumn.get_datetime(poll, "updated_at").isoformat() if TypeSafeColumn.get_datetime(poll, "updated_at") else None,
                "open_time": TypeSafeColumn.get_datetime(poll, "open_time").isoformat() if TypeSafeColumn.get_datetime(poll, "open_time") else None,
                "close_time": TypeSafeColumn.get_datetime(poll, "close_time").isoformat() if TypeSafeColumn.get_datetime(poll, "close_time") else None,
                # Pre-calculated expensive operations
                "total_votes": total_votes,
                # Add status class for template compatibility
                "status_class": {
                    "active": "bg-success",
                    "scheduled": "bg-warning", 
                    "closed": "bg-danger",
                }.get(TypeSafeColumn.get_string(poll, "status"), "bg-secondary")
            }
            
            serialized_polls.append(poll_data)
            
        except Exception as e:
            logger.error(f"Error serializing poll {TypeSafeColumn.get_int(poll, 'id', 0)}: {e}")
            continue
    
    return serialized_polls


def _reconstruct_polls_from_cache(cached_polls: list) -> list:
    """Recreate Poll-like objects from cached data with proper method interfaces"""
    reconstructed_polls = []
    
    for poll_data in cached_polls:
        try:
            # Create a Poll-like object that maintains template compatibility
            class CachedPoll:
                def __init__(self, data):
                    # Set all attributes from cached data
                    for key, value in data.items():
                        if key.endswith('_at') or key.endswith('_time'):
                            # Convert ISO strings back to datetime objects
                            if value:
                                try:
                                    setattr(self, key, datetime.fromisoformat(value.replace('Z', '+00:00')))
                                except (ValueError, AttributeError):
                                    setattr(self, key, None)
                            else:
                                setattr(self, key, None)
                        else:
                            setattr(self, key, value)
                
                def get_total_votes(self):
                    """Return pre-calculated total votes from cache"""
                    return getattr(self, 'total_votes', 0)
                
                @property
                def options(self):
                    """Return options list"""
                    return getattr(self, '_options', [])
                
                @options.setter
                def options(self, value):
                    self._options = value
                
                @property
                def emojis(self):
                    """Return emojis list"""
                    return getattr(self, '_emojis', [])
                
                @emojis.setter  
                def emojis(self, value):
                    self._emojis = value
            
            # Create the cached poll object
            cached_poll = CachedPoll(poll_data)
            
            # Set options and emojis using the properties
            cached_poll.options = poll_data.get('options', [])
            cached_poll.emojis = poll_data.get('emojis', [])
            
            reconstructed_polls.append(cached_poll)
            
        except Exception as e:
            logger.error(f"Error reconstructing cached poll {poll_data.get('id', 'unknown')}: {e}")
            continue
    
    return reconstructed_polls


async def invalidate_user_polls_cache(user_id: str, enhanced_cache=None):
    """Clear all poll cache variations for a user"""
    if enhanced_cache is None:
        from .enhanced_cache_service import get_enhanced_cache_service
        enhanced_cache = get_enhanced_cache_service()
    
    try:
        redis_client = await enhanced_cache._get_redis()
        if redis_client:
            # Clear all filter variations for the user using the cache_clear_pattern method
            cache_patterns = [
                f"user_polls:{user_id}:*",  # All filter variations (without cache: prefix - method adds it)
                f"user_polls:{user_id}",    # No filter (None) (without cache: prefix - method adds it)
            ]
            
            total_cleared = 0
            for pattern in cache_patterns:
                try:
                    # Use the cache_clear_pattern method from redis_client which handles the scan_iter properly
                    deleted_count = await redis_client.cache_clear_pattern(pattern)
                    total_cleared += deleted_count
                    logger.debug(f"🗑️ CACHE INVALIDATED - Cleared {deleted_count} poll cache keys for pattern {pattern}")
                except Exception as e:
                    logger.warning(f"Error clearing cache pattern {pattern} for user {user_id}: {e}")
            
            logger.info(f"✅ CACHE INVALIDATED - Successfully invalidated {total_cleared} poll cache entries for user {user_id}")
    except Exception as e:
        logger.error(f"Error invalidating poll cache for user {user_id}: {e}")


# HTMX endpoint functions that will be registered with the FastAPI app
async def get_polls_htmx(
    request: Request,
    filter: str = None,
    current_user: DiscordUser = Depends(require_auth),
):
    """Get user's polls as HTML for HTMX with Redis caching and 30-second TTL"""
    from .enhanced_cache_service import get_enhanced_cache_service

    enhanced_cache = get_enhanced_cache_service()
    
    logger.debug(f"Getting polls for user {current_user.id} with filter: {filter}")

    # Create filter-aware cache key
    filter_key = filter if filter else "all"
    cache_key = f"user_polls:{current_user.id}:{filter_key}"
    
    # Check cache first (30 second TTL)
    try:
        redis_client = await enhanced_cache._get_redis()
        if redis_client:
            cached_polls_data = await redis_client.cache_get(cache_key)
            if cached_polls_data:
                logger.debug(f"🚀 POLLS CACHE HIT - Retrieved cached polls for user {current_user.id} (filter: {filter})")
                
                # Debug the cache structure
                logger.debug(f"🔍 CACHE DEBUG - Cached data type: {type(cached_polls_data)}")
                logger.debug(f"🔍 CACHE DEBUG - Cached data keys: {list(cached_polls_data.keys()) if isinstance(cached_polls_data, dict) else 'Not a dict'}")
                
                serialized_polls = cached_polls_data.get("serialized_polls", [])
                logger.debug(f"🔍 CACHE DEBUG - Serialized polls type: {type(serialized_polls)}")
                logger.debug(f"🔍 CACHE DEBUG - Serialized polls count: {len(serialized_polls) if isinstance(serialized_polls, list) else 'Not a list'}")
                
                if serialized_polls and len(serialized_polls) > 0:
                    logger.debug(f"🔍 CACHE DEBUG - First poll data type: {type(serialized_polls[0])}")
                    logger.debug(f"🔍 CACHE DEBUG - First poll data keys: {list(serialized_polls[0].keys()) if isinstance(serialized_polls[0], dict) else 'Not a dict'}")
                
                try:
                    # Reconstruct Poll-like objects from cached data
                    cached_polls = _reconstruct_polls_from_cache(serialized_polls)
                    
                    logger.debug(f"🔍 CACHE DEBUG - Reconstructed polls count: {len(cached_polls)}")
                    
                    # Debug the reconstructed objects
                    if cached_polls and len(cached_polls) > 0:
                        first_poll = cached_polls[0]
                        logger.debug(f"🔍 CACHE DEBUG - First reconstructed poll type: {type(first_poll)}")
                        logger.debug(f"🔍 CACHE DEBUG - First poll has get_total_votes: {hasattr(first_poll, 'get_total_votes')}")
                        logger.debug(f"🔍 CACHE DEBUG - First poll get_total_votes callable: {callable(getattr(first_poll, 'get_total_votes', None))}")
                        
                        # Test the method
                        try:
                            test_votes = first_poll.get_total_votes()
                            logger.debug(f"🔍 CACHE DEBUG - First poll total votes: {test_votes}")
                        except Exception as method_error:
                            logger.error(f"🔍 CACHE DEBUG - Error calling get_total_votes: {method_error}")
                    
                    # Prepare template data with reconstructed polls
                    polls_data = {
                        "polls": cached_polls,
                        "current_filter": cached_polls_data.get("current_filter"),
                        "user_timezone": cached_polls_data.get("user_timezone", "US/Eastern"),
                    }
                    
                    logger.debug(f"✅ POLLS CACHE SUCCESS - Serving {len(cached_polls)} cached polls")
                    
                    return templates.TemplateResponse(
                        "htmx/polls.html",
                        {
                            "request": request,
                            "format_datetime_for_user": format_datetime_for_user,
                            **polls_data
                        },
                    )
                    
                except Exception as cache_reconstruction_error:
                    logger.error(f"❌ POLLS CACHE RECONSTRUCTION FAILED - {cache_reconstruction_error}")
                    logger.exception("Full traceback for cache reconstruction error:")
                    # Fall through to database query
                    
    except Exception as e:
        logger.warning(f"Error checking polls cache for user {current_user.id}: {e}")

    # Cache miss or reconstruction failed - generate from database
    logger.debug(f"🔍 POLLS CACHE MISS - Generating polls for user {current_user.id} (filter: {filter})")

    db = get_db_session()
    try:
        # Query polls with error handling
        try:
            query = db.query(Poll).filter(Poll.creator_id == current_user.id)

            # Apply filter if specified with validation
            if filter and filter in ["active", "scheduled", "closed"]:
                query = query.filter(Poll.status == filter)
                logger.debug(f"Applied filter: {filter}")

            polls = query.order_by(Poll.created_at.desc()).all()
            logger.debug(f"Found {len(polls)} polls for user {current_user.id}")

        except Exception as e:
            logger.error(
                f"Database error querying polls for user {current_user.id}: {e}"
            )
            logger.exception("Full traceback for polls query error:")

            # Return error template with empty polls list
            error_data = {
                "polls": [],
                "current_filter": filter,
                "user_timezone": "US/Eastern",
                "error": "Database error loading polls",
            }
            return templates.TemplateResponse("htmx/polls.html", {"request": request, "format_datetime_for_user": format_datetime_for_user, **error_data})

        # Process polls with individual error handling and defensive programming
        processed_polls = []
        for poll in polls:
            try:
                # Debug the poll object type and methods
                logger.debug(f"🔍 POLL PROCESSING DEBUG - Processing poll object type: {type(poll)}")
                logger.debug(f"🔍 POLL PROCESSING DEBUG - Poll object attributes: {dir(poll) if hasattr(poll, '__dict__') else 'No __dict__'}")
                
                # Check if poll has get_total_votes method
                if hasattr(poll, 'get_total_votes') and callable(getattr(poll, 'get_total_votes')):
                    logger.debug(f"🔍 POLL PROCESSING DEBUG - Poll {TypeSafeColumn.get_int(poll, 'id', 0)} has get_total_votes method")
                    try:
                        # Test the method to ensure it works
                        test_votes = poll.get_total_votes()
                        logger.debug(f"🔍 POLL PROCESSING DEBUG - Poll {TypeSafeColumn.get_int(poll, 'id', 0)} total votes: {test_votes}")
                    except Exception as method_error:
                        logger.error(f"🔍 POLL PROCESSING DEBUG - Error calling get_total_votes on poll {TypeSafeColumn.get_int(poll, 'id', 0)}: {method_error}")
                else:
                    logger.warning(f"🔍 POLL PROCESSING DEBUG - Poll {TypeSafeColumn.get_int(poll, 'id', 0)} missing get_total_votes method")

                # Add status_class to each poll for template
                poll.status_class = {
                    "active": "bg-success",
                    "scheduled": "bg-warning",
                    "closed": "bg-danger",
                }.get(TypeSafeColumn.get_string(poll, "status"), "bg-secondary")

                processed_polls.append(poll)
                logger.debug(
                    f"Processed poll {TypeSafeColumn.get_int(poll, 'id')} with status {TypeSafeColumn.get_string(poll, 'status')}"
                )

            except Exception as e:
                logger.error(
                    f"Error processing poll {TypeSafeColumn.get_int(poll, 'id', 0)}: {e}"
                )
                # Continue with other polls, skip this one

        # Get user's timezone preference with error handling
        try:
            user_prefs = get_user_preferences(current_user.id)
            user_timezone = user_prefs.get("default_timezone", "US/Eastern")
            logger.debug(f"User timezone: {user_timezone}")
        except Exception as e:
            logger.error(f"Error getting user preferences for {current_user.id}: {e}")
            user_timezone = "US/Eastern"

        logger.debug(f"Returning {len(processed_polls)} processed polls")

        # Serialize polls for caching (with pre-calculated expensive operations)
        try:
            serialized_polls = _serialize_polls_for_cache(processed_polls)
            
            # Prepare cacheable data
            cacheable_data = {
                "serialized_polls": serialized_polls,
                "current_filter": filter,
                "user_timezone": user_timezone,
                "cached_at": datetime.now().isoformat(),
            }
            
            # Cache with 30-second TTL
            if redis_client:
                await redis_client.cache_set(cache_key, cacheable_data, 30)
                logger.debug(f"💾 POLLS CACHED - Stored {len(serialized_polls)} polls for user {current_user.id} (filter: {filter}) with 30s TTL")
                
        except Exception as caching_error:
            logger.warning(f"Error caching polls for user {current_user.id}: {caching_error}")
            # Continue without caching

        # Prepare data for template
        polls_data = {
            "polls": processed_polls,
            "current_filter": filter,
            "user_timezone": user_timezone,
        }

        return templates.TemplateResponse(
            "htmx/polls.html",
            {
                "request": request,
                "format_datetime_for_user": format_datetime_for_user,
                **polls_data
            },
        )

    except Exception as e:
        logger.error(
            f"Critical error in get_polls_htmx for user {current_user.id}: {e}"
        )
        logger.exception("Full traceback for polls endpoint error:")

        # Return error-safe template
        error_data = {
            "polls": [],
            "current_filter": filter,
            "user_timezone": "US/Eastern",
            "error": f"Error loading polls: {str(e)}",
        }
        return templates.TemplateResponse("htmx/polls.html", {"request": request, "format_datetime_for_user": format_datetime_for_user, **error_data})
    finally:
        try:
            db.close()
        except Exception as e:
            logger.error(f"Error closing database connection: {e}")


async def get_stats_htmx(
    request: Request, current_user: DiscordUser = Depends(require_auth)
):
    """Get dashboard stats as HTML for HTMX with caching to prevent rate limiting"""
    from .enhanced_cache_service import get_enhanced_cache_service

    enhanced_cache = get_enhanced_cache_service()

    logger.debug(f"Getting stats for user {current_user.id}")

    # Check cache first (30 second TTL for stats to reduce database load)
    cache_key = f"user_stats_htmx:{current_user.id}"
    redis_client = None
    try:
        redis_client = await enhanced_cache._get_redis()
        if redis_client:
            cached_stats = await redis_client.cache_get(cache_key)
            if cached_stats:
                logger.debug(f"🚀 STATS CACHE HIT - Retrieved cached stats for user {current_user.id}")
                return templates.TemplateResponse(
                    "htmx/stats.html",
                    {
                        "request": request,
                        **cached_stats
                    },
                )
    except Exception as e:
        logger.warning(f"Error checking stats cache for user {current_user.id}: {e}")

    # Cache miss - generate stats
    logger.debug(f"🔍 STATS CACHE MISS - Generating stats for user {current_user.id}")

    db = get_db_session()
    try:
        # Query polls with error handling
        try:
            polls = db.query(Poll).filter(Poll.creator_id == current_user.id).all()
            logger.debug(f"Found {len(polls)} polls for user {current_user.id}")
        except Exception as e:
            logger.error(
                f"Database error querying polls for user {current_user.id}: {e}"
            )
            error_stats = {
                "total_polls": 0,
                "active_polls": 0,
                "total_votes": 0,
                "error": "Database error loading polls",
            }
            return templates.TemplateResponse("htmx/stats.html", {"request": request, **error_stats})

        # Calculate stats with individual error handling
        total_polls = len(polls)

        # Count active polls safely
        try:
            active_polls = len(
                [p for p in polls if TypeSafeColumn.get_string(p, "status") == "active"]
            )
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
                        f"Poll {TypeSafeColumn.get_int(poll, 'id')} has {poll_votes} votes"
                    )
                else:
                    logger.warning(
                        f"Poll {TypeSafeColumn.get_int(poll, 'id')} get_total_votes returned non-int: {type(poll_votes)}"
                    )
            except Exception as e:
                logger.error(
                    f"Error getting votes for poll {TypeSafeColumn.get_int(poll, 'id', 0)}: {e}"
                )
                # Try alternative method - direct vote count
                try:
                    vote_count = (
                        db.query(Vote)
                        .filter(Vote.poll_id == TypeSafeColumn.get_int(poll, "id"))
                        .count()
                    )
                    if isinstance(vote_count, int):
                        total_votes += vote_count
                        logger.debug(
                            f"Poll {TypeSafeColumn.get_int(poll, 'id')} fallback vote count: {vote_count}"
                        )
                except Exception as fallback_e:
                    logger.error(
                        f"Fallback vote count failed for poll {TypeSafeColumn.get_int(poll, 'id', 0)}: {fallback_e}"
                    )
                    # Continue without adding votes for this poll

        logger.debug(
            f"Stats calculated: polls={total_polls}, active={active_polls}, votes={total_votes}"
        )

        # Prepare stats data for caching and template
        stats_data = {
            "total_polls": total_polls,
            "active_polls": active_polls,
            "total_votes": total_votes,
        }

        # Cache the stats for 30 seconds to reduce database load
        try:
            if redis_client:
                await redis_client.cache_set(cache_key, stats_data, 30)
                logger.debug(f"💾 STATS CACHED - Stored stats for user {current_user.id} with 30s TTL")
        except Exception as e:
            logger.warning(f"Error caching stats for user {current_user.id}: {e}")

        return templates.TemplateResponse(
            "htmx/stats.html",
            {
                "request": request,
                **stats_data
            },
        )

    except Exception as e:
        logger.error(
            f"Critical error in get_stats_htmx for user {current_user.id}: {e}"
        )
        logger.exception("Full traceback for stats error:")

        # Return error-safe template
        error_stats = {
            "total_polls": 0,
            "active_polls": 0,
            "total_votes": 0,
            "error": f"Error loading stats: {str(e)}",
        }
        return templates.TemplateResponse("htmx/stats.html", {"request": request, **error_stats})
    finally:
        try:
            db.close()
        except Exception as e:
            logger.error(f"Error closing database connection: {e}")


async def get_create_form_htmx(
    request: Request, bot, current_user: DiscordUser = Depends(require_auth)
):
    """Get create poll form as HTML for HTMX"""
    # Get user's guilds with channels with error handling
    try:
        user_guilds = await get_user_guilds_with_channels(bot, current_user.id)
        # Ensure user_guilds is always a valid list
        if user_guilds is None:
            user_guilds = []
    except Exception as e:
        logger.error(
            f"Error getting user guilds for create form for {current_user.id}: {e}"
        )
        user_guilds = []

    # Get user preferences
    user_prefs = get_user_preferences(current_user.id)

    # Get priority timezone for new poll creation
    priority_timezone = get_priority_timezone_for_user(current_user.id)

    # Get timezones - priority timezone first
    common_timezones = [
        priority_timezone,
        "US/Eastern",
        "UTC",
        "US/Central",
        "US/Mountain",
        "US/Pacific",
        "Europe/London",
        "Europe/Paris",
        "Europe/Berlin",
        "Asia/Tokyo",
        "Asia/Shanghai",
        "Australia/Sydney",
    ]
    # Remove duplicates while preserving order
    seen = set()
    common_timezones = [
        tz for tz in common_timezones if not (tz in seen or seen.add(tz))
    ]

    # Set default times in priority timezone
    user_tz = pytz.timezone(priority_timezone)
    now = datetime.now(user_tz)

    # Default start time should be next day at 12:00AM (midnight)
    next_day = now.date() + timedelta(days=1)
    open_time_dt = datetime.combine(next_day, datetime.min.time())
    open_time_dt = user_tz.localize(open_time_dt)
    open_time = open_time_dt.strftime("%Y-%m-%dT%H:%M")

    # Close time should be 24 hours after open time (not creation time)
    close_time_dt = open_time_dt + timedelta(hours=24)
    close_time = close_time_dt.strftime("%Y-%m-%dT%H:%M")

    # Prepare timezone data for template
    timezones = []
    for tz in common_timezones:
        try:
            tz_obj = pytz.timezone(tz)
            offset = datetime.now(tz_obj).strftime("%z")
            timezones.append({"name": tz, "display": f"{tz} (UTC{offset})"})
        except (pytz.UnknownTimeZoneError, ValueError, AttributeError) as e:
            logger.warning(f"Error formatting timezone {tz}: {e}")
            timezones.append({"name": tz, "display": tz})

    return templates.TemplateResponse(
        "htmx/create_form_filepond.html",
        {
            "request": request,
            "guilds": user_guilds,
            "timezones": timezones,
            "open_time": open_time,
            "close_time": close_time,
            "user_preferences": user_prefs,
            "priority_timezone": priority_timezone,  # Pass priority timezone to template
            "default_emojis": POLL_EMOJIS,
            "template_data": None,  # No template data for regular form
            "is_template": False,  # Flag to indicate this is not a template creation
        },
    )


async def get_create_form_template_htmx(
    poll_id: int,
    request: Request,
    bot,
    current_user: DiscordUser = Depends(require_auth),
):
    """Get create poll form pre-filled with template data from existing poll"""
    logger.info(f"User {current_user.id} creating template from poll {poll_id}")
    db = get_db_session()
    try:
        # Get the source poll
        source_poll = (
            db.query(Poll)
            .filter(Poll.id == poll_id, Poll.creator_id == current_user.id)
            .first()
        )
        if not source_poll:
            logger.warning(
                f"Poll {poll_id} not found or not owned by user {current_user.id}"
            )
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {"request": request, "message": "Poll not found or access denied"},
            )

        # Get user's guilds with channels with error handling
        try:
            user_guilds = await get_user_guilds_with_channels(bot, current_user.id)
            if user_guilds is None:
                user_guilds = []
        except Exception as e:
            logger.error(
                f"Error getting user guilds for template form for {current_user.id}: {e}"
            )
            user_guilds = []

        # Get user preferences
        user_prefs = get_user_preferences(current_user.id)

        # Get timezones - user's default first
        common_timezones = [
            user_prefs["default_timezone"],
            "US/Eastern",
            "UTC",
            "US/Central",
            "US/Mountain",
            "US/Pacific",
            "Europe/London",
            "Europe/Paris",
            "Europe/Berlin",
            "Asia/Tokyo",
            "Asia/Shanghai",
            "Australia/Sydney",
        ]
        # Remove duplicates while preserving order
        seen = set()
        common_timezones = [
            tz for tz in common_timezones if not (tz in seen or seen.add(tz))
        ]

        # Set default times in user's timezone (not copying original times)
        user_tz = pytz.timezone(user_prefs["default_timezone"])
        now = datetime.now(user_tz)

        # Default start time should be next day at 12:00AM (midnight)
        next_day = now.date() + timedelta(days=1)
        open_time_dt = datetime.combine(next_day, datetime.min.time())
        open_time_dt = user_tz.localize(open_time_dt)
        open_time = open_time_dt.strftime("%Y-%m-%dT%H:%M")

        # Close time should be 24 hours after open time
        close_time_dt = open_time_dt + timedelta(hours=24)
        close_time = close_time_dt.strftime("%Y-%m-%dT%H:%M")

        # Prepare timezone data for template
        timezones = []
        for tz in common_timezones:
            try:
                tz_obj = pytz.timezone(tz)
                offset = datetime.now(tz_obj).strftime("%z")
                timezones.append({"name": tz, "display": f"{tz} (UTC{offset})"})
            except (pytz.UnknownTimeZoneError, ValueError, AttributeError) as e:
                logger.warning(f"Error formatting timezone {tz}: {e}")
                timezones.append({"name": tz, "display": tz})

        # Extract template data from source poll with detailed debugging
        logger.info(
            f"🔍 TEMPLATE DEBUG - Starting template data extraction from poll {poll_id}"
        )
        print(
            f"🔍 TEMPLATE DEBUG - Starting template data extraction from poll {poll_id}"
        )

        # Extract each field individually with debugging
        source_name = TypeSafeColumn.get_string(source_poll, "name")
        source_question = TypeSafeColumn.get_string(source_poll, "question")
        source_options = source_poll.options
        source_emojis = source_poll.emojis
        source_server_id = TypeSafeColumn.get_string(source_poll, "server_id")
        source_channel_id = TypeSafeColumn.get_string(source_poll, "channel_id")
        source_anonymous = TypeSafeColumn.get_bool(source_poll, "anonymous", False)
        source_multiple_choice = TypeSafeColumn.get_bool(
            source_poll, "multiple_choice", False
        )
        source_ping_role_enabled = TypeSafeColumn.get_bool(
            source_poll, "ping_role_enabled", False
        )
        source_ping_role_id = TypeSafeColumn.get_string(source_poll, "ping_role_id", "")

        # Log each extracted value
        logger.info(f"🔍 TEMPLATE DEBUG - source_name: '{source_name}'")
        logger.info(f"🔍 TEMPLATE DEBUG - source_question: '{source_question}'")
        logger.info(
            f"🔍 TEMPLATE DEBUG - source_options: {source_options} (type: {type(source_options)}, len: {len(source_options) if source_options else 0})"
        )
        logger.info(
            f"🔍 TEMPLATE DEBUG - source_emojis: {source_emojis} (type: {type(source_emojis)}, len: {len(source_emojis) if source_emojis else 0})"
        )
        logger.info(f"🔍 TEMPLATE DEBUG - source_server_id: '{source_server_id}'")
        logger.info(f"🔍 TEMPLATE DEBUG - source_channel_id: '{source_channel_id}'")
        logger.info(f"🔍 TEMPLATE DEBUG - source_anonymous: {source_anonymous}")
        logger.info(
            f"🔍 TEMPLATE DEBUG - source_multiple_choice: {source_multiple_choice}"
        )
        logger.info(
            f"🔍 TEMPLATE DEBUG - source_ping_role_enabled: {source_ping_role_enabled}"
        )
        logger.info(f"🔍 TEMPLATE DEBUG - source_ping_role_id: '{source_ping_role_id}'")

        # Also print to console for immediate visibility
        print(f"🔍 TEMPLATE DEBUG - source_name: '{source_name}'")
        print(f"🔍 TEMPLATE DEBUG - source_question: '{source_question}'")
        print(
            f"🔍 TEMPLATE DEBUG - source_options: {source_options} (type: {type(source_options)}, len: {len(source_options) if source_options else 0})"
        )
        print(
            f"🔍 TEMPLATE DEBUG - source_emojis: {source_emojis} (type: {type(source_emojis)}, len: {len(source_emojis) if source_emojis else 0})"
        )
        print(f"🔍 TEMPLATE DEBUG - source_server_id: '{source_server_id}'")
        print(f"🔍 TEMPLATE DEBUG - source_channel_id: '{source_channel_id}'")
        print(f"🔍 TEMPLATE DEBUG - source_anonymous: {source_anonymous}")
        print(f"🔍 TEMPLATE DEBUG - source_multiple_choice: {source_multiple_choice}")
        print(
            f"🔍 TEMPLATE DEBUG - source_ping_role_enabled: {source_ping_role_enabled}"
        )
        print(f"🔍 TEMPLATE DEBUG - source_ping_role_id: '{source_ping_role_id}'")

        template_data = {
            "name": f"Copy of {source_name}",
            "question": source_question,
            "options": source_options,
            "emojis": source_emojis,
            "server_id": source_server_id,
            "channel_id": source_channel_id,
            "anonymous": source_anonymous,
            "multiple_choice": source_multiple_choice,
            "ping_role_enabled": source_ping_role_enabled,
            "ping_role_id": source_ping_role_id,
            # Note: Intentionally NOT copying image_path or image_message_text as requested
        }

        logger.info(f"🔍 TEMPLATE DEBUG - Final template_data: {template_data}")
        print(f"🔍 TEMPLATE DEBUG - Final template_data: {template_data}")
        logger.info(
            f"Template data extracted from poll {poll_id}: {len(template_data['options'])} options, server={template_data['server_id']}"
        )

        return templates.TemplateResponse(
            "htmx/create_form_filepond.html",
            {
                "request": request,
                "guilds": user_guilds,
                "timezones": timezones,
                "open_time": open_time,
                "close_time": close_time,
                "user_preferences": user_prefs,
                "default_emojis": POLL_EMOJIS,
                "template_data": template_data,  # Pass template data to pre-fill form
                "is_template": True,  # Flag to indicate this is a template creation
            },
        )

    except Exception as e:
        logger.error(f"Error creating template from poll {poll_id}: {e}")
        return templates.TemplateResponse(
            "htmx/components/inline_error.html",
            {"request": request, "message": f"Error loading template: {str(e)}"},
        )
    finally:
        db.close()


async def get_channels_htmx(
    server_id: str,
    bot,
    current_user: DiscordUser = Depends(require_auth),
    preselect_last_channel: bool = True,
):
    """Get channels for a server as HTML options for HTMX with caching to prevent rate limiting"""
    from .enhanced_cache_service import get_enhanced_cache_service

    enhanced_cache = get_enhanced_cache_service()

    logger.debug(
        f"🔍 CHANNELS DEBUG - User {current_user.id} requesting channels for server {server_id}, preselect_last_channel={preselect_last_channel}"
    )

    if not server_id:
        logger.debug("🔍 CHANNELS DEBUG - No server_id provided")
        return '<option value="">Select a server first...</option>'

    # Check cache first (5 minute TTL for channels to reduce Discord API calls)
    cache_key = f"server_channels:{server_id}:{current_user.id}"
    try:
        redis_client = await enhanced_cache._get_redis()
        if redis_client:
            cached_channels = await redis_client.cache_get(cache_key)
            if cached_channels:
                logger.debug(f"🚀 CHANNELS CACHE HIT - Retrieved cached channels for server {server_id}")
                
                # Get user preferences for preselection
                user_prefs = get_user_preferences(current_user.id)
                last_channel_id = (
                    user_prefs.get("last_channel_id") if preselect_last_channel else None
                )
                last_server_id = user_prefs.get("last_server_id")

                # Only pre-select the last channel if we're loading the same server as last time
                should_preselect = (
                    preselect_last_channel
                    and last_channel_id
                    and last_server_id
                    and str(server_id) == str(last_server_id)
                )

                # Rebuild options HTML with current preselection logic
                options = '<option value="">Select a channel...</option>'
                for channel in cached_channels.get("channels", []):
                    escaped_channel_name = escape(channel["name"])
                    selected = (
                        "selected"
                        if should_preselect and channel["id"] == last_channel_id
                        else ""
                    )
                    options += f'<option value="{channel["id"]}" {selected}>#{escaped_channel_name}</option>'

                return options
    except Exception as e:
        logger.warning(f"Error checking channels cache for server {server_id}: {e}")

    # Cache miss - generate channels data
    logger.debug(f"🔍 CHANNELS CACHE MISS - Generating channels for server {server_id}")

    try:
        user_guilds = await get_user_guilds_with_channels(bot, current_user.id)
        if not user_guilds:
            logger.warning(
                f"🔍 CHANNELS DEBUG - No guilds found for user {current_user.id}"
            )
            return '<option value="">No servers available...</option>'

        guild = next((g for g in user_guilds if g["id"] == server_id), None)

        if not guild:
            logger.warning(
                f"🔍 CHANNELS DEBUG - Server {server_id} not found for user {current_user.id}"
            )
            return '<option value="">Server not found...</option>'

        logger.debug(
            f"🔍 CHANNELS DEBUG - Found guild: {guild['name']} with {len(guild['channels'])} channels"
        )

        # Cache the channels data for 5 minutes to reduce Discord API calls
        try:
            if redis_client:
                cacheable_data = {
                    "channels": guild["channels"],
                    "guild_name": guild["name"],
                    "cached_at": datetime.now().isoformat(),
                }
                await redis_client.cache_set(cache_key, cacheable_data, 300)  # 5 minutes
                logger.debug(f"💾 CHANNELS CACHED - Stored channels for server {server_id} with 5min TTL")
        except Exception as e:
            logger.warning(f"Error caching channels for server {server_id}: {e}")

        # Get user preferences to potentially pre-select last used channel
        user_prefs = get_user_preferences(current_user.id)
        last_channel_id = (
            user_prefs.get("last_channel_id") if preselect_last_channel else None
        )
        last_server_id = user_prefs.get("last_server_id")

        # Only pre-select the last channel if we're loading the same server as last time
        # This prevents pre-selecting channels from different servers when switching
        should_preselect = (
            preselect_last_channel
            and last_channel_id
            and last_server_id
            and str(server_id) == str(last_server_id)
        )

        logger.debug(
            f"🔍 CHANNELS DEBUG - Preselection logic: should_preselect={should_preselect}, last_channel_id={last_channel_id}, last_server_id={last_server_id}"
        )

        options = '<option value="">Select a channel...</option>'
        selected_channel_found = False

        for channel in guild["channels"]:
            # HTML escape the channel name to prevent JavaScript syntax errors
            escaped_channel_name = escape(channel["name"])
            # Pre-select the last used channel only if it's from the same server
            selected = (
                "selected"
                if should_preselect and channel["id"] == last_channel_id
                else ""
            )
            if selected:
                selected_channel_found = True
                logger.debug(
                    f"🔍 CHANNELS DEBUG - Pre-selecting channel: #{channel['name']} (ID: {channel['id']})"
                )
            options += f'<option value="{channel["id"]}" {selected}>#{escaped_channel_name}</option>'

        if should_preselect and not selected_channel_found and last_channel_id:
            logger.warning(
                f"🔍 CHANNELS DEBUG - Last used channel {last_channel_id} not found in server {server_id}"
            )

        logger.debug(
            f"🔍 CHANNELS DEBUG - Returning {len(guild['channels'])} channel options"
        )
        return options

    except Exception as e:
        logger.error(
            f"🔍 CHANNELS DEBUG - Error getting channels for server {server_id}: {e}"
        )
        logger.exception("Full traceback for channels error:")
        return '<option value="">Error loading channels...</option>'


async def get_roles_htmx(
    server_id: str,
    bot,
    current_user: DiscordUser = Depends(require_auth),
    preselect_last_role: bool = True,
):
    """Get roles for a server as HTML options for HTMX with caching to prevent rate limiting"""
    from .enhanced_cache_service import get_enhanced_cache_service

    enhanced_cache = get_enhanced_cache_service()

    logger.debug(
        f"🔍 ROLES DEBUG - User {current_user.id} requesting roles for server {server_id}, preselect_last_role={preselect_last_role}"
    )

    if not server_id:
        logger.debug("🔍 ROLES DEBUG - No server_id provided")
        return '<option value="">Select a server first...</option>'

    # Check cache first (5 minute TTL for roles to reduce Discord API calls)
    cache_key = f"server_roles:{server_id}:{current_user.id}"
    try:
        redis_client = await enhanced_cache._get_redis()
        if redis_client:
            cached_roles = await redis_client.cache_get(cache_key)
            if cached_roles:
                logger.debug(f"🚀 ROLES CACHE HIT - Retrieved cached roles for server {server_id}")
                
                # Get user preferences for preselection
                user_prefs = get_user_preferences(current_user.id)
                last_role_id = (
                    user_prefs.get("last_role_id") if preselect_last_role else None
                )
                last_server_id = user_prefs.get("last_server_id")

                # Only pre-select the last role if we're loading the same server as last time
                should_preselect = (
                    preselect_last_role
                    and last_role_id
                    and last_server_id
                    and str(server_id) == str(last_server_id)
                )

                # Rebuild options HTML with current preselection logic
                options = '<option value="">Select a role (optional)...</option>'
                for role in cached_roles.get("roles", []):
                    escaped_role_name = escape(role["name"])
                    selected = (
                        "selected" if should_preselect and role["id"] == last_role_id else ""
                    )

                    # Add color indicator if role has a color
                    color_indicator = ""
                    if role.get("color") and role["color"] != "0":
                        color_indicator = f'<span style="color: {role["color"]};">●</span> '

                    options += f'<option value="{role["id"]}" {selected}>{color_indicator}@{escaped_role_name}</option>'

                return options
    except Exception as e:
        logger.warning(f"Error checking roles cache for server {server_id}: {e}")

    # Cache miss - generate roles data
    logger.debug(f"🔍 ROLES CACHE MISS - Generating roles for server {server_id}")

    try:
        from .discord_utils import get_guild_roles

        roles = await get_guild_roles(bot, server_id)

        if not roles:
            logger.debug(f"🔍 ROLES DEBUG - No mentionable roles found for server {server_id}")
            return '<option value="">No mentionable roles found...</option>'

        logger.debug(f"🔍 ROLES DEBUG - Found {len(roles)} roles for server {server_id}")

        # Cache the roles data for 5 minutes to reduce Discord API calls
        try:
            if redis_client:
                cacheable_data = {
                    "roles": roles,
                    "cached_at": datetime.now().isoformat(),
                }
                await redis_client.cache_set(cache_key, cacheable_data, 300)  # 5 minutes
                logger.debug(f"💾 ROLES CACHED - Stored roles for server {server_id} with 5min TTL")
        except Exception as e:
            logger.warning(f"Error caching roles for server {server_id}: {e}")

        # Get user preferences to potentially pre-select last used role
        user_prefs = get_user_preferences(current_user.id)
        last_role_id = user_prefs.get("last_role_id") if preselect_last_role else None
        last_server_id = user_prefs.get("last_server_id")

        # Only pre-select the last role if we're loading the same server as last time
        should_preselect = (
            preselect_last_role
            and last_role_id
            and last_server_id
            and str(server_id) == str(last_server_id)
        )

        logger.debug(
            f"🔍 ROLES DEBUG - Preselection logic: should_preselect={should_preselect}, last_role_id={last_role_id}, last_server_id={last_server_id}"
        )

        options = '<option value="">Select a role (optional)...</option>'
        for role in roles:
            # HTML escape the role name to prevent JavaScript syntax errors
            escaped_role_name = escape(role["name"])
            # Pre-select the last used role only if it's from the same server
            selected = (
                "selected" if should_preselect and role["id"] == last_role_id else ""
            )

            # Add color indicator if role has a color
            color_indicator = ""
            if role.get("color") and role["color"] != "0":
                color_indicator = f'<span style="color: {role["color"]};">●</span> '

            options += f'<option value="{role["id"]}" {selected}>{color_indicator}@{escaped_role_name}</option>'

        logger.debug(f"🔍 ROLES DEBUG - Returning {len(roles)} role options")
        return options

    except Exception as e:
        logger.error(f"🔍 ROLES DEBUG - Error getting roles for server {server_id}: {e}")
        logger.exception("Full traceback for roles error:")
        return '<option value="">Error loading roles...</option>'


async def add_option_htmx(request: Request):
    """Add a new poll option input for HTMX with proper sequential numbering"""
    try:
        form_data = await request.form()

        # Count existing options by looking at form data
        # The form includes all current options when hx-include="#options-container" is used
        existing_options = 0
        for key in form_data.keys():
            if key.startswith("option") and key[6:].isdigit():
                option_number = int(key[6:])
                existing_options = max(existing_options, option_number)

        # Next option number should be existing + 1
        option_num = existing_options + 1

        # Ensure we don't exceed maximum options (10 total)
        if option_num > 10:
            logger.warning(
                f"Maximum options (10) reached, cannot add option {option_num}"
            )
            return ""  # Return empty to prevent adding more options

        emoji = POLL_EMOJIS[min(option_num - 1, len(POLL_EMOJIS) - 1)]

        logger.debug(
            f"✅ ADD OPTION - Adding option {option_num} with emoji {emoji} (found {existing_options} existing options)"
        )

        return templates.TemplateResponse(
            "htmx/components/poll_option.html",
            {"request": request, "emoji": emoji, "option_num": option_num},
        )
    except Exception as e:
        logger.error(f"Error in add_option_htmx: {e}")
        logger.exception("Full traceback for add_option_htmx error:")

        # Fallback: assume we're adding the 3rd option
        option_num = 3
        emoji = POLL_EMOJIS[min(option_num - 1, len(POLL_EMOJIS) - 1)]
        logger.debug(
            f"⚠️ ADD OPTION FALLBACK - Using option {option_num} with emoji {emoji}"
        )

        return templates.TemplateResponse(
            "htmx/components/poll_option.html",
            {"request": request, "emoji": emoji, "option_num": option_num},
        )


async def remove_option_htmx():
    """Remove a poll option for HTMX"""
    return ""  # Empty response removes the element


async def upload_image_htmx(
    request: Request, current_user: DiscordUser = Depends(require_auth)
):
    """Handle HTMX image upload with progress tracking and validation"""
    logger.info(f"🔍 HTMX IMAGE UPLOAD - User {current_user.id} starting image upload")
    
    try:
        form_data = await request.form()
        image_file = form_data.get("image")

        logger.info(f"🔍 HTMX IMAGE UPLOAD - Image file received: {type(image_file)}")
        logger.info(f"🔍 HTMX IMAGE UPLOAD - Has filename: {hasattr(image_file, 'filename') if image_file else False}")
        
        if not image_file or not hasattr(image_file, "filename") or not getattr(image_file, "filename", None):
            logger.warning("🔍 HTMX IMAGE UPLOAD - No valid image file provided")
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {"request": request, "message": "Please select an image file"}
            )

        filename = str(getattr(image_file, "filename", ""))
        logger.info(f"🔍 HTMX IMAGE UPLOAD - Processing file: {filename}")

        # Validate image file with comprehensive logging
        is_valid, error_msg, content = await validate_image_file(image_file)

        if not is_valid:
            logger.warning(f"🔍 HTMX IMAGE UPLOAD - Validation failed: {error_msg}")
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {"request": request, "message": error_msg}
            )

        if content and filename:
            # Save the image file
            image_path = await save_image_file(content, filename)
            if image_path:
                logger.info(f"🔍 HTMX IMAGE UPLOAD - ✅ Image saved successfully: {image_path}")
                
                # Return success response with image preview
                return templates.TemplateResponse(
                    "htmx/components/image_upload_success.html",
                    {
                        "request": request,
                        "image_path": image_path,
                        "filename": filename,
                        "file_size": len(content)
                    }
                )
            else:
                logger.error("🔍 HTMX IMAGE UPLOAD - Failed to save image file")
                return templates.TemplateResponse(
                    "htmx/components/inline_error.html",
                    {"request": request, "message": "Failed to save image file"}
                )

        logger.error("🔍 HTMX IMAGE UPLOAD - No valid image content")
        return templates.TemplateResponse(
            "htmx/components/inline_error.html",
            {"request": request, "message": "No valid image content"}
        )

    except Exception as e:
        logger.error(f"🔍 HTMX IMAGE UPLOAD - ❌ Error: {e}")
        logger.exception("Full traceback for HTMX image upload error:")
        return templates.TemplateResponse(
            "htmx/components/inline_error.html",
            {"request": request, "message": "Server error processing image"}
        )


async def remove_image_htmx(
    request: Request, current_user: DiscordUser = Depends(require_auth)
):
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


async def get_servers_htmx(
    request: Request, bot, current_user: DiscordUser = Depends(require_auth)
):
    """Get user's servers as HTML for HTMX"""
    user_guilds = await get_user_guilds_with_channels(bot, current_user.id)

    return templates.TemplateResponse(
        "htmx/servers.html", {"request": request, "guilds": user_guilds}
    )


async def get_settings_htmx(
    request: Request, current_user: DiscordUser = Depends(require_auth)
):
    """Get user settings form as HTML for HTMX"""
    # Get user preferences
    user_prefs = get_user_preferences(current_user.id)

    # Get common timezones
    timezones = get_common_timezones()

    return templates.TemplateResponse(
        "htmx/settings.html",
        {"request": request, "user_prefs": user_prefs, "timezones": timezones},
    )


async def save_settings_htmx(
    request: Request, current_user: DiscordUser = Depends(require_auth)
):
    """Save user settings via HTMX"""
    try:
        form_data = await request.form()
        timezone = safe_get_form_data(form_data, "timezone", "US/Eastern")

        # Validate and normalize timezone
        normalized_timezone = validate_and_normalize_timezone(timezone)

        # Save user preferences
        save_user_preferences(current_user.id, timezone=normalized_timezone)

        logger.info(
            f"Updated timezone preference for user {current_user.id} to {normalized_timezone}"
        )

        return templates.TemplateResponse(
            "htmx/components/alert_success.html",
            {
                "request": request,
                "message": "Settings saved successfully! Your timezone preference has been updated.",
                "redirect_url": "/htmx/settings",
            },
        )

    except Exception as e:
        logger.error(f"Error saving settings for user {current_user.id}: {e}")

        return templates.TemplateResponse(
            "htmx/components/inline_error.html",
            {"request": request, "message": f"Error saving settings: {str(e)}"},
        )


async def get_polls_realtime_htmx(
    request: Request,
    filter: str = None,
    current_user: DiscordUser = Depends(require_auth),
):
    """Get real-time poll data for HTMX polling updates - returns only poll cards content"""
    db = get_db_session()
    try:
        # Query polls with error handling
        try:
            query = db.query(Poll).filter(Poll.creator_id == current_user.id)

            # Apply filter if specified with validation
            if filter and filter in ["active", "scheduled", "closed"]:
                query = query.filter(Poll.status == filter)

            polls = query.order_by(Poll.created_at.desc()).all()

        except Exception as e:
            logger.error(
                f"Database error in realtime polls for user {current_user.id}: {e}"
            )
            return ""  # Return empty for real-time updates on error

        # Process polls with individual error handling (same as get_polls_htmx)
        processed_polls = []
        for poll in polls:
            try:
                # Add status_class to each poll for template
                poll.status_class = {
                    "active": "bg-success",
                    "scheduled": "bg-warning",
                    "closed": "bg-danger",
                }.get(TypeSafeColumn.get_string(poll, "status"), "bg-secondary")

                processed_polls.append(poll)

            except Exception as e:
                logger.error(
                    f"Error processing poll {TypeSafeColumn.get_int(poll, 'id', 0)} for realtime: {e}"
                )
                # Continue with other polls, skip this one

        # Get user's timezone preference with error handling
        try:
            user_prefs = get_user_preferences(current_user.id)
            user_timezone = user_prefs.get("default_timezone", "US/Eastern")
        except Exception as e:
            logger.error(f"Error getting user preferences for {current_user.id}: {e}")
            user_timezone = "US/Eastern"

        # Use the dedicated poll cards content component for real-time updates
        return templates.TemplateResponse(
            "htmx/components/poll_cards_content.html",
            {
                "request": request,
                "polls": processed_polls,
                "current_filter": filter,
                "user_timezone": user_timezone,
                "format_datetime_for_user": format_datetime_for_user,
            },
        )

    except Exception as e:
        logger.error(
            f"Critical error in realtime polls for user {current_user.id}: {e}"
        )
        return ""  # Return empty on error for real-time updates
    finally:
        try:
            db.close()
        except Exception as e:
            logger.error(f"Error closing database connection in realtime: {e}")


async def get_guild_emojis_htmx(
    server_id: str, bot, current_user: DiscordUser = Depends(require_auth)
):
    """Get custom emojis for a guild as JSON for HTMX"""
    logger.info(
        f"🔍 DISCORD EMOJI DEBUG - User {current_user.id} requesting emojis for server {server_id}"
    )
    print(
        f"🔍 DISCORD EMOJI DEBUG - User {current_user.id} requesting emojis for server {server_id}"
    )

    try:
        if not server_id:
            logger.warning("🔍 DISCORD EMOJI DEBUG - No server_id provided")
            print("🔍 DISCORD EMOJI DEBUG - No server_id provided")
            return {"emojis": []}

        # Check if bot is available
        if not bot:
            logger.error("🔍 DISCORD EMOJI DEBUG - Bot instance is None")
            print("🔍 DISCORD EMOJI DEBUG - Bot instance is None")
            return {"emojis": [], "error": "Bot not available"}

        # Check if server exists and bot has access
        try:
            guild = bot.get_guild(int(server_id))
            if not guild:
                logger.warning(
                    f"🔍 DISCORD EMOJI DEBUG - Guild {server_id} not found or bot has no access"
                )
                print(
                    f"🔍 DISCORD EMOJI DEBUG - Guild {server_id} not found or bot has no access"
                )
                return {
                    "emojis": [],
                    "error": f"Server {server_id} not found or bot has no access",
                }

            logger.info(
                f"🔍 DISCORD EMOJI DEBUG - Found guild: {guild.name} (ID: {guild.id})"
            )
            print(
                f"🔍 DISCORD EMOJI DEBUG - Found guild: {guild.name} (ID: {guild.id})"
            )

            # Check guild emoji count
            emoji_count = len(guild.emojis)
            logger.info(f"🔍 DISCORD EMOJI DEBUG - Guild has {emoji_count} emojis")
            print(f"🔍 DISCORD EMOJI DEBUG - Guild has {emoji_count} emojis")

            # Log first few emojis for debugging
            for i, emoji in enumerate(guild.emojis[:5]):  # Show first 5 emojis
                logger.info(
                    f"🔍 DISCORD EMOJI DEBUG - Emoji {i + 1}: {emoji.name} (ID: {emoji.id}, animated: {emoji.animated})"
                )
                print(
                    f"🔍 DISCORD EMOJI DEBUG - Emoji {i + 1}: {emoji.name} (ID: {emoji.id}, animated: {emoji.animated})"
                )

        except ValueError as ve:
            logger.error(
                f"🔍 DISCORD EMOJI DEBUG - Invalid server_id format: {server_id} - {ve}"
            )
            print(
                f"🔍 DISCORD EMOJI DEBUG - Invalid server_id format: {server_id} - {ve}"
            )
            return {"emojis": [], "error": f"Invalid server ID format: {server_id}"}

        # Create emoji handler
        logger.info("🔍 DISCORD EMOJI DEBUG - Creating DiscordEmojiHandler")
        print("🔍 DISCORD EMOJI DEBUG - Creating DiscordEmojiHandler")
        emoji_handler = DiscordEmojiHandler(bot)

        # Get guild emojis
        logger.info(
            f"🔍 DISCORD EMOJI DEBUG - Calling get_guild_emoji_list for server {server_id}"
        )
        print(
            f"🔍 DISCORD EMOJI DEBUG - Calling get_guild_emoji_list for server {server_id}"
        )
        emoji_list = await emoji_handler.get_guild_emoji_list(int(server_id))

        logger.info(
            f"🔍 DISCORD EMOJI DEBUG - get_guild_emoji_list returned {len(emoji_list)} emojis"
        )
        print(
            f"🔍 DISCORD EMOJI DEBUG - get_guild_emoji_list returned {len(emoji_list)} emojis"
        )

        # Log the structure of returned emojis
        # Show first 3 emoji data structures
        for i, emoji_data in enumerate(emoji_list[:3]):
            logger.info(f"🔍 DISCORD EMOJI DEBUG - Emoji data {i + 1}: {emoji_data}")
            print(f"🔍 DISCORD EMOJI DEBUG - Emoji data {i + 1}: {emoji_data}")

        result = {"success": True, "emojis": emoji_list}
        logger.info(
            f"🔍 DISCORD EMOJI DEBUG - Returning result with {len(emoji_list)} emojis"
        )
        print(
            f"🔍 DISCORD EMOJI DEBUG - Returning result with {len(emoji_list)} emojis"
        )

        return result

    except Exception as e:
        logger.error(
            f"🔍 DISCORD EMOJI DEBUG - Exception getting guild emojis for server {server_id}: {e}"
        )
        logger.exception("🔍 DISCORD EMOJI DEBUG - Full traceback:")
        print(
            f"🔍 DISCORD EMOJI DEBUG - Exception getting guild emojis for server {server_id}: {e}"
        )
        return {"emojis": [], "error": str(e)}


def validate_poll_form_data(form_data, current_user_id: str) -> tuple[bool, list, dict]:
    """Validate poll form data and return validation results"""
    validation_errors = []
    validated_data = {}

    # Extract form data
    name = safe_get_form_data(form_data, "name")
    question = safe_get_form_data(form_data, "question")
    server_id = safe_get_form_data(form_data, "server_id")
    channel_id = safe_get_form_data(form_data, "channel_id")
    open_time = safe_get_form_data(form_data, "open_time")
    close_time = safe_get_form_data(form_data, "close_time")
    timezone_str = safe_get_form_data(form_data, "timezone", "US/Eastern")
    open_immediately = form_data.get("open_immediately") == "true"

    # Validate poll name
    if not name or len(name.strip()) < 3:
        validation_errors.append(
            {
                "field_name": "Poll Name",
                "message": "Must be at least 3 characters long",
                "suggestion": "Try something descriptive like 'Weekend Movie Night' or 'Team Lunch Choice'",
            }
        )
    elif len(name.strip()) > 255:
        validation_errors.append(
            {
                "field_name": "Poll Name",
                "message": "Must be less than 255 characters",
                "suggestion": "Try shortening your poll name to be more concise",
            }
        )
    else:
        validated_data["name"] = name.strip()

    # Validate question
    if not question or len(question.strip()) < 5:
        validation_errors.append(
            {
                "field_name": "Question",
                "message": "Must be at least 5 characters long",
                "suggestion": "Be specific! Instead of 'Pick one', try 'Which movie should we watch this Friday?'",
            }
        )
    elif len(question.strip()) > 2000:
        validation_errors.append(
            {
                "field_name": "Question",
                "message": "Must be less than 2000 characters",
                "suggestion": "Try to keep your question concise and to the point",
            }
        )
    else:
        validated_data["question"] = question.strip()

    # Validate server selection
    if not server_id:
        validation_errors.append(
            {
                "field_name": "Server",
                "message": "Please select a Discord server",
                "suggestion": "Choose the server where you want to post this poll",
            }
        )
    else:
        validated_data["server_id"] = server_id

    # Validate channel selection
    if not channel_id:
        validation_errors.append(
            {
                "field_name": "Channel",
                "message": "Please select a Discord channel",
                "suggestion": "Choose the channel where you want to post this poll",
            }
        )
    else:
        validated_data["channel_id"] = channel_id

    # Validate options
    options = []
    for i in range(1, 11):
        option = form_data.get(f"option{i}")
        if option:
            option_text = str(option).strip()
            if option_text:
                options.append(option_text)

    if len(options) < 2:
        validation_errors.append(
            {
                "field_name": "Poll Options",
                "message": "At least 2 options are required",
                "suggestion": "Add more choices for people to vote on. Great polls usually have 3-5 options!",
            }
        )
    elif len(options) > 10:
        validation_errors.append(
            {
                "field_name": "Poll Options",
                "message": "Maximum 10 options allowed",
                "suggestion": "Try to keep your options focused. Too many choices can be overwhelming!",
            }
        )
    else:
        validated_data["options"] = options

    # Validate times - skip open_time validation if opening immediately
    if not open_immediately and not open_time:
        validation_errors.append(
            {
                "field_name": "Open Time",
                "message": "Please select when the poll should start",
                "suggestion": "Choose a time when your audience will be active",
            }
        )
    elif not close_time:
        validation_errors.append(
            {
                "field_name": "Close Time",
                "message": "Please select when the poll should end",
                "suggestion": "Give people enough time to vote, but not too long that they forget",
            }
        )
    else:
        try:
            # Parse times with timezone - handle immediate vs scheduled polls
            if open_immediately:
                # For immediate polls, set open_time to current time and only validate close_time
                now = datetime.now(pytz.UTC)
                open_dt = now
                close_dt = safe_parse_datetime_with_timezone(close_time, timezone_str)

                # Validate close time is in the future
                if close_dt <= now:
                    user_tz = pytz.timezone(
                        validate_and_normalize_timezone(timezone_str)
                    )
                    next_minute_local = (now + timedelta(minutes=1)).astimezone(user_tz)
                    suggested_time = next_minute_local.strftime("%I:%M %p")
                    validation_errors.append(
                        {
                            "field_name": "Close Time",
                            "message": "Must be in the future for immediate polls",
                            "suggestion": f"Try {suggested_time} or later",
                        }
                    )
                else:
                    # Check minimum duration (1 minute)
                    duration = close_dt - open_dt
                    if duration < timedelta(minutes=1):
                        validation_errors.append(
                            {
                                "field_name": "Poll Duration",
                                "message": "Poll must run for at least 1 minute",
                                "suggestion": "Give people time to see and respond to your poll",
                            }
                        )
                    elif duration > timedelta(days=30):
                        validation_errors.append(
                            {
                                "field_name": "Poll Duration",
                                "message": "Poll cannot run for more than 30 days",
                                "suggestion": "Try a shorter duration to keep engagement high",
                            }
                        )
                    else:
                        validated_data["open_time"] = open_dt
                        validated_data["close_time"] = close_dt
            else:
                # For scheduled polls, validate both times normally
                open_dt = safe_parse_datetime_with_timezone(open_time, timezone_str)
                close_dt = safe_parse_datetime_with_timezone(close_time, timezone_str)

                # Validate times using the poll's timezone
                now = datetime.now(pytz.UTC)
                
                # Get the user's timezone for proper validation
                user_tz = pytz.timezone(validate_and_normalize_timezone(timezone_str))
                now_in_user_tz = now.astimezone(user_tz)
                
                # Calculate next full minute in user's timezone, then convert to UTC for comparison
                next_minute_user_tz = now_in_user_tz.replace(second=0, microsecond=0) + timedelta(minutes=1)
                next_minute_utc = next_minute_user_tz.astimezone(pytz.UTC)

                if open_dt < next_minute_utc:
                    suggested_time = next_minute_user_tz.strftime("%I:%M %p")
                    validation_errors.append(
                        {
                            "field_name": "Open Time",
                            "message": "Must be scheduled for at least the next full minute",
                            "suggestion": f"Try {suggested_time} or later in your timezone ({timezone_str})",
                        }
                    )
                elif close_dt <= open_dt:
                    validation_errors.append(
                        {
                            "field_name": "Close Time",
                            "message": "Must be after the open time",
                            "suggestion": "Make sure your poll runs for at least a few minutes so people can vote",
                        }
                    )
                else:
                    # Check minimum duration (1 minute)
                    duration = close_dt - open_dt
                    if duration < timedelta(minutes=1):
                        validation_errors.append(
                            {
                                "field_name": "Poll Duration",
                                "message": "Poll must run for at least 1 minute",
                                "suggestion": "Give people time to see and respond to your poll",
                            }
                        )
                    elif duration > timedelta(days=30):
                        validation_errors.append(
                            {
                                "field_name": "Poll Duration",
                                "message": "Poll cannot run for more than 30 days",
                                "suggestion": "Try a shorter duration to keep engagement high",
                            }
                        )
                    else:
                        validated_data["open_time"] = open_dt
                        validated_data["close_time"] = close_dt
        except Exception:
            validation_errors.append(
                {
                    "field_name": "Poll Times",
                    "message": "Invalid date/time format",
                    "suggestion": "Please check your date and time selections",
                }
            )

    # Handle role ping fields
    ping_role_enabled = form_data.get("ping_role_enabled") == "true"
    ping_role_id = safe_get_form_data(form_data, "ping_role_id", "")
    ping_role_on_close = form_data.get("ping_role_on_close") == "true"
    ping_role_on_update = form_data.get("ping_role_on_update") == "true"

    # Validate role ping settings
    if ping_role_enabled and not ping_role_id:
        validation_errors.append(
            {
                "field_name": "Role Selection",
                "message": "Please select a role to ping when role ping is enabled",
                "suggestion": "Choose a role from the dropdown or disable role ping",
            }
        )

    validated_data["ping_role_enabled"] = ping_role_enabled
    validated_data["ping_role_id"] = ping_role_id if ping_role_enabled else None
    validated_data["ping_role_on_close"] = (
        ping_role_on_close if ping_role_enabled else False
    )
    validated_data["ping_role_on_update"] = (
        ping_role_on_update if ping_role_enabled else False
    )

    # Add other validated data
    validated_data["timezone"] = validate_and_normalize_timezone(timezone_str)
    validated_data["anonymous"] = form_data.get("anonymous") == "true"
    validated_data["multiple_choice"] = form_data.get("multiple_choice") == "true"
    
    # Handle max_choices for multiple choice polls
    max_choices_str = safe_get_form_data(form_data, "max_choices", "")
    max_choices = None
    if validated_data["multiple_choice"] and max_choices_str:
        try:
            max_choices = int(max_choices_str)
            # Validate max_choices is reasonable (between 2 and 10)
            if max_choices < 2 or max_choices > 10:
                validation_errors.append(
                    {
                        "field_name": "Maximum Choices",
                        "message": "Must be between 2 and 10 choices",
                        "suggestion": "Choose a reasonable number of choices users can select",
                    }
                )
            else:
                validated_data["max_choices"] = max_choices
        except ValueError:
            validation_errors.append(
                {
                    "field_name": "Maximum Choices",
                    "message": "Invalid number format",
                    "suggestion": "Please select a valid number of choices",
                }
            )
    else:
        validated_data["max_choices"] = max_choices
    
    validated_data["creator_id"] = current_user_id
    validated_data["image_message_text"] = safe_get_form_data(
        form_data, "image_message_text", ""
    )
    validated_data["open_immediately"] = open_immediately

    is_valid = len(validation_errors) == 0
    return is_valid, validation_errors, validated_data


async def create_poll_htmx(
    request: Request, bot, scheduler, current_user: DiscordUser = Depends(require_auth)
):
    """Create a new poll via HTMX using bulletproof operations with Discord native emoji handling"""
    logger.info(f"User {current_user.id} creating new poll")

    try:
        form_data = await request.form()

        # RAW FORM DATA DEBUGGING - OUTPUT IMMEDIATELY
        print(f"🔍 RAW FORM DATA DEBUG - Poll creation by user {current_user.id}")
        print(f"🔍 RAW FORM DATA DEBUG - Form data keys: {list(form_data.keys())}")
        logger.info(f"🔍 RAW FORM DATA DEBUG - Poll creation by user {current_user.id}")
        logger.info(
            f"🔍 RAW FORM DATA DEBUG - Form data keys: {list(form_data.keys())}"
        )

        # Log ALL form data values
        for key, value in form_data.items():
            print(f"🔍 RAW FORM DATA DEBUG - {key}: '{value}' (type: {type(value)})")
            logger.info(
                f"🔍 RAW FORM DATA DEBUG - {key}: '{value}' (type: {type(value)})"
            )

        # Specifically focus on emoji inputs
        emoji_keys = [key for key in form_data.keys() if key.startswith("emoji")]
        print(
            f"🔍 RAW FORM DATA DEBUG - Found {len(emoji_keys)} emoji keys: {emoji_keys}"
        )
        logger.info(
            f"🔍 RAW FORM DATA DEBUG - Found {len(emoji_keys)} emoji keys: {emoji_keys}"
        )

        for emoji_key in emoji_keys:
            emoji_value = form_data.get(emoji_key)
            print(
                f"🔍 RAW FORM DATA DEBUG - {emoji_key} = '{emoji_value}' (len: {len(str(emoji_value)) if emoji_value else 0})"
            )
            logger.info(
                f"🔍 RAW FORM DATA DEBUG - {emoji_key} = '{emoji_value}' (len: {len(str(emoji_value)) if emoji_value else 0})"
            )

        # Validate form data
        is_valid, validation_errors, validated_data = validate_poll_form_data(
            form_data, current_user.id
        )

        if not is_valid:
            logger.info(
                f"Poll creation validation failed for user {current_user.id}: {len(validation_errors)} errors"
            )
            # Log each validation error for debugging
            for i, error in enumerate(validation_errors):
                logger.error(f"Validation error {i + 1}: {error}")
                print(f"🔍 VALIDATION ERROR {i + 1}: {error}")
            
            # Create user-friendly error message from validation errors
            error_messages = []
            for error in validation_errors:
                field_name = error.get("field_name", "Field")
                message = error.get("message", "Invalid value")
                suggestion = error.get("suggestion", "")
                
                error_line = f"**{field_name}**: {message}"
                if suggestion:
                    error_line += f" - {suggestion}"
                error_messages.append(error_line)
            
            combined_error_message = "Please fix the following issues:\n\n" + "\n\n".join(error_messages)
            
            # Return inline error template instead of HTTPException
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {"request": request, "message": combined_error_message},
            )

        # Use unified emoji processor for consistent handling
        unified_processor = get_unified_emoji_processor(bot)
        options = validated_data["options"]
        server_id = validated_data["server_id"]

        # Extract emoji inputs from form data
        emoji_inputs = unified_processor.extract_emoji_inputs_from_form(
            form_data, len(options)
        )

        # Process emojis using unified processor
        (
            emoji_success,
            emojis,
            emoji_error,
        ) = await unified_processor.process_poll_emojis_unified(
            emoji_inputs, int(server_id), "create"
        )

        if not emoji_success:
            logger.warning(
                f"Unified emoji processing failed for user {current_user.id}: {emoji_error}"
            )
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {"request": request, "message": emoji_error},
            )

        # Extract validated data
        name = validated_data["name"]
        question = validated_data["question"]
        server_id = validated_data["server_id"]
        channel_id = validated_data["channel_id"]
        open_dt = validated_data["open_time"]
        close_dt = validated_data["close_time"]
        timezone_str = validated_data["timezone"]
        anonymous = validated_data["anonymous"]
        multiple_choice = validated_data["multiple_choice"]
        ping_role_enabled = validated_data["ping_role_enabled"]
        ping_role_id = validated_data["ping_role_id"]
        image_message_text = validated_data["image_message_text"]

        # Fetch role name if role ping is enabled
        ping_role_name = None
        logger.info(f"🔔 ROLE PING DEBUG - Poll creation for user {current_user.id}")
        logger.info(f"🔔 ROLE PING DEBUG - ping_role_enabled: {ping_role_enabled}")
        logger.info(f"🔔 ROLE PING DEBUG - ping_role_id: {ping_role_id}")
        logger.info(f"🔔 ROLE PING DEBUG - server_id: {server_id}")

        if ping_role_enabled and ping_role_id:
            logger.info(
                "🔔 ROLE PING DEBUG - Role ping is enabled, fetching role name..."
            )
            try:
                guild = bot.get_guild(int(server_id))
                logger.info(
                    f"🔔 ROLE PING DEBUG - Guild lookup result: {guild.name if guild else 'None'}"
                )

                if guild:
                    role = guild.get_role(int(ping_role_id))
                    logger.info(
                        f"🔔 ROLE PING DEBUG - Role lookup result: {role.name if role else 'None'}"
                    )

                    if role:
                        ping_role_name = role.name
                        logger.info(
                            f"🔔 ROLE PING DEBUG - ✅ Successfully fetched role name '{ping_role_name}' for role ID {ping_role_id}"
                        )
                    else:
                        logger.warning(
                            f"🔔 ROLE PING DEBUG - ❌ Role {ping_role_id} not found in guild {server_id}"
                        )
                else:
                    logger.warning(
                        f"🔔 ROLE PING DEBUG - ❌ Guild {server_id} not found"
                    )
            except Exception as e:
                logger.error(
                    f"🔔 ROLE PING DEBUG - ❌ Error fetching role name for role {ping_role_id}: {e}"
                )
        else:
            logger.info(
                "🔔 ROLE PING DEBUG - Role ping is disabled or no role ID provided"
            )

        # Extract open_immediately flag
        open_immediately = validated_data["open_immediately"]

        # Extract the new role ping settings
        ping_role_on_close = validated_data["ping_role_on_close"]
        ping_role_on_update = validated_data["ping_role_on_update"]

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
            "ping_role_enabled": ping_role_enabled,
            "ping_role_id": ping_role_id,
            "ping_role_name": ping_role_name,
            "ping_role_on_close": ping_role_on_close,
            "ping_role_on_update": ping_role_on_update,
            "creator_id": current_user.id,
            "open_immediately": open_immediately,
        }

        # Handle image file
        image_file_data = None
        image_filename = None
        image_file = form_data.get("image")
        if (
            image_file
            and hasattr(image_file, "filename")
            and getattr(image_file, "filename", None)
        ):
            try:
                # Ensure image_file has read method before calling it
                if hasattr(image_file, "read") and callable(
                    getattr(image_file, "read", None)
                ):
                    image_file_data = await image_file.read()
                    image_filename = str(getattr(image_file, "filename", ""))
                else:
                    logger.warning(
                        "Image file object does not have a callable read method"
                    )
                    image_file_data = None
                    image_filename = None
            except Exception as e:
                logger.error(f"Error reading image file: {e}")
                return templates.TemplateResponse(
                    "htmx/components/inline_error.html",
                    {"request": request, "message": "Error reading image file"},
                )

        # Use bulletproof poll operations for creation
        bulletproof_ops = BulletproofPollOperations(bot)

        result = await bulletproof_ops.create_bulletproof_poll(
            poll_data=poll_data,
            user_id=current_user.id,
            image_file=image_file_data,
            image_filename=image_filename,
            image_message_text=image_message_text if image_file_data else None,
        )

        if not result["success"]:
            logger.warning(f"Bulletproof poll creation failed: {result['error']}")
            # Use error handler for user-friendly messages
            error_msg = await PollErrorHandler.handle_poll_creation_error(
                Exception(result["error"]), poll_data, bot
            )
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {"request": request, "message": error_msg},
            )

        poll_id = result["poll_id"]
        logger.info(f"Created poll {poll_id} for user {current_user.id}")

        # Schedule poll opening and closing using timezone-aware scheduler
        try:
            from .background_tasks import close_poll

            # Use the timezone-aware scheduler wrapper
            tz_scheduler = TimezoneAwareScheduler(scheduler)

            # Create wrapper function for scheduled poll opening using unified service
            async def open_poll_scheduled_wrapper(poll_id):
                """Wrapper function for scheduled poll opening using unified service"""
                from .poll_open_service import poll_opening_service
                
                result = await poll_opening_service.open_poll_unified(
                    poll_id=poll_id,
                    reason="scheduled",
                    bot_instance=bot
                )
                if not result["success"]:
                    logger.error(f"❌ SCHEDULED OPEN {poll_id} - Failed: {result.get('error')}")
                else:
                    logger.info(f"✅ SCHEDULED OPEN {poll_id} - Success: {result.get('message')}")
                return result

            # Schedule poll to open at the specified time using unified opening service
            success_open = tz_scheduler.schedule_poll_opening(
                poll_id, open_dt, timezone_str, open_poll_scheduled_wrapper, bot
            )
            if not success_open:
                logger.error(f"Failed to schedule poll {poll_id} opening")
                await PollErrorHandler.handle_scheduler_error(
                    Exception("Failed to schedule poll opening"),
                    poll_id,
                    "poll_opening",
                    bot,
                )

            # Schedule poll to close
            success_close = tz_scheduler.schedule_poll_closing(
                poll_id, close_dt, timezone_str, close_poll
            )
            if not success_close:
                logger.error(f"Failed to schedule poll {poll_id} closing")
                await PollErrorHandler.handle_scheduler_error(
                    Exception("Failed to schedule poll closing"),
                    poll_id,
                    "poll_closure",
                    bot,
                )

        except Exception as scheduling_error:
            logger.error(
                f"Critical scheduling error for poll {poll_id}: {scheduling_error}"
            )
            await PollErrorHandler.handle_scheduler_error(
                scheduling_error, poll_id, "poll_scheduling", bot
            )

        # Save user preferences for next time
        save_user_preferences(
            current_user.id, server_id, channel_id, ping_role_id, timezone_str
        )

        # Invalidate user polls cache after successful creation
        await invalidate_user_polls_cache(current_user.id)

        # Return success message and redirect to polls view
        return templates.TemplateResponse(
            "htmx/components/alert_success.html",
            {
                "request": request,
                "message": "Poll created successfully! Redirecting to polls...",
                "redirect_url": "/htmx/polls",
            },
        )

    except Exception as e:
        logger.error(f"Error creating poll for user {current_user.id}: {e}")
        logger.exception("Full traceback for poll creation error:")

        # Use error handler for comprehensive error handling
        poll_name = locals().get("name", "Unknown")
        error_msg = await PollErrorHandler.handle_poll_creation_error(
            e, {"name": poll_name, "user_id": current_user.id}, bot
        )
        return templates.TemplateResponse(
            "htmx/components/inline_error.html",
            {"request": request, "message": error_msg},
        )


async def get_poll_details_htmx(
    poll_id: int, request: Request, bot, current_user: DiscordUser = Depends(require_auth)
):
    """Get poll details view as HTML for HTMX - serves pre-generated static files for closed polls"""
    logger.info(f"User {current_user.id} requesting details for poll {poll_id}")
    db = get_db_session()
    try:
        poll = (
            db.query(Poll)
            .filter(Poll.id == poll_id, Poll.creator_id == current_user.id)
            .first()
        )
        if not poll:
            logger.warning(
                f"Poll {poll_id} not found or not owned by user {current_user.id}"
            )
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {"request": request, "message": "Poll not found or access denied"},
            )

        # Check if poll is closed and serve pre-generated static content
        poll_status = TypeSafeColumn.get_string(poll, "status")
        if poll_status == "closed":
            logger.info(f"📄 STATIC SERVE - Checking for pre-generated static content for closed poll {poll_id}")
            
            # Import the static page generator to check for existing files
            from .static_page_generator import get_static_page_generator
            
            # Get the static page generator instance
            static_generator = get_static_page_generator()
            
            # Check if static file exists
            static_path = static_generator._get_static_page_path(poll_id, "details")
            
            if static_path.exists():
                logger.info(f"✅ STATIC SERVE - Found pre-generated static file for poll {poll_id}: {static_path}")
                
                # Read and serve the pre-generated static content
                try:
                    with open(static_path, 'r', encoding='utf-8') as f:
                        static_content = f.read()
                    
                    logger.info(f"📄 STATIC SERVE - Successfully served pre-generated static content for poll {poll_id}")
                    
                    # Return the static content directly as HTML response
                    from fastapi.responses import HTMLResponse
                    return HTMLResponse(content=static_content)
                    
                except Exception as read_error:
                    logger.error(f"❌ STATIC SERVE - Error reading static file for poll {poll_id}: {read_error}")
                    # Fall through to dynamic content as fallback
            else:
                logger.warning(f"⚠️ STATIC SERVE - No pre-generated static file found for poll {poll_id}: {static_path}")
                logger.warning("⚠️ STATIC SERVE - Expected file should exist for closed polls - this indicates a problem with static generation")
                
                # Try to regenerate the static file once if it's missing
                logger.info(f"🔄 STATIC SERVE - Attempting to regenerate missing static content for closed poll {poll_id}")
                try:
                    regeneration_success = await static_generator.generate_static_poll_details(poll_id, bot)
                    if regeneration_success and static_path.exists():
                        logger.info(f"✅ STATIC SERVE - Successfully regenerated static content for poll {poll_id}")
                        
                        # Try to serve the newly generated content
                        try:
                            with open(static_path, 'r', encoding='utf-8') as f:
                                static_content = f.read()
                            
                            logger.info(f"📄 STATIC SERVE - Successfully served regenerated static content for poll {poll_id}")
                            
                            # Return the static content directly as HTML response
                            from fastapi.responses import HTMLResponse
                            return HTMLResponse(content=static_content)
                            
                        except Exception as read_error:
                            logger.error(f"❌ STATIC SERVE - Error reading regenerated static file for poll {poll_id}: {read_error}")
                    else:
                        logger.error(f"❌ STATIC SERVE - Failed to regenerate static content for poll {poll_id}")
                        
                except Exception as regen_error:
                    logger.error(f"❌ STATIC SERVE - Error during static content regeneration for poll {poll_id}: {regen_error}")
            
            # For closed polls, we should NOT regenerate on-demand repeatedly - that defeats the purpose
            # Instead, fall back to dynamic content and log this as an issue
            logger.warning(f"⚠️ STATIC SERVE - Falling back to dynamic content for closed poll {poll_id} - static file missing or unreadable")

        # Serve dynamic content for active/scheduled polls or as fallback for closed polls
        return templates.TemplateResponse(
            "htmx/poll_details.html",
            {
                "request": request,
                "poll": poll,
                "format_datetime_for_user": format_datetime_for_user,
            },
        )
    except Exception as e:
        logger.error(f"Error getting poll details for poll {poll_id}: {e}")
        return templates.TemplateResponse(
            "htmx/components/inline_error.html",
            {"request": request, "message": f"Error loading template: {str(e)}"},
        )
    finally:
        db.close()


async def get_poll_results_realtime_htmx(
    poll_id: int, request: Request, current_user: DiscordUser = Depends(require_auth)
):
    """Get real-time poll results as HTML for HTMX with caching optimized for 10-second polling intervals"""
    from .enhanced_cache_service import get_enhanced_cache_service

    enhanced_cache = get_enhanced_cache_service()

    logger.debug(
        f"🔍 RESULTS REALTIME DEBUG - Starting realtime results request for poll {poll_id} by user {current_user.id}"
    )

    # Check cache first (10 second TTL for results data to match polling interval)
    cached_results = await enhanced_cache.get_cached_live_poll_results(poll_id)
    if cached_results:
        logger.debug(
            f"🚀 RESULTS CACHE HIT - Retrieved cached results for poll {poll_id}"
        )
        poll_status = cached_results.get("poll_status", "active")

        # If poll is closed, return cached static results without realtime polling
        if poll_status == "closed":
            logger.debug(
                f"📊 POLL CLOSED - Returning static cached results for poll {poll_id}"
            )
            return cached_results.get(
                "html_content",
                '<div class="alert alert-info">Poll results are no longer updating</div>',
            )

        # If poll is active, return cached results (will continue polling)
        return cached_results.get(
            "html_content",
            '<div class="alert alert-danger">Error loading poll results</div>',
        )

    # Cache miss - generate results data
    logger.debug(f"🔍 RESULTS CACHE MISS - Generating results for poll {poll_id}")

    db = get_db_session()
    try:
        poll = (
            db.query(Poll)
            .filter(Poll.id == poll_id, Poll.creator_id == current_user.id)
            .first()
        )
        if not poll:
            return (
                '<div class="alert alert-danger">Poll not found or access denied</div>'
            )

        # Get poll status - CRITICAL: Check if poll is closed to disable streaming
        poll_status = TypeSafeColumn.get_string(poll, "status", "active")
        logger.debug(f"📊 POLL STATUS - Poll {poll_id} status is '{poll_status}'")

        # Get poll results
        total_votes = poll.get_total_votes()
        results = poll.get_results()

        # Get poll data safely
        options = poll.options  # Use the property method from Poll model
        emojis = poll.emojis  # Use the property method from Poll model
        is_anonymous = TypeSafeColumn.get_bool(poll, "anonymous", False)

        # Generate HTML for results
        html_parts = []

        for i in range(len(options)):
            option_votes = results.get(i, 0)
            percentage = (option_votes / total_votes * 100) if total_votes > 0 else 0
            emoji = (
                emojis[i]
                if i < len(emojis)
                else POLL_EMOJIS[min(i, len(POLL_EMOJIS) - 1)]
            )
            option_text = options[i]

            html_parts.append(
                f"""
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
            """
            )

        # Add total votes and anonymous badge
        anonymous_badge = (
            '<span class="badge bg-info ms-2">Anonymous</span>' if is_anonymous else ""
        )

        # Add status indicator for closed polls
        status_indicator = ""
        if poll_status == "closed":
            status_indicator = '<div class="alert alert-info mt-2"><i class="fas fa-info-circle me-1"></i>This poll is closed. Results are final.</div>'

        html_parts.append(
            f"""
        <div class="mt-3">
            <strong>Total Votes: {total_votes}</strong>
            {anonymous_badge}
        </div>
        {status_indicator}
        """
        )

        html_content = "".join(html_parts)

        # Cache the results with status-aware TTL (10s for active, 7 days for closed)
        cacheable_data = {
            "html_content": html_content,
            "poll_status": poll_status,
            "total_votes": total_votes,
            "results": results,
            "cached_at": datetime.now().isoformat(),
        }

        await enhanced_cache.cache_live_poll_results(poll_id, cacheable_data, poll_status)
        ttl_description = "7 days" if poll_status == "closed" else "10s"
        logger.debug(
            f"💾 RESULTS CACHED - Stored results for poll {poll_id} (status: {poll_status}) with {ttl_description} TTL"
        )

        return html_content

    except Exception as e:
        logger.error(f"Error getting real-time results for poll {poll_id}: {e}")
        return '<div class="alert alert-danger">Error loading poll results</div>'
    finally:
        db.close()


async def get_poll_dashboard_htmx(
    poll_id: int,
    request: Request,
    bot,
    current_user: DiscordUser = Depends(require_auth),
):
    """Get poll dashboard with spreadsheet-style live results for HTMX with caching optimized for 10-second polling"""
    from .enhanced_cache_service import get_enhanced_cache_service

    enhanced_cache = get_enhanced_cache_service()

    logger.info(
        f"🔍 DASHBOARD DEBUG - Starting dashboard request for poll {poll_id} by user {current_user.id}"
    )

    # Check cache first (10 second TTL for dashboard data to match polling interval)
    cached_dashboard = await enhanced_cache.get_cached_poll_dashboard(poll_id)
    if cached_dashboard:
        logger.info(
            f"🚀 DASHBOARD CACHE HIT - Retrieved cached dashboard for poll {poll_id}"
        )
        logger.info(
            f"🔍 DASHBOARD DEBUG - Cached data keys: {list(cached_dashboard.keys())}"
        )
        logger.info(
            f"🔍 DASHBOARD DEBUG - Cached total_votes: {cached_dashboard.get('total_votes', 'NOT_FOUND')}"
        )
        logger.info(
            f"🔍 DASHBOARD DEBUG - Cached unique_voters: {cached_dashboard.get('unique_voters', 'NOT_FOUND')}"
        )
        logger.info(
            f"🔍 DASHBOARD DEBUG - Cached results: {cached_dashboard.get('results', 'NOT_FOUND')}"
        )
        logger.info(
            f"🔍 DASHBOARD DEBUG - Cached vote_data length: {len(cached_dashboard.get('vote_data', []))}"
        )

        # We still need to get the Poll object for the template since it's not cached
        db = get_db_session()
        try:
            poll = (
                db.query(Poll)
                .filter(Poll.id == poll_id, Poll.creator_id == current_user.id)
                .first()
            )
            if not poll:
                logger.error(
                    f"🔍 DASHBOARD DEBUG - Poll {poll_id} not found or access denied for user {current_user.id}"
                )
                return templates.TemplateResponse(
                    "htmx/components/inline_error.html",
                    {"request": request, "message": "Poll not found or access denied"},
                )

            logger.info(f"🔍 DASHBOARD DEBUG - Poll object retrieved: {poll.id}")

            # Convert cached vote data back to template-friendly format
            # The cached data has ISO strings, but templates need datetime objects
            cached_vote_data = cached_dashboard.get("vote_data", [])
            template_vote_data = []

            logger.info(
                f"🔍 DASHBOARD DEBUG - Processing {len(cached_vote_data)} cached votes"
            )

            for i, vote in enumerate(cached_vote_data):
                template_vote = vote.copy()
                # Convert ISO string back to datetime object for template use
                if vote.get("voted_at"):
                    try:
                        template_vote["voted_at"] = datetime.fromisoformat(
                            vote["voted_at"].replace("Z", "+00:00")
                        )
                    except (ValueError, AttributeError) as e:
                        logger.warning(
                            f"Error parsing cached datetime {vote.get('voted_at')}: {e}"
                        )
                        template_vote["voted_at"] = None
                else:
                    template_vote["voted_at"] = None
                template_vote_data.append(template_vote)

                if i < 3:  # Log first 3 votes for debugging
                    logger.info(
                        f"🔍 DASHBOARD DEBUG - Vote {i + 1}: user_id={vote.get('user_id', 'MISSING')}, option_index={vote.get('option_index', 'MISSING')}"
                    )

            # Always calculate fresh summary statistics from the Poll model to avoid cache corruption
            logger.info("🔍 DASHBOARD DEBUG - Calculating fresh summary statistics")
            fresh_total_votes = poll.get_total_votes()
            fresh_unique_voters = len(
                set(vote["user_id"] for vote in template_vote_data)
            )
            fresh_results = poll.get_results()

            logger.info("🔍 DASHBOARD DEBUG - Fresh calculations:")
            logger.info(f"🔍 DASHBOARD DEBUG - fresh_total_votes: {fresh_total_votes}")
            logger.info(
                f"🔍 DASHBOARD DEBUG - fresh_unique_voters: {fresh_unique_voters}"
            )
            logger.info(f"🔍 DASHBOARD DEBUG - fresh_results: {fresh_results}")

            # Compare with cached values
            cached_total = cached_dashboard.get("total_votes", "NOT_FOUND")
            cached_unique = cached_dashboard.get("unique_voters", "NOT_FOUND")
            cached_results = cached_dashboard.get("results", "NOT_FOUND")

            logger.info("🔍 DASHBOARD DEBUG - Comparison with cached values:")
            logger.info(
                f"🔍 DASHBOARD DEBUG - total_votes: fresh={fresh_total_votes} vs cached={cached_total}"
            )
            logger.info(
                f"🔍 DASHBOARD DEBUG - unique_voters: fresh={fresh_unique_voters} vs cached={cached_unique}"
            )
            logger.info(
                f"🔍 DASHBOARD DEBUG - results: fresh={fresh_results} vs cached={cached_results}"
            )

            # Add the non-cacheable objects to the cached data, but use fresh summary stats
            template_data = {
                "poll": poll,
                "vote_data": template_vote_data,  # Use converted vote data with datetime objects
                "total_votes": fresh_total_votes,  # Always use fresh calculation
                "unique_voters": fresh_unique_voters,  # Always use fresh calculation
                "results": fresh_results,  # Always use fresh calculation
                "format_datetime_for_user": format_datetime_for_user,
                **{
                    k: v
                    for k, v in cached_dashboard.items()
                    if k not in ["vote_data", "total_votes", "unique_voters", "results"]
                },  # Exclude vote_data and summary stats
            }

            logger.info("🔍 DASHBOARD DEBUG - Final template_data summary:")
            logger.info(
                f"🔍 DASHBOARD DEBUG - template_data total_votes: {template_data.get('total_votes', 'MISSING')}"
            )
            logger.info(
                f"🔍 DASHBOARD DEBUG - template_data unique_voters: {template_data.get('unique_voters', 'MISSING')}"
            )
            logger.info(
                f"🔍 DASHBOARD DEBUG - template_data results: {template_data.get('results', 'MISSING')}"
            )
            logger.info(
                f"🔍 DASHBOARD DEBUG - template_data vote_data length: {len(template_data.get('vote_data', []))}"
            )

            return templates.TemplateResponse(
                "htmx/components/poll_dashboard.html",
                {"request": request, **template_data},
            )
        finally:
            db.close()

    # Cache miss - generate dashboard data
    logger.debug(f"🔍 DASHBOARD CACHE MISS - Generating dashboard for poll {poll_id}")

    db = get_db_session()
    try:
        poll = (
            db.query(Poll)
            .filter(Poll.id == poll_id, Poll.creator_id == current_user.id)
            .first()
        )
        if not poll:
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {"request": request, "message": "Poll not found or access denied"},
            )

        # Get all votes for this poll with user information
        votes = (
            db.query(Vote)
            .filter(Vote.poll_id == poll_id)
            .order_by(Vote.voted_at.desc())
            .all()
        )

        # Get poll data safely
        options = poll.options
        emojis = poll.emojis
        is_anonymous = TypeSafeColumn.get_bool(poll, "anonymous", False)

        # IMPORTANT: Poll creators always see usernames, even for anonymous polls
        # This allows poll creators to see who voted while maintaining anonymity for other users
        show_usernames_to_creator = True

        # Prepare vote data with Discord usernames (with caching)
        vote_data = []
        unique_users = set()

        for vote in votes:
            try:
                user_id = TypeSafeColumn.get_string(vote, "user_id")
                option_index = TypeSafeColumn.get_int(vote, "option_index")
                voted_at = TypeSafeColumn.get_datetime(vote, "voted_at")

                # Get Discord user information with caching and avatar optimization
                username = "Unknown User"
                avatar_url = None
                cached_avatar_url = None

                if bot and user_id:
                    # Check cache for Discord user data first
                    cached_user = await enhanced_cache.get_cached_discord_user(user_id)
                    if cached_user:
                        username = cached_user.get("username", "Unknown User")
                        avatar_url = cached_user.get("avatar_url")
                    else:
                        # Fetch from Discord API and cache
                        try:
                            discord_user = await bot.fetch_user(int(user_id))
                            if discord_user:
                                username = (
                                    discord_user.display_name or discord_user.name
                                )
                                avatar_url = (
                                    discord_user.avatar.url
                                    if discord_user.avatar
                                    else None
                                )

                                # Cache Discord user data for 30 minutes
                                user_data = {
                                    "username": username,
                                    "avatar_url": avatar_url,
                                    "cached_at": datetime.now().isoformat(),
                                }
                                await enhanced_cache.cache_discord_user(
                                    user_id, user_data
                                )
                        except Exception as e:
                            logger.warning(
                                f"Could not fetch Discord user {user_id}: {e}"
                            )
                            username = f"User {user_id[:8]}..."

                    # Cache user avatar with deduplication and optimization
                    if avatar_url:
                        try:
                            from .avatar_cache_service import get_avatar_cache_service
                            avatar_service = get_avatar_cache_service()
                            cached_avatar_url = await avatar_service.cache_user_avatar(user_id, avatar_url, username)
                            if cached_avatar_url:
                                logger.debug(f"🖼️ AVATAR CACHED - User {user_id}: {cached_avatar_url}")
                        except Exception as e:
                            logger.warning(f"Error caching avatar for user {user_id}: {e}")

                # Get option details
                option_text = (
                    options[option_index]
                    if option_index < len(options)
                    else "Unknown Option"
                )
                emoji = (
                    emojis[option_index]
                    if option_index < len(emojis)
                    else POLL_EMOJIS[min(option_index, len(POLL_EMOJIS) - 1)]
                )

                vote_data.append(
                    {
                        "user_id": user_id,
                        "username": username,
                        "avatar_url": cached_avatar_url or avatar_url,  # Use cached avatar if available
                        "option_index": option_index,
                        "option_text": option_text,
                        "emoji": emoji,
                        "voted_at": (
                            voted_at.isoformat()
                            if voted_at and isinstance(voted_at, datetime)
                            else None
                        ),  # Convert datetime to ISO string for JSON serialization
                        "voted_at_datetime": voted_at,  # Keep original datetime for template use
                        "is_unique": user_id not in unique_users,
                    }
                )

                unique_users.add(user_id)

            except Exception as e:
                logger.error(f"Error processing vote data: {e}")
                continue

        # Get summary statistics
        total_votes = len(votes)
        unique_voters = len(unique_users)
        results = poll.get_results()

        # Prepare cacheable data (exclude non-serializable objects like Poll and functions)
        # Create a JSON-serializable version of vote_data without datetime objects
        cacheable_vote_data = []
        for vote in vote_data:
            cacheable_vote = vote.copy()
            # Remove the datetime object, keep only the ISO string
            if "voted_at_datetime" in cacheable_vote:
                del cacheable_vote["voted_at_datetime"]
            cacheable_vote_data.append(cacheable_vote)

        cacheable_data = {
            "vote_data": cacheable_vote_data,  # Use JSON-serializable version
            "total_votes": total_votes,
            "unique_voters": unique_voters,
            "results": results,
            "options": options,
            "emojis": emojis,
            "is_anonymous": is_anonymous,
            "show_usernames_to_creator": show_usernames_to_creator,
        }

        # Sanitize all data to prevent JSON serialization errors
        sanitized_cacheable_data = sanitize_data_for_json(cacheable_data)

        # Determine poll status for TTL selection
        poll_status = TypeSafeColumn.get_string(poll, "status", "active")
        # Cache with status-aware TTL (10s for active, 7 days for closed)
        await enhanced_cache.cache_poll_dashboard(poll_id, sanitized_cacheable_data, poll_status)
        ttl_description = "7 days" if poll_status == "closed" else "10s"
        logger.debug(
            f"💾 DASHBOARD CACHED - Stored dashboard for poll {poll_id} (status: {poll_status}) with {ttl_description} TTL"
        )

        # Prepare full template data (including non-cacheable objects)
        template_data = {
            "poll": poll,
            "vote_data": vote_data,  # Use original vote_data with datetime objects for template
            "total_votes": total_votes,
            "unique_voters": unique_voters,
            "results": results,
            "options": options,
            "emojis": emojis,
            "is_anonymous": is_anonymous,
            "show_usernames_to_creator": show_usernames_to_creator,
            "format_datetime_for_user": format_datetime_for_user,
        }

        return templates.TemplateResponse(
            "htmx/components/poll_dashboard.html", {"request": request, **template_data}
        )

    except Exception as e:
        logger.error(f"Error getting poll dashboard for poll {poll_id}: {e}")
        return templates.TemplateResponse(
            "htmx/components/inline_error.html",
            {"request": request, "message": f"Error loading poll dashboard: {str(e)}"},
        )
    finally:
        db.close()


async def export_poll_csv(
    poll_id: int,
    request: Request,
    bot,
    current_user: DiscordUser = Depends(require_auth),
):
    """Export poll results as CSV - Poll creators always see usernames, even for anonymous polls"""
    import csv
    import io

    # Add comprehensive debugging
    logger.info(
        f"🔍 CSV EXPORT DEBUG - Function called! Starting CSV export for poll {poll_id} by user {current_user.id}"
    )
    print(
        f"🔍 CSV EXPORT DEBUG - Function called! Starting CSV export for poll {poll_id} by user {current_user.id}"
    )

    # Log request details
    logger.info(f"🔍 CSV EXPORT DEBUG - Request method: {request.method}")
    logger.info(f"🔍 CSV EXPORT DEBUG - Request URL: {request.url}")
    logger.info(f"🔍 CSV EXPORT DEBUG - Request headers: {dict(request.headers)}")
    print(f"🔍 CSV EXPORT DEBUG - Request method: {request.method}")
    print(f"🔍 CSV EXPORT DEBUG - Request URL: {request.url}")
    print(
        f"🔍 CSV EXPORT DEBUG - User agent: {request.headers.get('user-agent', 'Not provided')}"
    )

    # Add function entry confirmation
    logger.info(
        "🔍 CSV EXPORT DEBUG - ✅ Function execution confirmed - we are inside export_poll_csv"
    )
    print(
        "🔍 CSV EXPORT DEBUG - ✅ Function execution confirmed - we are inside export_poll_csv"
    )

    db = get_db_session()
    try:
        logger.info("🔍 CSV EXPORT DEBUG - Database session created successfully")
        print("🔍 CSV EXPORT DEBUG - Database session created successfully")

        # Query for poll with detailed logging
        logger.info(
            f"🔍 CSV EXPORT DEBUG - Querying for poll {poll_id} owned by user {current_user.id}"
        )
        print(
            f"🔍 CSV EXPORT DEBUG - Querying for poll {poll_id} owned by user {current_user.id}"
        )

        poll = (
            db.query(Poll)
            .filter(Poll.id == poll_id, Poll.creator_id == current_user.id)
            .first()
        )

        if not poll:
            logger.error(
                f"🔍 CSV EXPORT DEBUG - Poll {poll_id} not found or access denied for user {current_user.id}"
            )
            print(
                f"🔍 CSV EXPORT DEBUG - Poll {poll_id} not found or access denied for user {current_user.id}"
            )
            from fastapi import HTTPException

            raise HTTPException(
                status_code=404, detail="Poll not found or access denied"
            )

        logger.info(f"🔍 CSV EXPORT DEBUG - Poll found successfully: {poll.id}")
        print(f"🔍 CSV EXPORT DEBUG - Poll found successfully: {poll.id}")

        # Get poll basic info with debugging
        poll_name = TypeSafeColumn.get_string(poll, "name", "Unknown Poll")
        is_anonymous = TypeSafeColumn.get_bool(poll, "anonymous", False)
        logger.info(
            f"🔍 CSV EXPORT DEBUG - Poll name: '{poll_name}', anonymous: {is_anonymous}"
        )
        print(
            f"🔍 CSV EXPORT DEBUG - Poll name: '{poll_name}', anonymous: {is_anonymous}"
        )

        # Get all votes for this poll with detailed logging
        logger.info(f"🔍 CSV EXPORT DEBUG - Querying votes for poll {poll_id}")
        print(f"🔍 CSV EXPORT DEBUG - Querying votes for poll {poll_id}")

        votes = (
            db.query(Vote)
            .filter(Vote.poll_id == poll_id)
            .order_by(Vote.voted_at.desc())
            .all()
        )

        logger.info(
            f"🔍 CSV EXPORT DEBUG - Found {len(votes)} votes for poll {poll_id}"
        )
        print(f"🔍 CSV EXPORT DEBUG - Found {len(votes)} votes for poll {poll_id}")

        # Get poll data with debugging
        options = poll.options
        emojis = poll.emojis
        logger.info(
            f"🔍 CSV EXPORT DEBUG - Poll has {len(options)} options and {len(emojis)} emojis"
        )
        print(
            f"🔍 CSV EXPORT DEBUG - Poll has {len(options)} options and {len(emojis)} emojis"
        )

        # Log first few options for debugging
        for i, option in enumerate(options[:3]):
            logger.info(f"🔍 CSV EXPORT DEBUG - Option {i}: '{option}'")
            print(f"🔍 CSV EXPORT DEBUG - Option {i}: '{option}'")

        # Create CSV content with debugging
        logger.info("🔍 CSV EXPORT DEBUG - Creating CSV content")
        print("🔍 CSV EXPORT DEBUG - Creating CSV content")

        output = io.StringIO()
        writer = csv.writer(output)

        # Write header - include poll anonymity status for reference
        header_row = [
            "Poll Name",
            "Poll Type",
            "Voter Username",
            "Voter ID",
            "Option Selected",
            "Option Index",
            "Emoji",
            "Vote Time (UTC)",
            "Vote Time (Local)",
        ]
        writer.writerow(header_row)
        logger.info(f"🔍 CSV EXPORT DEBUG - CSV header written: {header_row}")
        print("🔍 CSV EXPORT DEBUG - CSV header written successfully")

        # Get user timezone for local time display
        logger.info("🔍 CSV EXPORT DEBUG - Getting user preferences for timezone")
        print("🔍 CSV EXPORT DEBUG - Getting user preferences for timezone")

        user_prefs = get_user_preferences(current_user.id)
        user_timezone = user_prefs.get("default_timezone", "US/Eastern")
        logger.info(f"🔍 CSV EXPORT DEBUG - User timezone: {user_timezone}")
        print(f"🔍 CSV EXPORT DEBUG - User timezone: {user_timezone}")

        poll_type = "Anonymous" if is_anonymous else "Public"
        logger.info(f"🔍 CSV EXPORT DEBUG - Poll type: {poll_type}")
        print(f"🔍 CSV EXPORT DEBUG - Poll type: {poll_type}")

        # Write vote data - IMPORTANT: Poll creators always see usernames, even for anonymous polls
        logger.info(
            f"🔍 CSV EXPORT DEBUG - Processing {len(votes)} votes for CSV export"
        )
        print(f"🔍 CSV EXPORT DEBUG - Processing {len(votes)} votes for CSV export")

        processed_votes = 0
        failed_votes = 0

        for i, vote in enumerate(votes):
            try:
                logger.debug(
                    f"🔍 CSV EXPORT DEBUG - Processing vote {i + 1}/{len(votes)}"
                )

                user_id = TypeSafeColumn.get_string(vote, "user_id")
                option_index = TypeSafeColumn.get_int(vote, "option_index")
                voted_at = TypeSafeColumn.get_datetime(vote, "voted_at")

                if i < 3:  # Log details for first 3 votes
                    logger.info(
                        f"🔍 CSV EXPORT DEBUG - Vote {i + 1}: user_id={user_id}, option_index={option_index}, voted_at={voted_at}"
                    )
                    print(
                        f"🔍 CSV EXPORT DEBUG - Vote {i + 1}: user_id={user_id}, option_index={option_index}"
                    )

                # Get Discord username - always fetch for poll creator
                username = "Unknown User"
                if bot and user_id:
                    try:
                        logger.debug(
                            f"🔍 CSV EXPORT DEBUG - Fetching Discord user {user_id}"
                        )
                        discord_user = await bot.fetch_user(int(user_id))
                        if discord_user:
                            username = discord_user.display_name or discord_user.name
                            if i < 3:  # Log details for first 3 users
                                logger.info(
                                    f"🔍 CSV EXPORT DEBUG - Fetched username for vote {i + 1}: '{username}'"
                                )
                                print(
                                    f"🔍 CSV EXPORT DEBUG - Fetched username for vote {i + 1}: '{username}'"
                                )
                    except Exception as e:
                        logger.warning(
                            f"🔍 CSV EXPORT DEBUG - Could not fetch Discord user {user_id}: {e}"
                        )
                        username = f"User {user_id[:8]}..."

                # Get option details
                option_text = (
                    options[option_index]
                    if option_index < len(options)
                    else "Unknown Option"
                )
                emoji = (
                    emojis[option_index]
                    if option_index < len(emojis)
                    else POLL_EMOJIS[min(option_index, len(POLL_EMOJIS) - 1)]
                )

                # Format times
                utc_time = "Unknown"
                local_time = "Unknown"
                if voted_at and isinstance(voted_at, datetime):
                    utc_time = voted_at.strftime("%Y-%m-%d %H:%M:%S UTC")
                    local_time = format_datetime_for_user(voted_at, user_timezone)

                # Write the row
                row_data = [
                    poll_name,
                    poll_type,
                    username,  # Always show username to poll creator
                    user_id,
                    option_text,
                    option_index,
                    emoji,
                    utc_time,
                    local_time,
                ]
                writer.writerow(row_data)
                processed_votes += 1

                if i < 3:  # Log details for first 3 rows
                    logger.info(
                        f"🔍 CSV EXPORT DEBUG - Row {i + 1} written: {row_data[:4]}..."
                    )  # Log first 4 fields
                    print(f"🔍 CSV EXPORT DEBUG - Row {i + 1} written successfully")

            except Exception as e:
                failed_votes += 1
                logger.error(
                    f"🔍 CSV EXPORT DEBUG - Error processing vote {i + 1} for CSV export: {e}"
                )
                print(f"🔍 CSV EXPORT DEBUG - Error processing vote {i + 1}: {e}")
                continue

        logger.info(
            f"🔍 CSV EXPORT DEBUG - Vote processing complete: {processed_votes} successful, {failed_votes} failed"
        )
        print(
            f"🔍 CSV EXPORT DEBUG - Vote processing complete: {processed_votes} successful, {failed_votes} failed"
        )

        # Prepare response
        logger.info("🔍 CSV EXPORT DEBUG - Preparing CSV response")
        print("🔍 CSV EXPORT DEBUG - Preparing CSV response")

        output.seek(0)
        csv_content = output.getvalue()
        csv_size = len(csv_content)

        logger.info(f"🔍 CSV EXPORT DEBUG - CSV content size: {csv_size} characters")
        print(f"🔍 CSV EXPORT DEBUG - CSV content size: {csv_size} characters")

        # Create filename
        safe_poll_name = "".join(
            c for c in poll_name if c.isalnum() or c in (" ", "-", "_")
        ).rstrip()
        filename = f"poll_results_{safe_poll_name}_{poll_id}.csv"

        logger.info(f"🔍 CSV EXPORT DEBUG - Generated filename: '{filename}'")
        print(f"🔍 CSV EXPORT DEBUG - Generated filename: '{filename}'")

        # CSV content ready for response
        # Return CSV as a file download
        from fastapi.responses import Response

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "text/csv",
            "Cache-Control": "no-cache"
        }

        logger.info("🔍 CSV EXPORT DEBUG - Returning CSV Response with attachment headers")
        print("🔍 CSV EXPORT DEBUG - Returning CSV Response with attachment headers")
        return Response(content=csv_content, media_type="text/csv", headers=headers)

    except Exception as e:
        logger.error(f"❌ CSV EXPORT DEBUG - Error exporting CSV for poll {poll_id}: {e}")
        logger.exception("Full traceback for CSV export error:")
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"Error exporting CSV: {str(e)}")
    finally:
        db.close()


async def export_poll_json_htmx(
    poll_id: int, request: Request, current_user: DiscordUser = Depends(require_auth)
):
    """Export poll as JSON file via HTMX"""
    from fastapi.responses import Response

    logger.info(
        f"🔍 JSON EXPORT - User {current_user.id} starting export for poll {poll_id}"
    )
    db = get_db_session()
    try:
        poll = (
            db.query(Poll)
            .filter(Poll.id == poll_id, Poll.creator_id == current_user.id)
            .first()
        )
        if not poll:
            logger.warning(
                f"⚠️ JSON EXPORT - Poll {poll_id} not found or access denied for user {current_user.id}"
            )
            from fastapi import HTTPException

            raise HTTPException(
                status_code=404, detail="Poll not found or access denied"
            )

        poll_name = TypeSafeColumn.get_string(poll, "name", "Unknown Poll")
        logger.info(f"🔍 JSON EXPORT - Exporting poll: '{poll_name}' (ID: {poll_id})")

        # Export poll to JSON
        json_string = PollJSONExporter.export_poll_to_json_string(poll, indent=2)
        filename = PollJSONExporter.generate_filename(poll)

        logger.info(
            f"✅ JSON EXPORT - Successfully exported poll {poll_id} as '{filename}' for user {current_user.id}"
        )

        return Response(
            content=json_string,
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except Exception as e:
        logger.error(
            f"❌ JSON EXPORT - Error exporting poll {poll_id} for user {current_user.id}: {e}"
        )
        logger.exception("Full traceback for JSON export error:")
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail=f"Error exporting JSON: {str(e)}")
    finally:
        db.close()


async def delete_poll_htmx(
    poll_id: int, request: Request, current_user: DiscordUser = Depends(require_auth)
):
    """Delete a scheduled or closed poll via HTMX"""
    logger.info(f"User {current_user.id} requesting to delete poll {poll_id}")
    db = get_db_session()
    try:
        poll = (
            db.query(Poll)
            .filter(Poll.id == poll_id, Poll.creator_id == current_user.id)
            .first()
        )
        if not poll:
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {"request": request, "message": "Poll not found or access denied"},
            )

        poll_status = TypeSafeColumn.get_string(poll, "status")
        if poll_status not in ["scheduled", "closed"]:
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {
                    "request": request,
                    "message": "Only scheduled or closed polls can be deleted",
                },
            )

        # Clean up image file if exists
        image_path = TypeSafeColumn.get_string(poll, "image_path")
        if image_path:
            await cleanup_image(str(image_path))

        # Delete associated votes first
        db.query(Vote).filter(Vote.poll_id == poll_id).delete()

        # Delete the poll
        db.delete(poll)
        db.commit()

        logger.info(f"Poll {poll_id} deleted by user {current_user.id}")

        # Invalidate user polls cache after successful deletion
        await invalidate_user_polls_cache(current_user.id)

        return templates.TemplateResponse(
            "htmx/components/alert_success.html",
            {
                "request": request,
                "message": "Poll deleted successfully! Redirecting to polls...",
                "redirect_url": "/htmx/polls",
            },
        )

    except Exception as e:
        logger.error(f"Error deleting poll {poll_id}: {e}")
        db.rollback()
        return templates.TemplateResponse(
            "htmx/components/inline_error.html",
            {"request": request, "message": f"Error deleting poll: {str(e)}"},
        )
    finally:
        db.close()


async def get_poll_edit_form(
    poll_id: int,
    request: Request,
    bot,
    current_user: DiscordUser = Depends(require_auth),
):
    """Get edit form for a scheduled poll"""
    logger.info(f"User {current_user.id} requesting edit form for poll {poll_id}")
    db = get_db_session()
    try:
        poll = (
            db.query(Poll)
            .filter(Poll.id == poll_id, Poll.creator_id == current_user.id)
            .first()
        )
        if not poll:
            logger.warning(
                f"Poll {poll_id} not found or not owned by user {current_user.id}"
            )
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {"request": request, "message": "Poll not found or access denied"},
            )

        if TypeSafeColumn.get_string(poll, "status") != "scheduled":
            logger.warning(
                f"Attempt to edit non-scheduled poll {poll_id} (status: {TypeSafeColumn.get_string(poll, 'status')})"
            )
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {"request": request, "message": "Only scheduled polls can be edited"},
            )

        # Get user's guilds with channels
        user_guilds = await get_user_guilds_with_channels(bot, current_user.id)

        # Get timezones - US/Eastern first as default
        common_timezones = [
            "US/Eastern",
            "UTC",
            "US/Central",
            "US/Mountain",
            "US/Pacific",
            "Europe/London",
            "Europe/Paris",
            "Europe/Berlin",
            "Asia/Tokyo",
            "Asia/Shanghai",
            "Australia/Sydney",
        ]

        # Convert times to local timezone for editing
        poll_timezone = TypeSafeColumn.get_string(poll, "timezone", "UTC")
        tz = pytz.timezone(poll_timezone)

        # Ensure the stored times have timezone info (they should be UTC)
        # Use TypeSafeColumn to get datetime values safely
        open_time_value = TypeSafeColumn.get_datetime(poll, "open_time")
        close_time_value = TypeSafeColumn.get_datetime(poll, "close_time")

        # Ensure we have valid datetime objects before processing
        if not isinstance(open_time_value, datetime) or not isinstance(
            close_time_value, datetime
        ):
            logger.error(f"Invalid datetime values for poll {poll_id}")
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {"request": request, "message": "Error processing poll times"},
            )

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

        open_time = open_time_local.strftime("%Y-%m-%dT%H:%M")
        close_time = close_time_local.strftime("%Y-%m-%dT%H:%M")

        # Prepare timezone data for template
        timezones = []
        for tz_name in common_timezones:
            try:
                tz_obj = pytz.timezone(tz_name)
                offset = datetime.now(tz_obj).strftime("%z")
                timezones.append(
                    {"name": tz_name, "display": f"{tz_name} (UTC{offset})"}
                )
            except (pytz.UnknownTimeZoneError, ValueError, AttributeError) as e:
                logger.warning(f"Error formatting timezone {tz_name}: {e}")
                timezones.append({"name": tz_name, "display": tz_name})

        return templates.TemplateResponse(
            "htmx/edit_form_filepond.html",
            {
                "request": request,
                "poll": poll,
                "guilds": user_guilds,
                "timezones": timezones,
                "open_time": open_time,
                "close_time": close_time,
                "default_emojis": POLL_EMOJIS,
            },
        )
    finally:
        db.close()


async def update_poll_htmx(
    poll_id: int,
    request: Request,
    bot,
    scheduler,
    current_user: DiscordUser = Depends(require_auth),
):
    """Update a scheduled poll"""
    logger.info(f"User {current_user.id} updating poll {poll_id}")
    db = get_db_session()
    try:
        poll = (
            db.query(Poll)
            .filter(Poll.id == poll_id, Poll.creator_id == current_user.id)
            .first()
        )
        if not poll:
            logger.warning(
                f"Poll {poll_id} not found or not owned by user {current_user.id}"
            )
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {"request": request, "message": "Poll not found or access denied"},
            )

        if TypeSafeColumn.get_string(poll, "status") != "scheduled":
            logger.warning(
                f"Attempt to edit non-scheduled poll {poll_id} (status: {TypeSafeColumn.get_string(poll, 'status')})"
            )
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {"request": request, "message": "Only scheduled polls can be edited"},
            )

        form_data = await request.form()

        # RAW FORM DATA DEBUGGING - OUTPUT IMMEDIATELY
        print(f"🔍 RAW FORM DATA DEBUG - Poll {poll_id} edit by user {current_user.id}")
        print(f"🔍 RAW FORM DATA DEBUG - Form data keys: {list(form_data.keys())}")
        logger.info(
            f"🔍 RAW FORM DATA DEBUG - Poll {poll_id} edit by user {current_user.id}"
        )
        logger.info(
            f"🔍 RAW FORM DATA DEBUG - Form data keys: {list(form_data.keys())}"
        )

        # Log ALL form data values
        for key, value in form_data.items():
            print(f"🔍 RAW FORM DATA DEBUG - {key}: '{value}' (type: {type(value)})")
            logger.info(
                f"🔍 RAW FORM DATA DEBUG - {key}: '{value}' (type: {type(value)})"
            )

        # Specifically focus on emoji inputs
        emoji_keys = [key for key in form_data.keys() if key.startswith("emoji")]
        print(
            f"🔍 RAW FORM DATA DEBUG - Found {len(emoji_keys)} emoji keys: {emoji_keys}"
        )
        logger.info(
            f"🔍 RAW FORM DATA DEBUG - Found {len(emoji_keys)} emoji keys: {emoji_keys}"
        )

        for emoji_key in emoji_keys:
            emoji_value = form_data.get(emoji_key)
            print(
                f"🔍 RAW FORM DATA DEBUG - {emoji_key} = '{emoji_value}' (len: {len(str(emoji_value)) if emoji_value else 0})"
            )
            logger.info(
                f"🔍 RAW FORM DATA DEBUG - {emoji_key} = '{emoji_value}' (len: {len(str(emoji_value)) if emoji_value else 0})"
            )

        # Validate form data using the same validation function
        is_valid, validation_errors, validated_data = validate_poll_form_data(
            form_data, current_user.id
        )

        if not is_valid:
            logger.info(
                f"Poll update validation failed for poll {poll_id}: {len(validation_errors)} errors"
            )
            # Log each validation error for debugging
            for i, error in enumerate(validation_errors):
                logger.error(f"Validation error {i + 1}: {error}")
                print(f"🔍 VALIDATION ERROR {i + 1}: {error}")
            
            # Create user-friendly error message from validation errors
            error_messages = []
            for error in validation_errors:
                field_name = error.get("field_name", "Field")
                message = error.get("message", "Invalid value")
                suggestion = error.get("suggestion", "")
                
                error_line = f"**{field_name}**: {message}"
                if suggestion:
                    error_line += f" - {suggestion}"
                error_messages.append(error_line)
            
            combined_error_message = "Please fix the following issues:\n\n" + "\n\n".join(error_messages)
            
            # Return inline error template instead of HTTPException
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {"request": request, "message": combined_error_message},
            )

        # Extract validated data
        name = validated_data["name"]
        question = validated_data["question"]
        server_id = validated_data["server_id"]
        channel_id = validated_data["channel_id"]
        open_dt = validated_data["open_time"]
        close_dt = validated_data["close_time"]
        timezone_str = validated_data["timezone"]
        anonymous = validated_data["anonymous"]
        multiple_choice = validated_data["multiple_choice"]
        ping_role_enabled = validated_data["ping_role_enabled"]
        ping_role_id = validated_data["ping_role_id"]
        image_message_text = validated_data["image_message_text"]

        # Handle image upload
        image_file = form_data.get("image")
        is_valid, error_msg, content = await validate_image_file(image_file)

        if not is_valid:
            logger.warning(f"Image validation failed for poll {poll_id}: {error_msg}")
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {"request": request, "message": error_msg},
            )

        # Save new image if provided
        new_image_path = TypeSafeColumn.get_string(poll, "image_path")
        if (
            content
            and hasattr(image_file, "filename")
            and getattr(image_file, "filename", None)
        ):
            new_image_path = await save_image_file(
                content, str(getattr(image_file, "filename", ""))
            )
            if not new_image_path:
                logger.error(f"Failed to save new image for poll {poll_id}")
                return templates.TemplateResponse(
                    "htmx/components/inline_error.html",
                    {"request": request, "message": "Failed to save image file"},
                )
            # Clean up old image
            old_image_path = TypeSafeColumn.get_string(poll, "image_path")
            if old_image_path:
                await cleanup_image(str(old_image_path))

        # Use unified emoji processor for consistent handling
        unified_processor = get_unified_emoji_processor(bot)

        # Get options from form data
        options = []
        for i in range(1, 11):
            option = form_data.get(f"option{i}")
            if option:
                option_text = str(option).strip()
                options.append(option_text)

        # Extract emoji inputs from form data
        emoji_inputs = unified_processor.extract_emoji_inputs_from_form(
            form_data, len(options)
        )

        # Process emojis using unified processor
        (
            emoji_success,
            emojis,
            emoji_error,
        ) = await unified_processor.process_poll_emojis_unified(
            emoji_inputs, int(server_id), "edit"
        )

        if not emoji_success:
            logger.warning(
                f"Unified emoji processing failed for poll {poll_id} edit: {emoji_error}"
            )
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {"request": request, "message": emoji_error},
            )

        if len(options) < 2:
            logger.warning(f"Insufficient options for poll {poll_id}: {len(options)}")
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {"request": request, "message": "At least 2 options required"},
            )

        # Use the validated times from the validation function
        # open_dt and close_dt are already set in validated_data

        # Normalize timezone for storage
        timezone_str = validate_and_normalize_timezone(timezone_str)

        # Validate times
        now = datetime.now(pytz.UTC)
        next_minute = now.replace(second=0, microsecond=0) + timedelta(minutes=1)

        if open_dt < next_minute:
            # Convert next_minute to user's timezone for display
            user_tz = pytz.timezone(timezone_str)
            next_minute_local = next_minute.astimezone(user_tz)
            suggested_time = next_minute_local.strftime("%I:%M %p")

            logger.warning(
                f"Attempt to schedule poll in the past: {open_dt} < {next_minute}"
            )
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {
                    "request": request,
                    "message": f"Poll open time must be scheduled for the next minute or later. Try {suggested_time} or later.",
                },
            )

        if close_dt <= open_dt:
            logger.warning(
                f"Invalid time range for poll {poll_id}: open={open_dt}, close={close_dt}"
            )
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {"request": request, "message": "Close time must be after open time"},
            )

        # Get server and channel names
        guild = bot.get_guild(int(server_id))
        channel = bot.get_channel(int(channel_id))

        if not guild or not channel:
            logger.error(
                f"Invalid guild or channel for poll {poll_id}: guild={guild}, channel={channel}"
            )
            return templates.TemplateResponse(
                "htmx/components/inline_error.html",
                {"request": request, "message": "Invalid server or channel"},
            )

        # Extract the new role ping settings
        ping_role_on_close = validated_data["ping_role_on_close"]
        ping_role_on_update = validated_data["ping_role_on_update"]

        # Fetch role name if role ping is enabled
        ping_role_name = None
        if ping_role_enabled and ping_role_id:
            try:
                role = guild.get_role(int(ping_role_id))
                if role:
                    ping_role_name = role.name
                    logger.info(
                        f"Fetched role name '{ping_role_name}' for role ID {ping_role_id}"
                    )
                else:
                    logger.warning(
                        f"Role {ping_role_id} not found in guild {server_id}"
                    )
            except Exception as e:
                logger.error(f"Error fetching role name for role {ping_role_id}: {e}")

        # Update poll using setattr to avoid SQLAlchemy Column type issues
        setattr(poll, "name", name)
        setattr(poll, "question", question)
        poll.options = options
        poll.emojis = emojis
        setattr(poll, "image_path", new_image_path)
        setattr(
            poll, "image_message_text", image_message_text if new_image_path else None
        )
        setattr(poll, "server_id", server_id)
        setattr(poll, "server_name", guild.name)
        setattr(poll, "channel_id", channel_id)
        setattr(poll, "channel_name", getattr(channel, "name", "Unknown"))
        setattr(poll, "open_time", open_dt)
        setattr(poll, "close_time", close_dt)
        setattr(poll, "timezone", timezone_str)
        setattr(poll, "anonymous", anonymous)
        setattr(poll, "multiple_choice", multiple_choice)
        setattr(poll, "ping_role_enabled", ping_role_enabled)
        setattr(poll, "ping_role_id", ping_role_id)
        setattr(poll, "ping_role_name", ping_role_name)
        setattr(poll, "ping_role_on_close", ping_role_on_close)
        setattr(poll, "ping_role_on_update", ping_role_on_update)

        db.commit()

        # Update scheduled jobs
        try:
            scheduler.remove_job(f"open_poll_{poll_id}")
        except Exception as e:
            logger.debug(f"Job open_poll_{poll_id} not found or already removed: {e}")
        try:
            scheduler.remove_job(f"close_poll_{poll_id}")
        except Exception as e:
            logger.debug(f"Job close_poll_{poll_id} not found or already removed: {e}")

        # Reschedule jobs using unified opening service
        from .background_tasks import close_poll

        # Create wrapper function for scheduled poll opening using unified service
        async def open_poll_scheduled_wrapper(poll_id):
            """Wrapper function for scheduled poll opening using unified service"""
            from .poll_open_service import poll_opening_service
            
            result = await poll_opening_service.open_poll_unified(
                poll_id=poll_id,
                reason="scheduled",
                bot_instance=bot
            )
            if not result["success"]:
                logger.error(f"❌ SCHEDULED OPEN {poll_id} - Failed: {result.get('error')}")
            else:
                logger.info(f"✅ SCHEDULED OPEN {poll_id} - Success: {result.get('message')}")
            return result

        if open_dt > datetime.now(pytz.UTC):
            scheduler.add_job(
                open_poll_scheduled_wrapper,
                DateTrigger(run_date=open_dt),
                args=[poll_id],
                id=f"open_poll_{poll_id}",
            )

        scheduler.add_job(
            close_poll,
            DateTrigger(run_date=close_dt),
            args=[poll_id],
            id=f"close_poll_{poll_id}",
        )

        logger.info(f"Successfully updated poll {poll_id}")

        # Invalidate user polls cache after successful update
        await invalidate_user_polls_cache(current_user.id)

        return templates.TemplateResponse(
            "htmx/components/alert_success.html",
            {
                "request": request,
                "message": "Poll updated successfully! Redirecting to polls...",
                "redirect_url": "/htmx/polls",
            },
        )

    except Exception as e:
        logger.error(f"Error updating poll {poll_id}: {e}")
        db.rollback()
        return templates.TemplateResponse(
            "htmx/components/inline_error.html",
            {"request": request, "message": f"Error updating poll: {str(e)}"},
        )
    finally:
        db.close()
