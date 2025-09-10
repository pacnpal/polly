"""
Polly Validation System
Comprehensive validation for poll creation, scheduling, and data integrity.
"""

import re
import pytz
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional
import logging
from .database import Poll, Vote, get_db_session

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Custom validation error with user-friendly messages"""

    def __init__(self, message: str, field: str = None):
        self.message = message
        self.field = field
        super().__init__(message)


class PollValidator:
    """Comprehensive poll validation system"""

    # Constants for validation
    MIN_POLL_NAME_LENGTH = 3
    MAX_POLL_NAME_LENGTH = 255
    MIN_QUESTION_LENGTH = 5
    MAX_QUESTION_LENGTH = 2000
    MIN_OPTIONS = 2
    MAX_OPTIONS = 10
    MIN_OPTION_LENGTH = 1
    MAX_OPTION_LENGTH = 100
    MAX_IMAGE_SIZE = 8 * 1024 * 1024  # 8MB
    ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"]
    MIN_POLL_DURATION_MINUTES = 1
    MAX_POLL_DURATION_DAYS = 30

    @staticmethod
    def validate_poll_name(name: str) -> str:
        """Validate and sanitize poll name"""
        if not name or not isinstance(name, str):
            raise ValidationError("Poll name is required", "name")

        name = name.strip()
        if len(name) < PollValidator.MIN_POLL_NAME_LENGTH:
            raise ValidationError(
                f"Poll name must be at least {PollValidator.MIN_POLL_NAME_LENGTH} characters",
                "name",
            )

        if len(name) > PollValidator.MAX_POLL_NAME_LENGTH:
            raise ValidationError(
                f"Poll name cannot exceed {PollValidator.MAX_POLL_NAME_LENGTH} characters",
                "name",
            )

        # Remove potentially harmful characters
        name = re.sub(r'[<>"\']', "", name)

        return name

    @staticmethod
    def validate_poll_question(question: str) -> str:
        """Validate and sanitize poll question"""
        if not question or not isinstance(question, str):
            raise ValidationError("Poll question is required", "question")

        question = question.strip()
        if len(question) < PollValidator.MIN_QUESTION_LENGTH:
            raise ValidationError(
                f"Poll question must be at least {PollValidator.MIN_QUESTION_LENGTH} characters",
                "question",
            )

        if len(question) > PollValidator.MAX_QUESTION_LENGTH:
            raise ValidationError(
                f"Poll question cannot exceed {PollValidator.MAX_QUESTION_LENGTH} characters",
                "question",
            )

        return question

    @staticmethod
    def validate_poll_options(options: List[str]) -> List[str]:
        """Validate and sanitize poll options"""
        if not options or not isinstance(options, list):
            raise ValidationError("Poll options are required", "options")

        # Filter out empty options
        valid_options = []
        for option in options:
            if option and isinstance(option, str):
                option = option.strip()
                if option:
                    valid_options.append(option)

        if len(valid_options) < PollValidator.MIN_OPTIONS:
            raise ValidationError(
                f"At least {PollValidator.MIN_OPTIONS} options are required", "options"
            )

        if len(valid_options) > PollValidator.MAX_OPTIONS:
            raise ValidationError(
                f"Maximum {PollValidator.MAX_OPTIONS} options allowed", "options"
            )

        # Validate individual options
        for i, option in enumerate(valid_options):
            if len(option) < PollValidator.MIN_OPTION_LENGTH:
                raise ValidationError(f"Option {i + 1} is too short", "options")

            if len(option) > PollValidator.MAX_OPTION_LENGTH:
                raise ValidationError(
                    f"Option {i + 1} is too long (max {PollValidator.MAX_OPTION_LENGTH} characters)",
                    "options",
                )

            # Remove potentially harmful characters but preserve Discord emoji format
            # Discord emojis use <:name:id> or <a:name:id> format, so we need to preserve < and >
            valid_options[i] = re.sub(r'["\']', "", option)

        # Check for duplicate options
        if len(set(valid_options)) != len(valid_options):
            raise ValidationError("Duplicate options are not allowed", "options")

        return valid_options

    @staticmethod
    def validate_poll_emojis(emojis: List[str], bot_instance=None) -> List[str]:
        """Validate and sanitize poll emojis using the emoji library for reliable validation"""
        if not emojis or not isinstance(emojis, list):
            return []  # Empty emojis list is valid, will use defaults

        valid_emojis = []

        # Import emoji handler for Unicode emoji preparation
        emoji_handler = None
        if bot_instance:
            try:
                from .discord_emoji_handler import DiscordEmojiHandler

                emoji_handler = DiscordEmojiHandler(bot_instance)
                logger.debug(
                    "✅ EMOJI VALIDATION - Emoji handler initialized for reaction preparation"
                )
            except Exception as e:
                logger.warning(
                    f"⚠️ EMOJI VALIDATION - Could not initialize emoji handler: {e}"
                )

        for i, emoji_text in enumerate(emojis):
            if not emoji_text or not isinstance(emoji_text, str):
                continue  # Skip empty/invalid emojis

            emoji_text = emoji_text.strip()
            if not emoji_text:
                continue

            try:
                # 1. Validate Discord custom emoji format: <:name:id> or <a:name:id>
                discord_emoji_pattern = r"^<a?:[a-zA-Z0-9_]+:\d+>$"
                if re.match(discord_emoji_pattern, emoji_text):
                    valid_emojis.append(emoji_text)
                    logger.debug(
                        f"✅ EMOJI VALIDATION - Discord custom emoji validated: {emoji_text}"
                    )
                    continue

                # 2. Use the emoji library for reliable Unicode emoji validation
                try:
                    import emoji

                    # Check if it's a single emoji
                    if emoji.is_emoji(emoji_text):
                        # Prepare Unicode emoji for Discord reactions
                        if emoji_handler:
                            try:
                                prepared_emoji = (
                                    emoji_handler.prepare_emoji_for_reaction(emoji_text)
                                )
                                valid_emojis.append(prepared_emoji)
                                logger.debug(
                                    f"✅ EMOJI VALIDATION - Single emoji validated and prepared: '{emoji_text}' -> '{prepared_emoji}'"
                                )
                            except Exception as prep_error:
                                logger.warning(
                                    f"⚠️ EMOJI VALIDATION - Error preparing emoji '{emoji_text}': {prep_error}"
                                )
                                valid_emojis.append(
                                    emoji_text
                                )  # Use original if preparation fails
                        else:
                            valid_emojis.append(emoji_text)
                            logger.debug(
                                f"✅ EMOJI VALIDATION - Single emoji validated (no preparation): {emoji_text}"
                            )
                        continue

                    # Check if it's a string containing only emoji characters
                    if emoji.purely_emoji(emoji_text):
                        # Prepare Unicode emoji for Discord reactions
                        if emoji_handler:
                            try:
                                prepared_emoji = (
                                    emoji_handler.prepare_emoji_for_reaction(emoji_text)
                                )
                                valid_emojis.append(prepared_emoji)
                                logger.debug(
                                    f"✅ EMOJI VALIDATION - Pure emoji string validated and prepared: '{emoji_text}' -> '{prepared_emoji}'"
                                )
                            except Exception as prep_error:
                                logger.warning(
                                    f"⚠️ EMOJI VALIDATION - Error preparing emoji '{emoji_text}': {prep_error}"
                                )
                                valid_emojis.append(
                                    emoji_text
                                )  # Use original if preparation fails
                        else:
                            valid_emojis.append(emoji_text)
                            logger.debug(
                                f"✅ EMOJI VALIDATION - Pure emoji string validated (no preparation): {emoji_text}"
                            )
                        continue

                    # Check if it contains any emoji and is reasonably short
                    emoji_count = emoji.emoji_count(emoji_text)
                    if emoji_count > 0 and len(emoji_text) <= 10:
                        # Prepare Unicode emoji for Discord reactions
                        if emoji_handler:
                            try:
                                prepared_emoji = (
                                    emoji_handler.prepare_emoji_for_reaction(emoji_text)
                                )
                                valid_emojis.append(prepared_emoji)
                                logger.debug(
                                    f"✅ EMOJI VALIDATION - Text with {emoji_count} emoji(s) validated and prepared: '{emoji_text}' -> '{prepared_emoji}'"
                                )
                            except Exception as prep_error:
                                logger.warning(
                                    f"⚠️ EMOJI VALIDATION - Error preparing emoji '{emoji_text}': {prep_error}"
                                )
                                valid_emojis.append(
                                    emoji_text
                                )  # Use original if preparation fails
                        else:
                            valid_emojis.append(emoji_text)
                            logger.debug(
                                f"✅ EMOJI VALIDATION - Text with {emoji_count} emoji(s) validated (no preparation): {emoji_text}"
                            )
                        continue

                    # If emoji library says it's not an emoji, check if it's a flag emoji or other special case
                    # Flag emojis (🇦🇧🇨 etc.) are often not recognized by the emoji library but are valid
                    if len(emoji_text) <= 4 and any(
                        ord(char) >= 0x1F1E6 and ord(char) <= 0x1F1FF
                        for char in emoji_text
                    ):
                        # This looks like a flag emoji or regional indicator
                        valid_emojis.append(emoji_text)
                        logger.debug(
                            f"✅ EMOJI VALIDATION - Flag/regional emoji accepted: {emoji_text}"
                        )
                        continue

                    # Check for other common emoji patterns that might not be recognized
                    if len(emoji_text) <= 6 and any(
                        ord(char) >= 0x1F300 for char in emoji_text
                    ):
                        # This looks like a Unicode emoji in the emoji block
                        valid_emojis.append(emoji_text)
                        logger.debug(
                            f"✅ EMOJI VALIDATION - Unicode emoji pattern accepted: {emoji_text}"
                        )
                        continue

                    # Only log as warning if it's not a common emoji pattern
                    logger.debug(
                        f"⚠️ EMOJI VALIDATION - Not recognized as emoji by library, skipping: {emoji_text}"
                    )

                except Exception as e:
                    # If emoji library fails, be lenient and include it anyway
                    if emoji_handler:
                        try:
                            prepared_emoji = emoji_handler.prepare_emoji_for_reaction(
                                emoji_text
                            )
                            valid_emojis.append(prepared_emoji)
                            logger.warning(
                                f"⚠️ EMOJI VALIDATION - Error using emoji library for '{emoji_text}', prepared anyway: '{prepared_emoji}' (error: {e})"
                            )
                        except Exception:
                            valid_emojis.append(emoji_text)
                            logger.warning(
                                f"⚠️ EMOJI VALIDATION - Error using emoji library and preparing '{emoji_text}', including original: {e}"
                            )
                    else:
                        valid_emojis.append(emoji_text)
                        logger.warning(
                            f"⚠️ EMOJI VALIDATION - Error using emoji library for '{emoji_text}', including anyway: {e}"
                        )

            except Exception as validation_error:
                logger.error(
                    f"❌ EMOJI VALIDATION - Unexpected error validating emoji '{emoji_text}': {validation_error}"
                )
                # Include the emoji anyway to prevent breaking the poll creation
                valid_emojis.append(emoji_text)

        logger.debug(f"✅ EMOJI VALIDATION - Final validated emojis: {valid_emojis}")
        return valid_emojis

    @staticmethod
    def validate_server_and_channel(server_id: str, channel_id: str) -> Tuple[str, str]:
        """Validate server and channel IDs"""
        if not server_id or not isinstance(server_id, str):
            raise ValidationError("Server selection is required", "server_id")

        if not channel_id or not isinstance(channel_id, str):
            raise ValidationError("Channel selection is required", "channel_id")

        # Validate Discord ID format (should be numeric string)
        if not re.match(r"^\d+$", server_id):
            raise ValidationError("Invalid server ID format", "server_id")

        if not re.match(r"^\d+$", channel_id):
            raise ValidationError("Invalid channel ID format", "channel_id")

        return server_id, channel_id

    @staticmethod
    def validate_timezone(timezone_str: str) -> str:
        """Validate and normalize timezone"""
        if not timezone_str:
            return "UTC"

        # Handle common timezone aliases
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

        if timezone_str in timezone_mapping:
            timezone_str = timezone_mapping[timezone_str]

        try:
            pytz.timezone(timezone_str)
            return timezone_str
        except pytz.UnknownTimeZoneError:
            logger.warning(f"Unknown timezone '{timezone_str}', using UTC")
            return "UTC"

    @staticmethod
    def validate_poll_timing(
        open_time: datetime, close_time: datetime, timezone_str: str = "UTC"
    ) -> Tuple[datetime, datetime]:
        """Validate poll timing with comprehensive checks"""
        if not isinstance(open_time, datetime) or not isinstance(close_time, datetime):
            raise ValidationError("Invalid datetime format", "timing")

        # Ensure times are timezone-aware
        if open_time.tzinfo is None:
            tz = pytz.timezone(PollValidator.validate_timezone(timezone_str))
            open_time = tz.localize(open_time)

        if close_time.tzinfo is None:
            tz = pytz.timezone(PollValidator.validate_timezone(timezone_str))
            close_time = tz.localize(close_time)

        # Convert to UTC for comparison
        open_utc = open_time.astimezone(pytz.UTC)
        close_utc = close_time.astimezone(pytz.UTC)

        # Get current time with buffer for scheduling
        now = datetime.now(pytz.UTC)
        min_start_time = now.replace(second=0, microsecond=0) + timedelta(minutes=1)

        # Validate open time is in the future
        if open_utc < min_start_time:
            user_tz = pytz.timezone(PollValidator.validate_timezone(timezone_str))
            suggested_time = min_start_time.astimezone(user_tz).strftime("%I:%M %p")
            raise ValidationError(
                f"Poll must be scheduled for at least the next minute. Try {suggested_time} or later.",
                "open_time",
            )

        # Validate close time is after open time
        if close_utc <= open_utc:
            raise ValidationError(
                "Poll close time must be after open time", "close_time"
            )

        # Validate minimum duration
        duration = close_utc - open_utc
        if duration < timedelta(minutes=PollValidator.MIN_POLL_DURATION_MINUTES):
            raise ValidationError(
                f"Poll must run for at least {PollValidator.MIN_POLL_DURATION_MINUTES} minutes",
                "timing",
            )

        # Validate maximum duration
        if duration > timedelta(days=PollValidator.MAX_POLL_DURATION_DAYS):
            raise ValidationError(
                f"Poll cannot run for more than {PollValidator.MAX_POLL_DURATION_DAYS} days",
                "timing",
            )

        return open_utc, close_utc

    @staticmethod
    def validate_image_file(
        image_file, content: Optional[bytes] = None
    ) -> Tuple[bool, str]:
        """Validate uploaded image file"""
        if (
            not image_file
            or not hasattr(image_file, "filename")
            or not image_file.filename
        ):
            return True, ""  # No image is valid

        # Validate file size
        if content and len(content) > PollValidator.MAX_IMAGE_SIZE:
            return (
                False,
                f"Image file too large (max {PollValidator.MAX_IMAGE_SIZE // (1024 * 1024)}MB)",
            )

        # Validate file type
        if hasattr(image_file, "content_type") and image_file.content_type:
            if image_file.content_type not in PollValidator.ALLOWED_IMAGE_TYPES:
                return False, "Invalid image format (JPEG, PNG, GIF, WebP only)"

        # Validate filename
        filename = str(image_file.filename).lower()
        valid_extensions = [".jpg", ".jpeg", ".png", ".gif", ".webp"]
        if not any(filename.endswith(ext) for ext in valid_extensions):
            return False, "Invalid image file extension"

        return True, ""

    @staticmethod
    def validate_poll_data(poll_data: Dict[str, Any]) -> Dict[str, Any]:
        """Comprehensive validation of all poll data"""
        validated_data = {}

        try:
            # Validate basic fields
            validated_data["name"] = PollValidator.validate_poll_name(
                poll_data.get("name", "")
            )
            validated_data["question"] = PollValidator.validate_poll_question(
                poll_data.get("question", "")
            )
            validated_data["options"] = PollValidator.validate_poll_options(
                poll_data.get("options", [])
            )

            # Validate server and channel
            server_id, channel_id = PollValidator.validate_server_and_channel(
                poll_data.get("server_id", ""), poll_data.get("channel_id", "")
            )
            validated_data["server_id"] = server_id
            validated_data["channel_id"] = channel_id

            # Validate timezone
            validated_data["timezone"] = PollValidator.validate_timezone(
                poll_data.get("timezone", "UTC")
            )

            # Validate timing
            open_time_raw = poll_data.get("open_time")
            close_time_raw = poll_data.get("close_time")

            if not open_time_raw or not close_time_raw:
                raise ValidationError("Open time and close time are required", "timing")

            open_time, close_time = PollValidator.validate_poll_timing(
                open_time_raw, close_time_raw, validated_data["timezone"]
            )
            validated_data["open_time"] = open_time
            validated_data["close_time"] = close_time

            # Validate emojis (CRITICAL FIX - this was missing!)
            # Try to get bot instance for emoji preparation
            bot_instance = poll_data.get("bot_instance", None)
            validated_data["emojis"] = PollValidator.validate_poll_emojis(
                poll_data.get("emojis", []), bot_instance
            )

            # Validate boolean fields
            validated_data["anonymous"] = bool(poll_data.get("anonymous", False))
            validated_data["multiple_choice"] = bool(
                poll_data.get("multiple_choice", False)
            )

            # Validate optional image message text
            image_message_text = poll_data.get("image_message_text", "")
            if image_message_text and isinstance(image_message_text, str):
                validated_data["image_message_text"] = image_message_text.strip()
            else:
                validated_data["image_message_text"] = ""

            # Validate creator ID
            creator_id = poll_data.get("creator_id", "")
            if not creator_id or not isinstance(creator_id, str):
                raise ValidationError("Creator ID is required", "creator_id")
            validated_data["creator_id"] = creator_id

            # Validate role ping fields
            ping_role_enabled = bool(poll_data.get("ping_role_enabled", False))
            validated_data["ping_role_enabled"] = ping_role_enabled
            
            if ping_role_enabled:
                ping_role_id = poll_data.get("ping_role_id", "")
                if ping_role_id and isinstance(ping_role_id, str) and ping_role_id.strip():
                    # Validate Discord role ID format (should be numeric string)
                    if re.match(r"^\d+$", ping_role_id.strip()):
                        validated_data["ping_role_id"] = ping_role_id.strip()
                    else:
                        raise ValidationError("Invalid role ID format", "ping_role_id")
                else:
                    validated_data["ping_role_id"] = None
                
                # Role name is optional but should be validated if provided
                ping_role_name = poll_data.get("ping_role_name", "")
                if ping_role_name and isinstance(ping_role_name, str):
                    validated_data["ping_role_name"] = ping_role_name.strip()
                else:
                    validated_data["ping_role_name"] = None
            else:
                validated_data["ping_role_id"] = None
                validated_data["ping_role_name"] = None

            logger.debug(
                f"✅ VALIDATOR - Emojis validated and included: {validated_data.get('emojis', [])}"
            )
            logger.debug(
                f"✅ VALIDATOR - Role ping data validated: enabled={validated_data.get('ping_role_enabled')}, role_id={validated_data.get('ping_role_id')}, role_name={validated_data.get('ping_role_name')}"
            )

            return validated_data

        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Unexpected validation error: {e}")
            raise ValidationError(f"Validation failed: {str(e)}")


class VoteValidator:
    """Validation for vote operations"""

    @staticmethod
    def validate_vote_data(
        poll: Poll, user_id: str, option_index: int
    ) -> Tuple[str, int]:
        """Validate vote data"""
        if not poll:
            raise ValidationError("Poll not found")

        if str(poll.status) != "active":
            raise ValidationError("Poll is not active for voting")

        if not user_id or not isinstance(user_id, str):
            raise ValidationError("Invalid user ID")

        if not isinstance(option_index, int) or option_index < 0:
            raise ValidationError("Invalid option selection")

        if option_index >= len(poll.options):
            raise ValidationError("Selected option does not exist")

        # Check if poll has expired
        now = datetime.now(pytz.UTC)

        # Ensure poll.close_time is timezone-aware for comparison
        poll_close_time = getattr(poll, "close_time", None)
        if poll_close_time and poll_close_time.tzinfo is None:
            # If poll close time is naive, assume it's in UTC
            poll_close_time = pytz.UTC.localize(poll_close_time)
        elif poll_close_time:
            # Already timezone-aware, use as-is
            pass
        else:
            raise ValidationError("Poll close time not set")

        if poll_close_time <= now:
            raise ValidationError("Poll has expired")

        return user_id, option_index

    @staticmethod
    def validate_existing_vote(poll_id: int, user_id: str) -> Optional[Vote]:
        """Check for existing vote and validate"""
        db = get_db_session()
        try:
            existing_vote = (
                db.query(Vote)
                .filter(Vote.poll_id == poll_id, Vote.user_id == user_id)
                .first()
            )
            return existing_vote
        except Exception as e:
            logger.error(f"Error checking existing vote: {e}")
            return None
        finally:
            db.close()


class SchedulerValidator:
    """Validation for scheduler operations"""

    @staticmethod
    def validate_job_id(job_id: str) -> str:
        """Validate scheduler job ID"""
        if not job_id or not isinstance(job_id, str):
            raise ValidationError("Invalid job ID")

        # Ensure job ID follows expected pattern
        if not re.match(r"^(open|close)_poll_\d+$", job_id):
            raise ValidationError("Invalid job ID format")

        return job_id

    @staticmethod
    def validate_poll_for_scheduling(poll: Poll) -> bool:
        """Validate poll is ready for scheduling"""
        if not poll:
            raise ValidationError("Poll not found")

        if not str(poll.server_id) or not str(poll.channel_id):
            raise ValidationError("Poll missing server or channel information")

        if not poll.options or len(poll.options) < 2:
            raise ValidationError("Poll must have at least 2 options")

        now = datetime.now(pytz.UTC)
        poll_open_time = getattr(poll, "open_time", None)
        poll_close_time = getattr(poll, "close_time", None)
        poll_status = str(poll.status)

        if poll_open_time and poll_open_time <= now and poll_status == "scheduled":
            raise ValidationError("Poll open time has passed")

        if poll_close_time and poll_open_time and poll_close_time <= poll_open_time:
            raise ValidationError("Poll close time must be after open time")

        return True


def safe_get_form_data(form_data, key: str, default: str = "") -> str:
    """Safely extract form data with validation"""
    try:
        value = form_data.get(key)
        if value is None:
            return default

        # Convert to string and sanitize
        str_value = str(value).strip()

        # Basic XSS prevention
        str_value = re.sub(r'[<>"\']', "", str_value)

        return str_value
    except Exception as e:
        logger.warning(f"Error extracting form data for key '{key}': {e}")
        return default


def validate_discord_permissions(
    member, required_permissions: Optional[List[str]] = None
) -> bool:
    """Validate Discord member permissions"""
    if not member:
        return False

    if required_permissions is None:
        required_permissions = ["administrator", "manage_guild", "manage_channels"]

    try:
        permissions = member.guild_permissions
        safe_permissions = (
            required_permissions if required_permissions is not None else []
        )
        return any(getattr(permissions, perm, False) for perm in safe_permissions)
    except Exception as e:
        logger.error(f"Error checking Discord permissions: {e}")
        return False
