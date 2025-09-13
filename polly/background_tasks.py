"""
Polly Background Tasks
Background task management and scheduling functionality.
"""

import asyncio
import logging
from datetime import datetime
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import discord

try:
    from .database import get_db_session, Poll, Vote, TypeSafeColumn
    from .discord_utils import update_poll_message
    from .timezone_scheduler_fix import TimezoneAwareScheduler
    from .error_handler import PollErrorHandler
except ImportError:
    from database import get_db_session, Poll, Vote, TypeSafeColumn  # type: ignore
    from discord_utils import update_poll_message  # type: ignore
    from timezone_scheduler_fix import TimezoneAwareScheduler  # type: ignore
    from error_handler import PollErrorHandler  # type: ignore
# Track failed message fetch attempts for polls during runtime
# Format: {poll_id: {"count": int, "first_failure": datetime, "last_attempt": datetime}}
message_fetch_failures = {}
MAX_FETCH_RETRIES = 5  # Number of consecutive failures before deleting poll
RETRY_WINDOW_MINUTES = 30  # Time window to track failures

# Threshold-based logging counters to reduce log noise
startup_warning_counts = {
    "message_not_found": 0,
    "permission_denied": 0,
    "channel_not_found": 0,
    "rate_limited": 0,
    "message_fix_failed": 0
}

# Thresholds for escalating to WARNING level
WARNING_THRESHOLDS = {
    "message_not_found": 3,  # Warn after 3 missing messages
    "permission_denied": 3,  # Warn after 3 permission issues
    "channel_not_found": 3,  # Warn after 3 missing channels
    "rate_limited": 5,       # Warn after 5 rate limits
    "message_fix_failed": 5  # Warn after 5 failed message fixes
}

logger = logging.getLogger(__name__)

# Scheduler for poll timing
scheduler = AsyncIOScheduler()


async def close_poll(poll_id: int):
    """Close a poll using unified closure service for consistent behavior"""
    try:
        logger.info(f"🏁 SCHEDULED CLOSE {poll_id} - Starting scheduled poll closure")
        
        # Use the unified closure service for consistent behavior
        from .poll_closure_service import poll_closure_service
        
        result = await poll_closure_service.close_poll_unified(
            poll_id=poll_id,
            reason="scheduled"
        )
        
        if result["success"]:
            if result.get("already_closed"):
                logger.info(f"ℹ️ SCHEDULED CLOSE {poll_id} - Poll was already closed")
            else:
                logger.info(f"🎉 SCHEDULED CLOSE {poll_id} - Poll closed successfully via scheduled task")
        else:
            logger.error(f"❌ SCHEDULED CLOSE {poll_id} - Scheduled closure failed: {result.get('error')}")
            
    except Exception as e:
        logger.error(f"❌ SCHEDULED CLOSE {poll_id} - Unexpected error in scheduled close_poll function: {e}")
        
        # Handle unexpected closure errors with bot owner notification
        from .discord_bot import get_bot_instance
        bot = get_bot_instance()
        error_msg = await PollErrorHandler.handle_poll_closure_error(e, poll_id, bot)
        logger.error(f"❌ SCHEDULED CLOSE {poll_id} - Error handled: {error_msg}")


async def cleanup_polls_with_deleted_messages():
    """
    Check for polls whose Discord messages have been deleted and remove them from the database.

    This function checks all active and scheduled polls to see if their Discord messages still exist.
    If a message has been deleted, the poll is removed from the database to maintain consistency.
    """
    logger.info("🧹 MESSAGE CLEANUP - Starting cleanup of polls with deleted messages")

    from .discord_bot import get_bot_instance

    bot = get_bot_instance()

    if not bot or not bot.is_ready():
        logger.warning("⚠️ MESSAGE CLEANUP - Bot not ready, skipping message cleanup")
        return

    db = get_db_session()
    try:
        # STRICT LIMIT: Get only a limited number of polls to prevent overwhelming Discord API
        polls_with_messages = (
            db.query(Poll)
            .filter(
                Poll.message_id.isnot(None), Poll.status.in_(["active", "scheduled"])
            )
            .order_by(Poll.created_at.desc())  # Check newest first
            .limit(15)  # STRICT LIMIT: Only check 15 polls max on startup
            .all()
        )

        logger.info(
            f"📊 MESSAGE CLEANUP - Found {len(polls_with_messages)} polls with message IDs to check (limited to 15 for startup)"
        )

        deleted_polls = []
        api_call_delay = 1.0  # 1 second delay between Discord API calls

        for poll in polls_with_messages:
            try:
                poll_id = TypeSafeColumn.get_int(poll, "id")
                poll_name = TypeSafeColumn.get_string(poll, "name", "Unknown")
                message_id = TypeSafeColumn.get_string(poll, "message_id")
                channel_id = TypeSafeColumn.get_string(poll, "channel_id")

                logger.debug(
                    f"🔍 MESSAGE CLEANUP - Checking poll {poll_id}: '{poll_name}' (message: {message_id})"
                )

                # Get the channel
                try:
                    channel = bot.get_channel(int(channel_id))
                    if not channel:
                        logger.warning(
                            f"⚠️ MESSAGE CLEANUP - Channel {channel_id} not found for poll {poll_id}, marking for deletion"
                        )
                        deleted_polls.append(poll)
                        continue
                except (ValueError, TypeError) as e:
                    logger.error(
                        f"❌ MESSAGE CLEANUP - Invalid channel ID {channel_id} for poll {poll_id}: {e}"
                    )
                    deleted_polls.append(poll)
                    continue

                # Try to fetch the message (only for text channels) with RATE LIMITING
                try:
                    if isinstance(channel, discord.TextChannel):
                        # RATE LIMIT: Add delay before Discord API call
                        await asyncio.sleep(api_call_delay)
                        
                        await channel.fetch_message(int(message_id))
                        logger.debug(
                            f"✅ MESSAGE CLEANUP - Message {message_id} exists for poll {poll_id}"
                        )
                    else:
                        logger.warning(
                            f"⚠️ MESSAGE CLEANUP - Channel {channel_id} is not a text channel for poll {poll_id}, marking for deletion"
                        )
                        deleted_polls.append(poll)
                        continue
                except discord.NotFound:
                    startup_warning_counts["message_not_found"] += 1
                    if startup_warning_counts["message_not_found"] <= WARNING_THRESHOLDS["message_not_found"]:
                        logger.info(
                            f"🗑️ MESSAGE CLEANUP - Message {message_id} not found for poll {poll_id}, marking for deletion ({startup_warning_counts['message_not_found']}/{WARNING_THRESHOLDS['message_not_found']})"
                        )
                    else:
                        logger.warning(
                            f"🗑️ MESSAGE CLEANUP - Message {message_id} not found for poll {poll_id}, marking for deletion (threshold exceeded: {startup_warning_counts['message_not_found']} occurrences)"
                        )
                    deleted_polls.append(poll)
                except discord.Forbidden:
                    startup_warning_counts["permission_denied"] += 1
                    if startup_warning_counts["permission_denied"] <= WARNING_THRESHOLDS["permission_denied"]:
                        logger.info(
                            f"🔒 MESSAGE CLEANUP - No permission to access message {message_id} for poll {poll_id}, keeping poll ({startup_warning_counts['permission_denied']}/{WARNING_THRESHOLDS['permission_denied']})"
                        )
                    else:
                        logger.warning(
                            f"🔒 MESSAGE CLEANUP - No permission to access message {message_id} for poll {poll_id}, keeping poll (threshold exceeded: {startup_warning_counts['permission_denied']} occurrences)"
                        )
                except discord.HTTPException as e:
                    if e.status == 429:  # Rate limited
                        startup_warning_counts["rate_limited"] += 1
                        # Always warn on rate limits (threshold = 1)
                        logger.warning(
                            f"⚠️ MESSAGE CLEANUP - Rate limited checking message {message_id} for poll {poll_id}, implementing backoff (occurrence #{startup_warning_counts['rate_limited']})"
                        )
                        # EXPONENTIAL BACKOFF: Wait longer on rate limit
                        await asyncio.sleep(15.0)
                    else:
                        logger.error(
                            f"❌ MESSAGE CLEANUP - HTTP error checking message {message_id} for poll {poll_id}: {e}"
                        )
                    # Don't delete on HTTP errors, might be temporary
                except (ValueError, TypeError) as e:
                    logger.error(
                        f"❌ MESSAGE CLEANUP - Invalid message ID {message_id} for poll {poll_id}: {e}"
                    )
                    deleted_polls.append(poll)
                except Exception as e:
                    logger.error(
                        f"❌ MESSAGE CLEANUP - Unexpected error checking message {message_id} for poll {poll_id}: {e}"
                    )
                    # Don't delete on unexpected errors

            except Exception as e:
                poll_id = TypeSafeColumn.get_int(poll, "id", 0) if poll else 0
                logger.error(
                    f"❌ MESSAGE CLEANUP - Error processing poll {poll_id}: {e}"
                )
                continue

        # Delete polls whose messages were not found
        if deleted_polls:
            logger.info(
                f"🗑️ MESSAGE CLEANUP - Deleting {len(deleted_polls)} polls with missing messages"
            )

            for poll in deleted_polls:
                try:
                    poll_id = TypeSafeColumn.get_int(poll, "id")
                    poll_name = TypeSafeColumn.get_string(poll, "name", "Unknown")

                    # Delete associated votes first (cascade should handle this, but be explicit)
                    db.query(Vote).filter(Vote.poll_id == poll_id).delete()

                    # Delete the poll
                    db.delete(poll)

                    logger.info(
                        f"✅ MESSAGE CLEANUP - Deleted poll {poll_id}: '{poll_name}'"
                    )

                except Exception as e:
                    poll_id = TypeSafeColumn.get_int(poll, "id", 0) if poll else 0
                    logger.error(
                        f"❌ MESSAGE CLEANUP - Error deleting poll {poll_id}: {e}"
                    )
                    continue

            # Commit all deletions
            db.commit()
            logger.info(
                f"✅ MESSAGE CLEANUP - Successfully deleted {len(deleted_polls)} polls with missing messages"
            )
        else:
            logger.info("✅ MESSAGE CLEANUP - No polls with missing messages found")

    except Exception as e:
        logger.error(f"❌ MESSAGE CLEANUP - Critical error during message cleanup: {e}")
        logger.exception("Full traceback for message cleanup error:")
        db.rollback()
    finally:
        db.close()
        logger.debug("🔄 MESSAGE CLEANUP - Database connection closed")


async def restore_scheduled_jobs():
    """
    Restore scheduled jobs from database on startup with comprehensive debugging.

    This function queries the database for all polls with status 'scheduled' and restores their scheduled jobs in the APScheduler.
    - If a poll's open time is overdue (in the past), it is posted immediately to Discord and activated.
    - Future polls are scheduled to open at their designated time.
    - All polls (active or scheduled) have their closing jobs scheduled if their close time is in the future.
    - If a poll's close time is overdue, it is closed immediately.
    Side effects:
    - Overdue polls are posted and/or closed immediately, which may result in multiple polls being posted or closed at startup.
    - Scheduler jobs are created for both opening and closing polls, ensuring no scheduled poll is missed after a restart.
    - Errors during restoration are logged but do not halt the restoration process for other polls.
    """
    logger.info("🔄 SCHEDULER RESTORE - Starting restore_scheduled_jobs")

    # Schedule Discord-dependent tasks to run after bot is ready
    asyncio.create_task(run_discord_dependent_startup_tasks())


async def run_discord_dependent_startup_tasks():
    """Run Discord-dependent startup tasks after bot is ready"""
    try:
        from .discord_bot import get_bot_instance
        
        logger.info("⏳ DISCORD STARTUP - Waiting for bot to be ready before running Discord-dependent tasks")
        
        # Wait for bot to be ready with timeout
        max_wait_time = 60  # 60 seconds timeout
        wait_interval = 2   # Check every 2 seconds
        total_waited = 0
        
        while total_waited < max_wait_time:
            bot = get_bot_instance()
            if bot and bot.is_ready():
                logger.info(f"✅ DISCORD STARTUP - Bot is ready after {total_waited} seconds, starting Discord-dependent tasks")
                break
            
            await asyncio.sleep(wait_interval)
            total_waited += wait_interval
            
            if total_waited % 10 == 0:  # Log every 10 seconds
                logger.info(f"⏳ DISCORD STARTUP - Still waiting for bot to be ready ({total_waited}/{max_wait_time}s)")
        
        # Check if we timed out
        bot = get_bot_instance()
        if not bot or not bot.is_ready():
            logger.error(f"❌ DISCORD STARTUP - Bot not ready after {max_wait_time} seconds, skipping Discord-dependent tasks")
            return
        
        # Now run the Discord-dependent tasks
        logger.info("🚀 DISCORD STARTUP - Running Discord-dependent startup tasks")
        
        # First, clean up polls whose messages have been deleted
        await cleanup_polls_with_deleted_messages()
        
        # Fix Discord messages for existing closed polls that may not have been updated properly
        await fix_closed_polls_discord_messages_on_startup()
        
        # Run static content recovery for existing closed polls
        await run_static_content_recovery_on_startup()
        
        logger.info("🎉 DISCORD STARTUP - All Discord-dependent startup tasks completed")
        
    except Exception as e:
        logger.error(f"❌ DISCORD STARTUP - Error in Discord-dependent startup tasks: {e}")
        logger.exception("Full traceback for Discord startup error:")


async def fix_closed_polls_discord_messages_on_startup():
    """Fix Discord messages for existing closed polls that may not have been updated properly"""
    try:
        from .discord_bot import get_bot_instance
        from sqlalchemy.orm import joinedload
        from .enhanced_cache_service import get_enhanced_cache_service
        import discord
        
        logger.info("🔧 STARTUP FIX - Starting Discord message fix for existing closed polls")
        
        bot = get_bot_instance()
        if not bot:
            logger.warning("⚠️ STARTUP FIX - Bot instance not available, skipping Discord message fix")
            return
        
        if not bot.is_ready():
            logger.warning("⚠️ STARTUP FIX - Bot is not ready yet, skipping Discord message fix")
            return
        
        # Get enhanced cache service for rate limiting prevention
        enhanced_cache = get_enhanced_cache_service()
        
        # Get all closed polls that have message IDs - LIMIT TO PREVENT OVERWHELMING
        db = get_db_session()
        try:
            closed_polls = (
                db.query(Poll)
                .options(joinedload(Poll.votes))
                .filter(Poll.status == 'closed')
                .filter(Poll.message_id.isnot(None))
                .order_by(Poll.created_at.desc())  # Process newest first
                .limit(20)  # STRICT LIMIT: Only process 20 polls max on startup
                .all()
            )
            
            logger.info(f"📊 STARTUP FIX - Found {len(closed_polls)} closed polls with message IDs to check (limited to 20 for startup)")
            
            if not closed_polls:
                logger.info("✅ STARTUP FIX - No closed polls found that need Discord message fixing")
                return
            
            success_count = 0
            reaction_clear_count = 0
            
            # STRICTER RATE LIMITS: Process polls in smaller batches with longer delays
            batch_size = 3  # Process only 3 polls at a time (reduced from 5)
            batch_delay = 5.0  # 5 second delay between batches (increased from 2.0)
            poll_delay = 1.5  # 1.5 second delay between individual polls (increased from 0.5)
            api_call_delay = 0.8  # Additional delay between API calls within a poll
            
            for i in range(0, len(closed_polls), batch_size):
                batch = closed_polls[i:i + batch_size]
                logger.info(f"🔄 STARTUP FIX - Processing batch {i//batch_size + 1}/{(len(closed_polls) + batch_size - 1)//batch_size} ({len(batch)} polls)")
                
                for poll in batch:
                    poll_id = TypeSafeColumn.get_int(poll, "id")
                    poll_name = TypeSafeColumn.get_string(poll, "name", "Unknown")
                    message_id = TypeSafeColumn.get_string(poll, "message_id")
                    channel_id = TypeSafeColumn.get_string(poll, "channel_id")
                    
                    logger.debug(f"🔄 STARTUP FIX - Checking poll {poll_id}: '{poll_name}' (Message: {message_id})")
                    
                    try:
                        # RATE LIMIT: Add delay before Discord API call
                        await asyncio.sleep(api_call_delay)
                        
                        # Update the Discord message to show final results
                        message_updated = await update_poll_message(bot, poll)
                        
                        if message_updated:
                            logger.info(f"✅ STARTUP FIX - Successfully updated Discord message for poll {poll_id}")
                            success_count += 1
                        else:
                            startup_warning_counts["message_fix_failed"] += 1
                            if startup_warning_counts["message_fix_failed"] <= WARNING_THRESHOLDS["message_fix_failed"]:
                                logger.debug(f"⚠️ STARTUP FIX - Failed to update Discord message for poll {poll_id} (may already be correct) ({startup_warning_counts['message_fix_failed']}/{WARNING_THRESHOLDS['message_fix_failed']})")
                            else:
                                logger.warning(f"⚠️ STARTUP FIX - Failed to update Discord message for poll {poll_id} (threshold exceeded: {startup_warning_counts['message_fix_failed']} failures)")
                        
                        # INCREASED delay to prevent rate limiting on message updates
                        await asyncio.sleep(api_call_delay)
                        
                        # Clear reactions from Discord message for closed polls with STRICT rate limiting
                        if message_id and channel_id:
                            try:
                                # RATE LIMIT: Add delay before channel access
                                await asyncio.sleep(api_call_delay)
                                
                                channel = bot.get_channel(int(channel_id))
                                if channel and isinstance(channel, discord.TextChannel):
                                    try:
                                        # RATE LIMIT: Add delay before message fetch
                                        await asyncio.sleep(api_call_delay)
                                        
                                        message = await channel.fetch_message(int(message_id))
                                        if message:
                                            # RATE LIMIT: Add delay before clearing reactions
                                            await asyncio.sleep(api_call_delay)
                                            
                                            # Clear all reactions from the poll message
                                            await message.clear_reactions()
                                            logger.info(f"✅ STARTUP FIX - Cleared all reactions from Discord message for poll {poll_id}")
                                            reaction_clear_count += 1
                                        else:
                                            logger.warning(f"⚠️ STARTUP FIX - Could not find message {message_id} for poll {poll_id}")
                                    except discord.NotFound:
                                        startup_warning_counts["message_not_found"] += 1
                                        if startup_warning_counts["message_not_found"] <= WARNING_THRESHOLDS["message_not_found"]:
                                            logger.info(f"⚠️ STARTUP FIX - Message {message_id} not found for poll {poll_id} (may have been deleted) ({startup_warning_counts['message_not_found']}/{WARNING_THRESHOLDS['message_not_found']})")
                                        else:
                                            logger.warning(f"⚠️ STARTUP FIX - Message {message_id} not found for poll {poll_id} (threshold exceeded: {startup_warning_counts['message_not_found']} occurrences)")
                                    except discord.Forbidden:
                                        startup_warning_counts["permission_denied"] += 1
                                        if startup_warning_counts["permission_denied"] <= WARNING_THRESHOLDS["permission_denied"]:
                                            logger.info(f"⚠️ STARTUP FIX - No permission to clear reactions for poll {poll_id} ({startup_warning_counts['permission_denied']}/{WARNING_THRESHOLDS['permission_denied']})")
                                        else:
                                            logger.warning(f"⚠️ STARTUP FIX - No permission to clear reactions for poll {poll_id} (threshold exceeded: {startup_warning_counts['permission_denied']} occurrences)")
                                    except discord.HTTPException as http_error:
                                        if http_error.status == 429:  # Rate limited
                                            logger.warning(f"⚠️ STARTUP FIX - Rate limited while clearing reactions for poll {poll_id}, implementing exponential backoff")
                                            # EXPONENTIAL BACKOFF: Start with 10 seconds, double on subsequent rate limits
                                            backoff_delay = 10.0
                                            await asyncio.sleep(backoff_delay)
                                        else:
                                            logger.error(f"❌ STARTUP FIX - HTTP error clearing reactions for poll {poll_id}: {http_error}")
                                    except Exception as reaction_error:
                                        logger.error(f"❌ STARTUP FIX - Error clearing reactions for poll {poll_id}: {reaction_error}")
                                else:
                                    startup_warning_counts["channel_not_found"] += 1
                                    if startup_warning_counts["channel_not_found"] <= WARNING_THRESHOLDS["channel_not_found"]:
                                        logger.info(f"⚠️ STARTUP FIX - Could not find or access channel {channel_id} for poll {poll_id} ({startup_warning_counts['channel_not_found']}/{WARNING_THRESHOLDS['channel_not_found']})")
                                    else:
                                        logger.warning(f"⚠️ STARTUP FIX - Could not find or access channel {channel_id} for poll {poll_id} (threshold exceeded: {startup_warning_counts['channel_not_found']} occurrences)")
                            except Exception as channel_error:
                                logger.error(f"❌ STARTUP FIX - Error accessing channel for poll {poll_id}: {channel_error}")
                            
                    except Exception as e:
                        # Keep individual poll processing errors as debug unless they become frequent
                        logger.debug(f"⚠️ STARTUP FIX - Error processing poll {poll_id}: {e}")
                        continue
                    
                    # Rate limiting delay between individual polls
                    await asyncio.sleep(poll_delay)
                
                # LONGER delay between batches to respect Discord rate limits
                if i + batch_size < len(closed_polls):  # Don't delay after the last batch
                    logger.info(f"⏳ STARTUP FIX - Waiting {batch_delay}s before next batch to respect rate limits")
                    await asyncio.sleep(batch_delay)
            
            if success_count > 0 or reaction_clear_count > 0:
                logger.info(f"🎉 STARTUP FIX - Successfully updated {success_count}/{len(closed_polls)} closed poll Discord messages and cleared reactions from {reaction_clear_count} polls")
            else:
                logger.info("✅ STARTUP FIX - All closed poll Discord messages and reactions appear to be already correct")
            
        except Exception as e:
            logger.error(f"❌ STARTUP FIX - Database error during Discord message fix: {e}")
        finally:
            db.close()
        
    except Exception as e:
        logger.error(f"❌ STARTUP FIX - Error during Discord message fix: {e}")
        # Don't fail startup if fix fails
        logger.info("🔄 STARTUP FIX - Continuing startup despite Discord message fix failure")


async def run_static_content_recovery_on_startup():
    """Run static content recovery for existing closed polls on startup"""
    try:
        from .static_recovery import run_static_content_recovery
        from .discord_bot import get_bot_instance
        
        logger.info("🔄 STARTUP RECOVERY - Starting static content recovery for existing closed polls")
        
        bot = get_bot_instance()
        if not bot:
            logger.warning("⚠️ STARTUP RECOVERY - Bot instance not available, skipping static recovery")
            return
        
        # STRICT LIMIT: Run recovery with a much smaller limit to avoid overwhelming the system on startup
        results = await run_static_content_recovery(bot, limit=10)  # Reduced from 50 to 10
        
        if results["successful_generations"] > 0:
            logger.info(f"✅ STARTUP RECOVERY - Generated static content for {results['successful_generations']} existing closed polls")
        
        if results["failed_generations"] > 0:
            # Only warn if failure rate is high (>50% of attempted generations)
            if results["failed_generations"] > (results.get("successful_generations", 0)):
                logger.warning(f"⚠️ STARTUP RECOVERY - Failed to generate static content for {results['failed_generations']} polls (high failure rate)")
            else:
                logger.info(f"ℹ️ STARTUP RECOVERY - Failed to generate static content for {results['failed_generations']} polls (acceptable failure rate)")
        
        if results["polls_needing_static"] == 0:
            logger.info("✅ STARTUP RECOVERY - All existing closed polls already have static content")
        
        logger.info(f"📊 STARTUP RECOVERY - Recovery complete: {results['successful_generations']}/{results['polls_needing_static']} polls processed")
        
    except Exception as e:
        logger.error(f"❌ STARTUP RECOVERY - Error during static content recovery: {e}")
        # Don't fail startup if recovery fails
        logger.info("🔄 STARTUP RECOVERY - Continuing startup despite recovery failure")

    # Debug scheduler status
    if not scheduler:
        logger.error("❌ SCHEDULER RESTORE - Scheduler instance is None")
        return

    if not scheduler.running:
        logger.error("❌ SCHEDULER RESTORE - Scheduler is not running")
        return

    logger.debug(
        f"✅ SCHEDULER RESTORE - Scheduler is running, state: {scheduler.state}"
    )

    # Debug bot status
    from .discord_bot import get_bot_instance

    bot = get_bot_instance()
    if not bot:
        logger.error("❌ SCHEDULER RESTORE - Bot instance is None")
        return

    if not bot.is_ready():
        logger.warning("⚠️ SCHEDULER RESTORE - Bot is not ready yet, jobs may fail")
    else:
        logger.debug(f"✅ SCHEDULER RESTORE - Bot is ready: {bot.user}")

    db = get_db_session()
    try:
        # Get all scheduled polls with debugging
        logger.debug("🔍 SCHEDULER RESTORE - Querying database for scheduled polls")
        scheduled_polls = db.query(Poll).filter(Poll.status == "scheduled").all()
        logger.info(
            f"📊 SCHEDULER RESTORE - Found {len(scheduled_polls)} scheduled polls to restore"
        )

        # CRITICAL FIX: Also get active polls that may need to be closed
        logger.debug("🔍 SCHEDULER RESTORE - Querying database for active polls that may need closing")
        active_polls = db.query(Poll).filter(Poll.status == "active").all()
        logger.info(
            f"📊 SCHEDULER RESTORE - Found {len(active_polls)} active polls to check for closure"
        )

        if not scheduled_polls and not active_polls:
            logger.info(
                "✅ SCHEDULER RESTORE - No scheduled or active polls found, restoration complete"
            )
            return

        # Get current time for comparison
        now = datetime.now(pytz.UTC)
        logger.debug(f"⏰ SCHEDULER RESTORE - Current time: {now}")

        # Process each scheduled poll
        restored_count = 0
        immediate_closes = 0

        for poll in scheduled_polls:
            try:
                poll_id = TypeSafeColumn.get_int(poll, "id")
                poll_name = TypeSafeColumn.get_string(poll, "name", "Unknown")

                logger.info(
                    f"🔄 SCHEDULER RESTORE - Processing poll {poll_id}: '{poll_name}'"
                )
                logger.debug(
                    f"Poll {poll_id} details: open_time={poll.open_time_aware}, close_time={poll.close_time_aware}, status={poll.status}"
                )

                # Get poll times as actual datetime objects using TypeSafeColumn
                poll_open_time = poll.open_time
                poll_close_time = poll.close_time

                # Ensure we have valid datetime objects
                if not isinstance(poll_open_time, datetime) or not isinstance(
                    poll_close_time, datetime
                ):
                    logger.error(
                        f"❌ SCHEDULER RESTORE - Invalid datetime objects for poll {poll_id}"
                    )
                    continue

                # Ensure poll times are timezone-aware for comparison
                if poll_open_time.tzinfo is None:
                    poll_open_time = pytz.UTC.localize(poll_open_time)
                    logger.debug(
                        f"🕐 SCHEDULER RESTORE - Localized naive open_time to UTC for poll {poll_id}"
                    )

                if poll_close_time.tzinfo is None:
                    poll_close_time = pytz.UTC.localize(poll_close_time)
                    logger.debug(
                        f"🕐 SCHEDULER RESTORE - Localized naive close_time to UTC for poll {poll_id}"
                    )

                # All polls should be scheduled only - no immediate posting during restore
                # Schedule poll to open at its designated time
                time_until_open = (poll_open_time - now).total_seconds()

                if poll_open_time <= now:
                    logger.info(
                        f"📅 SCHEDULER RESTORE - Poll {poll_id} is overdue by {abs(time_until_open):.0f} seconds, scheduling for immediate posting"
                    )
                else:
                    logger.info(
                        f"📅 SCHEDULER RESTORE - Scheduling poll {poll_id} to open in {time_until_open:.0f} seconds at {poll_open_time}"
                    )

                # Use timezone-aware scheduler for restoration
                tz_scheduler = TimezoneAwareScheduler(scheduler)
                poll_timezone = TypeSafeColumn.get_string(poll, "timezone", "UTC")

                # Schedule poll opening using unified opening service
                from .poll_open_service import poll_opening_service
                
                async def open_poll_scheduled(bot_instance, poll_id):
                    """Wrapper function for scheduled poll opening"""
                    result = await poll_opening_service.open_poll_unified(
                        poll_id=poll_id,
                        reason="scheduled",
                        bot_instance=bot_instance
                    )
                    if not result["success"]:
                        logger.error(f"❌ SCHEDULED OPEN {poll_id} - Failed: {result.get('error')}")
                    else:
                        logger.info(f"✅ SCHEDULED OPEN {poll_id} - Success: {result.get('message')}")
                    return result
                
                success_open = tz_scheduler.schedule_poll_opening(
                    poll_id, poll_open_time, poll_timezone, open_poll_scheduled, bot
                )
                if success_open:
                    logger.debug(
                        f"✅ SCHEDULER RESTORE - Scheduled opening job for poll {poll_id}"
                    )
                else:
                    logger.error(
                        f"❌ SCHEDULER RESTORE - Failed to schedule opening for poll {poll_id}"
                    )

                # Always schedule poll to close (whether it's active or scheduled)
                if poll_close_time > now:
                    time_until_close = (poll_close_time - now).total_seconds()
                    logger.debug(
                        f"📅 SCHEDULER RESTORE - Scheduling poll {poll_id} to close in {time_until_close:.0f} seconds at {poll_close_time}"
                    )

                    success_close = tz_scheduler.schedule_poll_closing(
                        poll_id, poll_close_time, poll_timezone, close_poll
                    )
                    if success_close:
                        logger.debug(
                            f"✅ SCHEDULER RESTORE - Scheduled closing job for poll {poll_id}"
                        )
                    else:
                        logger.error(
                            f"❌ SCHEDULER RESTORE - Failed to schedule closing for poll {poll_id}"
                        )
                else:
                    # Poll should have already closed
                    time_overdue = (now - poll_close_time).total_seconds()
                    logger.warning(
                        f"⏰ SCHEDULER RESTORE - Poll {poll_id} close time is {time_overdue:.0f} seconds overdue, closing now"
                    )

                    try:
                        await close_poll(poll_id)
                        immediate_closes += 1
                        logger.info(
                            f"✅ SCHEDULER RESTORE - Successfully closed overdue poll {poll_id}"
                        )
                    except Exception as close_exc:
                        logger.error(
                            f"❌ SCHEDULER RESTORE - Exception closing poll {poll_id}: {close_exc}"
                        )
                        logger.exception(f"Full traceback for poll {poll_id} closing:")

                restored_count += 1
                logger.debug(
                    f"✅ SCHEDULER RESTORE - Completed processing poll {poll_id}"
                )

            except Exception as e:
                poll_id = TypeSafeColumn.get_int(poll, "id", 0) if poll else 0
                logger.error(
                    f"❌ SCHEDULER RESTORE - Error processing poll {poll_id}: {e}"
                )
                logger.exception(
                    f"Full traceback for poll {poll_id} restoration error:"
                )

        # CRITICAL FIX: Process active polls that may need to be closed
        active_immediate_closes = 0
        active_restored_count = 0

        for poll in active_polls:
            try:
                poll_id = TypeSafeColumn.get_int(poll, "id")
                poll_name = TypeSafeColumn.get_string(poll, "name", "Unknown")

                logger.info(
                    f"🔄 SCHEDULER RESTORE - Processing active poll {poll_id}: '{poll_name}'"
                )
                logger.debug(
                    f"Active poll {poll_id} details: open_time={poll.open_time_aware}, close_time={poll.close_time_aware}, status={poll.status}"
                )

                # Get poll times as actual datetime objects using TypeSafeColumn
                poll_close_time = poll.close_time

                # Ensure we have valid datetime objects
                if not isinstance(poll_close_time, datetime):
                    logger.error(
                        f"❌ SCHEDULER RESTORE - Invalid close_time datetime object for active poll {poll_id}"
                    )
                    continue

                # Ensure poll times are timezone-aware for comparison
                if poll_close_time.tzinfo is None:
                    poll_close_time = pytz.UTC.localize(poll_close_time)
                    logger.debug(
                        f"🕐 SCHEDULER RESTORE - Localized naive close_time to UTC for active poll {poll_id}"
                    )

                # Check if active poll should be closed
                if poll_close_time <= now:
                    # Active poll should have already closed
                    time_overdue = (now - poll_close_time).total_seconds()
                    logger.warning(
                        f"⏰ SCHEDULER RESTORE - Active poll {poll_id} close time is {time_overdue:.0f} seconds overdue, closing now"
                    )

                    try:
                        await close_poll(poll_id)
                        active_immediate_closes += 1
                        logger.info(
                            f"✅ SCHEDULER RESTORE - Successfully closed overdue active poll {poll_id}"
                        )
                    except Exception as close_exc:
                        logger.error(
                            f"❌ SCHEDULER RESTORE - Exception closing active poll {poll_id}: {close_exc}"
                        )
                        logger.exception(f"Full traceback for active poll {poll_id} closing:")
                else:
                    # Active poll still has time left - schedule it to close
                    time_until_close = (poll_close_time - now).total_seconds()
                    logger.info(
                        f"📅 SCHEDULER RESTORE - Scheduling active poll {poll_id} to close in {time_until_close:.0f} seconds at {poll_close_time}"
                    )

                    # Use timezone-aware scheduler for restoration
                    tz_scheduler = TimezoneAwareScheduler(scheduler)
                    poll_timezone = TypeSafeColumn.get_string(poll, "timezone", "UTC")

                    success_close = tz_scheduler.schedule_poll_closing(
                        poll_id, poll_close_time, poll_timezone, close_poll
                    )
                    if success_close:
                        logger.debug(
                            f"✅ SCHEDULER RESTORE - Scheduled closing job for active poll {poll_id}"
                        )
                    else:
                        logger.error(
                            f"❌ SCHEDULER RESTORE - Failed to schedule closing for active poll {poll_id}"
                        )

                active_restored_count += 1
                logger.debug(
                    f"✅ SCHEDULER RESTORE - Completed processing active poll {poll_id}"
                )

            except Exception as e:
                poll_id = TypeSafeColumn.get_int(poll, "id", 0) if poll else 0
                logger.error(
                    f"❌ SCHEDULER RESTORE - Error processing active poll {poll_id}: {e}"
                )
                logger.exception(
                    f"Full traceback for active poll {poll_id} restoration error:"
                )

        # Log final restoration summary
        logger.info("🎉 SCHEDULER RESTORE - Restoration complete!")
        logger.info(
            f"📊 SCHEDULER RESTORE - Summary: {restored_count}/{len(scheduled_polls)} scheduled polls processed, {active_restored_count}/{len(active_polls)} active polls processed"
        )
        logger.info(
            f"📊 SCHEDULER RESTORE - Immediate actions: {immediate_closes} scheduled polls closed, {active_immediate_closes} active polls closed"
        )

        # Debug current scheduler jobs
        current_jobs = scheduler.get_jobs()
        logger.info(
            f"📊 SCHEDULER RESTORE - Total active jobs after restoration: {len(current_jobs)}"
        )
        for job in current_jobs:
            logger.debug(f"Active job: {job.id} - next run: {job.next_run_time}")

    except Exception as e:
        logger.error(f"❌ SCHEDULER RESTORE - Critical error during restoration: {e}")
        logger.exception("Full traceback for scheduler restoration error:")
    finally:
        db.close()
        logger.debug("🔄 SCHEDULER RESTORE - Database connection closed")


async def start_scheduler():
    """Start the job scheduler"""
    scheduler.start()
    logger.info("Scheduler started")

    # Restore scheduled jobs from database
    await restore_scheduled_jobs()


async def shutdown_scheduler():
    """Shutdown the job scheduler"""
    if scheduler and scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler shutdown")


async def reaction_safeguard_task():
    """
    Safeguard task that runs every 5 seconds to check for unprocessed reactions
    on active polls and handle them to ensure no votes are lost.
    """
    from .discord_bot import get_bot_instance
    from .poll_operations import BulletproofPollOperations
    from .database import POLL_EMOJIS

    while True:
        try:
            await asyncio.sleep(5)  # Run every 5 seconds

            bot = get_bot_instance()
            if not bot or not bot.is_ready():
                continue

            # Get all active polls
            db = get_db_session()
            try:
                active_polls = db.query(Poll).filter(Poll.status == "active").all()

                for poll in active_polls:
                    try:
                        poll_message_id = TypeSafeColumn.get_string(poll, "message_id")
                        if not poll_message_id:
                            continue

                        # Get the Discord message
                        try:
                            poll_channel_id = TypeSafeColumn.get_string(
                                poll, "channel_id"
                            )
                            channel = bot.get_channel(int(poll_channel_id))
                            if not channel:
                                continue
                        except Exception as channel_error:
                            poll_id = TypeSafeColumn.get_int(poll, "id")
                            logger.error(
                                f"❌ Safeguard: Error getting channel {poll_channel_id} for poll {poll_id}: {channel_error}"
                            )
                            continue

                        try:
                            if isinstance(channel, discord.TextChannel):
                                message = await channel.fetch_message(
                                    int(poll_message_id)
                                )
                                # Message found successfully - clear any failure tracking
                                poll_id = TypeSafeColumn.get_int(poll, "id")
                                if poll_id in message_fetch_failures:
                                    del message_fetch_failures[poll_id]
                                    logger.debug(
                                        f"✅ Safeguard: Message {poll_message_id} found for poll {poll_id}, cleared failure tracking"
                                    )
                            else:
                                # Skip non-text channels
                                continue
                        except discord.NotFound:
                            # Message not found - implement retry logic with multiple methods
                            poll_id = TypeSafeColumn.get_int(poll, "id")
                            poll_name = TypeSafeColumn.get_string(
                                poll, "name", "Unknown"
                            )
                            current_time = datetime.now(pytz.UTC)

                            # Initialize or update failure tracking
                            if poll_id not in message_fetch_failures:
                                message_fetch_failures[poll_id] = {
                                    "count": 1,
                                    "first_failure": current_time,
                                    "last_attempt": current_time,
                                    "methods_tried": ["fetch_message"],
                                }
                                logger.info(
                                    f"ℹ️ Safeguard: Message {poll_message_id} not found for poll {poll_id} (attempt 1/{MAX_FETCH_RETRIES})"
                                )
                            else:
                                failure_info = message_fetch_failures[poll_id]
                                failure_info["count"] += 1
                                failure_info["last_attempt"] = current_time

                                # Check if we're within the retry window
                                time_since_first_failure = (
                                    current_time - failure_info["first_failure"]
                                ).total_seconds() / 60

                                if time_since_first_failure > RETRY_WINDOW_MINUTES:
                                    # Reset the failure tracking if too much time has passed
                                    message_fetch_failures[poll_id] = {
                                        "count": 1,
                                        "first_failure": current_time,
                                        "last_attempt": current_time,
                                        "methods_tried": ["fetch_message"],
                                    }
                                    logger.warning(
                                        f"⚠️ Safeguard: Message {poll_message_id} not found for poll {poll_id} (attempt 1/{MAX_FETCH_RETRIES}, reset after {time_since_first_failure:.1f} minutes)"
                                    )
                                else:
                                    # Only warn after multiple attempts
                                    if failure_info['count'] >= 3:
                                        logger.warning(
                                            f"⚠️ Safeguard: Message {poll_message_id} not found for poll {poll_id} (attempt {failure_info['count']}/{MAX_FETCH_RETRIES})"
                                        )
                                    else:
                                        logger.info(
                                            f"ℹ️ Safeguard: Message {poll_message_id} not found for poll {poll_id} (attempt {failure_info['count']}/{MAX_FETCH_RETRIES})"
                                        )

                                # Try alternative methods before giving up
                                if failure_info["count"] <= MAX_FETCH_RETRIES:
                                    # Try different approaches to find the message
                                    message_found = False

                                    # Method 2: Try to get message from channel history
                                    if (
                                        "history_search"
                                        not in failure_info["methods_tried"]
                                        and failure_info["count"] >= 2
                                    ):
                                        try:
                                            logger.debug(
                                                f"🔍 Safeguard: Trying history search for message {poll_message_id} in poll {poll_id}"
                                            )
                                            async for hist_message in channel.history(
                                                limit=100
                                            ):
                                                if (
                                                    str(hist_message.id)
                                                    == poll_message_id
                                                ):
                                                    message = hist_message
                                                    message_found = True
                                                    logger.info(
                                                        f"✅ Safeguard: Found message {poll_message_id} via history search for poll {poll_id}"
                                                    )
                                                    break
                                            failure_info["methods_tried"].append(
                                                "history_search"
                                            )
                                        except Exception as history_error:
                                            logger.debug(
                                                f"❌ Safeguard: History search failed for poll {poll_id}: {history_error}"
                                            )

                                    # Method 3: Try with a small delay and retry fetch
                                    if (
                                        not message_found
                                        and "delayed_fetch"
                                        not in failure_info["methods_tried"]
                                        and failure_info["count"] >= 3
                                    ):
                                        try:
                                            logger.debug(
                                                f"🔍 Safeguard: Trying delayed fetch for message {poll_message_id} in poll {poll_id}"
                                            )
                                            # Small delay
                                            await asyncio.sleep(2)
                                            message = await channel.fetch_message(
                                                int(poll_message_id)
                                            )
                                            message_found = True
                                            logger.info(
                                                f"✅ Safeguard: Found message {poll_message_id} via delayed fetch for poll {poll_id}"
                                            )
                                            failure_info["methods_tried"].append(
                                                "delayed_fetch"
                                            )
                                        except discord.NotFound:
                                            logger.debug(
                                                f"❌ Safeguard: Delayed fetch still failed for poll {poll_id}"
                                            )
                                            failure_info["methods_tried"].append(
                                                "delayed_fetch"
                                            )
                                        except Exception as delayed_error:
                                            logger.debug(
                                                f"❌ Safeguard: Delayed fetch error for poll {poll_id}: {delayed_error}"
                                            )

                                    if message_found:
                                        # Clear failure tracking since we found the message
                                        del message_fetch_failures[poll_id]
                                        logger.info(
                                            f"✅ Safeguard: Message {poll_message_id} recovered for poll {poll_id}, cleared failure tracking"
                                        )
                                        # Continue processing the message normally
                                    elif failure_info["count"] >= MAX_FETCH_RETRIES:
                                        # All retry attempts exhausted - delete the poll
                                        logger.error(
                                            f"🗑️ Safeguard: Message {poll_message_id} not found after {MAX_FETCH_RETRIES} attempts over {time_since_first_failure:.1f} minutes for poll {poll_id}, deleting poll"
                                        )

                                        try:
                                            # Delete associated votes first
                                            db.query(Vote).filter(
                                                Vote.poll_id == poll_id
                                            ).delete()
                                            # Delete the poll
                                            db.delete(poll)
                                            db.commit()

                                            # Clear failure tracking
                                            del message_fetch_failures[poll_id]

                                            logger.info(
                                                f"✅ Safeguard: Deleted poll {poll_id}: '{poll_name}' after {MAX_FETCH_RETRIES} failed message fetch attempts"
                                            )
                                        except Exception as delete_error:
                                            logger.error(
                                                f"❌ Safeguard: Error deleting poll {poll_id}: {delete_error}"
                                            )
                                            db.rollback()
                                        continue
                                    else:
                                        # Still within retry limit, continue to next poll
                                        continue

                            continue
                        except Exception as fetch_error:
                            poll_id = TypeSafeColumn.get_int(poll, "id")
                            logger.error(
                                f"❌ Safeguard: Error fetching message {poll_message_id} for poll {poll_id}: {fetch_error}"
                            )
                            continue

                        # Check each reaction on the message
                        for reaction in message.reactions:
                            try:
                                if str(reaction.emoji) not in POLL_EMOJIS:
                                    continue

                                option_index = POLL_EMOJIS.index(str(reaction.emoji))
                                if option_index >= len(poll.options):
                                    continue

                                # Get users who reacted (excluding the bot)
                                try:
                                    async for user in reaction.users():
                                        if user.bot:
                                            continue

                                        try:
                                            poll_id = TypeSafeColumn.get_int(poll, "id")
                                            # Check if this user's vote is already recorded
                                            existing_vote = (
                                                db.query(Vote)
                                                .filter(
                                                    Vote.poll_id == poll_id,
                                                    Vote.user_id == str(user.id),
                                                )
                                                .first()
                                            )

                                            if existing_vote:
                                                # User has existing vote - let normal vote processing handle this
                                                # The bulletproof_vote_collection already handles vote changes correctly
                                                logger.info(
                                                    f"🛡️ Safeguard: User {user.id} has existing vote, processing through normal vote system for poll {poll_id}"
                                                )

                                                try:
                                                    # Use bulletproof vote collection to handle the vote properly
                                                    bulletproof_ops = (
                                                        BulletproofPollOperations(bot)
                                                    )
                                                    result = await bulletproof_ops.bulletproof_vote_collection(
                                                        poll_id,
                                                        str(user.id),
                                                        option_index,
                                                    )

                                                    if result["success"]:
                                                        vote_action = result.get("action", "unknown")
                                                        
                                                        # Vote was processed successfully - remove the reaction
                                                        try:
                                                            await reaction.remove(user)
                                                            logger.info(
                                                                f"✅ Safeguard: Vote processed and reaction removed for user {user.id} on poll {poll_id} (action: {vote_action})"
                                                            )
                                                        except Exception as remove_error:
                                                            logger.warning(
                                                                f"⚠️ Safeguard: Vote processed but failed to remove reaction from user {user.id}: {remove_error}"
                                                            )

                                                        # Send DM confirmation to the voter
                                                        try:
                                                            from .discord_utils import send_vote_confirmation_dm

                                                            logger.info(f"🔔 SAFEGUARD DM DEBUG - About to send DM for vote_action: {vote_action} to user {user.id}")
                                                            dm_sent = await send_vote_confirmation_dm(
                                                                bot, poll, str(user.id), option_index, vote_action
                                                            )
                                                            if dm_sent:
                                                                logger.info(
                                                                    f"✅ Safeguard: Vote confirmation DM sent to user {user.id} for poll {poll_id} (action: {vote_action})"
                                                                )
                                                            else:
                                                                logger.warning(
                                                                    f"⚠️ Safeguard: Vote confirmation DM not sent to user {user.id} (DMs disabled or error) (action: {vote_action})"
                                                                )
                                                        except Exception as dm_error:
                                                            logger.error(
                                                                f"❌ Safeguard: Failed to send vote confirmation DM to user {user.id}: {dm_error} (action: {vote_action})"
                                                            )
                                                            # Don't fail the vote process if DM fails

                                                        # Update poll embed for live updates
                                                        try:
                                                            await update_poll_message(bot, poll)
                                                            logger.debug(f"✅ Safeguard: Poll message updated for poll {poll_id}")
                                                        except Exception as update_error:
                                                            logger.error(f"❌ Safeguard: Failed to update poll message for poll {poll_id}: {update_error}")
                                                    else:
                                                        # Vote processing failed - leave reaction for user to try again
                                                        logger.error(
                                                            f"❌ Safeguard: Vote processing FAILED for user {user.id} on poll {poll_id}: {result['error']}"
                                                        )

                                                except Exception as vote_error:
                                                    logger.error(
                                                        f"❌ Safeguard: Critical error processing existing vote for user {user.id} on poll {poll_id}: {vote_error}"
                                                    )
                                            else:
                                                # No vote recorded, but first re-check poll status to avoid race conditions
                                                # The poll might have closed between our initial query and now
                                                fresh_db = get_db_session()
                                                try:
                                                    fresh_poll = fresh_db.query(Poll).filter(Poll.id == poll_id).first()
                                                    if not fresh_poll or TypeSafeColumn.get_string(fresh_poll, "status") != "active":
                                                        logger.info(
                                                            f"🛡️ Safeguard: Poll {poll_id} is no longer active, removing reaction from user {user.id}"
                                                        )
                                                        try:
                                                            await reaction.remove(user)
                                                            logger.debug(
                                                                f"🧹 Safeguard: Removed reaction from user {user.id} on closed poll {poll_id}"
                                                            )
                                                        except Exception as remove_error:
                                                            logger.debug(
                                                                f"⚠️ Safeguard: Failed to remove reaction from user {user.id} on closed poll: {remove_error}"
                                                            )
                                                        continue
                                                finally:
                                                    fresh_db.close()

                                                # Poll is still active, process the vote
                                                logger.info(
                                                    f"🛡️ Safeguard: Processing missed reaction from user {user.id} on poll {poll_id}"
                                                )

                                                try:
                                                    # Use bulletproof vote collection
                                                    bulletproof_ops = (
                                                        BulletproofPollOperations(bot)
                                                    )
                                                    result = await bulletproof_ops.bulletproof_vote_collection(
                                                        poll_id,
                                                        str(user.id),
                                                        option_index,
                                                    )

                                                    if result["success"]:
                                                        # Vote was successfully recorded - NOW remove the reaction
                                                        try:
                                                            await reaction.remove(user)
                                                            logger.info(
                                                                f"✅ Safeguard: Vote recorded and reaction removed for user {user.id} on poll {poll_id}"
                                                            )
                                                        except (
                                                            Exception
                                                        ) as remove_error:
                                                            logger.warning(
                                                                f"⚠️ Safeguard: Vote recorded but failed to remove reaction from user {user.id}: {remove_error}"
                                                            )

                                                        # Update poll embed for live updates
                                                        try:
                                                            await update_poll_message(
                                                                bot, poll
                                                            )
                                                            logger.debug(
                                                                f"✅ Safeguard: Poll message updated for poll {poll_id}"
                                                            )
                                                        except (
                                                            Exception
                                                        ) as update_error:
                                                            logger.error(
                                                                f"❌ Safeguard: Failed to update poll message for poll {poll_id}: {update_error}"
                                                            )
                                                    else:
                                                        # Vote failed - leave reaction for user to try again
                                                        logger.error(
                                                            f"❌ Safeguard: Vote FAILED for user {user.id} on poll {poll_id}: {result['error']}"
                                                        )

                                                except Exception as vote_error:
                                                    logger.error(
                                                        f"❌ Safeguard: Critical error processing vote for user {user.id} on poll {poll_id}: {vote_error}"
                                                    )

                                        except Exception as user_error:
                                            poll_id = TypeSafeColumn.get_int(poll, "id")
                                            logger.error(
                                                f"❌ Safeguard: Error processing user {user.id} reaction on poll {poll_id}: {user_error}"
                                            )
                                            continue

                                except Exception as users_error:
                                    poll_id = TypeSafeColumn.get_int(poll, "id")
                                    logger.error(
                                        f"❌ Safeguard: Error iterating reaction users for poll {poll_id}: {users_error}"
                                    )
                                    continue

                            except Exception as reaction_error:
                                poll_id = TypeSafeColumn.get_int(poll, "id")
                                logger.error(
                                    f"❌ Safeguard: Error processing reaction {reaction.emoji} on poll {poll_id}: {reaction_error}"
                                )
                                continue

                    except Exception as poll_error:
                        poll_id = TypeSafeColumn.get_int(poll, "id")
                        logger.error(
                            f"❌ Safeguard: Error processing poll {poll_id}: {poll_error}"
                        )
                        continue

            except Exception as db_error:
                logger.error(f"❌ Safeguard: Database error: {db_error}")
            finally:
                try:
                    db.close()
                except Exception as close_error:
                    logger.error(f"❌ Safeguard: Error closing database: {close_error}")

        except Exception as e:
            logger.error(
                f"❌ Safeguard: Critical error in reaction safeguard task: {e}"
            )
            # Continue running even if there's an error
            continue


async def start_reaction_safeguard():
    """Start the reaction safeguard background task"""
    try:
        logger.info("🛡️ Starting reaction safeguard task")
        asyncio.create_task(reaction_safeguard_task())
        logger.info("✅ Reaction safeguard task started successfully")
    except Exception as e:
        logger.error(f"❌ Failed to start reaction safeguard task: {e}")
        raise e  # Re-raise to ensure the application knows the safeguard failed to start


def get_scheduler():
    """Get the scheduler instance"""
    return scheduler
