"""
Poll Opening Service
Unified poll opening procedures for consistent behavior across all opening methods.
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional
import pytz
import discord
from pathlib import Path

from ...database import get_db_session, Poll, TypeSafeColumn
from ...error_handler import PollErrorHandler

logger = logging.getLogger(__name__)


class PollOpeningService:
    """Unified service for opening polls with consistent procedures"""

    @staticmethod
    async def open_poll_unified(
        poll_id: int, 
        reason: str = "scheduled",
        admin_user_id: Optional[str] = None,
        bot_instance=None
    ) -> Dict[str, Any]:
        """
        Unified poll opening procedure that ensures consistent behavior
        regardless of how the poll is being opened (scheduled, manual, immediate, reopen, recovery, etc.)
        
        Args:
            poll_id: ID of the poll to open
            reason: Reason for opening ("scheduled", "manual", "immediate", "reopen", "recovery", etc.)
            admin_user_id: ID of admin user if this is an admin action
            bot_instance: Discord bot instance (will be fetched if not provided)
            
        Returns:
            Dict with success status and details
        """
        try:
            logger.info(f"🚀 UNIFIED OPEN {poll_id} - Starting unified poll opening (reason: {reason})")
            
            # Get bot instance if not provided
            from .poll_db_utils import get_bot_instance_safe, get_poll_with_votes, extract_poll_fields
            
            bot_instance = get_bot_instance_safe(bot_instance)
            if not bot_instance:
                logger.error(f"❌ UNIFIED OPEN {poll_id} - Bot instance not available")
                return {"success": False, "error": "Bot instance not available"}

            # STEP 1: Get poll data and validate eligibility
            db = get_db_session()
            poll = None
            try:
                poll, db = get_poll_with_votes(poll_id, db)
                if not poll:
                    logger.error(f"❌ UNIFIED OPEN {poll_id} - Poll not found in database")
                    return {"success": False, "error": "Poll not found"}

                # Extract poll fields
                poll_data = extract_poll_fields(poll)
                current_status = poll_data["status"]
                poll_name = poll_data["name"]
                message_id = poll_data["message_id"]
                channel_id = poll_data["channel_id"]
                image_path = poll_data["image_path"]
                image_message_text = poll_data["image_message_text"]
                
                logger.info(f"📊 UNIFIED OPEN {poll_id} - Poll '{poll_name}' found, status: {current_status}")

                # Validate opening eligibility based on current status and reason
                if current_status == "active":
                    if reason not in ["recovery", "manual", "immediate"]:
                        logger.info(f"ℹ️ UNIFIED OPEN {poll_id} - Poll already active, skipping")
                        return {"success": True, "message": "Poll was already active", "already_active": True}
                elif current_status == "closed" and reason not in ["reopen", "manual"]:
                    logger.error(f"❌ UNIFIED OPEN {poll_id} - Cannot open closed poll with reason: {reason}")
                    return {"success": False, "error": f"Cannot open closed poll (reason: {reason})"}
                
            except Exception as e:
                logger.error(f"❌ UNIFIED OPEN {poll_id} - Error fetching poll data: {e}")
                return {"success": False, "error": "Database error while fetching poll data"}
            finally:
                db.close()

            # STEP 2: Comprehensive field validation
            logger.info(f"🔍 UNIFIED OPEN {poll_id} - Running comprehensive field validation")
            try:
                from ...poll_field_validator import PollFieldValidator
                
                validation_result = await PollFieldValidator.validate_poll_fields_before_posting(
                    poll_id, bot_instance
                )
                
                if not validation_result["success"]:
                    error_msg = f"Poll validation failed: {'; '.join(validation_result['errors'][:3])}"
                    logger.error(f"❌ UNIFIED OPEN {poll_id} - {error_msg}")
                    return {
                        "success": False,
                        "error": error_msg,
                        "validation_details": validation_result,
                    }
                else:
                    logger.info(f"✅ UNIFIED OPEN {poll_id} - Field validation passed")
                    
            except Exception as validation_error:
                logger.error(f"❌ UNIFIED OPEN {poll_id} - Validation system error: {validation_error}")
                # Continue with opening but log the validation failure

            # STEP 3: Handle image posting (if poll has image)
            discord_image_message_id = None
            if image_path and Path(image_path).exists():
                logger.info(f"📷 UNIFIED OPEN {poll_id} - Processing image posting")
                try:
                    channel = bot_instance.get_channel(int(channel_id))
                    if channel and isinstance(channel, discord.TextChannel):
                        # Check bot permissions for image posting
                        bot_member = channel.guild.get_member(bot_instance.user.id)
                        if bot_member and channel.permissions_for(bot_member).attach_files:
                            
                            # Post image message before poll
                            image_result = await PollOpeningService._post_image_message(
                                channel, image_path, image_message_text
                            )
                            
                            if image_result["success"]:
                                discord_image_message_id = image_result["message_id"]
                                logger.info(f"✅ UNIFIED OPEN {poll_id} - Image posted successfully")
                            else:
                                logger.warning(f"⚠️ UNIFIED OPEN {poll_id} - Image posting failed: {image_result['error']}")
                        else:
                            logger.warning(f"⚠️ UNIFIED OPEN {poll_id} - Bot lacks attach_files permission for image")
                    else:
                        logger.warning(f"⚠️ UNIFIED OPEN {poll_id} - Channel not found or not text channel")
                        
                except Exception as image_error:
                    logger.error(f"❌ UNIFIED OPEN {poll_id} - Error posting image: {image_error}")
                    # Continue with poll opening even if image fails

            # STEP 4: Prepare role mention content for poll posting
            role_mention_content = None
            db = get_db_session()
            try:
                fresh_poll = db.query(Poll).filter(Poll.id == poll_id).first()
                if fresh_poll:
                    ping_role_enabled = TypeSafeColumn.get_bool(fresh_poll, "ping_role_enabled", False)
                    ping_role_id = TypeSafeColumn.get_string(fresh_poll, "ping_role_id")
                    ping_role_name = TypeSafeColumn.get_string(fresh_poll, "ping_role_name", "Unknown Role")
                    
                    # Check if we should ping role on poll opening
                    if ping_role_enabled and ping_role_id and reason in ["scheduled", "immediate", "manual"]:
                        poll_name = TypeSafeColumn.get_string(fresh_poll, "name", "Unknown Poll")
                        message_content = "📊 **Vote Now!**"
                        
                        role_id = str(ping_role_id)
                        role_mention_content = f"<@&{role_id}>\n{message_content}"
                        
                        logger.info(f"🔔 UNIFIED OPEN {poll_id} - Prepared role ping content for {ping_role_name} ({role_id})")
                        
            except Exception as e:
                logger.error(f"❌ UNIFIED OPEN {poll_id} - Error preparing role ping content: {e}")
            finally:
                db.close()

            # STEP 5: Post poll to Discord using existing robust function with role mention
            logger.info(f"📊 UNIFIED OPEN {poll_id} - Posting poll to Discord")
            try:
                from ...discord_utils import post_poll_to_channel
                
                post_result = await post_poll_to_channel(bot_instance, poll_id, role_mention_content)
                
                if not post_result["success"]:
                    error_msg = await PollErrorHandler.handle_poll_creation_error(
                        Exception(post_result["error"]), {"poll_id": poll_id}, bot_instance
                    )
                    logger.error(f"❌ UNIFIED OPEN {poll_id} - Discord posting failed: {error_msg}")
                    return {"success": False, "error": post_result["error"]}
                else:
                    discord_poll_message_id = post_result.get("message_id")
                    
                    # CRITICAL: Validate that we received a message ID from Discord
                    if not discord_poll_message_id:
                        error_msg = "Discord posting succeeded but no message ID was returned"
                        logger.error(f"❌ UNIFIED OPEN {poll_id} - {error_msg}")
                        await PollErrorHandler.handle_poll_creation_error(
                            Exception(error_msg), {"poll_id": poll_id}, bot_instance
                        )
                        return {"success": False, "error": error_msg}
                    
                    logger.info(f"✅ UNIFIED OPEN {poll_id} - Poll posted to Discord successfully with message ID: {discord_poll_message_id}")

            except Exception as e:
                error_msg = await PollErrorHandler.handle_poll_creation_error(e, {"poll_id": poll_id}, bot_instance)
                logger.error(f"❌ UNIFIED OPEN {poll_id} - Discord posting exception: {error_msg}")
                return {"success": False, "error": f"Discord posting failed: {str(e)}"}

            # STEP 6: Update database with Discord message IDs and ensure active status
            db = get_db_session()
            try:
                poll = db.query(Poll).filter(Poll.id == poll_id).first()
                if poll:
                    # CRITICAL: Ensure we have a message ID before updating database
                    if not discord_poll_message_id:
                        error_msg = "Cannot update database: missing Discord message ID"
                        logger.error(f"❌ UNIFIED OPEN {poll_id} - {error_msg}")
                        return {"success": False, "error": error_msg}
                    
                    # Update message ID (we know it exists due to validation above)
                    setattr(poll, "message_id", str(discord_poll_message_id))
                    
                    # Ensure poll is marked as active
                    setattr(poll, "status", "active")
                    
                    db.commit()
                    logger.info(f"✅ UNIFIED OPEN {poll_id} - Database updated with active status and message ID: {discord_poll_message_id}")
                    
            except Exception as e:
                db.rollback()
                logger.error(f"❌ UNIFIED OPEN {poll_id} - Database update failed: {e}")
                return {"success": False, "error": "Database update failed"}
            finally:
                db.close()

            # STEP 7: Schedule poll closure if not already scheduled
            try:
                from ...background_tasks import get_scheduler
                from ...timezone_scheduler_fix import TimezoneAwareScheduler
                
                scheduler = get_scheduler()
                if scheduler and scheduler.running:
                    # Check if close job already exists
                    close_job_id = f"close_poll_{poll_id}"
                    existing_job = scheduler.get_job(close_job_id)
                    
                    if not existing_job:
                        # Get poll close time and schedule closure
                        db = get_db_session()
                        try:
                            poll = db.query(Poll).filter(Poll.id == poll_id).first()
                            if poll:
                                poll_close_time = poll.close_time_aware
                                poll_timezone = TypeSafeColumn.get_string(poll, "timezone", "UTC")
                                
                                if poll_close_time and poll_close_time > datetime.now(pytz.UTC):
                                    from ...background_tasks import close_poll
                                    
                                    tz_scheduler = TimezoneAwareScheduler(scheduler)
                                    success = tz_scheduler.schedule_poll_closing(
                                        poll_id, poll_close_time, poll_timezone, close_poll
                                    )
                                    
                                    if success:
                                        logger.info(f"✅ UNIFIED OPEN {poll_id} - Scheduled poll closure")
                                    else:
                                        logger.warning(f"⚠️ UNIFIED OPEN {poll_id} - Failed to schedule poll closure")
                                        
                        finally:
                            db.close()
                    else:
                        logger.info(f"ℹ️ UNIFIED OPEN {poll_id} - Poll closure already scheduled")
                        
            except Exception as schedule_error:
                logger.error(f"❌ UNIFIED OPEN {poll_id} - Error scheduling poll closure: {schedule_error}")
                # Don't fail the opening process if scheduling fails

            # STEP 8: Cache management - invalidate stale caches and warm new ones
            from ..cache.cache_invalidation_utils import invalidate_poll_cache_safely
            await invalidate_poll_cache_safely(poll_id, "UNIFIED OPEN")
            
            # Warm caches for the newly active poll (optional - will be populated on first access)
            logger.info(f"ℹ️ UNIFIED OPEN {poll_id} - Caches will be warmed on first access")

            # STEP 9: Static content generation is handled only at poll closure
            # No static content generation needed during poll opening
            logger.info(f"ℹ️ UNIFIED OPEN {poll_id} - Static content will be generated when poll closes")

            # Log admin action if this was an admin opening
            if admin_user_id:
                logger.info(f"Admin poll opening: poll_id={poll_id} admin_user_id={admin_user_id} reason={reason}")

            logger.info(f"🎉 UNIFIED OPEN {poll_id} - Unified poll opening process completed successfully")
            
            return {
                "success": True,
                "message": f"Poll opened successfully via {reason}",
                "poll_id": poll_id,
                "reason": reason,
                "admin_user_id": admin_user_id,
                "discord_poll_message_id": discord_poll_message_id,
                "discord_image_message_id": discord_image_message_id
            }

        except Exception as e:
            # Handle unexpected opening errors with bot owner notification
            error_msg = await PollErrorHandler.handle_poll_creation_error(e, {"poll_id": poll_id}, bot_instance)
            logger.error(f"❌ UNIFIED OPEN {poll_id} - Unexpected error in unified opening: {error_msg}")
            return {
                "success": False,
                "error": f"Unexpected error during poll opening: {str(e)}",
                "poll_id": poll_id
            }

    @staticmethod
    async def _post_image_message(
        channel: discord.TextChannel, 
        image_path: str, 
        message_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """Post image as separate message before poll (similar to bulletproof_operations pattern)"""
        try:
            file_path = Path(image_path)
            if not file_path.exists():
                return {"success": False, "error": "Image file not found"}

            # Create Discord file object
            discord_file = discord.File(file_path, filename=file_path.name)

            # Prepare message content
            content = message_text if message_text else ""

            # Post message with image
            message = await channel.send(content=content, file=discord_file)

            return {
                "success": True,
                "message_id": message.id,
                "message": "Image posted successfully",
            }

        except discord.Forbidden:
            return {"success": False, "error": "No permission to post images"}
        except discord.HTTPException as e:
            return {"success": False, "error": f"Discord HTTP error: {str(e)}"}
        except Exception as e:
            logger.error(f"Failed to post image: {e}")
            return {"success": False, "error": f"Failed to post image: {str(e)}"}


# Global service instance
poll_opening_service = PollOpeningService()