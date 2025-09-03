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
    """Validates and processes poll JSON data"""
    
    REQUIRED_FIELDS = ['name', 'question', 'options']
    OPTIONAL_FIELDS = [
        'emojis', 'server_id', 'channel_id', 'open_time', 'close_time', 
        'timezone', 'anonymous', 'multiple_choice', 'ping_role_enabled', 
        'ping_role_id', 'image_message_text'
    ]
    
    @staticmethod
    def validate_json_structure(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate the basic structure of the JSON data"""
        errors = []
        
        # Check if data is a dictionary
        if not isinstance(data, dict):
            errors.append("JSON must be an object/dictionary")
            return False, errors
        
        # Check required fields
        for field in PollJSONValidator.REQUIRED_FIELDS:
            if field not in data:
                errors.append(f"Missing required field: '{field}'")
            elif not data[field]:
                errors.append(f"Required field '{field}' cannot be empty")
        
        # Validate field types and values
        if 'name' in data:
            if not isinstance(data['name'], str):
                errors.append("Field 'name' must be a string")
            elif len(data['name'].strip()) < 3:
                errors.append("Field 'name' must be at least 3 characters long")
            elif len(data['name'].strip()) > 255:
                errors.append("Field 'name' must be less than 255 characters")
        
        if 'question' in data:
            if not isinstance(data['question'], str):
                errors.append("Field 'question' must be a string")
            elif len(data['question'].strip()) < 5:
                errors.append("Field 'question' must be at least 5 characters long")
            elif len(data['question'].strip()) > 2000:
                errors.append("Field 'question' must be less than 2000 characters")
        
        if 'options' in data:
            if not isinstance(data['options'], list):
                errors.append("Field 'options' must be an array/list")
            elif len(data['options']) < 2:
                errors.append("At least 2 options are required")
            elif len(data['options']) > 10:
                errors.append("Maximum 10 options allowed")
            else:
                for i, option in enumerate(data['options']):
                    if not isinstance(option, str):
                        errors.append(f"Option {i+1} must be a string")
                    elif not option.strip():
                        errors.append(f"Option {i+1} cannot be empty")
                    elif len(option.strip()) > 500:
                        errors.append(f"Option {i+1} must be less than 500 characters")
        
        # Validate optional fields
        if 'emojis' in data:
            if not isinstance(data['emojis'], list):
                errors.append("Field 'emojis' must be an array/list")
            elif len(data['emojis']) > 10:
                errors.append("Maximum 10 emojis allowed")
            else:
                for i, emoji in enumerate(data['emojis']):
                    if not isinstance(emoji, str):
                        errors.append(f"Emoji {i+1} must be a string")
                    elif not emoji.strip():
                        errors.append(f"Emoji {i+1} cannot be empty")
        
        if 'server_id' in data and data['server_id']:
            if not isinstance(data['server_id'], str):
                errors.append("Field 'server_id' must be a string")
        
        if 'channel_id' in data and data['channel_id']:
            if not isinstance(data['channel_id'], str):
                errors.append("Field 'channel_id' must be a string")
        
        if 'timezone' in data and data['timezone']:
            if not isinstance(data['timezone'], str):
                errors.append("Field 'timezone' must be a string")
            else:
                try:
                    pytz.timezone(data['timezone'])
                except pytz.UnknownTimeZoneError:
                    errors.append(f"Invalid timezone: '{data['timezone']}'")
        
        if 'anonymous' in data:
            if not isinstance(data['anonymous'], bool):
                errors.append("Field 'anonymous' must be a boolean (true/false)")
        
        if 'multiple_choice' in data:
            if not isinstance(data['multiple_choice'], bool):
                errors.append("Field 'multiple_choice' must be a boolean (true/false)")
        
        if 'ping_role_enabled' in data:
            if not isinstance(data['ping_role_enabled'], bool):
                errors.append("Field 'ping_role_enabled' must be a boolean (true/false)")
        
        if 'ping_role_id' in data and data['ping_role_id']:
            if not isinstance(data['ping_role_id'], str):
                errors.append("Field 'ping_role_id' must be a string")
        
        if 'image_message_text' in data and data['image_message_text']:
            if not isinstance(data['image_message_text'], str):
                errors.append("Field 'image_message_text' must be a string")
            elif len(data['image_message_text'].strip()) > 2000:
                errors.append("Field 'image_message_text' must be less than 2000 characters")
        
        # Validate time fields if present
        if 'open_time' in data and data['open_time']:
            if not isinstance(data['open_time'], str):
                errors.append("Field 'open_time' must be a string in ISO format (YYYY-MM-DDTHH:MM)")
            else:
                try:
                    datetime.fromisoformat(data['open_time'])
                except ValueError:
                    errors.append("Field 'open_time' must be in ISO format (YYYY-MM-DDTHH:MM)")
        
        if 'close_time' in data and data['close_time']:
            if not isinstance(data['close_time'], str):
                errors.append("Field 'close_time' must be a string in ISO format (YYYY-MM-DDTHH:MM)")
            else:
                try:
                    datetime.fromisoformat(data['close_time'])
                except ValueError:
                    errors.append("Field 'close_time' must be in ISO format (YYYY-MM-DDTHH:MM)")
        
        # Validate time relationship if both times are present
        if ('open_time' in data and data['open_time'] and 
            'close_time' in data and data['close_time']):
            try:
                open_dt = datetime.fromisoformat(data['open_time'])
                close_dt = datetime.fromisoformat(data['close_time'])
                if close_dt <= open_dt:
                    errors.append("Field 'close_time' must be after 'open_time'")
                elif close_dt - open_dt < timedelta(minutes=1):
                    errors.append("Poll must run for at least 1 minute")
                elif close_dt - open_dt > timedelta(days=30):
                    errors.append("Poll cannot run for more than 30 days")
            except ValueError:
                pass  # Time format errors already caught above
        
        return len(errors) == 0, errors
    
    @staticmethod
    def process_json_data(data: Dict[str, Any], user_timezone: str = "US/Eastern") -> Dict[str, Any]:
        """Process and normalize JSON data for poll creation"""
        processed_data = {}
        
        # Process required fields
        processed_data['name'] = data['name'].strip()
        processed_data['question'] = data['question'].strip()
        processed_data['options'] = [option.strip() for option in data['options']]
        
        # Process optional fields with defaults
        processed_data['emojis'] = data.get('emojis', [])
        processed_data['server_id'] = data.get('server_id', '')
        processed_data['channel_id'] = data.get('channel_id', '')
        processed_data['anonymous'] = data.get('anonymous', False)
        processed_data['multiple_choice'] = data.get('multiple_choice', False)
        processed_data['ping_role_enabled'] = data.get('ping_role_enabled', False)
        processed_data['ping_role_id'] = data.get('ping_role_id', '')
        processed_data['image_message_text'] = data.get('image_message_text', '')
        
        # Process timezone
        timezone_str = data.get('timezone', user_timezone)
        try:
            pytz.timezone(timezone_str)
            processed_data['timezone'] = timezone_str
        except pytz.UnknownTimeZoneError:
            logger.warning(f"Invalid timezone '{timezone_str}', using {user_timezone}")
            processed_data['timezone'] = user_timezone
        
        # Process times - if not provided, set defaults
        if 'open_time' in data and data['open_time']:
            try:
                processed_data['open_time'] = data['open_time']
            except ValueError:
                logger.warning(f"Invalid open_time format: {data['open_time']}")
                processed_data['open_time'] = None
        else:
            processed_data['open_time'] = None
        
        if 'close_time' in data and data['close_time']:
            try:
                processed_data['close_time'] = data['close_time']
            except ValueError:
                logger.warning(f"Invalid close_time format: {data['close_time']}")
                processed_data['close_time'] = None
        else:
            processed_data['close_time'] = None
        
        # Ensure emojis list matches options length
        if len(processed_data['emojis']) < len(processed_data['options']):
            from .database import POLL_EMOJIS
            # Fill missing emojis with defaults
            for i in range(len(processed_data['emojis']), len(processed_data['options'])):
                if i < len(POLL_EMOJIS):
                    processed_data['emojis'].append(POLL_EMOJIS[i])
                else:
                    processed_data['emojis'].append('❓')
        elif len(processed_data['emojis']) > len(processed_data['options']):
            # Trim excess emojis
            processed_data['emojis'] = processed_data['emojis'][:len(processed_data['options'])]
        
        return processed_data


class PollJSONImporter:
    """Handles importing polls from JSON files"""
    
    @staticmethod
    async def import_from_json_file(file_content: bytes, user_timezone: str = "US/Eastern") -> Tuple[bool, Optional[Dict[str, Any]], List[str]]:
        """Import poll data from JSON file content"""
        errors = []
        
        try:
            # Decode file content
            try:
                json_str = file_content.decode('utf-8')
            except UnicodeDecodeError:
                errors.append("File must be UTF-8 encoded")
                return False, None, errors
            
            # Parse JSON
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError as e:
                errors.append(f"Invalid JSON format: {str(e)}")
                return False, None, errors
            
            # Validate JSON structure
            is_valid, validation_errors = PollJSONValidator.validate_json_structure(data)
            if not is_valid:
                errors.extend(validation_errors)
                return False, None, errors
            
            # Process and normalize data
            processed_data = PollJSONValidator.process_json_data(data, user_timezone)
            
            logger.info(f"Successfully imported poll JSON: {processed_data['name']}")
            return True, processed_data, []
            
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
            "options": [
                "The Matrix",
                "Inception",
                "Interstellar",
                "Blade Runner 2049"
            ],
            "emojis": [
                "🔴",
                "🧠",
                "🌌",
                "🤖"
            ],
            "server_id": "",
            "channel_id": "",
            "open_time": "2024-01-15T19:00",
            "close_time": "2024-01-15T23:59",
            "timezone": "US/Eastern",
            "anonymous": False,
            "multiple_choice": False,
            "ping_role_enabled": False,
            "ping_role_id": "",
            "image_message_text": ""
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
                    "example": "Weekend Movie Night"
                },
                "question": {
                    "type": "string", 
                    "description": "Poll question (5-2000 characters)",
                    "example": "Which movie should we watch this Friday?"
                },
                "options": {
                    "type": "array of strings",
                    "description": "Poll options (2-10 items, each up to 500 characters)",
                    "example": ["Option 1", "Option 2", "Option 3"]
                }
            },
            "optional_fields": {
                "emojis": {
                    "type": "array of strings",
                    "description": "Custom emojis for each option (will use defaults if not provided)",
                    "example": ["🔴", "🟢", "🔵"]
                },
                "server_id": {
                    "type": "string",
                    "description": "Discord server ID (leave empty to select manually)",
                    "example": "123456789012345678"
                },
                "channel_id": {
                    "type": "string",
                    "description": "Discord channel ID (leave empty to select manually)",
                    "example": "123456789012345678"
                },
                "open_time": {
                    "type": "string",
                    "description": "When poll opens (ISO format: YYYY-MM-DDTHH:MM)",
                    "example": "2024-01-15T19:00"
                },
                "close_time": {
                    "type": "string",
                    "description": "When poll closes (ISO format: YYYY-MM-DDTHH:MM)",
                    "example": "2024-01-15T23:59"
                },
                "timezone": {
                    "type": "string",
                    "description": "Timezone for scheduling (defaults to US/Eastern)",
                    "example": "US/Eastern"
                },
                "anonymous": {
                    "type": "boolean",
                    "description": "Hide results until poll ends",
                    "example": False
                },
                "multiple_choice": {
                    "type": "boolean",
                    "description": "Allow multiple selections",
                    "example": False
                },
                "ping_role_enabled": {
                    "type": "boolean",
                    "description": "Ping a role when poll opens/closes",
                    "example": False
                },
                "ping_role_id": {
                    "type": "string",
                    "description": "Role ID to ping (required if ping_role_enabled is true)",
                    "example": "123456789012345678"
                },
                "image_message_text": {
                    "type": "string",
                    "description": "Optional message to display with poll image",
                    "example": "Check out this awesome poll!"
                }
            },
            "notes": [
                "All time fields should be in ISO format (YYYY-MM-DDTHH:MM)",
                "If server_id or channel_id are empty, you'll need to select them manually",
                "If open_time or close_time are empty, default times will be set",
                "Emojis can be Unicode emojis or Discord custom emoji format (<:name:id>)",
                "The poll must run for at least 1 minute and no more than 30 days"
            ]
        }


class PollJSONExporter:
    """Handles exporting polls to JSON format"""
    
    @staticmethod
    def export_poll_to_json(poll) -> Dict[str, Any]:
        """Export a poll object to JSON format compatible with import"""
        from .database import TypeSafeColumn
        
        # Build the JSON structure
        json_data = {
            "name": TypeSafeColumn.get_string(poll, 'name'),
            "question": TypeSafeColumn.get_string(poll, 'question'),
            "options": poll.options if hasattr(poll, 'options') else [],
        }
        
        # Add emojis if they exist
        if hasattr(poll, 'emojis') and poll.emojis:
            json_data["emojis"] = poll.emojis
        
        # Add server and channel info
        server_id = TypeSafeColumn.get_string(poll, 'server_id')
        if server_id:
            json_data["server_id"] = server_id
            
        channel_id = TypeSafeColumn.get_string(poll, 'channel_id')
        if channel_id:
            json_data["channel_id"] = channel_id
        
        # Add poll settings
        json_data["multiple_choice"] = TypeSafeColumn.get_bool(poll, 'multiple_choice', False)
        json_data["anonymous"] = TypeSafeColumn.get_bool(poll, 'anonymous', False)
        
        # Add role ping settings
        ping_role_enabled = TypeSafeColumn.get_bool(poll, 'ping_role_enabled', False)
        if ping_role_enabled:
            json_data["ping_role_enabled"] = True
            ping_role_id = TypeSafeColumn.get_string(poll, 'ping_role_id')
            if ping_role_id:
                json_data["ping_role_id"] = ping_role_id
        
        # Add image message text if present
        image_message_text = TypeSafeColumn.get_string(poll, 'image_message_text')
        if image_message_text:
            json_data["image_message_text"] = image_message_text
        
        # Add scheduling information
        timezone = TypeSafeColumn.get_string(poll, 'timezone', 'UTC')
        json_data["timezone"] = timezone
        
        # Add open and close times if they exist
        open_time = TypeSafeColumn.get_datetime(poll, 'open_time')
        if open_time:
            json_data["open_time"] = open_time.isoformat()
            
        close_time = TypeSafeColumn.get_datetime(poll, 'close_time')
        if close_time:
            json_data["close_time"] = close_time.isoformat()
        
        # Add metadata for context
        json_data["metadata"] = {
            "exported_at": datetime.now().isoformat(),
            "poll_id": TypeSafeColumn.get_int(poll, 'id'),
            "status": TypeSafeColumn.get_string(poll, 'status', 'unknown'),
            "created_at": TypeSafeColumn.get_datetime(poll, 'created_at').isoformat() if TypeSafeColumn.get_datetime(poll, 'created_at') else None,
            "total_votes": poll.get_total_votes() if hasattr(poll, 'get_total_votes') else 0,
            "server_name": TypeSafeColumn.get_string(poll, 'server_name'),
            "channel_name": TypeSafeColumn.get_string(poll, 'channel_name')
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
        
        poll_name = TypeSafeColumn.get_string(poll, 'name', 'poll')
        poll_id = TypeSafeColumn.get_int(poll, 'id', 0)
        
        # Clean the poll name for use in filename
        safe_name = re.sub(r'[^\w\s-]', '', poll_name)
        safe_name = re.sub(r'[-\s]+', '-', safe_name)
        safe_name = safe_name.strip('-')[:50]  # Limit length
        
        if not safe_name:
            safe_name = 'poll'
        
        return f"{safe_name}-{poll_id}.json"
