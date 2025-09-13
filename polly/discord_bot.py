"""
Polly Discord Bot
Discord bot setup and event handling functionality.
"""

from decouple import config
import os
import logging
import discord
from discord.ext import commands
try:
    from .database import get_db_session, Poll, POLL_EMOJIS, TypeSafeColumn
    from .discord_utils import update_poll_message
    from .error_handler import PollErrorHandler, setup_automatic_bot_owner_notifications, set_bot_for_automatic_notifications
except ImportError:
    ############### Temporary fix for import issues during testing ################
    import sys
    import pathlib
    current_dir = pathlib.Path(__file__).parent.resolve()
    sys.path.append(str(current_dir))
    ###############################################################################
    from database import get_db_session, Poll, POLL_EMOJIS, TypeSafeColumn  # type: ignore
    from discord_utils import update_poll_message  # type: ignore
    from error_handler import PollErrorHandler, setup_automatic_bot_owner_notifications, set_bot_for_automatic_notifications  # type: ignore

logger = logging.getLogger(__name__)

# Configuration
DISCORD_TOKEN = config("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN environment variable is required")

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.reactions = True

bot = commands.Bot(command_prefix=lambda bot, message: None, intents=intents)


@bot.event
async def on_ready():
    """Bot ready event"""
    logger.info(f"{bot.user} has connected to Discord!")

    # Initialize automatic bot owner notifications for WARNING+ level logs AFTER bot is ready
    try:
        setup_automatic_bot_owner_notifications()
        set_bot_for_automatic_notifications(bot)
        logger.info(
            "✅ Automatic bot owner notifications initialized for WARNING+ level logs"
        )
    except Exception as e:
        logger.error(f"Failed to initialize automatic bot owner notifications: {e}")

    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} command(s)")
    except Exception as e:
        # Removed manual notification - automatic system will handle this
        logger.error(f"Failed to sync commands: {e}")


@bot.event
async def on_guild_role_create(role):
    """Handle guild role creation - invalidate role cache"""
    try:
        from .enhanced_cache_service import get_enhanced_cache_service
        cache_service = get_enhanced_cache_service()
        
        invalidated = await cache_service.invalidate_guild_roles_cache(str(role.guild.id))
        logger.info(f"Role '{role.name}' created in guild {role.guild.name} - invalidated {invalidated} cache entries")
    except Exception as e:
        logger.warning(f"Error invalidating role cache after role creation: {e}")


@bot.event
async def on_guild_role_delete(role):
    """Handle guild role deletion - invalidate role cache"""
    try:
        from .enhanced_cache_service import get_enhanced_cache_service
        cache_service = get_enhanced_cache_service()
        
        invalidated = await cache_service.invalidate_guild_roles_cache(str(role.guild.id))
        logger.info(f"Role '{role.name}' deleted from guild {role.guild.name} - invalidated {invalidated} cache entries")
    except Exception as e:
        logger.warning(f"Error invalidating role cache after role deletion: {e}")


@bot.event
async def on_guild_role_update(before, after):
    """Handle guild role updates - invalidate role cache if permissions changed"""
    try:
        # Check if role permissions changed (affects whether bot can ping the role)
        permissions_changed = (
            before.mentionable != after.mentionable or
            before.managed != after.managed or
            before.name != after.name
        )
        
        if permissions_changed:
            from .enhanced_cache_service import get_enhanced_cache_service
            cache_service = get_enhanced_cache_service()
            
            invalidated = await cache_service.invalidate_guild_roles_cache(str(after.guild.id))
            logger.info(f"Role '{after.name}' updated in guild {after.guild.name} - invalidated {invalidated} cache entries")
    except Exception as e:
        logger.warning(f"Error invalidating role cache after role update: {e}")


@bot.event
async def on_error(event, *args, **kwargs):
    """Handle bot errors and suppress command prefix errors"""
    import sys
    import traceback
    
    # Get the exception info
    exc_type, exc_value, exc_traceback = sys.exc_info()
    
    # Suppress command prefix errors since this is a reaction-only bot
    if (exc_type == TypeError and 
        exc_value and 
        "command_prefix must be plain string" in str(exc_value)):
        logger.debug(f"Suppressed command prefix error: {exc_value}")
        return
    
    # Log other errors normally
    logger.error(f"Bot error in event {event}: {exc_value}")
    logger.error(''.join(traceback.format_exception(exc_type, exc_value, exc_traceback)))


@bot.event
async def on_reaction_add(reaction, user):
    """Handle poll voting via reactions using bulletproof operations"""
    if user.bot:
        return

    # Check if this is a poll message
    db = get_db_session()
    poll = None  # Initialize poll variable
    try:
        poll = (
            db.query(Poll).filter(Poll.message_id == str(reaction.message.id)).first()
        )
        if not poll or TypeSafeColumn.get_string(poll, "status") != "active":
            return

        # Check if emoji is valid poll option using the poll's actual emojis
        poll_emojis = poll.emojis if poll.emojis else POLL_EMOJIS
        reaction_emoji = str(reaction.emoji)

        if reaction_emoji not in poll_emojis:
            return

        option_index = poll_emojis.index(reaction_emoji)
        if option_index >= len(poll.options):
            return

        # Get poll ID as integer for use throughout
        poll_id = TypeSafeColumn.get_int(poll, "id")

        # CRITICAL: Vote MUST be counted FIRST, reaction removed ONLY if vote succeeds
        # Use bulletproof vote collection
        from .poll_operations import BulletproofPollOperations

        bulletproof_ops = BulletproofPollOperations(bot)
        result = await bulletproof_ops.bulletproof_vote_collection(
            poll_id, str(user.id), option_index
        )

        if result["success"]:
            # Vote was successfully recorded - handle reaction based on poll type and anonymity
            vote_action = result.get("action", "unknown")
            logger.info(f"🔔 DM DEBUG - Vote processing successful, vote_action: {vote_action}, poll_id: {poll_id}, user: {user.id}")

            # Check poll properties safely using TypeSafeColumn
            is_anonymous = TypeSafeColumn.get_bool(poll, "anonymous", False)
            is_multiple_choice = TypeSafeColumn.get_bool(poll, "multiple_choice", False)

            # Always remove reactions for anonymous polls (to maintain anonymity)
            # Always remove reactions for single choice polls (traditional behavior)
            # For multiple choice non-anonymous polls: keep reactions to show selections
            should_remove_reaction = (
                is_anonymous  # Anonymous polls: always remove
                or not is_multiple_choice  # Single choice polls: always remove
                or vote_action
                == "removed"  # Multiple choice: remove if vote was toggled off
            )

            if should_remove_reaction:
                try:
                    await reaction.remove(user)
                    logger.debug(
                        f"✅ Vote {vote_action} and reaction removed for user {user.id} on poll {poll_id} "
                        f"(anonymous={is_anonymous}, multiple_choice={is_multiple_choice})"
                    )
                except Exception as remove_error:
                    logger.warning(
                        f"⚠️ Vote recorded but failed to remove reaction from user {user.id}: {remove_error}"
                    )
                    # Vote is still counted even if reaction removal fails
            else:
                # Multiple choice non-anonymous: keep reaction to show user's selection
                logger.debug(
                    f"✅ Multiple choice non-anonymous vote {vote_action}, keeping reaction for user {user.id} on poll {poll_id}"
                )

            # Send DM confirmation to the voter
            try:
                from .discord_utils import send_vote_confirmation_dm

                logger.info(f"🔔 DM DEBUG - About to call send_vote_confirmation_dm for vote_action: {vote_action} to user {user.id}")
                logger.info(f"🔔 DM DEBUG - Parameters: poll_id={poll_id}, user_id={user.id}, option_index={option_index}, vote_action={vote_action}")
                dm_sent = await send_vote_confirmation_dm(
                    bot, poll, str(user.id), option_index, vote_action
                )
                logger.info(f"🔔 DM DEBUG - send_vote_confirmation_dm returned: {dm_sent}")
                if dm_sent:
                    logger.info(
                        f"✅ Vote confirmation DM sent to user {user.id} for poll {poll_id} (action: {vote_action})"
                    )
                else:
                    logger.warning(
                        f"⚠️ Vote confirmation DM not sent to user {user.id} (DMs disabled or error) (action: {vote_action})"
                    )
            except Exception as dm_error:
                logger.error(
                    f"❌ Failed to send vote confirmation DM to user {user.id}: {dm_error} (action: {vote_action})"
                )
                # Don't fail the vote process if DM fails

            # Always update poll embed for live updates (key requirement)
            try:
                await update_poll_message(bot, poll)
                logger.debug(f"✅ Poll message updated for poll {poll_id}")
            except Exception as update_error:
                logger.error(
                    f"❌ Failed to update poll message for poll {poll_id}: {update_error}"
                )
        else:
            # Vote failed - do NOT remove reaction, log the error
            error_msg = await PollErrorHandler.handle_vote_error(
                Exception(result["error"]), poll_id, str(user.id), bot
            )
            logger.error(
                f"❌ Vote FAILED for user {user.id} on poll {poll_id}: {error_msg}"
            )
            # Reaction stays so user can try again

    except Exception as e:
        # Handle unexpected voting errors - removed manual notifications, automatic system will handle
        try:
            poll_id_for_error = TypeSafeColumn.get_int(poll, "id", 0) if poll else 0
            error_msg = await PollErrorHandler.handle_vote_error(
                e, poll_id_for_error, str(user.id), bot
            )
            logger.error(f"Error handling vote: {error_msg}")
        except Exception as error_handling_error:
            logger.error(
                f"Critical error in vote error handling: {error_handling_error}"
            )
    finally:
        db.close()


async def start_bot():
    """Start the Discord bot"""
    if DISCORD_TOKEN:
        await bot.start(DISCORD_TOKEN)


async def shutdown_bot():
    """Shutdown the Discord bot"""
    if bot and not bot.is_closed():
        await bot.close()


def get_bot_instance():
    """Get the bot instance"""
    return bot
