"""
Discord Utility Functions
Helper functions for Discord bot operations, guild/channel management, and poll posting.
"""

import discord
from discord.ext import commands
from datetime import datetime
from typing import List, Dict, Any
import pytz
import asyncio

# Handle both relative and absolute imports for direct execution
try:
    from .database import get_db_session, Guild, Channel, Poll, POLL_EMOJIS
    from .debug_config import get_debug_logger
except ImportError:
    # Fallback for direct execution
    import sys
    import os
    sys.path.insert(0, os.path.dirname(__file__))
    from database import get_db_session, Guild, Channel, Poll, POLL_EMOJIS
    from debug_config import get_debug_logger

logger = get_debug_logger(__name__)


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

    # Get the appropriate timestamp based on poll status and timezone
    poll_timezone = str(getattr(poll, "timezone", "UTC"))
    poll_id = getattr(poll, "id", "unknown")
    
    logger.debug(f"🔍 EMBED TIMEZONE - Poll {poll_id}: status={poll_status}, timezone='{poll_timezone}'")
    
    # For closed polls, use close time; for others, use open time
    # Use the timezone-aware properties from the Poll model
    if poll_status == "closed":
        poll_timestamp = poll.close_time_aware
    else:
        poll_timestamp = poll.open_time_aware
    
    # The timestamp should now always be timezone-aware thanks to the Poll model properties
    # This check should no longer be needed, but keeping as a safety net
    if poll_timestamp and poll_timestamp.tzinfo is None:
        logger.warning(f"⚠️ EMBED TIMEZONE - Poll {poll_id} has timezone-naive timestamp, localizing to UTC")
        poll_timestamp = pytz.UTC.localize(poll_timestamp)
    
    # Convert timestamp to poll's timezone for display if specified and different from UTC
    if poll_timezone and poll_timezone != "UTC":
        try:
            # Validate and normalize timezone first
            from .utils import validate_and_normalize_timezone
            normalized_tz = validate_and_normalize_timezone(poll_timezone)
            
            if normalized_tz != "UTC":
                tz = pytz.timezone(normalized_tz)
                # Convert to the poll's timezone for display
                poll_timestamp = poll_timestamp.astimezone(tz)
                logger.debug(f"✅ EMBED TIMEZONE - Poll {poll_id} timestamp converted to {normalized_tz}")
            else:
                logger.debug(f"ℹ️ EMBED TIMEZONE - Poll {poll_id} using UTC (normalized from {poll_timezone})")
            
        except Exception as e:
            logger.error(f"❌ EMBED TIMEZONE - Poll {poll_id} timezone conversion failed: {e}")
            # Ensure we have a valid UTC timestamp as fallback
            if poll_timestamp.tzinfo != pytz.UTC:
                poll_timestamp = poll_timestamp.astimezone(pytz.UTC)
            logger.info(f"⚠️ EMBED TIMEZONE - Poll {poll_id} using UTC fallback")
    else:
        logger.debug(f"ℹ️ EMBED TIMEZONE - Poll {poll_id} using UTC timezone")

    # Add anonymity indicator to title for better visibility
    poll_anonymous = bool(getattr(poll, "anonymous", False))
    poll_title = f"{status_emoji} {str(getattr(poll, 'name', ''))}"
    if poll_anonymous:
        poll_title += " 🔒"  # Add lock icon to title for anonymous polls
    
    embed = discord.Embed(
        title=poll_title,
        description=str(getattr(poll, "question", "")),
        color=color,
        timestamp=poll_timestamp,
    )
    
    # Add spacing after description for better visual separation
    embed.add_field(name="", value="", inline=False)

    # For closed polls, use a cleaner layout without duplicates
    if poll_status == "closed" and show_results:
        # Show results with enhanced progress bars and percentages
        results = poll.get_results()
        total_votes = poll.get_total_votes()
        option_text = ""

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
            name="📊 Results",
            value=option_text or "No votes cast",
            inline=False,
        )

        # Single total votes display (no duplicate)
        embed.add_field(
            name="🗳️ Total Votes", value=f"**{total_votes}**", inline=True
        )

        # Winner announcement for closed polls
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
            # Show "No votes cast" for closed polls with no votes
            embed.add_field(name="🏆 Winner", value="No votes cast", inline=True)

        # Add poll type information for closed polls (consolidated, no duplicates)
        poll_anonymous = bool(getattr(poll, "anonymous", False))
        poll_multiple_choice = bool(getattr(poll, "multiple_choice", False))

        poll_type = []
        if poll_anonymous:
            poll_type.append("🔒 Anonymous")
        if poll_multiple_choice:
            poll_type.append("☑️ Multiple Choice")

        if poll_type:
            embed.add_field(name="📋 Poll Type", value=" • ".join(poll_type), inline=False)

        # No voting instructions for closed polls
        # No duplicate anonymous poll information for closed polls

    elif show_results:
        # Active/scheduled polls with results
        results = poll.get_results()
        total_votes = poll.get_total_votes()
        option_text = ""

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
            name="📈 Live Results",
            value=option_text or "No votes yet",
            inline=False,
        )

        # Enhanced total votes display
        if total_votes > 0:
            embed.add_field(
                name="🗳️ Total Votes", value=f"**{total_votes}**", inline=True
            )

        # Add choice limit information for active/scheduled polls
        poll_multiple_choice = bool(getattr(poll, "multiple_choice", False))
        if poll_multiple_choice:
            # For multiple choice, use configurable max_choices or fall back to total options
            max_choices = getattr(poll, "max_choices", None)
            if max_choices and max_choices > 0:
                num_choices = max_choices
            else:
                # Fallback to total number of options if max_choices not set
                num_choices = len(poll.options)
            choice_info = f"🔢 You may make up to **{num_choices} choices** in this poll"
        else:
            choice_info = "🔢 You may make **1 choice** in this poll"
            
        embed.add_field(name="", value=choice_info, inline=False)

        # Always show total votes for active polls
        total_votes = poll.get_total_votes()

        poll_anonymous = bool(getattr(poll, "anonymous", False))
        if poll_anonymous:
            # Consolidated anonymous poll display for active polls
            total_votes = poll.get_total_votes()
            anonymous_text = f"🔒 Anonymous Poll - Results will be revealed when poll ends\n🗳️ **{total_votes}** votes cast so far"
            embed.add_field(name="", value=anonymous_text, inline=False)
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
                        f"{emoji} **{option}** `{bar}` **{votes}** ({percentage:.1f}%)\n"
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
                    results_text += f"{emoji} **{option}** `{bar}` **0** (0.0%)\n"

                embed.add_field(
                    name="📈 Live Results", value=results_text, inline=False
                )
    else:
        # Just show options without results (for scheduled polls) - with better spacing
        option_text = ""
        for i, option in enumerate(poll.options):
            emoji = poll.emojis[i] if i < len(poll.emojis) else POLL_EMOJIS[i]
            option_text += f"\n** {emoji} {option}**\n"  # Double newline for more space
                # Add spacing after options section
        embed.add_field(name="📝 Options", value="", inline=False)
        embed.add_field(name="", value=option_text.rstrip(), inline=False)
        

        
        # Consolidated poll type and anonymous info for scheduled polls
        poll_anonymous = bool(getattr(poll, "anonymous", False))
        poll_multiple_choice = bool(getattr(poll, "multiple_choice", False))

        if poll_anonymous:
            total_votes = poll.get_total_votes()
            anonymous_text = f"🔒 Anonymous Poll - Results will be revealed when poll ends\n🗳️ **{total_votes}** votes cast so far"
            if poll_multiple_choice:
                anonymous_text += "\n☑️ Multiple Choice"
            embed.add_field(name="", value=anonymous_text, inline=False)
        elif poll_multiple_choice:
            embed.add_field(name="", value="☑️ Multiple Choice Poll", inline=False)

    # Add timing information with timezone support
    if poll_status == "scheduled":
        # Only show opens time for scheduled polls, with timezone-specific time
        poll_timezone = str(getattr(poll, "timezone", "UTC"))
        try:
            # Validate and normalize timezone first
            from .utils import validate_and_normalize_timezone

            normalized_tz = validate_and_normalize_timezone(poll_timezone)
            
            if normalized_tz != "UTC":
                tz = pytz.timezone(normalized_tz)
                # Use timezone-aware property instead of raw database field
                open_time = poll.open_time_aware
                local_open = open_time.astimezone(tz)
                embed.add_field(
                    name=f"Opens ({normalized_tz})",
                    value=local_open.strftime("%Y-%m-%d %I:%M %p"),
                    inline=True,
                )
            else:
                # Use UTC formatting with timezone-aware property
                open_time = poll.open_time_aware
                embed.add_field(
                    name="Opens (UTC)",
                    value=open_time.strftime("%Y-%m-%d %I:%M %p"),
                    inline=True,
                )
        except Exception as e:
            logger.error(f"❌ EMBED TIMEZONE - Poll {poll_id} open time formatting failed: {e}")
            # Fallback to UTC
            try:
                open_time = poll.open_time
                if open_time.tzinfo is None:
                    open_time = pytz.UTC.localize(open_time)
                embed.add_field(
                    name="Opens (UTC)",
                    value=open_time.strftime("%Y-%m-%d %I:%M %p"),
                    inline=True,
                )
            except Exception as fallback_error:
                logger.error(f"❌ EMBED TIMEZONE - Poll {poll_id} UTC fallback failed: {fallback_error}")

    # Show close time for scheduled and active polls only (not closed polls)
    if poll_status in ["scheduled", "active"]:
        poll_timezone = str(getattr(poll, "timezone", "UTC"))
        try:
            # Use the new helper function to format closing time with Today/Tomorrow
            from .utils import format_poll_closing_time, validate_and_normalize_timezone
            
            # Use timezone-aware property instead of raw database field
            close_time = poll.close_time_aware
            
            formatted_time = format_poll_closing_time(close_time, poll_timezone)
            normalized_tz = validate_and_normalize_timezone(poll_timezone)
            
            embed.add_field(
                name=f"Closes ({normalized_tz})",
                value=formatted_time,
                inline=True,
            )
        except Exception as e:
            logger.error(f"❌ EMBED TIMEZONE - Poll {poll_id} close time formatting failed: {e}")
            # Fallback to UTC
            try:
                close_time = poll.close_time
                if close_time.tzinfo is None:
                    close_time = pytz.UTC.localize(close_time)
                embed.add_field(
                    name="Closes (UTC)",
                    value=close_time.strftime("%Y-%m-%d %I:%M %p"),
                    inline=True,
                )
            except Exception as fallback_error:
                logger.error(f"❌ EMBED TIMEZONE - Poll {poll_id} close time UTC fallback failed: {fallback_error}")

    # Add poll info in footer without Poll ID
    embed.set_footer(text="Created by Polly")

    return embed


async def post_poll_to_channel(bot: commands.Bot, poll_or_id, message_content: str = None):
    """Post a poll to its designated Discord channel with comprehensive debugging and validation

    Args:
        bot: Discord bot instance
        poll_or_id: Either a Poll object or poll_id (int)
        message_content: Optional message content to include above the embed (e.g., role mentions)

    Returns:
        Dict with success status and message_id if successful, or error details if failed
    """
    # Handle both Poll object and poll_id
    if isinstance(poll_or_id, int):
        poll_id = poll_or_id
        logger.info(
            f"🚀 POSTING POLL {poll_id} - Starting post_poll_to_channel (from poll_id)"
        )

        # Fetch poll from database with explicit field loading
        db = get_db_session()
        try:
            from sqlalchemy.orm import joinedload
            from sqlalchemy import text

            # First, get the poll with all fields using a direct query to ensure all columns are loaded
            poll_data = db.execute(
                text("""
                    SELECT id, name, question, options_json, emojis_json, server_id, server_name, 
                           channel_id, channel_name, open_time, close_time, timezone, 
                           anonymous, multiple_choice, ping_role_enabled, ping_role_id, 
                           ping_role_name, image_path, image_message_text, status, 
                           message_id, creator_id, created_at
                    FROM polls WHERE id = :poll_id
                """),
                {"poll_id": poll_id}
            ).fetchone()
            
            if not poll_data:
                logger.error(f"❌ POSTING POLL {poll_id} - Poll not found in database")
                return {"success": False, "error": "Poll not found in database"}
            
            # Now get the ORM object with votes loaded
            poll = (
                db.query(Poll)
                .options(joinedload(Poll.votes))
                .filter(Poll.id == poll_id)
                .first()
            )
            
            if not poll:
                logger.error(f"❌ POSTING POLL {poll_id} - Poll ORM object not found")
                return {"success": False, "error": "Poll ORM object not found"}
            
            # Ensure role ping data is correctly set from the direct query
            if poll_data:
                logger.info("🔔 ROLE PING INITIAL LOAD - Direct query results:")
                logger.info(f"🔔 ROLE PING INITIAL LOAD - ping_role_enabled: {poll_data.ping_role_enabled}")
                logger.info(f"🔔 ROLE PING INITIAL LOAD - ping_role_id: {poll_data.ping_role_id}")
                logger.info(f"🔔 ROLE PING INITIAL LOAD - ping_role_name: {poll_data.ping_role_name}")
                
                # Force set the role ping attributes from the direct query to ensure they're correct
                if poll_data.ping_role_enabled and poll_data.ping_role_id:
                    setattr(poll, "ping_role_enabled", bool(poll_data.ping_role_enabled))
                    setattr(poll, "ping_role_id", poll_data.ping_role_id)
                    setattr(poll, "ping_role_name", poll_data.ping_role_name)
                    logger.info("🔔 ROLE PING INITIAL LOAD - ✅ Forced role ping data from direct query")
                else:
                    logger.info("🔔 ROLE PING INITIAL LOAD - No role ping data in direct query")
            else:
                logger.error("🔔 ROLE PING INITIAL LOAD - poll_data is None")
                
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

        # Create embed
        embed = await create_poll_embed(poll, show_results=bool(poll.should_show_results()))

        # Post message with optional content above embed
        message = await channel.send(content=message_content, embed=embed)
        
        # Add reactions for voting
        for i in range(len(poll.options)):
            emoji = poll.emojis[i] if i < len(poll.emojis or []) else POLL_EMOJIS[i]
            try:
                await message.add_reaction(emoji)
            except Exception as reaction_error:
                logger.error(f"Failed to add reaction {emoji}: {reaction_error}")

        # Update poll with message ID
        db = get_db_session()
        try:
            poll_to_update = db.query(Poll).filter(Poll.id == getattr(poll, "id")).first()
            if poll_to_update:
                setattr(poll_to_update, "message_id", str(message.id))
                setattr(poll_to_update, "status", "active")
                db.commit()
                return {
                    "success": True,
                    "message_id": message.id,
                    "message": "Poll posted successfully",
                }
        except Exception as db_error:
            logger.error(f"Database update failed: {db_error}")
            db.rollback()
            return {"success": False, "error": f"Database update failed: {str(db_error)}"}
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error posting poll: {e}")
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


async def update_poll_message(bot: commands.Bot, poll: Poll):
    """Update poll message with current results and send role ping notification for status changes"""
    poll_id = getattr(poll, "id", "unknown")
    try:
        logger.info(f"🔄 UPDATE MESSAGE - Starting update for poll {poll_id}")
        
        poll_message_id = getattr(poll, "message_id", None)
        if not poll_message_id:
            logger.error(f"❌ UPDATE MESSAGE - Poll {poll_id} has no message_id")
            return False

        poll_channel_id = getattr(poll, "channel_id", None)
        if not poll_channel_id:
            logger.error(f"❌ UPDATE MESSAGE - Poll {poll_id} has no channel_id")
            return False
            
        channel = bot.get_channel(int(str(poll_channel_id)))
        if not channel:
            logger.error(f"❌ UPDATE MESSAGE - Channel {poll_channel_id} not found for poll {poll_id}")
            return False

        # Ensure we have a text channel
        if not isinstance(channel, discord.TextChannel):
            logger.error(f"❌ UPDATE MESSAGE - Channel {poll_channel_id} is not a text channel for poll {poll_id}")
            return False

        try:
            message = await channel.fetch_message(int(str(poll_message_id)))
        except discord.NotFound:
            logger.error(f"❌ UPDATE MESSAGE - Poll message {poll_message_id} not found for poll {poll_id}")
            return False
        except Exception as fetch_error:
            logger.error(f"❌ UPDATE MESSAGE - Error fetching message {poll_message_id} for poll {poll_id}: {fetch_error}")
            return False

        # Update embed - ALWAYS show results for closed polls, regardless of anonymity
        poll_status = str(getattr(poll, "status", "unknown"))
        
        if poll_status == "closed":
            show_results = True
        else:
            show_results = bool(poll.should_show_results())
        
        embed = await create_poll_embed(poll, show_results=show_results)
        await message.edit(embed=embed)

        # CRITICAL: Restore reactions for reopened polls
        if poll_status == "active":
            await _ensure_poll_reactions_restored(message, poll, bot)

        return True

    except Exception as e:
        logger.error(f"Error updating poll message {poll.id}: {e}")
        return False


async def _ensure_poll_reactions_restored(message: discord.Message, poll: Poll, bot: commands.Bot):
    """Ensure all required reactions are present on a poll message (for reopened polls)"""
    try:
        poll_id = getattr(poll, "id", "unknown")
        logger.info(f"🔄 RESTORE REACTIONS - Starting reaction restoration for poll {poll_id}")
        
        # Get current reactions on the message
        current_reactions = {str(reaction.emoji) for reaction in message.reactions}
        
        # Get required reactions from poll
        poll_emojis = getattr(poll, "emojis", [])
        poll_options = getattr(poll, "options", [])
        
        if not poll_emojis or not poll_options:
            logger.warning(f"⚠️ RESTORE REACTIONS - Poll {poll_id} missing emojis or options")
            return
        
        # Add missing reactions
        reactions_added = 0
        for i in range(len(poll_options)):
            emoji = poll_emojis[i] if i < len(poll_emojis) else POLL_EMOJIS[i]
            
            if emoji not in current_reactions:
                try:
                    await message.add_reaction(emoji)
                    reactions_added += 1
                    logger.info(f"✅ RESTORE REACTIONS - Added missing reaction {emoji} to poll {poll_id}")
                    
                    # Rate limit protection
                    await asyncio.sleep(0.1)
                    
                except Exception as reaction_error:
                    logger.error(f"❌ RESTORE REACTIONS - Failed to add reaction {emoji} to poll {poll_id}: {reaction_error}")
        
        if reactions_added > 0:
            logger.info(f"🎉 RESTORE REACTIONS - Successfully restored {reactions_added} reactions for poll {poll_id}")
        else:
            logger.debug(f"✅ RESTORE REACTIONS - All reactions already present for poll {poll_id}")
            
    except Exception as e:
        logger.error(f"❌ RESTORE REACTIONS - Error restoring reactions for poll {getattr(poll, 'id', 'unknown')}: {e}")


async def get_guild_roles(bot: commands.Bot, guild_id: str) -> List[Dict[str, Any]]:
    """Get roles for a guild that can be mentioned/pinged by the bot with caching"""
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
                    role_data = {
                        "id": str(role.id),
                        "name": role.name,
                        "color": str(role.color)
                        if role.color != discord.Color.default()
                        else None,
                        "position": role.position,
                        "mentionable": role.mentionable,
                        "managed": role.managed,
                        "can_ping": True,
                    }
                    roles.append(role_data)
                        
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


async def create_poll_results_embed(poll: Poll) -> discord.Embed:
    """Create comprehensive results embed for closed polls - ALWAYS shows full breakdown"""
    poll_name = str(getattr(poll, "name", ""))
    poll_question = str(getattr(poll, "question", ""))

    # Use poll's close time in the correct timezone for the timestamp
    poll_timezone = str(getattr(poll, "timezone", "UTC"))
    poll_close_time = poll.close_time_aware

    # Ensure close_time is timezone-aware - if naive, assume it's in the poll's timezone
    if poll_close_time.tzinfo is None:
        logger.warning("⚠️ RESULTS EMBED - Poll close_time was timezone-naive, localizing to poll timezone")

        # Try to use the poll's timezone first, fallback to UTC
        try:
            if poll_timezone and poll_timezone != "UTC":
                from .utils import validate_and_normalize_timezone
                normalized_tz = validate_and_normalize_timezone(poll_timezone)
                if normalized_tz != "UTC":
                    tz = pytz.timezone(normalized_tz)
                    poll_close_time = tz.localize(poll_close_time)
                    logger.info(f"✅ RESULTS EMBED - Poll close_time localized to {normalized_tz}")
                else:
                    poll_close_time = pytz.UTC.localize(poll_close_time)
                    logger.info("✅ RESULTS EMBED - Poll close_time localized to UTC (normalized)")
            else:
                poll_close_time = pytz.UTC.localize(poll_close_time)
                logger.info("✅ RESULTS EMBED - Poll close_time localized to UTC (default)")
        except Exception as localize_error:
            logger.error(f"❌ RESULTS EMBED - Poll close_time localization failed: {localize_error}")
            poll_close_time = pytz.UTC.localize(poll_close_time)
            logger.info("⚠️ RESULTS EMBED - Poll close_time using UTC fallback")

    # Convert close time to poll's timezone if specified and different from UTC
    if poll_timezone and poll_timezone != "UTC":
        try:
            # Validate and normalize timezone first
            from .utils import validate_and_normalize_timezone
            normalized_tz = validate_and_normalize_timezone(poll_timezone)

            if normalized_tz != "UTC":
                tz = pytz.timezone(normalized_tz)
                # Convert to the poll's timezone for display
                poll_close_time = poll_close_time.astimezone(tz)
                logger.debug(f"✅ RESULTS EMBED - Converted close time to {normalized_tz}")
            else:
                logger.debug(f"ℹ️ RESULTS EMBED - Using UTC (normalized from {poll_timezone})")
        except Exception as e:
            logger.error(f"❌ RESULTS EMBED - Close time timezone conversion failed: {e}")
            # Ensure we have a valid UTC timestamp as fallback
            if poll_close_time.tzinfo != pytz.UTC:
                poll_close_time = poll_close_time.astimezone(pytz.UTC)
            logger.info("⚠️ RESULTS EMBED - Using UTC fallback")

    embed = discord.Embed(
        title=f"🏁 Poll Results: {poll_name}",
        description=poll_question,
        color=0xFF0000,  # Red for closed
        timestamp=poll_close_time,
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

        # Check if role ping is enabled and configured for poll closure
        message_content = f"📊 **Poll '{poll_name}' has ended!**"
        role_ping_attempted = False
        ping_role_enabled = getattr(poll, "ping_role_enabled", False)
        ping_role_id = getattr(poll, "ping_role_id", None)
        ping_role_on_close = getattr(poll, "ping_role_on_close", False)

        if ping_role_enabled and ping_role_id and ping_role_on_close:
            role_id = str(ping_role_id)
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
    Checks previous vote status and customizes message accordingly.

    Args:
        bot: Discord bot instance
        poll: Poll object
        user_id: Discord user ID who voted
        option_index: Index of the option they voted for
        vote_action: Action taken ("added", "removed", "updated", "created", "already_recorded")

    Returns:
        bool: True if DM was sent successfully, False otherwise
    """
    logger.info(f"🔔 DM FUNCTION DEBUG - Starting send_vote_confirmation_dm for user {user_id}, action: {vote_action}")
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

        # Get poll information
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

        # Check user's voting history for this poll to provide context
        db = get_db_session()
        previous_votes = []
        try:
            from .database import Vote
            user_votes = (
                db.query(Vote)
                .filter(Vote.poll_id == getattr(poll, "id"), Vote.user_id == user_id)
                .all()
            )
            previous_votes = [vote.option_index for vote in user_votes]
        except Exception as e:
            logger.warning(f"Could not fetch previous votes for user {user_id}: {e}")
        finally:
            db.close()

        # Determine action message based on vote action and previous votes
        poll_multiple_choice = bool(getattr(poll, "multiple_choice", False))

        if vote_action == "added":
            if poll_multiple_choice:
                action_description = f"✅ You added a vote for: {selected_emoji} **{selected_option}**"
                if len(previous_votes) > 1:
                    action_description += f"\n💡 You now have {len(previous_votes)} selections in this poll"
            else:
                action_description = f"✅ You voted for: {selected_emoji} **{selected_option}**"

        elif vote_action == "removed":
            action_description = f"❌ You removed your vote for: {selected_emoji} **{selected_option}**"
            if poll_multiple_choice and len(previous_votes) > 0:
                action_description += f"\n💡 You still have {len(previous_votes)} other selection(s) in this poll"
            elif poll_multiple_choice and len(previous_votes) == 0:
                action_description += "\n💡 You have no selections remaining in this poll"

        elif vote_action == "updated":
            action_description = f"🔄 You changed your vote to: {selected_emoji} **{selected_option}**"
            # For single-choice polls, this means they had a different previous vote
            if not poll_multiple_choice:
                action_description += "\n💡 Your previous vote has been replaced"

        elif vote_action == "created":
            action_description = f"✅ You voted for: {selected_emoji} **{selected_option}**"

        elif vote_action == "already_recorded":
            action_description = f"Your vote for {selected_emoji} **{selected_option}** was previously recorded.\n\n💡 Your vote already counted and this is just confirmation of your vote."

        else:
            # Fallback for unknown actions
            action_description = f"🗳️ Your vote: {selected_emoji} **{selected_option}**"

        # Check if user already had this exact vote (for better messaging)
        had_this_vote_before = option_index in [v.option_index for v in (
            db.query(Vote).filter(
                Vote.poll_id == getattr(poll, "id"),
                Vote.user_id == user_id,
                Vote.option_index == option_index
            ).all() if 'db' in locals() else []
        )]

        # Add contextual information for repeated votes
        if vote_action == "added" and not poll_multiple_choice:
            # For single choice, "added" usually means first vote, but let's be explicit
            if len(previous_votes) == 1:  # This is their first and only vote
                action_description += "\n💡 This is your only vote in this poll"
        elif vote_action == "created" and not poll_multiple_choice:
            # For single choice polls, clarify it's their only vote
            action_description += "\n💡 This is your only vote in this poll"

        # Create embed with poll information
        embed_color = 0x00FF00  # Green for confirmation
        if vote_action == "removed":
            embed_color = 0xFFA500  # Orange for removal
        elif vote_action == "updated":
            embed_color = 0x0099FF  # Blue for change

        embed = discord.Embed(
            title="🗳️ Vote Confirmation",
            description=action_description,
            color=embed_color,
            timestamp=datetime.now(pytz.UTC),
        )

        # Add poll details with choice limit information
        poll_info_text = f"**{poll_name}**\n{poll_question}\n\n"

        # Add choice limit information
        if poll_multiple_choice:
            poll_info_text += "🔢 You may make **multiple choices** in this poll"
        else:
            poll_info_text += "🔢 You may make **1 choice** in this poll"

        embed.add_field(
            name="📊 Poll", value=poll_info_text, inline=False
        )

        # Add all poll options for reference, highlighting current selections
        options_text = ""
        current_user_votes = []

        # Get current votes after the action
        db = get_db_session()
        try:
            from .database import Vote
            current_votes = (
                db.query(Vote)
                .filter(Vote.poll_id == getattr(poll, "id"), Vote.user_id == user_id)
                .all()
            )
            current_user_votes = [vote.option_index for vote in current_votes]
        except Exception as e:
            logger.warning(f"Could not fetch current votes for user {user_id}: {e}")
        finally:
            db.close()

        for i, option in enumerate(poll.options):
            emoji = poll.emojis[i] if i < len(poll.emojis) else POLL_EMOJIS[i]
            if i in current_user_votes:
                # Highlight all current selections
                if i == option_index and vote_action in ["added", "updated", "created"]:
                    options_text += f"{emoji} **{option}** ← Your current choice ✅\n"
                else:
                    options_text += f"{emoji} **{option}** ← Selected ✅\n"
            else:
                options_text += f"{emoji} {option}\n"

        embed.add_field(name="📝 All Options", value=options_text, inline=False)

        # Add voting summary for multiple choice polls
        if poll_multiple_choice and len(current_user_votes) > 0:
            summary_text = f"You have selected {len(current_user_votes)} option(s) in this poll"
            embed.add_field(name="📊 Your Selections", value=summary_text, inline=True)

        # Add poll type information
        poll_anonymous = bool(getattr(poll, "anonymous", False))

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
            f"✅ Sent enhanced vote confirmation DM to user {user_id} for poll {getattr(poll, 'id')} (action: {vote_action})"
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


def user_has_admin_permissions(member: discord.Member) -> bool:
    """Check if user has admin permissions in the guild"""
    return (
        member.guild_permissions.administrator
        or member.guild_permissions.manage_guild
        or member.guild_permissions.manage_channels
    )
