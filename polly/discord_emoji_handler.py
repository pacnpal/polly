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
        
        print(f"🔍 IS_UNICODE_EMOJI DEBUG - Checking text: '{text}' (len: {len(text)})")
        logger.info(f"🔍 IS_UNICODE_EMOJI DEBUG - Checking text: '{text}' (len: {len(text)})")

        # Check for multi-character emoji sequences first (more comprehensive)
        emoji_pattern = re.compile(
            r'[\U0001F600-\U0001F64F]|'  # emoticons
            r'[\U0001F300-\U0001F5FF]|'  # symbols & pictographs
            r'[\U0001F680-\U0001F6FF]|'  # transport & map symbols
            r'[\U0001F1E0-\U0001F1FF]|'  # flags (iOS)
            r'[\U00002702-\U000027B0]|'  # dingbats
            r'[\U000024C2-\U0001F251]|'  # enclosed characters
            r'[\U0001F900-\U0001F9FF]|'  # supplemental symbols
            r'[\U0001FA70-\U0001FAFF]|'  # symbols and pictographs extended-A
            r'[\U00002600-\U000026FF]|'  # miscellaneous symbols
            r'[\U0000FE00-\U0000FE0F]'   # variation selectors
        )
        
        # Check if the entire text matches emoji patterns
        if emoji_pattern.search(text):
            print(f"✅ IS_UNICODE_EMOJI DEBUG - Found emoji pattern match: '{text}'")
            logger.info(f"✅ IS_UNICODE_EMOJI DEBUG - Found emoji pattern match: '{text}'")
            return True

        # Check if it's a single Unicode emoji character using category
        if len(text) == 1:
            import unicodedata
            try:
                category = unicodedata.category(text)
                codepoint = ord(text)
                print(f"🔍 IS_UNICODE_EMOJI DEBUG - Single char '{text}': category={category}, codepoint={codepoint}")
                logger.info(f"🔍 IS_UNICODE_EMOJI DEBUG - Single char '{text}': category={category}, codepoint={codepoint}")
                
                # More inclusive category check
                is_emoji = (category.startswith('So') or  # Symbol, other (most emojis)
                           category.startswith('Sm') or  # Math symbols (some emojis)
                           category.startswith('Sk') or  # Modifier symbols
                           codepoint in range(0x1F000, 0x1FAFF) or  # Emoji blocks
                           codepoint in range(0x2600, 0x27BF) or   # Miscellaneous symbols
                           codepoint in range(0x1F300, 0x1F9FF) or  # Emoji ranges
                           codepoint in range(0x1F600, 0x1F64F) or  # Emoticons
                           codepoint in range(0x1F680, 0x1F6FF) or  # Transport symbols
                           codepoint in range(0x2700, 0x27BF) or   # Dingbats
                           codepoint in range(0xFE00, 0xFE0F))     # Variation selectors
                
                if is_emoji:
                    print(f"✅ IS_UNICODE_EMOJI DEBUG - Single char emoji validated: '{text}'")
                    logger.info(f"✅ IS_UNICODE_EMOJI DEBUG - Single char emoji validated: '{text}'")
                else:
                    print(f"❌ IS_UNICODE_EMOJI DEBUG - Single char not emoji: '{text}'")
                    logger.info(f"❌ IS_UNICODE_EMOJI DEBUG - Single char not emoji: '{text}'")
                
                return is_emoji
            except Exception as e:
                print(f"💥 IS_UNICODE_EMOJI DEBUG - Error checking single char: {e}")
                logger.error(f"💥 IS_UNICODE_EMOJI DEBUG - Error checking single char: {e}")
                return False

        print(f"❌ IS_UNICODE_EMOJI DEBUG - No emoji pattern found: '{text}'")
        logger.info(f"❌ IS_UNICODE_EMOJI DEBUG - No emoji pattern found: '{text}'")
        return False

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
        
        print(f"🔍 PROCESS_EMOJI_INPUT DEBUG - Processing: '{emoji_input}' for guild {guild_id}")
        logger.info(f"🔍 PROCESS_EMOJI_INPUT DEBUG - Processing: '{emoji_input}' for guild {guild_id}")

        # 1. Check if it's already a Unicode emoji
        if self.is_unicode_emoji(emoji_input):
            print(f"✅ PROCESS_EMOJI_INPUT DEBUG - Valid Unicode emoji: {emoji_input}")
            logger.debug(f"Valid Unicode emoji: {emoji_input}")
            return emoji_input

        # 2. Check if it's a custom emoji format <:name:id> or <a:name:id>
        custom_emoji_data = self.parse_custom_emoji(emoji_input)
        if custom_emoji_data:
            print(f"🎭 PROCESS_EMOJI_INPUT DEBUG - Parsed custom emoji: {custom_emoji_data}")
            logger.info(f"🎭 PROCESS_EMOJI_INPUT DEBUG - Parsed custom emoji: {custom_emoji_data}")
            
            # For custom emojis, we need to verify they're from the correct guild
            try:
                guild = self.bot.get_guild(guild_id)
                if guild:
                    # Look for the emoji in the guild's emoji list
                    guild_emoji = discord.utils.get(guild.emojis, id=custom_emoji_data['id'])
                    if guild_emoji:
                        print(f"✅ PROCESS_EMOJI_INPUT DEBUG - Found custom emoji in guild: {guild_emoji}")
                        logger.debug(f"Valid custom emoji from guild: {guild_emoji.name} ({guild_emoji.id})")
                        return str(guild_emoji)  # Returns <:name:id> format
                    else:
                        print(f"❌ PROCESS_EMOJI_INPUT DEBUG - Custom emoji {custom_emoji_data['id']} not found in guild {guild_id}")
                        logger.warning(f"Custom emoji {custom_emoji_data['id']} not found in guild {guild_id}")
                        
                        # Try global bot emoji lookup as fallback
                        global_emoji = self.bot.get_emoji(custom_emoji_data['id'])
                        if global_emoji:
                            print(f"⚠️ PROCESS_EMOJI_INPUT DEBUG - Found emoji globally but not in target guild: {global_emoji}")
                            logger.warning(f"Found emoji globally but not in target guild: {global_emoji.name}")
                            # Still return it - Discord might allow cross-guild emoji usage in some cases
                            return str(global_emoji)
                else:
                    print(f"❌ PROCESS_EMOJI_INPUT DEBUG - Guild {guild_id} not found")
                    logger.warning(f"Guild {guild_id} not found")
            except Exception as e:
                print(f"💥 PROCESS_EMOJI_INPUT DEBUG - Error validating custom emoji: {e}")
                logger.error(f"Error validating custom emoji {custom_emoji_data['id']}: {e}")

        # 3. Try to find by name in the guild (for shortcode-style input like :smile:)
        emoji_name = emoji_input.strip(':')
        custom_emoji = await self.find_emoji_by_name(guild_id, emoji_name)
        if custom_emoji:
            print(f"✅ PROCESS_EMOJI_INPUT DEBUG - Found custom emoji by name: {custom_emoji}")
            logger.debug(f"Found custom emoji by name: {custom_emoji.name}")
            return str(custom_emoji)

        # 4. If nothing worked, return None
        print(f"❌ PROCESS_EMOJI_INPUT DEBUG - Could not process emoji input: '{emoji_input}'")
        logger.debug(f"Could not process emoji input: {emoji_input}")
        return None

    async def process_poll_emojis(self, emoji_inputs: List[str], guild_id: int) -> List[str]:
        """
        Process a list of emoji inputs for a poll

        Args:
            emoji_inputs: List of emoji strings from user input
            guild_id: Guild ID for custom emoji lookup

        Returns:
            List of valid emoji strings, preserving duplicates for form validation
        """
        processed_emojis = []
        default_emojis = ["🇦", "🇧", "🇨", "🇩", "🇪", "🇫", "🇬", "🇭", "🇮", "🇯"]

        print(f"🎯 PROCESS_POLL_EMOJIS DEBUG - Starting with {len(emoji_inputs)} emoji inputs for guild {guild_id}")
        logger.info(f"🎯 PROCESS_POLL_EMOJIS DEBUG - Starting with {len(emoji_inputs)} emoji inputs for guild {guild_id}")

        for i, emoji_input in enumerate(emoji_inputs):
            print(f"🔄 PROCESS_POLL_EMOJIS DEBUG - Processing emoji {i+1}/{len(emoji_inputs)}: '{emoji_input}'")
            logger.info(f"🔄 PROCESS_POLL_EMOJIS DEBUG - Processing emoji {i+1}/{len(emoji_inputs)}: '{emoji_input}'")
            
            if not emoji_input or not emoji_input.strip():
                # Use default emoji for empty input
                if i < len(default_emojis):
                    final_emoji = default_emojis[i]
                    print(f"⚪ PROCESS_POLL_EMOJIS DEBUG - Empty input, using default emoji for option {i}: {final_emoji}")
                    logger.debug(f"Using default emoji for option {i}: {final_emoji}")
                else:
                    final_emoji = default_emojis[0]  # Fallback to first default
                    print(f"⚪ PROCESS_POLL_EMOJIS DEBUG - Empty input beyond defaults, using fallback: {final_emoji}")
                    logger.debug(f"Using fallback emoji for option {i}: {final_emoji}")
            else:
                # Process the emoji input
                print(f"🔍 PROCESS_POLL_EMOJIS DEBUG - Calling process_emoji_input for '{emoji_input}'")
                logger.info(f"🔍 PROCESS_POLL_EMOJIS DEBUG - Calling process_emoji_input for '{emoji_input}'")
                
                processed_emoji = await self.process_emoji_input(emoji_input, guild_id)
                
                print(f"📤 PROCESS_POLL_EMOJIS DEBUG - process_emoji_input returned: '{processed_emoji}' (type: {type(processed_emoji)})")
                logger.info(f"📤 PROCESS_POLL_EMOJIS DEBUG - process_emoji_input returned: '{processed_emoji}' (type: {type(processed_emoji)})")

                if processed_emoji:
                    final_emoji = processed_emoji
                    print(f"✅ PROCESS_POLL_EMOJIS DEBUG - Successfully processed emoji for option {i}: '{final_emoji}'")
                    logger.debug(f"Processed emoji for option {i}: {final_emoji}")
                else:
                    # Fallback to default emoji
                    if i < len(default_emojis):
                        final_emoji = default_emojis[i]
                    else:
                        final_emoji = default_emojis[0]  # Fallback to first default
                    print(f"❌ PROCESS_POLL_EMOJIS DEBUG - Failed to process emoji '{emoji_input}', using fallback: {final_emoji}")
                    logger.warning(f"Failed to process emoji '{emoji_input}', using fallback: {final_emoji}")

            # Add the final emoji to our results (preserving duplicates for validation)
            processed_emojis.append(final_emoji)
            print(f"📝 PROCESS_POLL_EMOJIS DEBUG - Added emoji to results: '{final_emoji}'")
            logger.debug(f"Added emoji to results: '{final_emoji}'")

        print(f"🏁 PROCESS_POLL_EMOJIS DEBUG - Final result: {processed_emojis} (unique count: {len(set(processed_emojis))})")
        logger.info(f"🏁 PROCESS_POLL_EMOJIS DEBUG - Final result: {processed_emojis} (unique count: {len(set(processed_emojis))})")
        
        # Log if duplicates exist (but don't fix them - let form validation handle it)
        if len(set(processed_emojis)) != len(processed_emojis):
            print(f"⚠️ PROCESS_POLL_EMOJIS DEBUG - Duplicates detected, will be caught by form validation: {processed_emojis}")
            logger.warning(f"Duplicates detected in emoji processing, will be caught by form validation: {processed_emojis}")
        
        return processed_emojis

    def _get_unique_default_emoji(self, option_index: int, used_emojis: set, default_emojis: List[str]) -> str:
        """Get a unique default emoji that hasn't been used yet"""
        # Try the default emoji for this index first
        if option_index < len(default_emojis) and default_emojis[option_index] not in used_emojis:
            return default_emojis[option_index]
        
        # If that's taken, find the first unused default emoji
        for emoji in default_emojis:
            if emoji not in used_emojis:
                return emoji
        
        # If all default emojis are used (shouldn't happen with 10 defaults), use numbered emojis
        fallback_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        for emoji in fallback_emojis:
            if emoji not in used_emojis:
                return emoji
        
        # Last resort: use option index as emoji (shouldn't happen)
        return f"{option_index + 1}️⃣"

    def _ensure_all_unique(self, emojis: List[str], default_emojis: List[str]) -> List[str]:
        """Ensure all emojis in the list are unique, replacing duplicates"""
        unique_emojis = []
        used = set()
        
        for i, emoji in enumerate(emojis):
            if emoji not in used:
                unique_emojis.append(emoji)
                used.add(emoji)
            else:
                # Find a replacement
                replacement = self._get_unique_default_emoji(i, used, default_emojis)
                unique_emojis.append(replacement)
                used.add(replacement)
                print(f"🔄 ENSURE_UNIQUE DEBUG - Replaced duplicate '{emoji}' with '{replacement}' at index {i}")
                logger.warning(f"Replaced duplicate '{emoji}' with '{replacement}' at index {i}")
        
        return unique_emojis

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
