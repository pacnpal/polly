import discord
from decouple import config
from discord.ext import commands
import re
import unicodedata
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot setup with required intents
intents = discord.Intents.default()
intents.emojis_and_stickers = True  # Required for emoji events and caching
intents.guilds = True  # Required for guild information

bot = commands.Bot(command_prefix='!', intents=intents)

class EmojiValidator:
    """A comprehensive emoji validator for Discord.py"""
    
    def __init__(self, bot_instance):
        self.bot = bot_instance
        
    def is_unicode_emoji(self, text: str) -> bool:
        """
        Check if the text is a valid Unicode emoji.
        
        Args:
            text (str): The text to validate
            
        Returns:
            bool: True if it's a Unicode emoji, False otherwise
        """
        try:
            # Remove variation selectors and check if it's an emoji
            cleaned_text = text.replace('\ufe0f', '').replace('\ufe0e', '')
            
            # Check if all characters are emoji-related
            for char in cleaned_text:
                if not unicodedata.category(char).startswith('So') and not unicodedata.name(char, '').startswith('EMOJI'):
                    # Allow some specific emoji-related categories
                    if unicodedata.category(char) not in ['Mn', 'Me', 'Cf']:  # Modifiers and formatters
                        return False
            
            return len(cleaned_text) > 0
        except Exception:
            return False
    
    def is_custom_emoji_format(self, text: str) -> bool:
        """
        Check if the text matches Discord's custom emoji format: <:name:id> or <a:name:id>
        
        Args:
            text (str): The text to validate
            
        Returns:
            bool: True if it matches custom emoji format, False otherwise
        """
        pattern = r'^<(a?):(\w+):(\d+)>$'
        return bool(re.match(pattern, text))
    
    def parse_custom_emoji(self, text: str) -> dict:
        """
        Parse a custom emoji string and extract components.
        
        Args:
            text (str): The custom emoji string
            
        Returns:
            dict: Dictionary with 'animated', 'name', and 'id' keys, or None if invalid
        """
        pattern = r'^<(a?):(\w+):(\d+)>$'
        match = re.match(pattern, text)
        
        if match:
            return {
                'animated': bool(match.group(1)),  # 'a' if animated, empty if not
                'name': match.group(2),
                'id': int(match.group(3))
            }
        return None
    
    def get_emoji_by_id(self, emoji_id: int) -> discord.Emoji:
        """
        Get an emoji object by its ID from the bot's cache.
        
        Args:
            emoji_id (int): The emoji ID
            
        Returns:
            discord.Emoji: The emoji object if found, None otherwise
        """
        return self.bot.get_emoji(emoji_id)
    
    def get_emoji_by_name(self, name: str, guild: discord.Guild = None) -> discord.Emoji:
        """
        Get an emoji object by its name.
        
        Args:
            name (str): The emoji name
            guild (discord.Guild, optional): Specific guild to search in
            
        Returns:
            discord.Emoji: The emoji object if found, None otherwise
        """
        if guild:
            return discord.utils.get(guild.emojis, name=name)
        else:
            # Search through all available emojis
            return discord.utils.get(self.bot.emojis, name=name)
    
    def is_emoji_usable(self, emoji: discord.Emoji, guild: discord.Guild = None) -> bool:
        """
        Check if an emoji is usable by the bot in the given context.
        
        Args:
            emoji (discord.Emoji): The emoji to check
            guild (discord.Guild, optional): The guild context
            
        Returns:
            bool: True if the emoji is usable, False otherwise
        """
        if not emoji:
            return False
            
        # Use the built-in is_usable method if available
        if hasattr(emoji, 'is_usable'):
            return emoji.is_usable()
        
        # Fallback logic for older versions
        if guild and emoji.guild_id == guild.id:
            return True
        
        # Check if emoji is available to the bot
        return emoji in self.bot.emojis
    
    async def validate_emoji(self, emoji_input: str, guild: discord.Guild = None) -> dict:
        """
        Comprehensive emoji validation function.
        
        Args:
            emoji_input (str): The emoji to validate (Unicode, custom format, or name)
            guild (discord.Guild, optional): Guild context for validation
            
        Returns:
            dict: Validation result with details
        """
        result = {
            'valid': False,
            'type': None,
            'emoji': None,
            'usable': False,
            'details': {}
        }
        
        # Check if it's a Unicode emoji
        if self.is_unicode_emoji(emoji_input):
            result.update({
                'valid': True,
                'type': 'unicode',
                'emoji': emoji_input,
                'usable': True,
                'details': {'name': unicodedata.name(emoji_input[0], 'Unknown Unicode Character')}
            })
            return result
        
        # Check if it's a custom emoji format
        if self.is_custom_emoji_format(emoji_input):
            parsed = self.parse_custom_emoji(emoji_input)
            emoji_obj = self.get_emoji_by_id(parsed['id'])
            
            result.update({
                'valid': True,
                'type': 'custom',
                'emoji': emoji_obj,
                'usable': self.is_emoji_usable(emoji_obj, guild),
                'details': {
                    'parsed': parsed,
                    'found_in_cache': emoji_obj is not None,
                    'guild_id': emoji_obj.guild_id if emoji_obj else None
                }
            })
            return result
        
        # Try to find by name (assume it's a custom emoji name)
        emoji_obj = self.get_emoji_by_name(emoji_input, guild)
        if emoji_obj:
            result.update({
                'valid': True,
                'type': 'custom_by_name',
                'emoji': emoji_obj,
                'usable': self.is_emoji_usable(emoji_obj, guild),
                'details': {
                    'id': emoji_obj.id,
                    'animated': emoji_obj.animated,
                    'guild_id': emoji_obj.guild_id
                }
            })
            return result
        
        # If we get here, the emoji is invalid
        result['details'] = {'reason': 'Emoji not found or invalid format'}
        return result

# Initialize the validator
emoji_validator = EmojiValidator(bot)

@bot.event
async def on_ready():
    """Event fired when the bot is ready."""
    logger.info(f'{bot.user} has connected to Discord!')
    logger.info(f'Bot is in {len(bot.guilds)} guilds')
    logger.info(f'Bot has access to {len(bot.emojis)} emojis')

@bot.command(name='validate_emoji')
async def validate_emoji_command(ctx, *, emoji_input: str):
    """
    Validate an emoji and provide detailed information.
    
    Usage:
        !validate_emoji 😀
        !validate_emoji <:python:1234567890>
        !validate_emoji python
    """
    result = await emoji_validator.validate_emoji(emoji_input, ctx.guild)
    
    embed = discord.Embed(
        title="Emoji Validation Result",
        color=discord.Color.green() if result['valid'] else discord.Color.red()
    )
    
    embed.add_field(name="Input", value=f"`{emoji_input}`", inline=True)
    embed.add_field(name="Valid", value="✅ Yes" if result['valid'] else "❌ No", inline=True)
    embed.add_field(name="Type", value=result['type'] or "Invalid", inline=True)
    
    if result['valid']:
        embed.add_field(name="Usable", value="✅ Yes" if result['usable'] else "❌ No", inline=True)
        
        if result['type'] == 'unicode':
            embed.add_field(name="Character Name", value=result['details'].get('name', 'Unknown'), inline=False)
        
        elif result['type'] in ['custom', 'custom_by_name']:
            if result['emoji']:
                emoji_obj = result['emoji']
                embed.add_field(name="Emoji Name", value=emoji_obj.name, inline=True)
                embed.add_field(name="Emoji ID", value=str(emoji_obj.id), inline=True)
                embed.add_field(name="Animated", value="Yes" if emoji_obj.animated else "No", inline=True)
                embed.add_field(name="From Guild", value=emoji_obj.guild.name if emoji_obj.guild else "Unknown", inline=True)
                
                # Add emoji URL if possible
                if hasattr(emoji_obj, 'url'):
                    embed.set_thumbnail(url=emoji_obj.url)
            else:
                embed.add_field(name="Note", value="Emoji format is valid but not found in bot's cache", inline=False)
    
    else:
        embed.add_field(name="Reason", value=result['details'].get('reason', 'Unknown error'), inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name='list_guild_emojis')
async def list_guild_emojis(ctx, limit: int = 10):
    """
    List custom emojis available in the current guild.
    
    Usage:
        !list_guild_emojis
        !list_guild_emojis 20
    """
    if not ctx.guild:
        await ctx.send("❌ This command can only be used in a guild!")
        return
    
    emojis = ctx.guild.emojis[:limit]
    
    if not emojis:
        await ctx.send("❌ No custom emojis found in this guild.")
        return
    
    embed = discord.Embed(
        title=f"Guild Emojis ({len(ctx.guild.emojis)} total, showing {len(emojis)})",
        color=discord.Color.blue()
    )
    
    emoji_list = []
    for emoji in emojis:
        usable = emoji_validator.is_emoji_usable(emoji, ctx.guild)
        status = "✅" if usable else "❌"
        emoji_list.append(f"{status} {emoji} `:{emoji.name}:` (ID: {emoji.id})")
    
    embed.description = "\n".join(emoji_list)
    await ctx.send(embed=embed)

@bot.command(name='emoji_info')
async def emoji_info_command(ctx, emoji_id: int):
    """
    Get detailed information about a specific emoji by ID.
    
    Usage:
        !emoji_info 1234567890
    """
    emoji = emoji_validator.get_emoji_by_id(emoji_id)
    
    if not emoji:
        await ctx.send(f"❌ No emoji found with ID: {emoji_id}")
        return
    
    embed = discord.Embed(
        title=f"Emoji Information: {emoji.name}",
        color=discord.Color.blue()
    )
    
    embed.add_field(name="Name", value=f"`:{emoji.name}:`", inline=True)
    embed.add_field(name="ID", value=str(emoji.id), inline=True)
    embed.add_field(name="Animated", value="Yes" if emoji.animated else "No", inline=True)
    embed.add_field(name="Guild", value=emoji.guild.name if emoji.guild else "Unknown", inline=True)
    embed.add_field(name="Usable", value="✅ Yes" if emoji_validator.is_emoji_usable(emoji, ctx.guild) else "❌ No", inline=True)
    embed.add_field(name="Created At", value=emoji.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"), inline=True)
    
    if hasattr(emoji, 'url'):
        embed.set_thumbnail(url=emoji.url)
        embed.add_field(name="URL", value=f"[Click here]({emoji.url})", inline=False)
    
    # Show emoji usage format
    embed.add_field(name="Usage Format", value=f"`{emoji}`", inline=False)
    
    await ctx.send(embed=embed)

@bot.event
async def on_guild_emojis_update(guild, before, after):
    """Event fired when a guild's emojis are updated."""
    logger.info(f"Guild {guild.name} emoji update: {len(before)} -> {len(after)} emojis")

# Error handling for commands
@bot.event
async def on_command_error(ctx, error):
    """Handle command errors."""
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing required argument: `{error.param}`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Invalid argument: {error}")
    else:
        logger.error(f"Unexpected error: {error}")
        await ctx.send("❌ An unexpected error occurred. Please check the logs.")

# Help command override to show available commands
@bot.command(name='emoji_help')
async def emoji_help_command(ctx):
    """Show help for emoji validation commands."""
    embed = discord.Embed(
        title="Emoji Validator Commands",
        description="Commands for validating and managing Discord emojis",
        color=discord.Color.gold()
    )
    
    commands_info = [
        ("!validate_emoji <emoji>", "Validate any emoji (Unicode or custom)"),
        ("!list_guild_emojis [limit]", "List custom emojis in the current guild"),
        ("!emoji_info <emoji_id>", "Get detailed information about an emoji"),
        ("!emoji_help", "Show this help message")
    ]
    
    for name, desc in commands_info:
        embed.add_field(name=name, value=desc, inline=False)
    
    embed.add_field(
        name="Examples",
        value="""
        `!validate_emoji 😀`
        `!validate_emoji <:python:1234567890>`
        `!validate_emoji python`
        `!list_guild_emojis 5`
        `!emoji_info 1234567890`
        """,
        inline=False
    )
    
    await ctx.send(embed=embed)

if __name__ == "__main__":
    # Load bot token from environment variables using python-decouple
    # Create a .env file in the same directory with: DISCORD_BOT_TOKEN=your_actual_token_here
    try:
        TOKEN = config('DISCORD_BOT_TOKEN')
        
        if not TOKEN:
            raise ValueError("Bot token is empty")
            
        print("✅ Bot token loaded successfully from environment")
        bot.run(TOKEN)
        
    except Exception as e:
        print("❌ Error loading bot token from environment variables!")
        print(f"Error: {e}")
        print("\n📋 Setup Instructions:")
        print("1. Install python-decouple: pip install python-decouple")
        print("2. Create a .env file in the same directory as this script")
        print("3. Add this line to your .env file: DISCORD_BOT_TOKEN=your_actual_token_here")
        print("4. Get your token from: https://discord.com/developers/applications")
        print("5. Make sure to add .env to your .gitignore file for security!")

