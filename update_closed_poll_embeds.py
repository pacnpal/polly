#!/usr/bin/env python3
"""
Update Closed Poll Embeds Script
This script will update Discord messages for all existing closed polls to use the new cleaned-up embed format.
It removes duplicates and unnecessary information to make closed poll embeds less busy and more readable.
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


async def update_closed_poll_embeds():
    """Update Discord messages for all existing closed polls with cleaned-up embed format"""
    print("🧹 UPDATING CLOSED POLL EMBEDS")
    print("=" * 40)
    print("This script will update all existing closed poll Discord messages")
    print("to use the new cleaned-up embed format that removes duplicates")
    print("and unnecessary information.")
    print()
    
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
        print()
        
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
            
            print(f"📊 Found {len(closed_polls)} closed polls with Discord messages")
            
            if not closed_polls:
                print("✅ No closed polls found that need updating")
                await bot.close()
                return
            
            print(f"🔄 Starting to update {len(closed_polls)} closed poll embeds...")
            print()
            
            updated_count = 0
            failed_count = 0
            
            for i, poll in enumerate(closed_polls, 1):
                poll_id = poll.id
                poll_name = poll.name[:50] + "..." if len(poll.name) > 50 else poll.name
                message_id = poll.message_id
                server_name = poll.server_name or "Unknown Server"
                channel_name = poll.channel_name or "Unknown Channel"
                poll_timezone = poll.timezone or "UTC"
                
                print(f"[{i}/{len(closed_polls)}] 🔄 Poll {poll_id}: '{poll_name}'")
                print(f"    📍 {server_name} → #{channel_name}")
                print(f"    💬 Message ID: {message_id}")
                print(f"    🌍 Timezone: {poll_timezone}")
                
                try:
                    # Refresh poll from database to ensure all fields are properly loaded
                    # and the poll object is attached to an active database session
                    fresh_db = get_db_session()
                    try:
                        fresh_poll = (
                            fresh_db.query(Poll)
                            .options(joinedload(Poll.votes))
                            .filter(Poll.id == poll_id)
                            .first()
                        )
                        
                        if not fresh_poll:
                            print(f"    ❌ Poll {poll_id} not found in database refresh")
                            failed_count += 1
                            continue
                        
                        # Update the Discord message with the new cleaned-up embed format
                        # using the fresh poll object with active database session
                        success = await update_poll_message(bot, fresh_poll)
                        
                        if success:
                            print(f"    ✅ Successfully updated embed (removed duplicates & clutter, timezone: {fresh_poll.timezone})")
                            updated_count += 1
                        else:
                            print(f"    ❌ Failed to update embed (message may not exist)")
                            failed_count += 1
                            
                    finally:
                        fresh_db.close()
                        
                except Exception as e:
                    print(f"    ❌ Error updating poll: {e}")
                    failed_count += 1
                    continue
                
                print()  # Add spacing between polls
            
            print("=" * 60)
            print(f"🎉 EMBED UPDATE COMPLETE")
            print(f"✅ Successfully updated: {updated_count} polls")
            if failed_count > 0:
                print(f"❌ Failed to update: {failed_count} polls")
            print(f"📊 Total processed: {len(closed_polls)} polls")
            print()
            print("🧹 All closed poll embeds have been cleaned up!")
            print("   - Removed duplicate 'Total Votes' sections")
            print("   - Removed voting instructions for closed polls")
            print("   - Removed outdated anonymous poll messages")
            print("   - Removed close time information for closed polls")
            print("   - Kept essential results, winner, and poll type info")
            
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
    print("🚀 Starting closed poll embed cleanup...")
    print()
    
    try:
        exit_code = await update_closed_poll_embeds()
        return exit_code
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    # Run the embed update
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
