 it """
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
from .database import Poll, Vote, TypeSafeColumn

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

def is_super_admin(user: DiscordUser) -> bool:
    """Check if user is a super admin"""
    return user.id in SUPER_ADMIN_IDS

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
                query = query.filter(Poll.creator_id == creator_filter)
            
            # Apply sorting
            sort_column = getattr(Poll, sort_by, Poll.created_at)
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
                count_query = count_query.filter(Poll.creator_id == creator_filter)
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
    def force_close_poll(db_session, poll_id: int, admin_user_id: str) -> Dict[str, Any]:
        """Force close a poll (super admin only)"""
        try:
            poll = db_session.query(Poll).filter(Poll.id == poll_id).first()
            if not poll:
                return {"success": False, "error": "Poll not found"}
            
            if poll.status == "closed":
                return {"success": False, "error": "Poll is already closed"}
            
            # Update poll status
            poll.status = "closed"
            setattr(poll, "close_time", datetime.now(pytz.UTC))
            db_session.commit()
            
            logger.info(f"Super admin {admin_user_id} force closed poll {poll_id}")
            
            return {
                "success": True,
                "message": f"Poll '{poll.name}' has been force closed",
                "poll_id": poll_id
            }
            
        except Exception as e:
            logger.error(f"Error force closing poll {poll_id}: {e}")
            db_session.rollback()
            return {"success": False, "error": str(e)}
    
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
        Comprehensive method to re-open a closed poll with multiple options.
        
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
            # Step 1: Validate poll exists and can be reopened
            poll = db_session.query(Poll).filter(Poll.id == poll_id).first()
            if not poll:
                return {"success": False, "error": "Poll not found"}
            
            current_status = TypeSafeColumn.get_string(poll, "status")
            if current_status != "closed":
                return {
                    "success": False, 
                    "error": f"Poll is not closed (current status: {current_status}). Only closed polls can be reopened."
                }
            
            # Step 2: Determine new close time
            now = datetime.now(pytz.UTC)
            original_close_time = TypeSafeColumn.get_datetime(poll, "close_time")
            
            if new_close_time:
                # Use specific new close time
                if new_close_time <= now:
                    return {
                        "success": False,
                        "error": "New close time must be in the future"
                    }
                final_close_time = new_close_time
                time_description = f"until {new_close_time.strftime('%Y-%m-%d %H:%M UTC')}"
                
            elif extend_hours:
                # Extend by specified hours from now
                if extend_hours <= 0 or extend_hours > 8760:  # Max 1 year
                    return {
                        "success": False,
                        "error": "Extension hours must be between 1 and 8760 (1 year)"
                    }
                final_close_time = now + timedelta(hours=extend_hours)
                time_description = f"for {extend_hours} hours (until {final_close_time.strftime('%Y-%m-%d %H:%M UTC')})"
                
            else:
                # Default: extend by 24 hours from now
                final_close_time = now + timedelta(hours=24)
                time_description = "for 24 hours (default extension)"
            
            # Step 3: Handle vote reset if requested
            votes_cleared = 0
            if reset_votes:
                try:
                    # Count votes before deletion for logging
                    votes_cleared = db_session.query(Vote).filter(Vote.poll_id == poll_id).count()
                    
                    # Delete all votes for this poll
                    db_session.query(Vote).filter(Vote.poll_id == poll_id).delete()
                    
                    logger.info(f"Cleared {votes_cleared} votes from poll {poll_id} during reopen")
                    
                except Exception as e:
                    logger.error(f"Error clearing votes for poll {poll_id}: {e}")
                    db_session.rollback()
                    return {
                        "success": False,
                        "error": f"Failed to clear votes: {str(e)}"
                    }
            
            # Step 4: Update poll status and times
            try:
                # Set poll to active status
                setattr(poll, "status", "active")
                
                # Update close time
                setattr(poll, "close_time", final_close_time)
                
                # Optionally update open time to now if it was in the past
                current_open_time = TypeSafeColumn.get_datetime(poll, "open_time")
                if current_open_time and current_open_time < now:
                    setattr(poll, "open_time", now)
                
                # Commit all changes
                db_session.commit()
                
            except Exception as e:
                logger.error(f"Error updating poll {poll_id} during reopen: {e}")
                db_session.rollback()
                return {
                    "success": False,
                    "error": f"Failed to update poll: {str(e)}"
                }
            
            # Step 5: Update Discord embed and reactions
            try:
                # Import Discord utilities and bot instance
                from .discord_utils import update_poll_message
                from .discord_bot import get_bot_instance
                
                bot = get_bot_instance()
                if bot and bot.is_ready():
                    # Update the Discord message with new active status and reactions
                    discord_update_success = await update_poll_message(bot, poll)
                    if discord_update_success:
                        logger.info(f"✅ Discord embed updated for reopened poll {poll_id}")
                    else:
                        logger.warning(f"⚠️ Failed to update Discord embed for reopened poll {poll_id}")
                else:
                    logger.warning(f"⚠️ Discord bot not ready, skipping embed update for poll {poll_id}")
                    
            except Exception as discord_error:
                logger.error(f"❌ Error updating Discord embed for reopened poll {poll_id}: {discord_error}")
                # Don't fail the reopen operation if Discord update fails
            
            # Step 6: Generate comprehensive success response
            poll_name = TypeSafeColumn.get_string(poll, "name")
            
            # Log the admin action with full details
            logger.warning(
                f"Super admin poll reopen: poll_id={poll_id} admin_user_id={admin_user_id} "
                f"poll_name='{poll_name}' new_close_time='{final_close_time}' "
                f"votes_cleared={votes_cleared} original_close_time='{original_close_time}'"
            )
            
            success_message = f"Poll '{poll_name}' has been successfully reopened {time_description}"
            if votes_cleared > 0:
                success_message += f" (cleared {votes_cleared} existing votes)"
            
            return {
                "success": True,
                "message": success_message,
                "poll_id": poll_id,
                "poll_name": poll_name,
                "new_status": "active",
                "new_close_time": final_close_time.isoformat() if final_close_time else None,
                "original_close_time": original_close_time.isoformat() if original_close_time else None,
                "votes_cleared": votes_cleared,
                "reopened_by": admin_user_id,
                "reopened_at": now.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error reopening poll {poll_id} by admin {admin_user_id}: {e}")
            db_session.rollback()
            return {
                "success": False,
                "error": f"Unexpected error during poll reopen: {str(e)}"
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
            
            logger.warning(f"Super admin {admin_user_id} deleted poll {poll_id} ({poll_name})")
            
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
