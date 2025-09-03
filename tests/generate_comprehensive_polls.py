#!/usr/bin/env python3
"""
Comprehensive Poll Generation Script
Creates polls with every possible combination of options and configurations.

This script generates polls systematically covering:
- Option counts: 2, 3, 4, 5, 6, 7, 8, 9, 10 options
- Poll types: single choice, multiple choice
- Visibility: anonymous, public
- Media: with images, without images (including real images from sample-images repository)
- Role pings: enabled, disabled
- Emojis: default Unicode, custom Discord emojis, mixed
- Scheduling: immediate, future scheduled
- All edge cases and combinations

Features:
- Standard mode: Generate ~880+ systematic poll combinations
- Real images mode: Use 2000+ real images from sample-images repository  
- Ultimate mode: Create polls using RANDOM COMBINATIONS with each real image (1 combination per image = 2000+ polls with combination tallies)
- Export mode: Export poll configurations to JSON for analysis

Usage:
    # Standard comprehensive testing
    uv run tests/generate_comprehensive_polls.py [--dry-run] [--limit N]
    
    # With real images from sample-images repository
    uv run tests/generate_comprehensive_polls.py --use-real-images

    # Ultimate testing: create a poll for each real image
    uv run tests/generate_comprehensive_polls.py --use-all-images

    # Keep repository after testing
    uv run tests/generate_comprehensive_polls.py --use-all-images --no-cleanup
    
    # Export poll combinations to JSON
    uv run tests/generate_comprehensive_polls.py --export-json
"""

import asyncio
import logging
import os
import sys
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional
import pytz
import json
import uuid
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from polly.database import get_db_session, Poll, init_database
from polly.discord_bot import get_bot_instance
from polly.poll_operations import BulletproofPollOperations
from polly.error_handler import PollErrorHandler
from polly.timezone_scheduler_fix import TimezoneAwareScheduler
from polly.background_tasks import get_scheduler
from tests.test_image_generator import TestImageGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ComprehensivePollGenerator:
    """Generates comprehensive test polls covering all possible combinations"""
    
    def __init__(self, dry_run: bool = False, limit: Optional[int] = None, 
                 server_id: Optional[str] = None, channel_id: Optional[str] = None,
                 user_id: Optional[str] = None, role_id: Optional[str] = None):
        self.dry_run = dry_run
        self.limit = limit
        self.generated_count = 0
        self.success_count = 0
        self.error_count = 0
        self.combinations = []
        self.should_cleanup = True  # Default to cleanup
        
        # Test data - use provided IDs or defaults
        self.test_user_id = user_id or "123456789012345678"  # Mock Discord user ID
        self.test_server_id = server_id or "987654321098765432"  # Mock Discord server ID
        self.test_channel_id = channel_id or "111222333444555666"  # Mock Discord channel ID
        self.test_role_id = role_id or "777888999000111222"  # Mock Discord role ID
        
        # Sample poll content
        self.poll_names = [
            "Test Poll",
            "Sample Survey",
            "Quick Question",
            "Team Decision",
            "Community Choice",
            "Feedback Request",
            "Opinion Poll",
            "Preference Survey",
            "Vote Now",
            "Choose Wisely"
        ]
        
        self.poll_questions = [
            "What is your favorite option?",
            "Which choice do you prefer?",
            "What should we do next?",
            "Pick your top selection:",
            "What's your opinion on this?",
            "Which option works best?",
            "What do you think about this?",
            "Select your preference:",
            "What would you choose?",
            "Which one do you like most?"
        ]
        
        self.option_templates = {
            2: ["Option A", "Option B"],
            3: ["First Choice", "Second Choice", "Third Choice"],
            4: ["Alpha", "Beta", "Gamma", "Delta"],
            5: ["Red", "Blue", "Green", "Yellow", "Purple"],
            6: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
            7: ["Spring", "Summer", "Fall", "Winter", "Rainy", "Snowy", "Sunny"],
            8: ["Apple", "Banana", "Cherry", "Date", "Elderberry", "Fig", "Grape", "Honeydew"],
            9: ["One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"],
            10: ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
        }
        
        # Emoji sets for testing
        self.unicode_emojis = ["😀", "😃", "😄", "😁", "😆", "😅", "😂", "🤣", "😊", "😇"]
        self.letter_emojis = ["🇦", "🇧", "🇨", "🇩", "🇪", "🇫", "🇬", "🇭", "🇮", "🇯"]
        self.symbol_emojis = ["⭐", "❤️", "🔥", "👍", "👎", "✅", "❌", "⚠️", "❓", "❗"]
        
        # Extended emoji sets for random selection
        self.all_unicode_emojis = [
            "😀", "😃", "😄", "😁", "😆", "😅", "😂", "🤣", "😊", "😇",
            "🙂", "🙃", "😉", "😌", "😍", "🥰", "😘", "😗", "😙", "😚",
            "😋", "😛", "😝", "😜", "🤪", "🤨", "🧐", "🤓", "😎", "🤩",
            "🥳", "😏", "😒", "😞", "😔", "😟", "😕", "🙁", "☹️", "😣",
            "😖", "😫", "😩", "🥺", "😢", "😭", "😤", "😠", "😡", "🤬"
        ]
        
        self.all_symbol_emojis = [
            "⭐", "❤️", "🔥", "👍", "👎", "✅", "❌", "⚠️", "❓", "❗",
            "💯", "💢", "💥", "💫", "💦", "💨", "🕳️", "💣", "💤", "👋",
            "🤚", "🖐️", "✋", "🖖", "👌", "🤌", "🤏", "✌️", "🤞", "🤟",
            "🤘", "🤙", "👈", "👉", "👆", "🖕", "👇", "☝️", "👍", "👎"
        ]
        
        self.all_letter_emojis = [
            "🇦", "🇧", "🇨", "🇩", "🇪", "🇫", "🇬", "🇭", "🇮", "🇯",
            "🇰", "🇱", "🇲", "🇳", "🇴", "🇵", "🇶", "🇷", "🇸", "🇹",
            "🇺", "🇻", "🇼", "🇽", "🇾", "🇿", "1️⃣", "2️⃣", "3️⃣", "4️⃣",
            "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟", "🔢", "#️⃣", "*️⃣", "⏏️"
        ]
        
        # Timezones for testing
        self.test_timezones = [
            "UTC",
            "US/Eastern",
            "US/Central", 
            "US/Mountain",
            "US/Pacific",
            "Europe/London",
            "Europe/Paris",
            "Asia/Tokyo",
            "Australia/Sydney"
        ]
        
        # Initialize image generator for real test images
        self.image_generator = TestImageGenerator()
        
        # Image types for different scenarios
        self.image_types = ["small", "medium", "large", "pattern", "unicode", "minimal", "real"]
    
    def generate_all_combinations(self) -> List[Dict[str, Any]]:
        """Generate all possible poll combinations"""
        combinations = []
        
        # Option counts to test
        option_counts = [2, 3, 4, 5, 6, 7, 8, 9, 10]
        
        # Boolean flags to test
        anonymous_options = [True, False]
        multiple_choice_options = [True, False]
        ping_role_options = [True, False]
        image_options = [True, False]
        
        # Emoji types to test
        emoji_types = ["default", "unicode", "symbols", "mixed", "random", "custom"]
        
        # Scheduling options
        schedule_types = ["immediate", "future", "far_future"]
        
        # Generate combinations
        combination_id = 0
        for option_count in option_counts:
            for anonymous in anonymous_options:
                for multiple_choice in multiple_choice_options:
                    for ping_role in ping_role_options:
                        for has_image in image_options:
                            for emoji_type in emoji_types:
                                for schedule_type in schedule_types:
                                    # Skip custom emojis for now (requires Discord bot)
                                    if emoji_type == "custom":
                                        continue
                                    
                                    combination = {
                                        "id": combination_id,
                                        "option_count": option_count,
                                        "anonymous": anonymous,
                                        "multiple_choice": multiple_choice,
                                        "ping_role_enabled": ping_role,
                                        "has_image": has_image,
                                        "emoji_type": emoji_type,
                                        "schedule_type": schedule_type,
                                        "timezone": self.test_timezones[combination_id % len(self.test_timezones)]
                                    }
                                    combinations.append(combination)
                                    combination_id += 1
        
        # Add edge cases
        edge_cases = self.generate_edge_cases()
        combinations.extend(edge_cases)
        
        logger.info(f"Generated {len(combinations)} poll combinations")
        return combinations
    
    def generate_edge_cases(self) -> List[Dict[str, Any]]:
        """Generate edge case poll combinations"""
        edge_cases = []
        
        # Edge case 1: Maximum options with all features enabled
        edge_cases.append({
            "id": "edge_max_features",
            "option_count": 10,
            "anonymous": True,
            "multiple_choice": True,
            "ping_role_enabled": True,
            "has_image": True,
            "emoji_type": "mixed",
            "schedule_type": "future",
            "timezone": "US/Eastern",
            "name": "Maximum Features Test Poll",
            "question": "This poll tests all maximum features enabled at once with 10 options, anonymous voting, multiple choice, role ping, and image."
        })
        
        # Edge case 2: Minimum options with no extra features
        edge_cases.append({
            "id": "edge_min_features",
            "option_count": 2,
            "anonymous": False,
            "multiple_choice": False,
            "ping_role_enabled": False,
            "has_image": False,
            "emoji_type": "default",
            "schedule_type": "immediate",
            "timezone": "UTC",
            "name": "Minimal Test Poll",
            "question": "Simple two-option poll with no extra features."
        })
        
        # Edge case 3: Long content test
        edge_cases.append({
            "id": "edge_long_content",
            "option_count": 5,
            "anonymous": False,
            "multiple_choice": True,
            "ping_role_enabled": False,
            "has_image": False,
            "emoji_type": "unicode",
            "schedule_type": "future",
            "timezone": "Europe/London",
            "name": "Very Long Poll Name That Tests The Maximum Length Limits For Poll Names In The System",
            "question": "This is a very long poll question that tests the maximum length limits for poll questions in the system. It contains multiple sentences and should test how the system handles longer text content. The question continues to be quite lengthy to ensure we test the boundaries of what the system can handle for poll question text content.",
            "long_options": True
        })
        
        # Edge case 4: Special characters and Unicode
        edge_cases.append({
            "id": "edge_special_chars",
            "option_count": 4,
            "anonymous": True,
            "multiple_choice": False,
            "ping_role_enabled": True,
            "has_image": True,
            "emoji_type": "symbols",
            "schedule_type": "immediate",
            "timezone": "Asia/Tokyo",
            "name": "Special Characters Test: !@#$%^&*()_+-=[]{}|;':\",./<>?",
            "question": "Testing special characters: àáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ and symbols: ™®©℠℡№℮",
            "special_options": True
        })
        
        # Edge case 5: Different timezone combinations
        for i, tz in enumerate(self.test_timezones):
            edge_cases.append({
                "id": f"edge_timezone_{i}",
                "option_count": 3,
                "anonymous": i % 2 == 0,
                "multiple_choice": i % 3 == 0,
                "ping_role_enabled": i % 4 == 0,
                "has_image": i % 5 == 0,
                "emoji_type": ["default", "unicode", "symbols"][i % 3],
                "schedule_type": "future",
                "timezone": tz,
                "name": f"Timezone Test {tz}",
                "question": f"Testing poll creation in {tz} timezone."
            })
        
        logger.info(f"Generated {len(edge_cases)} edge case combinations")
        return edge_cases
    
    def create_poll_data(self, combination: Dict[str, Any]) -> Dict[str, Any]:
        """Create poll data from combination specification"""
        option_count = combination["option_count"]
        
        # Generate poll name
        if "name" in combination:
            name = combination["name"]
        else:
            base_name = self.poll_names[combination["id"] % len(self.poll_names)]
            name = f"{base_name} ({option_count} options, {combination['emoji_type']} emojis)"
        
        # Generate poll question
        if "question" in combination:
            question = combination["question"]
        else:
            base_question = self.poll_questions[combination["id"] % len(self.poll_questions)]
            question = f"{base_question} [Test ID: {combination['id']}]"
        
        # Generate options
        if combination.get("long_options"):
            options = [
                f"This is a very long option text that tests the maximum length limits for poll options in the system - Option {i+1}"
                for i in range(option_count)
            ]
        elif combination.get("special_options"):
            options = [
                "Option 1: Special chars !@#$%^&*()_+-=[]{}|;':\",./<>?",
                "Option 2: Unicode àáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ",
                "Option 3: Symbols ™®©℠℡№℮",
                "Option 4: Mixed content 123 ABC !@# àáâ ™®©"
            ][:option_count]
        else:
            base_options = self.option_templates[option_count]
            options = [f"{opt} (Test {combination['id']})" for opt in base_options]
        
        # Generate emojis based on type
        emojis = self.generate_emojis(combination["emoji_type"], option_count)
        
        # Generate times
        now = datetime.now(pytz.UTC)
        if combination["schedule_type"] == "immediate":
            open_time = now + timedelta(minutes=1)
            close_time = open_time + timedelta(hours=1)
        elif combination["schedule_type"] == "future":
            open_time = now + timedelta(hours=1)
            close_time = open_time + timedelta(hours=2)
        else:  # far_future
            open_time = now + timedelta(days=1)
            close_time = open_time + timedelta(days=1)
        
        poll_data = {
            "name": name,
            "question": question,
            "options": options,
            "emojis": emojis,
            "server_id": self.test_server_id,
            "channel_id": self.test_channel_id,
            "open_time": open_time,
            "close_time": close_time,
            "timezone": combination["timezone"],
            "anonymous": combination["anonymous"],
            "multiple_choice": combination["multiple_choice"],
            "ping_role_enabled": combination["ping_role_enabled"],
            "ping_role_id": self.test_role_id if combination["ping_role_enabled"] else None,
            "creator_id": self.test_user_id
        }
        
        return poll_data
    
    def generate_emojis(self, emoji_type: str, count: int) -> List[str]:
        """Generate emojis based on type and count"""
        import random
        
        if emoji_type == "default":
            return self.letter_emojis[:count]
        elif emoji_type == "unicode":
            return self.unicode_emojis[:count]
        elif emoji_type == "symbols":
            return self.symbol_emojis[:count]
        elif emoji_type == "mixed":
            # Mix different emoji types
            emojis = []
            for i in range(count):
                if i % 3 == 0:
                    emojis.append(self.unicode_emojis[i % len(self.unicode_emojis)])
                elif i % 3 == 1:
                    emojis.append(self.symbol_emojis[i % len(self.symbol_emojis)])
                else:
                    emojis.append(self.letter_emojis[i % len(self.letter_emojis)])
            return emojis
        elif emoji_type == "random":
            # Randomly select from all available emoji types
            all_emojis = self.all_unicode_emojis + self.all_symbol_emojis + self.all_letter_emojis
            return random.sample(all_emojis, min(count, len(all_emojis)))
        else:
            # Fallback to default
            return self.letter_emojis[:count]
    
    async def create_single_poll(self, combination: Dict[str, Any]) -> Tuple[bool, str]:
        """Create a single poll from combination data"""
        try:
            poll_data = self.create_poll_data(combination)
            
            if self.dry_run:
                logger.info(f"DRY RUN: Would create poll - {poll_data['name']}")
                return True, f"DRY RUN: Poll {combination['id']} would be created"
            
            # Get bot instance (may be None in test environment)
            bot = get_bot_instance()
            
            # Create bulletproof poll operations
            bulletproof_ops = BulletproofPollOperations(bot)
            
            # Handle image data if needed
            image_file_data = None
            image_filename = None
            image_message_text = None
            
            if combination["has_image"]:
                # Generate appropriate test image based on combination
                image_type = self.image_types[combination["id"] % len(self.image_types)]
                image_file_data, image_filename = self.image_generator.get_image_for_scenario(
                    image_type, combination['id']
                )
                image_message_text = f"Test image for poll {combination['id']} ({image_type})"
            
            # Create the poll
            result = await bulletproof_ops.create_bulletproof_poll(
                poll_data=poll_data,
                user_id=self.test_user_id,
                image_file=image_file_data,
                image_filename=image_filename,
                image_message_text=image_message_text
            )
            
            if result["success"]:
                poll_id = result["poll_id"]
                logger.info(f"✅ Created poll {poll_id}: {poll_data['name']}")
                return True, f"Created poll {poll_id}"
            else:
                error_msg = result.get("error", "Unknown error")
                logger.error(f"❌ Failed to create poll {combination['id']}: {error_msg}")
                return False, error_msg
                
        except Exception as e:
            logger.error(f"❌ Exception creating poll {combination['id']}: {e}")
            return False, str(e)
    
    async def generate_all_polls(self):
        """Generate all poll combinations"""
        logger.info("Starting comprehensive poll generation...")
        
        # Initialize database
        init_database()
        
        # Generate all combinations
        self.combinations = self.generate_all_combinations()
        
        if self.limit:
            self.combinations = self.combinations[:self.limit]
            logger.info(f"Limited to first {self.limit} combinations")
        
        logger.info(f"Will generate {len(self.combinations)} polls")
        
        # Create polls
        for i, combination in enumerate(self.combinations):
            logger.info(f"Creating poll {i+1}/{len(self.combinations)} (ID: {combination['id']})")
            
            success, message = await self.create_single_poll(combination)
            
            self.generated_count += 1
            if success:
                self.success_count += 1
            else:
                self.error_count += 1
            
            # Add small delay to avoid overwhelming the system
            await asyncio.sleep(0.1)
        
        # Print summary
        self.print_summary()
    
    def print_summary(self):
        """Print generation summary"""
        logger.info("=" * 60)
        logger.info("COMPREHENSIVE POLL GENERATION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total combinations generated: {self.generated_count}")
        logger.info(f"Successful creations: {self.success_count}")
        logger.info(f"Failed creations: {self.error_count}")
        logger.info(f"Success rate: {(self.success_count/self.generated_count*100):.1f}%" if self.generated_count > 0 else "N/A")
        
        if self.dry_run:
            logger.info("NOTE: This was a DRY RUN - no polls were actually created")
        
        logger.info("=" * 60)
        
        # Print combination breakdown
        logger.info("COMBINATION BREAKDOWN:")
        option_counts = {}
        emoji_types = {}
        schedule_types = {}
        
        for combo in self.combinations:
            # Count option counts
            count = combo["option_count"]
            option_counts[count] = option_counts.get(count, 0) + 1
            
            # Count emoji types
            emoji_type = combo["emoji_type"]
            emoji_types[emoji_type] = emoji_types.get(emoji_type, 0) + 1
            
            # Count schedule types
            schedule_type = combo["schedule_type"]
            schedule_types[schedule_type] = schedule_types.get(schedule_type, 0) + 1
        
        logger.info(f"Option counts: {dict(sorted(option_counts.items()))}")
        logger.info(f"Emoji types: {emoji_types}")
        logger.info(f"Schedule types: {schedule_types}")
        logger.info("=" * 60)
    
    async def generate_polls_for_all_images(self):
        """Generate polls using random combinations with each real image"""
        logger.info("Starting comprehensive poll generation with ALL IMAGES...")
        logger.info("This will create polls using RANDOM COMBINATIONS with each real image!")
        
        # Initialize database
        init_database()
        
        # Setup real images
        if not hasattr(self.image_generator, 'real_images_cache') or not self.image_generator.real_images_cache:
            self.image_generator._setup_real_images()
        
        total_images = len(self.image_generator.real_images_cache)
        logger.info(f"Found {total_images} real images to create polls for")
        
        if total_images == 0:
            logger.error("No real images found! Make sure the sample-images repository is available.")
            return
        
        # Generate all combinations (but force has_image=True for all)
        base_combinations = self.generate_all_combinations()
        
        # Filter to only combinations that have images
        image_combinations = [combo for combo in base_combinations if combo["has_image"]]
        logger.info(f"Available {len(image_combinations)} combinations that include images")
        
        # Apply limit to images if specified
        if self.limit:
            total_images = min(self.limit, total_images)
            logger.info(f"Limited to first {total_images} images")
        
        logger.info(f"Will create {total_images} total polls (1 random combination per image)")
        
        start_time = datetime.now()
        
        # Track combination usage for tallying
        combination_usage = {}
        
        # Create one poll per image with a random combination
        for img_idx, image_path in enumerate(self.image_generator.real_images_cache[:total_images]):
            image_name = os.path.basename(image_path)
            
            # Select a random combination for this image
            import random
            combination = random.choice(image_combinations)
            
            # Track combination usage
            combo_key = f"{combination['option_count']}opt_{combination['emoji_type']}_{combination['schedule_type']}_{'anon' if combination['anonymous'] else 'pub'}_{'multi' if combination['multiple_choice'] else 'single'}_{'ping' if combination['ping_role_enabled'] else 'noping'}"
            combination_usage[combo_key] = combination_usage.get(combo_key, 0) + 1
            
            logger.info(f"Creating poll {img_idx+1}/{total_images} - Image: {image_name}, Combo: {combo_key}")
            
            success = await self.create_poll_with_image_and_combination(image_path, combination, img_idx + 1)
            
            self.generated_count += 1
            if success:
                self.success_count += 1
            else:
                self.error_count += 1
            
            # Add small delay to avoid overwhelming the system
            await asyncio.sleep(0.1)
            
            # Progress update every 100 polls
            if (img_idx + 1) % 100 == 0:
                elapsed = datetime.now() - start_time
                rate = (img_idx + 1) / elapsed.total_seconds()
                logger.info(f"Progress: {img_idx+1}/{total_images} polls created ({rate:.1f} polls/sec)")
        
        # Print summary with combination tallies
        self.print_all_images_summary_with_tallies(start_time, combination_usage)
    
    async def create_poll_with_image_and_combination(self, image_path: str, combination: Dict[str, Any], poll_number: int) -> bool:
        """Create a poll with a specific image using a full combination"""
        try:
            # Create poll data from the combination
            poll_data = self.create_poll_data(combination)
            
            # Override the poll name and question to be image-specific
            image_name = os.path.basename(image_path)
            poll_data["name"] = f"Real Image Poll #{poll_number}: {image_name} (Combo {combination['id']})"
            poll_data["question"] = f"What do you think of this image? ({image_name}) - Testing combination {combination['id']}"
            
            if self.dry_run:
                logger.info(f"DRY RUN: Would create poll with image {image_name} using combination {combination['id']}")
                return True
            
            # Get bot instance (may be None in test environment)
            bot = get_bot_instance()
            
            # Create bulletproof poll operations
            bulletproof_ops = BulletproofPollOperations(bot)
            
            # Load the specific real image
            try:
                with open(image_path, 'rb') as f:
                    image_file_data = f.read()
                image_filename = image_name
                image_message_text = f"Real image test: {image_name} (Combination {combination['id']})"
            except Exception as e:
                logger.error(f"Failed to load image {image_path}: {e}")
                return False
            
            # Create the poll
            result = await bulletproof_ops.create_bulletproof_poll(
                poll_data=poll_data,
                user_id=self.test_user_id,
                image_file=image_file_data,
                image_filename=image_filename,
                image_message_text=image_message_text
            )
            
            if result["success"]:
                poll_id = result["poll_id"]
                logger.info(f"✅ Created poll {poll_id} with image {image_name} using combination {combination['id']}")
                return True
            else:
                error_msg = result.get("error", "Unknown error")
                logger.error(f"❌ Failed to create poll with image {image_name} using combination {combination['id']}: {error_msg}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Exception creating poll with image {image_path} using combination {combination['id']}: {e}")
            return False

    async def create_poll_with_specific_image(self, image_path: str, index: int) -> bool:
        """Create a poll with a specific image (legacy method for backward compatibility)"""
        try:
            # Create a basic poll configuration for this image
            option_count = 2 + (index % 9)  # 2-10 options
            
            combination = {
                "id": f"image_{index}",
                "option_count": option_count,
                "anonymous": index % 2 == 0,
                "multiple_choice": index % 3 == 0,
                "ping_role_enabled": index % 4 == 0,
                "has_image": True,
                "emoji_type": ["default", "unicode", "symbols", "mixed"][index % 4],
                "schedule_type": "immediate",
                "timezone": self.test_timezones[index % len(self.test_timezones)]
            }
            
            return await self.create_poll_with_image_and_combination(image_path, combination, index + 1)
                
        except Exception as e:
            logger.error(f"❌ Exception creating poll with image {image_path}: {e}")
            return False
    
    def print_all_images_summary_with_tallies(self, start_time: datetime, combination_usage: Dict[str, int]):
        """Print summary for all images generation with combination tallies"""
        end_time = datetime.now()
        duration = end_time - start_time
        
        logger.info("=" * 60)
        logger.info("ALL IMAGES POLL GENERATION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total images processed: {self.generated_count}")
        logger.info(f"Successful poll creations: {self.success_count}")
        logger.info(f"Failed poll creations: {self.error_count}")
        logger.info(f"Success rate: {(self.success_count/self.generated_count*100):.1f}%" if self.generated_count > 0 else "N/A")
        logger.info(f"Total execution time: {duration.total_seconds():.2f} seconds")
        logger.info(f"Average time per poll: {(duration.total_seconds()/self.generated_count):.2f} seconds" if self.generated_count > 0 else "N/A")
        
        if self.dry_run:
            logger.info("NOTE: This was a DRY RUN - no polls were actually created")
        
        logger.info("=" * 60)
        logger.info("COMBINATION USAGE TALLIES:")
        logger.info("=" * 60)
        
        # Sort combinations by usage count (most used first)
        sorted_combinations = sorted(combination_usage.items(), key=lambda x: x[1], reverse=True)
        
        for combo_key, count in sorted_combinations:
            logger.info(f"{combo_key}: {count} polls")
        
        logger.info("=" * 60)
        logger.info(f"Total unique combinations used: {len(combination_usage)}")
        logger.info("=" * 60)

    def print_all_images_summary(self, start_time: datetime):
        """Print summary for all images generation"""
        end_time = datetime.now()
        duration = end_time - start_time
        
        logger.info("=" * 60)
        logger.info("ALL IMAGES POLL GENERATION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total images processed: {self.generated_count}")
        logger.info(f"Successful poll creations: {self.success_count}")
        logger.info(f"Failed poll creations: {self.error_count}")
        logger.info(f"Success rate: {(self.success_count/self.generated_count*100):.1f}%" if self.generated_count > 0 else "N/A")
        logger.info(f"Total execution time: {duration.total_seconds():.2f} seconds")
        logger.info(f"Average time per poll: {(duration.total_seconds()/self.generated_count):.2f} seconds" if self.generated_count > 0 else "N/A")
        
        if self.dry_run:
            logger.info("NOTE: This was a DRY RUN - no polls were actually created")
        
        logger.info("=" * 60)
    
    def export_combinations_json(self, filename: str = "poll_combinations.json"):
        """Export all combinations to JSON file for analysis"""
        try:
            # Convert datetime objects to strings for JSON serialization
            exportable_combinations = []
            for combo in self.combinations:
                poll_data = self.create_poll_data(combo)
                
                # Convert datetime objects to ISO format strings
                exportable_data = {**poll_data}
                exportable_data["open_time"] = poll_data["open_time"].isoformat()
                exportable_data["close_time"] = poll_data["close_time"].isoformat()
                exportable_data["combination_id"] = combo["id"]
                exportable_data["combination_config"] = combo
                
                exportable_combinations.append(exportable_data)
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(exportable_combinations, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Exported {len(exportable_combinations)} combinations to {filename}")
            
        except Exception as e:
            logger.error(f"Failed to export combinations: {e}")

async def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Generate comprehensive test polls")
    parser.add_argument("--dry-run", action="store_true", 
                       help="Show what would be created without actually creating polls")
    parser.add_argument("--limit", type=int, 
                       help="Limit the number of polls to create")
    parser.add_argument("--export-json", action="store_true",
                       help="Export poll combinations to JSON file")
    parser.add_argument("--use-real-images", action="store_true",
                       help="Use real images from sample-images repository")
    parser.add_argument("--use-all-images", action="store_true",
                       help="Create a poll for each image in the repository (2000+ polls)")
    parser.add_argument("--no-cleanup", action="store_true",
                       help="Keep the sample-images repository after testing")
    
    # Discord configuration options
    parser.add_argument("--server-id", type=str,
                       help="Discord server/guild ID to create polls in")
    parser.add_argument("--channel-id", type=str,
                       help="Discord channel ID to create polls in")
    parser.add_argument("--user-id", type=str,
                       help="Discord user ID to use as poll creator")
    parser.add_argument("--role-id", type=str,
                       help="Discord role ID to use for role pings")
    
    args = parser.parse_args()
    
    generator = ComprehensivePollGenerator(
        dry_run=args.dry_run, 
        limit=args.limit,
        server_id=args.server_id,
        channel_id=args.channel_id,
        user_id=args.user_id,
        role_id=args.role_id
    )
    
    # Enable real images if requested
    if args.use_real_images or args.use_all_images:
        generator.image_generator = TestImageGenerator(use_real_images=True)
        logger.info("Real images enabled - will use sample-images repository")
        
        # Store cleanup preference for later use
        generator.should_cleanup = not args.no_cleanup
        if args.no_cleanup:
            logger.info("Repository cleanup disabled - will keep sample-images after testing")
    
    # Handle --use-all-images mode
    if args.use_all_images:
        logger.info("USE ALL IMAGES MODE: Will create a poll for each image in repository")
        await generator.generate_polls_for_all_images()
        return
    
    if args.export_json:
        # Just export combinations without creating polls
        generator.combinations = generator.generate_all_combinations()
        if args.limit:
            generator.combinations = generator.combinations[:args.limit]
        generator.export_combinations_json()
    else:
        # Generate actual polls
        await generator.generate_all_polls()

if __name__ == "__main__":
    asyncio.run(main())
