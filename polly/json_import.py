"""
JSON Import Module
Handles importing poll data from JSON files with validation and parsing.
"""

import json
import logging
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime, timedelta
import pytz

logger = logging.getLogger(__name__)


class PollJSONValidator:
    """Validates and processes poll JSON data with graceful error handling"""

    REQUIRED_FIELDS = ["name", "question", "options"]
    OPTIONAL_FIELDS = [
        "emojis",
        "server_id",
        "channel_id",
        "open_time",
        "close_time",
        "timezone",
        "anonymous",
        "multiple_choice",
        "ping_role_enabled",
        "ping_role_id",
        "image_message_text",
    ]

    @staticmethod
    def validate_json_structure_graceful(
        data: Dict[str, Any],
    ) -> Tuple[bool, List[str], List[str]]:
        """Gracefully validate JSON data - only fail on critical errors, warn on field issues"""
        critical_errors = []  # These prevent import
        warnings = []  # These reset fields but allow import

        # Check if data is a dictionary
        if not isinstance(data, dict):
            critical_errors.append("JSON must be an object/dictionary")
            return False, critical_errors, warnings

        # Check required fields - these are critical
        for field in PollJSONValidator.REQUIRED_FIELDS:
            if field not in data:
                critical_errors.append(f"Missing required field: '{field}'")
            elif not data[field]:
                critical_errors.append(f"Required field '{field}' cannot be empty")

        # Validate required field types and values - these are critical
        if "name" in data and data["name"]:
            if not isinstance(data["name"], str):
                critical_errors.append("Field 'name' must be a string")
            elif len(data["name"].strip()) < 3:
                critical_errors.append(
                    "Field 'name' must be at least 3 characters long"
                )
            elif len(data["name"].strip()) > 255:
                critical_errors.append("Field 'name' must be less than 255 characters")

        if "question" in data and data["question"]:
            if not isinstance(data["question"], str):
                critical_errors.append("Field 'question' must be a string")
            elif len(data["question"].strip()) < 5:
                critical_errors.append(
                    "Field 'question' must be at least 5 characters long"
                )
            elif len(data["question"].strip()) > 2000:
                critical_errors.append(
                    "Field 'question' must be less than 2000 characters"
                )

        if "options" in data and data["options"]:
            if not isinstance(data["options"], list):
                critical_errors.append("Field 'options' must be an array/list")
            elif len(data["options"]) < 2:
                critical_errors.append("At least 2 options are required")
            elif len(data["options"]) > 10:
                critical_errors.append("Maximum 10 options allowed")
            else:
                # Check individual options - these are critical
                for i, option in enumerate(data["options"]):
                    if not isinstance(option, str):
                        critical_errors.append(f"Option {i + 1} must be a string")
                    elif not option.strip():
                        critical_errors.append(f"Option {i + 1} cannot be empty")
                    elif len(option.strip()) > 500:
                        critical_errors.append(
                            f"Option {i + 1} must be less than 500 characters"
                        )

        # Validate optional fields - these generate warnings and get reset
        if "emojis" in data and data["emojis"]:
            if not isinstance(data["emojis"], list):
                warnings.append(
                    "Field 'emojis' must be an array/list - using default emojis"
                )
            elif len(data["emojis"]) > 10:
                warnings.append("Maximum 10 emojis allowed - using default emojis")
            else:
                invalid_emojis = []
                for i, emoji in enumerate(data["emojis"]):
                    if not isinstance(emoji, str):
                        invalid_emojis.append(f"emoji {i + 1}")
                    elif not emoji.strip():
                        invalid_emojis.append(f"emoji {i + 1}")
                if invalid_emojis:
                    warnings.append(
                        f"Invalid emojis found ({', '.join(invalid_emojis)}) - using default emojis"
                    )

        if "server_id" in data and data["server_id"]:
            if not isinstance(data["server_id"], str):
                warnings.append(
                    "Field 'server_id' must be a string - will need to select server manually"
                )

        if "channel_id" in data and data["channel_id"]:
            if not isinstance(data["channel_id"], str):
                warnings.append(
                    "Field 'channel_id' must be a string - will need to select channel manually"
                )

        if "timezone" in data and data["timezone"]:
            if not isinstance(data["timezone"], str):
                warnings.append(
                    "Field 'timezone' must be a string - using default timezone"
                )
            else:
                try:
                    pytz.timezone(data["timezone"])
                except pytz.UnknownTimeZoneError:
                    warnings.append(
                        f"Invalid timezone '{data['timezone']}' - using default timezone"
                    )

        if "anonymous" in data and data["anonymous"] is not None:
            if not isinstance(data["anonymous"], bool):
                warnings.append(
                    "Field 'anonymous' must be a boolean (true/false) - setting to false"
                )

        if "multiple_choice" in data and data["multiple_choice"] is not None:
            if not isinstance(data["multiple_choice"], bool):
                warnings.append(
                    "Field 'multiple_choice' must be a boolean (true/false) - setting to false"
                )

        if "ping_role_enabled" in data and data["ping_role_enabled"] is not None:
            if not isinstance(data["ping_role_enabled"], bool):
                warnings.append(
                    "Field 'ping_role_enabled' must be a boolean (true/false) - setting to false"
                )

        if "ping_role_id" in data and data["ping_role_id"]:
            if not isinstance(data["ping_role_id"], str):
                warnings.append(
                    "Field 'ping_role_id' must be a string - clearing role ping settings"
                )

        if "image_message_text" in data and data["image_message_text"]:
            if not isinstance(data["image_message_text"], str):
                warnings.append(
                    "Field 'image_message_text' must be a string - clearing image message"
                )
            elif len(data["image_message_text"].strip()) > 2000:
                warnings.append(
                    "Field 'image_message_text' must be less than 2000 characters - clearing image message"
                )

        # Validate time fields - these generate warnings and get reset to defaults
        current_time = datetime.now()

        if "open_time" in data and data["open_time"]:
            if not isinstance(data["open_time"], str):
                warnings.append(
                    "Field 'open_time' must be a string in ISO format - using default time"
                )
            else:
                try:
                    open_dt = datetime.fromisoformat(data["open_time"])
                    # Check if the date is in the past
                    if open_dt <= current_time:
                        warnings.append(
                            "Field 'open_time' is in the past - using default time (tomorrow at midnight)"
                        )
                except ValueError:
                    warnings.append(
                        "Field 'open_time' must be in ISO format (YYYY-MM-DDTHH:MM) - using default time"
                    )

        if "close_time" in data and data["close_time"]:
            if not isinstance(data["close_time"], str):
                warnings.append(
                    "Field 'close_time' must be a string in ISO format - using default time"
                )
            else:
                try:
                    close_dt = datetime.fromisoformat(data["close_time"])
                    # Check if the date is in the past
                    if close_dt <= current_time:
                        warnings.append(
                            "Field 'close_time' is in the past - using default time (24 hours after open time)"
                        )
                except ValueError:
                    warnings.append(
                        "Field 'close_time' must be in ISO format (YYYY-MM-DDTHH:MM) - using default time"
                    )

        # Validate time relationship if both times are present and valid
        if (
            "open_time" in data
            and data["open_time"]
            and "close_time" in data
            and data["close_time"]
        ):
            try:
                open_dt = datetime.fromisoformat(data["open_time"])
                close_dt = datetime.fromisoformat(data["close_time"])

                # Skip relationship validation if either time is in the past (already warned about)
                open_in_past = open_dt <= current_time
                close_in_past = close_dt <= current_time

                if not open_in_past and not close_in_past:
                    if close_dt <= open_dt:
                        warnings.append(
                            "Close time must be after open time - using default times"
                        )
                    elif close_dt - open_dt < timedelta(minutes=1):
                        warnings.append(
                            "Poll must run for at least 1 minute - using default times"
                        )
                    elif close_dt - open_dt > timedelta(days=30):
                        warnings.append(
                            "Poll cannot run for more than 30 days - using default times"
                        )
            except ValueError:
                pass  # Time format errors already caught above

        # Only fail if there are critical errors
        return len(critical_errors) == 0, critical_errors, warnings

    @staticmethod
    def process_json_data_graceful(
        data: Dict[str, Any], warnings: List[str], user_timezone: str = "US/Eastern"
    ) -> Dict[str, Any]:
        """Process and normalize JSON data with graceful field resetting based on warnings"""
        processed_data = {}

        # Process required fields (these should always be valid if we got this far)
        processed_data["name"] = data["name"].strip()
        processed_data["question"] = data["question"].strip()
        processed_data["options"] = [option.strip() for option in data["options"]]

        # Process emojis - reset to defaults if warnings indicate issues
        emoji_warnings = [w for w in warnings if "emoji" in w.lower()]
        if emoji_warnings or not isinstance(data.get("emojis"), list):
            # Use default emojis
            from .database import POLL_EMOJIS

            processed_data["emojis"] = []
            for i in range(len(processed_data["options"])):
                if i < len(POLL_EMOJIS):
                    processed_data["emojis"].append(POLL_EMOJIS[i])
                else:
                    processed_data["emojis"].append("❓")
        else:
            # Use provided emojis, but validate each one
            emojis = data.get("emojis", [])
            processed_emojis = []
            from .database import POLL_EMOJIS

            for i, emoji in enumerate(emojis):
                if i >= len(processed_data["options"]):
                    break  # Don't add more emojis than options

                if isinstance(emoji, str) and emoji.strip():
                    processed_emojis.append(emoji.strip())
                else:
                    # Use default emoji for invalid ones
                    if i < len(POLL_EMOJIS):
                        processed_emojis.append(POLL_EMOJIS[i])
                    else:
                        processed_emojis.append("❓")

            # Fill remaining with defaults if needed
            while len(processed_emojis) < len(processed_data["options"]):
                i = len(processed_emojis)
                if i < len(POLL_EMOJIS):
                    processed_emojis.append(POLL_EMOJIS[i])
                else:
                    processed_emojis.append("❓")

            processed_data["emojis"] = processed_emojis

        # Process server_id - reset if warnings indicate issues
        server_warnings = [w for w in warnings if "server_id" in w.lower()]
        if server_warnings or not isinstance(data.get("server_id"), str):
            processed_data["server_id"] = ""
        else:
            processed_data["server_id"] = data.get("server_id", "").strip()

        # Process channel_id - reset if warnings indicate issues
        channel_warnings = [w for w in warnings if "channel_id" in w.lower()]
        if channel_warnings or not isinstance(data.get("channel_id"), str):
            processed_data["channel_id"] = ""
        else:
            processed_data["channel_id"] = data.get("channel_id", "").strip()

        # Process timezone - reset if warnings indicate issues
        timezone_warnings = [w for w in warnings if "timezone" in w.lower()]
        if timezone_warnings:
            processed_data["timezone"] = user_timezone
        else:
            timezone_str = data.get("timezone", user_timezone)
            try:
                pytz.timezone(timezone_str)
                processed_data["timezone"] = timezone_str
            except pytz.UnknownTimeZoneError:
                processed_data["timezone"] = user_timezone

        # Process boolean fields - reset if warnings indicate issues
        anonymous_warnings = [w for w in warnings if "anonymous" in w.lower()]
        if anonymous_warnings or not isinstance(data.get("anonymous"), bool):
            processed_data["anonymous"] = False
        else:
            processed_data["anonymous"] = data.get("anonymous", False)

        multiple_choice_warnings = [
            w for w in warnings if "multiple_choice" in w.lower()
        ]
        if multiple_choice_warnings or not isinstance(
            data.get("multiple_choice"), bool
        ):
            processed_data["multiple_choice"] = False
        else:
            processed_data["multiple_choice"] = data.get("multiple_choice", False)

        ping_role_warnings = [w for w in warnings if "ping_role" in w.lower()]
        if ping_role_warnings:
            processed_data["ping_role_enabled"] = False
            processed_data["ping_role_id"] = ""
        else:
            if isinstance(data.get("ping_role_enabled"), bool):
                processed_data["ping_role_enabled"] = data.get(
                    "ping_role_enabled", False
                )
            else:
                processed_data["ping_role_enabled"] = False

            if processed_data["ping_role_enabled"] and isinstance(
                data.get("ping_role_id"), str
            ):
                processed_data["ping_role_id"] = data.get("ping_role_id", "").strip()
            else:
                processed_data["ping_role_id"] = ""

        # Process image message text - reset if warnings indicate issues
        image_message_warnings = [w for w in warnings if "image_message" in w.lower()]
        if image_message_warnings or not isinstance(
            data.get("image_message_text"), str
        ):
            processed_data["image_message_text"] = ""
        else:
            text = data.get("image_message_text", "").strip()
            if len(text) <= 2000:
                processed_data["image_message_text"] = text
            else:
                processed_data["image_message_text"] = ""

        # Process times - reset if warnings indicate issues
        time_warnings = [w for w in warnings if "time" in w.lower()]
        if time_warnings:
            processed_data["open_time"] = None
            processed_data["close_time"] = None
        else:
            # Validate and process times
            open_time_valid = False
            close_time_valid = False
            current_time = datetime.now()

            if (
                "open_time" in data
                and data["open_time"]
                and isinstance(data["open_time"], str)
            ):
                try:
                    open_dt = datetime.fromisoformat(data["open_time"])
                    # Check if time is in the past - if so, don't use it
                    if open_dt > current_time:
                        processed_data["open_time"] = data["open_time"]
                        open_time_valid = True
                    else:
                        processed_data["open_time"] = None
                except ValueError:
                    processed_data["open_time"] = None
            else:
                processed_data["open_time"] = None

            if (
                "close_time" in data
                and data["close_time"]
                and isinstance(data["close_time"], str)
            ):
                try:
                    close_dt = datetime.fromisoformat(data["close_time"])
                    # Check if time is in the past - if so, don't use it
                    if close_dt > current_time:
                        processed_data["close_time"] = data["close_time"]
                        close_time_valid = True
                    else:
                        processed_data["close_time"] = None
                except ValueError:
                    processed_data["close_time"] = None
            else:
                processed_data["close_time"] = None

            # Validate time relationship if both are valid
            if open_time_valid and close_time_valid:
                try:
                    open_dt = datetime.fromisoformat(processed_data["open_time"])
                    close_dt = datetime.fromisoformat(processed_data["close_time"])
                    if (
                        close_dt <= open_dt
                        or close_dt - open_dt < timedelta(minutes=1)
                        or close_dt - open_dt > timedelta(days=30)
                    ):
                        # Invalid time relationship, reset both
                        processed_data["open_time"] = None
                        processed_data["close_time"] = None
                except ValueError:
                    processed_data["open_time"] = None
                    processed_data["close_time"] = None

        return processed_data


class PollJSONImporter:
    """Handles importing polls from JSON files"""

    @staticmethod
    async def import_from_json_file(
        file_content: bytes, user_timezone: str = "US/Eastern"
    ) -> Tuple[bool, Optional[Dict[str, Any]], List[str]]:
        """Import poll data from JSON file content with graceful error handling"""
        errors = []

        try:
            # Decode file content
            try:
                json_str = file_content.decode("utf-8")
            except UnicodeDecodeError:
                errors.append("File must be UTF-8 encoded")
                return False, None, errors

            # Parse JSON
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError as e:
                errors.append(f"Invalid JSON format: {str(e)}")
                return False, None, errors

            # Use graceful validation - only fail on critical errors
            is_valid, critical_errors, warnings = (
                PollJSONValidator.validate_json_structure_graceful(data)
            )
            if not is_valid:
                # Critical errors prevent import
                errors.extend(critical_errors)
                return False, None, errors

            # Process and normalize data with graceful field resetting
            processed_data = PollJSONValidator.process_json_data_graceful(
                data, warnings, user_timezone
            )

            logger.info(
                f"✅ JSON IMPORT - Successfully processed poll: '{processed_data['name']}' with {len(warnings)} warnings"
            )

            # Return success with warnings as "errors" (they're actually warnings for the UI)
            return True, processed_data, warnings

        except Exception as e:
            logger.error(f"Unexpected error importing JSON: {e}")
            errors.append(f"Unexpected error processing file: {str(e)}")
            return False, None, errors

    @staticmethod
    def generate_example_json() -> Dict[str, Any]:
        """Generate an example JSON structure for poll import"""
        return {
            "name": "Weekend Movie Night",
            "question": "Which movie should we watch this Friday?",
            "options": ["The Matrix", "Inception", "Interstellar", "Blade Runner 2049"],
            "emojis": ["🔴", "🧠", "🌌", "🤖"],
            "server_id": "",
            "channel_id": "",
            "open_time": "2024-01-15T19:00",
            "close_time": "2024-01-15T23:59",
            "timezone": "US/Eastern",
            "anonymous": False,
            "multiple_choice": False,
            "ping_role_enabled": False,
            "ping_role_id": "",
            "image_message_text": "",
        }

    @staticmethod
    def get_json_schema_documentation() -> Dict[str, Any]:
        """Get documentation for the JSON schema"""
        return {
            "description": "JSON schema for importing poll data",
            "required_fields": {
                "name": {
                    "type": "string",
                    "description": "Poll name (3-255 characters)",
                    "example": "Weekend Movie Night",
                },
                "question": {
                    "type": "string",
                    "description": "Poll question (5-2000 characters)",
                    "example": "Which movie should we watch this Friday?",
                },
                "options": {
                    "type": "array of strings",
                    "description": "Poll options (2-10 items, each up to 500 characters)",
                    "example": ["Option 1", "Option 2", "Option 3"],
                },
            },
            "optional_fields": {
                "emojis": {
                    "type": "array of strings",
                    "description": "Custom emojis for each option (will use defaults if not provided)",
                    "example": ["🔴", "🟢", "🔵"],
                },
                "server_id": {
                    "type": "string",
                    "description": "Discord server ID (leave empty to select manually)",
                    "example": "123456789012345678",
                },
                "channel_id": {
                    "type": "string",
                    "description": "Discord channel ID (leave empty to select manually)",
                    "example": "123456789012345678",
                },
                "open_time": {
                    "type": "string",
                    "description": "When poll opens (ISO format: YYYY-MM-DDTHH:MM)",
                    "example": "2024-01-15T19:00",
                },
                "close_time": {
                    "type": "string",
                    "description": "When poll closes (ISO format: YYYY-MM-DDTHH:MM)",
                    "example": "2024-01-15T23:59",
                },
                "timezone": {
                    "type": "string",
                    "description": "Timezone for scheduling (defaults to US/Eastern)",
                    "example": "US/Eastern",
                },
                "anonymous": {
                    "type": "boolean",
                    "description": "Hide results until poll ends",
                    "example": False,
                },
                "multiple_choice": {
                    "type": "boolean",
                    "description": "Allow multiple selections",
                    "example": False,
                },
                "ping_role_enabled": {
                    "type": "boolean",
                    "description": "Ping a role when poll opens/closes",
                    "example": False,
                },
                "ping_role_id": {
                    "type": "string",
                    "description": "Role ID to ping (required if ping_role_enabled is true)",
                    "example": "123456789012345678",
                },
                "image_message_text": {
                    "type": "string",
                    "description": "Optional message to display with poll image",
                    "example": "Check out this awesome poll!",
                },
            },
            "notes": [
                "All time fields should be in ISO format (YYYY-MM-DDTHH:MM)",
                "If server_id or channel_id are empty, you'll need to select them manually",
                "If open_time or close_time are empty, default times will be set",
                "Emojis can be Unicode emojis or Discord custom emoji format (<:name:id>)",
                "The poll must run for at least 1 minute and no more than 30 days",
            ],
        }


class PollJSONExporter:
    """Handles exporting polls to JSON format"""

    @staticmethod
    def export_poll_to_json(poll) -> Dict[str, Any]:
        """Export a poll object to JSON format compatible with import"""
        from .database import TypeSafeColumn

        # Build the JSON structure
        json_data = {
            "name": TypeSafeColumn.get_string(poll, "name"),
            "question": TypeSafeColumn.get_string(poll, "question"),
            "options": poll.options if hasattr(poll, "options") else [],
        }

        # Add emojis if they exist
        if hasattr(poll, "emojis") and poll.emojis:
            json_data["emojis"] = poll.emojis

        # Add server and channel info
        server_id = TypeSafeColumn.get_string(poll, "server_id")
        if server_id:
            json_data["server_id"] = server_id

        channel_id = TypeSafeColumn.get_string(poll, "channel_id")
        if channel_id:
            json_data["channel_id"] = channel_id

        # Add poll settings
        json_data["multiple_choice"] = TypeSafeColumn.get_bool(
            poll, "multiple_choice", False
        )
        json_data["anonymous"] = TypeSafeColumn.get_bool(poll, "anonymous", False)

        # Add role ping settings
        ping_role_enabled = TypeSafeColumn.get_bool(poll, "ping_role_enabled", False)
        if ping_role_enabled:
            json_data["ping_role_enabled"] = True
            ping_role_id = TypeSafeColumn.get_string(poll, "ping_role_id")
            if ping_role_id:
                json_data["ping_role_id"] = ping_role_id

        # Add image message text if present
        image_message_text = TypeSafeColumn.get_string(poll, "image_message_text")
        if image_message_text:
            json_data["image_message_text"] = image_message_text

        # Add scheduling information
        timezone = TypeSafeColumn.get_string(poll, "timezone", "UTC")
        json_data["timezone"] = timezone

        # Add open and close times if they exist
        open_time = TypeSafeColumn.get_datetime(poll, "open_time")
        if open_time:
            json_data["open_time"] = open_time.isoformat()

        close_time = TypeSafeColumn.get_datetime(poll, "close_time")
        if close_time:
            json_data["close_time"] = close_time.isoformat()

        # Add metadata for context
        json_data["metadata"] = {
            "exported_at": datetime.now().isoformat(),
            "poll_id": TypeSafeColumn.get_int(poll, "id"),
            "status": TypeSafeColumn.get_string(poll, "status", "unknown"),
            "created_at": TypeSafeColumn.get_datetime(poll, "created_at").isoformat()
            if TypeSafeColumn.get_datetime(poll, "created_at")
            else None,
            "total_votes": poll.get_total_votes()
            if hasattr(poll, "get_total_votes")
            else 0,
            "server_name": TypeSafeColumn.get_string(poll, "server_name"),
            "channel_name": TypeSafeColumn.get_string(poll, "channel_name"),
        }

        return json_data

    @staticmethod
    def export_poll_to_json_string(poll, indent: int = 2) -> str:
        """Export a poll to a formatted JSON string"""
        json_data = PollJSONExporter.export_poll_to_json(poll)
        return json.dumps(json_data, indent=indent, ensure_ascii=False)

    @staticmethod
    def generate_filename(poll) -> str:
        """Generate a safe filename for the exported poll"""
        from .database import TypeSafeColumn
        import re

        poll_name = TypeSafeColumn.get_string(poll, "name", "poll")
        poll_id = TypeSafeColumn.get_int(poll, "id", 0)

        # Clean the poll name for use in filename
        safe_name = re.sub(r"[^\w\s-]", "", poll_name)
        safe_name = re.sub(r"[-\s]+", "-", safe_name)
        safe_name = safe_name.strip("-")[:50]  # Limit length

        if not safe_name:
            safe_name = "poll"

        return f"{safe_name}-{poll_id}.json"
