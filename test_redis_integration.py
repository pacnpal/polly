#!/usr/bin/env python3
"""
Test script to verify Redis integration in Polly
"""

import asyncio
import sys
import os
from datetime import datetime

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from polly.redis_client import get_redis_client, close_redis_client
from polly.cache_service import get_cache_service


async def test_redis_connection():
    """Test basic Redis connection"""
    print("Testing Redis connection...")

    try:
        redis_client = await get_redis_client()

        if redis_client.is_connected:
            print("✅ Redis connection successful")
            return True
        else:
            print("❌ Redis connection failed")
            return False

    except Exception as e:
        print(f"❌ Redis connection error: {e}")
        return False


async def test_basic_operations():
    """Test basic Redis operations"""
    print("\nTesting basic Redis operations...")

    try:
        redis_client = await get_redis_client()

        # Test SET and GET
        test_key = "test_key"
        test_value = {
            "message": "Hello Redis!",
            "timestamp": datetime.now().isoformat(),
        }

        # Set value
        set_result = await redis_client.set(test_key, test_value, ttl=60)
        if not set_result:
            print("❌ Failed to set test key")
            return False
        print("✅ SET operation successful")

        # Get value
        get_result = await redis_client.get(test_key)
        if get_result != test_value:
            print(f"❌ GET operation failed. Expected: {test_value}, Got: {get_result}")
            return False
        print("✅ GET operation successful")

        # Test TTL
        ttl_result = await redis_client.ttl(test_key)
        if ttl_result <= 0:
            print(f"❌ TTL operation failed. Got: {ttl_result}")
            return False
        print(f"✅ TTL operation successful. TTL: {ttl_result} seconds")

        # Test DELETE
        delete_result = await redis_client.delete(test_key)
        if delete_result != 1:
            print(f"❌ DELETE operation failed. Expected: 1, Got: {delete_result}")
            return False
        print("✅ DELETE operation successful")

        return True

    except Exception as e:
        print(f"❌ Basic operations error: {e}")
        return False


async def test_cache_service():
    """Test cache service functionality"""
    print("\nTesting cache service...")

    try:
        cache_service = get_cache_service()

        # Test user preferences caching
        user_id = "test_user_123"
        test_prefs = {
            "last_server_id": "server_123",
            "last_channel_id": "channel_456",
            "default_timezone": "US/Eastern",
            "timezone_explicitly_set": True,
        }

        # Cache user preferences
        cache_result = await cache_service.cache_user_preferences(user_id, test_prefs)
        if not cache_result:
            print("❌ Failed to cache user preferences")
            return False
        print("✅ User preferences cached successfully")

        # Retrieve cached preferences
        cached_prefs = await cache_service.get_cached_user_preferences(user_id)
        if cached_prefs != test_prefs:
            print(
                f"❌ Failed to retrieve cached preferences. Expected: {test_prefs}, Got: {cached_prefs}"
            )
            return False
        print("✅ User preferences retrieved from cache successfully")

        # Test cache invalidation
        invalidate_result = await cache_service.invalidate_user_preferences(user_id)
        if not invalidate_result:
            print("❌ Failed to invalidate user preferences cache")
            return False
        print("✅ User preferences cache invalidated successfully")

        # Verify cache was invalidated
        cached_prefs_after = await cache_service.get_cached_user_preferences(user_id)
        if cached_prefs_after is not None:
            print(f"❌ Cache invalidation failed. Still got: {cached_prefs_after}")
            return False
        print("✅ Cache invalidation verified")

        return True

    except Exception as e:
        print(f"❌ Cache service error: {e}")
        return False


async def test_health_check():
    """Test cache service health check"""
    print("\nTesting cache service health check...")

    try:
        cache_service = get_cache_service()
        health_result = await cache_service.health_check()

        print(f"Health check result: {health_result}")

        if health_result.get("status") == "healthy":
            print("✅ Cache service health check passed")
            return True
        else:
            print(f"❌ Cache service health check failed: {health_result}")
            return False

    except Exception as e:
        print(f"❌ Health check error: {e}")
        return False


async def main():
    """Run all Redis integration tests"""
    print("🚀 Starting Redis integration tests for Polly\n")

    tests = [
        ("Redis Connection", test_redis_connection),
        ("Basic Operations", test_basic_operations),
        ("Cache Service", test_cache_service),
        ("Health Check", test_health_check),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"{'=' * 50}")
        print(f"Running: {test_name}")
        print(f"{'=' * 50}")

        try:
            result = await test_func()
            if result:
                passed += 1
                print(f"✅ {test_name} PASSED")
            else:
                print(f"❌ {test_name} FAILED")
        except Exception as e:
            print(f"❌ {test_name} FAILED with exception: {e}")

        print()

    # Cleanup
    try:
        await close_redis_client()
        print("🧹 Redis client closed")
    except Exception as e:
        print(f"⚠️  Error closing Redis client: {e}")

    # Summary
    print(f"{'=' * 50}")
    print("TEST SUMMARY")
    print(f"{'=' * 50}")
    print(f"Passed: {passed}/{total}")
    print(f"Failed: {total - passed}/{total}")

    if passed == total:
        print("🎉 All tests passed! Redis integration is working correctly.")
        return 0
    else:
        print("❌ Some tests failed. Please check your Redis configuration.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
