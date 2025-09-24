"""
Enhanced Cache Service Module
Provides extended caching functionality with longer TTLs specifically for Discord rate limiting prevention.
"""

import logging
from typing import Any, Optional, Dict, List
from datetime import datetime, timedelta
try:
    from .cache_service import CacheService
except ImportError:
    from cache_service import CacheService  # type: ignore

logger = logging.getLogger(__name__)


class EnhancedCacheService(CacheService):
    """Enhanced cache service with longer TTLs for Discord rate limiting prevention"""

    def __init__(self):
        super().__init__()
        # Extended TTLs for Discord API rate limiting prevention
        self.guild_emojis_ttl = 3600  # 1 hour for guild emojis (rarely change)
        self.live_results_ttl = (
            10  # 10 seconds for live poll results (matches polling interval)
        )
        self.poll_dashboard_ttl = (
            10  # 10 seconds for poll dashboard data (matches polling interval)
        )
        # Maximum TTL for static/closed poll data that never changes
        self.static_poll_results_ttl = 86400 * 7  # 7 days for closed/inactive polls
        self.static_poll_dashboard_ttl = 86400 * 7  # 7 days for closed poll dashboards
        self.discord_user_ttl = 1800  # 30 minutes for Discord user data
        self.guild_info_ttl = 1800  # 30 minutes for guild information

    def _get_poll_cache_ttl(self, poll_status: str, cache_type: str = "results") -> int:
        """Get appropriate cache TTL based on poll status
        
        Args:
            poll_status: Poll status ('scheduled', 'active', 'closed')
            cache_type: Type of cache ('results' or 'dashboard')
            
        Returns:
            TTL in seconds
        """
        if poll_status == "closed":
            # Closed polls are static - use maximum TTL
            if cache_type == "dashboard":
                return self.static_poll_dashboard_ttl
            else:
                return self.static_poll_results_ttl
        else:
            # Active or scheduled polls need frequent updates
            if cache_type == "dashboard":
                return self.poll_dashboard_ttl
            else:
                return self.live_results_ttl

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
        self, poll_id: int, results_data: Dict[str, Any], poll_status: str = "active"
    ) -> bool:
        """Cache live poll results with status-aware TTL (short for active, long for closed)"""
        redis_client = await self._get_redis()
        if not redis_client:
            return False

        # Use status-aware TTL
        ttl = self._get_poll_cache_ttl(poll_status, "results")
        cache_key = f"live_poll_results:{poll_id}"
        
        success = await redis_client.cache_set(cache_key, results_data, ttl)
        
        if success:
            logger.info(
                f"Cached poll results for poll {poll_id} (status: {poll_status}) with {ttl}s TTL"
            )
        
        return success

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
        self, poll_id: int, dashboard_data: Dict[str, Any], poll_status: str = "active"
    ) -> bool:
        """Cache poll dashboard data with status-aware TTL (short for active, long for closed)"""
        logger.info(
            f"🔍 CACHE DEBUG - Attempting to cache dashboard for poll {poll_id} (status: {poll_status})"
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

        # Use status-aware TTL
        ttl = self._get_poll_cache_ttl(poll_status, "dashboard")
        cache_key = f"poll_dashboard:{poll_id}"
        logger.info(f"🔍 CACHE DEBUG - Using cache key: {cache_key}")
        logger.info(f"🔍 CACHE DEBUG - Cache TTL: {ttl} seconds (status: {poll_status})")

        result = await redis_client.cache_set(cache_key, dashboard_data, ttl)
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

        try:
            cached_data = await redis_client.cache_get(cache_key)
        except Exception as e:
            logger.warning(f"🔍 CACHE DEBUG - Error retrieving cache for poll {poll_id}: {e}")
            # Clear corrupted cache entry
            await self.invalidate_poll_dashboard(poll_id)
            return None

        if cached_data:
            logger.info(f"🔍 CACHE DEBUG - Cache HIT for poll {poll_id}")
            
            # Sanitize retrieved data to handle any HTML entities that might cause issues
            try:
                from .data_utils import sanitize_data_for_json
                sanitized_data = sanitize_data_for_json(cached_data)
                logger.info(
                    f"🔍 CACHE DEBUG - Retrieved data keys: {list(sanitized_data.keys())}"
                )
                logger.info(
                    f"🔍 CACHE DEBUG - Retrieved total_votes: {sanitized_data.get('total_votes', 'NOT_FOUND')}"
                )
                logger.info(
                    f"🔍 CACHE DEBUG - Retrieved unique_voters: {sanitized_data.get('unique_voters', 'NOT_FOUND')}"
                )
                logger.info(
                    f"🔍 CACHE DEBUG - Retrieved results: {sanitized_data.get('results', 'NOT_FOUND')}"
                )
                logger.info(
                    f"🔍 CACHE DEBUG - Retrieved vote_data length: {len(sanitized_data.get('vote_data', []))}"
                )
                return sanitized_data
            except Exception as e:
                logger.warning(f"🔍 CACHE DEBUG - Error sanitizing cached data for poll {poll_id}: {e}")
                # Clear corrupted cache entry and return None to force fresh data generation
                await self.invalidate_poll_dashboard(poll_id)
                return None
        else:
            logger.info(f"🔍 CACHE DEBUG - Cache MISS for poll {poll_id}")

        return None

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
        try:
            cached_data = await redis_client.cache_get(cache_key)
            if cached_data:
                # Sanitize retrieved data to handle any HTML entities
                from .data_utils import sanitize_data_for_json
                return sanitize_data_for_json(cached_data)
            return cached_data
        except Exception as e:
            logger.warning(f"Error retrieving cached Discord user {user_id}: {e}")
            # Clear corrupted cache entry
            await redis_client.cache_delete(f"discord_user:{user_id}")
            return None

    # Avatar Caching with Deduplication and Space Optimization
    async def cache_avatar_metadata(self, user_id: str, avatar_data: Dict[str, Any]) -> bool:
        """
        Cache avatar metadata with deduplication support
        
        Args:
            user_id: Discord user ID
            avatar_data: Dictionary containing:
                - avatar_url: Original Discord avatar URL
                - avatar_hash: Discord avatar hash for deduplication
                - cached_path: Local cached file path (if downloaded)
                - file_size: File size in bytes
                - format: Image format (webp, png, jpg, gif)
                - last_modified: Last modification timestamp
        """
        redis_client = await self._get_redis()
        if not redis_client:
            return False

        cache_key = f"avatar_metadata:{user_id}"
        
        # Add caching timestamp
        avatar_data["cached_at"] = datetime.now().isoformat()
        
        # Cache with extended TTL (avatars don't change frequently)
        return await redis_client.cache_set(cache_key, avatar_data, self.discord_user_ttl)

    async def get_cached_avatar_metadata(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get cached avatar metadata"""
        redis_client = await self._get_redis()
        if not redis_client:
            return None

        cache_key = f"avatar_metadata:{user_id}"
        try:
            cached_data = await redis_client.cache_get(cache_key)
            if cached_data:
                from .data_utils import sanitize_data_for_json
                return sanitize_data_for_json(cached_data)
            return cached_data
        except Exception as e:
            logger.warning(f"Error retrieving cached avatar metadata for user {user_id}: {e}")
            await redis_client.cache_delete(cache_key)
            return None

    async def cache_avatar_hash_mapping(self, avatar_hash: str, file_info: Dict[str, Any]) -> bool:
        """
        Cache avatar hash to file mapping for deduplication
        
        Args:
            avatar_hash: Discord avatar hash (used for deduplication)
            file_info: Dictionary containing:
                - local_path: Local file path
                - file_size: File size in bytes
                - format: Image format
                - users: List of user IDs using this avatar
                - created_at: When this mapping was created
        """
        redis_client = await self._get_redis()
        if not redis_client:
            return False

        cache_key = f"avatar_hash:{avatar_hash}"
        
        # Add creation timestamp
        file_info["created_at"] = datetime.now().isoformat()
        
        # Cache with longer TTL since hash mappings are more stable
        return await redis_client.cache_set(cache_key, file_info, self.discord_user_ttl * 2)  # 1 hour

    async def get_cached_avatar_hash_mapping(self, avatar_hash: str) -> Optional[Dict[str, Any]]:
        """Get cached avatar hash mapping"""
        redis_client = await self._get_redis()
        if not redis_client:
            return None

        cache_key = f"avatar_hash:{avatar_hash}"
        try:
            return await redis_client.cache_get(cache_key)
        except Exception as e:
            logger.warning(f"Error retrieving avatar hash mapping for {avatar_hash}: {e}")
            await redis_client.cache_delete(cache_key)
            return None

    async def add_user_to_avatar_hash(self, avatar_hash: str, user_id: str) -> bool:
        """Add a user ID to an existing avatar hash mapping"""
        hash_mapping = await self.get_cached_avatar_hash_mapping(avatar_hash)
        if not hash_mapping:
            return False

        users = hash_mapping.get("users", [])
        if user_id not in users:
            users.append(user_id)
            hash_mapping["users"] = users
            hash_mapping["updated_at"] = datetime.now().isoformat()
            
            return await self.cache_avatar_hash_mapping(avatar_hash, hash_mapping)
        
        return True  # User already in list

    async def remove_user_from_avatar_hash(self, avatar_hash: str, user_id: str) -> bool:
        """Remove a user ID from an avatar hash mapping"""
        hash_mapping = await self.get_cached_avatar_hash_mapping(avatar_hash)
        if not hash_mapping:
            return False

        users = hash_mapping.get("users", [])
        if user_id in users:
            users.remove(user_id)
            hash_mapping["users"] = users
            hash_mapping["updated_at"] = datetime.now().isoformat()
            
            # If no users left, we could delete the mapping, but keep it for a while
            # in case the avatar is used again soon
            return await self.cache_avatar_hash_mapping(avatar_hash, hash_mapping)
        
        return True  # User wasn't in list anyway

    async def get_avatar_storage_stats(self) -> Dict[str, Any]:
        """Get comprehensive avatar storage statistics"""
        redis_client = await self._get_redis()
        if not redis_client:
            return {"error": "Redis not available"}

        stats = {
            "total_cached_users": 0,
            "total_unique_avatars": 0,
            "total_storage_bytes": 0,
            "deduplication_savings": 0,
            "format_breakdown": {},
            "cache_hit_potential": 0.0,
            "timestamp": datetime.now().isoformat()
        }

        try:
            # Count cached avatar metadata
            avatar_metadata_keys = []
            if redis_client._client:
                async for key in redis_client._client.scan_iter(match="cache:avatar_metadata:*"):
                    avatar_metadata_keys.append(key)
            
            stats["total_cached_users"] = len(avatar_metadata_keys)

            # Count unique avatar hashes
            avatar_hash_keys = []
            if redis_client._client:
                async for key in redis_client._client.scan_iter(match="cache:avatar_hash:*"):
                    avatar_hash_keys.append(key)
            
            stats["total_unique_avatars"] = len(avatar_hash_keys)

            # Calculate storage and deduplication stats
            total_file_size = 0
            total_logical_size = 0  # What size would be without deduplication
            format_counts = {}

            for key in avatar_hash_keys:
                try:
                    hash_data = await redis_client._client.get(key)
                    if hash_data:
                        import json
                        hash_info = json.loads(hash_data)
                        
                        file_size = hash_info.get("file_size", 0)
                        users_count = len(hash_info.get("users", []))
                        format_type = hash_info.get("format", "unknown")
                        
                        total_file_size += file_size
                        total_logical_size += file_size * users_count  # Size if each user had separate file
                        
                        format_counts[format_type] = format_counts.get(format_type, 0) + 1
                        
                except Exception as e:
                    logger.warning(f"Error processing avatar hash key {key}: {e}")
                    continue

            stats["total_storage_bytes"] = total_file_size
            stats["deduplication_savings"] = total_logical_size - total_file_size
            stats["format_breakdown"] = format_counts
            
            # Calculate cache hit potential (percentage of users with cached avatars)
            if stats["total_cached_users"] > 0:
                stats["cache_hit_potential"] = min(100.0, (stats["total_cached_users"] / max(1, stats["total_unique_avatars"])) * 100)

            logger.info(f"📊 AVATAR STATS - Users: {stats['total_cached_users']}, Unique: {stats['total_unique_avatars']}, Storage: {stats['total_storage_bytes']/1024/1024:.1f}MB, Savings: {stats['deduplication_savings']/1024/1024:.1f}MB")

        except Exception as e:
            logger.error(f"Error gathering avatar storage stats: {e}")
            stats["error"] = str(e)

        return stats

    async def cleanup_orphaned_avatars(self, max_age_hours: int = 24) -> Dict[str, int]:
        """
        Clean up avatar files that are no longer referenced by any users
        
        Args:
            max_age_hours: Maximum age in hours for orphaned avatars before cleanup
            
        Returns:
            Dictionary with cleanup statistics
        """
        redis_client = await self._get_redis()
        if not redis_client:
            return {"error": "Redis not available"}

        cleanup_stats = {
            "orphaned_hashes_found": 0,
            "orphaned_hashes_cleaned": 0,
            "storage_freed_bytes": 0,
            "errors": 0
        }

        try:
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
            
            # Get all avatar hash mappings
            avatar_hash_keys = []
            if redis_client._client:
                async for key in redis_client._client.scan_iter(match="cache:avatar_hash:*"):
                    avatar_hash_keys.append(key)

            for key in avatar_hash_keys:
                try:
                    hash_data = await redis_client._client.get(key)
                    if not hash_data:
                        continue
                        
                    import json
                    hash_info = json.loads(hash_data)
                    
                    users = hash_info.get("users", [])
                    created_at_str = hash_info.get("created_at")
                    updated_at_str = hash_info.get("updated_at", created_at_str)
                    
                    # Check if this hash has no users and is old enough
                    if len(users) == 0 and updated_at_str:
                        try:
                            updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                            if updated_at < cutoff_time:
                                cleanup_stats["orphaned_hashes_found"] += 1
                                
                                # Delete the hash mapping
                                file_size = hash_info.get("file_size", 0)
                                if await redis_client._client.delete(key):
                                    cleanup_stats["orphaned_hashes_cleaned"] += 1
                                    cleanup_stats["storage_freed_bytes"] += file_size
                                    
                                    # Also try to delete the actual file if path is provided
                                    local_path = hash_info.get("local_path")
                                    if local_path:
                                        try:
                                            from pathlib import Path
                                            file_path = Path(local_path)
                                            if file_path.exists():
                                                file_path.unlink()
                                                logger.info(f"🧹 AVATAR CLEANUP - Deleted orphaned avatar file: {local_path}")
                                        except Exception as file_error:
                                            logger.warning(f"Error deleting orphaned avatar file {local_path}: {file_error}")
                                            cleanup_stats["errors"] += 1
                        except ValueError as date_error:
                            logger.warning(f"Error parsing date for avatar hash cleanup: {date_error}")
                            cleanup_stats["errors"] += 1
                            
                except Exception as e:
                    logger.warning(f"Error processing avatar hash for cleanup {key}: {e}")
                    cleanup_stats["errors"] += 1
                    continue

            logger.info(f"🧹 AVATAR CLEANUP - Found {cleanup_stats['orphaned_hashes_found']} orphaned, cleaned {cleanup_stats['orphaned_hashes_cleaned']}, freed {cleanup_stats['storage_freed_bytes']/1024/1024:.1f}MB")

        except Exception as e:
            logger.error(f"Error during avatar cleanup: {e}")
            cleanup_stats["error"] = str(e)

        return cleanup_stats

    async def invalidate_user_avatar_cache(self, user_id: str) -> bool:
        """Invalidate all avatar-related cache for a specific user"""
        redis_client = await self._get_redis()
        if not redis_client:
            return False

        try:
            # Get user's current avatar metadata to find hash
            avatar_metadata = await self.get_cached_avatar_metadata(user_id)
            
            # Delete user's avatar metadata
            await redis_client.cache_delete(f"avatar_metadata:{user_id}")
            
            # Remove user from avatar hash mapping if exists
            if avatar_metadata and "avatar_hash" in avatar_metadata:
                avatar_hash = avatar_metadata["avatar_hash"]
                await self.remove_user_from_avatar_hash(avatar_hash, user_id)
            
            logger.info(f"🧹 AVATAR CACHE - Invalidated avatar cache for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error invalidating avatar cache for user {user_id}: {e}")
            return False

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
        success = await redis_client.cache_set(
            cache_key, roles, self.guild_info_ttl
        )  # 30 minutes

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
        self,
        guild_id: str,
        role_id: str,
        can_ping: bool,
        role_name: Optional[str] = None,
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

        return await redis_client.cache_set(
            cache_key, validation_data, self.guild_info_ttl
        )  # 30 minutes

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
            logger.warning(
                f"Error invalidating role validation cache for guild {guild_id}: {e}"
            )

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
