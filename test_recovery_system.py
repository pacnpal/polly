"""
Test script to verify the recovery system implementation
"""

import asyncio
import logging
from decouple import config
from polly.recovery_manager import RecoveryManager, get_recovery_manager
from polly.discord_bot import get_bot_instance

DISCORD_TOKEN = config("DISCORD_TOKEN")
# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_recovery_system():
    """Test the recovery system functionality"""
    print("🔄 Testing Recovery System")
    print("=" * 50)
    
    # Test 1: Recovery Manager Creation
    print("1. Testing Recovery Manager Creation...")
    try:
        # This should work without a bot instance
        recovery_manager = get_recovery_manager()
        if recovery_manager is None:
            print("✅ Recovery manager correctly returns None without bot")
        else:
            print("❌ Recovery manager should be None without bot")
    except Exception as e:
        print(f"❌ Error testing recovery manager creation: {e}")
    
    # Test 2: Recovery Stats
    print("\n2. Testing Recovery Stats...")
    try:
        recovery_manager = get_recovery_manager()
        if recovery_manager:
            stats = recovery_manager.get_recovery_stats()
            print(f"✅ Recovery stats: {stats}")
        else:
            print("✅ No recovery manager available (expected without bot)")
    except Exception as e:
        print(f"❌ Error getting recovery stats: {e}")
    
    # Test 3: Import Verification
    print("\n3. Testing Import Verification...")
    try:
        from polly.recovery_manager import perform_startup_recovery, recover_poll
        print("✅ Recovery functions imported successfully")
    except ImportError as e:
        print(f"❌ Import error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    
    # Test 4: Admin Endpoints Import
    print("\n4. Testing Admin Endpoints...")
    try:
        from polly.admin_endpoints import manual_full_recovery, recover_specific_poll, get_recovery_stats
        print("✅ Admin recovery endpoints imported successfully")
    except ImportError as e:
        print(f"❌ Admin endpoints import error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    
    print("\n" + "=" * 50)
    print("🎉 Recovery System Test Complete")
    print("\nNote: Full functionality testing requires a running Discord bot.")
    print("The recovery system will automatically activate on bot startup.")

if __name__ == "__main__":
    asyncio.run(test_recovery_system())
