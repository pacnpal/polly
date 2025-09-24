"""
Poll Reopening Service
Unified poll reopening procedures for consistent behavior across all reopening methods.
Handles updating existing Discord messages rather than creating new ones.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import pytz
import discord
from pathlib import Path

from .database import get_db_session, Poll, Vote, TypeSafeColumn
from .error_handler import PollErrorHandler
from .discord_utils import update_poll_message

logger = logging.getLogger(__name__)


class PollReopeningService:
    """Unified service for reopening polls with consistent procedures"""

    @staticmethod
    async def reopen_poll_unified(
        poll_id: int, 
        reason: str = "manual",
        admin_user_id: Optional[str] = None,
        bot_instance=None,
        reset_votes: bool = False,
        extend_minutes: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Unified poll reopening procedure that ensures consistent behavior
        regardless of how the poll is being reopened.
        
        Key difference from opening service: This UPDATES existing Discord messages
        instead of creating new ones.
        
        Args:
            poll_id: ID of the poll to reopen
            reason: Reason for reopening ("manual", "admin", "recovery", etc.)
            admin_user_id: ID of admin user if this is an admin action
            bot_instance: Discord bot instance (will be fetched if not provided)
            reset_votes: Whether to clear existing votes (default: False)
            extend_minutes: Minutes to extend the poll (optional)
            
        Returns:
            Dict with success status and details
        """
        try:
            logger.info(f"🔄 UNIFIED REOPEN {poll_id} - Starting unified poll reopening (reason: {reason})")
            
            # Get bot instance if not provided
            if not bot_instance:
                from .discord_bot import get_bot_instance
                bot_instance = get_bot_instance()
                
            if not bot_instance:
                logger.error(f"❌ UNIFIED REOPEN {poll_id} - Bot instance not available")
                return {"success": False, "error": "Bot instance not available"}

            # STEP 1: Get poll data and validate eligibility for reopening
            db = get_db_session()
            poll = None
            try:
                from sqlalchemy.orm import joinedload

                poll = (
                    db.query(Poll)
                    .options(joinedload(Poll.votes))
                    .filter(Poll.id == poll_id)
                    .first()
                )
                if not poll:
                    logger.error(f"❌ UNIFIED REOPEN {poll_id} - Poll not found in database")
                    return {"success": False, "error": "Poll not found"}

                # Check current status - only allow reopening of closed polls
                current_status = TypeSafeColumn.get_string(poll, "status")
                poll_name = TypeSafeColumn.get_string(poll, "name", "Unknown")
                
                logger.info(f"📊 UNIFIED REOPEN {poll_id} - Poll '{poll_name}' found, status: {current_status}")

                # Validate reopening eligibility
                if current_status != "closed":
                    logger.error(f"❌ UNIFIED REOPEN {poll_id} - Cannot reopen poll that is not closed (current status: {current_status})")
                    return {"success": False, "error": f"Poll is not closed (current status: {current_status})"}

                # Check if poll has existing Discord message
                message_id = TypeSafeColumn.get_string(poll, "message_id")
                channel_id = TypeSafeColumn.get_string(poll, "channel_id")
                
                if not message_id:
                    logger.error(f"❌ UNIFIED REOPEN {poll_id} - Poll has no Discord message ID")
                    return {"success": False, "error": "Poll has no Discord message to update"}
                    
                if not channel_id:
                    logger.error(f"❌ UNIFIED REOPEN {poll_id} - Poll has no channel ID")
                    return {"success": False, "error": "Poll has no channel ID"}
                
            except Exception as e:
                logger.error(f"❌ UNIFIED REOPEN {poll_id} - Error fetching poll data: {e}")
                return {"success": False, "error": f"Database error: {str(e)}"}
            finally:
                db.close()

            # STEP 2: Reset votes if requested
            if reset_votes:
                logger.info(f"🗳️ UNIFIED REOPEN {poll_id} - Resetting votes as requested")
                try:
                    db = get_db_session()
                    votes_deleted = db.query(Vote).filter(Vote.poll_id == poll_id).delete()
                    db.commit()
                    logger.info(f"✅ UNIFIED REOPEN {poll_id} - Deleted {votes_deleted} votes")
                except Exception as e:
                    db.rollback()
                    logger.error(f"❌ UNIFIED REOPEN {poll_id} - Error resetting votes: {e}")
                    return {"success": False, "error": f"Failed to reset votes: {str(e)}"}
                finally:
                    db.close()

            # STEP 3: Extend poll duration if requested
            original_close_time = None
            if extend_minutes and extend_minutes > 0:
                logger.info(f"⏰ UNIFIED REOPEN {poll_id} - Extending poll by {extend_minutes} minutes")
                try:
                    db = get_db_session()
                    poll = db.query(Poll).filter(Poll.id == poll_id).first()
                    if poll:
                        # Store original close time for logging
                        original_close_time = poll.close_time_aware
                        
                        # Extend from current time, not original close time
                        new_close_time = datetime.now(pytz.UTC) + timedelta(minutes=extend_minutes)
                        
                        # Update close time in database
                        setattr(poll, "close_time", new_close_time.replace(tzinfo=None))
                        db.commit()
                        
                        logger.info(f"✅ UNIFIED REOPEN {poll_id} - Extended poll close time to {new_close_time}")
                    else:
                        logger.error(f"❌ UNIFIED REOPEN {poll_id} - Poll not found for time extension")
                        return {"success": False, "error": "Poll not found for time extension"}
                except Exception as e:
                    db.rollback()
                    logger.error(f"❌ UNIFIED REOPEN {poll_id} - Error extending poll duration: {e}")
                    return {"success": False, "error": f"Failed to extend poll duration: {str(e)}"}
                finally:
                    db.close()

            # STEP 4: Update poll status to active
            logger.info(f"📊 UNIFIED REOPEN {poll_id} - Updating poll status to active")
            db = get_db_session()
            try:
                poll = db.query(Poll).filter(Poll.id == poll_id).first()
                if poll:
                    setattr(poll, "status", "active")
                    db.commit()
                    logger.info(f"✅ UNIFIED REOPEN {poll_id} - Poll status updated to active")
                else:
                    logger.error(f"❌ UNIFIED REOPEN {poll_id} - Poll not found for status update")
                    return {"success": False, "error": "Poll not found for status update"}
            except Exception as e:
                db.rollback()
                logger.error(f"❌ UNIFIED REOPEN {poll_id} - Error updating poll status: {e}")
                return {"success": False, "error": f"Database update failed: {str(e)}"}
            finally:
                db.close()

            # STEP 5: Update Discord message with new poll state
            logger.info(f"🔄 UNIFIED REOPEN {poll_id} - Updating Discord message")
            try:
                # Get fresh poll data with votes for Discord update
                db = get_db_session()
                try:
                    from sqlalchemy.orm import joinedload
                    fresh_poll = (
                        db.query(Poll)
                        .options(joinedload(Poll.votes))
                        .filter(Poll.id == poll_id)
                        .first()
                    )
                    
                    if not fresh_poll:
                        logger.error(f"❌ UNIFIED REOPEN {poll_id} - Could not fetch fresh poll data")
                        return {"success": False, "error": "Could not fetch updated poll data"}
                    
                    # Update the Discord message with new poll state
                    update_success = await update_poll_message(bot_instance, fresh_poll)
                    
                    if update_success:
                        logger.info(f"✅ UNIFIED REOPEN {poll_id} - Discord message updated successfully")
                    else:
                        logger.error(f"❌ UNIFIED REOPEN {poll_id} - Failed to update Discord message")
                        return {"success": False, "error": "Failed to update Discord message"}
                        
                finally:
                    db.close()
                    
            except Exception as e:
                logger.error(f"❌ UNIFIED REOPEN {poll_id} - Error updating Discord message: {e}")
                return {"success": False, "error": f"Discord update failed: {str(e)}"}

            # STEP 6: Schedule poll closure if extended
            if extend_minutes and extend_minutes > 0:
                try:
                    from .background_tasks import get_scheduler
                    from .timezone_scheduler_fix import TimezoneAwareScheduler
                    
                    scheduler = get_scheduler()
                    if scheduler and scheduler.running:
                        # Remove any existing close job
                        close_job_id = f"close_poll_{poll_id}"
                        existing_job = scheduler.get_job(close_job_id)
                        if existing_job:
                            scheduler.remove_job(close_job_id)
                            logger.info(f"🗑️ UNIFIED REOPEN {poll_id} - Removed existing close job")
                        
                        # Schedule new close job
                        db = get_db_session()
                        try:
                            poll = db.query(Poll).filter(Poll.id == poll_id).first()
                            if poll:
                                poll_close_time = poll.close_time_aware
                                poll_timezone = TypeSafeColumn.get_string(poll, "timezone", "UTC")
                                
                                # Ensure we have a proper datetime object
                                if poll_close_time and isinstance(poll_close_time, datetime) and poll_close_time > datetime.now(pytz.UTC):
                                    from .background_tasks import close_poll
                                    
                                    tz_scheduler = TimezoneAwareScheduler(scheduler)
                                    success = tz_scheduler.schedule_poll_closing(
                                        poll_id, poll_close_time, poll_timezone, close_poll
                                    )
                                    
                                    if success:
                                        logger.info(f"✅ UNIFIED REOPEN {poll_id} - Scheduled new poll closure")
                                    else:
                                        logger.warning(f"⚠️ UNIFIED REOPEN {poll_id} - Failed to schedule new poll closure")
                        finally:
                            db.close()
                            
                except Exception as schedule_error:
                    logger.error(f"❌ UNIFIED REOPEN {poll_id} - Error scheduling poll closure: {schedule_error}")
                    # Don't fail the reopening process if scheduling fails

            # STEP 7: Cache management - invalidate stale caches
            try:
                from .enhanced_cache_service import get_enhanced_cache_service
                
                enhanced_cache = get_enhanced_cache_service()
                if enhanced_cache:
                    # Invalidate any stale poll-related caches
                    invalidated = await enhanced_cache.invalidate_poll_related_cache(poll_id)
                    logger.info(f"✅ UNIFIED REOPEN {poll_id} - Invalidated {invalidated} stale cache entries")
                    
            except Exception as cache_error:
                logger.error(f"❌ UNIFIED REOPEN {poll_id} - Error managing caches: {cache_error}")
                # Don't fail the reopening process if cache management fails

            # Log admin action if this was an admin reopening
            if admin_user_id:
                logger.info(f"Admin poll reopening: poll_id={poll_id} admin_user_id={admin_user_id} reason={reason}")

            logger.info(f"🎉 UNIFIED REOPEN {poll_id} - Unified poll reopening process completed successfully")
            
            # Prepare response with details
            response = {
                "success": True,
                "message": f"Poll reopened successfully via {reason}",
                "poll_id": poll_id,
                "reason": reason,
                "admin_user_id": admin_user_id,
                "votes_reset": reset_votes,
                "extended_minutes": extend_minutes,
                "discord_message_updated": True
            }
            
            if original_close_time and extend_minutes and isinstance(original_close_time, datetime):
                response["original_close_time"] = original_close_time.isoformat()
                response["new_close_time"] = (datetime.now(pytz.UTC) + timedelta(minutes=extend_minutes)).isoformat()
            
            return response

        except Exception as e:
            # Handle unexpected reopening errors
            logger.error(f"❌ UNIFIED REOPEN {poll_id} - Unexpected error in unified reopening: {str(e)}")
            
            # Try to notify via error handler if possible
            try:
                if bot_instance:
                    await PollErrorHandler.handle_poll_creation_error(e, {"poll_id": poll_id}, bot_instance)
            except:
                pass  # Error handler failed, but don't mask original error
                
            return {
                "success": False,
                "error": f"Unexpected error during poll reopening: {str(e)}",
                "poll_id": poll_id
            }


# Global service instance
poll_reopening_service = PollReopeningService()