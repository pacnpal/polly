#!/usr/bin/env python3
"""
Poll Creation Scenarios Test Script
Tests specific poll creation scenarios and edge cases.

This script focuses on testing specific scenarios that might cause issues:
- Boundary conditions
- Error conditions
- Recovery scenarios
- Performance scenarios
- Integration scenarios

Usage:
    python tests/poll_creation_scenarios.py [--scenario SCENARIO_NAME]
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import pytz
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from polly.database import get_db_session, Poll, Vote, init_database
from polly.discord_bot import get_bot_instance
from polly.poll_operations import BulletproofPollOperations
from polly.error_handler import PollErrorHandler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PollCreationScenarios:
    """Test specific poll creation scenarios and edge cases"""
    
    def __init__(self):
        self.test_user_id = "123456789012345678"
        self.test_server_id = "987654321098765432"
        self.test_channel_id = "111222333444555666"
        self.test_role_id = "777888999000111222"
        
        self.scenarios = {
            "boundary_conditions": self.test_boundary_conditions,
            "error_conditions": self.test_error_conditions,
            "unicode_stress": self.test_unicode_stress,
            "timing_edge_cases": self.test_timing_edge_cases,
            "emoji_combinations": self.test_emoji_combinations,
            "large_content": self.test_large_content,
            "concurrent_creation": self.test_concurrent_creation,
            "malformed_data": self.test_malformed_data,
            "database_stress": self.test_database_stress,
            "all_scenarios": self.run_all_scenarios
        }
    
    async def test_boundary_conditions(self):
        """Test boundary conditions for poll creation"""
        logger.info("🔍 Testing boundary conditions...")
        
        scenarios = [
            # Minimum values
            {
                "name": "Min",
                "question": "Test?",
                "options": ["A", "B"],
                "description": "Minimum length values"
            },
            
            # Maximum values
            {
                "name": "A" * 255,  # Maximum name length
                "question": "Q" * 2000,  # Maximum question length
                "options": [f"Option {i}" * 20 for i in range(10)],  # Maximum options
                "description": "Maximum length values"
            },
            
            # Edge case: exactly at limits
            {
                "name": "X" * 254,  # Just under limit
                "question": "Y" * 1999,  # Just under limit
                "options": ["Option A", "Option B"],
                "description": "Just under limits"
            },
            
            # Edge case: special characters at boundaries
            {
                "name": "Test Poll 🎉",
                "question": "What do you think? 🤔",
                "options": ["Yes ✅", "No ❌", "Maybe 🤷"],
                "description": "Unicode at boundaries"
            }
        ]
        
        for i, scenario in enumerate(scenarios):
            try:
                poll_data = {
                    "name": scenario["name"],
                    "question": scenario["question"],
                    "options": scenario["options"],
                    "emojis": ["🇦", "🇧", "🇨"][:len(scenario["options"])],
                    "server_id": self.test_server_id,
                    "channel_id": self.test_channel_id,
                    "open_time": datetime.now(pytz.UTC) + timedelta(minutes=1),
                    "close_time": datetime.now(pytz.UTC) + timedelta(hours=1),
                    "timezone": "UTC",
                    "anonymous": False,
                    "multiple_choice": False,
                    "ping_role_enabled": False,
                    "ping_role_id": None,
                    "creator_id": self.test_user_id
                }
                
                bot = get_bot_instance()
                bulletproof_ops = BulletproofPollOperations(bot)
                
                result = await bulletproof_ops.create_bulletproof_poll(
                    poll_data=poll_data,
                    user_id=self.test_user_id
                )
                
                if result["success"]:
                    logger.info(f"✅ Boundary test {i+1} passed: {scenario['description']}")
                else:
                    logger.warning(f"⚠️ Boundary test {i+1} failed: {result.get('error', 'Unknown error')}")
                    
            except Exception as e:
                logger.error(f"❌ Boundary test {i+1} exception: {e}")
    
    async def test_error_conditions(self):
        """Test error conditions and recovery"""
        logger.info("🔍 Testing error conditions...")
        
        error_scenarios = [
            # Invalid data types
            {
                "name": None,
                "question": "Test?",
                "options": ["A", "B"],
                "description": "None name"
            },
            
            # Empty values
            {
                "name": "",
                "question": "Test?",
                "options": ["A", "B"],
                "description": "Empty name"
            },
            
            # Invalid options
            {
                "name": "Test",
                "question": "Test?",
                "options": [],
                "description": "No options"
            },
            
            # Single option
            {
                "name": "Test",
                "question": "Test?",
                "options": ["Only One"],
                "description": "Single option"
            },
            
            # Too many options
            {
                "name": "Test",
                "question": "Test?",
                "options": [f"Option {i}" for i in range(15)],
                "description": "Too many options"
            },
            
            # Invalid times
            {
                "name": "Test",
                "question": "Test?",
                "options": ["A", "B"],
                "open_time": datetime.now(pytz.UTC) - timedelta(hours=1),  # Past time
                "description": "Past open time"
            },
            
            # Close before open
            {
                "name": "Test",
                "question": "Test?",
                "options": ["A", "B"],
                "open_time": datetime.now(pytz.UTC) + timedelta(hours=2),
                "close_time": datetime.now(pytz.UTC) + timedelta(hours=1),
                "description": "Close before open"
            }
        ]
        
        for i, scenario in enumerate(error_scenarios):
            try:
                poll_data = {
                    "name": scenario.get("name", "Test"),
                    "question": scenario.get("question", "Test?"),
                    "options": scenario.get("options", ["A", "B"]),
                    "emojis": ["🇦", "🇧"],
                    "server_id": self.test_server_id,
                    "channel_id": self.test_channel_id,
                    "open_time": scenario.get("open_time", datetime.now(pytz.UTC) + timedelta(minutes=1)),
                    "close_time": scenario.get("close_time", datetime.now(pytz.UTC) + timedelta(hours=1)),
                    "timezone": "UTC",
                    "anonymous": False,
                    "multiple_choice": False,
                    "ping_role_enabled": False,
                    "ping_role_id": None,
                    "creator_id": self.test_user_id
                }
                
                bot = get_bot_instance()
                bulletproof_ops = BulletproofPollOperations(bot)
                
                result = await bulletproof_ops.create_bulletproof_poll(
                    poll_data=poll_data,
                    user_id=self.test_user_id
                )
                
                if result["success"]:
                    logger.warning(f"⚠️ Error test {i+1} unexpectedly succeeded: {scenario['description']}")
                else:
                    logger.info(f"✅ Error test {i+1} correctly failed: {scenario['description']} - {result.get('error', 'Unknown error')}")
                    
            except Exception as e:
                logger.info(f"✅ Error test {i+1} correctly threw exception: {scenario['description']} - {e}")
    
    async def test_unicode_stress(self):
        """Test Unicode and special character handling"""
        logger.info("🔍 Testing Unicode stress scenarios...")
        
        unicode_scenarios = [
            {
                "name": "Emoji Test 🎉🎊🎈🎁🎂",
                "question": "Which emoji do you like? 😀😃😄😁😆😅😂🤣😊😇",
                "options": ["😀 Happy", "😢 Sad", "😡 Angry", "😴 Sleepy"],
                "description": "Heavy emoji usage"
            },
            
            {
                "name": "Multilingual Test",
                "question": "多言語テスト - Тест на многих языках - اختبار متعدد اللغات",
                "options": ["日本語", "Русский", "العربية", "English"],
                "description": "Multiple languages"
            },
            
            {
                "name": "Special Chars ™®©℠℡№℮",
                "question": "Testing symbols: ∀∂∃∄∅∆∇∈∉∊∋∌∍∎∏∐∑−∓∔∕∖∗∘∙√∛∜∝∞∟∠∡∢∣∤∥∦∧∨∩∪∫∬∭∮∯∰∱∲∳∴∵∶∷∸∹∺∻∼∽∾∿≀≁≂≃≄≅≆≇≈≉≊≋≌≍≎≏≐≑≒≓≔≕≖≗≘≙≚≛≜≝≞≟≠≡≢≣≤≥≦≧≨≩≪≫≬≭≮≯≰≱≲≳≴≵≶≷≸≹≺≻≼≽≾≿⊀⊁⊂⊃⊄⊅⊆⊇⊈⊉⊊⊋⊌⊍⊎⊏⊐⊑⊒⊓⊔⊕⊖⊗⊘⊙⊚⊛⊜⊝⊞⊟⊠⊡⊢⊣⊤⊥⊦⊧⊨⊩⊪⊫⊬⊭⊮⊯⊰⊱⊲⊳⊴⊵⊶⊷⊸⊹⊺⊻⊼⊽⊾⊿⋀⋁⋂⋃⋄⋅⋆⋇⋈⋉⋊⋋⋌⋍⋎⋏⋐⋑⋒⋓⋔⋕⋖⋗⋘⋙⋚⋛⋜⋝⋞⋟⋠⋡⋢⋣⋤⋥⋦⋧⋨⋩⋪⋫⋬⋭⋮⋯⋰⋱⋲⋳⋴⋵⋶⋷⋸⋹⋺⋻⋼⋽⋾⋿",
                "options": ["Math ∑", "Greek α", "Arrows →", "Symbols ★"],
                "description": "Mathematical and special symbols"
            },
            
            {
                "name": "Zero Width Test",
                "question": "Testing zero-width characters: \u200b\u200c\u200d\ufeff",
                "options": ["Option\u200bA", "Option\u200cB", "Option\u200dC"],
                "description": "Zero-width characters"
            }
        ]
        
        for i, scenario in enumerate(unicode_scenarios):
            try:
                poll_data = {
                    "name": scenario["name"],
                    "question": scenario["question"],
                    "options": scenario["options"],
                    "emojis": ["🇦", "🇧", "🇨", "🇩"][:len(scenario["options"])],
                    "server_id": self.test_server_id,
                    "channel_id": self.test_channel_id,
                    "open_time": datetime.now(pytz.UTC) + timedelta(minutes=1),
                    "close_time": datetime.now(pytz.UTC) + timedelta(hours=1),
                    "timezone": "UTC",
                    "anonymous": False,
                    "multiple_choice": False,
                    "ping_role_enabled": False,
                    "ping_role_id": None,
                    "creator_id": self.test_user_id
                }
                
                bot = get_bot_instance()
                bulletproof_ops = BulletproofPollOperations(bot)
                
                result = await bulletproof_ops.create_bulletproof_poll(
                    poll_data=poll_data,
                    user_id=self.test_user_id
                )
                
                if result["success"]:
                    logger.info(f"✅ Unicode test {i+1} passed: {scenario['description']}")
                else:
                    logger.warning(f"⚠️ Unicode test {i+1} failed: {result.get('error', 'Unknown error')}")
                    
            except Exception as e:
                logger.error(f"❌ Unicode test {i+1} exception: {e}")
    
    async def test_timing_edge_cases(self):
        """Test timing-related edge cases"""
        logger.info("🔍 Testing timing edge cases...")
        
        now = datetime.now(pytz.UTC)
        
        timing_scenarios = [
            {
                "description": "Very short duration (1 minute)",
                "open_time": now + timedelta(minutes=1),
                "close_time": now + timedelta(minutes=2)
            },
            
            {
                "description": "Very long duration (30 days)",
                "open_time": now + timedelta(minutes=1),
                "close_time": now + timedelta(days=30)
            },
            
            {
                "description": "Different timezone (Tokyo)",
                "open_time": now + timedelta(hours=1),
                "close_time": now + timedelta(hours=2),
                "timezone": "Asia/Tokyo"
            },
            
            {
                "description": "DST transition period",
                "open_time": now + timedelta(hours=1),
                "close_time": now + timedelta(hours=2),
                "timezone": "US/Eastern"
            },
            
            {
                "description": "Leap year edge case",
                "open_time": datetime(2024, 2, 29, 12, 0, tzinfo=pytz.UTC),
                "close_time": datetime(2024, 3, 1, 12, 0, tzinfo=pytz.UTC)
            }
        ]
        
        for i, scenario in enumerate(timing_scenarios):
            try:
                poll_data = {
                    "name": f"Timing Test {i+1}",
                    "question": f"Testing: {scenario['description']}",
                    "options": ["Option A", "Option B"],
                    "emojis": ["🇦", "🇧"],
                    "server_id": self.test_server_id,
                    "channel_id": self.test_channel_id,
                    "open_time": scenario["open_time"],
                    "close_time": scenario["close_time"],
                    "timezone": scenario.get("timezone", "UTC"),
                    "anonymous": False,
                    "multiple_choice": False,
                    "ping_role_enabled": False,
                    "ping_role_id": None,
                    "creator_id": self.test_user_id
                }
                
                bot = get_bot_instance()
                bulletproof_ops = BulletproofPollOperations(bot)
                
                result = await bulletproof_ops.create_bulletproof_poll(
                    poll_data=poll_data,
                    user_id=self.test_user_id
                )
                
                if result["success"]:
                    logger.info(f"✅ Timing test {i+1} passed: {scenario['description']}")
                else:
                    logger.warning(f"⚠️ Timing test {i+1} failed: {result.get('error', 'Unknown error')}")
                    
            except Exception as e:
                logger.error(f"❌ Timing test {i+1} exception: {e}")
    
    async def test_emoji_combinations(self):
        """Test various emoji combinations"""
        logger.info("🔍 Testing emoji combinations...")
        
        emoji_scenarios = [
            {
                "description": "Standard Unicode emojis",
                "emojis": ["😀", "😃", "😄", "😁"]
            },
            
            {
                "description": "Flag emojis",
                "emojis": ["🇺🇸", "🇬🇧", "🇯🇵", "🇩🇪"]
            },
            
            {
                "description": "Complex emojis with modifiers",
                "emojis": ["👨‍💻", "👩‍🚀", "🏳️‍🌈", "👨‍👩‍👧‍👦"]
            },
            
            {
                "description": "Mixed emoji types",
                "emojis": ["🎉", "⭐", "🔥", "💯", "✨"]
            },
            
            {
                "description": "Skin tone modifiers",
                "emojis": ["👍🏻", "👍🏼", "👍🏽", "👍🏾", "👍🏿"]
            }
        ]
        
        for i, scenario in enumerate(emoji_scenarios):
            try:
                options = [f"Option {j+1}" for j in range(len(scenario["emojis"]))]
                
                poll_data = {
                    "name": f"Emoji Test {i+1}",
                    "question": f"Testing: {scenario['description']}",
                    "options": options,
                    "emojis": scenario["emojis"],
                    "server_id": self.test_server_id,
                    "channel_id": self.test_channel_id,
                    "open_time": datetime.now(pytz.UTC) + timedelta(minutes=1),
                    "close_time": datetime.now(pytz.UTC) + timedelta(hours=1),
                    "timezone": "UTC",
                    "anonymous": False,
                    "multiple_choice": False,
                    "ping_role_enabled": False,
                    "ping_role_id": None,
                    "creator_id": self.test_user_id
                }
                
                bot = get_bot_instance()
                bulletproof_ops = BulletproofPollOperations(bot)
                
                result = await bulletproof_ops.create_bulletproof_poll(
                    poll_data=poll_data,
                    user_id=self.test_user_id
                )
                
                if result["success"]:
                    logger.info(f"✅ Emoji test {i+1} passed: {scenario['description']}")
                else:
                    logger.warning(f"⚠️ Emoji test {i+1} failed: {result.get('error', 'Unknown error')}")
                    
            except Exception as e:
                logger.error(f"❌ Emoji test {i+1} exception: {e}")
    
    async def test_large_content(self):
        """Test handling of large content"""
        logger.info("🔍 Testing large content scenarios...")
        
        # Generate large content
        large_name = "Large Content Test " + "X" * 200
        large_question = "This is a very long question. " * 50  # ~1500 chars
        large_options = [f"This is a very long option that contains a lot of text to test the system's ability to handle large amounts of content in poll options. Option {i+1}." for i in range(10)]
        
        try:
            poll_data = {
                "name": large_name,
                "question": large_question,
                "options": large_options,
                "emojis": ["🇦", "🇧", "🇨", "🇩", "🇪", "🇫", "🇬", "🇭", "🇮", "🇯"],
                "server_id": self.test_server_id,
                "channel_id": self.test_channel_id,
                "open_time": datetime.now(pytz.UTC) + timedelta(minutes=1),
                "close_time": datetime.now(pytz.UTC) + timedelta(hours=1),
                "timezone": "UTC",
                "anonymous": False,
                "multiple_choice": True,  # Test with multiple choice
                "ping_role_enabled": True,  # Test with role ping
                "ping_role_id": self.test_role_id,
                "creator_id": self.test_user_id
            }
            
            bot = get_bot_instance()
            bulletproof_ops = BulletproofPollOperations(bot)
            
            result = await bulletproof_ops.create_bulletproof_poll(
                poll_data=poll_data,
                user_id=self.test_user_id
            )
            
            if result["success"]:
                logger.info("✅ Large content test passed")
            else:
                logger.warning(f"⚠️ Large content test failed: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            logger.error(f"❌ Large content test exception: {e}")
    
    async def test_concurrent_creation(self):
        """Test concurrent poll creation"""
        logger.info("🔍 Testing concurrent poll creation...")
        
        async def create_poll(poll_id: int):
            """Create a single poll"""
            poll_data = {
                "name": f"Concurrent Test Poll {poll_id}",
                "question": f"This is concurrent test poll number {poll_id}",
                "options": [f"Option A-{poll_id}", f"Option B-{poll_id}"],
                "emojis": ["🇦", "🇧"],
                "server_id": self.test_server_id,
                "channel_id": self.test_channel_id,
                "open_time": datetime.now(pytz.UTC) + timedelta(minutes=1),
                "close_time": datetime.now(pytz.UTC) + timedelta(hours=1),
                "timezone": "UTC",
                "anonymous": poll_id % 2 == 0,  # Alternate anonymous
                "multiple_choice": poll_id % 3 == 0,  # Every third is multiple choice
                "ping_role_enabled": False,
                "ping_role_id": None,
                "creator_id": self.test_user_id
            }
            
            bot = get_bot_instance()
            bulletproof_ops = BulletproofPollOperations(bot)
            
            result = await bulletproof_ops.create_bulletproof_poll(
                poll_data=poll_data,
                user_id=self.test_user_id
            )
            
            return poll_id, result["success"], result.get("error", "")
        
        # Create 10 polls concurrently
        tasks = [create_poll(i) for i in range(10)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = 0
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"❌ Concurrent creation exception: {result}")
            else:
                poll_id, success, error = result
                if success:
                    success_count += 1
                    logger.info(f"✅ Concurrent poll {poll_id} created successfully")
                else:
                    logger.warning(f"⚠️ Concurrent poll {poll_id} failed: {error}")
        
        logger.info(f"Concurrent creation results: {success_count}/10 successful")
    
    async def test_malformed_data(self):
        """Test handling of malformed data"""
        logger.info("🔍 Testing malformed data scenarios...")
        
        malformed_scenarios = [
            {
                "description": "Non-string name",
                "data": {"name": 12345}
            },
            
            {
                "description": "Non-list options",
                "data": {"options": "not a list"}
            },
            
            {
                "description": "Mixed type options",
                "data": {"options": ["String", 123, None, {"key": "value"}]}
            },
            
            {
                "description": "Invalid datetime",
                "data": {"open_time": "not a datetime"}
            },
            
            {
                "description": "Negative numbers",
                "data": {"server_id": "-123", "channel_id": "-456"}
            }
        ]
        
        for i, scenario in enumerate(malformed_scenarios):
            try:
                # Start with valid base data
                poll_data = {
                    "name": "Malformed Test",
                    "question": "Testing malformed data",
                    "options": ["Option A", "Option B"],
                    "emojis": ["🇦", "🇧"],
                    "server_id": self.test_server_id,
                    "channel_id": self.test_channel_id,
                    "open_time": datetime.now(pytz.UTC) + timedelta(minutes=1),
                    "close_time": datetime.now(pytz.UTC) + timedelta(hours=1),
                    "timezone": "UTC",
                    "anonymous": False,
                    "multiple_choice": False,
                    "ping_role_enabled": False,
                    "ping_role_id": None,
                    "creator_id": self.test_user_id
                }
                
                # Apply malformed data
                poll_data.update(scenario["data"])
                
                bot = get_bot_instance()
                bulletproof_ops = BulletproofPollOperations(bot)
                
                result = await bulletproof_ops.create_bulletproof_poll(
                    poll_data=poll_data,
                    user_id=self.test_user_id
                )
                
                if result["success"]:
                    logger.warning(f"⚠️ Malformed test {i+1} unexpectedly succeeded: {scenario['description']}")
                else:
                    logger.info(f"✅ Malformed test {i+1} correctly failed: {scenario['description']}")
                    
            except Exception as e:
                logger.info(f"✅ Malformed test {i+1} correctly threw exception: {scenario['description']} - {e}")
    
    async def test_database_stress(self):
        """Test database stress scenarios"""
        logger.info("🔍 Testing database stress scenarios...")
        
        # Create many polls rapidly
        for i in range(50):
            try:
                poll_data = {
                    "name": f"Stress Test Poll {i+1}",
                    "question": f"Database stress test poll number {i+1}",
                    "options": [f"Option A-{i+1}", f"Option B-{i+1}", f"Option C-{i+1}"],
                    "emojis": ["🇦", "🇧", "🇨"],
                    "server_id": self.test_server_id,
                    "channel_id": self.test_channel_id,
                    "open_time": datetime.now(pytz.UTC) + timedelta(minutes=1),
                    "close_time": datetime.now(pytz.UTC) + timedelta(hours=1),
                    "timezone": "UTC",
                    "anonymous": i % 2 == 0,
                    "multiple_choice": i % 3 == 0,
                    "ping_role_enabled": i % 4 == 0,
                    "ping_role_id": self.test_role_id if i % 4 == 0 else None,
                    "creator_id": self.test_user_id
                }
                
                bot = get_bot_instance()
                bulletproof_ops = BulletproofPollOperations(bot)
                
                result = await bulletproof_ops.create_bulletproof_poll(
                    poll_data=poll_data,
                    user_id=self.test_user_id
                )
                
                if result["success"]:
                    if i % 10 == 0:  # Log every 10th success
                        logger.info(f"✅ Stress test poll {i+1} created")
                else:
                    logger.warning(f"⚠️ Stress test poll {i+1} failed: {result.get('error', 'Unknown error')}")
                
                # Small delay to avoid overwhelming the system
                await asyncio.sleep(0.01)
                
            except Exception as e:
                logger.error(f"❌ Stress test poll {i+1} exception: {e}")
        
        logger.info("Database stress test completed")
    
    async def run_all_scenarios(self):
        """Run all test scenarios"""
        logger.info("🚀 Running all poll creation scenarios...")
        
        scenarios_to_run = [
            ("Boundary Conditions", self.test_boundary_conditions),
            ("Error Conditions", self.test_error_conditions),
            ("Unicode Stress", self.test_unicode_stress),
            ("Timing Edge Cases", self.test_timing_edge_cases),
            ("Emoji Combinations", self.test_emoji_combinations),
            ("Large Content", self.test_large_content),
            ("Concurrent Creation", self.test_concurrent_creation),
            ("Malformed Data", self.test_malformed_data),
            ("Database Stress", self.test_database_stress)
        ]
        
        for name, scenario_func in scenarios_to_run:
            logger.info(f"\n{'='*60}")
            logger.info(f"Running: {name}")
            logger.info(f"{'='*60}")
            
            try:
                await scenario_func()
                logger.info(f"✅ {name} completed")
            except Exception as e:
                logger.error(f"❌ {name} failed with exception: {e}")
            
            # Brief pause between scenarios
            await asyncio.sleep(1)
        
        logger.info("🎉 All poll creation scenarios completed!")

async def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test poll creation scenarios")
    parser.add_argument("--scenario", choices=list(PollCreationScenarios().scenarios.keys()),
                       help="Run specific scenario")
    
    args = parser.parse_args()
    
    # Initialize database
    init_database()
    
    scenarios = PollCreationScenarios()
    
    if args.scenario:
        logger.info(f"Running scenario: {args.scenario}")
        await scenarios.scenarios[args.scenario]()
    else:
        logger.info("Running all scenarios...")
        await scenarios.run_all_scenarios()

if __name__ == "__main__":
    asyncio.run(main())
