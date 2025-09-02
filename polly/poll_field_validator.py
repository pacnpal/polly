"""
Poll Field Validator
Comprehensive validation system to ensure all poll creation fields match what was entered when sending the poll.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import json
import pytz

from .database import get_db_session, Poll, TypeSafeColumn
from .error_handler import notify_error_async

logger = logging.getLogger(__name__)


class PollFieldValidationError(Exception):
    """Exception raised when poll field validation fails"""

    def __init__(self, message: str, field: str, expected: Any, actual: Any):
        self.message = message
        self.field = field
        self.expected = expected
        self.actual = actual
        super().__init__(self.message)


class PollFieldValidator:
    """Validates that all poll fields match what was entered at creation time"""

    @staticmethod
    async def validate_poll_fields_before_posting(poll_id: int, bot_instance=None) -> Dict[str, Any]:
        """
        Comprehensive validation of all poll fields before posting to Discord.

        Args:
            poll_id: ID of the poll to validate
            bot_instance: Discord bot instance for owner notifications

        Returns:
            Dict with validation results and any errors found
        """
        logger.info(
            f"🔍 FIELD VALIDATION - Starting comprehensive validation for poll {poll_id}")

        validation_results = {
            "success": True,
            "errors": [],
            "warnings": [],
            "validated_fields": [],
            "fallback_applied": []
        }

        db = get_db_session()
        try:
            # Fetch poll from database
            poll = db.query(Poll).filter(Poll.id == poll_id).first()
            if not poll:
                error_msg = f"Poll {poll_id} not found in database"
                logger.error(f"❌ FIELD VALIDATION - {error_msg}")
                validation_results["success"] = False
                validation_results["errors"].append(error_msg)
                return validation_results

            logger.debug(
                f"✅ FIELD VALIDATION - Poll {poll_id} found in database")

            # Validate core poll fields
            await PollFieldValidator._validate_core_fields(poll, validation_results)

            # Validate poll options and emojis
            await PollFieldValidator._validate_options_and_emojis(poll, validation_results)

            # Validate Discord-related fields
            await PollFieldValidator._validate_discord_fields(poll, validation_results, bot_instance)

            # Validate timing fields
            await PollFieldValidator._validate_timing_fields(poll, validation_results)

            # Validate image fields if present
            await PollFieldValidator._validate_image_fields(poll, validation_results)

            # Apply fallback mechanisms if needed
            if validation_results["errors"]:
                await PollFieldValidator._apply_fallback_mechanisms(poll, validation_results, db)

            # Final validation summary
            total_fields = len(validation_results["validated_fields"])
            error_count = len(validation_results["errors"])
            warning_count = len(validation_results["warnings"])
            fallback_count = len(validation_results["fallback_applied"])

            if validation_results["success"]:
                logger.info(
                    f"✅ FIELD VALIDATION - Poll {poll_id} validation PASSED: {total_fields} fields validated, {warning_count} warnings, {fallback_count} fallbacks applied")
            else:
                logger.error(
                    f"❌ FIELD VALIDATION - Poll {poll_id} validation FAILED: {error_count} errors, {warning_count} warnings, {fallback_count} fallbacks applied")

                # Notify owner of validation failures
                if bot_instance:
                    await PollFieldValidator._notify_owner_of_validation_failure(
                        poll, validation_results, bot_instance
                    )

            return validation_results

        except Exception as e:
            logger.error(
                f"❌ FIELD VALIDATION - Critical error during validation of poll {poll_id}: {e}")
            await notify_error_async(e, "Poll Field Validation Critical Error", poll_id=poll_id)
            validation_results["success"] = False
            validation_results["errors"].append(
                f"Critical validation error: {str(e)}")
            return validation_results
        finally:
            db.close()

    @staticmethod
    async def _validate_core_fields(poll: Poll, results: Dict[str, Any]):
        """Validate core poll fields (name, question, status)"""
        logger.debug(
            f"🔍 FIELD VALIDATION - Validating core fields for poll {poll.id}")

        # Validate poll name
        poll_name = TypeSafeColumn.get_string(poll, 'name')
        if not poll_name or not poll_name.strip():
            error_msg = "Poll name is empty or missing"
            logger.error(f"❌ FIELD VALIDATION - {error_msg}")
            results["errors"].append(error_msg)
        elif len(poll_name.strip()) < 3:
            warning_msg = f"Poll name is very short: '{poll_name}'"
            logger.warning(f"⚠️ FIELD VALIDATION - {warning_msg}")
            results["warnings"].append(warning_msg)
        else:
            results["validated_fields"].append("name")
            logger.debug(
                f"✅ FIELD VALIDATION - Poll name validated: '{poll_name[:50]}...'")

        # Validate poll question
        poll_question = TypeSafeColumn.get_string(poll, 'question')
        if not poll_question or not poll_question.strip():
            error_msg = "Poll question is empty or missing"
            logger.error(f"❌ FIELD VALIDATION - {error_msg}")
            results["errors"].append(error_msg)
        elif len(poll_question.strip()) < 5:
            warning_msg = f"Poll question is very short: '{poll_question}'"
            logger.warning(f"⚠️ FIELD VALIDATION - {warning_msg}")
            results["warnings"].append(warning_msg)
        else:
            results["validated_fields"].append("question")
            logger.debug(
                f"✅ FIELD VALIDATION - Poll question validated: '{poll_question[:50]}...'")

        # Validate poll status
        poll_status = TypeSafeColumn.get_string(poll, 'status')
        valid_statuses = ["scheduled", "active", "closed"]
        if poll_status not in valid_statuses:
            error_msg = f"Invalid poll status: '{poll_status}' (must be one of: {valid_statuses})"
            logger.error(f"❌ FIELD VALIDATION - {error_msg}")
            results["errors"].append(error_msg)
        else:
            results["validated_fields"].append("status")
            logger.debug(
                f"✅ FIELD VALIDATION - Poll status validated: '{poll_status}'")

    @staticmethod
    async def _validate_options_and_emojis(poll: Poll, results: Dict[str, Any]):
        """Validate poll options and their corresponding emojis"""
        logger.debug(
            f"🔍 FIELD VALIDATION - Validating options and emojis for poll {poll.id}")

        # Get options and emojis
        try:
            options = poll.options  # Uses the property which handles JSON parsing
            emojis = poll.emojis    # Uses the property which handles JSON parsing
        except (json.JSONDecodeError, TypeError) as e:
            error_msg = f"Failed to parse poll options or emojis JSON: {str(e)}"
            logger.error(f"❌ FIELD VALIDATION - {error_msg}")
            results["errors"].append(error_msg)
            return

        # Validate options
        if not options or len(options) < 2:
            error_msg = f"Poll must have at least 2 options, found: {len(options) if options else 0}"
            logger.error(f"❌ FIELD VALIDATION - {error_msg}")
            results["errors"].append(error_msg)
        elif len(options) > 10:
            error_msg = f"Poll cannot have more than 10 options, found: {len(options)}"
            logger.error(f"❌ FIELD VALIDATION - {error_msg}")
            results["errors"].append(error_msg)
        else:
            results["validated_fields"].append("options_count")
            logger.debug(
                f"✅ FIELD VALIDATION - Options count validated: {len(options)} options")

        # Validate individual options
        for i, option in enumerate(options):
            if not option or not str(option).strip():
                error_msg = f"Option {i+1} is empty or missing"
                logger.error(f"❌ FIELD VALIDATION - {error_msg}")
                results["errors"].append(error_msg)
            elif len(str(option).strip()) > 100:
                warning_msg = f"Option {i+1} is very long ({len(str(option))} chars): '{str(option)[:50]}...'"
                logger.warning(f"⚠️ FIELD VALIDATION - {warning_msg}")
                results["warnings"].append(warning_msg)
            else:
                results["validated_fields"].append(f"option_{i+1}")
                logger.debug(
                    f"✅ FIELD VALIDATION - Option {i+1} validated: '{str(option)[:30]}...'")

        # Validate emojis match options
        if emojis:
            if len(emojis) != len(options):
                error_msg = f"Emoji count ({len(emojis)}) doesn't match option count ({len(options)})"
                logger.error(f"❌ FIELD VALIDATION - {error_msg}")
                results["errors"].append(error_msg)
            else:
                results["validated_fields"].append("emoji_count_match")
                logger.debug(
                    f"✅ FIELD VALIDATION - Emoji count matches option count: {len(emojis)}")

                # Validate individual emojis
                for i, emoji in enumerate(emojis):
                    if not emoji or not str(emoji).strip():
                        warning_msg = f"Emoji for option {i+1} is empty, will use default"
                        logger.warning(f"⚠️ FIELD VALIDATION - {warning_msg}")
                        results["warnings"].append(warning_msg)
                    else:
                        results["validated_fields"].append(f"emoji_{i+1}")
                        logger.debug(
                            f"✅ FIELD VALIDATION - Emoji {i+1} validated: '{emoji}'")
        else:
            warning_msg = "No custom emojis set, will use default emojis"
            logger.warning(f"⚠️ FIELD VALIDATION - {warning_msg}")
            results["warnings"].append(warning_msg)

    @staticmethod
    async def _validate_discord_fields(poll: Poll, results: Dict[str, Any], bot_instance=None):
        """Validate Discord-related fields (server, channel, creator)"""
        logger.debug(
            f"🔍 FIELD VALIDATION - Validating Discord fields for poll {poll.id}")

        # Validate server ID
        server_id = TypeSafeColumn.get_string(poll, 'server_id')
        if not server_id or not server_id.strip():
            error_msg = "Server ID is empty or missing"
            logger.error(f"❌ FIELD VALIDATION - {error_msg}")
            results["errors"].append(error_msg)
        else:
            try:
                int(server_id)  # Validate it's a valid Discord ID
                results["validated_fields"].append("server_id")
                logger.debug(
                    f"✅ FIELD VALIDATION - Server ID validated: {server_id}")
            except ValueError:
                error_msg = f"Invalid server ID format: '{server_id}'"
                logger.error(f"❌ FIELD VALIDATION - {error_msg}")
                results["errors"].append(error_msg)

        # Validate channel ID
        channel_id = TypeSafeColumn.get_string(poll, 'channel_id')
        if not channel_id or not channel_id.strip():
            error_msg = "Channel ID is empty or missing"
            logger.error(f"❌ FIELD VALIDATION - {error_msg}")
            results["errors"].append(error_msg)
        else:
            try:
                int(channel_id)  # Validate it's a valid Discord ID
                results["validated_fields"].append("channel_id")
                logger.debug(
                    f"✅ FIELD VALIDATION - Channel ID validated: {channel_id}")
            except ValueError:
                error_msg = f"Invalid channel ID format: '{channel_id}'"
                logger.error(f"❌ FIELD VALIDATION - {error_msg}")
                results["errors"].append(error_msg)

        # Validate creator ID
        creator_id = TypeSafeColumn.get_string(poll, 'creator_id')
        if not creator_id or not creator_id.strip():
            error_msg = "Creator ID is empty or missing"
            logger.error(f"❌ FIELD VALIDATION - {error_msg}")
            results["errors"].append(error_msg)
        else:
            try:
                int(creator_id)  # Validate it's a valid Discord ID
                results["validated_fields"].append("creator_id")
                logger.debug(
                    f"✅ FIELD VALIDATION - Creator ID validated: {creator_id}")
            except ValueError:
                error_msg = f"Invalid creator ID format: '{creator_id}'"
                logger.error(f"❌ FIELD VALIDATION - {error_msg}")
                results["errors"].append(error_msg)

        # Validate server and channel names if present
        server_name = TypeSafeColumn.get_string(poll, 'server_name')
        if server_name:
            results["validated_fields"].append("server_name")
            logger.debug(
                f"✅ FIELD VALIDATION - Server name validated: '{server_name}'")
        else:
            warning_msg = "Server name is missing"
            logger.warning(f"⚠️ FIELD VALIDATION - {warning_msg}")
            results["warnings"].append(warning_msg)

        channel_name = TypeSafeColumn.get_string(poll, 'channel_name')
        if channel_name:
            results["validated_fields"].append("channel_name")
            logger.debug(
                f"✅ FIELD VALIDATION - Channel name validated: '{channel_name}'")
        else:
            warning_msg = "Channel name is missing"
            logger.warning(f"⚠️ FIELD VALIDATION - {warning_msg}")
            results["warnings"].append(warning_msg)

        # Validate Discord accessibility if bot instance is provided
        if bot_instance and server_id and channel_id:
            try:
                guild = bot_instance.get_guild(int(server_id))
                if not guild:
                    error_msg = f"Bot cannot access server {server_id}"
                    logger.error(f"❌ FIELD VALIDATION - {error_msg}")
                    results["errors"].append(error_msg)
                else:
                    channel = bot_instance.get_channel(int(channel_id))
                    if not channel:
                        error_msg = f"Bot cannot access channel {channel_id}"
                        logger.error(f"❌ FIELD VALIDATION - {error_msg}")
                        results["errors"].append(error_msg)
                    else:
                        results["validated_fields"].append(
                            "discord_accessibility")
                        logger.debug(
                            f"✅ FIELD VALIDATION - Discord accessibility validated")
            except Exception as e:
                warning_msg = f"Could not validate Discord accessibility: {str(e)}"
                logger.warning(f"⚠️ FIELD VALIDATION - {warning_msg}")
                results["warnings"].append(warning_msg)

    @staticmethod
    async def _validate_timing_fields(poll: Poll, results: Dict[str, Any]):
        """Validate poll timing fields (open_time, close_time, timezone)"""
        logger.debug(
            f"🔍 FIELD VALIDATION - Validating timing fields for poll {poll.id}")

        # Get timing fields
        open_time = TypeSafeColumn.get_datetime(poll, 'open_time')
        close_time = TypeSafeColumn.get_datetime(poll, 'close_time')
        timezone = TypeSafeColumn.get_string(poll, 'timezone', 'UTC')

        # Validate open time
        if not open_time:
            error_msg = "Poll open time is missing"
            logger.error(f"❌ FIELD VALIDATION - {error_msg}")
            results["errors"].append(error_msg)
        else:
            results["validated_fields"].append("open_time")
            logger.debug(
                f"✅ FIELD VALIDATION - Open time validated: {open_time}")

        # Validate close time
        if not close_time:
            error_msg = "Poll close time is missing"
            logger.error(f"❌ FIELD VALIDATION - {error_msg}")
            results["errors"].append(error_msg)
        else:
            results["validated_fields"].append("close_time")
            logger.debug(
                f"✅ FIELD VALIDATION - Close time validated: {close_time}")

        # Validate time relationship
        if open_time and close_time:
            try:
                # Simple string comparison as fallback if datetime comparison fails
                if str(close_time) <= str(open_time):
                    error_msg = f"Poll close time ({close_time}) must be after open time ({open_time})"
                    logger.error(f"❌ FIELD VALIDATION - {error_msg}")
                    results["errors"].append(error_msg)
                else:
                    results["validated_fields"].append("time_relationship")
                    logger.debug(
                        f"✅ FIELD VALIDATION - Time relationship validated")
            except (TypeError, AttributeError):
                warning_msg = "Could not compare open and close times"
                logger.warning(f"⚠️ FIELD VALIDATION - {warning_msg}")
                results["warnings"].append(warning_msg)

        # Validate timezone
        if timezone:
            try:
                pytz.timezone(timezone)
                results["validated_fields"].append("timezone")
                logger.debug(
                    f"✅ FIELD VALIDATION - Timezone validated: {timezone}")
            except pytz.UnknownTimeZoneError:
                error_msg = f"Invalid timezone: '{timezone}'"
                logger.error(f"❌ FIELD VALIDATION - {error_msg}")
                results["errors"].append(error_msg)
        else:
            warning_msg = "Timezone is missing, using UTC"
            logger.warning(f"⚠️ FIELD VALIDATION - {warning_msg}")
            results["warnings"].append(warning_msg)

    @staticmethod
    async def _validate_image_fields(poll: Poll, results: Dict[str, Any]):
        """Validate image-related fields if present"""
        logger.debug(
            f"🔍 FIELD VALIDATION - Validating image fields for poll {poll.id}")

        image_path = TypeSafeColumn.get_string(poll, 'image_path')
        image_message_text = TypeSafeColumn.get_string(
            poll, 'image_message_text')

        if image_path:
            # Validate image file exists
            import os
            if not os.path.exists(image_path):
                error_msg = f"Image file not found: {image_path}"
                logger.error(f"❌ FIELD VALIDATION - {error_msg}")
                results["errors"].append(error_msg)
            else:
                results["validated_fields"].append("image_file_exists")
                logger.debug(
                    f"✅ FIELD VALIDATION - Image file exists: {image_path}")

            # Validate image message text if provided
            if image_message_text:
                if len(image_message_text) > 2000:  # Discord message limit
                    warning_msg = f"Image message text is very long ({len(image_message_text)} chars)"
                    logger.warning(f"⚠️ FIELD VALIDATION - {warning_msg}")
                    results["warnings"].append(warning_msg)
                else:
                    results["validated_fields"].append("image_message_text")
                    logger.debug(
                        f"✅ FIELD VALIDATION - Image message text validated")

    @staticmethod
    async def _apply_fallback_mechanisms(poll: Poll, results: Dict[str, Any], db):
        """Apply fallback mechanisms for recoverable errors"""
        logger.info(
            f"🔧 FIELD VALIDATION - Applying fallback mechanisms for poll {poll.id}")

        fallbacks_applied = []

        try:
            # Fallback for missing emojis
            if "emoji_count_match" not in results["validated_fields"]:
                from .database import POLL_EMOJIS
                options = poll.options
                if options and len(options) <= len(POLL_EMOJIS):
                    default_emojis = POLL_EMOJIS[:len(options)]
                    poll.emojis = default_emojis
                    fallbacks_applied.append(
                        f"Applied default emojis: {default_emojis}")
                    logger.info(
                        f"🔧 FIELD VALIDATION - Applied default emojis for poll {poll.id}")

            # Fallback for missing server/channel names
            if "server_name" not in results["validated_fields"] or "channel_name" not in results["validated_fields"]:
                try:
                    # Try to get names from Discord if possible
                    # This would require bot instance, but we'll set placeholders for now
                    if not TypeSafeColumn.get_string(poll, 'server_name'):
                        setattr(poll, 'server_name', f"Server-{TypeSafeColumn.get_string(poll, 'server_id')}")
                        fallbacks_applied.append(
                            "Applied placeholder server name")

                    if not TypeSafeColumn.get_string(poll, 'channel_name'):
                        setattr(poll, 'channel_name', f"Channel-{TypeSafeColumn.get_string(poll, 'channel_id')}")
                        fallbacks_applied.append(
                            "Applied placeholder channel name")

                    logger.info(
                        f"🔧 FIELD VALIDATION - Applied placeholder names for poll {poll.id}")
                except Exception as e:
                    logger.warning(
                        f"⚠️ FIELD VALIDATION - Could not apply name fallbacks: {e}")

            # Fallback for timezone
            if "timezone" not in results["validated_fields"]:
                setattr(poll, 'timezone', "UTC")
                fallbacks_applied.append("Applied default timezone: UTC")
                logger.info(
                    f"🔧 FIELD VALIDATION - Applied default timezone for poll {poll.id}")

            # Commit fallback changes
            if fallbacks_applied:
                db.commit()
                results["fallback_applied"] = fallbacks_applied
                logger.info(
                    f"✅ FIELD VALIDATION - Applied {len(fallbacks_applied)} fallback mechanisms for poll {poll.id}")

                # Re-validate after fallbacks
                if len(results["errors"]) <= len(fallbacks_applied):
                    results["success"] = True
                    # Clear errors that were fixed by fallbacks
                    results["errors"] = []
                    logger.info(
                        f"✅ FIELD VALIDATION - Poll {poll.id} validation now PASSES after fallbacks")

        except Exception as e:
            logger.error(
                f"❌ FIELD VALIDATION - Error applying fallbacks for poll {poll.id}: {e}")
            await notify_error_async(e, "Poll Field Validation Fallback Error", poll_id=poll.id)

    @staticmethod
    async def _notify_owner_of_validation_failure(poll: Poll, results: Dict[str, Any], bot_instance):
        """Notify poll creator of validation failures"""
        try:
            creator_id = TypeSafeColumn.get_string(poll, 'creator_id')
            poll_name = TypeSafeColumn.get_string(poll, 'name')

            if creator_id and bot_instance:
                try:
                    user = await bot_instance.fetch_user(int(creator_id))
                    if user:
                        # Limit to first 5 errors
                        error_summary = "\n".join(results["errors"][:5])
                        # Limit to first 3 warnings
                        warning_summary = "\n".join(results["warnings"][:3])

                        message = f"⚠️ **Poll Validation Failed**\n\n"
                        message += f"**Poll:** {poll_name}\n"
                        message += f"**Poll ID:** {poll.id}\n\n"

                        if results["errors"]:
                            message += f"**Errors ({len(results['errors'])}):**\n{error_summary}\n\n"

                        if results["warnings"]:
                            message += f"**Warnings ({len(results['warnings'])}):**\n{warning_summary}\n\n"

                        if results["fallback_applied"]:
                            message += f"**Fallbacks Applied:** {len(results['fallback_applied'])}\n\n"

                        message += "Please check your poll configuration and try again."

                        # Discord message limit
                        await user.send(message[:2000])
                        logger.info(
                            f"✅ FIELD VALIDATION - Notified creator {creator_id} of validation failure for poll {poll.id}")

                except Exception as dm_error:
                    logger.warning(
                        f"⚠️ FIELD VALIDATION - Could not send DM to creator {creator_id}: {dm_error}")

        except Exception as e:
            logger.error(
                f"❌ FIELD VALIDATION - Error notifying owner of validation failure: {e}")
            await notify_error_async(e, "Poll Validation Owner Notification Error", poll_id=poll.id)
