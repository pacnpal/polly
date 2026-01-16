#!/usr/bin/env python3
"""
Test script for the unified poll opening service
Tests all the integration points we've updated
"""

import asyncio
import logging
from datetime import datetime, timedelta
import pytz

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_unified_opening_service():
    """Test the unified poll opening service integration"""
    
    print("🧪 TESTING UNIFIED POLL OPENING SERVICE")
    print("=" * 50)
    
    try:
        # Test 1: Import the unified opening service
        print("\n1. Testing service import...")
        from polly.poll_open_service import poll_opening_service
        print("✅ Successfully imported poll_opening_service")
        
        # Test 2: Check service methods
        print("\n2. Testing service methods...")
        methods = ['open_poll_unified', 'post_poll_to_discord', 'update_poll_message', 'add_poll_reactions']
        for method in methods:
            if hasattr(poll_opening_service, method):
                print(f"✅ Method {method} exists")
            else:
                print(f"❌ Method {method} missing")
        
        # Test 3: Test background_tasks integration
        print("\n3. Testing background_tasks integration...")
        try:
            from polly.background_tasks import open_poll_scheduled
            print("✅ Successfully imported updated open_poll_scheduled")
        except ImportError as e:
            print(f"❌ Failed to import open_poll_scheduled: {e}")
        
        # Test 4: Test super_admin integration
        print("\n4. Testing super_admin integration...")
        try:
            from polly.super_admin import SuperAdminService
            service = SuperAdminService()
            if hasattr(service, 'reopen_poll'):
                print("✅ SuperAdminService.reopen_poll method exists")
            else:
                print("❌ SuperAdminService.reopen_poll method missing")
        except ImportError as e:
            print(f"❌ Failed to import SuperAdminService: {e}")
        
        # Test 5: Test htmx_endpoints integration
        print("\n5. Testing htmx_endpoints integration...")
        try:
            # Check if the file contains the unified service import
            with open('polly/htmx_endpoints.py', 'r') as f:
                content = f.read()
                if 'poll_opening_service' in content:
                    print("✅ htmx_endpoints.py contains poll_opening_service reference")
                else:
                    print("❌ htmx_endpoints.py does not contain poll_opening_service reference")
        except Exception as e:
            print(f"❌ Failed to check htmx_endpoints.py: {e}")
        
        print("\n" + "=" * 50)
        print("🧪 TESTING COMPLETE")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        logger.exception("Test failed")


if __name__ == "__main__":
    asyncio.run(test_unified_opening_service())
