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
                        
                        # DETAILED TIMEZONE DEBUG LOGGING
                        print(f"    🔍 TIMEZONE DEBUG - Poll {poll_id}:")
                        print(f"        📅 Original open_time: {fresh_poll.open_time} (type: {type(fresh_poll.open_time)})")
                        print(f"        📅 Original close_time: {fresh_poll.close_time} (type: {type(fresh_poll.close_time)})")
                        print(f"        🌍 Poll timezone field: '{fresh_poll.timezone}'")
                        print(f"        📊 Poll status: '{fresh_poll.status}'")
                        
                        # TIME CORRECTION: Fix 4:00:00 times to 00:00:00 for Eastern timezone polls
                        time_corrected = False
                        if fresh_poll.timezone in ['US/Eastern', 'America/New_York'] and fresh_poll.close_time:
                            if fresh_poll.close_time.hour == 4 and fresh_poll.close_time.minute == 0:
                                print(f"        🔧 CORRECTING TIME: Found 4:00:00 close time, changing to 00:00:00")
                                # Create new datetime with corrected hour
                                from datetime import datetime
                                corrected_close_time = fresh_poll.close_time.replace(hour=12)
                                
                                # Update the database with corrected time
                                from sqlalchemy import text
                                fresh_db.execute(
                                    text("UPDATE polls SET close_time = :new_time WHERE id = :poll_id"),
                                    {"new_time": corrected_close_time, "poll_id": poll_id}
                                )
                                fresh_db.commit()
                                
                                # Update the poll object
                                fresh_poll.close_time = corrected_close_time
                                time_corrected = True
                                print(f"        ✅ CORRECTED: {fresh_poll.close_time} (changed from 4:00:00 to 12:00:00)")
                            else:
                                print(f"        ℹ️ No time correction needed (close time is {fresh_poll.close_time.hour}:{fresh_poll.close_time.minute:02d})")
                        
                        # Also check open_time for correction
                        if fresh_poll.timezone in ['US/Eastern', 'America/New_York'] and fresh_poll.open_time:
                            if fresh_poll.open_time.hour == 12 and fresh_poll.open_time.minute == 0:
                                print(f"        🔧 CORRECTING TIME: Found 4:00:00 open time, changing to 12:00:00")
                                # Create new datetime with corrected hour
                                from datetime import datetime
                                corrected_open_time = fresh_poll.open_time.replace(hour=00)
                                
                                # Update the database with corrected time
                                from sqlalchemy import text
                                fresh_db.execute(
                                    text("UPDATE polls SET open_time = :new_time WHERE id = :poll_id"),
                                    {"new_time": corrected_open_time, "poll_id": poll_id}
                                )
                                fresh_db.commit()
                                
                                # Update the poll object
                                fresh_poll.open_time = corrected_open_time
                                time_corrected = True
                                print(f"        ✅ CORRECTED: {fresh_poll.open_time} (changed from 4:00:00 to 00:00:00)")
                        
                        if time_corrected:
                            print(f"        🎯 TIME CORRECTION APPLIED - Database updated with corrected times")
                        
                        # Test timezone validation
                        try:
                            from polly.utils import validate_and_normalize_timezone
                            if fresh_poll.timezone:
                                normalized_tz = validate_and_normalize_timezone(fresh_poll.timezone)
                                print(f"        ✅ Normalized timezone: '{normalized_tz}'")
                                
                                import pytz
                                tz = pytz.timezone(normalized_tz)
                                print(f"        ✅ Pytz timezone object: {tz}")
                                
                                # Test conversion of close_time to poll timezone
                                if fresh_poll.close_time:
                                    converted_time = fresh_poll.close_time.astimezone(tz)
                                    print(f"        🔄 Close time in poll timezone: {converted_time}")
                                    print(f"        🔄 Close time timezone info: {converted_time.tzinfo}")
                                else:
                                    print(f"        ⚠️ No close_time available")
                            else:
                                print(f"        ⚠️ No timezone field set, will use UTC")
                        except Exception as tz_error:
                            print(f"        ❌ Timezone validation error: {tz_error}")
                        
                        # Update the Discord message with the new cleaned-up embed format
                        # using the fresh poll object with active database session
                        print(f"    🔄 Calling update_poll_message...")
                        success = await update_poll_message(bot, fresh_poll)
                        
                        if success:
                            print(f"    ✅ Successfully updated embed (removed duplicates & clutter)")
                            print(f"        🌍 Final timezone used: {fresh_poll.timezone}")
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
