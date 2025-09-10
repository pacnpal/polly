#!/usr/bin/env python3
"""
Test script to create a poll with role ping functionality and verify the fix works.
This script calculates valid opening and closing times relative to the current time.
"""

import sys
import os
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    import pytz
    from polly.validators import PollValidator
    from polly.poll_operations import BulletproofPollOperations
    from polly.database import get_db_session, Poll
    print("✅ Successfully imported required modules")
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Please ensure you're running this from the project directory with the virtual environment activated")
    sys.exit(1)


class MockBot:
    """Mock bot class for testing purposes"""
    def __init__(self):
        self.user = MockUser()
    
    def get_channel(self, channel_id):
        return MockChannel(channel_id)
    
    def get_guild(self, guild_id):
        return MockGuild(guild_id)


class MockUser:
    """Mock Discord user"""
    def __init__(self):
        self.id = 734980795957248010
        self.name = "TestBot"


class MockChannel:
    """Mock Discord channel"""
    def __init__(self, channel_id):
        self.id = channel_id
        self.name = "testing"
        self.guild = MockGuild(1067616268385009736)
    
    def permissions_for(self, member):
        return MockPermissions()


class MockGuild:
    """Mock Discord guild"""
    def __init__(self, guild_id):
        self.id = guild_id
        self.name = "Test Server"
        self.me = MockUser()
    
    def get_role(self, role_id):
        return MockRole(role_id)


class MockRole:
    """Mock Discord role"""
    def __init__(self, role_id):
        self.id = role_id
        self.name = "Test Role"


class MockPermissions:
    """Mock Discord permissions"""
    def __init__(self):
        self.send_messages = True
        self.embed_links = True
        self.add_reactions = True
        self.attach_files = True


def calculate_valid_times():
    """Calculate valid opening and closing times for the poll"""
    now = datetime.now(pytz.UTC)
    
    # Open time: 2 minutes from now (ensures it's in the future)
    open_time = now + timedelta(minutes=2)
    
    # Close time: 1 hour after open time
    close_time = open_time + timedelta(hours=1)
    
    return open_time, close_time


def test_role_ping_validation():
    """Test that role ping data is properly validated"""
    print("\n🔍 Testing Role Ping Validation")
    print("-" * 40)
    
    open_time, close_time = calculate_valid_times()
    
    # Test data with role ping enabled
    poll_data = {
        "name": "Test Poll with Role Ping",
        "question": "Should we test role ping functionality?",
        "options": ["Yes", "No", "Maybe"],
        "emojis": ["🇦", "🇧", "🇨"],
        "server_id": "1067616268385009736",
        "channel_id": "1102998270961258616",
        "timezone": "US/Eastern",
        "open_time": open_time,
        "close_time": close_time,
        "anonymous": False,
        "multiple_choice": False,
        "creator_id": "141517468408610816",
        "ping_role_enabled": True,
        "ping_role_id": "1412236527315976272",
        "ping_role_name": "Shockwave"
    }
    
    print(f"📅 Open time: {open_time}")
    print(f"📅 Close time: {close_time}")
    print(f"🔔 Role ping enabled: {poll_data['ping_role_enabled']}")
    print(f"🔔 Role ID: {poll_data['ping_role_id']}")
    print(f"🔔 Role name: {poll_data['ping_role_name']}")
    
    try:
        validated_data = PollValidator.validate_poll_data(poll_data)
        
        print("\n✅ Validation successful!")
        print(f"✅ ping_role_enabled: {validated_data.get('ping_role_enabled')}")
        print(f"✅ ping_role_id: {validated_data.get('ping_role_id')}")
        print(f"✅ ping_role_name: {validated_data.get('ping_role_name')}")
        
        # Verify role ping data is preserved
        assert validated_data.get('ping_role_enabled') == True, "ping_role_enabled should be True"
        assert validated_data.get('ping_role_id') == "1412236527315976272", "ping_role_id should be preserved"
        assert validated_data.get('ping_role_name') == "Shockwave", "ping_role_name should be preserved"
        
        print("✅ All role ping data correctly validated and preserved!")
        return True, validated_data
        
    except Exception as e:
        print(f"❌ Validation failed: {e}")
        import traceback
        traceback.print_exc()
        return False, None


async def test_poll_creation_with_role_ping():
    """Test creating a poll with role ping using BulletproofPollOperations"""
    print("\n🔍 Testing Poll Creation with Role Ping")
    print("-" * 40)
    
    # First validate the data
    validation_success, validated_data = test_role_ping_validation()
    if not validation_success:
        return False
    
    # Create mock bot
    mock_bot = MockBot()
    
    # Create BulletproofPollOperations instance
    poll_ops = BulletproofPollOperations(mock_bot)
    
    try:
        print("\n🔄 Creating poll with BulletproofPollOperations...")
        
        result = await poll_ops.create_bulletproof_poll(
            poll_data=validated_data,
            user_id="141517468408610816"
        )
        
        if result["success"]:
            poll_id = result["poll_id"]
            print(f"✅ Poll created successfully! Poll ID: {poll_id}")
            
            # Verify the poll was saved with role ping data
            db = get_db_session()
            try:
                poll = db.query(Poll).filter(Poll.id == poll_id).first()
                if poll:
                    print(f"✅ Poll found in database: {poll.name}")
                    print(f"✅ ping_role_enabled: {poll.ping_role_enabled}")
                    print(f"✅ ping_role_id: {poll.ping_role_id}")
                    print(f"✅ ping_role_name: {poll.ping_role_name}")
                    
                    # Verify role ping data was saved correctly
                    if poll.ping_role_enabled and poll.ping_role_id == "1412236527315976272" and poll.ping_role_name == "Shockwave":
                        print("🎉 SUCCESS: Role ping data was correctly saved to database!")
                        return True
                    else:
                        print("❌ FAILURE: Role ping data was not saved correctly")
                        print(f"   Expected: enabled=True, id='1412236527315976272', name='Shockwave'")
                        print(f"   Actual: enabled={poll.ping_role_enabled}, id={poll.ping_role_id}, name={poll.ping_role_name}")
                        return False
                else:
                    print("❌ Poll not found in database")
                    return False
            finally:
                db.close()
        else:
            print(f"❌ Poll creation failed: {result['error']}")
            return False
            
    except Exception as e:
        print(f"❌ Poll creation error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_role_ping_disabled():
    """Test that role ping data is properly handled when disabled"""
    print("\n🔍 Testing Role Ping Disabled")
    print("-" * 40)
    
    open_time, close_time = calculate_valid_times()
    
    # Test data with role ping disabled
    poll_data = {
        "name": "Test Poll without Role Ping",
        "question": "Should we test without role ping?",
        "options": ["Yes", "No"],
        "emojis": ["🇦", "🇧"],
        "server_id": "1067616268385009736",
        "channel_id": "1102998270961258616",
        "timezone": "US/Eastern",
        "open_time": open_time,
        "close_time": close_time,
        "anonymous": False,
        "multiple_choice": False,
        "creator_id": "141517468408610816",
        "ping_role_enabled": False,
        "ping_role_id": "",
        "ping_role_name": ""
    }
    
    print(f"🔔 Role ping enabled: {poll_data['ping_role_enabled']}")
    
    try:
        validated_data = PollValidator.validate_poll_data(poll_data)
        
        print("✅ Validation successful!")
        print(f"✅ ping_role_enabled: {validated_data.get('ping_role_enabled')}")
        print(f"✅ ping_role_id: {validated_data.get('ping_role_id')}")
        print(f"✅ ping_role_name: {validated_data.get('ping_role_name')}")
        
        # Check if role ping data is properly set to None/False
        assert validated_data.get('ping_role_enabled') == False, "ping_role_enabled should be False"
        assert validated_data.get('ping_role_id') is None, "ping_role_id should be None when disabled"
        assert validated_data.get('ping_role_name') is None, "ping_role_name should be None when disabled"
        
        print("✅ Role ping disabled case handled correctly!")
        return True
        
    except Exception as e:
        print(f"❌ Validation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main test function"""
    print("🧪 Testing Role Ping Fix with Poll Creation")
    print("=" * 60)
    
    # Test 1: Role ping validation (enabled)
    test1_passed = test_role_ping_validation()[0]
    
    # Test 2: Role ping validation (disabled)
    test2_passed = test_role_ping_disabled()
    
    # Test 3: Full poll creation with role ping
    test3_passed = await test_poll_creation_with_role_ping()
    
    print("\n" + "=" * 60)
    print("📊 TEST RESULTS")
    print("=" * 60)
    print(f"✅ Role ping validation (enabled): {'PASS' if test1_passed else 'FAIL'}")
    print(f"✅ Role ping validation (disabled): {'PASS' if test2_passed else 'FAIL'}")
    print(f"✅ Full poll creation with role ping: {'PASS' if test3_passed else 'FAIL'}")
    
    if test1_passed and test2_passed and test3_passed:
        print("\n🎉 ALL TESTS PASSED!")
