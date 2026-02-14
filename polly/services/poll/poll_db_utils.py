"""
Poll Database Utilities
Shared database query helpers for poll services to reduce code duplication.
"""

import logging
from typing import Optional, Tuple, Dict, Any
from sqlalchemy.orm import joinedload

from ...database import get_db_session, Poll, TypeSafeColumn

logger = logging.getLogger(__name__)


def get_bot_instance_safe(bot_instance=None):
    """
    Safely get bot instance, fetching if not provided.
    
    Args:
        bot_instance: Optional bot instance to use
        
    Returns:
        Bot instance or None if not available
    """
    if not bot_instance:
        from ...discord_bot import get_bot_instance
        bot_instance = get_bot_instance()
    return bot_instance


def get_poll_with_votes(poll_id: int, db=None) -> Tuple[Optional[Poll], Any]:
    """
    Fetch poll with votes eagerly loaded.
    
    This is a common pattern used across all poll services to fetch a poll
    with its related votes in a single query.
    
    Note: The caller is responsible for closing the database session in all cases,
    including exceptions.
    
    Args:
        poll_id: ID of the poll to fetch
        db: Optional database session (will create one if not provided)
        
    Returns:
        Tuple of (poll, db_session) or (None, db_session) if poll not found
        The caller must close the db_session after use.
    """
    if db is None:
        db = get_db_session()
    
    try:
        poll = (
            db.query(Poll)
            .options(joinedload(Poll.votes))
            .filter(Poll.id == poll_id)
            .first()
        )
        return poll, db
    except Exception as e:
        logger.error(f"Error fetching poll {poll_id}: {e}")
        # Don't close the session - let the caller handle it
        raise


def extract_poll_fields(poll) -> Dict[str, Any]:
    """
    Extract commonly used poll fields using TypeSafeColumn.
    
    Args:
        poll: Poll object attached to a session
        
    Returns:
        Dictionary containing extracted fields
    """
    return {
        "status": TypeSafeColumn.get_string(poll, "status"),
        "name": TypeSafeColumn.get_string(poll, "name", "Unknown"),
        "message_id": TypeSafeColumn.get_string(poll, "message_id"),
        "channel_id": TypeSafeColumn.get_string(poll, "channel_id"),
        "image_path": TypeSafeColumn.get_string(poll, "image_path"),
        "image_message_text": TypeSafeColumn.get_string(poll, "image_message_text"),
    }
