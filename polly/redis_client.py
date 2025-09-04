"""
Redis Client Module
Provides Redis connection and caching functionality for Polly.
"""

import json
import logging
from typing import Any, Optional, Dict, List
import redis.asyncio as redis
from redis.exceptions import RedisError, ConnectionError
from decouple import config

logger = logging.getLogger(__name__)


class RedisClient:
    """Redis client wrapper with connection management and caching utilities"""

    def __init__(self):
        self.redis_url = config("REDIS_URL", default="redis://localhost:6379")
        self.redis_host = config("REDIS_HOST", default="localhost")
        self.redis_port = config("REDIS_PORT", default=6379, cast=int)
        self.redis_db = config("REDIS_DB", default=0, cast=int)
        self.redis_password = config("REDIS_PASSWORD", default=None)

        self._client: Optional[redis.Redis] = None
        self._connected = False

    async def connect(self) -> bool:
        """Establish connection to Redis server"""
        try:
            if self.redis_url and self.redis_url != "redis://localhost:6379":
                # Use URL if provided and not default
                self._client = redis.from_url(
                    self.redis_url,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True,
                )
            else:
                # Use individual parameters
                self._client = redis.Redis(
                    host=self.redis_host,
                    port=self.redis_port,
                    db=self.redis_db,
                    password=self.redis_password,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True,
                )

            # Test connection
            await self._client.ping()
            self._connected = True
            logger.info(f"Connected to Redis at {self.redis_host}:{self.redis_port}")
            return True

        except (ConnectionError, RedisError) as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self._connected = False
            return False

    async def disconnect(self):
        """Close Redis connection"""
        if self._client:
            await self._client.aclose()
            self._connected = False
            logger.info("Disconnected from Redis")

    @property
    def is_connected(self) -> bool:
        """Check if Redis is connected"""
        return self._connected and self._client is not None

    async def _ensure_connected(self) -> bool:
        """Ensure Redis connection is active"""
        if not self.is_connected:
            return await self.connect()
        return True

    # Basic Redis operations
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set a key-value pair with optional TTL (in seconds)"""
        if not await self._ensure_connected():
            return False

        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)

            if ttl:
                result = await self._client.setex(key, ttl, value)
            else:
                result = await self._client.set(key, value)

            return bool(result)
        except RedisError as e:
            logger.error(f"Redis SET error for key {key}: {e}")
            return False

    async def get(self, key: str, default: Any = None) -> Any:
        """Get value by key"""
        if not await self._ensure_connected():
            return default

        try:
            value = await self._client.get(key)
            if value is None:
                return default

            # Try to parse as JSON, fallback to string
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value

        except RedisError as e:
            logger.error(f"Redis GET error for key {key}: {e}")
            return default

    async def delete(self, *keys: str) -> int:
        """Delete one or more keys"""
        if not await self._ensure_connected():
            return 0

        try:
            return await self._client.delete(*keys)
        except RedisError as e:
            logger.error(f"Redis DELETE error for keys {keys}: {e}")
            return 0

    async def exists(self, key: str) -> bool:
        """Check if key exists"""
        if not await self._ensure_connected():
            return False

        try:
            return bool(await self._client.exists(key))
        except RedisError as e:
            logger.error(f"Redis EXISTS error for key {key}: {e}")
            return False

    async def expire(self, key: str, ttl: int) -> bool:
        """Set TTL for existing key"""
        if not await self._ensure_connected():
            return False

        try:
            return bool(await self._client.expire(key, ttl))
        except RedisError as e:
            logger.error(f"Redis EXPIRE error for key {key}: {e}")
            return False

    async def ttl(self, key: str) -> int:
        """Get TTL for key (-1 if no expiry, -2 if key doesn't exist)"""
        if not await self._ensure_connected():
            return -2

        try:
            return await self._client.ttl(key)
        except RedisError as e:
            logger.error(f"Redis TTL error for key {key}: {e}")
            return -2

    # Hash operations
    async def hset(self, name: str, mapping: Dict[str, Any]) -> int:
        """Set hash fields"""
        if not await self._ensure_connected():
            return 0

        try:
            # Convert complex values to JSON
            processed_mapping = {}
            for key, value in mapping.items():
                if isinstance(value, (dict, list)):
                    processed_mapping[key] = json.dumps(value)
                else:
                    processed_mapping[key] = str(value)

            return await self._client.hset(name, mapping=processed_mapping)
        except RedisError as e:
            logger.error(f"Redis HSET error for hash {name}: {e}")
            return 0

    async def hget(self, name: str, key: str, default: Any = None) -> Any:
        """Get hash field value"""
        if not await self._ensure_connected():
            return default

        try:
            value = await self._client.hget(name, key)
            if value is None:
                return default

            # Try to parse as JSON, fallback to string
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value

        except RedisError as e:
            logger.error(f"Redis HGET error for hash {name}, key {key}: {e}")
            return default

    async def hgetall(self, name: str) -> Dict[str, Any]:
        """Get all hash fields"""
        if not await self._ensure_connected():
            return {}

        try:
            result = await self._client.hgetall(name)

            # Process values, trying to parse JSON where possible
            processed_result = {}
            for key, value in result.items():
                try:
                    processed_result[key] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    processed_result[key] = value

            return processed_result
        except RedisError as e:
            logger.error(f"Redis HGETALL error for hash {name}: {e}")
            return {}

    async def hdel(self, name: str, *keys: str) -> int:
        """Delete hash fields"""
        if not await self._ensure_connected():
            return 0

        try:
            return await self._client.hdel(name, *keys)
        except RedisError as e:
            logger.error(f"Redis HDEL error for hash {name}, keys {keys}: {e}")
            return 0

    # List operations
    async def lpush(self, name: str, *values: Any) -> int:
        """Push values to left of list"""
        if not await self._ensure_connected():
            return 0

        try:
            processed_values = []
            for value in values:
                if isinstance(value, (dict, list)):
                    processed_values.append(json.dumps(value))
                else:
                    processed_values.append(str(value))

            return await self._client.lpush(name, *processed_values)
        except RedisError as e:
            logger.error(f"Redis LPUSH error for list {name}: {e}")
            return 0

    async def rpush(self, name: str, *values: Any) -> int:
        """Push values to right of list"""
        if not await self._ensure_connected():
            return 0

        try:
            processed_values = []
            for value in values:
                if isinstance(value, (dict, list)):
                    processed_values.append(json.dumps(value))
                else:
                    processed_values.append(str(value))

            return await self._client.rpush(name, *processed_values)
        except RedisError as e:
            logger.error(f"Redis RPUSH error for list {name}: {e}")
            return 0

    async def lrange(self, name: str, start: int = 0, end: int = -1) -> List[Any]:
        """Get list range"""
        if not await self._ensure_connected():
            return []

        try:
            values = await self._client.lrange(name, start, end)

            # Process values, trying to parse JSON where possible
            processed_values = []
            for value in values:
                try:
                    processed_values.append(json.loads(value))
                except (json.JSONDecodeError, TypeError):
                    processed_values.append(value)

            return processed_values
        except RedisError as e:
            logger.error(f"Redis LRANGE error for list {name}: {e}")
            return []

    async def llen(self, name: str) -> int:
        """Get list length"""
        if not await self._ensure_connected():
            return 0

        try:
            return await self._client.llen(name)
        except RedisError as e:
            logger.error(f"Redis LLEN error for list {name}: {e}")
            return 0

    # Cache-specific methods
    async def cache_set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """Cache a value with default 1-hour TTL"""
        cache_key = f"cache:{key}"
        return await self.set(cache_key, value, ttl)

    async def cache_get(self, key: str, default: Any = None) -> Any:
        """Get cached value"""
        cache_key = f"cache:{key}"
        return await self.get(cache_key, default)

    async def cache_delete(self, key: str) -> bool:
        """Delete cached value"""
        cache_key = f"cache:{key}"
        return bool(await self.delete(cache_key))

    async def cache_clear_pattern(self, pattern: str) -> int:
        """Clear cache keys matching pattern"""
        if not await self._ensure_connected():
            return 0

        try:
            cache_pattern = f"cache:{pattern}"
            keys = []
            async for key in self._client.scan_iter(match=cache_pattern):
                keys.append(key)

            if keys:
                return await self.delete(*keys)
            return 0
        except RedisError as e:
            logger.error(f"Redis cache clear pattern error for {pattern}: {e}")
            return 0


# Global Redis client instance
_redis_client: Optional[RedisClient] = None


async def get_redis_client() -> RedisClient:
    """Get or create Redis client instance"""
    global _redis_client

    if _redis_client is None:
        _redis_client = RedisClient()
        await _redis_client.connect()

    return _redis_client


async def close_redis_client():
    """Close Redis client connection"""
    global _redis_client

    if _redis_client:
        await _redis_client.disconnect()
        _redis_client = None
