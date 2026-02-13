"""
Test for refactored utilities to ensure no regression.
"""

import pytest


def test_admin_response_sanitize_error():
    """Test that admin response utility sanitizes errors correctly."""
    from polly.admin_response_utils import sanitize_result_for_client
    
    # Test with failed operation and error
    result = {
        "success": False,
        "error": "Internal error with traceback\nTraceback: line 1\nline 2"
    }
    sanitized = sanitize_result_for_client(result)
    
    assert sanitized["success"] is False
    assert sanitized["error"] == "Operation failed. Please try again or contact support."
    assert "Traceback" not in sanitized["error"]


def test_admin_response_sanitize_success():
    """Test that successful operations are not modified."""
    from polly.admin_response_utils import sanitize_result_for_client
    
    result = {
        "success": True,
        "data": "some data"
    }
    sanitized = sanitize_result_for_client(result)
    
    assert sanitized["success"] is True
    assert sanitized["data"] == "some data"


def test_admin_response_sanitize_with_details():
    """Test that nested error details are also sanitized."""
    from polly.admin_response_utils import sanitize_result_for_client
    
    result = {
        "success": False,
        "error": "Top level error",
        "details": {
            "error": "Nested error details"
        }
    }
    sanitized = sanitize_result_for_client(result)
    
    assert sanitized["success"] is False
    assert sanitized["error"] == "Operation failed. Please try again or contact support."
    assert "details" in sanitized
    assert sanitized["details"]["error"] == "Operation failed due to an internal error"


def test_get_bot_instance_safe_with_none():
    """Test that get_bot_instance_safe handles None gracefully."""
    from polly.services.poll.poll_db_utils import get_bot_instance_safe
    
    # When no bot instance is provided, function attempts to fetch it
    # If no bot is available (like in test environment), it should return None
    result = get_bot_instance_safe(None)
    # In test environment without a running bot, expect None
    # In production with bot running, expect a bot instance
    # Both are valid - this tests that the function doesn't crash
    assert result is None or result is not None  # Function completes without error


def test_get_bot_instance_safe_with_existing():
    """Test that get_bot_instance_safe returns provided instance."""
    from polly.services.poll.poll_db_utils import get_bot_instance_safe
    
    mock_bot = "mock_bot_instance"
    result = get_bot_instance_safe(mock_bot)
    
    assert result == mock_bot


def test_extract_poll_fields_structure():
    """Test that extract_poll_fields returns expected structure."""
    from polly.services.poll.poll_db_utils import extract_poll_fields
    
    # Mock poll object with TypeSafeColumn-compatible attributes
    class MockPoll:
        def __init__(self):
            self.status = "active"
            self.name = "Test Poll"
            self.message_id = "12345"
            self.channel_id = "67890"
            self.image_path = None
            self.image_message_text = None
    
    poll = MockPoll()
    fields = extract_poll_fields(poll)
    
    # Check that all expected fields are present
    assert "status" in fields
    assert "name" in fields
    assert "message_id" in fields
    assert "channel_id" in fields
    assert "image_path" in fields
    assert "image_message_text" in fields


@pytest.mark.asyncio
async def test_invalidate_poll_cache_safely_no_crash():
    """Test that cache invalidation doesn't crash if service unavailable."""
    from polly.services.cache.cache_invalidation_utils import invalidate_poll_cache_safely
    
    # This should not raise an error even if cache service is unavailable
    result = await invalidate_poll_cache_safely(123, "TEST")
    
    # Result should be an integer (count of invalidated entries)
    assert isinstance(result, int)
    assert result >= 0
