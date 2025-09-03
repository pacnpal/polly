"""
Emoji utilities for testing.
Provides random emoji generation using the built-in emoji library.
"""

import emoji
import random
from typing import List, Optional


def get_random_emoji() -> str:
    """
    Get a single random emoji from the emoji library.
    
    Returns:
        str: A random emoji character
    """
    # Get all available emojis from the EMOJI_DATA dictionary
    all_emojis = list(emoji.EMOJI_DATA.keys())
    
    # Return a random emoji
    return random.choice(all_emojis)


def get_random_emojis(count: int = 4) -> List[str]:
    """
    Get multiple random emojis from the emoji library.
    
    Args:
        count: Number of emojis to return (default: 4)
        
    Returns:
        List[str]: List of random emoji characters
    """
    # Get all available emojis from the EMOJI_DATA dictionary
    all_emojis = list(emoji.EMOJI_DATA.keys())
    
    # Return random emojis (with replacement to allow duplicates if needed)
    return [random.choice(all_emojis) for _ in range(count)]


def get_unique_random_emojis(count: int = 4) -> List[str]:
    """
    Get multiple unique random emojis from the emoji library.
    
    Args:
        count: Number of unique emojis to return (default: 4)
        
    Returns:
        List[str]: List of unique random emoji characters
    """
    # Get all available emojis from the EMOJI_DATA dictionary
    all_emojis = list(emoji.EMOJI_DATA.keys())
    
    # Ensure we don't request more emojis than available
    actual_count = min(count, len(all_emojis))
    
    # Return random unique emojis
    return random.sample(all_emojis, actual_count)


def get_random_emoji_by_category(category: Optional[str] = None) -> str:
    """
    Get a random emoji, optionally filtered by category.
    
    Args:
        category: Optional category to filter by (e.g., 'Smileys & Emotion')
        
    Returns:
        str: A random emoji character
    """
    if category:
        # Filter emojis by category if specified
        filtered_emojis = [
            emoji_char for emoji_char, emoji_data in emoji.EMOJI_DATA.items()
            if emoji_data.get('en', '').startswith(category.lower())
        ]
        if filtered_emojis:
            return random.choice(filtered_emojis)
    
    # Fall back to any random emoji
    return get_random_emoji()


def get_random_poll_emojis(option_count: int = 4) -> List[str]:
    """
    Get random emojis suitable for poll options.
    Prioritizes commonly used poll emojis but falls back to any emoji.
    
    Args:
        option_count: Number of poll options (default: 4)
        
    Returns:
        List[str]: List of random emojis for poll options
    """
    # Common poll emojis that work well for reactions
    common_poll_emojis = [
        "🇦", "🇧", "🇨", "🇩", "🇪", "🇫", "🇬", "🇭", "🇮", "🇯",
        "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟",
        "✅", "❌", "👍", "👎", "❤️", "💙", "💚", "💛", "🧡", "💜",
        "🔴", "🔵", "🟢", "🟡", "🟠", "🟣", "⚫", "⚪", "🟤", "🔶",
        "😀", "😃", "😄", "😁", "😊", "😍", "🤔", "😎", "🥳", "🤩",
        "🎉", "🎊", "🔥", "💯", "⭐", "🌟", "✨", "💫", "🚀", "🎯"
    ]
    
    # If we need more emojis than available common ones, mix with random ones
    if option_count <= len(common_poll_emojis):
        return random.sample(common_poll_emojis, option_count)
    else:
        # Use all common emojis and fill the rest with random ones
        selected_emojis = common_poll_emojis.copy()
        remaining_count = option_count - len(common_poll_emojis)
        
        # Get additional random emojis
        all_emojis = list(emoji.EMOJI_DATA.keys())
        additional_emojis = [
            emoji_char for emoji_char in all_emojis 
            if emoji_char not in selected_emojis
        ]
        
        if additional_emojis:
            selected_emojis.extend(random.sample(additional_emojis, min(remaining_count, len(additional_emojis))))
        
        return selected_emojis[:option_count]


def is_valid_poll_emoji(emoji_char: str) -> bool:
    """
    Check if an emoji is valid for use in polls (can be used as Discord reactions).
    
    Args:
        emoji_char: The emoji character to check
        
    Returns:
        bool: True if the emoji is valid for polls
    """
    # Check if it's a valid emoji in the emoji library
    if emoji_char not in emoji.EMOJI_DATA:
        return False
    
    # Additional checks for Discord compatibility could be added here
    # For now, we'll assume all emojis in the library are valid
    return True


def get_emoji_description(emoji_char: str) -> str:
    """
    Get the description of an emoji.
    
    Args:
        emoji_char: The emoji character
        
    Returns:
        str: Description of the emoji, or the emoji itself if no description found
    """
    emoji_data = emoji.EMOJI_DATA.get(emoji_char, {})
    return emoji_data.get('en', emoji_char)
