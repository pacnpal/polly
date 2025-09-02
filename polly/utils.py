"""
Utility Functions Module
Shared utility functions used across the application.
"""

import logging
import os
import uuid
import aiofiles
from datetime import datetime
import pytz
from typing import Dict, List, Tuple, Optional, Any

logger = logging.getLogger(__name__)


# Image and File Management Utilities
async def cleanup_poll_images(poll_id: int) -> None:
    """Clean up images associated with a poll when it's closed"""
    from .database import get_db_session, Poll, TypeSafeColumn

    db = get_db_session()
    try:
        poll = db.query(Poll).filter(Poll.id == poll_id).first()
        if poll:
            image_path = TypeSafeColumn.get_string(poll, 'image_path')
            if image_path:
                await cleanup_image(image_path)
    except Exception as e:
        logger.error(f"Error cleaning up poll {poll_id} images: {e}")
        from .error_handler import notify_error
        notify_error(e, "Poll Image Cleanup", poll_id=poll_id)
    finally:
        db.close()


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


async def validate_image_file(image_file) -> Tuple[bool, str, Optional[bytes]]:
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


async def save_image_file(content: bytes, filename: str) -> Optional[str]:
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


# Form Data Utilities
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


# Timezone Utilities
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


def get_common_timezones() -> List[Dict[str, str]]:
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


# User Preferences Utilities
def get_user_preferences(user_id: str) -> Dict[str, Any]:
    """Get user preferences for poll creation"""
    from .database import get_db_session, UserPreference

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


def save_user_preferences(user_id: str, server_id: Optional[str] = None,
                          channel_id: Optional[str] = None, timezone: Optional[str] = None):
    """Save user preferences for poll creation"""
    from .database import get_db_session, UserPreference

    db = get_db_session()
    try:
        prefs = db.query(UserPreference).filter(
            UserPreference.user_id == user_id).first()

        if prefs:
            # Update existing preferences using setattr for type safety
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
