"""
Discord Utility Functions
Helper functions for Discord bot operations, guild/channel management, and poll posting.
"""

import discord
from discord.ext import commands
from datetime import datetime
from typing import List, Dict, Any
import logging
import pytz

from .database import get_db_session, Guild, Channel, Poll, POLL_EMOJIS

logger = logging.getLogger(__name__)


async def update_guild_cache(bot: commands.Bot, guild: discord.Guild):
    """Update cached guild information in database"""
    db = get_db_session()
    try:
        db_guild = db.query(Guild).filter(Guild.id == str(guild.id)).first()

        if db_guild:
            # Update existing guild
            db_guild.name = guild.name
            db_guild.icon = str(guild.icon) if guild.icon else None
            db_guild.owner_id = str(guild.owner_id)
        else:
            # Create new guild
            db_guild = Guild(
                id=str(guild.id),
                name=guild.name,
                icon=str(guild.icon) if guild.icon else None,
                owner_id=str(guild.owner_id)
            )
            db.add(db_guild)

        db.commit()
        logger.info(f"Updated guild cache for {guild.name} ({guild.id})")

    except Exception as e:
        logger.error(f"Error updating guild cache: {e}")
        # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
        from .error_handler import notify_error
        notify_error(e, "Guild Cache Update", guild_id=str(
            guild.id), guild_name=guild.name)
        db.rollback()
    finally:
        db.close()


async def update_channels_cache(bot: commands.Bot, guild: discord.Guild):
    """Update cached channel information for a guild"""
    db = get_db_session()
    try:
        # Remove old channels for this guild
        db.query(Channel).filter(Channel.guild_id == str(guild.id)).delete()

        # Add current channels
        for channel in guild.channels:
            if isinstance(channel, (discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel)):
                db_channel = Channel(
                    id=str(channel.id),
                    guild_id=str(guild.id),
                    name=channel.name,
                    type=channel.type.name,
                    position=getattr(channel, 'position', 0)
                )
                db.add(db_channel)

        db.commit()
        logger.info(
            f"Updated channel cache for {guild.name} ({len(guild.channels)} channels)")

    except Exception as e:
        logger.error(f"Error updating channel cache: {e}")
        # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
        from .error_handler import notify_error
        notify_error(e, "Channel Cache Update", guild_id=str(
            guild.id), guild_name=guild.name)
        db.rollback()
    finally:
        db.close()


async def get_user_guilds_with_channels(bot: commands.Bot, user_id: str) -> List[Dict[str, Any]]:
    """Get guilds where user has admin permissions along with available channels"""
    user_guilds = []

    if not bot or not bot.guilds:
        logger.warning("Bot not ready or no guilds available")
        return user_guilds

    for guild in bot.guilds:
        try:
            # Safely fetch member with better error handling
            member = None
            try:
                member = await guild.fetch_member(int(user_id))
            except (discord.NotFound, discord.Forbidden):
                logger.debug(f"User {user_id} not found in guild {guild.name}")
                continue
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid user_id format {user_id}: {e}")
                continue
            except Exception as e:
                logger.error(
                    f"Unexpected error fetching member {user_id} in {guild.name}: {e}")
                continue

            if not member:
                continue

            # Check if user has admin permissions with better error handling
            try:
                has_admin = member.guild_permissions.administrator or member.guild_permissions.manage_guild
            except Exception as e:
                logger.error(
                    f"Error checking permissions for {user_id} in {guild.name}: {e}")
                continue

            if has_admin:
                try:
                    # Update caches with error handling
                    await update_guild_cache(bot, guild)
                    await update_channels_cache(bot, guild)

                    # Get text channels where bot can send messages
                    text_channels = []
                    bot_member = guild.get_member(bot.user.id)

                    if bot_member:
                        for channel in guild.text_channels:
                            try:
                                if channel.permissions_for(bot_member).send_messages:
                                    text_channels.append({
                                        'id': str(channel.id),
                                        'name': channel.name,
                                        'position': channel.position
                                    })
                            except Exception as e:
                                logger.warning(
                                    f"Error checking permissions for channel {channel.name}: {e}")
                                # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
                                from .error_handler import notify_error
                                notify_error(
                                    e, "Channel Permission Check", channel_name=channel.name, guild_name=guild.name)
                                continue

                    # Sort channels by position
                    text_channels.sort(key=lambda x: x.get('position', 0))

                    user_guilds.append({
                        'id': str(guild.id),
                        'name': guild.name,
                        'icon': str(guild.icon) if guild.icon else None,
                        'channels': text_channels
                    })
                except Exception as e:
                    logger.error(
                        f"Error processing guild data for {guild.name}: {e}")
                    # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
                    from .error_handler import notify_error
                    notify_error(e, "Guild Data Processing",
                                 guild_name=guild.name, user_id=user_id)
                    continue

        except Exception as e:
            logger.error(
                f"Unexpected error processing guild {getattr(guild, 'name', 'Unknown')}: {e}")
            # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
            from .error_handler import notify_error
            notify_error(e, "Guild Processing", guild_name=getattr(
                guild, 'name', 'Unknown'), user_id=user_id)
            continue

    return user_guilds


async def create_poll_embed(poll: Poll, show_results: bool = True) -> discord.Embed:
    """Create Discord embed for a poll"""
    # CRITICAL FIX: Always refresh poll data from database to ensure we have latest votes
    # This prevents DetachedInstanceError and ensures vote counts are current
    db = get_db_session()
    try:
        # Get poll ID safely
        poll_id = getattr(poll, 'id')
        if poll_id is None:
            logger.error("Poll object has no ID, cannot refresh from database")
            raise Exception("Invalid poll object - no ID")

        # Refresh poll with all relationships loaded
        fresh_poll = db.query(Poll).filter(Poll.id == poll_id).first()
        if not fresh_poll:
            logger.error(
                f"Poll {poll_id} not found in database during embed creation")
            raise Exception(f"Poll {poll_id} not found in database")

        # Use the fresh poll object for all operations
        poll = fresh_poll
        logger.debug(
            f"Successfully refreshed poll {poll_id} data for embed creation")

    except Exception as e:
        logger.error(f"Critical error refreshing poll data for embed: {e}")
        # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
        from .error_handler import notify_error_async
        await notify_error_async(e, "Poll Embed Data Refresh", poll_id=getattr(poll, 'id', 'unknown'))
        # Continue with original poll object as fallback, but this may cause issues
    finally:
        db.close()

    # Determine embed color based on status
    poll_status = str(getattr(poll, 'status', 'unknown'))
    if poll_status == "scheduled":
        color = 0xffaa00  # Orange
        status_emoji = "⏰"
    elif poll_status == "active":
        color = 0x00ff00  # Green
        status_emoji = "📊"
    else:  # closed
        color = 0xff0000  # Red
        status_emoji = "🏁"

    embed = discord.Embed(
        title=f"{status_emoji} {str(getattr(poll, 'name', ''))}",
        description=str(getattr(poll, 'question', '')),
        color=color,
        timestamp=datetime.now(pytz.UTC)
    )

    # Add poll options
    option_text = ""
    if show_results and poll.should_show_results():
        # Show results with enhanced progress bars and percentages
        results = poll.get_results()
        total_votes = poll.get_total_votes()

        for i, option in enumerate(poll.options):
            emoji = poll.emojis[i] if i < len(poll.emojis) else POLL_EMOJIS[i]
            votes = results.get(i, 0)
            percentage = (votes / total_votes * 100) if total_votes > 0 else 0

            # Create enhanced progress bar with better visual representation
            bar_length = 15  # Longer bar for better granularity
            filled = int((percentage / 100) * bar_length)

            # Use different characters for better visual appeal
            if filled == 0:
                bar = "░" * bar_length
            else:
                # Use gradient-like characters for better visual appeal
                full_blocks = filled
                bar = "█" * full_blocks + "░" * (bar_length - full_blocks)

            # Format the option with enhanced styling
            option_text += f"{emoji} **{option}**\n"
            option_text += f"`{bar}` **{votes}** votes (**{percentage:.1f}%**)\n\n"

        embed.add_field(
            name="📊 Results" if poll_status == "closed" else "📈 Live Results",
            value=option_text or "No votes yet",
            inline=False
        )

        # Enhanced total votes display
        if total_votes > 0:
            embed.add_field(
                name="🗳️ Total Votes",
                value=f"**{total_votes}**",
                inline=True
            )

        # Winner announcement for closed polls
        if poll_status == "closed" and total_votes > 0:
            winners = poll.get_winner()
            if winners:
                if len(winners) == 1:
                    winner_emoji = poll.emojis[winners[0]] if winners[0] < len(
                        poll.emojis) else POLL_EMOJIS[winners[0]]
                    winner_option = poll.options[winners[0]]
                    winner_votes = results.get(winners[0], 0)
                    winner_percentage = (
                        winner_votes / total_votes * 100) if total_votes > 0 else 0
                    embed.add_field(
                        name="🏆 Winner",
                        value=f"{winner_emoji} **{winner_option}**\n{winner_votes} votes ({winner_percentage:.1f}%)",
                        inline=True
                    )
                else:
                    # Multiple winners (tie)
                    winner_text = "**TIE!**\n"
                    for winner_idx in winners:
                        winner_emoji = poll.emojis[winner_idx] if winner_idx < len(
                            poll.emojis) else POLL_EMOJIS[winner_idx]
                        winner_option = poll.options[winner_idx]
                        winner_votes = results.get(winner_idx, 0)
                        winner_percentage = (
                            winner_votes / total_votes * 100) if total_votes > 0 else 0
                        winner_text += f"{winner_emoji} {winner_option} ({winner_votes} votes, {winner_percentage:.1f}%)\n"
                    embed.add_field(name="🏆 Winners",
                                    value=winner_text, inline=True)
    else:
        # Just show options without results
        for i, option in enumerate(poll.options):
            emoji = poll.emojis[i] if i < len(poll.emojis) else POLL_EMOJIS[i]
            option_text += f"{emoji} {option}\n"

        embed.add_field(name="📝 Options", value=option_text, inline=False)

        # Always show total votes for active polls
        total_votes = poll.get_total_votes()

        poll_anonymous = bool(getattr(poll, 'anonymous', False))
        if poll_anonymous:
            # Enhanced anonymous poll display
            embed.add_field(
                name="🔒 Anonymous Poll",
                value=f"Results will be revealed when the poll ends\n🗳️ **{total_votes}** votes cast so far",
                inline=False
            )
        else:
            # For non-anonymous polls, ALWAYS show live results with percentages
            if total_votes > 0:
                # Show live vote breakdown for non-anonymous polls
                results = poll.get_results()
                live_results_text = ""

                for i, option in enumerate(poll.options):
                    emoji = poll.emojis[i] if i < len(
                        poll.emojis) else POLL_EMOJIS[i]
                    votes = results.get(i, 0)
                    percentage = (votes / total_votes *
                                  100) if total_votes > 0 else 0

                    # Shorter progress bar for live results
                    bar_length = 10
                    filled = int((percentage / 100) * bar_length)
                    bar = "█" * filled + "░" * (bar_length - filled)

                    live_results_text += f"{emoji} `{bar}` **{votes}** ({percentage:.1f}%)\n"

                embed.add_field(
                    name="📈 Live Results",
                    value=live_results_text,
                    inline=False
                )

                embed.add_field(
                    name="🗳️ Total Votes",
                    value=f"**{total_votes}**",
                    inline=True
                )
            else:
                # Even with 0 votes, show the structure for non-anonymous polls
                results_text = ""
                for i, option in enumerate(poll.options):
                    emoji = poll.emojis[i] if i < len(
                        poll.emojis) else POLL_EMOJIS[i]
                    bar = "░" * 10  # Empty bar
                    results_text += f"{emoji} `{bar}` **0** (0.0%)\n"

                embed.add_field(
                    name="📈 Live Results",
                    value=results_text,
                    inline=False
                )

    # Add timing information with timezone support
    if poll_status == "scheduled":
        # Only show opens time for scheduled polls, with timezone-specific time
        poll_timezone = str(getattr(poll, 'timezone', 'UTC'))
        if poll_timezone and poll_timezone != 'UTC':
            try:
                tz = pytz.timezone(poll_timezone)
                local_open = poll.open_time.astimezone(tz)
                embed.add_field(
                    name=f"Opens ({poll_timezone})",
                    value=local_open.strftime("%Y-%m-%d %I:%M %p"),
                    inline=True
                )
            except (pytz.UnknownTimeZoneError, ValueError, AttributeError) as e:
                logger.warning(
                    f"Error formatting timezone {poll_timezone}: {e}")
                # Fallback to UTC
                embed.add_field(
                    name="Opens (UTC)",
                    value=poll.open_time.strftime("%Y-%m-%d %I:%M %p"),
                    inline=True
                )

    # Show close time for scheduled and active polls
    if poll_status in ["scheduled", "active"]:
        poll_timezone = str(getattr(poll, 'timezone', 'UTC'))
        if poll_timezone and poll_timezone != 'UTC':
            try:
                tz = pytz.timezone(poll_timezone)
                local_close = poll.close_time.astimezone(tz)
                embed.add_field(
                    name=f"Closes ({poll_timezone})",
                    value=local_close.strftime("%Y-%m-%d %I:%M %p"),
                    inline=True
                )
            except (pytz.UnknownTimeZoneError, ValueError, AttributeError) as e:
                logger.warning(
                    f"Error formatting timezone {poll_timezone}: {e}")
                # Fallback to UTC
                embed.add_field(
                    name="Closes (UTC)",
                    value=poll.close_time.strftime("%Y-%m-%d %I:%M %p"),
                    inline=True
                )

    # Add poll info in footer without Poll ID
    embed.set_footer(text="Created by Polly")

    return embed


async def post_poll_to_channel(bot: commands.Bot, poll: Poll):
    """Post a poll to its designated Discord channel with comprehensive debugging"""
    logger.info(f"🚀 POSTING POLL {poll.id} - Starting post_poll_to_channel")
    logger.debug(
        f"Poll details: name='{poll.name}', server_id={poll.server_id}, channel_id={poll.channel_id}")

    try:
        # Debug bot status
        if not bot:
            logger.error(f"❌ POSTING POLL {poll.id} - Bot instance is None")
            return False

        if not bot.is_ready():
            logger.error(f"❌ POSTING POLL {poll.id} - Bot is not ready")
            return False

        logger.debug(
            f"✅ POSTING POLL {poll.id} - Bot is ready, user: {bot.user}")

        # Debug channel retrieval
        logger.debug(
            f"🔍 POSTING POLL {poll.id} - Looking for channel {poll.channel_id}")
        channel = bot.get_channel(int(str(poll.channel_id)))

        if not channel:
            logger.error(
                f"❌ POSTING POLL {poll.id} - Channel {poll.channel_id} not found")
            logger.debug(
                f"Available channels: {[c.id for c in bot.get_all_channels()]}")
            return False

        # Ensure we have a text channel
        if not isinstance(channel, discord.TextChannel):
            logger.error(
                f"❌ POSTING POLL {poll.id} - Channel {poll.channel_id} is not a text channel")
            return False

        logger.info(
            f"✅ POSTING POLL {poll.id} - Found channel: {channel.name} ({channel.id})")

        # Debug bot permissions in channel
        bot_member = channel.guild.get_member(bot.user.id)
        if not bot_member:
            logger.error(
                f"❌ POSTING POLL {poll.id} - Bot not found as member in guild {channel.guild.name}")
            return False

        permissions = channel.permissions_for(bot_member)
        logger.debug(
            f"🔐 POSTING POLL {poll.id} - Bot permissions: send_messages={permissions.send_messages}, embed_links={permissions.embed_links}, add_reactions={permissions.add_reactions}")

        if not permissions.send_messages:
            logger.error(
                f"❌ POSTING POLL {poll.id} - Bot lacks send_messages permission in {channel.name}")
            return False

        if not permissions.embed_links:
            logger.error(
                f"❌ POSTING POLL {poll.id} - Bot lacks embed_links permission in {channel.name}")
            return False

        if not permissions.add_reactions:
            logger.error(
                f"❌ POSTING POLL {poll.id} - Bot lacks add_reactions permission in {channel.name}")
            return False

        # CRITICAL FIX: Refresh poll object from database to avoid DetachedInstanceError
        # The poll object passed to this function may be detached from the database session
        logger.debug(
            f"🔄 POSTING POLL {getattr(poll, 'id', 'unknown')} - Refreshing poll from database to avoid DetachedInstanceError")
        db = get_db_session()
        try:
            # Eagerly load the votes relationship to avoid DetachedInstanceError
            from sqlalchemy.orm import joinedload
            fresh_poll = db.query(Poll).options(joinedload(Poll.votes)).filter(
                Poll.id == getattr(poll, 'id')).first()
            if not fresh_poll:
                logger.error(
                    f"❌ POSTING POLL {getattr(poll, 'id', 'unknown')} - Poll not found in database during refresh")
                return False

            # Use the fresh poll object for all operations
            poll = fresh_poll
            logger.debug(
                f"✅ POSTING POLL {getattr(poll, 'id', 'unknown')} - Successfully refreshed poll from database")

            # Create embed with debugging while poll is still attached to session
            logger.debug(
                f"📝 POSTING POLL {getattr(poll, 'id', 'unknown')} - Creating embed")
            embed = await create_poll_embed(poll, show_results=bool(poll.should_show_results()))
            logger.debug(
                f"✅ POSTING POLL {getattr(poll, 'id', 'unknown')} - Embed created successfully")

        except Exception as refresh_error:
            logger.error(
                f"❌ POSTING POLL {getattr(poll, 'id', 'unknown')} - Failed to refresh poll from database: {refresh_error}")
            return False
        finally:
            db.close()

        # Post image message first if poll has an image
        poll_image_path = getattr(poll, 'image_path', None)
        if poll_image_path is not None and str(poll_image_path).strip():
            try:
                logger.debug(
                    f"🖼️ POSTING POLL {poll.id} - Posting image message first")

                # Prepare image message content - ensure we get the actual string value
                poll_image_message_text = getattr(
                    poll, 'image_message_text', None)
                image_content = str(
                    poll_image_message_text) if poll_image_message_text else ""

                # Create file object for Discord
                import os
                image_path_str = str(poll_image_path)
                if os.path.exists(image_path_str):
                    with open(image_path_str, 'rb') as f:
                        file = discord.File(
                            f, filename=os.path.basename(image_path_str))

                        # Post image message
                        if image_content.strip():
                            await channel.send(content=image_content, file=file)
                            logger.info(
                                f"✅ POSTING POLL {poll.id} - Posted image with text: '{image_content[:50]}...'")
                        else:
                            await channel.send(file=file)
                            logger.info(
                                f"✅ POSTING POLL {poll.id} - Posted image without text")
                else:
                    logger.warning(
                        f"⚠️ POSTING POLL {poll.id} - Image file not found: {image_path_str}")

            except Exception as image_error:
                logger.error(
                    f"❌ POSTING POLL {poll.id} - Failed to post image: {image_error}")
                # Continue with poll posting even if image fails

        # Embed was already created above while poll was attached to database session

        # Post message with debugging
        logger.info(
            f"📤 POSTING POLL {poll.id} - Sending message to {channel.name}")
        message = await channel.send(embed=embed)
        logger.info(
            f"✅ POSTING POLL {poll.id} - Message sent successfully, ID: {message.id}")

        # Add reactions for voting with debugging
        logger.debug(
            f"😀 POSTING POLL {poll.id} - Adding {len(poll.options)} reactions")
        for i in range(len(poll.options)):
            emoji = poll.emojis[i] if i < len(
                poll.emojis or []) else POLL_EMOJIS[i]
            try:
                await message.add_reaction(emoji)
                logger.debug(
                    f"✅ POSTING POLL {poll.id} - Added reaction {emoji} for option {i}")
            except Exception as reaction_error:
                logger.error(
                    f"❌ POSTING POLL {poll.id} - Failed to add reaction {emoji}: {reaction_error}")

        # Update poll with message ID
        poll_id = getattr(poll, 'id')
        logger.debug(
            f"💾 POSTING POLL {poll_id} - Updating database with message ID")
        db = get_db_session()
        try:
            # Update poll in database
            poll_to_update = db.query(Poll).filter(Poll.id == poll_id).first()
            if poll_to_update:
                setattr(poll_to_update, 'message_id', str(message.id))
                setattr(poll_to_update, 'status', "active")
                db.commit()
                logger.info(
                    f"✅ POSTING POLL {poll_id} - Database updated, poll is now ACTIVE")
                logger.info(
                    f"🎉 POSTING POLL {poll_id} - Successfully posted to channel {channel.name}")
                return True
            else:
                logger.error(
                    f"❌ POSTING POLL {poll_id} - Poll not found for update")
                return False
        except Exception as db_error:
            logger.error(
                f"❌ POSTING POLL {poll_id} - Database update failed: {db_error}")
            db.rollback()
            return False
        finally:
            db.close()

    except discord.Forbidden as e:
        logger.error(
            f"❌ POSTING POLL {poll.id} - Discord Forbidden error: {e}")
        # Send DM notification to bot owner about permission error
        try:
            from .error_handler import BotOwnerNotifier
            await BotOwnerNotifier.send_error_dm(
                bot, e, "Poll Posting - Permission Error",
                {
                    "poll_id": getattr(poll, 'id'),
                    "poll_name": str(getattr(poll, 'name', '')),
                    "server_id": str(getattr(poll, 'server_id', '')),
                    "channel_id": str(getattr(poll, 'channel_id', ''))
                }
            )
        except Exception as dm_error:
            logger.error(f"Failed to send DM notification: {dm_error}")
        return False
    except discord.HTTPException as e:
        logger.error(f"❌ POSTING POLL {poll.id} - Discord HTTP error: {e}")
        # Send DM notification to bot owner about HTTP error
        try:
            from .error_handler import BotOwnerNotifier
            await BotOwnerNotifier.send_error_dm(
                bot, e, "Poll Posting - Discord API Error",
                {
                    "poll_id": getattr(poll, 'id'),
                    "poll_name": str(getattr(poll, 'name', '')),
                    "server_id": str(getattr(poll, 'server_id', '')),
                    "channel_id": str(getattr(poll, 'channel_id', ''))
                }
            )
        except Exception as dm_error:
            logger.error(f"Failed to send DM notification: {dm_error}")
        return False
    except Exception as e:
        logger.error(f"❌ POSTING POLL {poll.id} - Unexpected error: {e}")
        logger.exception(f"Full traceback for poll {poll.id} posting error:")
        # Send DM notification to bot owner about unexpected error
        try:
            from .error_handler import BotOwnerNotifier
            await BotOwnerNotifier.send_error_dm(
                bot, e, "Poll Posting - Unexpected Error",
                {
                    "poll_id": getattr(poll, 'id'),
                    "poll_name": str(getattr(poll, 'name', '')),
                    "server_id": str(getattr(poll, 'server_id', '')),
                    "channel_id": str(getattr(poll, 'channel_id', '')),
                    "error_type": type(e).__name__
                }
            )
        except Exception as dm_error:
            logger.error(f"Failed to send DM notification: {dm_error}")
        return False


async def update_poll_message(bot: commands.Bot, poll: Poll):
    """Update poll message with current results"""
    try:
        poll_message_id = getattr(poll, 'message_id', None)
        if not poll_message_id:
            return False

        poll_channel_id = getattr(poll, 'channel_id', None)
        channel = bot.get_channel(int(str(poll_channel_id)))
        if not channel:
            return False

        # Ensure we have a text channel
        if not isinstance(channel, discord.TextChannel):
            return False

        try:
            message = await channel.fetch_message(int(str(poll_message_id)))
        except discord.NotFound:
            logger.warning(f"Poll message {poll_message_id} not found")
            return False

        # Update embed
        embed = await create_poll_embed(poll, show_results=bool(poll.should_show_results()))
        await message.edit(embed=embed)

        logger.debug(f"Updated poll message for poll {getattr(poll, 'id')}")
        return True

    except Exception as e:
        logger.error(f"Error updating poll message {poll.id}: {e}")
        # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
        from .error_handler import notify_error_async
        await notify_error_async(e, "Poll Message Update", poll_id=getattr(poll, 'id'))
        return False


async def post_poll_results(bot: commands.Bot, poll: Poll):
    """Post final results when poll closes"""
    try:
        poll_channel_id = getattr(poll, 'channel_id', None)
        channel = bot.get_channel(int(str(poll_channel_id)))
        if not channel:
            return False

        # Ensure we have a text channel
        if not isinstance(channel, discord.TextChannel):
            return False

        # Create results embed
        embed = await create_poll_embed(poll, show_results=True)
        poll_name = str(getattr(poll, 'name', ''))
        embed.title = f"🏁 Poll Results: {poll_name}"
        embed.color = 0xff0000  # Red for closed

        # Post results message
        await channel.send(f"📊 **Poll '{poll_name}' has ended!**", embed=embed)

        logger.info(f"Posted final results for poll {getattr(poll, 'id')}")
        return True

    except Exception as e:
        logger.error(f"Error posting poll results {poll.id}: {e}")
        # EASY BOT OWNER NOTIFICATION - JUST ADD THIS LINE!
        from .error_handler import notify_error_async
        await notify_error_async(e, "Poll Results Posting", poll_id=getattr(poll, 'id'))
        return False


def user_has_admin_permissions(member: discord.Member) -> bool:
    """Check if user has admin permissions in the guild"""
    return member.guild_permissions.administrator or member.guild_permissions.manage_guild or member.guild_permissions.manage_channels
