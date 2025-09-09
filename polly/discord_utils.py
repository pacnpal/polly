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
                owner_id=str(guild.owner_id),
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
            if isinstance(
                channel,
                (discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel),
            ):
                db_channel = Channel(
                    id=str(channel.id),
                    guild_id=str(guild.id),
                    name=channel.name,
                    type=channel.type.name,
                    position=getattr(channel, "position", 0),
                )
                db.add(db_channel)

        db.commit()
        logger.info(
            f"Updated channel cache for {guild.name} ({len(guild.channels)} channels)"
        )

    except Exception as e:
        logger.error(f"Error updating channel cache: {e}")
        db.rollback()
    finally:
        db.close()


async def get_user_guilds_with_channels(
    bot: commands.Bot, user_id: str
) -> List[Dict[str, Any]]:
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
                    f"Unexpected error fetching member {user_id} in {guild.name}: {e}"
                )
                continue

            if not member:
                continue

            # Check if user has admin permissions with better error handling
            try:
                has_admin = (
                    member.guild_permissions.administrator
                    or member.guild_permissions.manage_guild
                )
            except Exception as e:
                logger.error(
                    f"Error checking permissions for {user_id} in {guild.name}: {e}"
                )
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
                                    text_channels.append(
                                        {
                                            "id": str(channel.id),
                                            "name": channel.name,
                                            "position": channel.position,
                                        }
                                    )
                            except Exception as e:
                                logger.warning(
                                    f"Error checking permissions for channel {channel.name}: {e}"
                                )
                                continue

                    # Sort channels by position
                    text_channels.sort(key=lambda x: x.get("position", 0))

                    user_guilds.append(
                        {
                            "id": str(guild.id),
                            "name": guild.name,
                            "icon": str(guild.icon) if guild.icon else None,
                            "channels": text_channels,
                        }
                    )
                except Exception as e:
                    logger.error(f"Error processing guild data for {guild.name}: {e}")
                    continue

        except Exception as e:
            logger.error(
                f"Unexpected error processing guild {getattr(guild, 'name', 'Unknown')}: {e}"
            )
            continue

    return user_guilds


async def create_poll_embed(poll: Poll, show_results: bool = True) -> discord.Embed:
    """Create Discord embed for a poll"""
    # Note: Poll object should already be attached to a database session with votes eagerly loaded
    # to prevent DetachedInstanceError. This is handled by the calling function.

    # Determine embed color based on status
    poll_status = str(getattr(poll, "status", "unknown"))
    if poll_status == "scheduled":
        color = 0xFFAA00  # Orange
        status_emoji = "⏰"
    elif poll_status == "active":
        color = 0x00FF00  # Green
        status_emoji = "📊"
    else:  # closed
        color = 0xFF0000  # Red
        status_emoji = "🏁"

    embed = discord.Embed(
        title=f"{status_emoji} {str(getattr(poll, 'name', ''))}",
        description=str(getattr(poll, "question", "")),
        color=color,
        timestamp=datetime.now(pytz.UTC),
    )

    # Add poll options
    option_text = ""
    if show_results:
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
            inline=False,
        )

        # Enhanced total votes display
        if total_votes > 0:
            embed.add_field(
                name="🗳️ Total Votes", value=f"**{total_votes}**", inline=True
            )

        # Winner announcement for closed polls
        if poll_status == "closed" and total_votes > 0:
            winners = poll.get_winner()
            if winners:
                if len(winners) == 1:
                    winner_emoji = (
                        poll.emojis[winners[0]]
                        if winners[0] < len(poll.emojis)
                        else POLL_EMOJIS[winners[0]]
                    )
                    winner_option = poll.options[winners[0]]
                    winner_votes = results.get(winners[0], 0)
                    winner_percentage = (
                        (winner_votes / total_votes * 100) if total_votes > 0 else 0
                    )
                    embed.add_field(
                        name="🏆 Winner",
                        value=f"{winner_emoji} **{winner_option}**\n{winner_votes} votes ({winner_percentage:.1f}%)",
                        inline=True,
                    )
                else:
                    # Multiple winners (tie)
                    winner_text = "**TIE!**\n"
                    for winner_idx in winners:
                        winner_emoji = (
                            poll.emojis[winner_idx]
                            if winner_idx < len(poll.emojis)
                            else POLL_EMOJIS[winner_idx]
                        )
                        winner_option = poll.options[winner_idx]
                        winner_votes = results.get(winner_idx, 0)
                        winner_percentage = (
                            (winner_votes / total_votes * 100) if total_votes > 0 else 0
                        )
                        winner_text += f"{winner_emoji} {winner_option} ({winner_votes} votes, {winner_percentage:.1f}%)\n"
                    embed.add_field(name="🏆 Winners", value=winner_text, inline=True)
    else:
        # Just show options without results
        for i, option in enumerate(poll.options):
            emoji = poll.emojis[i] if i < len(poll.emojis) else POLL_EMOJIS[i]
            option_text += f"{emoji} {option}\n"

        embed.add_field(name="📝 Options", value=option_text, inline=False)

        # Always show total votes for active polls
        total_votes = poll.get_total_votes()

        poll_anonymous = bool(getattr(poll, "anonymous", False))
        if poll_anonymous:
            # Enhanced anonymous poll display
            embed.add_field(
                name="🔒 Anonymous Poll",
                value=f"Results will be revealed when the poll ends\n🗳️ **{total_votes}** votes cast so far",
                inline=False,
            )
        else:
            # For non-anonymous polls, ALWAYS show live results with percentages
            if total_votes > 0:
                # Show live vote breakdown for non-anonymous polls
                results = poll.get_results()
                live_results_text = ""

                for i, option in enumerate(poll.options):
                    emoji = poll.emojis[i] if i < len(poll.emojis) else POLL_EMOJIS[i]
                    votes = results.get(i, 0)
                    percentage = (votes / total_votes * 100) if total_votes > 0 else 0

                    # Shorter progress bar for live results
                    bar_length = 10
                    filled = int((percentage / 100) * bar_length)
                    bar = "█" * filled + "░" * (bar_length - filled)

                    live_results_text += (
                        f"{emoji} `{bar}` **{votes}** ({percentage:.1f}%)\n"
                    )

                embed.add_field(
                    name="📈 Live Results", value=live_results_text, inline=False
                )

                embed.add_field(
                    name="🗳️ Total Votes", value=f"**{total_votes}**", inline=True
                )
            else:
                # Even with 0 votes, show the structure for non-anonymous polls
                results_text = ""
                for i, option in enumerate(poll.options):
                    emoji = poll.emojis[i] if i < len(poll.emojis) else POLL_EMOJIS[i]
                    bar = "░" * 10  # Empty bar
                    results_text += f"{emoji} `{bar}` **0** (0.0%)\n"

                embed.add_field(
                    name="📈 Live Results", value=results_text, inline=False
                )

        # Add timing information with timezone support
        if poll_status == "scheduled":
            # Only show opens time for scheduled polls, with timezone-specific time
            poll_timezone = str(getattr(poll, "timezone", "UTC"))
            if poll_timezone and poll_timezone != "UTC":
                try:
                    # Validate and normalize timezone first
                    from .utils import validate_and_normalize_timezone

                    normalized_tz = validate_and_normalize_timezone(poll_timezone)
                    tz = pytz.timezone(normalized_tz)
                    local_open = poll.open_time.astimezone(tz)
                    embed.add_field(
                        name=f"Opens ({normalized_tz})",
                        value=local_open.strftime("%Y-%m-%d %I:%M %p"),
                        inline=True,
                    )
                except Exception as e:
                    logger.debug(f"Could not format timezone {poll_timezone}: {e}")
                    # Fallback to UTC
                    embed.add_field(
                        name="Opens (UTC)",
                        value=poll.open_time.strftime("%Y-%m-%d %I:%M %p"),
                        inline=True,
                    )

        # Show close time for scheduled and active polls
        if poll_status in ["scheduled", "active"]:
            poll_timezone = str(getattr(poll, "timezone", "UTC"))
            if poll_timezone and poll_timezone != "UTC":
                try:
                    # Validate and normalize timezone first
                    from .utils import validate_and_normalize_timezone

                    normalized_tz = validate_and_normalize_timezone(poll_timezone)
                    tz = pytz.timezone(normalized_tz)
                    local_close = poll.close_time.astimezone(tz)
                    embed.add_field(
                        name=f"Closes ({normalized_tz})",
                        value=local_close.strftime("%Y-%m-%d %I:%M %p"),
                        inline=True,
                    )
                except Exception as e:
                    logger.debug(f"Could not format timezone {poll_timezone}: {e}")
                    # Fallback to UTC
                    embed.add_field(
                        name="Closes (UTC)",
                        value=poll.close_time.strftime("%Y-%m-%d %I:%M %p"),
                        inline=True,
                    )

    # Add poll info in footer without Poll ID
    embed.set_footer(text="Created by Polly")

    return embed


async def post_poll_to_channel(bot: commands.Bot, poll_or_id):
    """Post a poll to its designated Discord channel with comprehensive debugging and validation

    Args:
        bot: Discord bot instance
        poll_or_id: Either a Poll object or poll_id (int)

    Returns:
        Dict with success status and message_id if successful, or error details if failed
    """
    # Handle both Poll object and poll_id
    if isinstance(poll_or_id, int):
        poll_id = poll_or_id
        logger.info(
            f"🚀 POSTING POLL {poll_id} - Starting post_poll_to_channel (from poll_id)"
        )

        # Fetch poll from database
        db = get_db_session()
        try:
            from sqlalchemy.orm import joinedload

            poll = (
                db.query(Poll)
                .options(joinedload(Poll.votes))
                .filter(Poll.id == poll_id)
                .first()
            )
            if not poll:
                logger.error(f"❌ POSTING POLL {poll_id} - Poll not found in database")
                return {"success": False, "error": "Poll not found in database"}
        except Exception as e:
            logger.error(
                f"❌ POSTING POLL {poll_id} - Error fetching poll from database: {e}"
            )
            return {"success": False, "error": f"Database error: {str(e)}"}
        finally:
            db.close()
    else:
        # Assume it's a Poll object
        poll = poll_or_id
        poll_id = getattr(poll, "id", "unknown")
        logger.info(
            f"🚀 POSTING POLL {poll_id} - Starting post_poll_to_channel (from Poll object)"
        )

    # STEP 1: Comprehensive Field Validation
    logger.info(f"🔍 POSTING POLL {poll_id} - Running comprehensive field validation")
    try:
        from .poll_field_validator import PollFieldValidator

        # Ensure poll_id is an integer for validation
        if isinstance(poll_id, str) and poll_id != "unknown":
            try:
                poll_id_int = int(poll_id)
            except ValueError:
                poll_id_int = getattr(poll, "id", 0)
        else:
            poll_id_int = (
                poll_id if isinstance(poll_id, int) else getattr(poll, "id", 0)
            )

        validation_result = (
            await PollFieldValidator.validate_poll_fields_before_posting(
                poll_id_int, bot
            )
        )

        if not validation_result["success"]:
            error_msg = (
                f"Poll validation failed: {'; '.join(validation_result['errors'][:3])}"
            )
            logger.error(f"❌ POSTING POLL {poll_id} - {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "validation_details": validation_result,
            }
        else:
            logger.info(
                f"✅ POSTING POLL {poll_id} - Field validation passed with {len(validation_result['validated_fields'])} fields validated"
            )
            if validation_result["warnings"]:
                logger.warning(
                    f"⚠️ POSTING POLL {poll_id} - Validation warnings: {'; '.join(validation_result['warnings'][:3])}"
                )
            if validation_result["fallback_applied"]:
                logger.info(
                    f"🔧 POSTING POLL {poll_id} - Applied {len(validation_result['fallback_applied'])} fallback mechanisms"
                )

    except Exception as validation_error:
        logger.error(
            f"❌ POSTING POLL {poll_id} - Validation system error: {validation_error}"
        )
        # Continue with posting but log the validation failure

    logger.debug(
        f"Poll details: name='{getattr(poll, 'name', '')}', server_id={getattr(poll, 'server_id', '')}, channel_id={getattr(poll, 'channel_id', '')}"
    )

    try:
        # Debug bot status
        if not bot:
            logger.error(f"❌ POSTING POLL {poll_id} - Bot instance is None")
            return {"success": False, "error": "Bot instance is None"}

        if not bot.is_ready():
            logger.error(f"❌ POSTING POLL {poll_id} - Bot is not ready")
            return {"success": False, "error": "Bot is not ready"}

        logger.debug(f"✅ POSTING POLL {poll_id} - Bot is ready, user: {bot.user}")

        # Debug channel retrieval
        poll_channel_id = getattr(poll, "channel_id", None)
        logger.debug(
            f"🔍 POSTING POLL {poll_id} - Looking for channel {poll_channel_id}"
        )
        channel = bot.get_channel(int(str(poll_channel_id)))

        if not channel:
            logger.error(
                f"❌ POSTING POLL {poll_id} - Channel {poll_channel_id} not found"
            )
            logger.debug(
                f"Available channels: {[c.id for c in bot.get_all_channels()]}"
            )
            return {"success": False, "error": f"Channel {poll_channel_id} not found"}

        # Ensure we have a text channel
        if not isinstance(channel, discord.TextChannel):
            logger.error(
                f"❌ POSTING POLL {poll_id} - Channel {poll_channel_id} is not a text channel"
            )
            return {"success": False, "error": "Channel is not a text channel"}

        logger.info(
            f"✅ POSTING POLL {poll_id} - Found channel: {channel.name} ({channel.id})"
        )

        # Debug bot permissions in channel
        bot_member = channel.guild.get_member(bot.user.id)
        if not bot_member:
            logger.error(
                f"❌ POSTING POLL {poll_id} - Bot not found as member in guild {channel.guild.name}"
            )
            return {"success": False, "error": "Bot not found as member in guild"}

        permissions = channel.permissions_for(bot_member)
        logger.debug(
            f"🔐 POSTING POLL {poll_id} - Bot permissions: send_messages={permissions.send_messages}, embed_links={permissions.embed_links}, add_reactions={permissions.add_reactions}"
        )

        if not permissions.send_messages:
            logger.error(
                f"❌ POSTING POLL {poll_id} - Bot lacks send_messages permission in {channel.name}"
            )
            return {"success": False, "error": "Bot lacks send_messages permission"}

        if not permissions.embed_links:
            logger.error(
                f"❌ POSTING POLL {poll_id} - Bot lacks embed_links permission in {channel.name}"
            )
            return {"success": False, "error": "Bot lacks embed_links permission"}

        if not permissions.add_reactions:
            logger.error(
                f"❌ POSTING POLL {poll_id} - Bot lacks add_reactions permission in {channel.name}"
            )
            return {"success": False, "error": "Bot lacks add_reactions permission"}

        # CRITICAL FIX: Refresh poll object from database to avoid DetachedInstanceError
        # The poll object passed to this function may be detached from the database session
        logger.debug(
            f"🔄 POSTING POLL {getattr(poll, 'id', 'unknown')} - Refreshing poll from database to avoid DetachedInstanceError"
        )
        db = get_db_session()
        try:
            # Eagerly load the votes relationship to avoid DetachedInstanceError
            from sqlalchemy.orm import joinedload

            fresh_poll = (
                db.query(Poll)
                .options(joinedload(Poll.votes))
                .filter(Poll.id == getattr(poll, "id"))
                .first()
            )
            if not fresh_poll:
                logger.error(
                    f"❌ POSTING POLL {getattr(poll, 'id', 'unknown')} - Poll not found in database during refresh"
                )
                return {
                    "success": False,
                    "error": "Poll not found in database during refresh",
                }

            # Use the fresh poll object for all operations
            poll = fresh_poll
            logger.debug(
                f"✅ POSTING POLL {getattr(poll, 'id', 'unknown')} - Successfully refreshed poll from database"
            )

            # Create embed with debugging while poll is still attached to session
            logger.debug(
                f"📝 POSTING POLL {getattr(poll, 'id', 'unknown')} - Creating embed"
            )
            embed = await create_poll_embed(
                poll, show_results=bool(poll.should_show_results())
            )
            logger.debug(
                f"✅ POSTING POLL {getattr(poll, 'id', 'unknown')} - Embed created successfully"
            )

        except Exception as refresh_error:
            logger.error(
                f"❌ POSTING POLL {getattr(poll, 'id', 'unknown')} - Failed to refresh poll from database: {refresh_error}"
            )
            return {
                "success": False,
                "error": f"Failed to refresh poll from database: {str(refresh_error)}",
            }
        finally:
            db.close()

        # Post image message first if poll has an image
        poll_image_path = getattr(poll, "image_path", None)
        if poll_image_path is not None and str(poll_image_path).strip():
            try:
                logger.debug(
                    f"🖼️ POSTING POLL {getattr(poll, 'id', 'unknown')} - Posting image message first"
                )

                # Prepare image message content - ensure we get the actual string value
                poll_image_message_text = getattr(poll, "image_message_text", None)
                image_content = (
                    str(poll_image_message_text) if poll_image_message_text else ""
                )

                # Create file object for Discord
                import os

                image_path_str = str(poll_image_path)
                if os.path.exists(image_path_str):
                    with open(image_path_str, "rb") as f:
                        file = discord.File(
                            f, filename=os.path.basename(image_path_str)
                        )

                        # Post image message
                        if image_content.strip():
                            await channel.send(content=image_content, file=file)
                            logger.info(
                                f"✅ POSTING POLL {poll.id} - Posted image with text: '{image_content[:50]}...'"
                            )
                        else:
                            await channel.send(file=file)
                            logger.info(
                                f"✅ POSTING POLL {poll.id} - Posted image without text"
                            )
                else:
                    logger.warning(
                        f"⚠️ POSTING POLL {poll.id} - Image file not found: {image_path_str}"
                    )

            except Exception as image_error:
                logger.error(
                    f"❌ POSTING POLL {poll.id} - Failed to post image: {image_error}"
                )
                # Continue with poll posting even if image fails

        # Embed was already created above while poll was attached to database session

        # Check if role ping is enabled and prepare content
        message_content = None
        role_ping_attempted = False
        if getattr(poll, "ping_role_enabled", False) and getattr(
            poll, "ping_role_id", None
        ):
            role_id = str(getattr(poll, "ping_role_id"))
            role_name = str(getattr(poll, "ping_role_name", "Unknown Role"))
            message_content = (
                f"<@&{role_id}> 📊 **Poll '{getattr(poll, 'name', '')}' is now open!**"
            )
            role_ping_attempted = True
            logger.info(
                f"🔔 POSTING POLL {poll.id} - Will ping role {role_name} ({role_id})"
            )

        # Post message with debugging and graceful error handling for role pings
        logger.info(f"📤 POSTING POLL {poll.id} - Sending message to {channel.name}")

        try:
            if message_content:
                message = await channel.send(content=message_content, embed=embed)
                logger.info(
                    f"✅ POSTING POLL {poll.id} - Message sent with role ping, ID: {message.id}"
                )
            else:
                message = await channel.send(embed=embed)
                logger.info(
                    f"✅ POSTING POLL {poll.id} - Message sent successfully, ID: {message.id}"
                )
        except discord.Forbidden as role_error:
            if role_ping_attempted:
                # Role ping failed due to permissions, try without role ping
                logger.warning(
                    f"⚠️ POSTING POLL {poll.id} - Role ping failed due to permissions, posting without role ping: {role_error}"
                )
                try:
                    message = await channel.send(embed=embed)
                    logger.info(
                        f"✅ POSTING POLL {poll.id} - Message sent without role ping (fallback), ID: {message.id}"
                    )
                except Exception as fallback_error:
                    logger.error(
                        f"❌ POSTING POLL {poll.id} - Fallback message posting also failed: {fallback_error}"
                    )
                    raise fallback_error
            else:
                # Not a role ping issue, re-raise the error
                raise role_error

        # Add reactions for voting with debugging
        poll_emojis = poll.emojis
        poll_options = poll.options
        print(
            f"😀 POSTING POLL {poll.id} - Retrieved emojis from database: {poll_emojis}"
        )
        print(
            f"📝 POSTING POLL {poll.id} - Retrieved options from database: {poll_options}"
        )
        logger.info(
            f"😀 POSTING POLL {poll.id} - Retrieved emojis from database: {poll_emojis}"
        )
        logger.info(
            f"📝 POSTING POLL {poll.id} - Retrieved options from database: {poll_options}"
        )
        logger.debug(
            f"😀 POSTING POLL {poll.id} - Adding {len(poll.options)} reactions"
        )

        # Import emoji handler for Unicode emoji preparation
        from .discord_emoji_handler import DiscordEmojiHandler

        emoji_handler = DiscordEmojiHandler(bot)

        for i in range(len(poll.options)):
            emoji = poll.emojis[i] if i < len(poll.emojis or []) else POLL_EMOJIS[i]

            # Prepare emoji for reaction (handles Unicode emoji variation selectors)
            prepared_emoji = emoji_handler.prepare_emoji_for_reaction(emoji)

            try:
                await message.add_reaction(prepared_emoji)
                print(
                    f"✅ POSTING POLL {poll.id} - Added reaction {prepared_emoji} (original: {emoji}) for option {i}: '{poll.options[i]}'"
                )
                logger.info(
                    f"✅ POSTING POLL {poll.id} - Added reaction {prepared_emoji} (original: {emoji}) for option {i}: '{poll.options[i]}'"
                )
                logger.debug(
                    f"✅ POSTING POLL {poll.id} - Added reaction {prepared_emoji} for option {i}"
                )
            except Exception as reaction_error:
                print(
                    f"❌ POSTING POLL {poll.id} - Failed to add reaction {prepared_emoji} (original: {emoji}): {reaction_error}"
                )
                logger.error(
                    f"❌ POSTING POLL {poll.id} - Failed to add reaction {prepared_emoji} (original: {emoji}): {reaction_error}"
                )

        # Update poll with message ID
        poll_id = getattr(poll, "id")
        logger.debug(f"💾 POSTING POLL {poll_id} - Updating database with message ID")
        db = get_db_session()
        try:
            # Update poll in database
            poll_to_update = db.query(Poll).filter(Poll.id == poll_id).first()
            if poll_to_update:
                setattr(poll_to_update, "message_id", str(message.id))
                setattr(poll_to_update, "status", "active")
                db.commit()
                logger.info(
                    f"✅ POSTING POLL {poll_id} - Database updated, poll is now ACTIVE"
                )
                logger.info(
                    f"🎉 POSTING POLL {poll_id} - Successfully posted to channel {channel.name}"
                )
                return {
                    "success": True,
                    "message_id": message.id,
                    "message": "Poll posted successfully",
                }
            else:
                logger.error(f"❌ POSTING POLL {poll_id} - Poll not found for update")
                return {"success": False, "error": "Poll not found for update"}
        except Exception as db_error:
            logger.error(
                f"❌ POSTING POLL {poll_id} - Database update failed: {db_error}"
            )
            db.rollback()
            return {
                "success": False,
                "error": f"Database update failed: {str(db_error)}",
            }
        finally:
            db.close()

    except discord.Forbidden as e:
        logger.error(
            f"❌ POSTING POLL {getattr(poll, 'id', 'unknown')} - Discord Forbidden error: {e}"
        )
        # Send DM notification to bot owner about permission error
        try:
            from .error_handler import BotOwnerNotifier

            await BotOwnerNotifier.send_error_dm(
                bot,
                e,
                "Poll Posting - Permission Error",
                {
                    "poll_id": getattr(poll, "id"),
                    "poll_name": str(getattr(poll, "name", "")),
                    "server_id": str(getattr(poll, "server_id", "")),
                    "channel_id": str(getattr(poll, "channel_id", "")),
                },
            )
        except Exception as dm_error:
            logger.error(f"Failed to send DM notification: {dm_error}")
        return {"success": False, "error": f"Discord permission error: {str(e)}"}
    except discord.HTTPException as e:
        logger.error(
            f"❌ POSTING POLL {getattr(poll, 'id', 'unknown')} - Discord HTTP error: {e}"
        )
        # Send DM notification to bot owner about HTTP error
        try:
            from .error_handler import BotOwnerNotifier

            await BotOwnerNotifier.send_error_dm(
                bot,
                e,
                "Poll Posting - Discord API Error",
                {
                    "poll_id": getattr(poll, "id"),
                    "poll_name": str(getattr(poll, "name", "")),
                    "server_id": str(getattr(poll, "server_id", "")),
                    "channel_id": str(getattr(poll, "channel_id", "")),
                },
            )
        except Exception as dm_error:
            logger.error(f"Failed to send DM notification: {dm_error}")
        return {"success": False, "error": f"Discord HTTP error: {str(e)}"}
    except Exception as e:
        logger.error(
            f"❌ POSTING POLL {getattr(poll, 'id', 'unknown')} - Unexpected error: {e}"
        )
        logger.exception(
            f"Full traceback for poll {getattr(poll, 'id', 'unknown')} posting error:"
        )
        # Send DM notification to bot owner about unexpected error
        try:
            from .error_handler import BotOwnerNotifier

            await BotOwnerNotifier.send_error_dm(
                bot,
                e,
                "Poll Posting - Unexpected Error",
                {
                    "poll_id": getattr(poll, "id"),
                    "poll_name": str(getattr(poll, "name", "")),
                    "server_id": str(getattr(poll, "server_id", "")),
                    "channel_id": str(getattr(poll, "channel_id", "")),
                    "error_type": type(e).__name__,
                },
            )
        except Exception as dm_error:
            logger.error(f"Failed to send DM notification: {dm_error}")
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


async def update_poll_message(bot: commands.Bot, poll: Poll):
    """Update poll message with current results"""
    try:
        poll_message_id = getattr(poll, "message_id", None)
        if not poll_message_id:
            return False

        poll_channel_id = getattr(poll, "channel_id", None)
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

        # Update embed - ALWAYS show results for closed polls
        poll_status = str(getattr(poll, "status", "unknown"))
        show_results = poll_status == "closed" or bool(poll.should_show_results())
        
        embed = await create_poll_embed(poll, show_results=show_results)
        await message.edit(embed=embed)

        logger.debug(f"Updated poll message for poll {getattr(poll, 'id')} (status: {poll_status}, show_results: {show_results})")
        return True

    except Exception as e:
        logger.error(f"Error updating poll message {poll.id}: {e}")
        return False


async def create_poll_results_embed(poll: Poll) -> discord.Embed:
    """Create comprehensive results embed for closed polls - ALWAYS shows full breakdown"""
    poll_name = str(getattr(poll, "name", ""))
    poll_question = str(getattr(poll, "question", ""))

    embed = discord.Embed(
        title=f"🏁 Poll Results: {poll_name}",
        description=poll_question,
        color=0xFF0000,  # Red for closed
        timestamp=datetime.now(pytz.UTC),
    )

    # Get results data
    results = poll.get_results()
    total_votes = poll.get_total_votes()

    # Build comprehensive results breakdown
    results_text = ""

    if total_votes > 0:
        for i, option in enumerate(poll.options):
            emoji = poll.emojis[i] if i < len(poll.emojis) else POLL_EMOJIS[i]
            votes = results.get(i, 0)
            percentage = (votes / total_votes * 100) if total_votes > 0 else 0

            # Create enhanced progress bar
            bar_length = 15
            filled = int((percentage / 100) * bar_length)
            bar = (
                "█" * filled + "░" * (bar_length - filled)
                if filled > 0
                else "░" * bar_length
            )

            # Format the option with enhanced styling
            results_text += f"{emoji} **{option}**\n"
            results_text += f"`{bar}` **{votes}** votes (**{percentage:.1f}%**)\n\n"
    else:
        # Show options even with no votes
        for i, option in enumerate(poll.options):
            emoji = poll.emojis[i] if i < len(poll.emojis) else POLL_EMOJIS[i]
            bar = "░" * 15  # Empty bar
            results_text += f"{emoji} **{option}**\n"
            results_text += f"`{bar}` **0** votes (**0.0%**)\n\n"

    embed.add_field(
        name="📊 Final Results", value=results_text or "No votes cast", inline=False
    )

    # Total votes
    embed.add_field(name="🗳️ Total Votes", value=f"**{total_votes}**", inline=True)

    # Winner announcement
    if total_votes > 0:
        winners = poll.get_winner()
        if winners:
            if len(winners) == 1:
                winner_emoji = (
                    poll.emojis[winners[0]]
                    if winners[0] < len(poll.emojis)
                    else POLL_EMOJIS[winners[0]]
                )
                winner_option = poll.options[winners[0]]
                winner_votes = results.get(winners[0], 0)
                winner_percentage = (
                    (winner_votes / total_votes * 100) if total_votes > 0 else 0
                )
                embed.add_field(
                    name="🏆 Winner",
                    value=f"{winner_emoji} **{winner_option}**\n{winner_votes} votes ({winner_percentage:.1f}%)",
                    inline=True,
                )
            else:
                # Multiple winners (tie)
                winner_text = "**TIE!**\n"
                for winner_idx in winners:
                    winner_emoji = (
                        poll.emojis[winner_idx]
                        if winner_idx < len(poll.emojis)
                        else POLL_EMOJIS[winner_idx]
                    )
                    winner_option = poll.options[winner_idx]
                    winner_votes = results.get(winner_idx, 0)
                    winner_percentage = (
                        (winner_votes / total_votes * 100) if total_votes > 0 else 0
                    )
                    winner_text += f"{winner_emoji} {winner_option} ({winner_votes} votes, {winner_percentage:.1f}%)\n"
                embed.add_field(name="🏆 Winners", value=winner_text, inline=True)
    else:
        embed.add_field(name="🏆 Winner", value="No votes cast", inline=True)

    # Poll type indicator
    poll_anonymous = bool(getattr(poll, "anonymous", False))
    poll_multiple_choice = bool(getattr(poll, "multiple_choice", False))

    poll_type = []
    if poll_anonymous:
        poll_type.append("🔒 Anonymous")
    if poll_multiple_choice:
        poll_type.append("☑️ Multiple Choice")

    if poll_type:
        embed.add_field(name="📋 Poll Type", value=" • ".join(poll_type), inline=False)

    embed.set_footer(text="Poll completed • Created by Polly")
    return embed


async def post_poll_results(bot: commands.Bot, poll: Poll):
    """Post final results when poll closes - always shows full breakdown for all polls"""
    try:
        poll_channel_id = getattr(poll, "channel_id", None)
        channel = bot.get_channel(int(str(poll_channel_id)))
        if not channel:
            return False

        # Ensure we have a text channel
        if not isinstance(channel, discord.TextChannel):
            return False

        # Create comprehensive results embed - ALWAYS show results for closed polls
        embed = await create_poll_results_embed(poll)
        poll_name = str(getattr(poll, "name", ""))

        # Check if role ping is enabled and prepare content
        message_content = f"📊 **Poll '{poll_name}' has ended!**"
        role_ping_attempted = False
        if getattr(poll, "ping_role_enabled", False) and getattr(
            poll, "ping_role_id", None
        ):
            role_id = str(getattr(poll, "ping_role_id"))
            role_name = str(getattr(poll, "ping_role_name", "Unknown Role"))
            message_content = f"<@&{role_id}> {message_content}"
            role_ping_attempted = True
            logger.info(
                f"🔔 POLL RESULTS {getattr(poll, 'id')} - Will ping role {role_name} ({role_id}) for poll closure"
            )

        # Post results message with graceful error handling for role pings
        try:
            await channel.send(content=message_content, embed=embed)
        except discord.Forbidden as role_error:
            if role_ping_attempted:
                # Role ping failed due to permissions, try without role ping
                logger.warning(
                    f"⚠️ POLL RESULTS {getattr(poll, 'id')} - Role ping failed due to permissions, posting without role ping: {role_error}"
                )
                try:
                    fallback_content = f"📊 **Poll '{poll_name}' has ended!**"
                    await channel.send(content=fallback_content, embed=embed)
                    logger.info(
                        f"✅ POLL RESULTS {getattr(poll, 'id')} - Results posted without role ping (fallback)"
                    )
                except Exception as fallback_error:
                    logger.error(
                        f"❌ POLL RESULTS {getattr(poll, 'id')} - Fallback results posting also failed: {fallback_error}"
                    )
                    raise fallback_error
            else:
                # Not a role ping issue, re-raise the error
                raise role_error

        logger.info(f"Posted final results for poll {getattr(poll, 'id')}")
        return True

    except Exception as e:
        logger.error(f"Error posting poll results {poll.id}: {e}")
        return False


async def send_vote_confirmation_dm(
    bot: commands.Bot, poll: Poll, user_id: str, option_index: int, vote_action: str
) -> bool:
    """
    Send a DM to the user confirming their vote with poll information.

    Args:
        bot: Discord bot instance
        poll: Poll object
        user_id: Discord user ID who voted
        option_index: Index of the option they voted for
        vote_action: Action taken ("added", "removed", "updated", "created")

    Returns:
        bool: True if DM was sent successfully, False otherwise
    """
    try:
        # Get the user object
        user = bot.get_user(int(user_id))
        if not user:
            try:
                user = await bot.fetch_user(int(user_id))
            except (discord.NotFound, discord.HTTPException):
                logger.warning(
                    f"Could not find user {user_id} for vote confirmation DM"
                )
                return False

        if not user:
            logger.warning(f"User {user_id} not found for vote confirmation DM")
            return False

        # Create confirmation embed
        poll_name = str(getattr(poll, "name", ""))
        poll_question = str(getattr(poll, "question", ""))
        selected_option = (
            poll.options[option_index]
            if option_index < len(poll.options)
            else "Unknown Option"
        )
        selected_emoji = (
            poll.emojis[option_index]
            if option_index < len(poll.emojis)
            else POLL_EMOJIS[option_index]
        )

        # Determine action message
        if vote_action == "added":
            action_description = (
                f"You voted for: {selected_emoji} **{selected_option}**"
            )
        elif vote_action == "removed":
            action_description = (
                f"You removed your vote for: {selected_emoji} **{selected_option}**"
            )
        elif vote_action == "updated":
            action_description = (
                f"You changed your vote to: {selected_emoji} **{selected_option}**"
            )
        elif vote_action == "created":
            action_description = (
                f"You voted for: {selected_emoji} **{selected_option}**"
            )
        else:
            action_description = f"Your vote: {selected_emoji} **{selected_option}**"

        # Create embed with poll information
        embed = discord.Embed(
            title="🗳️ Vote Confirmation",
            description=action_description,
            color=0x00FF00,  # Green for confirmation
            timestamp=datetime.now(pytz.UTC),
        )

        # Add poll details
        embed.add_field(
            name="📊 Poll", value=f"**{poll_name}**\n{poll_question}", inline=False
        )

        # Add all poll options for reference
        options_text = ""
        for i, option in enumerate(poll.options):
            emoji = poll.emojis[i] if i < len(poll.emojis) else POLL_EMOJIS[i]
            if i == option_index:
                # Highlight the selected option
                options_text += f"{emoji} **{option}** ← Your choice\n"
            else:
                options_text += f"{emoji} {option}\n"

        embed.add_field(name="📝 All Options", value=options_text, inline=False)

        # Add poll type information
        poll_anonymous = bool(getattr(poll, "anonymous", False))
        poll_multiple_choice = bool(getattr(poll, "multiple_choice", False))

        poll_info = []
        if poll_anonymous:
            poll_info.append("🔒 Anonymous")
        if poll_multiple_choice:
            poll_info.append("☑️ Multiple Choice")

        if poll_info:
            embed.add_field(
                name="ℹ️ Poll Type", value=" • ".join(poll_info), inline=True
            )

        # Add server and channel info
        server_name = str(getattr(poll, "server_name", "Unknown Server"))
        channel_name = str(getattr(poll, "channel_name", "Unknown Channel"))
        embed.add_field(
            name="📍 Location",
            value=f"**{server_name}** → #{channel_name}",
            inline=True,
        )

        embed.set_footer(text="Vote confirmation • Created by Polly")

        # Send the DM
        await user.send(embed=embed)

        logger.info(
            f"✅ Sent vote confirmation DM to user {user_id} for poll {getattr(poll, 'id')}"
        )
        return True

    except discord.Forbidden:
        logger.info(f"⚠️ User {user_id} has DMs disabled, cannot send vote confirmation")
        return False
    except discord.HTTPException as e:
        logger.warning(f"⚠️ Failed to send vote confirmation DM to user {user_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Error sending vote confirmation DM to user {user_id}: {e}")
        return False


async def get_guild_roles(bot: commands.Bot, guild_id: str) -> List[Dict[str, Any]]:
    """Get roles for a guild that can be mentioned/pinged by the bot"""
    roles = []

    if not bot or not bot.guilds:
        logger.warning("Bot not ready or no guilds available")
        return roles

    try:
        guild = bot.get_guild(int(guild_id))
        if not guild:
            logger.warning(f"Guild {guild_id} not found")
            return roles

        # Check if bot has admin permissions in this guild
        if not bot.user:
            logger.warning("Bot user is None")
            return roles

        bot_member = guild.get_member(bot.user.id)
        if not bot_member:
            logger.warning(f"Bot not found as member in guild {guild.name}")
            return roles

        bot_has_admin = bot_member.guild_permissions.administrator
        bot_can_mention_everyone = bot_member.guild_permissions.mention_everyone

        logger.debug(
            f"Bot permissions in {guild.name}: admin={bot_has_admin}, mention_everyone={bot_can_mention_everyone}"
        )

        # Get roles based on bot's permissions
        for role in guild.roles:
            try:
                # Always skip @everyone role
                if role.name == "@everyone":
                    continue

                # Skip managed roles (like bot roles) unless bot has admin
                if role.managed and not bot_has_admin:
                    continue

                # Determine if bot can ping this role
                can_ping_role = False

                if bot_has_admin:
                    # Bot with admin can ping any role (except @everyone)
                    can_ping_role = True
                elif role.mentionable:
                    # Bot can ping mentionable roles
                    can_ping_role = True
                elif bot_can_mention_everyone and not role.managed:
                    # Bot with mention_everyone can ping non-managed roles
                    can_ping_role = True

                if can_ping_role:
                    roles.append(
                        {
                            "id": str(role.id),
                            "name": role.name,
                            "color": str(role.color)
                            if role.color != discord.Color.default()
                            else None,
                            "position": role.position,
                            "mentionable": role.mentionable,
                            "managed": role.managed,
                            "can_ping": True,  # All roles in this list can be pinged by the bot
                        }
                    )
            except Exception as e:
                logger.warning(f"Error processing role {role.name}: {e}")
                continue

        # Sort roles by position (higher position = higher in hierarchy)
        roles.sort(key=lambda x: x.get("position", 0), reverse=True)

        logger.debug(
            f"Found {len(roles)} pingable roles in guild {guild.name} (bot_admin={bot_has_admin})"
        )
        return roles

    except Exception as e:
        logger.error(f"Error getting roles for guild {guild_id}: {e}")
        return roles


def user_has_admin_permissions(member: discord.Member) -> bool:
    """Check if user has admin permissions in the guild"""
    return (
        member.guild_permissions.administrator
        or member.guild_permissions.manage_guild
        or member.guild_permissions.manage_channels
    )
