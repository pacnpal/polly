"""
Cache Service Module
Provides caching functionality using Redis for frequently accessed data.
"""

import logging
from typing import Any, Optional, Dict, List
from datetime import datetime
try:
    from .redis_client import get_redis_client
except ImportError:
    from redis_client import get_redis_client  # type: ignore

logger = logging.getLogger(__name__)


class CacheService:
    """Service for caching frequently accessed data"""

    def __init__(self):
        self.default_ttl = 3600  # 1 hour default TTL
        self.user_prefs_ttl = 1800  # 30 minutes for user preferences
        self.guild_data_ttl = 600  # 10 minutes for guild data
        self.poll_data_ttl = 300  # 5 minutes for poll data

    async def _get_redis(self):
        """Get Redis client instance"""
        try:
            return await get_redis_client()
        except Exception as e:
            logger.error(f"Failed to get Redis client: {e}")
            return None

    # User Preferences Caching
    async def cache_user_preferences(
        self, user_id: str, preferences: Dict[str, Any]
    ) -> bool:
        """Cache user preferences"""
        redis_client = await self._get_redis()
        if not redis_client:
            return False

        cache_key = f"user_prefs:{user_id}"
        return await redis_client.cache_set(cache_key, preferences, self.user_prefs_ttl)

    async def get_cached_user_preferences(
        self, user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get cached user preferences"""
        redis_client = await self._get_redis()
        if not redis_client:
            return None

        cache_key = f"user_prefs:{user_id}"
        return await redis_client.cache_get(cache_key)

    async def invalidate_user_preferences(self, user_id: str) -> bool:
        """Invalidate cached user preferences"""
        redis_client = await self._get_redis()
        if not redis_client:
            return False

        cache_key = f"user_prefs:{user_id}"
        return await redis_client.cache_delete(cache_key)

    # Guild Data Caching
    async def cache_user_guilds(
        self, user_id: str, guilds: List[Dict[str, Any]]
    ) -> bool:
        """Cache user's guild data"""
        redis_client = await self._get_redis()
        if not redis_client:
            return False

        cache_key = f"user_guilds:{user_id}"
        return await redis_client.cache_set(cache_key, guilds, self.guild_data_ttl)

    async def get_cached_user_guilds(
        self, user_id: str
    ) -> Optional[List[Dict[str, Any]]]:
        """Get cached user guild data"""
        redis_client = await self._get_redis()
        if not redis_client:
            return None

        cache_key = f"user_guilds:{user_id}"
        return await redis_client.cache_get(cache_key)

    async def invalidate_user_guilds(self, user_id: str) -> bool:
        """Invalidate cached user guild data"""
        redis_client = await self._get_redis()
        if not redis_client:
            return False

        cache_key = f"user_guilds:{user_id}"
        return await redis_client.cache_delete(cache_key)

    # Guild Channels Caching
    async def cache_guild_channels(
        self, guild_id: str, channels: List[Dict[str, Any]]
    ) -> bool:
        """Cache guild channels"""
        redis_client = await self._get_redis()
        if not redis_client:
            return False

        cache_key = f"guild_channels:{guild_id}"
        return await redis_client.cache_set(cache_key, channels, self.guild_data_ttl)

    async def get_cached_guild_channels(
        self, guild_id: str
    ) -> Optional[List[Dict[str, Any]]]:
        """Get cached guild channels"""
        redis_client = await self._get_redis()
        if not redis_client:
            return None

        cache_key = f"guild_channels:{guild_id}"
        return await redis_client.cache_get(cache_key)

    async def invalidate_guild_channels(self, guild_id: str) -> bool:
        """Invalidate cached guild channels"""
        redis_client = await self._get_redis()
        if not redis_client:
            return False

        cache_key = f"guild_channels:{guild_id}"
        return await redis_client.cache_delete(cache_key)

    # Guild Roles Caching
    async def cache_guild_roles(
        self, guild_id: str, roles: List[Dict[str, Any]]
    ) -> bool:
        """Cache guild roles"""
        redis_client = await self._get_redis()
        if not redis_client:
            return False

        cache_key = f"guild_roles:{guild_id}"
        return await redis_client.cache_set(cache_key, roles, self.guild_data_ttl)

    async def get_cached_guild_roles(
        self, guild_id: str
    ) -> Optional[List[Dict[str, Any]]]:
        """Get cached guild roles"""
        redis_client = await self._get_redis()
        if not redis_client:
            return None

        cache_key = f"guild_roles:{guild_id}"
        return await redis_client.cache_get(cache_key)

    async def invalidate_guild_roles(self, guild_id: str) -> bool:
        """Invalidate cached guild roles"""
        redis_client = await self._get_redis()
        if not redis_client:
            return False

        cache_key = f"guild_roles:{guild_id}"
        return await redis_client.cache_delete(cache_key)

    # Guild Emojis Caching
    async def cache_guild_emojis(
        self, guild_id: str, emojis: List[Dict[str, Any]]
    ) -> bool:
        """Cache guild emojis"""
        redis_client = await self._get_redis()
        if not redis_client:
            return False

        cache_key = f"guild_emojis:{guild_id}"
        return await redis_client.cache_set(cache_key, emojis, self.guild_data_ttl)

    async def get_cached_guild_emojis(
        self, guild_id: str
    ) -> Optional[List[Dict[str, Any]]]:
        """Get cached guild emojis"""
        redis_client = await self._get_redis()
        if not redis_client:
            return None

        cache_key = f"guild_emojis:{guild_id}"
        return await redis_client.cache_get(cache_key)

    async def invalidate_guild_emojis(self, guild_id: str) -> bool:
        """Invalidate cached guild emojis"""
        redis_client = await self._get_redis()
        if not redis_client:
            return False

        cache_key = f"guild_emojis:{guild_id}"
        return await redis_client.cache_delete(cache_key)

    # Poll Data Caching
    async def cache_poll_results(self, poll_id: int, results: Dict[str, Any]) -> bool:
        """Cache poll results for faster retrieval"""
        redis_client = await self._get_redis()
        if not redis_client:
            return False

        cache_key = f"poll_results:{poll_id}"
        return await redis_client.cache_set(cache_key, results, self.poll_data_ttl)

    # Static Content Caching
    async def cache_static_page_status(self, poll_id: int, has_static: bool) -> bool:
        """Cache whether a poll has static content available"""
        redis_client = await self._get_redis()
        if not redis_client:
            return False

        cache_key = f"static_page:{poll_id}"
        # Cache for 7 days since closed polls don't change
        return await redis_client.cache_set(cache_key, {"has_static": has_static}, 604800)

    async def get_cached_static_page_status(self, poll_id: int) -> Optional[bool]:
        """Get cached static page availability status"""
        redis_client = await self._get_redis()
        if not redis_client:
            return None

        cache_key = f"static_page:{poll_id}"
        result = await redis_client.cache_get(cache_key)
        return result.get("has_static") if result else None

    async def invalidate_static_page_status(self, poll_id: int) -> bool:
        """Invalidate cached static page status"""
        redis_client = await self._get_redis()
        if not redis_client:
            return False

        cache_key = f"static_page:{poll_id}"
        return await redis_client.cache_delete(cache_key)

    async def cache_closed_poll_results(self, poll_id: int, results: Dict[str, Any]) -> bool:
        """Cache closed poll results with extended TTL (7 days)"""
        redis_client = await self._get_redis()
        if not redis_client:
            return False

        cache_key = f"closed_poll_results:{poll_id}"
        # 7 days TTL for closed polls since they don't change
        return await redis_client.cache_set(cache_key, results, 604800)

    async def get_cached_closed_poll_results(self, poll_id: int) -> Optional[Dict[str, Any]]:
        """Get cached closed poll results"""
        redis_client = await self._get_redis()
        if not redis_client:
            return None

        cache_key = f"closed_poll_results:{poll_id}"
        return await redis_client.cache_get(cache_key)

    async def get_cached_poll_results(self, poll_id: int) -> Optional[Dict[str, Any]]:
        """Get cached poll results"""
        redis_client = await self._get_redis()
        if not redis_client:
            return None

        cache_key = f"poll_results:{poll_id}"
        return await redis_client.cache_get(cache_key)

    async def invalidate_poll_results(self, poll_id: int) -> bool:
        """Invalidate cached poll results"""
        redis_client = await self._get_redis()
        if not redis_client:
            return False

        cache_key = f"poll_results:{poll_id}"
        return await redis_client.cache_delete(cache_key)

    # User Stats Caching
    async def cache_user_stats(self, user_id: str, stats: Dict[str, Any]) -> bool:
        """Cache user statistics"""
        redis_client = await self._get_redis()
        if not redis_client:
            return False

        cache_key = f"user_stats:{user_id}"
        return await redis_client.cache_set(cache_key, stats, self.default_ttl)

    async def get_cached_user_stats(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get cached user statistics"""
        redis_client = await self._get_redis()
        if not redis_client:
            return None

        cache_key = f"user_stats:{user_id}"
        return await redis_client.cache_get(cache_key)

    async def invalidate_user_stats(self, user_id: str) -> bool:
        """Invalidate cached user statistics"""
        redis_client = await self._get_redis()
        if not redis_client:
            return False

        cache_key = f"user_stats:{user_id}"
        return await redis_client.cache_delete(cache_key)

    # Session Data Caching
    async def cache_session_data(
        self, session_id: str, data: Dict[str, Any], ttl: int = 1800
    ) -> bool:
        """Cache session data with custom TTL"""
        redis_client = await self._get_redis()
        if not redis_client:
            return False

        cache_key = f"session:{session_id}"
        return await redis_client.cache_set(cache_key, data, ttl)

    async def get_cached_session_data(
        self, session_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get cached session data"""
        redis_client = await self._get_redis()
        if not redis_client:
            return None

        cache_key = f"session:{session_id}"
        return await redis_client.cache_get(cache_key)

    async def invalidate_session_data(self, session_id: str) -> bool:
        """Invalidate cached session data"""
        redis_client = await self._get_redis()
        if not redis_client:
            return False

        cache_key = f"session:{session_id}"
        return await redis_client.cache_delete(cache_key)

    # Bulk Operations
    async def invalidate_user_cache(self, user_id: str) -> int:
        """Invalidate all cached data for a user"""
        redis_client = await self._get_redis()
        if not redis_client:
            return 0

        patterns = [
            f"user_prefs:{user_id}",
            f"user_guilds:{user_id}",
            f"user_stats:{user_id}",
        ]

        count = 0
        for pattern in patterns:
            if await redis_client.cache_delete(pattern):
                count += 1

        return count

    async def invalidate_guild_cache(self, guild_id: str) -> int:
        """Invalidate all cached data for a guild"""
        redis_client = await self._get_redis()
        if not redis_client:
            return 0

        patterns = [
            f"guild_channels:{guild_id}",
            f"guild_roles:{guild_id}",
            f"guild_emojis:{guild_id}",
        ]

        count = 0
        for pattern in patterns:
            if await redis_client.cache_delete(pattern):
                count += 1

        return count

    async def clear_all_cache(self) -> int:
        """Clear all cache data (use with caution)"""
        redis_client = await self._get_redis()
        if not redis_client:
            return 0

        return await redis_client.cache_clear_pattern("*")

    # Health Check
    async def health_check(self) -> Dict[str, Any]:
        """Check Redis connection and cache health"""
        redis_client = await self._get_redis()
        if not redis_client:
            return {
                "status": "unhealthy",
                "connected": False,
                "error": "Redis client unavailable",
            }

        try:
            # Test basic operations
            test_key = "health_check_test"
            test_value = {"timestamp": datetime.now().isoformat()}

            # Test set
            set_result = await redis_client.cache_set(test_key, test_value, 60)
            if not set_result:
                return {
                    "status": "unhealthy",
                    "connected": True,
                    "error": "Failed to set test key",
                }

            # Test get
            get_result = await redis_client.cache_get(test_key)
            if get_result != test_value:
                return {
                    "status": "unhealthy",
                    "connected": True,
                    "error": "Failed to retrieve test key",
                }

            # Test delete
            delete_result = await redis_client.cache_delete(test_key)
            if not delete_result:
                return {
                    "status": "unhealthy",
                    "connected": True,
                    "error": "Failed to delete test key",
                }

            return {
                "status": "healthy",
                "connected": True,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            return {
                "status": "unhealthy",
                "connected": redis_client.is_connected,
                "error": str(e),
            }


# Global cache service instance
_cache_service: Optional[CacheService] = None


def get_cache_service() -> CacheService:
    """Get or create cache service instance"""
    global _cache_service

    if _cache_service is None:
        _cache_service = CacheService()

    return _cache_service
