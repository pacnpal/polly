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
                    continue

        except Exception as e:
            logger.error(
                f"Unexpected error processing guild {getattr(guild, 'name', 'Unknown')}: {e}")
            continue

    return user_guilds


async def create_poll_embed(poll: Poll, show_results: bool = True) -> discord.Embed:
    """Create Discord embed for a poll"""
    # Determine embed color based on status
    if poll.status == "scheduled":
        color = 0xffaa00  # Orange
        status_emoji = "⏰"
    elif poll.status == "active":
        color = 0x00ff00  # Green
        status_emoji = "📊"
    else:  # closed
        color = 0xff0000  # Red
        status_emoji = "🏁"

    embed = discord.Embed(
        title=f"{status_emoji} {poll.name}",
        description=poll.question,
        color=color,
        timestamp=datetime.now(pytz.UTC)
    )

    # Add poll options
    option_text = ""
    if show_results and poll.should_show_results():
        # Show results
        results = poll.get_results()
        total_votes = poll.get_total_votes()

        for i, option in enumerate(poll.options):
            emoji = poll.emojis[i] if i < len(poll.emojis) else POLL_EMOJIS[i]
            votes = results.get(i, 0)
            percentage = (votes / total_votes * 100) if total_votes > 0 else 0

            # Create a simple progress bar
            bar_length = 10
            filled = int((percentage / 100) * bar_length)
            bar = "█" * filled + "░" * (bar_length - filled)

            option_text += f"{emoji} **{option}**\n"
            option_text += f"   {bar} {votes} votes ({percentage:.1f}%)\n\n"

        embed.add_field(
            name="Results" if poll.status == "closed" else "Current Results",
            value=option_text or "No votes yet",
            inline=False
        )

        if total_votes > 0:
            embed.add_field(name="Total Votes", value=str(
                total_votes), inline=True)

        if poll.status == "closed" and total_votes > 0:
            winners = poll.get_winner()
            if winners:
                winner_text = ", ".join(
                    [f"{(poll.emojis[i] if i < len(poll.emojis) else POLL_EMOJIS[i])} {poll.options[i]}" for i in winners])
                embed.add_field(name="🏆 Winner(s)",
                                value=winner_text, inline=True)
    else:
        # Just show options without results
        for i, option in enumerate(poll.options):
            emoji = poll.emojis[i] if i < len(poll.emojis) else POLL_EMOJIS[i]
            option_text += f"{emoji} {option}\n"

        embed.add_field(name="Options", value=option_text, inline=False)

        if poll.anonymous:
            total_votes = poll.get_total_votes()
            embed.add_field(
                name="ℹ️ Anonymous Poll",
                value=f"Results will be shown when the poll ends\nTotal votes so far: **{total_votes}**",
                inline=False
            )

    # Add timing information with timezone support
    if poll.status == "scheduled":
        # Show both Discord timestamp and timezone-specific time
        embed.add_field(
            name="Opens",
            value=f"<t:{int(poll.open_time.timestamp())}:R>",
            inline=True
        )

        # Add timezone-specific time if available
        if hasattr(poll, 'timezone') and poll.timezone:
            try:
                tz = pytz.timezone(poll.timezone)
                local_open = poll.open_time.astimezone(tz)
                embed.add_field(
                    name=f"Opens ({poll.timezone})",
                    value=local_open.strftime("%Y-%m-%d %I:%M %p"),
                    inline=True
                )
            except (pytz.UnknownTimeZoneError, ValueError, AttributeError) as e:
                logger.warning(
                    f"Error formatting timezone {poll.timezone}: {e}")

    if poll.status in ["scheduled", "active"]:
        embed.add_field(
            name="Closes",
            value=f"<t:{int(poll.close_time.timestamp())}:R>",
            inline=True
        )

        # Add timezone-specific time if available
        if hasattr(poll, 'timezone') and poll.timezone:
            try:
                tz = pytz.timezone(poll.timezone)
                local_close = poll.close_time.astimezone(tz)
                embed.add_field(
                    name=f"Closes ({poll.timezone})",
                    value=local_close.strftime("%Y-%m-%d %I:%M %p"),
                    inline=True
                )
            except (pytz.UnknownTimeZoneError, ValueError, AttributeError) as e:
                logger.warning(
                    f"Error formatting timezone {poll.timezone}: {e}")

    # Add poll info in footer
    embed.set_footer(text=f"Poll ID: {poll.id} • Created by Polly")

    return embed


async def post_poll_to_channel(bot: commands.Bot, poll: Poll) -> bool:
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

        # Post image message first if poll has an image
        if poll.image_path and hasattr(poll, 'image_message_text'):
            try:
                logger.debug(f"🖼️ POSTING POLL {poll.id} - Posting image message first")
                
                # Prepare image message content
                image_content = poll.image_message_text or ""
                
                # Create file object for Discord
                import os
                if os.path.exists(poll.image_path):
                    with open(poll.image_path, 'rb') as f:
                        file = discord.File(f, filename=os.path.basename(poll.image_path))
                        
                        # Post image message
                        if image_content.strip():
                            await channel.send(content=image_content, file=file)
                            logger.info(f"✅ POSTING POLL {poll.id} - Posted image with text: '{image_content[:50]}...'")
                        else:
                            await channel.send(file=file)
                            logger.info(f"✅ POSTING POLL {poll.id} - Posted image without text")
                else:
                    logger.warning(f"⚠️ POSTING POLL {poll.id} - Image file not found: {poll.image_path}")
                    
            except Exception as image_error:
                logger.error(f"❌ POSTING POLL {poll.id} - Failed to post image: {image_error}")
                # Continue with poll posting even if image fails

        # Create embed with debugging
        logger.debug(f"📝 POSTING POLL {poll.id} - Creating embed")
        embed = await create_poll_embed(poll, show_results=bool(poll.should_show_results()))
        logger.debug(f"✅ POSTING POLL {poll.id} - Embed created successfully")

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
        logger.debug(
            f"💾 POSTING POLL {poll.id} - Updating database with message ID")
        db = get_db_session()
        try:
            # Update poll in database
            db.query(Poll).filter(Poll.id == poll.id).update({
                Poll.message_id: str(message.id),
                Poll.status: "active"
            })
            db.commit()
            logger.info(
                f"✅ POSTING POLL {poll.id} - Database updated, poll is now ACTIVE")
            logger.info(
                f"🎉 POSTING POLL {poll.id} - Successfully posted to channel {channel.name}")
            return True
        except Exception as db_error:
            logger.error(
                f"❌ POSTING POLL {poll.id} - Database update failed: {db_error}")
            db.rollback()
            return False
        finally:
            db.close()

    except discord.Forbidden as e:
        logger.error(
            f"❌ POSTING POLL {poll.id} - Discord Forbidden error: {e}")
        return False
    except discord.HTTPException as e:
        logger.error(f"❌ POSTING POLL {poll.id} - Discord HTTP error: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ POSTING POLL {poll.id} - Unexpected error: {e}")
        logger.exception(f"Full traceback for poll {poll.id} posting error:")
        return False


async def update_poll_message(bot: commands.Bot, poll: Poll):
    """Update poll message with current results"""
    try:
        if not poll.message_id:
            return False

        channel = bot.get_channel(int(poll.channel_id))
        if not channel:
            return False

        try:
            message = await channel.fetch_message(int(poll.message_id))
        except discord.NotFound:
            logger.warning(f"Poll message {poll.message_id} not found")
            return False

        # Update embed
        embed = await create_poll_embed(poll, show_results=poll.should_show_results())
        await message.edit(embed=embed)

        logger.debug(f"Updated poll message for poll {poll.id}")
        return True

    except Exception as e:
        logger.error(f"Error updating poll message {poll.id}: {e}")
        return False


async def post_poll_results(bot: commands.Bot, poll: Poll):
    """Post final results when poll closes"""
    try:
        channel = bot.get_channel(int(poll.channel_id))
        if not channel:
            return False

        # Create results embed
        embed = await create_poll_embed(poll, show_results=True)
        embed.title = f"🏁 Poll Results: {poll.name}"
        embed.color = 0xff0000  # Red for closed

        # Post results message
        await channel.send(f"📊 **Poll '{poll.name}' has ended!**", embed=embed)

        logger.info(f"Posted final results for poll {poll.id}")
        return True

    except Exception as e:
        logger.error(f"Error posting poll results {poll.id}: {e}")
        return False


def user_has_admin_permissions(member: discord.Member) -> bool:
    """Check if user has admin permissions in the guild"""
    return member.guild_permissions.administrator or member.guild_permissions.manage_guild or member.guild_permissions.manage_channels
