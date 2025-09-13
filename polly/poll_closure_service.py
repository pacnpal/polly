"""
Poll Closure Service
Unified poll closure procedures for consistent behavior across all closing methods.
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional
import pytz
import discord

from .database import get_db_session, Poll, Vote, TypeSafeColumn
from .error_handler import PollErrorHandler

logger = logging.getLogger(__name__)


class PollClosureService:
    """Unified service for closing polls with consistent procedures"""

    @staticmethod
    async def close_poll_unified(
        poll_id: int, 
        reason: str = "manual",
        admin_user_id: Optional[str] = None,
        bot_instance=None
    ) -> Dict[str, Any]:
        """
        Unified poll closure procedure that ensures consistent behavior
        regardless of how the poll is being closed (scheduled, manual, super admin, etc.)
        
        Args:
            poll_id: ID of the poll to close
            reason: Reason for closure ("scheduled", "manual", "force_close", etc.)
            admin_user_id: ID of admin user if this is an admin action
            bot_instance: Discord bot instance (will be fetched if not provided)
            
        Returns:
            Dict with success status and details
        """
        try:
            logger.info(f"🏁 UNIFIED CLOSE {poll_id} - Starting unified poll closure (reason: {reason})")
            
            # Get bot instance if not provided
            if not bot_instance:
                from .discord_bot import get_bot_instance
                bot_instance = get_bot_instance()
                
            if not bot_instance:
                logger.error(f"❌ UNIFIED CLOSE {poll_id} - Bot instance not available")
                return {"success": False, "error": "Bot instance not available"}

            # STEP 1: Get poll data BEFORE closing it
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
                    logger.error(f"❌ UNIFIED CLOSE {poll_id} - Poll not found in database")
                    return {"success": False, "error": "Poll not found"}

                # Check if already closed
                current_status = TypeSafeColumn.get_string(poll, "status")
                if current_status == "closed":
                    logger.info(f"ℹ️ UNIFIED CLOSE {poll_id} - Poll already closed, skipping")
                    return {"success": True, "message": "Poll was already closed", "already_closed": True}

                # Extract poll data while still attached to session
                message_id = TypeSafeColumn.get_string(poll, "message_id")
                channel_id = TypeSafeColumn.get_string(poll, "channel_id")
                poll_name = TypeSafeColumn.get_string(poll, "name", "Unknown")
                
                logger.info(f"📊 UNIFIED CLOSE {poll_id} - Poll '{poll_name}' found, status: {current_status}")

            except Exception as e:
                logger.error(f"❌ UNIFIED CLOSE {poll_id} - Error fetching poll data: {e}")
                return {"success": False, "error": f"Database error: {str(e)}"}
            finally:
                db.close()

            # STEP 2: Close poll in database using bulletproof operations
            try:
                from .poll_operations import BulletproofPollOperations
                
                bulletproof_ops = BulletproofPollOperations(bot_instance)
                result = await bulletproof_ops.bulletproof_poll_closure(poll_id, reason)

                if not result["success"]:
                    error_msg = await PollErrorHandler.handle_poll_closure_error(
                        Exception(result["error"]), poll_id, bot_instance
                    )
                    logger.error(f"❌ UNIFIED CLOSE {poll_id} - Bulletproof closure failed: {error_msg}")
                    return {"success": False, "error": result["error"]}
                else:
                    logger.info(f"✅ UNIFIED CLOSE {poll_id} - Poll status updated to closed in database")

            except Exception as e:
                error_msg = await PollErrorHandler.handle_poll_closure_error(e, poll_id, bot_instance)
                logger.error(f"❌ UNIFIED CLOSE {poll_id} - Bulletproof closure exception: {error_msg}")
                return {"success": False, "error": f"Database closure failed: {str(e)}"}

            # STEP 3: Get fresh poll data and update the existing message to show it's closed FIRST
            db = get_db_session()
            try:
                from sqlalchemy.orm import joinedload

                fresh_poll = (
                    db.query(Poll)
                    .options(joinedload(Poll.votes))
                    .filter(Poll.id == poll_id)
                    .first()
                )
                if fresh_poll:
                    # Update the poll embed to show it's closed with final results BEFORE clearing reactions
                    try:
                        from .discord_utils import update_poll_message
                        await update_poll_message(bot_instance, fresh_poll)
                        logger.info(f"✅ UNIFIED CLOSE {poll_id} - Updated poll message to show closed status with final results")
                    except Exception as update_error:
                        logger.error(f"❌ UNIFIED CLOSE {poll_id} - Error updating poll message: {update_error}")
                        # Continue with closure process even if message update fails

                # STEP 4: Clear reactions from Discord message AFTER updating the embed
                if message_id and channel_id:
                    try:
                        channel = bot_instance.get_channel(int(channel_id))
                        if channel and isinstance(channel, discord.TextChannel):
                            try:
                                message = await channel.fetch_message(int(message_id))
                                if message:
                                    # Clear all reactions from the poll message
                                    await message.clear_reactions()
                                    logger.info(f"✅ UNIFIED CLOSE {poll_id} - Cleared all reactions from Discord message")
                                else:
                                    logger.warning(f"⚠️ UNIFIED CLOSE {poll_id} - Could not find message {message_id}")
                            except discord.NotFound:
                                logger.warning(f"⚠️ UNIFIED CLOSE {poll_id} - Message {message_id} not found (may have been deleted)")
                            except discord.Forbidden:
                                logger.warning(f"⚠️ UNIFIED CLOSE {poll_id} - No permission to clear reactions")
                            except Exception as reaction_error:
                                logger.error(f"❌ UNIFIED CLOSE {poll_id} - Error clearing reactions: {reaction_error}")
                        else:
                            logger.warning(f"⚠️ UNIFIED CLOSE {poll_id} - Could not find or access channel {channel_id}")
                    except Exception as channel_error:
                        logger.error(f"❌ UNIFIED CLOSE {poll_id} - Error accessing channel: {channel_error}")

                # Continue with fresh_poll processing for role ping notifications
                if fresh_poll:
                    # Send role ping notification if enabled and configured for poll closure
                    ping_role_enabled = TypeSafeColumn.get_bool(fresh_poll, "ping_role_enabled", False)
                    ping_role_id = TypeSafeColumn.get_string(fresh_poll, "ping_role_id")
                    ping_role_on_close = TypeSafeColumn.get_bool(fresh_poll, "ping_role_on_close", False)
                    ping_role_name = TypeSafeColumn.get_string(fresh_poll, "ping_role_name", "Unknown Role")
                    
                    if ping_role_enabled and ping_role_id and ping_role_on_close:
                        try:
                            poll_channel_id = TypeSafeColumn.get_string(fresh_poll, "channel_id")
                            if poll_channel_id:
                                channel = bot_instance.get_channel(int(poll_channel_id))
                                if channel and isinstance(channel, discord.TextChannel):
                                    poll_name = TypeSafeColumn.get_string(fresh_poll, "name", "Unknown Poll")
                                    
                                    # Prepare role ping message with comprehensive error handling
                                    message_content = f"📊 **Poll '{poll_name}' has ended!**"
                                    role_ping_attempted = False
                                    
                                    role_id = str(ping_role_id)
                                    message_content = f"<@&{role_id}> {message_content}"
                                    role_ping_attempted = True
                                    logger.info(
                                        f"🔔 UNIFIED CLOSE {poll_id} - Will ping role {ping_role_name} ({role_id}) for poll closure"
                                    )
                                    
                                    # Send role ping message with graceful error handling
                                    try:
                                        await channel.send(content=message_content)
                                        logger.info(f"✅ UNIFIED CLOSE {poll_id} - Sent role ping notification")
                                    except discord.Forbidden as role_error:
                                        if role_ping_attempted:
                                            # Role ping failed due to permissions, try without role ping
                                            logger.warning(
                                                f"⚠️ UNIFIED CLOSE {poll_id} - Role ping failed due to permissions, posting without role ping: {role_error}"
                                            )
                                            try:
                                                fallback_content = f"📊 **Poll '{poll_name}' has ended!**"
                                                await channel.send(content=fallback_content)
                                                logger.info(
                                                    f"✅ UNIFIED CLOSE {poll_id} - Sent fallback notification without role ping"
                                                )
                                            except Exception as fallback_error:
                                                logger.error(
                                                    f"❌ UNIFIED CLOSE {poll_id} - Fallback notification also failed: {fallback_error}"
                                                )
                                        else:
                                            # Not a role ping issue, re-raise the error
                                            raise role_error
                                    except Exception as send_error:
                                        logger.error(f"❌ UNIFIED CLOSE {poll_id} - Error sending role ping notification: {send_error}")
                                else:
                                    logger.warning(f"⚠️ UNIFIED CLOSE {poll_id} - Could not find or access channel {poll_channel_id}")
                            else:
                                logger.warning(f"⚠️ UNIFIED CLOSE {poll_id} - No channel ID found for role ping notification")
                        except Exception as ping_error:
                            logger.error(f"❌ UNIFIED CLOSE {poll_id} - Error in role ping notification process: {ping_error}")
                    elif ping_role_enabled and ping_role_id and not ping_role_on_close:
                        logger.info(f"ℹ️ UNIFIED CLOSE {poll_id} - Role ping enabled but ping_role_on_close is disabled")
                    elif ping_role_enabled and not ping_role_id:
                        logger.warning(f"⚠️ UNIFIED CLOSE {poll_id} - Role ping enabled but no role ID configured")
                else:
                    logger.error(f"❌ UNIFIED CLOSE {poll_id} - Poll not found for message update")
            finally:
                db.close()

            # STEP 5: Generate static content for closed poll
            try:
                from .static_page_generator import generate_static_content_on_poll_close
                
                logger.info(f"🔧 UNIFIED CLOSE {poll_id} - Generating static content for closed poll")
                static_success = await generate_static_content_on_poll_close(poll_id, bot_instance)
                
                if static_success:
                    logger.info(f"✅ UNIFIED CLOSE {poll_id} - Static content generated successfully")
                else:
                    logger.warning(f"⚠️ UNIFIED CLOSE {poll_id} - Static content generation failed, but poll closure continues")
                    
            except Exception as static_error:
                logger.error(f"❌ UNIFIED CLOSE {poll_id} - Error generating static content: {static_error}")
                # Don't fail the entire poll closure process if static generation fails
                logger.info(f"🔄 UNIFIED CLOSE {poll_id} - Continuing with poll closure despite static generation failure")

            # Log admin action if this was an admin closure
            if admin_user_id:
                logger.warning(f"Admin poll closure: poll_id={poll_id} admin_user_id={admin_user_id} reason={reason}")

            logger.info(f"🎉 UNIFIED CLOSE {poll_id} - Unified poll closure process completed successfully")
            
            return {
                "success": True,
                "message": f"Poll closed successfully via {reason}",
                "poll_id": poll_id,
                "reason": reason,
                "admin_user_id": admin_user_id
            }

        except Exception as e:
            # Handle unexpected closure errors with bot owner notification
            error_msg = await PollErrorHandler.handle_poll_closure_error(e, poll_id, bot_instance)
            logger.error(f"❌ UNIFIED CLOSE {poll_id} - Unexpected error in unified closure: {error_msg}")
            return {
                "success": False,
                "error": f"Unexpected error during poll closure: {str(e)}",
                "poll_id": poll_id
            }


# Global service instance
poll_closure_service = PollClosureService()
