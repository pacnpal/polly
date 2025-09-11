"""
Super Admin System
Administrative system for managing all polls across all servers.
"""

import logging
from typing import List, Optional, Dict, Any
from fastapi import HTTPException, Depends, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, and_, or_
from datetime import datetime, timedelta
import pytz
from decouple import config

from .auth import require_auth, DiscordUser
from .database import get_db_session, Poll, Vote, User, Guild, Channel, TypeSafeColumn

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
        """Get all polls with filtering and pagination"""
        try:
            query = db_session.query(Poll)
            
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
            
            # Get total count before pagination
            total_count = query.count()
            
            # Apply pagination
            polls = query.offset(offset).limit(limit).all()
            
            # Convert to dict format with additional data
            poll_data = []
            for poll in polls:
                # Get vote count
                vote_count = db_session.query(Vote).filter(Vote.poll_id == poll.id).count()
                
                # Get unique voter count
                unique_voters = db_session.query(func.count(func.distinct(Vote.user_id))).filter(
                    Vote.poll_id == poll.id
                ).scalar() or 0
                
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
                    "vote_count": vote_count,
                    "unique_voters": unique_voters,
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
        """Get system-wide statistics"""
        try:
            # Poll statistics
            total_polls = db_session.query(Poll).count()
            active_polls = db_session.query(Poll).filter(Poll.status == "active").count()
            scheduled_polls = db_session.query(Poll).filter(Poll.status == "scheduled").count()
            closed_polls = db_session.query(Poll).filter(Poll.status == "closed").count()
            
            # Vote statistics
            total_votes = db_session.query(Vote).count()
            unique_voters = db_session.query(func.count(func.distinct(Vote.user_id))).scalar() or 0
            
            # Server statistics
            total_servers = db_session.query(func.count(func.distinct(Poll.server_id))).scalar() or 0
            
            # User statistics
            total_users = db_session.query(User).count()
            poll_creators = db_session.query(func.count(func.distinct(Poll.creator_id))).scalar() or 0
            
            # Recent activity (last 24 hours)
            yesterday = datetime.now(pytz.UTC) - timedelta(days=1)
            recent_polls = db_session.query(Poll).filter(Poll.created_at >= yesterday).count()
            recent_votes = db_session.query(Vote).filter(Vote.voted_at >= yesterday).count()
            
            # Top servers by poll count
            top_servers = db_session.query(
                Poll.server_name,
                Poll.server_id,
                func.count(Poll.id).label('poll_count')
            ).group_by(Poll.server_id, Poll.server_name).order_by(
                desc(func.count(Poll.id))
            ).limit(10).all()
            
            # Top creators by poll count
            top_creators = db_session.query(
                Poll.creator_id,
                func.count(Poll.id).label('poll_count')
            ).group_by(Poll.creator_id).order_by(
                desc(func.count(Poll.id))
            ).limit(10).all()
            
            return {
                "polls": {
                    "total": total_polls,
                    "active": active_polls,
                    "scheduled": scheduled_polls,
                    "closed": closed_polls,
                    "recent_24h": recent_polls
                },
                "votes": {
                    "total": total_votes,
                    "unique_voters": unique_voters,
                    "recent_24h": recent_votes
                },
                "servers": {
                    "total": total_servers,
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
                    "total": total_users,
                    "poll_creators": poll_creators,
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
            poll.close_time = datetime.now(pytz.UTC)
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
            
            # Get vote statistics
            vote_count = len(votes)
            unique_voters = len(set(vote.user_id for vote in votes))
            
            # Get results
            results = poll.get_results()
            
            # Prepare vote data
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
                    "name": poll.name,
                    "question": poll.question,
                    "status": poll.status,
                    "server_id": poll.server_id,
                    "server_name": poll.server_name,
                    "channel_id": poll.channel_id,
                    "channel_name": poll.channel_name,
                    "creator_id": poll.creator_id,
                    "message_id": poll.message_id,
                    "open_time": poll.open_time,
                    "close_time": poll.close_time,
                    "created_at": poll.created_at,
                    "timezone": poll.timezone,
                    "anonymous": poll.anonymous,
                    "multiple_choice": poll.multiple_choice,
                    "options": poll.options,
                    "emojis": poll.emojis,
                    "image_path": poll.image_path,
                    "ping_role_enabled": poll.ping_role_enabled,
                    "ping_role_name": poll.ping_role_name,
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

# Global service instance
super_admin_service = SuperAdminService()
