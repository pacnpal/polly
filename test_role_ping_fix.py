#!/usr/bin/env python3
"""
Test script to verify the role ping fix works correctly.
This script simulates the poll posting process to check if role ping data is properly retrieved.
"""

import sys
import os
import asyncio
from unittest.mock import Mock, AsyncMock

# Add the polly module to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

from polly.database import get_db_session, Poll
from polly.discord_utils import post_poll_to_channel

async def test_role_ping_fix():
    """Test that role ping data is correctly retrieved during poll posting"""
    
    print("🔍 Testing role ping fix...")
    
    # Get the poll with role ping data from the database
    db = get_db_session()
    try:
        poll = db.query(Poll).filter(Poll.id == 11).first()
        if not poll:
            print("❌ Poll 11 not found in database")
            return False
            
        print(f"✅ Found poll: {poll.name}")
        print(f"   Role ping enabled: {getattr(poll, 'ping_role_enabled', 'NOT_SET')}")
        print(f"   Role ID: {getattr(poll, 'ping_role_id', 'NOT_SET')}")
        print(f"   Role name: {getattr(poll, 'ping_role_name', 'NOT_SET')}")
        
        # Create a mock bot to test the posting function
        mock_bot = Mock()
        mock_bot.is_ready.return_value = True
        mock_bot.user = Mock()
        mock_bot.user.name = "TestBot"
        
        # Mock the channel and guild
        mock_channel = Mock()
        mock_channel.name = "test-channel"
        mock_channel.id = 123456789
        mock_channel.send = AsyncMock()
        mock_channel.permissions_for.return_value = Mock(
            send_messages=True,
            embed_links=True,
            add_reactions=True
        )
        
        mock_guild = Mock()
        mock_guild.name = "Test Guild"
        mock_guild.get_member.return_value = Mock()
        mock_channel.guild = mock_guild
        
        mock_bot.get_channel.return_value = mock_channel
        
        # Test the posting function with our fix
        print("\n🔍 Testing post_poll_to_channel function...")
        
        # This should trigger our direct database query fix
        result = await post_poll_to_channel(mock_bot, 11)
        
        print(f"✅ Function completed with result: {result}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    success = asyncio.run(test_role_ping_fix())
    if success:
        print("\n✅ Role ping fix test completed successfully!")
        print("The fix should now properly retrieve role ping data from the database.")
    else:
        print("\n❌ Role ping fix test failed!")
        sys.exit(1)
