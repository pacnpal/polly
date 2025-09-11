#!/usr/bin/env python3
"""
Simple test script to regenerate static content for a specific poll
"""

import asyncio
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from polly.static_page_generator import get_static_page_generator
from polly.discord_bot import get_bot_instance
from polly.database import get_db_session, Poll, TypeSafeColumn

async def test_static_generation():
    """Test static generation for a specific poll"""
    
    # Get a closed poll from the database
    db = get_db_session()
    try:
        # Find a closed poll
        closed_poll = db.query(Poll).filter(
            TypeSafeColumn.get_string(Poll.status) == "closed"
        ).first()
        
        if not closed_poll:
            print("❌ No closed polls found in database")
            return
            
        poll_id = closed_poll.id
        print(f"🔍 Testing static generation for poll {poll_id}: {closed_poll.name}")
        
        # Get static page generator
        generator = get_static_page_generator()
        
        # Check current state
        details_exists = generator.static_page_exists(poll_id, "details")
        screenshot_path = generator._get_dashboard_screenshot_path(poll_id)
        screenshot_exists = screenshot_path.exists()
        
        print(f"📄 Current state:")
        print(f"  - Details page exists: {details_exists}")
        print(f"  - Screenshot exists: {screenshot_exists}")
        if screenshot_exists:
            print(f"  - Screenshot path: {screenshot_path}")
        
        # Try to get bot instance
        bot = get_bot_instance()
        print(f"🤖 Bot instance available: {bot is not None}")
        
        # Test screenshot generation specifically
        print(f"\n📸 Testing screenshot generation...")
        screenshot_success = await generator.generate_dashboard_with_screenshot(poll_id, bot)
        print(f"📸 Screenshot generation result: {screenshot_success}")
        
        # Check if screenshot was created
        screenshot_exists_after = screenshot_path.exists()
        print(f"📸 Screenshot exists after generation: {screenshot_exists_after}")
        
        # Test full static content generation
        print(f"\n🔧 Testing full static content generation...")
        results = await generator.generate_all_static_content(poll_id, bot)
        print(f"🔧 Static generation results: {results}")
        
        # Check final state
        details_exists_after = generator.static_page_exists(poll_id, "details")
        screenshot_exists_final = screenshot_path.exists()
        
        print(f"\n✅ Final state:")
        print(f"  - Details page exists: {details_exists_after}")
        print(f"  - Screenshot exists: {screenshot_exists_final}")
        
        if details_exists_after:
            details_path = generator._get_static_page_path(poll_id, "details")
            print(f"  - Details page path: {details_path}")
            
        if screenshot_exists_final:
            print(f"  - Screenshot path: {screenshot_path}")
            print(f"  - Screenshot URL: /static/images/shared/{screenshot_path.name}")
            
    finally:
        db.close()

if __name__ == "__main__":
    print("🚀 Starting static generation test...")
    asyncio.run(test_static_generation())
    print("✅ Test completed!")
