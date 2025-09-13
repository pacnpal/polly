"""
Emoji Pipeline Consistency Fix
Unified emoji processing for create and edit operations
"""

import logging
from typing import List, Tuple
try:
    from .discord_emoji_handler import DiscordEmojiHandler
    from .validators import PollValidator
    from .database import POLL_EMOJIS
except ImportError:
    from discord_emoji_handler import DiscordEmojiHandler  # type: ignore
    from validators import PollValidator  # type: ignore
    from database import POLL_EMOJIS  # type: ignore

logger = logging.getLogger(__name__)


class UnifiedEmojiProcessor:
    """Unified emoji processing for consistent behavior across create/edit operations"""

    def __init__(self, bot):
        self.bot = bot
        self.emoji_handler = DiscordEmojiHandler(bot)

    async def process_poll_emojis_unified(
        self, emoji_inputs: List[str], server_id: int, operation: str = "create"
    ) -> Tuple[bool, List[str], str]:
        """
        Unified emoji processing for both create and edit operations

        Args:
            emoji_inputs: List of emoji strings from form data
            server_id: Discord server ID for custom emoji validation
            operation: "create" or "edit" for logging purposes

        Returns:
            Tuple of (success, processed_emojis, error_message)
        """
        try:
            logger.info(
                f"🔄 UNIFIED EMOJI PROCESSOR - Starting {operation} operation with {len(emoji_inputs)} emoji inputs for server {server_id}"
            )
            print(
                f"🔄 UNIFIED EMOJI PROCESSOR - Starting {operation} operation with {len(emoji_inputs)} emoji inputs for server {server_id}"
            )

            # Step 1: Process each emoji input using the Discord handler
            processed_emojis = await self.emoji_handler.process_poll_emojis(
                emoji_inputs, server_id
            )

            logger.info(
                f"📊 UNIFIED EMOJI PROCESSOR - Discord handler returned {len(processed_emojis)} emojis: {processed_emojis}"
            )
            print(
                f"📊 UNIFIED EMOJI PROCESSOR - Discord handler returned {len(processed_emojis)} emojis: {processed_emojis}"
            )

            # Step 2: Validate emojis using the validator with bot instance for emoji preparation
            try:
                validated_emojis = PollValidator.validate_poll_emojis(
                    processed_emojis, self.bot
                )
                logger.info(
                    f"✅ UNIFIED EMOJI PROCESSOR - Validator approved {len(validated_emojis)} emojis: {validated_emojis}"
                )
                print(
                    f"✅ UNIFIED EMOJI PROCESSOR - Validator approved {len(validated_emojis)} emojis: {validated_emojis}"
                )
            except Exception as validation_error:
                logger.error(
                    f"❌ UNIFIED EMOJI PROCESSOR - Validation failed: {validation_error}"
                )
                print(
                    f"❌ UNIFIED EMOJI PROCESSOR - Validation failed: {validation_error}"
                )
                return False, [], f"Emoji validation failed: {str(validation_error)}"

            # Step 3: Check for duplicates (critical for poll functionality)
            if len(set(validated_emojis)) != len(validated_emojis):
                duplicate_emojis = [
                    emoji
                    for emoji in validated_emojis
                    if validated_emojis.count(emoji) > 1
                ]
                error_msg = f"Duplicate emojis detected: {list(set(duplicate_emojis))}. Each poll option must have a unique emoji."
                logger.warning(f"❌ UNIFIED EMOJI PROCESSOR - {error_msg}")
                print(f"❌ UNIFIED EMOJI PROCESSOR - {error_msg}")
                return False, [], error_msg

            # Step 4: Ensure we have the right number of emojis for the options
            if len(validated_emojis) < len(emoji_inputs):
                # Fill in missing emojis with defaults
                for i in range(len(validated_emojis), len(emoji_inputs)):
                    if i < len(POLL_EMOJIS):
                        default_emoji = POLL_EMOJIS[i]
                        # Make sure the default isn't already used
                        while default_emoji in validated_emojis:
                            # Find next available default
                            next_index = (POLL_EMOJIS.index(default_emoji) + 1) % len(
                                POLL_EMOJIS
                            )
                            default_emoji = POLL_EMOJIS[next_index]
                        validated_emojis.append(default_emoji)
                        logger.info(
                            f"🔧 UNIFIED EMOJI PROCESSOR - Added default emoji for option {i + 1}: {default_emoji}"
                        )
                        print(
                            f"🔧 UNIFIED EMOJI PROCESSOR - Added default emoji for option {i + 1}: {default_emoji}"
                        )

            # Final validation - ensure no duplicates after adding defaults
            if len(set(validated_emojis)) != len(validated_emojis):
                error_msg = "Unable to resolve emoji conflicts. Please select different emojis for each option."
                logger.error(f"❌ UNIFIED EMOJI PROCESSOR - {error_msg}")
                print(f"❌ UNIFIED EMOJI PROCESSOR - {error_msg}")
                return False, [], error_msg

            logger.info(
                f"🎉 UNIFIED EMOJI PROCESSOR - Successfully processed {len(validated_emojis)} emojis for {operation}: {validated_emojis}"
            )
            print(
                f"🎉 UNIFIED EMOJI PROCESSOR - Successfully processed {len(validated_emojis)} emojis for {operation}: {validated_emojis}"
            )

            return True, validated_emojis, ""

        except Exception as e:
            error_msg = f"Emoji processing failed: {str(e)}"
            logger.error(f"💥 UNIFIED EMOJI PROCESSOR - {error_msg}")
            print(f"💥 UNIFIED EMOJI PROCESSOR - {error_msg}")
            return False, [], error_msg

    def extract_emoji_inputs_from_form(self, form_data, num_options: int) -> List[str]:
        """
        Extract emoji inputs from form data consistently

        Args:
            form_data: FastAPI form data
            num_options: Number of poll options

        Returns:
            List of emoji input strings
        """
        emoji_inputs = []

        logger.info(
            f"🔍 EMOJI EXTRACTION - Extracting emojis for {num_options} options"
        )
        print(f"🔍 EMOJI EXTRACTION - Extracting emojis for {num_options} options")

        for i in range(1, num_options + 1):
            emoji_key = f"emoji{i}"
            emoji_value = form_data.get(emoji_key, "")

            # Convert to string and strip whitespace
            if emoji_value is not None:
                emoji_str = str(emoji_value).strip()
            else:
                emoji_str = ""

            emoji_inputs.append(emoji_str)

            logger.info(
                f"🔍 EMOJI EXTRACTION - {emoji_key}: '{emoji_str}' (len: {len(emoji_str)})"
            )
            print(
                f"🔍 EMOJI EXTRACTION - {emoji_key}: '{emoji_str}' (len: {len(emoji_str)})"
            )

        logger.info(f"📋 EMOJI EXTRACTION - Final emoji inputs: {emoji_inputs}")
        print(f"📋 EMOJI EXTRACTION - Final emoji inputs: {emoji_inputs}")

        return emoji_inputs


# Global instance for easy import
_unified_processor = None


def get_unified_emoji_processor(bot):
    """Get or create the unified emoji processor instance"""
    global _unified_processor
    if _unified_processor is None:
        _unified_processor = UnifiedEmojiProcessor(bot)
    return _unified_processor
