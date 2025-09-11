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

from .database import get_db_session, Poll, Vote, TypeSafeColumn
from .discord_utils import post_poll_to_channel, update_poll_message
from .timezone_scheduler_fix import TimezoneAwareScheduler
from .error_handler import PollErrorHandler

# Track failed message fetch attempts for polls during runtime
# Format: {poll_id: {"count": int, "first_failure": datetime, "last_attempt": datetime}}
message_fetch_failures = {}
MAX_FETCH_RETRIES = 5  # Number of consecutive failures before deleting poll
RETRY_WINDOW_MINUTES = 30  # Time window to track failures

logger = logging.getLogger(__name__)

# Scheduler for poll timing
scheduler = AsyncIOScheduler()


async def close_poll(poll_id: int):
    """Close a poll using bulletproof operations and post final results"""
    try:
        from .discord_bot import get_bot_instance
        from .discord_utils import update_poll_message
        import discord

        bot = get_bot_instance()
        if not bot:
            logger.error(f"❌ CLOSE POLL {poll_id} - Bot instance not available")
            return

        logger.info(f"🏁 CLOSE POLL {poll_id} - Starting poll closure process")

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
                logger.error(f"❌ CLOSE POLL {poll_id} - Poll not found in database")
                return

            # Check if already closed
            current_status = TypeSafeColumn.get_string(poll, "status")
            if current_status == "closed":
                logger.info(f"ℹ️ CLOSE POLL {poll_id} - Poll already closed, skipping")
                return

            # Extract poll data while still attached to session
            message_id = TypeSafeColumn.get_string(poll, "message_id")
            channel_id = TypeSafeColumn.get_string(poll, "channel_id")
            poll_name = TypeSafeColumn.get_string(poll, "name", "Unknown")
            
            logger.info(f"📊 CLOSE POLL {poll_id} - Poll '{poll_name}' found, status: {current_status}")

        except Exception as e:
            logger.error(f"❌ CLOSE POLL {poll_id} - Error fetching poll data: {e}")
            return
        finally:
            db.close()

        # STEP 2: Close poll in database using bulletproof operations
        try:
            from .poll_operations import BulletproofPollOperations
            
            bulletproof_ops = BulletproofPollOperations(bot)
            result = await bulletproof_ops.bulletproof_poll_closure(poll_id)

            if not result["success"]:
                error_msg = await PollErrorHandler.handle_poll_closure_error(
                    Exception(result["error"]), poll_id, bot
                )
                logger.error(f"❌ CLOSE POLL {poll_id} - Bulletproof closure failed: {error_msg}")
                return
            else:
                logger.info(f"✅ CLOSE POLL {poll_id} - Poll status updated to closed in database")

        except Exception as e:
            error_msg = await PollErrorHandler.handle_poll_closure_error(e, poll_id, bot)
            logger.error(f"❌ CLOSE POLL {poll_id} - Bulletproof closure exception: {error_msg}")
            return

        # STEP 3: Clear reactions from Discord message
        if message_id and channel_id:
            try:
                channel = bot.get_channel(int(channel_id))
                if channel and isinstance(channel, discord.TextChannel):
                    try:
                        message = await channel.fetch_message(int(message_id))
                        if message:
                            # Clear all reactions from the poll message
                            await message.clear_reactions()
                            logger.info(f"✅ CLOSE POLL {poll_id} - Cleared all reactions from Discord message")
                        else:
                            logger.warning(f"⚠️ CLOSE POLL {poll_id} - Could not find message {message_id}")
                    except discord.NotFound:
                        logger.warning(f"⚠️ CLOSE POLL {poll_id} - Message {message_id} not found (may have been deleted)")
                    except discord.Forbidden:
                        logger.warning(f"⚠️ CLOSE POLL {poll_id} - No permission to clear reactions")
                    except Exception as reaction_error:
                        logger.error(f"❌ CLOSE POLL {poll_id} - Error clearing reactions: {reaction_error}")
                else:
                    logger.warning(f"⚠️ CLOSE POLL {poll_id} - Could not find or access channel {channel_id}")
            except Exception as channel_error:
                logger.error(f"❌ CLOSE POLL {poll_id} - Error accessing channel: {channel_error}")

        # STEP 4: Get fresh poll data and update the existing message to show it's closed
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
                # Update the poll embed to show it's closed with final results
                try:
                    await update_poll_message(bot, fresh_poll)
                    logger.info(f"✅ CLOSE POLL {poll_id} - Updated poll message to show closed status with final results")
                except Exception as update_error:
                    logger.error(f"❌ CLOSE POLL {poll_id} - Error updating poll message: {update_error}")

                # Send role ping notification if enabled and configured for poll closure
                ping_role_enabled = TypeSafeColumn.get_bool(fresh_poll, "ping_role_enabled", False)
                ping_role_id = TypeSafeColumn.get_string(fresh_poll, "ping_role_id")
                ping_role_on_close = TypeSafeColumn.get_bool(fresh_poll, "ping_role_on_close", False)
                ping_role_name = TypeSafeColumn.get_string(fresh_poll, "ping_role_name", "Unknown Role")
                
                if ping_role_enabled and ping_role_id and ping_role_on_close:
                    try:
                        poll_channel_id = TypeSafeColumn.get_string(fresh_poll, "channel_id")
                        if poll_channel_id:
                            channel = bot.get_channel(int(poll_channel_id))
                            if channel and isinstance(channel, discord.TextChannel):
                                poll_name = TypeSafeColumn.get_string(fresh_poll, "name", "Unknown Poll")
                                
                                # Prepare role ping message with comprehensive error handling
                                message_content = f"📊 **Poll '{poll_name}' has ended!**"
                                role_ping_attempted = False
                                
                                role_id = str(ping_role_id)
                                message_content = f"<@&{role_id}> {message_content}"
                                role_ping_attempted = True
                                logger.info(
                                    f"🔔 CLOSE POLL {poll_id} - Will ping role {ping_role_name} ({role_id}) for poll closure"
                                )
                                
                                # Send role ping message with graceful error handling
                                try:
                                    await channel.send(content=message_content)
                                    logger.info(f"✅ CLOSE POLL {poll_id} - Sent role ping notification")
                                except discord.Forbidden as role_error:
                                    if role_ping_attempted:
                                        # Role ping failed due to permissions, try without role ping
                                        logger.warning(
                                            f"⚠️ CLOSE POLL {poll_id} - Role ping failed due to permissions, posting without role ping: {role_error}"
                                        )
                                        try:
                                            fallback_content = f"📊 **Poll '{poll_name}' has ended!**"
                                            await channel.send(content=fallback_content)
                                            logger.info(
                                                f"✅ CLOSE POLL {poll_id} - Sent fallback notification without role ping"
                                            )
                                        except Exception as fallback_error:
                                            logger.error(
                                                f"❌ CLOSE POLL {poll_id} - Fallback notification also failed: {fallback_error}"
                                            )
                                    else:
                                        # Not a role ping issue, re-raise the error
                                        raise role_error
                                except Exception as send_error:
                                    logger.error(f"❌ CLOSE POLL {poll_id} - Error sending role ping notification: {send_error}")
                            else:
                                logger.warning(f"⚠️ CLOSE POLL {poll_id} - Could not find or access channel {poll_channel_id}")
                        else:
                            logger.warning(f"⚠️ CLOSE POLL {poll_id} - No channel ID found for role ping notification")
                    except Exception as ping_error:
                        logger.error(f"❌ CLOSE POLL {poll_id} - Error in role ping notification process: {ping_error}")
                elif ping_role_enabled and ping_role_id and not ping_role_on_close:
                    logger.info(f"ℹ️ CLOSE POLL {poll_id} - Role ping enabled but ping_role_on_close is disabled")
                elif ping_role_enabled and not ping_role_id:
                    logger.warning(f"⚠️ CLOSE POLL {poll_id} - Role ping enabled but no role ID configured")
            else:
                logger.error(f"❌ CLOSE POLL {poll_id} - Poll not found for message update")
        finally:
            db.close()

        # STEP 5: Generate static content for closed poll
        try:
            from .static_page_generator import generate_static_content_on_poll_close
            
            logger.info(f"🔧 CLOSE POLL {poll_id} - Generating static content for closed poll")
            static_success = await generate_static_content_on_poll_close(poll_id, bot)
            
            if static_success:
                logger.info(f"✅ CLOSE POLL {poll_id} - Static content generated successfully")
            else:
                logger.warning(f"⚠️ CLOSE POLL {poll_id} - Static content generation failed, but poll closure continues")
                
        except Exception as static_error:
            logger.error(f"❌ CLOSE POLL {poll_id} - Error generating static content: {static_error}")
            # Don't fail the entire poll closure process if static generation fails
            logger.info(f"🔄 CLOSE POLL {poll_id} - Continuing with poll closure despite static generation failure")

        logger.info(f"🎉 CLOSE POLL {poll_id} - Poll closure process completed")

    except Exception as e:
        # Handle unexpected closure errors with bot owner notification
        from .discord_bot import get_bot_instance

        bot = get_bot_instance()
        error_msg = await PollErrorHandler.handle_poll_closure_error(e, poll_id, bot)
        logger.error(f"❌ CLOSE POLL {poll_id} - Unexpected error in close_poll function: {error_msg}")


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
        # Get all polls that have message IDs (active and scheduled polls that were posted)
        polls_with_messages = (
            db.query(Poll)
            .filter(
                Poll.message_id.isnot(None), Poll.status.in_(["active", "scheduled"])
            )
            .all()
        )

        logger.info(
            f"📊 MESSAGE CLEANUP - Found {len(polls_with_messages)} polls with message IDs to check"
        )

        deleted_polls = []

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

                # Try to fetch the message (only for text channels)
                try:
                    if isinstance(channel, discord.TextChannel):
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
                    logger.warning(
                        f"🗑️ MESSAGE CLEANUP - Message {message_id} not found for poll {poll_id}, marking for deletion"
                    )
                    deleted_polls.append(poll)
                except discord.Forbidden:
                    logger.warning(
                        f"🔒 MESSAGE CLEANUP - No permission to access message {message_id} for poll {poll_id}, keeping poll"
                    )
                except discord.HTTPException as e:
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

    # First, clean up polls whose messages have been deleted
    await cleanup_polls_with_deleted_messages()
    
    # Run static content recovery for existing closed polls
    await run_static_content_recovery_on_startup()


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
        
        # Run recovery with a reasonable limit to avoid overwhelming the system on startup
        results = await run_static_content_recovery(bot, limit=50)
        
        if results["successful_generations"] > 0:
            logger.info(f"✅ STARTUP RECOVERY - Generated static content for {results['successful_generations']} existing closed polls")
        
        if results["failed_generations"] > 0:
            logger.warning(f"⚠️ STARTUP RECOVERY - Failed to generate static content for {results['failed_generations']} polls")
        
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

        if not scheduled_polls:
            logger.info(
                "✅ SCHEDULER RESTORE - No scheduled polls found, restoration complete"
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
                    f"Poll {poll_id} details: open_time={poll.open_time}, close_time={poll.close_time}, status={poll.status}"
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

                # Schedule poll opening (use the timezone-aware datetime)
                success_open = tz_scheduler.schedule_poll_opening(
                    poll_id, poll_open_time, poll_timezone, post_poll_to_channel, bot
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

        # Log final restoration summary
        logger.info("🎉 SCHEDULER RESTORE - Restoration complete!")
        logger.info(
            f"📊 SCHEDULER RESTORE - Summary: {restored_count}/{len(scheduled_polls)} polls processed"
        )
        logger.info(
            f"📊 SCHEDULER RESTORE - Immediate actions: {immediate_closes} closed"
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
                                logger.warning(
                                    f"⚠️ Safeguard: Message {poll_message_id} not found for poll {poll_id} (attempt 1/{MAX_FETCH_RETRIES})"
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
                                    logger.warning(
                                        f"⚠️ Safeguard: Message {poll_message_id} not found for poll {poll_id} (attempt {failure_info['count']}/{MAX_FETCH_RETRIES})"
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
                                                        # Vote was processed successfully - remove the reaction
                                                        try:
                                                            await reaction.remove(user)
                                                            logger.info(
                                                                f"✅ Safeguard: Vote processed and reaction removed for user {user.id} on poll {poll_id} (action: {result.get('action', 'unknown')})"
                                                            )
                                                        except Exception as remove_error:
                                                            logger.warning(
                                                                f"⚠️ Safeguard: Vote processed but failed to remove reaction from user {user.id}: {remove_error}"
                                                            )

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
