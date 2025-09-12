#!/usr/bin/env python3
"""
Fix Existing Closed Poll Script
This script will update the Discord message for existing closed polls that weren't properly updated.
"""

import asyncio
import sys
import os
from decouple import config

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from polly.database import get_db_session, Poll
from polly.discord_utils import update_poll_message
from sqlalchemy.orm import joinedload
import discord
from discord.ext import commands


async def fix_existing_closed_polls():
    """Fix Discord messages for existing closed polls"""
    print("🔧 FIXING EXISTING CLOSED POLLS")
    print("=" * 40)
    
    # Get Discord token
    DISCORD_TOKEN = config("DISCORD_TOKEN")
    if not DISCORD_TOKEN:
        print("❌ DISCORD_TOKEN environment variable is required")
        return 1
    
    # Set up bot with proper intents
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.reactions = True
    
    bot = commands.Bot(command_prefix=lambda bot, message: None, intents=intents)
    
    @bot.event
    async def on_ready():
        print(f"✅ Bot is ready: {bot.user}")
        
        # Get all closed polls that have message IDs
        db = get_db_session()
        try:
            closed_polls = (
                db.query(Poll)
                .options(joinedload(Poll.votes))
                .filter(Poll.status == 'closed')
                .filter(Poll.message_id.isnot(None))
                .all()
            )
            
            print(f"📊 Found {len(closed_polls)} closed polls with message IDs")
            
            if not closed_polls:
                print("✅ No closed polls found that need fixing")
                await bot.close()
                return
            
            for poll in closed_polls:
                poll_id = poll.id
                poll_name = poll.name
                message_id = poll.message_id
                
                print(f"\n🔄 Processing Poll {poll_id}: '{poll_name}' (Message: {message_id})")
                
                try:
                    # Update the Discord message to show final results
                    success = await update_poll_message(bot, poll)
                    
                    if success:
                        print(f"✅ Successfully updated Discord message for poll {poll_id}")
                    else:
                        print(f"❌ Failed to update Discord message for poll {poll_id}")
                        
                except Exception as e:
                    print(f"❌ Error updating poll {poll_id}: {e}")
                    continue
            
            print(f"\n🎉 Finished processing {len(closed_polls)} closed polls")
            
        except Exception as e:
            print(f"❌ Database error: {e}")
        finally:
            db.close()
            await bot.close()
    
    # Start the bot
    try:
        await bot.start(DISCORD_TOKEN)
    except Exception as e:
        print(f"❌ Error starting bot: {e}")
        return 1
    
    return 0


async def main():
    """Main function"""
    print("🚀 Starting fix for existing closed polls...")
    
    try:
        exit_code = await fix_existing_closed_polls()
        return exit_code
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    # Run the fix
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
