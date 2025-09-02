"""
Discord Native Emoji Handler
Simplified emoji handling using Discord.py's native capabilities
"""

import logging
import re
import discord
from typing import List, Optional, Dict, Any
from discord.ext import commands

logger = logging.getLogger(__name__)


class DiscordEmojiHandler:
    """Handles emoji processing using Discord's native capabilities"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def get_guild_emojis(self, guild_id: int) -> List[discord.Emoji]:
        """Get all custom emojis available in a guild"""
        try:
            # Debug: Guild lookup
            print(f"🏰 EMOJI HANDLER DEBUG - Looking up guild {guild_id}")
            logger.info(f"🏰 EMOJI HANDLER DEBUG - Looking up guild {guild_id}")
            
            guild = self.bot.get_guild(guild_id)
            if not guild:
                print(f"❌ EMOJI HANDLER DEBUG - Guild {guild_id} not found")
                logger.warning(f"❌ EMOJI HANDLER DEBUG - Guild {guild_id} not found")
                logger.warning(f"Guild {guild_id} not found")
                return []

            print(f"✅ EMOJI HANDLER DEBUG - Found guild: {guild.name} (ID: {guild.id}, Member count: {guild.member_count})")
            logger.info(f"✅ EMOJI HANDLER DEBUG - Found guild: {guild.name} (ID: {guild.id}, Member count: {guild.member_count})")

            # Debug: Check guild emoji access
            print(f"🎭 EMOJI HANDLER DEBUG - Accessing guild.emojis for {guild.name}")
            logger.info(f"🎭 EMOJI HANDLER DEBUG - Accessing guild.emojis for {guild.name}")

            emojis = list(guild.emojis)
            
            # Debug: Log emoji count and details
            print(f"📊 EMOJI HANDLER DEBUG - Raw guild.emojis returned {len(emojis)} emojis")
            logger.info(f"📊 EMOJI HANDLER DEBUG - Raw guild.emojis returned {len(emojis)} emojis")
            
            if emojis:
                print(f"🎯 EMOJI HANDLER DEBUG - First emoji: {emojis[0].name} (ID: {emojis[0].id})")
                logger.info(f"🎯 EMOJI HANDLER DEBUG - First emoji: {emojis[0].name} (ID: {emojis[0].id})")
            else:
                print("⚠️ EMOJI HANDLER DEBUG - No emojis found in guild")
                logger.warning("⚠️ EMOJI HANDLER DEBUG - No emojis found in guild")

            logger.debug(
                f"Found {len(emojis)} custom emojis in guild {guild.name}")
            return emojis

        except Exception as e:
            print(f"💥 EMOJI HANDLER DEBUG - Exception in get_guild_emojis: {e}")
            logger.error(f"💥 EMOJI HANDLER DEBUG - Exception in get_guild_emojis: {e}")
            logger.error(
                f"Error getting guild emojis for guild {guild_id}: {e}")
            return []

    async def find_emoji_by_name(self, guild_id: int, emoji_name: str) -> Optional[discord.Emoji]:
        """Find a custom emoji by name in a guild"""
        try:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return None

            # Clean the emoji name (remove colons if present)
            clean_name = emoji_name.strip(':')

            # Use Discord's utility to find emoji by name
            emoji = discord.utils.get(guild.emojis, name=clean_name)

            if emoji:
                logger.debug(f"Found custom emoji: {emoji.name} ({emoji.id})")
            else:
                logger.debug(
                    f"Custom emoji '{clean_name}' not found in guild {guild.name}")

            return emoji

        except Exception as e:
            logger.error(
                f"Error finding emoji '{emoji_name}' in guild {guild_id}: {e}")
            return None

    def is_unicode_emoji(self, text: str) -> bool:
        """Check if text is a valid Unicode emoji"""
        if not text:
            return False

        # Remove whitespace
        text = text.strip()

        # Check if it's a single Unicode emoji character
        if len(text) == 1:
            import unicodedata
            try:
                category = unicodedata.category(text)
                return category == 'So'  # Symbol, other (includes emojis)
            except:
                return False

        # Check for multi-character emoji sequences (like skin tone modifiers)
        emoji_pattern = re.compile(
            r'[\U0001F600-\U0001F64F]|'  # emoticons
            r'[\U0001F300-\U0001F5FF]|'  # symbols & pictographs
            r'[\U0001F680-\U0001F6FF]|'  # transport & map symbols
            r'[\U0001F1E0-\U0001F1FF]|'  # flags (iOS)
            r'[\U00002702-\U000027B0]|'  # dingbats
            r'[\U000024C2-\U0001F251]'   # enclosed characters
        )
        return bool(emoji_pattern.fullmatch(text))

    def parse_custom_emoji(self, emoji_text: str) -> Optional[Dict[str, Any]]:
        """Parse custom emoji format <:name:id> or <a:name:id>"""
        if not emoji_text:
            return None

        # Match custom emoji format
        custom_emoji_pattern = r'<(a?):([^:]+):(\d+)>'
        match = re.match(custom_emoji_pattern, emoji_text.strip())

        if match:
            animated = bool(match.group(1))  # 'a' for animated
            name = match.group(2)
            emoji_id = int(match.group(3))

            return {
                'animated': animated,
                'name': name,
                'id': emoji_id,
                'format': emoji_text
            }

        return None

    async def process_emoji_input(self, emoji_input: str, guild_id: int) -> Optional[str]:
        """
        Process emoji input and return a valid emoji string for reactions

        Args:
            emoji_input: User input (could be unicode emoji, custom emoji format, or emoji name)
            guild_id: Guild ID to search for custom emojis

        Returns:
            Valid emoji string for Discord reactions, or None if invalid
        """
        if not emoji_input:
            return None

        emoji_input = emoji_input.strip()

        # 1. Check if it's already a Unicode emoji
        if self.is_unicode_emoji(emoji_input):
            logger.debug(f"Valid Unicode emoji: {emoji_input}")
            return emoji_input

        # 2. Check if it's a custom emoji format <:name:id>
        custom_emoji_data = self.parse_custom_emoji(emoji_input)
        if custom_emoji_data:
            # Verify the emoji exists and is accessible
            try:
                emoji = self.bot.get_emoji(custom_emoji_data['id'])
                if emoji:
                    logger.debug(
                        f"Valid custom emoji: {emoji.name} ({emoji.id})")
                    return str(emoji)  # Returns <:name:id> format
                else:
                    logger.warning(
                        f"Custom emoji {custom_emoji_data['id']} not accessible")
            except Exception as e:
                logger.error(
                    f"Error validating custom emoji {custom_emoji_data['id']}: {e}")

        # 3. Try to find by name in the guild (for shortcode-style input like :smile:)
        emoji_name = emoji_input.strip(':')
        custom_emoji = await self.find_emoji_by_name(guild_id, emoji_name)
        if custom_emoji:
            logger.debug(f"Found custom emoji by name: {custom_emoji.name}")
            return str(custom_emoji)

        # 4. If nothing worked, return None
        logger.debug(f"Could not process emoji input: {emoji_input}")
        return None

    async def process_poll_emojis(self, emoji_inputs: List[str], guild_id: int) -> List[str]:
        """
        Process a list of emoji inputs for a poll

        Args:
            emoji_inputs: List of emoji strings from user input
            guild_id: Guild ID for custom emoji lookup

        Returns:
            List of valid emoji strings, with fallbacks to default emojis if needed
        """
        processed_emojis = []
        default_emojis = ["🇦", "🇧", "🇨", "🇩", "🇪", "🇫", "🇬", "🇭", "🇮", "🇯"]

        for i, emoji_input in enumerate(emoji_inputs):
            if not emoji_input or not emoji_input.strip():
                # Use default emoji for empty input
                if i < len(default_emojis):
                    processed_emojis.append(default_emojis[i])
                    logger.debug(
                        f"Using default emoji for option {i}: {default_emojis[i]}")
                continue

            # Process the emoji input
            processed_emoji = await self.process_emoji_input(emoji_input, guild_id)

            if processed_emoji:
                processed_emojis.append(processed_emoji)
                logger.debug(
                    f"Processed emoji for option {i}: {processed_emoji}")
            else:
                # Fallback to default emoji
                if i < len(default_emojis):
                    processed_emojis.append(default_emojis[i])
                    logger.warning(
                        f"Failed to process emoji '{emoji_input}', using fallback: {default_emojis[i]}")

        return processed_emojis

    async def get_guild_emoji_list(self, guild_id: int) -> List[Dict[str, Any]]:
        """
        Get a list of all guild emojis for frontend display

        Returns:
            List of emoji data dictionaries with name, id, url, animated status
        """
        try:
            # Debug: Start of emoji list retrieval
            print(
                f"🔍 EMOJI HANDLER DEBUG - Starting get_guild_emoji_list for guild {guild_id}")
            logger.info(
                f"🔍 EMOJI HANDLER DEBUG - Starting get_guild_emoji_list for guild {guild_id}")

            # Debug: Check bot availability
            if not self.bot:
                print("❌ EMOJI HANDLER DEBUG - Bot instance is None")
                logger.error("❌ EMOJI HANDLER DEBUG - Bot instance is None")
                return []

            print(
                "✅ EMOJI HANDLER DEBUG - Bot instance available, getting guild emojis...")
            logger.info(
                "✅ EMOJI HANDLER DEBUG - Bot instance available, getting guild emojis...")

            guild_emojis = await self.get_guild_emojis(guild_id)

            # Debug: Log emoji retrieval results
            print(
                f"📊 EMOJI HANDLER DEBUG - Retrieved {len(guild_emojis)} raw guild emojis")
            logger.info(
                f"📊 EMOJI HANDLER DEBUG - Retrieved {len(guild_emojis)} raw guild emojis")

            emoji_list = []
            for i, emoji in enumerate(guild_emojis):
                try:
                    emoji_data = {
                        'name': emoji.name,
                        'id': emoji.id,
                        'animated': emoji.animated,
                        'url': str(emoji.url),
                        'format': str(emoji),  # <:name:id> format
                        'usable': emoji.is_usable()
                    }
                    emoji_list.append(emoji_data)

                    # Debug: Log each emoji being processed
                    print(
                        f"✨ EMOJI HANDLER DEBUG - Emoji {i+1}: {emoji.name} (ID: {emoji.id}, Animated: {emoji.animated}, Usable: {emoji.is_usable()})")
                    logger.info(
                        f"✨ EMOJI HANDLER DEBUG - Emoji {i+1}: {emoji.name} (ID: {emoji.id}, Animated: {emoji.animated}, Usable: {emoji.is_usable()})")

                except Exception as emoji_error:
                    print(
                        f"❌ EMOJI HANDLER DEBUG - Error processing emoji {i+1}: {emoji_error}")
                    logger.error(
                        f"❌ EMOJI HANDLER DEBUG - Error processing emoji {i+1}: {emoji_error}")
                    continue

            # Debug: Final results
            print(
                f"🎯 EMOJI HANDLER DEBUG - Final emoji list contains {len(emoji_list)} processed emojis")
            logger.info(
                f"🎯 EMOJI HANDLER DEBUG - Final emoji list contains {len(emoji_list)} processed emojis")

            # Debug: Log sample of emoji data structure
            if emoji_list:
                sample_emoji = emoji_list[0]
                print(
                    f"📋 EMOJI HANDLER DEBUG - Sample emoji data structure: {sample_emoji}")
                logger.info(
                    f"📋 EMOJI HANDLER DEBUG - Sample emoji data structure: {sample_emoji}")
            else:
                print("⚠️ EMOJI HANDLER DEBUG - No emojis in final list")
                logger.warning(
                    "⚠️ EMOJI HANDLER DEBUG - No emojis in final list")

            logger.debug(
                f"Retrieved {len(emoji_list)} emojis for guild {guild_id}")
            return emoji_list

        except Exception as e:
            print(
                f"💥 EMOJI HANDLER DEBUG - Exception in get_guild_emoji_list: {e}")
            logger.error(
                f"💥 EMOJI HANDLER DEBUG - Exception in get_guild_emoji_list: {e}")
            logger.error(f"Error getting emoji list for guild {guild_id}: {e}")
            return []


# Convenience function for easy import
async def create_emoji_handler(bot: commands.Bot) -> DiscordEmojiHandler:
    """Create and return a DiscordEmojiHandler instance"""
    return DiscordEmojiHandler(bot)
