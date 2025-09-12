#!/usr/bin/env python3
"""
Simple Poll Fix Script
This script connects to the existing running bot to fix closed polls.
Run this while the main Polly application is running.
"""

import asyncio
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def fix_closed_poll_by_id(poll_id: int):
    """Fix a specific closed poll by ID"""
    from polly.database import get_db_session, Poll
    from polly.discord_utils import update_poll_message
    from polly.discord_bot import get_bot_instance
    from sqlalchemy.orm import joinedload
    
    print(f"🔧 Fixing poll {poll_id}...")
    
    # Get bot instance from the running application
    bot = get_bot_instance()
    if not bot:
        print("❌ Bot instance not available - make sure Polly is running")
        return False
    
    if not bot.is_ready():
        print("❌ Bot is not ready - make sure Polly is fully started")
        return False
    
    print(f"✅ Bot is ready: {bot.user}")
    
    # Get the specific poll
    db = get_db_session()
    try:
        poll = (
            db.query(Poll)
            .options(joinedload(Poll.votes))
            .filter(Poll.id == poll_id)
            .first()
        )
        
        if not poll:
            print(f"❌ Poll {poll_id} not found")
            return False
        
        if poll.status != 'closed':
            print(f"❌ Poll {poll_id} is not closed (status: {poll.status})")
            return False
        
        if not poll.message_id:
            print(f"❌ Poll {poll_id} has no Discord message ID")
            return False
        
        print(f"📊 Found poll: '{poll.name}' (Message: {poll.message_id})")
        
        # Update the Discord message to show final results
        success = await update_poll_message(bot, poll)
        
        if success:
            print(f"✅ Successfully updated Discord message for poll {poll_id}")
            return True
        else:
            print(f"❌ Failed to update Discord message for poll {poll_id}")
            return False
            
    except Exception as e:
        print(f"❌ Error updating poll {poll_id}: {e}")
        return False
    finally:
        db.close()


async def fix_all_closed_polls():
    """Fix all closed polls that have message IDs"""
    from polly.database import get_db_session, Poll
    from polly.discord_utils import update_poll_message
    from polly.discord_bot import get_bot_instance
    from sqlalchemy.orm import joinedload
    
    print("🔧 Fixing all closed polls...")
    
    # Get bot instance from the running application
    bot = get_bot_instance()
    if not bot:
        print("❌ Bot instance not available - make sure Polly is running")
        return False
    
    if not bot.is_ready():
        print("❌ Bot is not ready - make sure Polly is fully started")
        return False
    
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
            return True
        
        success_count = 0
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
                    success_count += 1
                else:
                    print(f"❌ Failed to update Discord message for poll {poll_id}")
                    
            except Exception as e:
                print(f"❌ Error updating poll {poll_id}: {e}")
                continue
        
        print(f"\n🎉 Finished processing {len(closed_polls)} closed polls")
        print(f"✅ Successfully updated {success_count}/{len(closed_polls)} polls")
        return success_count > 0
        
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False
    finally:
        db.close()


async def main():
    """Main function"""
    if len(sys.argv) > 1:
        try:
            poll_id = int(sys.argv[1])
            print(f"🚀 Fixing specific poll {poll_id}...")
            success = await fix_closed_poll_by_id(poll_id)
            return 0 if success else 1
        except ValueError:
            print("❌ Invalid poll ID. Please provide a valid integer.")
            return 1
    else:
        print("🚀 Fixing all closed polls...")
        success = await fix_all_closed_polls()
        return 0 if success else 1


if __name__ == "__main__":
    print("Simple Poll Fix Script")
    print("Usage:")
    print("  python fix_poll_simple.py        # Fix all closed polls")
    print("  python fix_poll_simple.py <id>   # Fix specific poll by ID")
    print()
    
    # Run the fix
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
