"""
Data utility functions for sanitization and processing
"""
import logging
from html import unescape
from typing import Any, Dict, List, Union

logger = logging.getLogger(__name__)


def decode_html_entities_safe(text: str) -> str:
    """Safely decode HTML entities from text to prevent JSON serialization errors"""
    if not isinstance(text, str):
        return text
    try:
        # Decode common HTML entities that cause JSON parsing issues
        return unescape(text)
    except Exception as e:
        logger.warning(f"Error decoding HTML entities from text '{text}': {e}")
        return text


def sanitize_data_for_json(data: Any) -> Any:
    """Recursively sanitize data to ensure it's JSON-serializable"""
    if isinstance(data, dict):
        return {key: sanitize_data_for_json(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [sanitize_data_for_json(item) for item in data]
    elif isinstance(data, str):
        return decode_html_entities_safe(data)
    else:
        return data
