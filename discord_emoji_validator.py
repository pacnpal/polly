import discord
from discord.ext import commands
from decouple import config
import re
import unicodedata
import logging
import asyncio
import urllib.parse

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot setup with required intents
intents = discord.Intents.default()
intents.emojis_and_stickers = True  # Required for emoji events and caching
intents.guilds = True  # Required for guild information
intents.message_content = True  # Required for reading message content in commands

bot = commands.Bot(command_prefix='!', intents=intents)

class EmojiValidator:
    """A comprehensive emoji validator for Discord.py"""
    
    def __init__(self, bot_instance):
        self.bot = bot_instance
        
    async def get_message_from_url(self, message_url: str) -> discord.Message:
        """
        Get a Discord message object from a message URL.
        
        Args:
            message_url (str): Discord message URL
            
        Returns:
            discord.Message: The message object if found, None otherwise
        """
        logger.info(f"Attempting to get message from URL: {message_url}")
        
        try:
            # Parse Discord message URL format:
            # https://discord.com/channels/{guild_id}/{channel_id}/{message_id}
            # or https://discordapp.com/channels/{guild_id}/{channel_id}/{message_id}
            url_pattern = r'https://(?:discord|discordapp)\.com/channels/(\d+)/(\d+)/(\d+)'
            match = re.match(url_pattern, message_url)
            
            if not match:
                logger.warning(f"Invalid message URL format: {message_url}")
                return None
                
            guild_id, channel_id, message_id = map(int, match.groups())
            logger.info(f"Parsed URL - Guild: {guild_id}, Channel: {channel_id}, Message: {message_id}")
            
            # Get the channel
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logger.info(f"Channel {channel_id} not found in cache, attempting to fetch...")
                # Try fetching the channel if not in cache
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                    logger.info(f"Successfully fetched channel: {channel.name} ({channel_id})")
                except discord.NotFound:
                    logger.error(f"Channel {channel_id} not found or bot lacks access")
                    return None
                except Exception as e:
                    logger.error(f"Error fetching channel {channel_id}: {e}")
                    return None
            else:
                logger.info(f"Found channel in cache: {channel.name} ({channel_id})")
            
            # Get the message
            try:
                logger.info(f"Attempting to fetch message {message_id} from channel {channel_id}")
                message = await channel.fetch_message(message_id)
                logger.info(f"Successfully retrieved message {message_id} from {channel.name}")
                return message
            except discord.NotFound:
                logger.error(f"Message {message_id} not found in channel {channel_id}")
                return None
            except Exception as e:
                logger.error(f"Error fetching message {message_id}: {e}")
                return None
                
        except Exception as e:
            logger.error(f"Unexpected error getting message from URL: {e}")
            return None
    
    async def test_emoji_reaction(self, emoji_input: str, test_message_url: str = None) -> dict:
        """
        Test if an emoji can be used as a reaction by actually trying to add it.
        
        Args:
            emoji_input (str): The emoji to test
            test_message_url (str): URL of message to test reaction on
            
        Returns:
            dict: Test result with success status and details
        """
        logger.info(f"Starting emoji reaction test for: '{emoji_input}'")
        
        result = {
            'can_react': False,
            'error': None,
            'message_found': False,
            'reaction_added': False,
            'reaction_removed': False,
            'emoji_encoded': None
        }
        
        if not test_message_url:
            logger.warning("No test message URL provided for reaction test")
            result['error'] = 'No test message URL provided'
            return result
            
        # Get the test message
        logger.info(f"Retrieving test message from URL: {test_message_url}")
        test_message = await self.get_message_from_url(test_message_url)
        if not test_message:
            logger.error("Failed to retrieve test message")
            result['error'] = 'Could not find test message from URL'
            return result
            
        result['message_found'] = True
        logger.info(f"Test message found: {test_message.id} in {test_message.channel.name}")
        
        try:
            # Prepare emoji for reaction - handle URL encoding properly
            logger.info(f"Preparing emoji '{emoji_input}' for reaction...")
            emoji_to_use = self._prepare_emoji_for_reaction(emoji_input)
            result['emoji_encoded'] = emoji_to_use
            logger.info(f"Emoji prepared for reaction: '{emoji_to_use}'")
            
            # Try to add the reaction
            logger.info(f"Attempting to add reaction '{emoji_to_use}' to message {test_message.id}")
            await test_message.add_reaction(emoji_to_use)
            result['reaction_added'] = True
            result['can_react'] = True
            logger.info("✅ Reaction added successfully!")
            
            # Wait a moment then remove the reaction to clean up
            logger.info("Waiting 1 second before cleanup...")
            await asyncio.sleep(1)
            
            logger.info("Removing reaction for cleanup...")
            await test_message.remove_reaction(emoji_to_use, self.bot.user)
            result['reaction_removed'] = True
            logger.info("✅ Reaction removed successfully (cleanup completed)")
            
        except discord.HTTPException as e:
            if e.code == 10014:
                logger.error(f"❌ Unknown Emoji error (10014): '{emoji_input}' -> '{emoji_to_use}'")
                result['error'] = f'Unknown Emoji (10014): Emoji not found or invalid format'
            else:
                logger.error(f"❌ Discord HTTP error ({e.code}): {e}")
                result['error'] = f'Discord API error ({e.code}): {e}'
        except discord.Forbidden:
            logger.error("❌ Bot lacks permission to add reactions")
            result['error'] = 'Bot lacks permission to add reactions'
        except discord.NotFound:
            logger.error("❌ Message not found or emoji invalid during reaction")
            result['error'] = 'Message not found or emoji invalid'
        except discord.InvalidArgument:
            logger.error(f"❌ Invalid emoji format: '{emoji_input}' -> '{emoji_to_use}'")
            result['error'] = 'Invalid emoji format'
        except Exception as e:
            logger.error(f"❌ Unexpected error during reaction test: {e}")
            result['error'] = f'Unexpected error: {e}'
            
        logger.info(f"Reaction test completed. Can react: {result['can_react']}")
        return result
    
    def _prepare_emoji_for_reaction(self, emoji_input: str) -> str:
        """
        Prepare an emoji for use in reactions by properly encoding it.
        
        Args:
            emoji_input (str): The raw emoji input
            
        Returns:
            str: The properly formatted emoji for reactions
        """
        logger.debug(f"Preparing emoji for reaction: '{emoji_input}'")
        
        # If it's a custom emoji format (<:name:id> or <a:name:id>), return as-is
        if self.is_custom_emoji_format(emoji_input):
            logger.debug(f"Emoji is custom format, using as-is: '{emoji_input}'")
            return emoji_input
        
        # For Unicode emojis, Discord actually expects the raw Unicode characters
        # NOT URL encoded strings for reactions!
        if self.is_unicode_emoji(emoji_input):
            # Remove variation selectors but keep as Unicode characters
            cleaned = emoji_input.replace('\ufe0f', '').replace('\ufe0e', '')
            logger.debug(f"Unicode emoji cleaned (variation selectors removed): '{emoji_input}' -> '{cleaned}'")
            return cleaned
        
        # If it's just a name, try to find the emoji and return its proper format
        # This will be handled by get_emoji_by_name in the validation process
        logger.debug(f"Emoji appears to be a name, returning as-is: '{emoji_input}'")
        return emoji_input
        
    def is_unicode_emoji(self, text: str) -> bool:
        """
        Check if the text is a valid Unicode emoji.
        
        Args:
            text (str): The text to validate
            
        Returns:
            bool: True if it's a Unicode emoji, False otherwise
        """
        logger.debug(f"Checking if '{text}' is Unicode emoji")
        
        try:
            # Remove variation selectors and check if it's an emoji
            cleaned_text = text.replace('\ufe0f', '').replace('\ufe0e', '')
            
            # Check if all characters are emoji-related
            for char in cleaned_text:
                if not unicodedata.category(char).startswith('So') and not unicodedata.name(char, '').startswith('EMOJI'):
                    # Allow some specific emoji-related categories
                    if unicodedata.category(char) not in ['Mn', 'Me', 'Cf']:  # Modifiers and formatters
                        logger.debug(f"Character '{char}' (category: {unicodedata.category(char)}) is not emoji-related")
                        return False
            
            is_emoji = len(cleaned_text) > 0
            logger.debug(f"Unicode emoji check result: {is_emoji}")
            return is_emoji
        except Exception as e:
            logger.debug(f"Error checking Unicode emoji: {e}")
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
        matches = bool(re.match(pattern, text))
        logger.debug(f"Custom emoji format check for '{text}': {matches}")
        return matches
    
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
        logger.debug(f"Looking up emoji by ID: {emoji_id}")
        emoji = self.bot.get_emoji(emoji_id)
        if emoji:
            logger.debug(f"Found emoji: {emoji.name} ({emoji_id}) from {emoji.guild.name}")
        else:
            logger.debug(f"Emoji with ID {emoji_id} not found in bot cache")
        return emoji
    
    def get_emoji_by_name(self, name: str, guild: discord.Guild = None) -> discord.Emoji:
        """
        Get an emoji object by its name.
        
        Args:
            name (str): The emoji name
            guild (discord.Guild, optional): Specific guild to search in
            
        Returns:
            discord.Emoji: The emoji object if found, None otherwise
        """
        logger.debug(f"Looking up emoji by name: '{name}'" + (f" in guild {guild.name}" if guild else " globally"))
        
        if guild:
            emoji = discord.utils.get(guild.emojis, name=name)
            if emoji:
                logger.debug(f"Found emoji in guild: {emoji.name} ({emoji.id})")
            else:
                logger.debug(f"Emoji '{name}' not found in guild {guild.name}")
        else:
            # Search through all available emojis
            emoji = discord.utils.get(self.bot.emojis, name=name)
            if emoji:
                logger.debug(f"Found emoji globally: {emoji.name} ({emoji.id}) from {emoji.guild.name}")
            else:
                logger.debug(f"Emoji '{name}' not found in bot's emoji cache")
        
        return emoji
    
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
    
    async def validate_emoji(self, emoji_input: str, guild: discord.Guild = None, test_reaction: bool = False, test_message_url: str = None) -> dict:
        """
        Comprehensive emoji validation function.
        
        Args:
            emoji_input (str): The emoji to validate (Unicode, custom format, or name)
            guild (discord.Guild, optional): Guild context for validation
            test_reaction (bool): Whether to test actual reaction capability
            test_message_url (str): URL of message to test reaction on
            
        Returns:
            dict: Validation result with details
        """
        logger.info(f"Starting emoji validation for: '{emoji_input}'" + (f" in guild {guild.name}" if guild else " globally"))
        
        result = {
            'valid': False,
            'type': None,
            'emoji': None,
            'usable': False,
            'can_react': None,
            'reaction_test': None,
            'details': {}
        }
        
        # Check if it's a Unicode emoji
        if self.is_unicode_emoji(emoji_input):
            logger.info(f"✅ Emoji '{emoji_input}' identified as Unicode emoji")
            result.update({
                'valid': True,
                'type': 'unicode',
                'emoji': emoji_input,
                'usable': True,
                'details': {'name': unicodedata.name(emoji_input[0], 'Unknown Unicode Character')}
            })
        
        # Check if it's a custom emoji format
        elif self.is_custom_emoji_format(emoji_input):
            logger.info(f"✅ Emoji '{emoji_input}' identified as custom emoji format")
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
            
            if emoji_obj:
                logger.info(f"Custom emoji found in cache: {emoji_obj.name} from {emoji_obj.guild.name}")
            else:
                logger.warning(f"Custom emoji with ID {parsed['id']} not found in bot cache")
        
        else:
            # Try to find by name (assume it's a custom emoji name)
            logger.info(f"Attempting to find emoji by name: '{emoji_input}'")
            emoji_obj = self.get_emoji_by_name(emoji_input, guild)
            if emoji_obj:
                logger.info(f"✅ Found emoji by name: {emoji_obj.name} ({emoji_obj.id})")
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
            else:
                logger.warning(f"❌ Emoji '{emoji_input}' not found - invalid format or not accessible")
                # If we get here, the emoji is invalid
                result['details'] = {'reason': 'Emoji not found or invalid format'}
                return result
        
        # Test actual reaction capability if requested
        if test_reaction and result['valid'] and test_message_url:
            logger.info("Proceeding with reaction testing...")
            # For reaction testing, we need to use the proper format
            emoji_for_reaction = emoji_input
            
            # If we found an emoji object (custom emoji), use its proper format
            if result['type'] in ['custom', 'custom_by_name'] and result['emoji']:
                emoji_for_reaction = str(result['emoji'])  # This gives us <:name:id> format
                logger.info(f"Using emoji object format for reaction test: {emoji_for_reaction}")
            
            reaction_test = await self.test_emoji_reaction(emoji_for_reaction, test_message_url)
            result['can_react'] = reaction_test['can_react']
            result['reaction_test'] = reaction_test
        elif test_reaction:
            logger.warning("Reaction testing requested but no test message URL provided or emoji invalid")
        
        logger.info(f"Emoji validation completed. Valid: {result['valid']}, Type: {result['type']}, Usable: {result['usable']}, Can React: {result['can_react']}")
        return result

# Initialize the validator
emoji_validator = EmojiValidator(bot)

@bot.event
async def on_ready():
    """Event fired when the bot is ready."""
    logger.info(f'🤖 {bot.user} has connected to Discord!')
    logger.info(f'📊 Bot is in {len(bot.guilds)} guilds')
    logger.info(f'😀 Bot has access to {len(bot.emojis)} emojis')
    
    # Log guild information
    for guild in bot.guilds:
        logger.info(f'  - {guild.name} ({guild.id}) - {len(guild.emojis)} emojis')

@bot.event
async def on_guild_emojis_update(guild, before, after):
    """Event fired when a guild's emojis are updated."""
    logger.info(f"🔄 Guild {guild.name} emoji update: {len(before)} -> {len(after)} emojis")
    
    # Log added emojis
    added = set(after) - set(before)
    if added:
        logger.info(f"  ➕ Added emojis: {[e.name for e in added]}")
    
    # Log removed emojis
    removed = set(before) - set(after)
    if removed:
        logger.info(f"  ➖ Removed emojis: {[e.name for e in removed]}")

# Error handling for commands
@bot.event
async def on_command_error(ctx, error):
    """Handle command errors."""
    logger.error(f"Command error in {ctx.command} by {ctx.author}: {error}")
    
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        logger.warning(f"Missing argument: {error.param}")
        await ctx.send(f"❌ Missing required argument: `{error.param}`")
    elif isinstance(error, commands.BadArgument):
        logger.warning(f"Bad argument: {error}")
        await ctx.send(f"❌ Invalid argument: {error}")
    else:
        logger.error(f"Unexpected error: {error}")
        await ctx.send("❌ An unexpected error occurred. Please check the logs.")

@bot.event
async def on_command(ctx):
    """Called when a command is invoked."""
    logger.info(f"🔧 Command '{ctx.command}' invoked by {ctx.author} in {ctx.guild.name if ctx.guild else 'DM'}")

@bot.command(name='validate_emoji')
async def validate_emoji_command(ctx, *, emoji_input: str):
    """
    Validate an emoji and test if it can be used as a reaction.
    
    Usage:
        !validate_emoji 😀
        !validate_emoji <:python:1234567890>
        !validate_emoji python
    """
    logger.info(f"Validate emoji command called by {ctx.author} in {ctx.guild.name if ctx.guild else 'DM'}: '{emoji_input}'")
    
    # Get test message URL from environment
    test_message_url = None
    try:
        test_message_url = config('TEST_MESSAGE_URL', default=None)
        if test_message_url:
            logger.info("Test message URL loaded from environment for reaction testing")
        else:
            logger.info("No test message URL configured - reaction testing disabled")
    except Exception as e:
        logger.warning(f"Error loading test message URL from config: {e}")
    
    # Validate emoji with reaction testing
    result = await emoji_validator.validate_emoji(
        emoji_input, 
        ctx.guild, 
        test_reaction=bool(test_message_url),
        test_message_url=test_message_url
    )
    
    logger.info(f"Sending validation result embed to user...")
    
    embed = discord.Embed(
        title="Emoji Validation Result",
        color=discord.Color.green() if result['valid'] else discord.Color.red()
    )
    
    embed.add_field(name="Input", value=f"`{emoji_input}`", inline=True)
    embed.add_field(name="Valid", value="✅ Yes" if result['valid'] else "❌ No", inline=True)
    embed.add_field(name="Type", value=result['type'] or "Invalid", inline=True)
    
    if result['valid']:
        embed.add_field(name="Usable", value="✅ Yes" if result['usable'] else "❌ No", inline=True)
        
        # Add reaction test results if available
        if result['reaction_test'] is not None:
            reaction_status = "✅ Yes" if result['can_react'] else "❌ No"
            embed.add_field(name="Can React", value=reaction_status, inline=True)
            
            if result['reaction_test']['error']:
                embed.add_field(name="Reaction Error", value=result['reaction_test']['error'], inline=False)
                if result['reaction_test'].get('emoji_encoded'):
                    embed.add_field(name="Encoded Format", value=f"`{result['reaction_test']['emoji_encoded']}`", inline=False)
            else:
                test_details = []
                if result['reaction_test']['message_found']:
                    test_details.append("✅ Test message found")
                if result['reaction_test']['reaction_added']:
                    test_details.append("✅ Reaction added successfully")
                if result['reaction_test']['reaction_removed']:
                    test_details.append("✅ Reaction removed (cleanup)")
                
                if test_details:
                    embed.add_field(name="Test Results", value="\n".join(test_details), inline=False)
        elif test_message_url:
            embed.add_field(name="Reaction Test", value="❌ Failed to run test", inline=True)
        else:
            embed.add_field(name="Reaction Test", value="⚠️ No test message URL configured", inline=True)
        
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
    
    # Add configuration info in footer
    footer_text = "💡 Configure TEST_MESSAGE_URL in .env for reaction testing"
    if test_message_url:
        footer_text = "✅ Reaction testing enabled"
    embed.set_footer(text=footer_text)
    
    logger.info(f"Sending validation result to {ctx.author}")
    await ctx.send(embed=embed)

@bot.command(name='test_reaction')
async def test_reaction_command(ctx, *, emoji_input: str):
    """
    Test if an emoji can be added as a reaction to the configured test message.
    
    Usage:
        !test_reaction 😀
        !test_reaction <:python:1234567890>
    """
    # Clean up input - remove comments and extra whitespace
    original_input = emoji_input
    if '#' in emoji_input:
        emoji_input = emoji_input.split('#')[0].strip()
        logger.info(f"Detected comment in input, using cleaned emoji: '{original_input}' -> '{emoji_input}'")
    else:
        emoji_input = emoji_input.strip()
    
    if not emoji_input:
        await ctx.send("❌ No emoji provided after cleaning input!")
        return
    
    logger.info(f"Test reaction command called by {ctx.author} in {ctx.guild.name if ctx.guild else 'DM'}: '{emoji_input}'")
    
    # Get test message URL from environment
    try:
        test_message_url = config('TEST_MESSAGE_URL')
        logger.info(f"Test message URL loaded from config: {test_message_url[:50]}...")
    except Exception as e:
        logger.error(f"Failed to load TEST_MESSAGE_URL from config: {e}")
        await ctx.send("❌ No test message URL configured in .env file!\nAdd: `TEST_MESSAGE_URL=https://discord.com/channels/guild_id/channel_id/message_id`")
        return
    
    embed = discord.Embed(
        title="Reaction Test Result",
        color=discord.Color.blue()
    )
    
    embed.add_field(name="Testing Emoji", value=f"`{emoji_input}`", inline=True)
    if original_input != emoji_input:
        embed.add_field(name="Original Input", value=f"`{original_input}`", inline=True)
    
    # Test the reaction
    emoji_for_test = emoji_input
    
    # If the input looks like an emoji name, try to find the actual emoji
    if not emoji_validator.is_unicode_emoji(emoji_input) and not emoji_validator.is_custom_emoji_format(emoji_input):
        logger.info(f"Emoji appears to be a name, attempting to resolve: '{emoji_input}'")
        found_emoji = emoji_validator.get_emoji_by_name(emoji_input, ctx.guild)
        if found_emoji:
            emoji_for_test = str(found_emoji)  # Convert to proper <:name:id> format
            logger.info(f"Resolved emoji name to format: {emoji_for_test}")
        else:
            logger.warning(f"Could not resolve emoji name: '{emoji_input}'")
    
    result = await emoji_validator.test_emoji_reaction(emoji_for_test, test_message_url)
    
    if result['can_react']:
        embed.color = discord.Color.green()
        embed.add_field(name="Result", value="✅ Can be used as reaction!", inline=True)
        logger.info(f"✅ Emoji '{emoji_input}' can be used as reaction")
    else:
        embed.color = discord.Color.red()
        embed.add_field(name="Result", value="❌ Cannot be used as reaction", inline=True)
        logger.info(f"❌ Emoji '{emoji_input}' cannot be used as reaction")
    
    # Add detailed test results
    test_details = []
    if result['message_found']:
        test_details.append("✅ Test message found")
    else:
        test_details.append("❌ Test message not found")
    
    if result['reaction_added']:
        test_details.append("✅ Reaction added successfully")
    
    if result['reaction_removed']:
        test_details.append("✅ Reaction removed (cleanup)")
    
    if result['error']:
        test_details.append(f"❌ Error: {result['error']}")
    
    if result.get('emoji_encoded'):
        embed.add_field(name="Encoded Format Used", value=f"`{result['emoji_encoded']}`", inline=False)
    
    embed.add_field(name="Test Details", value="\n".join(test_details), inline=False)
    
    # Show the test message URL (truncated for security)
    url_display = test_message_url[:50] + "..." if len(test_message_url) > 50 else test_message_url
    embed.set_footer(text=f"Test message: {url_display}")
    
    logger.info(f"Sending reaction test result to {ctx.author}")
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
        ("!validate_emoji <emoji>", "Validate emoji and test as reaction (if configured)"),
        ("!test_reaction <emoji>", "Test if emoji can be used as a reaction"),
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
        `!test_reaction 🚀`
        `!list_guild_emojis 5`
        `!emoji_info 1234567890`
        """,
        inline=False
    )
    
    embed.add_field(
        name="Configuration",
        value="""
        Add to your .env file:
        `TEST_MESSAGE_URL=https://discord.com/channels/guild_id/channel_id/message_id`
        
        This enables actual reaction testing to verify if emojis work as reactions.
        """,
        inline=False
    )
    
    await ctx.send(embed=embed)

if __name__ == "__main__":
    # Load configuration from environment variables using python-decouple
    try:
        TOKEN = config('DISCORD_TOKEN')
        
        if not TOKEN:
            raise ValueError("Bot token is empty")
        
        # Optional: Load test message URL
        test_message_url = config('TEST_MESSAGE_URL', default=None)
        if test_message_url:
            logger.info("✅ Test message URL configured for reaction testing")
        else:
            logger.info("⚠️  No test message URL configured - reaction testing disabled")
            
        print("✅ Bot token loaded successfully from environment")
        bot.run(TOKEN)
        
    except Exception as e:
        print("❌ Error loading configuration from environment variables!")
        print(f"Error: {e}")
        print("\n📋 Setup Instructions:")
        print("1. Install dependencies:")
        print("   pip install discord.py python-decouple")
        print("\n2. Create a .env file in the same directory as this script")
        print("\n3. Add these lines to your .env file:")
        print("   DISCORD_TOKEN=your_actual_token_here")
        print("   TEST_MESSAGE_URL=https://discord.com/channels/guild_id/channel_id/message_id")
        print("\n4. Get your bot token from: https://discord.com/developers/applications")
        print("\n5. Get a message URL by right-clicking any Discord message and selecting 'Copy Message Link'")
        print("\n6. Make sure to add .env to your .gitignore file for security!")
        print("\n📝 Required Bot Permissions:")
        print("   - Read Messages")
        print("   - Send Messages") 
        print("   - Add Reactions")
        print("   - Embed Links")
        print("   - Use External Emojis")
