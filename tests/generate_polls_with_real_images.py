#!/usr/bin/env python3
"""
Real Image Poll Generator
Creates polls using real images from the sample-images repository.

This script clones the sample-images repository, uses the 2000 real images
for comprehensive poll testing, and cleans up afterward.
"""

import os
import sys
import asyncio
import logging
import argparse
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

# Add the parent directory to the path so we can import from polly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from test_image_generator import TestImageGenerator
from polly.database import get_db_session, Poll, User, Guild, Channel, init_database
from polly.discord_bot import get_bot_instance
from polly.poll_operations import BulletproofPollOperations
from polly.error_handler import PollErrorHandler
import pytz

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('tests/real_image_poll_generation.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class RealImagePollGenerator:
    """Generates polls using real images from sample-images repository"""
    
    def __init__(self, loops: int = 1, cleanup: bool = True):
        self.loops = loops
        self.cleanup = cleanup
        self.image_generator = TestImageGenerator(use_real_images=True)
        self.polls_created = 0
        self.errors = 0
        
        # Poll configuration variations
        self.poll_configs = [
            # Basic configurations
            {"options": 2, "multiple_choice": False, "anonymous": False},
            {"options": 3, "multiple_choice": False, "anonymous": True},
            {"options": 4, "multiple_choice": True, "anonymous": False},
            {"options": 5, "multiple_choice": True, "anonymous": True},
            {"options": 6, "multiple_choice": False, "anonymous": False},
            {"options": 7, "multiple_choice": True, "anonymous": True},
            {"options": 8, "multiple_choice": False, "anonymous": True},
            {"options": 9, "multiple_choice": True, "anonymous": False},
            {"options": 10, "multiple_choice": True, "anonymous": True},
            
            # Edge cases
            {"options": 2, "multiple_choice": True, "anonymous": True},  # Min options with all features
            {"options": 10, "multiple_choice": False, "anonymous": False},  # Max options, basic
        ]
        
        # Test user and guild data
        self.test_user_id = "123456789012345678"
        self.test_guild_id = "987654321098765432"
        self.test_channel_id = "555666777888999000"
        
    def setup_test_data(self):
        """Setup test data - bulletproof operations handle database setup automatically"""
        logger.info("Test data will be created automatically by bulletproof operations")
    
    async def create_poll_with_real_image(self, config: Dict[str, Any], loop_num: int, poll_num: int) -> bool:
        """Create a single poll with a real image"""
        try:
            # Get a random real image
            real_image = self.image_generator.get_random_real_image()
            if not real_image:
                logger.warning("No real image available, skipping poll")
                return False
            
            image_data, image_filename = real_image
            
            # Generate poll data using the same pattern as comprehensive generator
            title = f"Real Image Poll {loop_num}-{poll_num} ({config['options']} options)"
            question = f"Real image test poll with {config['options']} options using {image_filename}"
            
            # Create options
            options = []
            for i in range(config['options']):
                option_text = f"Option {i+1} - Real Image Test"
                options.append(option_text)
            
            # Generate emojis (simple letter emojis)
            letter_emojis = ["🇦", "🇧", "🇨", "🇩", "🇪", "🇫", "🇬", "🇭", "🇮", "🇯"]
            emojis = letter_emojis[:config['options']]
            
            # Generate times
            now = datetime.now(pytz.UTC)
            open_time = now + timedelta(minutes=1)
            close_time = open_time + timedelta(hours=24)
            
            # Create poll data in the format expected by BulletproofPollOperations
            poll_data = {
                "name": title,
                "question": question,
                "options": options,
                "emojis": emojis,
                "server_id": self.test_guild_id,
                "channel_id": self.test_channel_id,
                "open_time": open_time,
                "close_time": close_time,
                "timezone": "UTC",
                "anonymous": config["anonymous"],
                "multiple_choice": config["multiple_choice"],
                "ping_role_enabled": False,
                "ping_role_id": None,
                "creator_id": self.test_user_id
            }
            
            # Get bot instance (may be None in test environment)
            bot = get_bot_instance()
            
            # Create bulletproof poll operations
            bulletproof_ops = BulletproofPollOperations(bot)
            
            # Create the poll using bulletproof operations
            result = await bulletproof_ops.create_bulletproof_poll(
                poll_data=poll_data,
                user_id=self.test_user_id,
                image_file=image_data,
                image_filename=image_filename,
                image_message_text=f"Real image from {image_filename} for poll testing"
            )
            
            if result["success"]:
                poll_id = result["poll_id"]
                self.polls_created += 1
                logger.info(f"✅ Created poll {poll_id}: {title} with image {image_filename}")
                return True
            else:
                error_msg = result.get("error", "Unknown error")
                logger.error(f"❌ Failed to create poll: {error_msg}")
                self.errors += 1
                return False
                    
        except Exception as e:
            logger.error(f"❌ Exception creating poll with real image: {e}")
            self.errors += 1
            return False
    
    async def create_poll_with_specific_image(self, image_path: str, image_index: int) -> bool:
        """Create a single poll with a specific image"""
        try:
            # Read the specific image
            image_filename = os.path.basename(image_path)
            with open(image_path, 'rb') as f:
                image_data = f.read()
            
            # Use a rotating config for variety
            config = self.poll_configs[image_index % len(self.poll_configs)]
            
            # Generate poll data
            title = f"Image Poll {image_index + 1}: {image_filename}"
            question = f"Poll for {image_filename} with {config['options']} options"
            
            # Create options
            options = []
            for i in range(config['options']):
                option_text = f"Option {i+1} for {image_filename}"
                options.append(option_text)
            
            # Generate emojis (simple letter emojis)
            letter_emojis = ["🇦", "🇧", "🇨", "🇩", "🇪", "🇫", "🇬", "🇭", "🇮", "🇯"]
            emojis = letter_emojis[:config['options']]
            
            # Generate times
            now = datetime.now(pytz.UTC)
            open_time = now + timedelta(minutes=1)
            close_time = open_time + timedelta(hours=24)
            
            # Create poll data
            poll_data = {
                "name": title,
                "question": question,
                "options": options,
                "emojis": emojis,
                "server_id": self.test_guild_id,
                "channel_id": self.test_channel_id,
                "open_time": open_time,
                "close_time": close_time,
                "timezone": "UTC",
                "anonymous": config["anonymous"],
                "multiple_choice": config["multiple_choice"],
                "ping_role_enabled": False,
                "ping_role_id": None,
                "creator_id": self.test_user_id
            }
            
            # Get bot instance and create poll
            bot = get_bot_instance()
            bulletproof_ops = BulletproofPollOperations(bot)
            
            result = await bulletproof_ops.create_bulletproof_poll(
                poll_data=poll_data,
                user_id=self.test_user_id,
                image_file=image_data,
                image_filename=image_filename,
                image_message_text=f"Poll using {image_filename}"
            )
            
            if result["success"]:
                poll_id = result["poll_id"]
                self.polls_created += 1
                logger.info(f"✅ Created poll {poll_id} for {image_filename}")
                return True
            else:
                error_msg = result.get("error", "Unknown error")
                logger.error(f"❌ Failed to create poll for {image_filename}: {error_msg}")
                self.errors += 1
                return False
                
        except Exception as e:
            image_filename = os.path.basename(image_path) if 'image_path' in locals() else "unknown"
            logger.error(f"❌ Exception creating poll for {image_filename}: {e}")
            self.errors += 1
            return False

    async def generate_polls_for_all_images(self) -> Dict[str, Any]:
        """Generate a poll for each image in the repository"""
        start_time = datetime.now()
        total_images = len(self.image_generator.real_images_cache)
        logger.info(f"Starting poll generation for all {total_images} images")
        
        for i, image_path in enumerate(self.image_generator.real_images_cache):
            success = await self.create_poll_with_specific_image(image_path, i)
            
            # Progress updates
            if (i + 1) % 100 == 0 or (i + 1) == total_images:
                logger.info(f"Progress: {i + 1}/{total_images} images processed")
            
            # Small delay to avoid overwhelming the system
            await asyncio.sleep(0.05)  # Shorter delay since we have many images
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        result = {
            "success": True,
            "polls_created": self.polls_created,
            "errors": self.errors,
            "total_images": total_images,
            "duration": duration,
            "polls_per_second": self.polls_created / duration if duration > 0 else 0
        }
        
        logger.info(f"All images poll generation completed:")
        logger.info(f"  - Total images: {result['total_images']}")
        logger.info(f"  - Polls created: {result['polls_created']}")
        logger.info(f"  - Errors: {result['errors']}")
        logger.info(f"  - Duration: {result['duration']:.2f} seconds")
        logger.info(f"  - Rate: {result['polls_per_second']:.2f} polls/second")
        
        return result

    async def generate_polls_loop(self, loop_num: int) -> int:
        """Generate polls for one loop iteration"""
        polls_in_loop = 0
        
        logger.info(f"Starting loop {loop_num}/{self.loops}")
        
        for poll_num, config in enumerate(self.poll_configs, 1):
            success = await self.create_poll_with_real_image(config, loop_num, poll_num)
            if success:
                polls_in_loop += 1
            
            # Small delay to avoid overwhelming the system
            await asyncio.sleep(0.1)
        
        logger.info(f"Completed loop {loop_num}: {polls_in_loop} polls created")
        return polls_in_loop
    
    async def generate_all_polls(self) -> Dict[str, Any]:
        """Generate all polls across all loops"""
        start_time = datetime.now()
        logger.info(f"Starting real image poll generation: {self.loops} loops")
        
        # Initialize database
        init_database()
        
        # Setup test data
        self.setup_test_data()
        
        # Check if real images are available
        if not self.image_generator.real_images_cache:
            logger.error("No real images available. Make sure the sample-images repository is accessible.")
            return {
                "success": False,
                "error": "No real images available",
                "polls_created": 0,
                "errors": 0,
                "duration": 0
            }
        
        logger.info(f"Using {len(self.image_generator.real_images_cache)} real images")
        
        # Generate polls for each loop
        for loop_num in range(1, self.loops + 1):
            await self.generate_polls_loop(loop_num)
            
            # Progress update
            if loop_num % 10 == 0 or loop_num == self.loops:
                logger.info(f"Progress: {loop_num}/{self.loops} loops completed")
        
        # Cleanup if requested
        if self.cleanup:
            logger.info("Cleaning up sample-images repository...")
            self.image_generator.cleanup_real_images()
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        result = {
            "success": True,
            "polls_created": self.polls_created,
            "errors": self.errors,
            "loops_completed": self.loops,
            "duration": duration,
            "polls_per_loop": len(self.poll_configs),
            "total_expected": self.loops * len(self.poll_configs),
            "real_images_used": len(self.image_generator.real_images_cache)
        }
        
        logger.info(f"Real image poll generation completed:")
        logger.info(f"  - Polls created: {result['polls_created']}")
        logger.info(f"  - Errors: {result['errors']}")
        logger.info(f"  - Duration: {result['duration']:.2f} seconds")
        logger.info(f"  - Real images available: {result['real_images_used']}")
        
        return result

async def main():
    """Main function to run the real image poll generator"""
    parser = argparse.ArgumentParser(description="Generate polls with real images")
    parser.add_argument("--loops", type=int, default=1, 
                       help="Number of times to loop through all poll configurations (default: 1)")
    parser.add_argument("--no-cleanup", action="store_true", 
                       help="Don't clean up the sample-images repository after completion")
    parser.add_argument("--dry-run", action="store_true", 
                       help="Show what would be created without actually creating polls")
    parser.add_argument("--use-all-images", action="store_true",
                       help="Create a poll for each image in the repository (2000+ polls)")
    
    args = parser.parse_args()
    
    if args.dry_run:
        logger.info("DRY RUN MODE - No polls will be created")
        generator = RealImagePollGenerator(loops=args.loops, cleanup=not args.no_cleanup)
        
        if args.use_all_images:
            # Show what would be created for all images
            total_images = len(generator.image_generator.real_images_cache)
            logger.info(f"Would create {total_images} polls, one for each image")
            logger.info(f"Images available: {total_images}")
            logger.info(f"Poll configurations will rotate through {len(generator.poll_configs)} different configs")
        else:
            # Show what would be created for loops
            total_polls = args.loops * len(generator.poll_configs)
            logger.info(f"Would create {total_polls} polls across {args.loops} loops")
            logger.info(f"Poll configurations per loop: {len(generator.poll_configs)}")
            
            for i, config in enumerate(generator.poll_configs, 1):
                logger.info(f"  Config {i}: {config['options']} options, "
                           f"multiple_choice={config['multiple_choice']}, "
                           f"anonymous={config['anonymous']}")
        
        return
    
    try:
        generator = RealImagePollGenerator(loops=args.loops, cleanup=not args.no_cleanup)
        
        # Initialize database and setup
        init_database()
        generator.setup_test_data()
        
        # Check if real images are available
        if not generator.image_generator.real_images_cache:
            logger.error("No real images available. Make sure the sample-images repository is accessible.")
            print(f"\n❌ No real images available")
            sys.exit(1)
        
        if args.use_all_images:
            # Create a poll for each image
            logger.info(f"Creating polls for all {len(generator.image_generator.real_images_cache)} images")
            result = await generator.generate_polls_for_all_images()
            
            if result["success"]:
                print(f"\n✅ Successfully completed poll generation for all images!")
                print(f"📊 Created {result['polls_created']} polls in {result['duration']:.2f} seconds")
                print(f"🖼️  Processed {result['total_images']} images")
                print(f"⚡ Rate: {result['polls_per_second']:.2f} polls/second")
                
                if result["errors"] > 0:
                    print(f"⚠️  {result['errors']} errors occurred during generation")
            else:
                print(f"\n❌ Poll generation failed")
                sys.exit(1)
        else:
            # Use the standard loop-based generation
            result = await generator.generate_all_polls()
            
            if result["success"]:
                print(f"\n✅ Successfully completed real image poll generation!")
                print(f"📊 Created {result['polls_created']} polls in {result['duration']:.2f} seconds")
                print(f"🔄 Completed {result['loops_completed']} loops")
                print(f"🖼️  Used {result['real_images_used']} real images from sample-images repository")
                
                if result["errors"] > 0:
                    print(f"⚠️  {result['errors']} errors occurred during generation")
            else:
                print(f"\n❌ Poll generation failed: {result.get('error', 'Unknown error')}")
                sys.exit(1)
        
        # Cleanup if requested
        if generator.cleanup:
            logger.info("Cleaning up sample-images repository...")
            generator.image_generator.cleanup_real_images()
            
    except KeyboardInterrupt:
        logger.info("Poll generation interrupted by user")
        print("\n🛑 Poll generation interrupted")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
