#!/usr/bin/env python3
"""
Test script to verify Redis integration in Docker environment
This script tests the Redis connection using Docker Compose configuration
"""

import asyncio
import sys
import os
from datetime import datetime

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from polly.redis_client import get_redis_client, close_redis_client
from polly.cache_service import get_cache_service


async def test_docker_redis_connection():
    """Test Redis connection with Docker configuration"""
    print("Testing Redis connection with Docker configuration...")
    print("Expected Redis URL: redis://:polly_redis_pass@redis:6379")
    print("External port: 6340")

    try:
        redis_client = await get_redis_client()

        if redis_client.is_connected:
            print("✅ Redis connection successful")

            # Test authentication
            try:
                # Try a simple operation to verify auth works
                await redis_client.set("docker_test", "connection_verified", ttl=10)
                result = await redis_client.get("docker_test")
                if result == "connection_verified":
                    print("✅ Redis authentication successful")
                    await redis_client.delete("docker_test")
                    return True
                else:
                    print("❌ Redis authentication test failed")
                    return False
            except Exception as auth_error:
                print(f"❌ Redis authentication error: {auth_error}")
                return False
        else:
            print("❌ Redis connection failed")
            return False

    except Exception as e:
        print(f"❌ Redis connection error: {e}")
        print("Make sure Docker Compose is running: docker-compose up -d")
        return False


async def test_docker_environment():
    """Test Docker environment variables"""
    print("\nTesting Docker environment configuration...")

    redis_url = os.getenv("REDIS_URL", "Not set")
    redis_host = os.getenv("REDIS_HOST", "Not set")
    redis_port = os.getenv("REDIS_PORT", "Not set")
    redis_password = os.getenv("REDIS_PASSWORD", "Not set")

    print(f"REDIS_URL: {redis_url}")
    print(f"REDIS_HOST: {redis_host}")
    print(f"REDIS_PORT: {redis_port}")
    print(f"REDIS_PASSWORD: {'***' if redis_password != 'Not set' else 'Not set'}")

    # Check if we're likely running in Docker
    if redis_host == "redis" and redis_port == "6379":
        print("✅ Docker environment variables detected")
        return True
    elif redis_host == "localhost" and redis_port == "6340":
        print("✅ Local development environment detected")
        return True
    else:
        print("⚠️  Environment variables may not be configured for Docker")
        return True  # Don't fail the test for this


async def test_cache_operations_docker():
    """Test cache operations in Docker environment"""
    print("\nTesting cache operations in Docker environment...")

    try:
        cache_service = get_cache_service()

        # Test with Docker-specific data
        docker_test_data = {
            "environment": "docker",
            "container": "polly-app",
            "redis_container": "polly-redis",
            "timestamp": datetime.now().isoformat(),
        }

        # Test caching
        cache_key = "docker_integration_test"
        cache_result = await cache_service.cache_set(cache_key, docker_test_data, 60)
        if not cache_result:
            print("❌ Failed to cache Docker test data")
            return False
        print("✅ Docker test data cached successfully")

        # Test retrieval
        cached_data = await cache_service.cache_get(cache_key)
        if cached_data != docker_test_data:
            print(
                f"❌ Failed to retrieve Docker test data. Expected: {docker_test_data}, Got: {cached_data}"
            )
            return False
        print("✅ Docker test data retrieved successfully")

        # Test cleanup
        cleanup_result = await cache_service.cache_delete(cache_key)
        if not cleanup_result:
            print("❌ Failed to cleanup Docker test data")
            return False
        print("✅ Docker test data cleaned up successfully")

        return True

    except Exception as e:
        print(f"❌ Docker cache operations error: {e}")
        return False


async def test_health_endpoint_simulation():
    """Simulate health endpoint test"""
    print("\nTesting health check functionality...")

    try:
        cache_service = get_cache_service()
        health_result = await cache_service.health_check()

        print(f"Health check result: {health_result}")

        if health_result.get("status") == "healthy":
            print("✅ Health check passed - Redis is healthy")
            print("✅ /health endpoint should return Redis status")
            return True
        else:
            print(f"❌ Health check failed: {health_result}")
            return False

    except Exception as e:
        print(f"❌ Health check error: {e}")
        return False


async def main():
    """Run Docker-specific Redis integration tests"""
    print("🐳 Starting Redis integration tests for Docker environment\n")

    tests = [
        ("Docker Environment Check", test_docker_environment),
        ("Docker Redis Connection", test_docker_redis_connection),
        ("Docker Cache Operations", test_cache_operations_docker),
        ("Health Check Simulation", test_health_endpoint_simulation),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"{'=' * 60}")
        print(f"Running: {test_name}")
        print(f"{'=' * 60}")

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
    print(f"{'=' * 60}")
    print("DOCKER TEST SUMMARY")
    print(f"{'=' * 60}")
    print(f"Passed: {passed}/{total}")
    print(f"Failed: {total - passed}/{total}")

    if passed == total:
        print("🎉 All Docker tests passed! Redis integration is working correctly.")
        print("\n📋 Next steps:")
        print("1. Start the stack: docker-compose up -d")
        print("2. Check health: curl http://localhost:8000/health")
        print("3. View logs: docker-compose logs -f")
        return 0
    else:
        print("❌ Some Docker tests failed. Check your configuration.")
        print("\n🔧 Troubleshooting:")
        print("1. Ensure Docker Compose is running: docker-compose up -d")
        print("2. Check Redis container: docker-compose logs redis")
        print("3. Verify environment variables in .env file")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
