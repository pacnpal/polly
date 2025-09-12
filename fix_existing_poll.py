#!/usr/bin/env python3
"""
Fix Existing Closed Poll Script
This script will update the Discord message for existing closed polls that weren't properly updated.
"""

import asyncio
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from polly.database import get_db_session, Poll
from polly.discord_bot import get_bot_instance
from polly.discord_utils import update_poll_message
from sqlalchemy.orm import joinedload


async def fix_existing_closed_polls():
    """Fix Discord messages for existing closed polls"""
    print("🔧 FIXING EXISTING CLOSED POLLS")
    print("=" * 40)
    
    # Get bot instance
    from polly.discord_bot import bot
    if not bot:
        print("❌ Bot instance not available")
        return
    
    if not bot.is_ready():
        print("❌ Bot is not ready")
        return
    
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


async def main():
    """Main function"""
    print("🚀 Starting fix for existing closed polls...")
    
    # Import and start the bot if needed
    try:
        from polly.discord_bot import bot
        
        # Check if bot is already running
        if not bot.is_ready():
            print("⏳ Waiting for bot to be ready...")
            await bot.wait_until_ready()
        
        await fix_existing_closed_polls()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    # Run the fix
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
