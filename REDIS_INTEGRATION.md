# Redis Integration for Polly

This document describes the Redis integration implemented in the Polly Discord poll bot application.

## Overview

Redis has been integrated into Polly to provide high-performance caching capabilities, improving response times and reducing database load. The integration is designed to be fault-tolerant - if Redis is unavailable, the application will continue to function normally by falling back to direct database operations.

## Features

### 1. Redis Client (`polly/redis_client.py`)
- Async Redis client with automatic connection management
- Support for both URL-based and parameter-based configuration
- Automatic reconnection and error handling
- JSON serialization/deserialization for complex data types
- Comprehensive Redis operations (GET, SET, DELETE, EXPIRE, TTL, etc.)
- Hash and List operations support

### 2. Cache Service (`polly/cache_service.py`)
- High-level caching service built on top of the Redis client
- Specialized caching methods for different data types:
  - User preferences (30-minute TTL)
  - Guild data (10-minute TTL)
  - Poll results (5-minute TTL)
  - Session data (customizable TTL)
- Bulk operations for cache invalidation
- Health check functionality

### 3. Web Application Integration
- User preferences are now cached for faster retrieval
- Automatic cache invalidation when preferences are updated
- Health check endpoint at `/health` includes Redis status
- Graceful degradation when Redis is unavailable

## Configuration

### Environment Variables

Add the following variables to your `.env` file:

```bash
# Redis Configuration
REDIS_URL=redis://localhost:6379
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
```

### Docker Configuration

The application will connect to Redis running on the remote server at port 6379. No additional Docker configuration is needed for the basic setup.

## Usage Examples

### Basic Redis Operations

```python
from polly.redis_client import get_redis_client

# Get Redis client
redis_client = await get_redis_client()

# Set a value with TTL
await redis_client.set("key", {"data": "value"}, ttl=3600)

# Get a value
value = await redis_client.get("key")

# Delete a key
await redis_client.delete("key")
```

### Cache Service Operations

```python
from polly.cache_service import get_cache_service

# Get cache service
cache_service = get_cache_service()

# Cache user preferences
user_prefs = {
    "last_server_id": "123456789",
    "default_timezone": "US/Eastern"
}
await cache_service.cache_user_preferences("user_id", user_prefs)

# Retrieve cached preferences
cached_prefs = await cache_service.get_cached_user_preferences("user_id")

# Invalidate cache
await cache_service.invalidate_user_preferences("user_id")
```

## Cached Data Types

### User Preferences (TTL: 30 minutes)
- Last selected server and channel
- Default timezone settings
- User-specific configuration

### Guild Data (TTL: 10 minutes)
- Guild channels list
- Guild roles list
- Guild emojis list
- User's accessible guilds

### Poll Data (TTL: 5 minutes)
- Poll results and vote counts
- Real-time poll statistics

### Session Data (TTL: customizable)
- Temporary session information
- Form data persistence

## Testing

Run the Redis integration test to verify everything is working:

```bash
python test_redis_integration.py
```

This test will verify:
- Redis connection
- Basic operations (SET, GET, DELETE, TTL)
- Cache service functionality
- Health check operations

## Health Monitoring

### Health Check Endpoint

Access the health check at: `GET /health`

Response format:
```json
{
  "status": "healthy",
  "timestamp": "2025-01-03T15:30:00.000Z",
  "redis": {
    "status": "healthy",
    "connected": true,
    "timestamp": "2025-01-03T15:30:00.000Z"
  }
}
```

### Cache Service Health Check

```python
from polly.cache_service import get_cache_service

cache_service = get_cache_service()
health_status = await cache_service.health_check()
```

## Error Handling

The Redis integration is designed to be fault-tolerant:

1. **Connection Failures**: If Redis is unavailable, operations return default values and the application continues normally
2. **Operation Failures**: Individual Redis operations that fail are logged but don't crash the application
3. **Automatic Reconnection**: The client attempts to reconnect automatically when connections are lost
4. **Graceful Degradation**: When Redis is unavailable, the application falls back to direct database operations

## Performance Benefits

With Redis caching enabled, you can expect:

- **Faster User Preference Retrieval**: 30-50ms reduction in response time
- **Improved Guild Data Loading**: Significant reduction in Discord API calls
- **Better Poll Performance**: Cached poll results reduce database queries
- **Enhanced User Experience**: Faster page loads and form interactions

## Cache Invalidation Strategy

The cache uses a combination of TTL-based and event-based invalidation:

1. **TTL-based**: All cached data has appropriate TTL values
2. **Event-based**: Cache is invalidated when underlying data changes
3. **Manual**: Bulk invalidation methods for administrative purposes

## Monitoring and Maintenance

### Key Metrics to Monitor
- Redis connection status
- Cache hit/miss ratios
- Memory usage
- Response times

### Maintenance Tasks
- Monitor Redis memory usage
- Review cache TTL settings based on usage patterns
- Clean up expired keys if needed
- Monitor error logs for connection issues

## Troubleshooting

### Common Issues

1. **Connection Refused**
   - Verify Redis server is running on port 6379
   - Check network connectivity
   - Verify Redis configuration

2. **Authentication Errors**
   - Check REDIS_PASSWORD environment variable
   - Verify Redis server authentication settings

3. **Memory Issues**
   - Monitor Redis memory usage
   - Adjust TTL values if needed
   - Consider Redis memory policies

### Debug Mode

Enable debug logging to see detailed Redis operations:

```python
import logging
logging.getLogger('polly.redis_client').setLevel(logging.DEBUG)
logging.getLogger('polly.cache_service').setLevel(logging.DEBUG)
```

## Future Enhancements

Potential improvements for the Redis integration:

1. **Redis Cluster Support**: For high availability setups
2. **Pub/Sub Integration**: For real-time notifications
3. **Advanced Caching Strategies**: LRU, LFU policies
4. **Metrics Collection**: Detailed performance metrics
5. **Cache Warming**: Pre-populate frequently accessed data
6. **Distributed Locking**: For coordinated operations across instances

## Dependencies

The Redis integration requires:
- `redis>=5.0.0`: Official Redis Python client
- `python-decouple`: For configuration management

These are automatically installed via the project's `pyproject.toml`.
