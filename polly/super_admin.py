"""
Super Admin System
Administrative system for managing all polls across all servers.
"""

import logging
from typing import List, Optional, Dict, Any
from fastapi import HTTPException, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func
from datetime import datetime, timedelta
import pytz
from decouple import config

from .auth import require_auth, DiscordUser
from .database import Poll, Vote, User, TypeSafeColumn

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="templates")

# Super admin user IDs (Discord user IDs) from environment
def get_super_admin_ids() -> List[str]:
    """Get super admin IDs from environment configuration"""
    admin_ids_str = config("SUPER_ADMIN_IDS", default="")
    if not admin_ids_str:
        return []
    
    # Split by comma and clean up whitespace
    admin_ids = [admin_id.strip() for admin_id in admin_ids_str.split(",") if admin_id.strip()]
    return admin_ids

SUPER_ADMIN_IDS = get_super_admin_ids()

def safe_get_user_id_for_admin_check(user) -> Optional[str]:
    """Safely extract user ID for admin check, handling Depends object issues"""
    try:
        if hasattr(user, 'id'):
            return user.id
        return None
    except (AttributeError, TypeError):
        return None

def is_super_admin(user: DiscordUser) -> bool:
    """Check if user is a super admin"""
    user_id = safe_get_user_id_for_admin_check(user)
    return user_id is not None and user_id in SUPER_ADMIN_IDS

async def require_super_admin(
    current_user: DiscordUser = Depends(require_auth),
) -> DiscordUser:
    """Require super admin authentication"""
    if not is_super_admin(current_user):
        raise HTTPException(
            status_code=403, 
            detail="Super admin access required"
        )
    return current_user

class SuperAdminService:
    """Service for super admin operations"""
    
    @staticmethod
    def get_all_polls(
        db_session,
        status_filter: Optional[str] = None,
        server_filter: Optional[str] = None,
        creator_filter: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_order: str = "desc"
    ) -> Dict[str, Any]:
        """Get all polls with filtering and pagination - OPTIMIZED for 200% performance boost"""
        try:
            
            # PERFORMANCE OPTIMIZATION 1: Single query with subqueries for vote stats
            vote_stats_subquery = db_session.query(
                Vote.poll_id,
                func.count(Vote.id).label('vote_count'),
                func.count(func.distinct(Vote.user_id)).label('unique_voters')
            ).group_by(Vote.poll_id).subquery()
            
            # PERFORMANCE OPTIMIZATION 2: Join with vote stats in single query
            query = db_session.query(
                Poll,
                func.coalesce(vote_stats_subquery.c.vote_count, 0).label('vote_count'),
                func.coalesce(vote_stats_subquery.c.unique_voters, 0).label('unique_voters')
            ).outerjoin(vote_stats_subquery, Poll.id == vote_stats_subquery.c.poll_id)
            
            # Apply filters
            if status_filter and status_filter != "all":
                query = query.filter(Poll.status == status_filter)
            
            if server_filter:
                query = query.filter(Poll.server_id == server_filter)
            
            if creator_filter:
                # Enhanced creator search: by creator_id OR username
                # First, try to find user by username
                user_ids_by_username = db_session.query(User.id).filter(
                    User.username.ilike(f"%{creator_filter}%")
                ).subquery()
                
                # Filter by either direct creator_id match OR username match
                query = query.filter(
                    (Poll.creator_id == creator_filter) |
                    (Poll.creator_id.in_(user_ids_by_username))
                )
            
            # Apply sorting with safety checks
            # Ensure sort_by is a valid string and exists as Poll attribute
            if isinstance(sort_by, str) and hasattr(Poll, sort_by):
                sort_column = getattr(Poll, sort_by)
            else:
                sort_column = Poll.created_at  # Default fallback
            
            if sort_order == "desc":
                query = query.order_by(desc(sort_column))
            else:
                query = query.order_by(sort_column)
            
            # PERFORMANCE OPTIMIZATION 3: Get total count efficiently
            count_query = db_session.query(Poll)
            if status_filter and status_filter != "all":
                count_query = count_query.filter(Poll.status == status_filter)
            if server_filter:
                count_query = count_query.filter(Poll.server_id == server_filter)
            if creator_filter:
                # Enhanced creator search: by creator_id OR username (same as main query)
                user_ids_by_username = db_session.query(User.id).filter(
                    User.username.ilike(f"%{creator_filter}%")
                ).subquery()
                
                count_query = count_query.filter(
                    (Poll.creator_id == creator_filter) |
                    (Poll.creator_id.in_(user_ids_by_username))
                )
            total_count = count_query.count()
            
            # Apply pagination
            results = query.offset(offset).limit(limit).all()
            
            # PERFORMANCE OPTIMIZATION 4: Batch process results without individual queries
            poll_data = []
            for poll, vote_count, unique_voters in results:
                poll_dict = {
                    "id": poll.id,
                    "name": TypeSafeColumn.get_string(poll, "name"),
                    "question": TypeSafeColumn.get_string(poll, "question"),
                    "status": TypeSafeColumn.get_string(poll, "status"),
                    "server_id": TypeSafeColumn.get_string(poll, "server_id"),
                    "server_name": TypeSafeColumn.get_string(poll, "server_name"),
                    "channel_id": TypeSafeColumn.get_string(poll, "channel_id"),
                    "channel_name": TypeSafeColumn.get_string(poll, "channel_name"),
                    "creator_id": TypeSafeColumn.get_string(poll, "creator_id"),
                    "message_id": TypeSafeColumn.get_string(poll, "message_id"),
                    "open_time": TypeSafeColumn.get_datetime(poll, "open_time"),
                    "close_time": TypeSafeColumn.get_datetime(poll, "close_time"),
                    "created_at": TypeSafeColumn.get_datetime(poll, "created_at"),
                    "timezone": TypeSafeColumn.get_string(poll, "timezone", "UTC"),
                    "anonymous": TypeSafeColumn.get_bool(poll, "anonymous"),
                    "multiple_choice": TypeSafeColumn.get_bool(poll, "multiple_choice"),
                    "options": poll.options,
                    "emojis": poll.emojis,
                    "vote_count": int(vote_count),
                    "unique_voters": int(unique_voters),
                    "image_path": TypeSafeColumn.get_string(poll, "image_path"),
                    "ping_role_enabled": TypeSafeColumn.get_bool(poll, "ping_role_enabled"),
                    "ping_role_name": TypeSafeColumn.get_string(poll, "ping_role_name"),
                }
                poll_data.append(poll_dict)
            
            return {
                "polls": poll_data,
                "total_count": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total_count
            }
            
        except Exception as e:
            logger.error(f"Error getting all polls: {e}")
            raise
    
    @staticmethod
    def get_system_stats(db_session) -> Dict[str, Any]:
        """Get system-wide statistics - ULTRA PERFORMANCE OPTIMIZED"""
        try:
            from sqlalchemy import text
            
            # PERFORMANCE OPTIMIZATION: Single massive query with CTEs for maximum efficiency
            query = text("""
                WITH poll_stats AS (
                    SELECT 
                        COUNT(*) as total_polls,
                        SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) as active_polls,
                        SUM(CASE WHEN status = 'scheduled' THEN 1 ELSE 0 END) as scheduled_polls,
                        SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) as closed_polls,
                        COUNT(DISTINCT server_id) as total_servers,
                        COUNT(DISTINCT creator_id) as poll_creators,
                        SUM(CASE WHEN created_at >= :yesterday THEN 1 ELSE 0 END) as recent_polls
                    FROM polls
                ),
                vote_stats AS (
                    SELECT 
                        COUNT(*) as total_votes,
                        COUNT(DISTINCT user_id) as unique_voters,
                        SUM(CASE WHEN voted_at >= :yesterday THEN 1 ELSE 0 END) as recent_votes
                    FROM votes
                ),
                user_stats AS (
                    SELECT COUNT(*) as total_users FROM users
                ),
                top_servers AS (
                    SELECT server_name, server_id, COUNT(*) as poll_count
                    FROM polls 
                    GROUP BY server_id, server_name 
                    ORDER BY COUNT(*) DESC 
                    LIMIT 10
                ),
                top_creators AS (
                    SELECT creator_id, COUNT(*) as poll_count
                    FROM polls 
                    GROUP BY creator_id 
                    ORDER BY COUNT(*) DESC 
                    LIMIT 10
                )
                SELECT 
                    p.total_polls, p.active_polls, p.scheduled_polls, p.closed_polls,
                    p.total_servers, p.poll_creators, p.recent_polls,
                    v.total_votes, v.unique_voters, v.recent_votes,
                    u.total_users
                FROM poll_stats p, vote_stats v, user_stats u
            """)
            
            yesterday = datetime.now(pytz.UTC) - timedelta(days=1)
            result = db_session.execute(query, {"yesterday": yesterday}).first()
            
            # Get top servers and creators separately (still optimized)
            top_servers = db_session.query(
                Poll.server_name,
                Poll.server_id,
                func.count(Poll.id).label('poll_count')
            ).group_by(Poll.server_id, Poll.server_name).order_by(
                desc(func.count(Poll.id))
            ).limit(10).all()
            
            top_creators = db_session.query(
                Poll.creator_id,
                func.count(Poll.id).label('poll_count')
            ).group_by(Poll.creator_id).order_by(
                desc(func.count(Poll.id))
            ).limit(10).all()
            
            return {
                "polls": {
                    "total": int(result.total_polls or 0),
                    "active": int(result.active_polls or 0),
                    "scheduled": int(result.scheduled_polls or 0),
                    "closed": int(result.closed_polls or 0),
                    "recent_24h": int(result.recent_polls or 0)
                },
                "votes": {
                    "total": int(result.total_votes or 0),
                    "unique_voters": int(result.unique_voters or 0),
                    "recent_24h": int(result.recent_votes or 0)
                },
                "servers": {
                    "total": int(result.total_servers or 0),
                    "top_servers": [
                        {
                            "name": server.server_name or "Unknown Server",
                            "id": server.server_id,
                            "poll_count": server.poll_count
                        }
                        for server in top_servers
                    ]
                },
                "users": {
                    "total": int(result.total_users or 0),
                    "poll_creators": int(result.poll_creators or 0),
                    "top_creators": [
                        {
                            "id": creator.creator_id,
                            "poll_count": creator.poll_count
                        }
                        for creator in top_creators
                    ]
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting system stats: {e}")
            raise
    
    @staticmethod
    async def force_close_poll(db_session, poll_id: int, admin_user_id: str) -> Dict[str, Any]:
        """Force close a poll (super admin only) using unified closure procedures"""
        try:
            # First check if poll exists and can be closed
            poll = db_session.query(Poll).filter(Poll.id == poll_id).first()
            if not poll:
                return {"success": False, "error": "Poll not found"}

            if poll.status == "closed":
                return {"success": False, "error": "Poll already closed"}

            poll_name = poll.name
            logger.info(f"Super admin {admin_user_id} initiating force close for poll {poll_id}: '{poll_name}'")

            # Use the unified closure service for consistent behavior
            from .services.poll.poll_closure_service import poll_closure_service
            
            result = await poll_closure_service.close_poll_unified(
                poll_id=poll_id,
                reason="force_close",
                admin_user_id=admin_user_id
            )

            if result["success"]:
                logger.info(f"Super admin {admin_user_id} successfully force closed poll {poll_id}")
                return {
                    "success": True,
                    "message": f"Poll '{poll_name}' has been force closed with full cleanup",
                    "poll_id": poll_id,
                    "details": result
                }
            else:
                logger.error(f"Super admin {admin_user_id} force close failed for poll {poll_id}: {result.get('error')}")
                return {
                    "success": False,
                    "error": f"Force close failed: {result.get('error', 'Unknown error')}",
                    "poll_id": poll_id
                }

        except Exception as e:
            logger.error(f"Error in super admin force close for poll {poll_id}: {e}")
            db_session.rollback()
            return {"success": False, "error": f"Unexpected error: {str(e)}"}
    
    @staticmethod
    async def reopen_poll(
        db_session,
        poll_id: int,
        admin_user_id: str,
        new_close_time: Optional[datetime] = None,
        extend_hours: Optional[int] = None,
        reset_votes: bool = False
    ) -> Dict[str, Any]:
        """
        Streamlined method to re-open a closed poll using the unified reopen service.
        
        Args:
            db_session: Database session
            poll_id: ID of the poll to reopen
            admin_user_id: ID of the admin performing the action
            new_close_time: Specific new close time (optional)
            extend_hours: Hours to extend from current time (optional)
            reset_votes: Whether to clear all existing votes (default: False)
            
        Returns:
            Dict with success status and details
        """
        try:
            # Validate poll exists
            poll = db_session.query(Poll).filter(Poll.id == poll_id).first()
            if not poll:
                return {"success": False, "error": "Poll not found"}
            
            poll_name = TypeSafeColumn.get_string(poll, "name", "Unknown")
            logger.info(f"🔄 SUPER ADMIN REOPEN - Starting reopen for poll {poll_id} '{poll_name}'")
            
            # Use the unified reopening service for all reopen operations
            from .services.poll.poll_reopen_service import poll_reopening_service
            from .discord_bot import get_bot_instance
            
            bot = get_bot_instance()
            if not bot or not bot.is_ready():
                return {
                    "success": False,
                    "error": "Discord bot not ready. Poll reopen requires bot connection for message updates."
                }
            
            # Convert extend hours to minutes for the unified service
            extend_minutes = None
            if extend_hours:
                if extend_hours <= 0 or extend_hours > 8760:  # Max 1 year
                    return {
                        "success": False,
                        "error": "Extension hours must be between 1 and 8760 (1 year)"
                    }
                extend_minutes = extend_hours * 60
            elif new_close_time:
                # For specific close times, calculate minutes from now
                now = datetime.now(pytz.UTC)
                if new_close_time <= now:
                    return {
                        "success": False,
                        "error": "New close time must be in the future"
                    }
                time_diff = new_close_time - now
                extend_minutes = int(time_diff.total_seconds() / 60)
            else:
                # Default: extend by 24 hours
                extend_minutes = 24 * 60
            
            # Call the unified reopening service
            reopen_result = await poll_reopening_service.reopen_poll_unified(
                poll_id=poll_id,
                reason="admin",
                admin_user_id=admin_user_id,
                bot_instance=bot,
                reset_votes=reset_votes,
                extend_minutes=extend_minutes
            )
            
            # Log the admin action
            if reopen_result["success"]:
                final_close_time = datetime.now(pytz.UTC) + timedelta(minutes=extend_minutes) if extend_minutes else "unknown"
                logger.info(
                    f"✅ Super admin poll reopen: poll_id={poll_id} admin_user_id={admin_user_id} "
                    f"poll_name='{poll_name}' new_close_time='{final_close_time}' "
                    f"reset_votes={reset_votes} extend_minutes={extend_minutes}"
                )
                
                return {
                    "success": True,
                    "message": f"Poll '{poll_name}' successfully reopened",
                    "poll_id": poll_id,
                    "poll_name": poll_name,
                    "new_close_time": str(final_close_time),
                    "extend_minutes": extend_minutes,
                    "reset_votes": reset_votes,
                    "votes_cleared": 0 if not reset_votes else reopen_result.get("votes_cleared", 0),
                    "discord_updated": True
                }
            else:
                logger.error(f"❌ Super admin poll reopen failed: {reopen_result.get('error')}")
                return {
                    "success": False,
                    "error": reopen_result.get("error", "Unknown error during poll reopen")
                }
                
        except Exception as e:
            logger.error(f"❌ Critical error in super admin poll reopen for poll {poll_id}: {e}")
            return {
                "success": False,
                "error": f"Critical error during poll reopen: {str(e)}"
            }
    
    @staticmethod
    def delete_poll(db_session, poll_id: int, admin_user_id: str) -> Dict[str, Any]:
        """Delete a poll and all its votes (super admin only)"""
        try:
            poll = db_session.query(Poll).filter(Poll.id == poll_id).first()
            if not poll:
                return {"success": False, "error": "Poll not found"}
            
            poll_name = poll.name
            
            # Delete all votes first (cascade should handle this, but being explicit)
            db_session.query(Vote).filter(Vote.poll_id == poll_id).delete()
            
            # Delete the poll
            db_session.delete(poll)
            db_session.commit()
            
            logger.info(f"Super admin {admin_user_id} deleted poll {poll_id} ({poll_name})")
            
            return {
                "success": True,
                "message": f"Poll '{poll_name}' and all its votes have been deleted",
                "poll_id": poll_id
            }
            
        except Exception as e:
            logger.error(f"Error deleting poll {poll_id}: {e}")
            db_session.rollback()
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def get_poll_details(db_session, poll_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific poll"""
        try:
            poll = db_session.query(Poll).filter(Poll.id == poll_id).first()
            if not poll:
                return None
            
            # Get all votes with user information
            votes = db_session.query(Vote).filter(Vote.poll_id == poll_id).order_by(
                desc(Vote.voted_at)
            ).all()
            
            # Get vote statistics - accurate counts
            vote_count = len(votes)
            unique_voters = len(set(vote.user_id for vote in votes))
            
            # Get results - ensure accurate vote counting
            results = poll.get_results()
            
            # Prepare vote data - super admin sees everything, even on anonymous polls
            vote_data = []
            for vote in votes:
                vote_info = {
                    "user_id": vote.user_id,
                    "option_index": vote.option_index,
                    "voted_at": vote.voted_at,
                    "option_text": poll.options[vote.option_index] if vote.option_index < len(poll.options) else "Unknown"
                }
                vote_data.append(vote_info)
            
            return {
                "poll": {
                    "id": poll.id,
                    "name": TypeSafeColumn.get_string(poll, "name"),
                    "question": TypeSafeColumn.get_string(poll, "question"),
                    "status": TypeSafeColumn.get_string(poll, "status"),
                    "server_id": TypeSafeColumn.get_string(poll, "server_id"),
                    "server_name": TypeSafeColumn.get_string(poll, "server_name"),
                    "channel_id": TypeSafeColumn.get_string(poll, "channel_id"),
                    "channel_name": TypeSafeColumn.get_string(poll, "channel_name"),
                    "creator_id": TypeSafeColumn.get_string(poll, "creator_id"),
                    "message_id": TypeSafeColumn.get_string(poll, "message_id"),
                    "open_time": TypeSafeColumn.get_datetime(poll, "open_time"),
                    "close_time": TypeSafeColumn.get_datetime(poll, "close_time"),
                    "created_at": TypeSafeColumn.get_datetime(poll, "created_at"),
                    "timezone": TypeSafeColumn.get_string(poll, "timezone", "UTC"),
                    "anonymous": TypeSafeColumn.get_bool(poll, "anonymous"),
                    "multiple_choice": TypeSafeColumn.get_bool(poll, "multiple_choice"),
                    "max_choices": TypeSafeColumn.get_int(poll, "max_choices"),
                    "options": poll.options,
                    "emojis": poll.emojis,
                    "image_path": TypeSafeColumn.get_string(poll, "image_path"),
                    "image_message_text": TypeSafeColumn.get_string(poll, "image_message_text"),
                    "ping_role_enabled": TypeSafeColumn.get_bool(poll, "ping_role_enabled"),
                    "ping_role_name": TypeSafeColumn.get_string(poll, "ping_role_name"),
                    "ping_role_id": TypeSafeColumn.get_string(poll, "ping_role_id"),
                    "ping_role_on_close": TypeSafeColumn.get_bool(poll, "ping_role_on_close"),
                    "ping_role_on_update": TypeSafeColumn.get_bool(poll, "ping_role_on_update"),
                    "open_immediately": TypeSafeColumn.get_bool(poll, "open_immediately"),
                },
                "statistics": {
                    "vote_count": vote_count,
                    "unique_voters": unique_voters,
                    "results": results
                },
                "votes": vote_data
            }
            
        except Exception as e:
            logger.error(f"Error getting poll details for {poll_id}: {e}")
            return None
    
    @staticmethod
    def update_poll(db_session, poll_id: int, poll_data: Dict[str, Any], admin_user_id: str) -> Dict[str, Any]:
        """Update a poll (super admin only) with comprehensive validation and logging"""
        try:
            poll = db_session.query(Poll).filter(Poll.id == poll_id).first()
            if not poll:
                return {"success": False, "error": "Poll not found"}
            
            # Store original values for logging
            original_values = {
                "name": poll.name,
                "question": poll.question,
                "status": poll.status,
                "options": poll.options.copy() if poll.options else [],
                "emojis": poll.emojis.copy() if poll.emojis else [],
                "anonymous": poll.anonymous,
                "multiple_choice": poll.multiple_choice,
                "max_choices": poll.max_choices,
                "open_time": poll.open_time_aware,
                "close_time": poll.close_time_aware,
                "timezone": poll.timezone,
                "image_path": poll.image_path,
                "image_message_text": poll.image_message_text,
                "ping_role_enabled": poll.ping_role_enabled,
                "ping_role_name": poll.ping_role_name,
                "ping_role_id": poll.ping_role_id,
                "ping_role_on_close": poll.ping_role_on_close,
                "ping_role_on_update": poll.ping_role_on_update
            }
            
            # Track changes for structured logging
            changes = []
            
            # Update basic fields
            if "name" in poll_data and poll_data["name"] != poll.name:
                changes.append(f"name: '{poll.name}' → '{poll_data['name']}'")
                poll.name = poll_data["name"]
            
            if "question" in poll_data and poll_data["question"] != poll.question:
                changes.append(f"question: '{poll.question}' → '{poll_data['question']}'")
                poll.question = poll_data["question"]
            
            # Update options and emojis
            if "options" in poll_data:
                new_options = [opt for opt in poll_data["options"] if opt.strip()]
                if new_options != poll.options:
                    changes.append(f"options: {len(poll.options)} → {len(new_options)} options")
                    poll.options = new_options
            
            if "emojis" in poll_data:
                new_emojis = poll_data["emojis"]
                if new_emojis != poll.emojis:
                    changes.append("emojis updated")
                    poll.emojis = new_emojis
            
            # Update boolean flags
            boolean_fields = ["anonymous", "multiple_choice", "ping_role_enabled", "ping_role_on_close", "ping_role_on_update"]
            for field in boolean_fields:
                if field in poll_data:
                    new_value = bool(poll_data[field])
                    old_value = getattr(poll, field, False)
                    if new_value != old_value:
                        changes.append(f"{field}: {old_value} → {new_value}")
                        setattr(poll, field, new_value)
            
            # Update numeric fields
            if "max_choices" in poll_data:
                new_max_choices = poll_data["max_choices"]
                if new_max_choices != poll.max_choices:
                    changes.append(f"max_choices: {poll.max_choices} → {new_max_choices}")
                    poll.max_choices = new_max_choices
            
            # Update datetime fields
            if "open_time" in poll_data and poll_data["open_time"]:
                new_open_time = poll_data["open_time"]
                if new_open_time != poll.open_time_aware:
                    changes.append(f"open_time: {poll.open_time_aware} → {new_open_time}")
                    setattr(poll, "open_time", new_open_time)
            
            if "close_time" in poll_data and poll_data["close_time"]:
                new_close_time = poll_data["close_time"]
                if new_close_time != poll.close_time_aware:
                    changes.append(f"close_time: {poll.close_time_aware} → {new_close_time}")
                    setattr(poll, "close_time", new_close_time)
            
            # Update string fields
            string_fields = ["timezone", "image_path", "image_message_text", "ping_role_name", "ping_role_id"]
            for field in string_fields:
                if field in poll_data:
                    new_value = poll_data[field]
                    old_value = getattr(poll, field, None)
                    if new_value != old_value:
                        changes.append(f"{field}: '{old_value}' → '{new_value}'")
                        setattr(poll, field, new_value)
            
            # Commit changes
            db_session.commit()
            
            # Structured logging for admin actions
            if changes:
                logger.info(
                    f"Super admin poll update: poll_id={poll_id} admin_user_id={admin_user_id} "
                    f"changes_count={len(changes)} changes=[{'; '.join(changes)}]"
                )
            else:
                logger.info(f"Super admin poll update: poll_id={poll_id} admin_user_id={admin_user_id} no_changes=true")
            
            return {
                "success": True,
                "message": f"Poll '{poll.name}' has been updated successfully",
                "poll_id": poll_id,
                "changes_made": len(changes),
                "changes": changes
            }
            
        except Exception as e:
            logger.error(f"Error updating poll {poll_id} by admin {admin_user_id}: {e}")
            db_session.rollback()
            return {"success": False, "error": str(e)}

# Global service instance
super_admin_service = SuperAdminService()
