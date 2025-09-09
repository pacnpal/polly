#!/usr/bin/env python3
"""
Debug script to test role ping functionality
"""

import asyncio
import logging
from polly.database import get_db_session, Poll
from polly.discord_utils import post_poll_to_channel

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def debug_role_ping():
    """Debug role ping functionality by checking a specific poll"""
    
    # Get the most recent poll with role ping enabled
    db = get_db_session()
    try:
        poll = db.query(Poll).filter(
            Poll.ping_role_enabled.is_(True),
            Poll.ping_role_id.isnot(None)
        ).order_by(Poll.created_at.desc()).first()
        
        if not poll:
            print("❌ No polls found with role ping enabled")
            return
            
        print(f"🔍 Found poll {poll.id} with role ping enabled")
        print(f"🔍 Poll name: {poll.name}")
        print(f"🔍 ping_role_enabled: {poll.ping_role_enabled}")
        print(f"🔍 ping_role_id: {poll.ping_role_id}")
        print(f"🔍 ping_role_name: {getattr(poll, 'ping_role_name', 'NOT_SET')}")
        print(f"🔍 server_id: {poll.server_id}")
        print(f"🔍 channel_id: {poll.channel_id}")
        print(f"🔍 status: {poll.status}")
        
        # Check if the role ping data is properly set
        if poll.ping_role_enabled and poll.ping_role_id:
            role_id = str(poll.ping_role_id)
            role_name = str(getattr(poll, 'ping_role_name', 'Unknown Role'))
            expected_message = f"<@&{role_id}> 📊 **Poll '{poll.name}' is now open!**"
            
            print(f"✅ Role ping should work!")
            print(f"✅ Expected message content: {expected_message}")
            print(f"✅ Role ID: {role_id}")
            print(f"✅ Role Name: {role_name}")
        else:
            print(f"❌ Role ping data incomplete:")
            print(f"   - ping_role_enabled: {poll.ping_role_enabled}")
            print(f"   - ping_role_id: {poll.ping_role_id}")
            
    except Exception as e:
        print(f"❌ Error during debug: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(debug_role_ping())
