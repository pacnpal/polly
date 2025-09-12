#!/usr/bin/env python3
"""
Test Script for create_poll_results_embed Timezone Handling
This script tests the create_poll_results_embed function with various timezone scenarios
to ensure it properly handles timezone-naive and timezone-aware timestamps.
"""

import asyncio
import sys
import os
from datetime import datetime
import pytz

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from polly.database import get_db_session, Poll
from polly.discord_utils import create_poll_results_embed
from sqlalchemy.orm import joinedload


class MockPoll:
    """Mock Poll object for testing timezone scenarios"""
    
    def __init__(self, poll_id, name, question, options, emojis, close_time, timezone, anonymous=False, multiple_choice=False):
        self.id = poll_id
        self.name = name
        self.question = question
        self.options = options
        self.emojis = emojis
        self.close_time = close_time
        self.timezone = timezone
        self.anonymous = anonymous
        self.multiple_choice = multiple_choice
        self.status = "closed"
        
        # Mock results for testing
        self._mock_results = {0: 5, 1: 3, 2: 7}  # Option 0: 5 votes, Option 1: 3 votes, Option 2: 7 votes
        self._mock_total_votes = 15
    
    def get_results(self):
        """Mock results method"""
        return self._mock_results
    
    def get_total_votes(self):
        """Mock total votes method"""
        return self._mock_total_votes
    
    def get_winner(self):
        """Mock winner method - returns option 2 (index 2) as winner with 7 votes"""
        if self._mock_total_votes > 0:
            max_votes = max(self._mock_results.values())
            winners = [idx for idx, votes in self._mock_results.items() if votes == max_votes]
            return winners
        return []


async def test_timezone_scenarios():
    """Test create_poll_results_embed with various timezone scenarios"""
    print("🧪 TESTING create_poll_results_embed TIMEZONE HANDLING")
    print("=" * 60)
    print()
    
    # Test scenarios
    test_cases = [
        {
            "name": "Timezone-Naive Close Time (should localize to poll timezone)",
            "close_time": datetime(2025, 9, 12, 15, 30, 0),  # No timezone info
            "timezone": "America/New_York",
            "expected_behavior": "Should localize naive datetime to Eastern timezone"
        },
        {
            "name": "Timezone-Aware Close Time (Eastern)",
            "close_time": pytz.timezone('America/New_York').localize(datetime(2025, 9, 12, 15, 30, 0)),
            "timezone": "America/New_York",
            "expected_behavior": "Should use existing Eastern timezone"
        },
        {
            "name": "Timezone-Aware Close Time (UTC) with Eastern Poll Timezone",
            "close_time": pytz.UTC.localize(datetime(2025, 9, 12, 19, 30, 0)),  # 7:30 PM UTC = 3:30 PM Eastern
            "timezone": "America/New_York",
            "expected_behavior": "Should convert UTC to Eastern timezone"
        },
        {
            "name": "Timezone-Naive Close Time with UTC Poll Timezone",
            "close_time": datetime(2025, 9, 12, 15, 30, 0),  # No timezone info
            "timezone": "UTC",
            "expected_behavior": "Should localize naive datetime to UTC"
        },
        {
            "name": "Timezone-Aware Close Time (Pacific) with Eastern Poll Timezone",
            "close_time": pytz.timezone('America/Los_Angeles').localize(datetime(2025, 9, 12, 12, 30, 0)),  # 12:30 PM Pacific = 3:30 PM Eastern
            "timezone": "America/New_York",
            "expected_behavior": "Should convert Pacific to Eastern timezone"
        },
        {
            "name": "Invalid Timezone with Timezone-Naive Close Time",
            "close_time": datetime(2025, 9, 12, 15, 30, 0),  # No timezone info
            "timezone": "Invalid/Timezone",
            "expected_behavior": "Should fallback to UTC localization"
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"[{i}/{len(test_cases)}] 🧪 TEST: {test_case['name']}")
        print(f"    📅 Close Time: {test_case['close_time']} (tzinfo: {test_case['close_time'].tzinfo})")
        print(f"    🌍 Poll Timezone: '{test_case['timezone']}'")
        print(f"    🎯 Expected: {test_case['expected_behavior']}")
        print()
        
        try:
            # Create mock poll
            mock_poll = MockPoll(
                poll_id=i,
                name=f"Test Poll {i}",
                question=f"Test question for scenario {i}?",
                options=["Option A", "Option B", "Option C"],
                emojis=["🅰️", "🅱️", "🅲"],
                close_time=test_case['close_time'],
                timezone=test_case['timezone']
            )
            
            print(f"    🔄 Creating results embed...")
            
            # Test the function
            embed = await create_poll_results_embed(mock_poll)
            
            print(f"    ✅ Embed created successfully!")
            print(f"    📊 Embed Title: {embed.title}")
            print(f"    📅 Embed Timestamp: {embed.timestamp} (tzinfo: {embed.timestamp.tzinfo if embed.timestamp else None})")
            
            # Analyze the timestamp
            if embed.timestamp:
                if embed.timestamp.tzinfo is None:
                    print(f"    ⚠️ WARNING: Embed timestamp is timezone-naive!")
                else:
                    print(f"    ✅ Embed timestamp is timezone-aware: {embed.timestamp.tzinfo}")
                    
                    # Show the timestamp in different timezones for comparison
                    utc_time = embed.timestamp.astimezone(pytz.UTC)
                    eastern_time = embed.timestamp.astimezone(pytz.timezone('America/New_York'))
                    
                    print(f"    🌍 Timestamp in UTC: {utc_time}")
                    print(f"    🌍 Timestamp in Eastern: {eastern_time}")
            else:
                print(f"    ❌ No timestamp in embed!")
            
            # Check embed fields
            print(f"    📋 Embed has {len(embed.fields)} fields:")
            for field in embed.fields:
                print(f"        - {field.name}: {field.value[:50]}{'...' if len(field.value) > 50 else ''}")
            
        except Exception as e:
            print(f"    ❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
        
        print()
        print("-" * 60)
        print()
    
    print("🎉 TIMEZONE TESTING COMPLETE")
    print()
    
    # Additional test: Compare with real database poll
    print("🔍 TESTING WITH REAL DATABASE POLL")
    print("=" * 40)
    
    try:
        db = get_db_session()
        try:
            # Get a real closed poll from the database
            real_poll = (
                db.query(Poll)
                .options(joinedload(Poll.votes))
                .filter(Poll.status == 'closed')
                .first()
            )
            
            if real_poll:
                print(f"📊 Found real poll: {real_poll.name} (ID: {real_poll.id})")
                print(f"📅 Real poll close_time: {real_poll.close_time} (tzinfo: {real_poll.close_time.tzinfo if real_poll.close_time else None})")
                print(f"🌍 Real poll timezone: '{real_poll.timezone}'")
                print()
                
                print("🔄 Creating embed for real poll...")
                real_embed = await create_poll_results_embed(real_poll)
                
                print(f"✅ Real poll embed created successfully!")
                print(f"📅 Real embed timestamp: {real_embed.timestamp} (tzinfo: {real_embed.timestamp.tzinfo if real_embed.timestamp else None})")
                
                if real_embed.timestamp and real_embed.timestamp.tzinfo:
                    utc_time = real_embed.timestamp.astimezone(pytz.UTC)
                    eastern_time = real_embed.timestamp.astimezone(pytz.timezone('America/New_York'))
                    
                    print(f"🌍 Real timestamp in UTC: {utc_time}")
                    print(f"🌍 Real timestamp in Eastern: {eastern_time}")
                
            else:
                print("⚠️ No closed polls found in database for real testing")
                
        finally:
            db.close()
            
    except Exception as e:
        print(f"❌ Error testing with real database poll: {e}")
        import traceback
        traceback.print_exc()
    
    print()
    print("🏁 ALL TESTING COMPLETE")


async def main():
    """Main function"""
    print("🚀 Starting create_poll_results_embed timezone testing...")
    print()
    
    try:
        await test_timezone_scenarios()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    # Run the timezone tests
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
