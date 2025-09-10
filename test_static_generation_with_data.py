#!/usr/bin/env python3
"""
Test script to check static page generation for closed polls
Creates test data if needed
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta

# Add the project directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from polly.database import get_db_session, Poll, Vote, TypeSafeColumn
from polly.static_page_generator import get_static_page_generator

async def create_test_poll():
    """Create a test closed poll for testing"""
    print("🔧 Creating test closed poll...")
    
    db = get_db_session()
    try:
        # Check if we already have a test poll
        existing_poll = db.query(Poll).filter(Poll.name.like("Test Static Poll%")).first()
        if existing_poll:
            print(f"📊 Found existing test poll: {existing_poll.id}")
            return TypeSafeColumn.get_int(existing_poll, "id")
        
        # Create a new test poll
        test_poll = Poll(
            name="Test Static Poll for Generation",
            question="This is a test poll to verify static page generation works correctly",
            options_json='["Option A", "Option B", "Option C"]',
            emojis_json='["🅰️", "🅱️", "🆎"]',
            server_id="123456789",
            channel_id="987654321",
            creator_id="555666777",
            status="closed",
            created_at=datetime.utcnow() - timedelta(days=2),
            open_time=datetime.utcnow() - timedelta(days=2),
            close_time=datetime.utcnow() - timedelta(hours=1),
            multiple_choice=False,
            max_choices=1,
            anonymous=False,
            open_immediately=True
        )
        
        db.add(test_poll)
        db.flush()  # Get the ID
        
        poll_id = test_poll.id
        print(f"✅ Created test poll with ID: {poll_id}")
        
        # Add some test votes (votes reference option_index, not option_id)
        votes = [
            Vote(poll_id=poll_id, user_id="user1", option_index=0),
            Vote(poll_id=poll_id, user_id="user2", option_index=0),
            Vote(poll_id=poll_id, user_id="user3", option_index=1),
            Vote(poll_id=poll_id, user_id="user4", option_index=2),
            Vote(poll_id=poll_id, user_id="user5", option_index=2),
        ]
        
        for vote in votes:
            db.add(vote)
        
        db.commit()
        print(f"✅ Added {len(test_poll.options)} options and {len(votes)} votes")
        
        return poll_id
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error creating test poll: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        db.close()

async def test_static_generation():
    """Test static page generation for closed polls"""
    print("🔧 Testing static page generation...")
    
    # Create test data if needed
    test_poll_id = await create_test_poll()
    if not test_poll_id:
        print("❌ Failed to create test poll")
        return
    
    # Get database session
    db = get_db_session()
    try:
        # Find the test poll
        test_poll = db.query(Poll).filter(Poll.id == test_poll_id).first()
        if not test_poll:
            print("❌ Test poll not found")
            return
        
        poll_name = TypeSafeColumn.get_string(test_poll, "name", "Unknown Poll")
        print(f"\n🔧 Testing poll {test_poll_id}: '{poll_name}'")
        
        # Get static page generator
        generator = get_static_page_generator()
        
        # Check if static page already exists
        exists = generator.static_page_exists(test_poll_id, "details")
        print(f"📄 Static page exists: {exists}")
        
        # Try to generate static content
        try:
            success = await generator.generate_static_poll_details(test_poll_id)
            print(f"✅ Generation result: {success}")
            
            if success:
                # Check if file was created
                static_path = generator._get_static_page_path(test_poll_id, "details")
                print(f"📁 Static file path: {static_path}")
                print(f"📁 File exists: {static_path.exists()}")
                
                if static_path.exists():
                    file_size = static_path.stat().st_size
                    print(f"📏 File size: {file_size} bytes")
                    
                    # Read first 500 characters to check content
                    with open(static_path, 'r', encoding='utf-8') as f:
                        content_preview = f.read(500)
                    print(f"📄 Content preview:\n{content_preview[:300]}...")
                    
                    # Check for key elements that should be in the static page
                    content_lower = content_preview.lower()
                    checks = [
                        ("poll title", poll_name.lower() in content_lower),
                        ("poll description", "test poll" in content_lower),
                        ("options", "option a" in content_lower or "option b" in content_lower),
                        ("votes", "vote" in content_lower or "result" in content_lower),
                    ]
                    
                    print("\n🔍 Content validation:")
                    for check_name, passed in checks:
                        status = "✅" if passed else "❌"
                        print(f"  {status} {check_name}")
            
        except Exception as e:
            print(f"❌ Error generating static content: {e}")
            import traceback
            traceback.print_exc()
    
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_static_generation())
