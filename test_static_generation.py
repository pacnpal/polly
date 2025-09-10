#!/usr/bin/env python3
"""
Test script to check static page generation for closed polls
"""

import asyncio
import sys
import os

# Add the project directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from polly.database import get_db_session, Poll, TypeSafeColumn
from polly.static_page_generator import get_static_page_generator

async def test_static_generation():
    """Test static page generation for closed polls"""
    print("🔧 Testing static page generation...")
    
    # Get database session
    db = get_db_session()
    try:
        # Find closed polls
        closed_polls = db.query(Poll).filter(Poll.status == "closed").all()
        print(f"📊 Found {len(closed_polls)} closed polls")
        
        if not closed_polls:
            print("⚠️ No closed polls found to test with")
            return
        
        # Get static page generator
        generator = get_static_page_generator()
        
        # Test generation for each closed poll
        for poll in closed_polls:
            poll_id = TypeSafeColumn.get_int(poll, "id")
            poll_name = TypeSafeColumn.get_string(poll, "name", "Unknown Poll")
            
            print(f"\n🔧 Testing poll {poll_id}: '{poll_name}'")
            
            # Check if static page already exists
            exists = generator.static_page_exists(poll_id, "details")
            print(f"📄 Static page exists: {exists}")
            
            # Try to generate static content
            try:
                success = await generator.generate_static_poll_details(poll_id)
                print(f"✅ Generation result: {success}")
                
                if success:
                    # Check if file was created
                    static_path = generator._get_static_page_path(poll_id, "details")
                    print(f"📁 Static file path: {static_path}")
                    print(f"📁 File exists: {static_path.exists()}")
                    
                    if static_path.exists():
                        file_size = static_path.stat().st_size
                        print(f"📏 File size: {file_size} bytes")
                        
                        # Read first 200 characters to check content
                        with open(static_path, 'r', encoding='utf-8') as f:
                            content_preview = f.read(200)
                        print(f"📄 Content preview: {content_preview[:100]}...")
                
            except Exception as e:
                print(f"❌ Error generating static content: {e}")
                import traceback
                traceback.print_exc()
    
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_static_generation())
