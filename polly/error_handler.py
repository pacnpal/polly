"""
Polly Error Handling and Recovery System
Comprehensive error handling, logging, and recovery mechanisms for bulletproof operation.
"""

import logging
import asyncio
import os
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable
from functools import wraps
import pytz
import discord
from discord.ext import commands

from .database import get_db_session, Poll, Vote
from .validators import ValidationError

logger = logging.getLogger(__name__)


class BotOwnerLogHandler(logging.Handler):
    """Custom logging handler that automatically notifies bot owner for WARNING+ level logs"""
    
    def __init__(self, level=logging.WARNING):
        super().__init__(level)
        self.bot = None
        self._notification_queue = asyncio.Queue() if hasattr(asyncio, 'Queue') else None
        self._processing_task = None
        
    def set_bot(self, bot: commands.Bot):
        """Set the bot instance for notifications"""
        self.bot = bot
        # Start processing task if not already running
        if self._notification_queue and not self._processing_task:
            try:
                loop = asyncio.get_event_loop()
                self._processing_task = loop.create_task(self._process_notifications())
            except RuntimeError:
                # No event loop running yet, will be started later
                pass
    
    def emit(self, record: logging.LogRecord):
        """Handle log record and queue notification if needed"""
        if not self.bot or not self._notification_queue:
            return
            
        # Skip if this is already a notification-related log to prevent recursion
        if 'bot owner notification' in record.getMessage().lower():
            return
            
        # Only process WARNING and above
        if record.levelno < logging.WARNING:
            return
            
        try:
            # Queue the notification for async processing
            self._notification_queue.put_nowait({
                'level': record.levelname,
                'message': record.getMessage(),
                'module': record.module,
                'funcName': record.funcName,
                'lineno': record.lineno,
                'timestamp': datetime.fromtimestamp(record.created, tz=pytz.UTC),
                'exc_info': record.exc_info
            })
        except Exception:
            # Don't let logging errors crash the application
            pass
    
    async def _process_notifications(self):
        """Process queued notifications asynchronously"""
        while True:
            try:
                if not self._notification_queue:
                    await asyncio.sleep(1)
                    continue
                    
                # Wait for notification with timeout
                try:
                    notification = await asyncio.wait_for(
                        self._notification_queue.get(), 
                        timeout=5.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                # Send notification to bot owner
                await self._send_log_notification(notification)
                
            except Exception as e:
                # Don't let notification errors crash the processing loop
                print(f"Error in log notification processing: {e}")
                await asyncio.sleep(1)
    
    async def _send_log_notification(self, notification: Dict[str, Any]):
        """Send log notification to bot owner"""
        try:
            if not self.bot or not self.bot.is_ready():
                return
                
            bot_owner_id = get_bot_owner_id()
            if not bot_owner_id:
                return
                
            owner = await self.bot.fetch_user(int(bot_owner_id))
            if not owner:
                return
            
            # Determine color based on log level
            level = notification['level']
            if level == 'CRITICAL':
                color = 0xFF0000  # Red
                emoji = "🚨"
            elif level == 'ERROR':
                color = 0xFF4500  # Orange Red
                emoji = "❌"
            elif level == 'WARNING':
                color = 0xFFA500  # Orange
                emoji = "⚠️"
            else:
                color = 0x808080  # Gray
                emoji = "ℹ️"
            
            # Create embed
            embed = discord.Embed(
                title=f"{emoji} {level} Log Alert",
                description=notification['message'][:2000],  # Discord limit
                color=color,
                timestamp=notification['timestamp']
            )
            
            embed.add_field(
                name="Location",
                value=f"**Module:** {notification['module']}\n**Function:** {notification['funcName']}\n**Line:** {notification['lineno']}",
                inline=False
            )
            
            # Add exception info if available
            if notification['exc_info']:
                exc_type, exc_value, exc_traceback = notification['exc_info']
                if exc_type and exc_value:
                    import traceback
                    # Get full traceback
                    tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
                    full_traceback = ''.join(tb_lines)
                    
                    embed.add_field(
                        name="Exception",
                        value=f"**Type:** {exc_type.__name__}\n**Details:** {str(exc_value)[:500]}",
                        inline=False
                    )
                    
                    # Add full traceback (truncated if too long for Discord)
                    if len(full_traceback) > 1024:
                        traceback_preview = full_traceback[:1000] + "\n... (truncated)"
                    else:
                        traceback_preview = full_traceback
                    
                    embed.add_field(
                        name="Full Traceback",
                        value=f"```python\n{traceback_preview}\n```",
                        inline=False
                    )
            
            embed.set_footer(text="Polly Auto-Log Monitor")
            
            # Send DM with retry logic
            for attempt in range(2):
                try:
                    await owner.send(embed=embed)
                    break
                except discord.Forbidden:
                    # Bot owner has DMs disabled
                    break
                except discord.HTTPException:
                    if attempt == 1:
                        break
                    await asyncio.sleep(1)
                    
        except Exception:
            # Don't let notification errors crash anything
            pass


# Global log handler instance
_bot_owner_log_handler = None


def setup_automatic_bot_owner_notifications():
    """Set up automatic bot owner notifications for WARNING+ level logs"""
    global _bot_owner_log_handler
    
    if _bot_owner_log_handler:
        return _bot_owner_log_handler
    
    # Create and configure the handler
    _bot_owner_log_handler = BotOwnerLogHandler(level=logging.WARNING)
    
    # Add to root logger to catch all WARNING+ logs
    root_logger = logging.getLogger()
    root_logger.addHandler(_bot_owner_log_handler)
    
    # Also add to polly-specific loggers
    polly_logger = logging.getLogger('polly')
    polly_logger.addHandler(_bot_owner_log_handler)
    
    return _bot_owner_log_handler


def set_bot_for_automatic_notifications(bot: commands.Bot):
    """Set the bot instance for automatic notifications"""
    global _bot_owner_log_handler
    
    if not _bot_owner_log_handler:
        _bot_owner_log_handler = setup_automatic_bot_owner_notifications()
    
    _bot_owner_log_handler.set_bot(bot)
    
    # Start processing task if we have an event loop
    try:
        if not _bot_owner_log_handler._processing_task:
            loop = asyncio.get_event_loop()
            _bot_owner_log_handler._processing_task = loop.create_task(
                _bot_owner_log_handler._process_notifications()
            )
    except RuntimeError:
        # No event loop yet, will be started when bot is ready
        pass


def get_automatic_notification_handler():
    """Get the automatic notification handler instance"""
    global _bot_owner_log_handler
    return _bot_owner_log_handler

# Get bot owner ID from environment (loaded dynamically to ensure .env is loaded)


def get_bot_owner_id():
    """Get BOT_OWNER_ID from environment, ensuring .env is loaded"""
    return os.getenv("BOT_OWNER_ID")


class BotOwnerNotifier:
    """Handle DM notifications to bot owner on critical errors"""

    @staticmethod
    async def send_error_dm(bot: commands.Bot, error: Exception, operation: str, context: Optional[Dict[str, Any]] = None):
        """Send DM to bot owner about critical errors"""
        bot_owner_id = get_bot_owner_id()
        if not bot_owner_id or not bot or not bot.is_ready():
            logger.warning(
                "Cannot send bot owner DM: BOT_OWNER_ID not set or bot not ready")
            return False

        try:
            owner_id = int(bot_owner_id)
            owner = await bot.fetch_user(owner_id)

            if not owner:
                logger.error(f"Could not fetch bot owner with ID: {owner_id}")
                return False

            # Create error embed
            embed = discord.Embed(
                title="🚨 Critical Error Alert",
                description=f"**Operation:** {operation}\n**Error:** {str(error)[:1000]}",
                color=0xFF0000,
                timestamp=datetime.now(pytz.UTC)
            )

            embed.add_field(
                name="Error Type",
                value=type(error).__name__,
                inline=True
            )

            if context:
                context_str = "\n".join(
                    [f"**{k}:** {v}" for k, v in context.items() if v is not None])
                if context_str:
                    embed.add_field(
                        name="Context",
                        value=context_str[:1024],
                        inline=False
                    )

            embed.set_footer(text="Polly Bot Error System")

            # Send DM with retry logic
            for attempt in range(3):
                try:
                    await owner.send(embed=embed)
                    logger.info(
                        f"Successfully sent error DM to bot owner for operation: {operation}")
                    return True
                except discord.Forbidden:
                    logger.error(
                        "Bot owner has DMs disabled or blocked the bot")
                    return False
                except discord.HTTPException as e:
                    if attempt == 2:
                        logger.error(
                            f"Failed to send DM after 3 attempts: {e}")
                        return False
                    await asyncio.sleep(2 ** attempt)

        except ValueError:
            logger.error(f"Invalid BOT_OWNER_ID format: {bot_owner_id}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending bot owner DM: {e}")
            return False

        return False

    @staticmethod
    async def send_system_status_dm(bot: commands.Bot, status: str, details: Optional[Dict[str, Any]] = None):
        """Send system status updates to bot owner"""
        bot_owner_id = get_bot_owner_id()
        if not bot_owner_id or not bot or not bot.is_ready():
            return False

        try:
            owner_id = int(bot_owner_id)
            owner = await bot.fetch_user(owner_id)

            if not owner:
                return False

            color = 0x00FF00 if "healthy" in status.lower(
            ) or "recovered" in status.lower() else 0xFFAA00

            embed = discord.Embed(
                title="📊 System Status Update",
                description=status,
                color=color,
                timestamp=datetime.now(pytz.UTC)
            )

            if details:
                for key, value in details.items():
                    embed.add_field(
                        name=key.replace("_", " ").title(),
                        value=str(value)[:1024],
                        inline=True
                    )

            embed.set_footer(text="Polly Bot Status System")

            await owner.send(embed=embed)
            logger.info(f"Sent system status DM to bot owner: {status}")
            return True

        except Exception as e:
            logger.error(f"Error sending system status DM: {e}")
            return False


class PollError(Exception):
    """Base exception for poll-related errors"""

    def __init__(self, message: str, poll_id: Optional[int] = None, recoverable: bool = True):
        self.message = message
        self.poll_id = poll_id
        self.recoverable = recoverable
        super().__init__(message)


class DiscordError(PollError):
    """Discord-specific errors"""
    pass


class DatabaseError(PollError):
    """Database-specific errors"""
    pass


class SchedulerError(PollError):
    """Scheduler-specific errors"""
    pass


class ErrorRecovery:
    """Error recovery and retry mechanisms"""

    MAX_RETRIES = 3
    RETRY_DELAYS = [1, 5, 15]  # seconds

    @staticmethod
    async def retry_with_backoff(func: Callable, *args, max_retries: Optional[int] = None, **kwargs) -> Any:
        """Retry function with exponential backoff"""
        max_retries = max_retries or ErrorRecovery.MAX_RETRIES

        for attempt in range(max_retries):
            try:
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(
                        f"Final retry failed for {func.__name__}: {e}")
                    raise

                delay = ErrorRecovery.RETRY_DELAYS[min(
                    attempt, len(ErrorRecovery.RETRY_DELAYS) - 1)]
                logger.warning(
                    f"Retry {attempt + 1}/{max_retries} for {func.__name__} failed: {e}. Retrying in {delay}s...")
                await asyncio.sleep(delay)

        raise Exception(f"All retries exhausted for {func.__name__}")

    @staticmethod
    def safe_database_operation(operation_name: str):
        """Decorator for safe database operations with automatic rollback"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                db = get_db_session()
                try:
                    result = func(db, *args, **kwargs)
                    db.commit()
                    logger.debug(
                        f"Database operation '{operation_name}' completed successfully")
                    return result
                except Exception as e:
                    db.rollback()
                    logger.error(
                        f"Database operation '{operation_name}' failed: {e}")
                    logger.exception(f"Full traceback for {operation_name}:")
                    raise DatabaseError(f"Database operation failed: {str(e)}")
                finally:
                    db.close()
            return wrapper
        return decorator

    @staticmethod
    def safe_async_database_operation(operation_name: str):
        """Decorator for safe async database operations with automatic rollback"""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                db = get_db_session()
                try:
                    result = await func(db, *args, **kwargs)
                    db.commit()
                    logger.debug(
                        f"Async database operation '{operation_name}' completed successfully")
                    return result
                except Exception as e:
                    db.rollback()
                    logger.error(
                        f"Async database operation '{operation_name}' failed: {e}")
                    logger.exception(f"Full traceback for {operation_name}:")
                    raise DatabaseError(f"Database operation failed: {str(e)}")
                finally:
                    db.close()
            return wrapper
        return decorator


class PollErrorHandler:
    """Centralized error handling for poll operations"""

    @staticmethod
    async def handle_poll_creation_error(e: Exception, poll_data: Dict[str, Any], bot: Optional[commands.Bot] = None) -> str:
        """Handle poll creation errors with user-friendly messages and bot owner notifications"""
        poll_name = poll_data.get('name', 'Unknown')
        context = {
            "poll_name": poll_name,
            "server_id": poll_data.get('server_id'),
            "channel_id": poll_data.get('channel_id'),
            "user_id": poll_data.get('user_id')
        }

        if isinstance(e, ValidationError):
            logger.warning(
                f"Validation error creating poll '{poll_name}': {e.message}")
            return f"❌ {e.message}"

        # Critical errors that need bot owner notification
        if isinstance(e, discord.Forbidden):
            logger.error(
                f"Discord permission error creating poll '{poll_name}': {e}")
            if bot:
                await BotOwnerNotifier.send_error_dm(bot, e, "Poll Creation - Permission Error", context)
            return "❌ Bot lacks permissions in the selected channel. Please check bot permissions."

        if isinstance(e, discord.HTTPException):
            logger.error(f"Discord API error creating poll '{poll_name}': {e}")
            if bot:
                await BotOwnerNotifier.send_error_dm(bot, e, "Poll Creation - Discord API Error", context)
            return "❌ Discord API error. Please try again in a moment."

        if isinstance(e, DatabaseError):
            logger.error(f"Database error creating poll '{poll_name}': {e}")
            if bot:
                await BotOwnerNotifier.send_error_dm(bot, e, "Poll Creation - Database Error", context)
            return "❌ Database error. Please try again."

        # Unexpected errors always notify bot owner
        logger.error(f"Unexpected error creating poll '{poll_name}': {e}")
        logger.exception("Full traceback for poll creation error:")
        if bot:
            await BotOwnerNotifier.send_error_dm(bot, e, "Poll Creation - Unexpected Error", context)
        return "❌ An unexpected error occurred. Please try again."

    @staticmethod
    async def handle_vote_error(e: Exception, poll_id: int, user_id: str, bot: Optional[commands.Bot] = None) -> str:
        """Handle voting errors with user-friendly messages and bot owner notifications"""
        context = {
            "poll_id": poll_id,
            "user_id": user_id
        }

        if isinstance(e, ValidationError):
            logger.warning(
                f"Validation error voting on poll {poll_id} by user {user_id}: {e.message}")
            return f"❌ {e.message}"

        if isinstance(e, DatabaseError):
            logger.error(
                f"Database error voting on poll {poll_id} by user {user_id}: {e}")
            if bot:
                await BotOwnerNotifier.send_error_dm(bot, e, "Voting - Database Error", context)
            return "❌ Database error processing vote. Please try again."

        # Unexpected voting errors notify bot owner
        logger.error(
            f"Unexpected error voting on poll {poll_id} by user {user_id}: {e}")
        logger.exception("Full traceback for voting error:")
        if bot:
            await BotOwnerNotifier.send_error_dm(bot, e, "Voting - Unexpected Error", context)
        return "❌ An unexpected error occurred while voting. Please try again."

    @staticmethod
    async def handle_poll_closure_error(e: Exception, poll_id: int, bot: Optional[commands.Bot] = None) -> str:
        """Handle poll closure errors with user-friendly messages and bot owner notifications"""
        context = {
            "poll_id": poll_id
        }

        if isinstance(e, ValidationError):
            logger.warning(
                f"Validation error closing poll {poll_id}: {e.message}")
            return f"❌ {e.message}"

        if isinstance(e, DatabaseError):
            logger.error(f"Database error closing poll {poll_id}: {e}")
            if bot:
                await BotOwnerNotifier.send_error_dm(bot, e, "Poll Closure - Database Error", context)
            return "❌ Database error closing poll. Please try again."

        if isinstance(e, discord.Forbidden):
            logger.error(
                f"Discord permission error closing poll {poll_id}: {e}")
            if bot:
                await BotOwnerNotifier.send_error_dm(bot, e, "Poll Closure - Permission Error", context)
            return "❌ Bot lacks permissions to close poll in the channel."

        if isinstance(e, discord.HTTPException):
            logger.error(f"Discord API error closing poll {poll_id}: {e}")
            if bot:
                await BotOwnerNotifier.send_error_dm(bot, e, "Poll Closure - Discord API Error", context)
            return "❌ Discord API error closing poll. Please try again."

        # Unexpected closure errors notify bot owner
        logger.error(f"Unexpected error closing poll {poll_id}: {e}")
        logger.exception("Full traceback for poll closure error:")
        if bot:
            await BotOwnerNotifier.send_error_dm(bot, e, "Poll Closure - Unexpected Error", context)
        return "❌ An unexpected error occurred while closing poll. Please try again."

    @staticmethod
    async def handle_scheduler_error(e: Exception, poll_id: int, operation: str, bot: Optional[commands.Bot] = None) -> bool:
        """Handle scheduler errors and attempt recovery with bot owner notifications"""
        context = {
            "poll_id": poll_id,
            "operation": operation
        }

        logger.error(
            f"Scheduler error for poll {poll_id} during {operation}: {e}")
        logger.exception("Full traceback for scheduler error:")

        # Always notify bot owner of scheduler errors as they're critical
        if bot:
            await BotOwnerNotifier.send_error_dm(bot, e, f"Scheduler Error - {operation}", context)

        # Attempt to recover by rescheduling
        try:
            from .background_tasks import get_scheduler
            scheduler = get_scheduler()
            if scheduler and scheduler.running:
                # Remove any existing jobs for this poll
                for job_type in ['open', 'close']:
                    job_id = f"{job_type}_poll_{poll_id}"
                    try:
                        scheduler.remove_job(job_id)
                        logger.info(
                            f"Removed existing job {job_id} during error recovery")
                    except Exception:
                        pass  # Job might not exist

                # Try to reschedule based on poll status
                db = get_db_session()
                try:
                    poll = db.query(Poll).filter(Poll.id == poll_id).first()
                    if poll:
                        now = datetime.now(pytz.UTC)

                        # Reschedule opening if needed
                        poll_open_time = getattr(poll, 'open_time', None)
                        if str(poll.status) == "scheduled" and poll_open_time and poll_open_time > now:
                            from .discord_utils import post_poll_to_channel
                            from .discord_bot import get_bot_instance
                            from apscheduler.triggers.date import DateTrigger

                            main_bot = get_bot_instance()
                            scheduler.add_job(
                                post_poll_to_channel,
                                DateTrigger(run_date=poll.open_time),
                                args=[main_bot, poll],
                                id=f"open_poll_{poll.id}",
                                replace_existing=True
                            )
                            logger.info(
                                f"Rescheduled opening for poll {poll_id}")

                        # Reschedule closing if needed
                        poll_close_time = getattr(poll, 'close_time', None)
                        if str(poll.status) in ["scheduled", "active"] and poll_close_time is not None and poll_close_time > now:
                            from .background_tasks import close_poll
                            from apscheduler.triggers.date import DateTrigger

                            scheduler.add_job(
                                close_poll,
                                DateTrigger(run_date=poll.close_time),
                                args=[poll.id],
                                id=f"close_poll_{poll.id}",
                                replace_existing=True
                            )
                            logger.info(
                                f"Rescheduled closing for poll {poll_id}")

                        # Notify bot owner of successful recovery
                        if bot:
                            await BotOwnerNotifier.send_system_status_dm(
                                bot,
                                f"✅ Scheduler recovered for poll {poll_id}",
                                {"operation": operation,
                                    "poll_status": str(poll.status)}
                            )
                        return True
                finally:
                    db.close()
        except Exception as recovery_error:
            logger.error(
                f"Failed to recover from scheduler error for poll {poll_id}: {recovery_error}")
            # Notify bot owner of failed recovery
            if bot:
                await BotOwnerNotifier.send_error_dm(
                    bot,
                    recovery_error,
                    f"Scheduler Recovery Failed - {operation}",
                    {"poll_id": poll_id, "original_error": str(e)}
                )

        return False


class DiscordErrorHandler:
    """Specialized error handling for Discord operations"""

    @staticmethod
    async def safe_send_message(channel, content=None, embed=None, max_retries: int = 3) -> Optional[discord.Message]:
        """Safely send a Discord message with retries"""
        for attempt in range(max_retries):
            try:
                if embed:
                    return await channel.send(content=content, embed=embed)
                else:
                    return await channel.send(content=content)
            except discord.Forbidden:
                logger.error(
                    f"No permission to send message in channel {channel.id}")
                return None
            except discord.HTTPException as e:
                if attempt == max_retries - 1:
                    logger.error(
                        f"Failed to send message after {max_retries} attempts: {e}")
                    return None

                delay = 2 ** attempt  # Exponential backoff
                logger.warning(
                    f"HTTP error sending message (attempt {attempt + 1}): {e}. Retrying in {delay}s...")
                await asyncio.sleep(delay)
            except Exception as e:
                logger.error(f"Unexpected error sending message: {e}")
                return None

        return None

    @staticmethod
    async def safe_add_reactions(message: discord.Message, emojis: List[str], bot: Optional[commands.Bot] = None) -> List[str]:
        """Safely add reactions to a message, returning list of successfully added emojis"""
        successful_reactions = []

        # Import emoji handler for Unicode emoji preparation
        from .discord_emoji_handler import DiscordEmojiHandler
        emoji_handler = DiscordEmojiHandler(bot) if bot else None

        for emoji in emojis:
            try:
                # Prepare emoji for reaction if we have a bot instance
                prepared_emoji = emoji_handler.prepare_emoji_for_reaction(emoji) if emoji_handler else emoji
                
                await message.add_reaction(prepared_emoji)
                successful_reactions.append(prepared_emoji)
                logger.debug(f"Successfully added reaction {prepared_emoji} (original: {emoji})")
            except discord.Forbidden:
                logger.error(f"No permission to add reaction {emoji}")
                break  # If we can't add one, we likely can't add any
            except discord.HTTPException as e:
                logger.warning(f"Failed to add reaction {emoji}: {e}")
                # Continue trying other reactions
            except Exception as e:
                logger.error(f"Unexpected error adding reaction {emoji}: {e}")

        return successful_reactions

    @staticmethod
    async def safe_edit_message(message: discord.Message, content=None, embed=None, max_retries: int = 3) -> bool:
        """Safely edit a Discord message with retries"""
        for attempt in range(max_retries):
            try:
                if embed:
                    await message.edit(content=content, embed=embed)
                else:
                    await message.edit(content=content)
                return True
            except discord.NotFound:
                logger.warning(f"Message {message.id} not found for editing")
                return False
            except discord.Forbidden:
                logger.error(f"No permission to edit message {message.id}")
                return False
            except discord.HTTPException as e:
                if attempt == max_retries - 1:
                    logger.error(
                        f"Failed to edit message after {max_retries} attempts: {e}")
                    return False

                delay = 2 ** attempt
                logger.warning(
                    f"HTTP error editing message (attempt {attempt + 1}): {e}. Retrying in {delay}s...")
                await asyncio.sleep(delay)
            except Exception as e:
                logger.error(f"Unexpected error editing message: {e}")
                return False

        return False


class DatabaseHealthChecker:
    """Database health monitoring and recovery"""

    @staticmethod
    def check_database_health() -> bool:
        """Check if database is accessible and healthy"""
        try:
            db = get_db_session()
            # Simple query to test connectivity
            from sqlalchemy import text
            db.execute(text("SELECT 1"))
            db.close()
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False

    @staticmethod
    @ErrorRecovery.safe_database_operation("poll_integrity_check")
    def check_poll_integrity(db, poll_id: int) -> Dict[str, Any]:
        """Check poll data integrity and return status"""
        poll = db.query(Poll).filter(Poll.id == poll_id).first()
        if not poll:
            return {"valid": False, "error": "Poll not found"}

        issues = []

        # Check required fields
        if not str(getattr(poll, 'name', '')) or not str(getattr(poll, 'question', '')):
            issues.append("Missing name or question")

        if not poll.options or len(poll.options) < 2:
            issues.append("Invalid options")

        if not str(getattr(poll, 'server_id', '')) or not str(getattr(poll, 'channel_id', '')):
            issues.append("Missing server or channel ID")

        poll_open_time = getattr(poll, 'open_time', None)
        poll_close_time = getattr(poll, 'close_time', None)
        if poll_open_time is None or poll_close_time is None:
            issues.append("Missing timing information")
        elif poll_close_time <= poll_open_time:
            issues.append("Invalid time range")

        # Check vote integrity
        vote_count = db.query(Vote).filter(Vote.poll_id == poll_id).count()

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "vote_count": vote_count,
            "status": str(poll.status)
        }


class SystemHealthMonitor:
    """Overall system health monitoring"""

    @staticmethod
    async def check_bot_health(bot: commands.Bot) -> Dict[str, Any]:
        """Check Discord bot health"""
        health_status = {
            "bot_ready": bot.is_ready() if bot else False,
            "guild_count": len(bot.guilds) if bot and bot.guilds else 0,
            "latency": round(bot.latency * 1000, 2) if bot else None,
            "user": str(bot.user) if bot and bot.user else None
        }

        return health_status

    @staticmethod
    def check_scheduler_health(scheduler) -> Dict[str, Any]:
        """Check scheduler health"""
        if not scheduler:
            return {"running": False, "job_count": 0}

        return {
            "running": scheduler.running,
            "job_count": len(scheduler.get_jobs()),
            "state": str(scheduler.state)
        }

    @staticmethod
    async def full_system_health_check(bot: commands.Bot, scheduler) -> Dict[str, Any]:
        """Comprehensive system health check"""
        return {
            "timestamp": datetime.now(pytz.UTC).isoformat(),
            "database": DatabaseHealthChecker.check_database_health(),
            "bot": await SystemHealthMonitor.check_bot_health(bot),
            "scheduler": SystemHealthMonitor.check_scheduler_health(scheduler)
        }


def log_error_with_context(error: Exception, context: Dict[str, Any], operation: str):
    """Log error with comprehensive context information"""
    logger.error(f"Error in {operation}: {str(error)}")
    logger.error(f"Context: {context}")
    logger.exception(f"Full traceback for {operation}:")

    # Log additional system state if available
    try:
        logger.error(f"System time: {datetime.now(pytz.UTC)}")
        logger.error(f"Error type: {type(error).__name__}")
    except Exception:
        pass  # Don't let logging errors crash the system


async def handle_critical_error(error: Exception, operation: str, poll_id: Optional[int] = None, bot: Optional[commands.Bot] = None):
    """Handle critical errors that could crash the system"""
    context = {
        "operation": operation,
        "poll_id": poll_id,
        "timestamp": datetime.now(pytz.UTC).isoformat()
    }

    log_error_with_context(error, context, operation)

    # Send bot owner notification for critical errors
    if bot:
        await BotOwnerNotifier.send_error_dm(bot, error, f"Critical System Error - {operation}", context)

    # Could add additional critical error handling here:
    # - Create error reports
    # - Trigger recovery procedures

    return False  # Indicate operation failed


async def notify_bot_owner_of_error(error: Exception, operation: str, context: Optional[Dict[str, Any]] = None, bot: Optional[commands.Bot] = None):
    """Universal function to notify bot owner of ANY error in the application"""
    try:
        # Get bot instance if not provided
        if not bot:
            # Try to get bot from discord_bot module
            try:
                from .discord_bot import get_bot_instance
                bot = get_bot_instance()
            except ImportError:
                logger.warning(
                    "Could not import bot instance for error notification")
                return False

        # Prepare error context
        error_context = {
            "operation": operation,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "timestamp": datetime.now(pytz.UTC).isoformat()
        }

        # Add additional context if provided
        if context:
            error_context.update(context)

        # Send DM notification
        await BotOwnerNotifier.send_error_dm(
            bot, error, f"System Error - {operation}", error_context
        )

        logger.debug(f"Sent bot owner notification for error in {operation}")
        return True

    except Exception as notification_error:
        logger.error(
            f"Failed to send bot owner notification for {operation}: {notification_error}")
        return False


def notify_bot_owner_of_error_sync(error: Exception, operation: str, context: Optional[Dict[str, Any]] = None):
    """Synchronous wrapper for bot owner error notifications"""
    try:
        import asyncio

        # Try to get the current event loop
        try:
            loop = asyncio.get_running_loop()
            # If we're in an async context, schedule the notification
            loop.create_task(notify_bot_owner_of_error(
                error, operation, context))
        except RuntimeError:
            # No event loop running, create a new one
            asyncio.run(notify_bot_owner_of_error(error, operation, context))

        return True
    except Exception as e:
        logger.error(
            f"Failed to send sync bot owner notification for {operation}: {e}")
        return False


# EASY-TO-USE FUNCTIONS FOR EXISTING ERROR HANDLERS
def notify_error(error: Exception, operation: str, **context_kwargs):
    """
    SIMPLE FUNCTION TO ADD TO ANY EXISTING ERROR HANDLER

    Usage examples:

    # Basic usage:
    except Exception as e:
        logger.error(f"Something failed: {e}")
        notify_error(e, "Database Operation")

    # With context:
    except Exception as e:
        logger.error(f"Poll creation failed: {e}")
        notify_error(e, "Poll Creation", poll_id=123, user_id="456")

    # With any additional context:
    except Exception as e:
        logger.error(f"Image upload failed: {e}")
        notify_error(e, "Image Upload", file_size=1024, file_type="png")
    """
    try:
        context = context_kwargs if context_kwargs else None
        notify_bot_owner_of_error_sync(error, operation, context)
    except Exception:
        pass  # Never let notification errors crash the application


async def notify_error_async(error: Exception, operation: str, **context_kwargs):
    """
    SIMPLE ASYNC FUNCTION TO ADD TO ANY EXISTING ASYNC ERROR HANDLER

    Usage examples:

    # Basic usage:
    except Exception as e:
        logger.error(f"Something failed: {e}")
        await notify_error_async(e, "Discord Operation")

    # With context:
    except Exception as e:
        logger.error(f"Poll posting failed: {e}")
        await notify_error_async(e, "Poll Posting", poll_id=123, channel_id="456")
    """
    try:
        context = context_kwargs if context_kwargs else None
        await notify_bot_owner_of_error(error, operation, context)
    except Exception:
        pass  # Never let notification errors crash the application


# Decorator for critical operations
def critical_operation(operation_name: str):
    """Decorator for critical operations that must not crash the system"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                await handle_critical_error(e, operation_name)
                return None

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # For sync functions, we can't await, so we'll use asyncio.create_task
                # or just log the error without bot notification
                log_error_with_context(
                    e, {"operation": operation_name}, operation_name)
                return None

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator
