#!/usr/bin/env python3
"""
Force regenerate all static poll components for closed polls
"""

import asyncio
import sys
import os
from datetime import datetime

# Add the project directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from polly.database import get_db_session, Poll, TypeSafeColumn
from polly.static_page_generator import get_static_page_generator
from polly.discord_bot import get_bot_instance

async def force_regenerate_all_static():
    """Force regenerate static components for all closed polls"""
    print("🔧 FORCE REGENERATE - Starting regeneration of all static poll components...")
    
    db = get_db_session()
    try:
        # Find all closed polls
        closed_polls = db.query(Poll).filter(Poll.status == "closed").all()
        print(f"📊 FORCE REGENERATE - Found {len(closed_polls)} closed polls")
        
        if not closed_polls:
            print("⚠️ FORCE REGENERATE - No closed polls found")
            return
        
        # Get Discord bot for username fetching
        bot = get_bot_instance()
        bot_status = "ready" if bot and hasattr(bot, "is_ready") and bot.is_ready() else "not ready"
        print(f"🤖 DEBUG - Bot status: {bot_status}")
        if bot:
            print("🤖 FORCE REGENERATE - Discord bot available for username fetching")
        else:
            print("⚠️ FORCE REGENERATE - Discord bot not available, usernames will be generic")
        
        # Get static page generator
        generator = get_static_page_generator()
        
        success_count = 0
        error_count = 0
        
        # Process each closed poll
        for poll in closed_polls:
            poll_id = TypeSafeColumn.get_int(poll, "id")
            poll_name = TypeSafeColumn.get_string(poll, "name", "Unknown Poll")
            
            print(f"\n🔧 FORCE REGENERATE - Processing poll {poll_id}: '{poll_name}'")
            
            try:
                # Force regenerate all static content with image compression and real usernames
                results = await generator.generate_all_static_content(poll_id, bot)
                print(f"🔧 DEBUG - About to generate static content for poll {poll_id} with bot: {bool(bot)}")
                
                if all(results.values()):
                    print(f"✅ FORCE REGENERATE - Successfully generated all static content for poll {poll_id}")
                    success_count += 1
                    
                    # Verify the files were created
                    static_path = generator._get_static_page_path(poll_id, "details")
                    data_path = generator._get_static_data_path(poll_id)
                    
                    if static_path.exists():
                        file_size = static_path.stat().st_size
                        print(f"📁 FORCE REGENERATE - Static HTML created: {static_path} ({file_size} bytes)")
                        
                        # Check content preview
                        with open(static_path, 'r', encoding='utf-8') as f:
                            content = f.read(200)
                        
                        # Verify it's a component (not full HTML document)
                        if content.strip().startswith('<!-- Static Poll Details Component'):
                            print(f"✅ FORCE REGENERATE - Verified component format for poll {poll_id}")
                        else:
                            print(f"⚠️ FORCE REGENERATE - Warning: poll {poll_id} may not be in component format")
                    else:
                        print(f"❌ FORCE REGENERATE - Static HTML file not found after generation for poll {poll_id}")
                        error_count += 1
                        
                    if data_path.exists():
                        data_size = data_path.stat().st_size
                        print(f"📁 FORCE REGENERATE - Static JSON created: {data_path} ({data_size} bytes)")
                    else:
                        print(f"❌ FORCE REGENERATE - Static JSON file not found after generation for poll {poll_id}")
                        
                    # Show image processing results
                    if results.get("details_page"):
                        print(f"🖼️ FORCE REGENERATE - Images processed and compressed for poll {poll_id}")
                else:
                    failed_components = [k for k, v in results.items() if not v]
                    print(f"❌ FORCE REGENERATE - Failed to generate some static content for poll {poll_id}: {failed_components}")
                    error_count += 1
                    
            except Exception as e:
                print(f"❌ FORCE REGENERATE - Error processing poll {poll_id}: {e}")
                error_count += 1
                import traceback
                traceback.print_exc()
        
        print("\n📊 FORCE REGENERATE - Summary:")
        print(f"✅ Successfully processed: {success_count} polls")
        print(f"❌ Errors: {error_count} polls")
        print(f"📊 Total closed polls: {len(closed_polls)}")
        
        # Get image storage statistics
        if success_count > 0:
            try:
                image_stats = await generator.get_image_storage_stats()
                print("\n🖼️ IMAGE COMPRESSION - Statistics:")
                print(f"📊 Total storage: {image_stats['total_storage_mb']:.1f}MB")
                print(f"🔗 Shared images: {image_stats['shared_images']['count']} files ({image_stats['shared_images']['total_size_mb']:.1f}MB)")
                print(f"📁 Poll-specific images: {image_stats['poll_specific_images']['count']} files ({image_stats['poll_specific_images']['total_size_mb']:.1f}MB)")
                print(f"♻️ Deduplication: {'Enabled' if image_stats['deduplication_enabled'] else 'Disabled'}")
                print(f"📏 Max image size: {image_stats['max_image_size_mb']}MB")
                
                if image_stats['shared_images']['formats']:
                    print(f"🎨 Image formats: {', '.join(f'{ext}({count})' for ext, count in image_stats['shared_images']['formats'].items())}")
                    
            except Exception as e:
                print(f"⚠️ IMAGE COMPRESSION - Could not get statistics: {e}")
            
            print(f"\n🎉 FORCE REGENERATE - Successfully regenerated {success_count} static poll components with image compression!")
        
        if error_count > 0:
            print(f"\n⚠️ FORCE REGENERATE - {error_count} polls had errors during regeneration")
            
    finally:
        db.close()

async def test_component_loading():
    """Test that the HTMX endpoint properly loads static components"""
    print("\n🔍 COMPONENT TEST - Testing HTMX endpoint component loading...")
    
    db = get_db_session()
    try:
        # Find a closed poll to test with
        test_poll = db.query(Poll).filter(Poll.status == "closed").first()
        
        if not test_poll:
            print("⚠️ COMPONENT TEST - No closed polls available for testing")
            return
            
        poll_id = TypeSafeColumn.get_int(test_poll, "id")
        poll_name = TypeSafeColumn.get_string(test_poll, "name", "Unknown Poll")
        
        print(f"🔍 COMPONENT TEST - Testing with poll {poll_id}: '{poll_name}'")
        
        # Check if static component exists
        generator = get_static_page_generator()
        static_path = generator._get_static_page_path(poll_id, "details")
        
        if not static_path.exists():
            print(f"❌ COMPONENT TEST - Static component not found for poll {poll_id}")
            return
            
        print(f"✅ COMPONENT TEST - Static component exists: {static_path}")
        
        # Read and analyze the component
        with open(static_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        print(f"📏 COMPONENT TEST - Component size: {len(content)} characters")
        
        # Check for key component elements
        checks = [
            ("Component header", "<!-- Static Poll Details Component" in content),
            ("Container structure", '<div class="container-fluid">' in content),
            ("Poll card", '<div class="card">' in content),
            ("Dashboard container", '<div id="poll-dashboard-container">' in content),
            ("Progress bars", 'data-width=' in content),
            ("JavaScript", '<script>' in content),
            ("HTMX attributes", 'hx-get=' in content),
        ]
        
        print("\n🔍 COMPONENT TEST - Component validation:")
        all_passed = True
        for check_name, passed in checks:
            status = "✅" if passed else "❌"
            print(f"  {status} {check_name}")
            if not passed:
                all_passed = False
                
        if all_passed:
            print(f"\n🎉 COMPONENT TEST - All component checks passed for poll {poll_id}!")
        else:
            print(f"\n⚠️ COMPONENT TEST - Some component checks failed for poll {poll_id}")
            
        # Show content preview
        lines = content.split('\n')
        print("\n📄 COMPONENT TEST - Content preview (first 10 lines):")
        for i, line in enumerate(lines[:10]):
            print(f"  {i+1:2d}: {line[:80]}{'...' if len(line) > 80 else ''}")
            
    finally:
        db.close()

if __name__ == "__main__":
    print("🚀 FORCE REGENERATE SCRIPT - Starting...")
    print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Run the regeneration
    asyncio.run(force_regenerate_all_static())
    
    # Test component loading
    asyncio.run(test_component_loading())
    
    print(f"\n✅ FORCE REGENERATE SCRIPT - Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
