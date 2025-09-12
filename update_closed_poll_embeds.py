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
                        
                        # FORCE EASTERN TIMEZONE FOR ALL POLLS
                        print(f"    🔍 TIMEZONE DEBUG - Poll {poll_id}:")
                        print(f"        📅 Original open_time: {fresh_poll.open_time} (type: {type(fresh_poll.open_time)})")
                        print(f"        📅 Original close_time: {fresh_poll.close_time} (type: {type(fresh_poll.close_time)})")
                        print(f"        🌍 Original timezone field: '{fresh_poll.timezone}'")
                        print(f"        📊 Poll status: '{fresh_poll.status}'")
                        
                        # FORCE ALL POLLS TO USE EASTERN TIMEZONE
                        import pytz
                        from datetime import datetime
                        from sqlalchemy import text
                        
                        eastern_tz = pytz.timezone('America/New_York')
                        updates_made = False
                        
                        # Force timezone to Eastern
                        if fresh_poll.timezone != 'America/New_York':
                            print(f"        🔧 FORCING TIMEZONE: Changing from '{fresh_poll.timezone}' to 'America/New_York'")
                            fresh_db.execute(
                                text("UPDATE polls SET timezone = :new_timezone WHERE id = :poll_id"),
                                {"new_timezone": "America/New_York", "poll_id": poll_id}
                            )
                            fresh_poll.timezone = "America/New_York"
                            updates_made = True
                        
                        # Fix timezone-naive timestamps by making them timezone-aware in Eastern
                        if fresh_poll.open_time and fresh_poll.open_time.tzinfo is None:
                            print(f"        🔧 FIXING TIMEZONE-NAIVE open_time: {fresh_poll.open_time}")
                            # Assume the naive datetime is already in Eastern time and make it timezone-aware
                            aware_open_time = eastern_tz.localize(fresh_poll.open_time)
                            fresh_db.execute(
                                text("UPDATE polls SET open_time = :new_time WHERE id = :poll_id"),
                                {"new_time": aware_open_time, "poll_id": poll_id}
                            )
                            fresh_poll.open_time = aware_open_time
                            updates_made = True
                            print(f"        ✅ FIXED open_time: {fresh_poll.open_time} (now timezone-aware in Eastern)")
                        
                        if fresh_poll.close_time and fresh_poll.close_time.tzinfo is None:
                            print(f"        🔧 FIXING TIMEZONE-NAIVE close_time: {fresh_poll.close_time}")
                            # Assume the naive datetime is already in Eastern time and make it timezone-aware
                            aware_close_time = eastern_tz.localize(fresh_poll.close_time)
                            fresh_db.execute(
                                text("UPDATE polls SET close_time = :new_time WHERE id = :poll_id"),
                                {"new_time": aware_close_time, "poll_id": poll_id}
                            )
                            fresh_poll.close_time = aware_close_time
                            updates_made = True
                            print(f"        ✅ FIXED close_time: {fresh_poll.close_time} (now timezone-aware in Eastern)")
                        
                        # If timestamps are already timezone-aware but not in Eastern, convert them
                        if fresh_poll.open_time and fresh_poll.open_time.tzinfo is not None:
                            if fresh_poll.open_time.tzinfo != eastern_tz:
                                print(f"        🔧 CONVERTING open_time to Eastern: {fresh_poll.open_time}")
                                # Convert to Eastern time
                                eastern_open_time = fresh_poll.open_time.astimezone(eastern_tz)
                                fresh_db.execute(
                                    text("UPDATE polls SET open_time = :new_time WHERE id = :poll_id"),
                                    {"new_time": eastern_open_time, "poll_id": poll_id}
                                )
                                fresh_poll.open_time = eastern_open_time
                                updates_made = True
                                print(f"        ✅ CONVERTED open_time: {fresh_poll.open_time} (now in Eastern)")
                        
                        if fresh_poll.close_time and fresh_poll.close_time.tzinfo is not None:
                            if fresh_poll.close_time.tzinfo != eastern_tz:
                                print(f"        🔧 CONVERTING close_time to Eastern: {fresh_poll.close_time}")
                                # Convert to Eastern time
                                eastern_close_time = fresh_poll.close_time.astimezone(eastern_tz)
                                fresh_db.execute(
                                    text("UPDATE polls SET close_time = :new_time WHERE id = :poll_id"),
                                    {"new_time": eastern_close_time, "poll_id": poll_id}
                                )
                                fresh_poll.close_time = eastern_close_time
                                updates_made = True
                                print(f"        ✅ CONVERTED close_time: {fresh_poll.close_time} (now in Eastern)")
                        
                        if updates_made:
                            fresh_db.commit()
                            print(f"        🎯 EASTERN TIMEZONE ENFORCEMENT COMPLETE - Database updated")
                            
                            # CRITICAL: Refresh the poll object after database updates to ensure
                            # it has the updated timezone-aware timestamps
                            print(f"        🔄 REFRESHING poll object after timezone updates...")
                            fresh_poll = (
                                fresh_db.query(Poll)
                                .options(joinedload(Poll.votes))
                                .filter(Poll.id == poll_id)
                                .first()
                            )
                            if fresh_poll:
                                print(f"        ✅ Poll object refreshed with updated timestamps")
                                print(f"        📅 Refreshed open_time: {fresh_poll.open_time} (tzinfo: {fresh_poll.open_time.tzinfo if fresh_poll.open_time else None})")
                                print(f"        📅 Refreshed close_time: {fresh_poll.close_time} (tzinfo: {fresh_poll.close_time.tzinfo if fresh_poll.close_time else None})")
                            else:
                                print(f"        ❌ Failed to refresh poll object after timezone updates")
                        else:
                            print(f"        ✅ Poll already has proper Eastern timezone configuration")
                        
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
            print("   - FORCED all polls to use Eastern timezone (America/New_York)")
            print("   - FIXED all timezone-naive timestamps to be timezone-aware")
            print("   - CONVERTED all timestamps to Eastern timezone")
            
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
