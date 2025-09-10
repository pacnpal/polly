"""
Enhanced Cache Service Module
Provides extended caching functionality with longer TTLs specifically for Discord rate limiting prevention.
"""

import logging
from typing import Any, Optional, Dict, List
from datetime import datetime
from .cache_service import CacheService

logger = logging.getLogger(__name__)


class EnhancedCacheService(CacheService):
    """Enhanced cache service with longer TTLs for Discord rate limiting prevention"""

    def __init__(self):
        super().__init__()
        # Extended TTLs for Discord API rate limiting prevention
        self.guild_emojis_ttl = 3600  # 1 hour for guild emojis (rarely change)
        self.live_results_ttl = 30  # 30 seconds for live poll results
        self.poll_dashboard_ttl = 15  # 15 seconds for poll dashboard data
        self.discord_user_ttl = 1800  # 30 minutes for Discord user data
        self.guild_info_ttl = 1800  # 30 minutes for guild information

    # Guild Emojis Caching (Extended TTL)
    async def cache_guild_emojis_extended(
        self, guild_id: str, emojis: List[Dict[str, Any]]
    ) -> bool:
        """Cache guild emojis with extended TTL to prevent Discord rate limiting"""
        redis_client = await self._get_redis()
        if not redis_client:
            return False

        cache_key = f"guild_emojis_extended:{guild_id}"
        success = await redis_client.cache_set(cache_key, emojis, self.guild_emojis_ttl)

        if success:
            logger.info(
                f"Cached {len(emojis)} emojis for guild {guild_id} with {self.guild_emojis_ttl}s TTL"
            )

        return success

    async def get_cached_guild_emojis_extended(
        self, guild_id: str
    ) -> Optional[List[Dict[str, Any]]]:
        """Get cached guild emojis with extended TTL"""
        redis_client = await self._get_redis()
        if not redis_client:
            return None

        cache_key = f"guild_emojis_extended:{guild_id}"
        cached_emojis = await redis_client.cache_get(cache_key)

        if cached_emojis:
            logger.debug(
                f"Retrieved {len(cached_emojis)} cached emojis for guild {guild_id}"
            )

        return cached_emojis

    # Live Poll Results Caching
    async def cache_live_poll_results(
        self, poll_id: int, results_data: Dict[str, Any]
    ) -> bool:
        """Cache live poll results with short TTL for real-time updates"""
        redis_client = await self._get_redis()
        if not redis_client:
            return False

        cache_key = f"live_poll_results:{poll_id}"
        return await redis_client.cache_set(
            cache_key, results_data, self.live_results_ttl
        )

    async def get_cached_live_poll_results(
        self, poll_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get cached live poll results"""
        redis_client = await self._get_redis()
        if not redis_client:
            return None

        cache_key = f"live_poll_results:{poll_id}"
        return await redis_client.cache_get(cache_key)

    # Poll Dashboard Caching
    async def cache_poll_dashboard(
        self, poll_id: int, dashboard_data: Dict[str, Any]
    ) -> bool:
        """Cache poll dashboard data with moderate TTL"""
        logger.info(
            f"🔍 CACHE DEBUG - Attempting to cache dashboard for poll {poll_id}"
        )
        logger.info(
            f"🔍 CACHE DEBUG - Dashboard data keys: {list(dashboard_data.keys())}"
        )
        logger.info(
            f"🔍 CACHE DEBUG - Dashboard data total_votes: {dashboard_data.get('total_votes', 'NOT_FOUND')}"
        )
        logger.info(
            f"🔍 CACHE DEBUG - Dashboard data unique_voters: {dashboard_data.get('unique_voters', 'NOT_FOUND')}"
        )
        logger.info(
            f"🔍 CACHE DEBUG - Dashboard data results: {dashboard_data.get('results', 'NOT_FOUND')}"
        )
        logger.info(
            f"🔍 CACHE DEBUG - Dashboard data vote_data length: {len(dashboard_data.get('vote_data', []))}"
        )

        redis_client = await self._get_redis()
        if not redis_client:
            logger.error(
                f"🔍 CACHE DEBUG - Redis client not available for poll {poll_id}"
            )
            return False

        cache_key = f"poll_dashboard:{poll_id}"
        logger.info(f"🔍 CACHE DEBUG - Using cache key: {cache_key}")
        logger.info(f"🔍 CACHE DEBUG - Cache TTL: {self.poll_dashboard_ttl} seconds")

        result = await redis_client.cache_set(
            cache_key, dashboard_data, self.poll_dashboard_ttl
        )
        logger.info(f"🔍 CACHE DEBUG - Cache set result for poll {poll_id}: {result}")

        return result

    async def get_cached_poll_dashboard(self, poll_id: int) -> Optional[Dict[str, Any]]:
        """Get cached poll dashboard data"""
        logger.info(
            f"🔍 CACHE DEBUG - Attempting to retrieve cached dashboard for poll {poll_id}"
        )

        redis_client = await self._get_redis()
        if not redis_client:
            logger.error(
                f"🔍 CACHE DEBUG - Redis client not available for poll {poll_id}"
            )
            return None

        cache_key = f"poll_dashboard:{poll_id}"
        logger.info(f"🔍 CACHE DEBUG - Using cache key: {cache_key}")

        cached_data = await redis_client.cache_get(cache_key)

        if cached_data:
            logger.info(f"🔍 CACHE DEBUG - Cache HIT for poll {poll_id}")
            logger.info(
                f"🔍 CACHE DEBUG - Retrieved data keys: {list(cached_data.keys())}"
            )
            logger.info(
                f"🔍 CACHE DEBUG - Retrieved total_votes: {cached_data.get('total_votes', 'NOT_FOUND')}"
            )
            logger.info(
                f"🔍 CACHE DEBUG - Retrieved unique_voters: {cached_data.get('unique_voters', 'NOT_FOUND')}"
            )
            logger.info(
                f"🔍 CACHE DEBUG - Retrieved results: {cached_data.get('results', 'NOT_FOUND')}"
            )
            logger.info(
                f"🔍 CACHE DEBUG - Retrieved vote_data length: {len(cached_data.get('vote_data', []))}"
            )
        else:
            logger.info(f"🔍 CACHE DEBUG - Cache MISS for poll {poll_id}")

        return cached_data

    async def invalidate_poll_dashboard(self, poll_id: int) -> bool:
        """Invalidate cached poll dashboard data"""
        redis_client = await self._get_redis()
        if not redis_client:
            return False

        cache_key = f"poll_dashboard:{poll_id}"
        return await redis_client.cache_delete(cache_key)

    # Discord User Data Caching (Extended TTL)
    async def cache_discord_user(self, user_id: str, user_data: Dict[str, Any]) -> bool:
        """Cache Discord user data with extended TTL"""
        redis_client = await self._get_redis()
        if not redis_client:
            return False

        cache_key = f"discord_user:{user_id}"
        return await redis_client.cache_set(cache_key, user_data, self.discord_user_ttl)

    async def get_cached_discord_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get cached Discord user data"""
        redis_client = await self._get_redis()
        if not redis_client:
            return None

        cache_key = f"discord_user:{user_id}"
        return await redis_client.cache_get(cache_key)

    # Guild Information Caching (Extended TTL)
    async def cache_guild_info(self, guild_id: str, guild_data: Dict[str, Any]) -> bool:
        """Cache guild information with extended TTL"""
        redis_client = await self._get_redis()
        if not redis_client:
            return False

        cache_key = f"guild_info:{guild_id}"
        return await redis_client.cache_set(cache_key, guild_data, self.guild_info_ttl)

    async def get_cached_guild_info(self, guild_id: str) -> Optional[Dict[str, Any]]:
        """Get cached guild information"""
        redis_client = await self._get_redis()
        if not redis_client:
            return None

        cache_key = f"guild_info:{guild_id}"
        return await redis_client.cache_get(cache_key)

    # Bulk Cache Operations for Poll Updates
    async def invalidate_poll_related_cache(self, poll_id: int) -> int:
        """Invalidate all poll-related cached data when poll is updated"""
        redis_client = await self._get_redis()
        if not redis_client:
            return 0

        patterns = [
            f"live_poll_results:{poll_id}",
            f"poll_dashboard:{poll_id}",
            f"poll_results:{poll_id}",  # From base cache service
        ]

        count = 0
        for pattern in patterns:
            if await redis_client.cache_delete(pattern):
                count += 1

        logger.info(
            f"Invalidated {count} poll-related cache entries for poll {poll_id}"
        )
        return count

    # Cache Statistics and Monitoring
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics for monitoring"""
        redis_client = await self._get_redis()
        if not redis_client:
            return {"error": "Redis not available"}

        try:
            # Get cache key counts by pattern
            patterns = {
                "guild_emojis_extended": "guild_emojis_extended:*",
                "live_poll_results": "live_poll_results:*",
                "poll_dashboard": "poll_dashboard:*",
                "discord_user": "discord_user:*",
                "guild_info": "guild_info:*",
            }

            stats = {}
            for name, pattern in patterns.items():
                try:
                    keys = []
                    if redis_client._client:
                        async for key in redis_client._client.scan_iter(
                            match=f"cache:{pattern}"
                        ):
                            keys.append(key)
                    stats[f"{name}_count"] = len(keys)
                except Exception as e:
                    logger.warning(f"Error counting keys for pattern {pattern}: {e}")
                    stats[f"{name}_count"] = 0

            stats["timestamp"] = datetime.now().isoformat()
            return stats

        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {"error": str(e)}

    # Role Ping Caching (Extended TTL for role data)
    async def cache_guild_roles_for_ping(
        self, guild_id: str, roles: List[Dict[str, Any]]
    ) -> bool:
        """Cache guild roles specifically for role ping functionality with extended TTL"""
        redis_client = await self._get_redis()
        if not redis_client:
            return False

        cache_key = f"guild_roles_ping:{guild_id}"
        success = await redis_client.cache_set(cache_key, roles, self.guild_info_ttl)  # 30 minutes

        if success:
            logger.info(
                f"Cached {len(roles)} pingable roles for guild {guild_id} with {self.guild_info_ttl}s TTL"
            )

        return success

    async def get_cached_guild_roles_for_ping(
        self, guild_id: str
    ) -> Optional[List[Dict[str, Any]]]:
        """Get cached guild roles for role ping functionality"""
        redis_client = await self._get_redis()
        if not redis_client:
            return None

        cache_key = f"guild_roles_ping:{guild_id}"
        cached_roles = await redis_client.cache_get(cache_key)

        if cached_roles:
            logger.debug(
                f"Retrieved {len(cached_roles)} cached pingable roles for guild {guild_id}"
            )

        return cached_roles

    async def cache_role_validation(
        self, guild_id: str, role_id: str, can_ping: bool, role_name: Optional[str] = None
    ) -> bool:
        """Cache role ping validation results"""
        redis_client = await self._get_redis()
        if not redis_client:
            return False

        cache_key = f"role_validation:{guild_id}:{role_id}"
        validation_data = {
            "can_ping": can_ping,
            "role_name": role_name or "",
            "cached_at": datetime.now().isoformat(),
        }
        
        return await redis_client.cache_set(cache_key, validation_data, self.guild_info_ttl)  # 30 minutes

    async def get_cached_role_validation(
        self, guild_id: str, role_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get cached role ping validation"""
        redis_client = await self._get_redis()
        if not redis_client:
            return None

        cache_key = f"role_validation:{guild_id}:{role_id}"
        return await redis_client.cache_get(cache_key)

    async def invalidate_guild_roles_cache(self, guild_id: str) -> int:
        """Invalidate all role-related cache for a guild"""
        redis_client = await self._get_redis()
        if not redis_client:
            return 0

        patterns = [
            f"guild_roles:{guild_id}",
            f"guild_roles_ping:{guild_id}",
        ]

        count = 0
        for pattern in patterns:
            if await redis_client.cache_delete(pattern):
                count += 1

        # Also invalidate role validation cache for this guild
        try:
            if redis_client._client:
                async for key in redis_client._client.scan_iter(
                    match=f"cache:role_validation:{guild_id}:*"
                ):
                    if await redis_client._client.delete(key):
                        count += 1
        except Exception as e:
            logger.warning(f"Error invalidating role validation cache for guild {guild_id}: {e}")

        logger.info(f"Invalidated {count} role cache entries for guild {guild_id}")
        return count

    # Cache Warming for Frequently Accessed Data
    async def warm_guild_cache(self, guild_id: str, bot) -> bool:
        """Pre-warm cache with guild data to prevent rate limiting"""
        try:
            # Check if we already have cached data
            cached_emojis = await self.get_cached_guild_emojis_extended(guild_id)
            cached_info = await self.get_cached_guild_info(guild_id)
            cached_roles = await self.get_cached_guild_roles_for_ping(guild_id)

            if cached_emojis and cached_info and cached_roles:
                logger.debug(f"Guild {guild_id} cache already warm")
                return True

            # Fetch and cache guild data
            guild = bot.get_guild(int(guild_id))
            if not guild:
                logger.warning(f"Guild {guild_id} not found for cache warming")
                return False

            # Cache guild info
            if not cached_info:
                guild_data = {
                    "id": guild.id,
                    "name": guild.name,
                    "member_count": guild.member_count,
                    "cached_at": datetime.now().isoformat(),
                }
                await self.cache_guild_info(guild_id, guild_data)

            # Cache guild emojis
            if not cached_emojis:
                emoji_list = []
                for emoji in guild.emojis:
                    try:
                        emoji_data = {
                            "name": emoji.name,
                            "id": emoji.id,
                            "animated": emoji.animated,
                            "url": str(emoji.url),
                            "format": str(emoji),
                            "usable": emoji.is_usable(),
                        }
                        emoji_list.append(emoji_data)
                    except Exception as e:
                        logger.warning(f"Error processing emoji {emoji.name}: {e}")
                        continue

                await self.cache_guild_emojis_extended(guild_id, emoji_list)

            # Cache guild roles for ping functionality
            if not cached_roles:
                # Import here to avoid circular imports
                from .discord_utils import get_guild_roles
                roles = await get_guild_roles(bot, guild_id)
                if roles:
                    await self.cache_guild_roles_for_ping(guild_id, roles)

            logger.info(f"Successfully warmed cache for guild {guild_id}")
            return True

        except Exception as e:
            logger.error(f"Error warming cache for guild {guild_id}: {e}")
            return False


# Global enhanced cache service instance
_enhanced_cache_service: Optional[EnhancedCacheService] = None


def get_enhanced_cache_service() -> EnhancedCacheService:
    """Get or create enhanced cache service instance"""
    global _enhanced_cache_service

    if _enhanced_cache_service is None:
        _enhanced_cache_service = EnhancedCacheService()

    return _enhanced_cache_service
