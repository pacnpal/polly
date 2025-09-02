"""
Polly Discord Bot
Discord bot setup and event handling functionality.
"""

import os
import logging
from datetime import datetime, timedelta
import pytz
import discord
from discord.ext import commands

from .database import get_db_session, Poll, POLL_EMOJIS, TypeSafeColumn
from .discord_utils import create_poll_embed, update_poll_message, user_has_admin_permissions
from .error_handler import PollErrorHandler, notify_error_async

logger = logging.getLogger(__name__)

# Configuration
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN environment variable is required")

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.reactions = True

bot = commands.Bot(command_prefix='!', intents=intents)


@bot.event
async def on_ready():
    """Bot ready event"""
    logger.info(f'{bot.user} has connected to Discord!')

    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} command(s)")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")
        from .error_handler import notify_error
        notify_error(e, "Discord Command Sync")


@bot.tree.command(name="quickpoll", description="Create a quick poll in the current channel")
async def create_quick_poll_command(
    interaction: discord.Interaction,
    question: str,
    option1: str,
    option2: str,
    option3: str = None,
    option4: str = None,
    option5: str = None,
    anonymous: bool = False
):
    """Create a quick poll via Discord slash command"""
    # Check if user has admin permissions
    if not user_has_admin_permissions(interaction.user):
        await interaction.response.send_message(
            "❌ You need Administrator or Manage Server permissions to create polls.",
            ephemeral=True
        )
        return

    # Collect options
    options = [option1, option2]
    emojis = ["🇦", "🇧", "🇨", "🇩", "🇪"][:len(options)]
    for opt in [option3, option4, option5]:
        if opt:
            options.append(opt)

    if len(options) > 10:
        await interaction.response.send_message(
            "❌ Maximum 10 poll options allowed.",
            ephemeral=True
        )
        return

    # Create poll in database
    db = get_db_session()
    try:
        poll = Poll(
            name=f"Quick Poll - {question[:50]}",
            question=question,
            options=options,
            emojis=emojis,
            server_id=str(interaction.guild_id),
            server_name=interaction.guild.name if interaction.guild else "Unknown",
            channel_id=str(interaction.channel_id),
            channel_name=getattr(interaction.channel, 'name', 'Unknown'),
            creator_id=str(interaction.user.id),
            open_time=datetime.now(pytz.UTC),
            close_time=datetime.now(pytz.UTC) + timedelta(hours=24),
            anonymous=anonymous,
            status="active"
        )
        db.add(poll)
        db.commit()
        db.refresh(poll)

        # Create embed
        embed = await create_poll_embed(poll, show_results=bool(poll.should_show_results()))

        await interaction.response.send_message(embed=embed)

        # Get the message and add reactions
        message = await interaction.original_response()
        poll.message_id = str(message.id)
        db.commit()

        # Add reaction emojis
        for i in range(len(options)):
            await message.add_reaction(POLL_EMOJIS[i])

        # Schedule poll closure
        from .background_tasks import get_scheduler
        from .background_tasks import close_poll
        from apscheduler.triggers.date import DateTrigger

        scheduler = get_scheduler()
        scheduler.add_job(
            close_poll,
            DateTrigger(run_date=poll.close_time),
            args=[TypeSafeColumn.get_int(poll, 'id')],
            id=f"close_poll_{TypeSafeColumn.get_int(poll, 'id')}"
        )

    except Exception as e:
        logger.error(f"Error creating poll: {e}")
        await notify_error_async(e, "Quick Poll Creation", question=question, user_id=str(interaction.user.id))
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Error creating poll. Please try again.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Error creating poll. Please try again.", ephemeral=True)
    finally:
        db.close()


@bot.event
async def on_reaction_add(reaction, user):
    """Handle poll voting via reactions using bulletproof operations"""
    if user.bot:
        return

    # Check if this is a poll message
    db = get_db_session()
    try:
        poll = db.query(Poll).filter(Poll.message_id ==
                                     str(reaction.message.id)).first()
        if not poll or TypeSafeColumn.get_string(poll, 'status') != "active":
            return

        # Check if emoji is valid poll option
        if str(reaction.emoji) not in POLL_EMOJIS:
            return

        option_index = POLL_EMOJIS.index(str(reaction.emoji))
        if option_index >= len(poll.options):
            return

        # Get poll ID as integer for use throughout
        poll_id = TypeSafeColumn.get_int(poll, 'id')

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

            # Check poll properties safely using TypeSafeColumn
            is_anonymous = TypeSafeColumn.get_bool(poll, 'anonymous', False)
            is_multiple_choice = TypeSafeColumn.get_bool(
                poll, 'multiple_choice', False)

            # Always remove reactions for anonymous polls (to maintain anonymity)
            # Always remove reactions for single choice polls (traditional behavior)
            # For multiple choice non-anonymous polls: keep reactions to show selections
            should_remove_reaction = (
                is_anonymous or  # Anonymous polls: always remove
                not is_multiple_choice or  # Single choice polls: always remove
                vote_action == "removed"  # Multiple choice: remove if vote was toggled off
            )

            if should_remove_reaction:
                try:
                    await reaction.remove(user)
                    logger.debug(
                        f"✅ Vote {vote_action} and reaction removed for user {user.id} on poll {poll_id} "
                        f"(anonymous={is_anonymous}, multiple_choice={is_multiple_choice})")
                except Exception as remove_error:
                    logger.warning(
                        f"⚠️ Vote recorded but failed to remove reaction from user {user.id}: {remove_error}")
                    # Vote is still counted even if reaction removal fails
            else:
                # Multiple choice non-anonymous: keep reaction to show user's selection
                logger.debug(
                    f"✅ Multiple choice non-anonymous vote {vote_action}, keeping reaction for user {user.id} on poll {poll_id}")

            # Always update poll embed for live updates (key requirement)
            try:
                await update_poll_message(bot, poll)
                logger.debug(f"✅ Poll message updated for poll {poll_id}")
            except Exception as update_error:
                logger.error(
                    f"❌ Failed to update poll message for poll {poll_id}: {update_error}")
        else:
            # Vote failed - do NOT remove reaction, log the error
            error_msg = await PollErrorHandler.handle_vote_error(
                Exception(result["error"]), poll_id, str(user.id), bot
            )
            logger.error(
                f"❌ Vote FAILED for user {user.id} on poll {poll_id}: {error_msg}")
            # Reaction stays so user can try again

    except Exception as e:
        # Handle unexpected voting errors with bot owner notification
        try:
            poll_id_for_error = TypeSafeColumn.get_int(
                poll, 'id', 0) if 'poll' in locals() and poll else 0
            error_msg = await PollErrorHandler.handle_vote_error(
                e, poll_id_for_error, str(user.id), bot
            )
            logger.error(f"Error handling vote: {error_msg}")
            await notify_error_async(e, "Reaction Vote Handling Critical Error",
                                     poll_id=poll_id_for_error, user_id=str(user.id))
        except Exception as error_handling_error:
            logger.error(
                f"Critical error in vote error handling: {error_handling_error}")
            await notify_error_async(error_handling_error, "Vote Error Handler Failure",
                                     user_id=str(user.id))
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
