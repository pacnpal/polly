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
from .error_handler import PollErrorHandler, notify_error_async

logger = logging.getLogger(__name__)

# Scheduler for poll timing
scheduler = AsyncIOScheduler()


async def close_poll(poll_id: int):
    """Close a poll using bulletproof operations"""
    try:
        from .poll_operations import BulletproofPollOperations
        from .discord_bot import get_bot_instance

        # Use bulletproof poll closure
        bot = get_bot_instance()
        bulletproof_ops = BulletproofPollOperations(bot)
        result = await bulletproof_ops.bulletproof_poll_closure(poll_id)

        if not result["success"]:
            # Handle closure error with bot owner notification
            error_msg = await PollErrorHandler.handle_poll_closure_error(
                Exception(result["error"]), poll_id, bot
            )
            logger.error(
                f"Bulletproof poll closure failed for poll {poll_id}: {error_msg}")
        else:
            logger.info(
                f"Successfully closed poll {poll_id} using bulletproof operations")

    except Exception as e:
        # Handle unexpected closure errors with bot owner notification
        from .discord_bot import get_bot_instance
        bot = get_bot_instance()
        error_msg = await PollErrorHandler.handle_poll_closure_error(
            e, poll_id, bot
        )
        logger.error(f"Error in close_poll function: {error_msg}")


async def cleanup_polls_with_deleted_messages():
    """
    Check for polls whose Discord messages have been deleted and remove them from the database.

    This function checks all active and scheduled polls to see if their Discord messages still exist.
    If a message has been deleted, the poll is removed from the database to maintain consistency.
    """
    logger.info(
        "🧹 MESSAGE CLEANUP - Starting cleanup of polls with deleted messages")

    from .discord_bot import get_bot_instance
    bot = get_bot_instance()

    if not bot or not bot.is_ready():
        logger.warning(
            "⚠️ MESSAGE CLEANUP - Bot not ready, skipping message cleanup")
        return

    db = get_db_session()
    try:
        # Get all polls that have message IDs (active and scheduled polls that were posted)
        polls_with_messages = db.query(Poll).filter(
            Poll.message_id.isnot(None),
            Poll.status.in_(["active", "scheduled"])
        ).all()

        logger.info(
            f"📊 MESSAGE CLEANUP - Found {len(polls_with_messages)} polls with message IDs to check")

        deleted_polls = []

        for poll in polls_with_messages:
            try:
                poll_id = TypeSafeColumn.get_int(poll, 'id')
                poll_name = TypeSafeColumn.get_string(poll, 'name', 'Unknown')
                message_id = TypeSafeColumn.get_string(poll, 'message_id')
                channel_id = TypeSafeColumn.get_string(poll, 'channel_id')

                logger.debug(
                    f"🔍 MESSAGE CLEANUP - Checking poll {poll_id}: '{poll_name}' (message: {message_id})")

                # Get the channel
                try:
                    channel = bot.get_channel(int(channel_id))
                    if not channel:
                        logger.warning(
                            f"⚠️ MESSAGE CLEANUP - Channel {channel_id} not found for poll {poll_id}, marking for deletion")
                        deleted_polls.append(poll)
                        continue
                except (ValueError, TypeError) as e:
                    logger.error(
                        f"❌ MESSAGE CLEANUP - Invalid channel ID {channel_id} for poll {poll_id}: {e}")
                    deleted_polls.append(poll)
                    continue

                # Try to fetch the message (only for text channels)
                try:
                    if isinstance(channel, discord.TextChannel):
                        await channel.fetch_message(int(message_id))
                        logger.debug(
                            f"✅ MESSAGE CLEANUP - Message {message_id} exists for poll {poll_id}")
                    else:
                        logger.warning(
                            f"⚠️ MESSAGE CLEANUP - Channel {channel_id} is not a text channel for poll {poll_id}, marking for deletion")
                        deleted_polls.append(poll)
                        continue
                except discord.NotFound:
                    logger.warning(
                        f"🗑️ MESSAGE CLEANUP - Message {message_id} not found for poll {poll_id}, marking for deletion")
                    deleted_polls.append(poll)
                except discord.Forbidden:
                    logger.warning(
                        f"🔒 MESSAGE CLEANUP - No permission to access message {message_id} for poll {poll_id}, keeping poll")
                except discord.HTTPException as e:
                    logger.error(
                        f"❌ MESSAGE CLEANUP - HTTP error checking message {message_id} for poll {poll_id}: {e}")
                    # Don't delete on HTTP errors, might be temporary
                except (ValueError, TypeError) as e:
                    logger.error(
                        f"❌ MESSAGE CLEANUP - Invalid message ID {message_id} for poll {poll_id}: {e}")
                    deleted_polls.append(poll)
                except Exception as e:
                    logger.error(
                        f"❌ MESSAGE CLEANUP - Unexpected error checking message {message_id} for poll {poll_id}: {e}")
                    # Don't delete on unexpected errors

            except Exception as e:
                poll_id = TypeSafeColumn.get_int(poll, 'id', 0) if poll else 0
                logger.error(
                    f"❌ MESSAGE CLEANUP - Error processing poll {poll_id}: {e}")
                continue

        # Delete polls whose messages were not found
        if deleted_polls:
            logger.info(
                f"🗑️ MESSAGE CLEANUP - Deleting {len(deleted_polls)} polls with missing messages")

            for poll in deleted_polls:
                try:
                    poll_id = TypeSafeColumn.get_int(poll, 'id')
                    poll_name = TypeSafeColumn.get_string(
                        poll, 'name', 'Unknown')

                    # Delete associated votes first (cascade should handle this, but be explicit)
                    db.query(Vote).filter(Vote.poll_id == poll_id).delete()

                    # Delete the poll
                    db.delete(poll)

                    logger.info(
                        f"✅ MESSAGE CLEANUP - Deleted poll {poll_id}: '{poll_name}'")

                except Exception as e:
                    poll_id = TypeSafeColumn.get_int(
                        poll, 'id', 0) if poll else 0
                    logger.error(
                        f"❌ MESSAGE CLEANUP - Error deleting poll {poll_id}: {e}")
                    continue

            # Commit all deletions
            db.commit()
            logger.info(
                f"✅ MESSAGE CLEANUP - Successfully deleted {len(deleted_polls)} polls with missing messages")
        else:
            logger.info(
                "✅ MESSAGE CLEANUP - No polls with missing messages found")

    except Exception as e:
        logger.error(
            f"❌ MESSAGE CLEANUP - Critical error during message cleanup: {e}")
        logger.exception("Full traceback for message cleanup error:")
        db.rollback()
        await notify_error_async(e, "Message Cleanup Critical Error")
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

    # Debug scheduler status
    if not scheduler:
        logger.error("❌ SCHEDULER RESTORE - Scheduler instance is None")
        return

    if not scheduler.running:
        logger.error("❌ SCHEDULER RESTORE - Scheduler is not running")
        return

    logger.debug(
        f"✅ SCHEDULER RESTORE - Scheduler is running, state: {scheduler.state}")

    # Debug bot status
    from .discord_bot import get_bot_instance
    bot = get_bot_instance()
    if not bot:
        logger.error("❌ SCHEDULER RESTORE - Bot instance is None")
        return

    if not bot.is_ready():
        logger.warning(
            "⚠️ SCHEDULER RESTORE - Bot is not ready yet, jobs may fail")
    else:
        logger.debug(f"✅ SCHEDULER RESTORE - Bot is ready: {bot.user}")

    db = get_db_session()
    try:
        # Get all scheduled polls with debugging
        logger.debug(
            "🔍 SCHEDULER RESTORE - Querying database for scheduled polls")
        scheduled_polls = db.query(Poll).filter(
            Poll.status == "scheduled").all()
        logger.info(
            f"📊 SCHEDULER RESTORE - Found {len(scheduled_polls)} scheduled polls to restore")

        if not scheduled_polls:
            logger.info(
                "✅ SCHEDULER RESTORE - No scheduled polls found, restoration complete")
            return

        # Get current time for comparison
        now = datetime.now(pytz.UTC)
        logger.debug(f"⏰ SCHEDULER RESTORE - Current time: {now}")

        # Process each scheduled poll
        restored_count = 0
        immediate_closes = 0

        for poll in scheduled_polls:
            try:
                poll_id = TypeSafeColumn.get_int(poll, 'id')
                poll_name = TypeSafeColumn.get_string(poll, 'name', 'Unknown')

                logger.info(
                    f"🔄 SCHEDULER RESTORE - Processing poll {poll_id}: '{poll_name}'")
                logger.debug(
                    f"Poll {poll_id} details: open_time={poll.open_time}, close_time={poll.close_time}, status={poll.status}")

                # All polls should be scheduled only - no immediate posting during restore
                # Schedule poll to open at its designated time
                time_until_open = (poll.open_time - now).total_seconds()

                if poll.open_time <= now:
                    logger.info(
                        f"📅 SCHEDULER RESTORE - Poll {poll_id} is overdue by {abs(time_until_open):.0f} seconds, scheduling for immediate posting")
                else:
                    logger.info(
                        f"📅 SCHEDULER RESTORE - Scheduling poll {poll_id} to open in {time_until_open:.0f} seconds at {poll.open_time}")

                # Use timezone-aware scheduler for restoration
                tz_scheduler = TimezoneAwareScheduler(scheduler)
                poll_timezone = TypeSafeColumn.get_string(
                    poll, 'timezone', 'UTC')

                # Schedule poll opening
                success_open = tz_scheduler.schedule_poll_opening(
                    poll_id, poll.open_time, poll_timezone, post_poll_to_channel, bot
                )
                if success_open:
                    logger.debug(
                        f"✅ SCHEDULER RESTORE - Scheduled opening job for poll {poll_id}")
                else:
                    logger.error(
                        f"❌ SCHEDULER RESTORE - Failed to schedule opening for poll {poll_id}")

                # Always schedule poll to close (whether it's active or scheduled)
                if poll.close_time > now:
                    time_until_close = (poll.close_time - now).total_seconds()
                    logger.debug(
                        f"📅 SCHEDULER RESTORE - Scheduling poll {poll_id} to close in {time_until_close:.0f} seconds at {poll.close_time}")

                    success_close = tz_scheduler.schedule_poll_closing(
                        poll_id, poll.close_time, poll_timezone, close_poll
                    )
                    if success_close:
                        logger.debug(
                            f"✅ SCHEDULER RESTORE - Scheduled closing job for poll {poll_id}")
                    else:
                        logger.error(
                            f"❌ SCHEDULER RESTORE - Failed to schedule closing for poll {poll_id}")
                else:
                    # Poll should have already closed
                    time_overdue = (now - poll.close_time).total_seconds()
                    logger.warning(
                        f"⏰ SCHEDULER RESTORE - Poll {poll_id} close time is {time_overdue:.0f} seconds overdue, closing now")

                    try:
                        await close_poll(poll_id)
                        immediate_closes += 1
                        logger.info(
                            f"✅ SCHEDULER RESTORE - Successfully closed overdue poll {poll_id}")
                    except Exception as close_exc:
                        logger.error(
                            f"❌ SCHEDULER RESTORE - Exception closing poll {poll_id}: {close_exc}")
                        logger.exception(
                            f"Full traceback for poll {poll_id} closing:")

                restored_count += 1
                logger.debug(
                    f"✅ SCHEDULER RESTORE - Completed processing poll {poll_id}")

            except Exception as e:
                poll_id = TypeSafeColumn.get_int(poll, 'id', 0) if poll else 0
                logger.error(
                    f"❌ SCHEDULER RESTORE - Error processing poll {poll_id}: {e}")
                logger.exception(
                    f"Full traceback for poll {poll_id} restoration error:")

        # Log final restoration summary
        logger.info("🎉 SCHEDULER RESTORE - Restoration complete!")
        logger.info(
            f"📊 SCHEDULER RESTORE - Summary: {restored_count}/{len(scheduled_polls)} polls processed")
        logger.info(
            f"📊 SCHEDULER RESTORE - Immediate actions: {immediate_closes} closed")

        # Debug current scheduler jobs
        current_jobs = scheduler.get_jobs()
        logger.info(
            f"📊 SCHEDULER RESTORE - Total active jobs after restoration: {len(current_jobs)}")
        for job in current_jobs:
            logger.debug(
                f"Active job: {job.id} - next run: {job.next_run_time}")

    except Exception as e:
        logger.error(
            f"❌ SCHEDULER RESTORE - Critical error during restoration: {e}")
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
                active_polls = db.query(Poll).filter(
                    Poll.status == "active").all()

                for poll in active_polls:
                    try:
                        poll_message_id = TypeSafeColumn.get_string(
                            poll, 'message_id')
                        if not poll_message_id:
                            continue

                        # Get the Discord message
                        try:
                            poll_channel_id = TypeSafeColumn.get_string(
                                poll, 'channel_id')
                            channel = bot.get_channel(int(poll_channel_id))
                            if not channel:
                                continue
                        except Exception as channel_error:
                            poll_id = TypeSafeColumn.get_int(poll, 'id')
                            logger.error(
                                f"❌ Safeguard: Error getting channel {poll_channel_id} for poll {poll_id}: {channel_error}")
                            await notify_error_async(channel_error, "Safeguard Channel Access",
                                                     poll_id=poll_id, channel_id=poll_channel_id)
                            continue

                        try:
                            if isinstance(channel, discord.TextChannel):
                                message = await channel.fetch_message(int(poll_message_id))
                            else:
                                # Skip non-text channels
                                continue
                        except Exception as fetch_error:
                            poll_id = TypeSafeColumn.get_int(poll, 'id')
                            logger.error(
                                f"❌ Safeguard: Error fetching message {poll_message_id} for poll {poll_id}: {fetch_error}")
                            await notify_error_async(fetch_error, "Safeguard Message Fetch",
                                                     poll_id=poll_id, message_id=poll_message_id)
                            continue

                        # Check each reaction on the message
                        for reaction in message.reactions:
                            try:
                                if str(reaction.emoji) not in POLL_EMOJIS:
                                    continue

                                option_index = POLL_EMOJIS.index(
                                    str(reaction.emoji))
                                if option_index >= len(poll.options):
                                    continue

                                # Get users who reacted (excluding the bot)
                                try:
                                    async for user in reaction.users():
                                        if user.bot:
                                            continue

                                        try:
                                            poll_id = TypeSafeColumn.get_int(
                                                poll, 'id')
                                            # Check if this user's vote is already recorded
                                            existing_vote = db.query(Vote).filter(
                                                Vote.poll_id == poll_id,
                                                Vote.user_id == str(user.id)
                                            ).first()

                                            if existing_vote:
                                                # Vote exists, remove the reaction (cleanup)
                                                try:
                                                    await reaction.remove(user)
                                                    logger.debug(
                                                        f"🧹 Safeguard: Cleaned up reaction from user {user.id} on poll {poll_id} (vote already recorded)")
                                                except Exception as remove_error:
                                                    logger.debug(
                                                        f"⚠️ Safeguard: Failed to remove reaction from user {user.id}: {remove_error}")
                                            else:
                                                # No vote recorded, process the vote
                                                logger.info(
                                                    f"🛡️ Safeguard: Processing missed reaction from user {user.id} on poll {poll_id}")

                                                try:
                                                    # Use bulletproof vote collection
                                                    bulletproof_ops = BulletproofPollOperations(
                                                        bot)
                                                    result = await bulletproof_ops.bulletproof_vote_collection(
                                                        poll_id, str(
                                                            user.id), option_index
                                                    )

                                                    if result["success"]:
                                                        # Vote was successfully recorded - NOW remove the reaction
                                                        try:
                                                            await reaction.remove(user)
                                                            logger.info(
                                                                f"✅ Safeguard: Vote recorded and reaction removed for user {user.id} on poll {poll_id}")
                                                        except Exception as remove_error:
                                                            logger.warning(
                                                                f"⚠️ Safeguard: Vote recorded but failed to remove reaction from user {user.id}: {remove_error}")

                                                        # Update poll embed for live updates
                                                        try:
                                                            await update_poll_message(bot, poll)
                                                            logger.debug(
                                                                f"✅ Safeguard: Poll message updated for poll {poll_id}")
                                                        except Exception as update_error:
                                                            logger.error(
                                                                f"❌ Safeguard: Failed to update poll message for poll {poll_id}: {update_error}")
                                                            await notify_error_async(update_error, "Safeguard Poll Message Update",
                                                                                     poll_id=poll_id, user_id=str(user.id))
                                                    else:
                                                        # Vote failed - leave reaction for user to try again
                                                        logger.error(
                                                            f"❌ Safeguard: Vote FAILED for user {user.id} on poll {poll_id}: {result['error']}")
                                                        await notify_error_async(Exception(result['error']), "Safeguard Vote Processing Failed",
                                                                                 poll_id=poll_id, user_id=str(user.id), option_index=option_index)

                                                except Exception as vote_error:
                                                    logger.error(
                                                        f"❌ Safeguard: Critical error processing vote for user {user.id} on poll {poll_id}: {vote_error}")
                                                    await notify_error_async(vote_error, "Safeguard Vote Processing Critical Error",
                                                                             poll_id=poll_id, user_id=str(user.id), option_index=option_index)

                                        except Exception as user_error:
                                            poll_id = TypeSafeColumn.get_int(
                                                poll, 'id')
                                            logger.error(
                                                f"❌ Safeguard: Error processing user {user.id} reaction on poll {poll_id}: {user_error}")
                                            await notify_error_async(user_error, "Safeguard User Processing Error",
                                                                     poll_id=poll_id, user_id=str(user.id))
                                            continue

                                except Exception as users_error:
                                    poll_id = TypeSafeColumn.get_int(
                                        poll, 'id')
                                    logger.error(
                                        f"❌ Safeguard: Error iterating reaction users for poll {poll_id}: {users_error}")
                                    await notify_error_async(users_error, "Safeguard Reaction Users Iteration",
                                                             poll_id=poll_id, emoji=str(reaction.emoji))
                                    continue

                            except Exception as reaction_error:
                                poll_id = TypeSafeColumn.get_int(poll, 'id')
                                logger.error(
                                    f"❌ Safeguard: Error processing reaction {reaction.emoji} on poll {poll_id}: {reaction_error}")
                                await notify_error_async(reaction_error, "Safeguard Reaction Processing",
                                                         poll_id=poll_id, emoji=str(reaction.emoji))
                                continue

                    except Exception as poll_error:
                        poll_id = TypeSafeColumn.get_int(poll, 'id')
                        logger.error(
                            f"❌ Safeguard: Error processing poll {poll_id}: {poll_error}")
                        await notify_error_async(poll_error, "Safeguard Poll Processing", poll_id=poll_id)
                        continue

            except Exception as db_error:
                logger.error(f"❌ Safeguard: Database error: {db_error}")
                await notify_error_async(db_error, "Safeguard Database Error")
            finally:
                try:
                    db.close()
                except Exception as close_error:
                    logger.error(
                        f"❌ Safeguard: Error closing database: {close_error}")
                    await notify_error_async(close_error, "Safeguard Database Close Error")

        except Exception as e:
            logger.error(
                f"❌ Safeguard: Critical error in reaction safeguard task: {e}")
            await notify_error_async(e, "Safeguard Task Critical Error")
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
        await notify_error_async(e, "Safeguard Task Startup Error")
        raise e  # Re-raise to ensure the application knows the safeguard failed to start


def get_scheduler():
    """Get the scheduler instance"""
    return scheduler
