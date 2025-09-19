# Memory Optimization Implementation Plan

## Completed Work

### ✅ Analysis Phase
1. **Memory Issues Identified**:
   - Global dictionaries growing indefinitely in `background_tasks.py`
   - No database connection pooling limits
   - Missing memory monitoring capabilities
   - Potential Discord API retry accumulation

2. **Best Practices Documentation**:
   - Created comprehensive guide with Memray, Scalene, and pytest-memray
   - Documented automatic tools with `uv run` usage
   - Identified memory optimization patterns

### ✅ Implementation Phase
1. **Created Memory Utilities**: [`polly/memory_utils.py`](polly/memory_utils.py)
   - `cleanup_global_dict()` - Prevents dictionary memory leaks
   - `force_garbage_collection()` - Manual GC triggering
   - `reset_counter_dict()` - Counter reset functionality
   - `cleanup_background_tasks_memory()` - Specific background tasks cleanup

2. **Enhanced Database Module**: [`polly/enhanced_database.py`](polly/enhanced_database.py)
   - Connection pooling with configurable limits
   - Database monitoring and cleanup utilities
   - Context manager for automatic session cleanup
   - Memory optimization functions

3. **Advanced Memory Monitor**: [`polly/memory_optimizer.py`](polly/memory_optimizer.py)
   - Real-time memory monitoring with psutil
   - Memory profiling decorators
   - Checkpoint comparison system
   - Global dictionary cleaning utilities

## Integration Strategy

### Phase 1: Basic Integration
1. **Add memory cleanup to background tasks**:
   ```python
   # In background_tasks.py cleanup_polls_with_deleted_messages()
   from .memory_utils import cleanup_background_tasks_memory
   
   # Add at start of function:
   cleanup_background_tasks_memory()
   ```

2. **Integrate memory monitoring**:
   ```python
   # In critical functions
   from .memory_utils import memory_cleanup_decorator
   
   @memory_cleanup_decorator()
   async def cleanup_polls_with_deleted_messages():
       # Function implementation
   ```

### Phase 2: Advanced Monitoring
1. **Add automatic profiling tools**:
   ```bash
   uv add --dev scalene pytest-memray memray psutil
   ```

2. **Configure pytest memory testing**:
   ```ini
   # pytest.ini
   [tool:pytest]
   addopts = --memray --fail-on-increase
   ```

3. **Add memory monitoring endpoints** to web app for production monitoring

### Phase 3: Production Deployment
1. **Environment configuration**:
   ```env
   DB_POOL_SIZE=10
   DB_MAX_OVERFLOW=20
   DB_POOL_RECYCLE=3600
   MEMORY_MONITORING=true
   ```

2. **Periodic cleanup scheduling**:
   - Add memory cleanup to scheduler jobs
   - Monitor memory usage trends
   - Alert on memory threshold breaches

## Immediate Benefits

### Memory Leak Prevention
- **Global dictionaries**: Limited to 1000 entries with 60-minute aging
- **Database connections**: Pooled with automatic recycling
- **Background tasks**: Automatic cleanup on startup

### Monitoring Capabilities
- **Real-time tracking**: Memory usage per function
- **Pool monitoring**: Database connection status
- **Regression testing**: Automated memory limit testing

### Performance Improvements
- **Connection reuse**: Database connection pooling
- **Garbage collection**: Forced cleanup at strategic points
- **Resource management**: Automatic cleanup decorators

## Testing Strategy

### Unit Tests
```python
import pytest
from polly.memory_utils import cleanup_global_dict

@pytest.mark.limit_memory("10 MB")
def test_memory_cleanup():
    # Test memory cleanup functions
    large_dict = {i: {"data": "x" * 1000} for i in range(10000)}
    removed = cleanup_global_dict(large_dict, max_size=100)
    assert removed > 0
    assert len(large_dict) <= 100
```

### Integration Tests
```bash
# Profile memory usage during tests
uv run pytest --memray tests/

# Run with memory limits
uv run pytest --memray --fail-on-increase tests/
```

### Production Monitoring
```python
# Add to web app health check
from polly.memory_optimizer import get_memory_stats

@app.get("/health/memory")
async def memory_health():
    return get_memory_stats()
```

## Configuration Options

### Environment Variables
```env
# Database Connection Pool
DB_POOL_SIZE=10              # Number of connections to maintain
DB_MAX_OVERFLOW=20           # Additional connections allowed
DB_POOL_RECYCLE=3600         # Seconds before connection refresh

# Memory Management
MAX_FAILURE_ENTRIES=1000     # Max entries in failure tracking
FAILURE_CLEANUP_AGE=60       # Minutes before cleanup
MEMORY_MONITORING=true       # Enable memory monitoring

# Development
DB_ECHO=false               # Log SQL queries (dev only)
```

### Runtime Configuration
```python
# Adjust cleanup parameters
cleanup_global_dict(
    my_dict,
    max_size=500,           # Fewer entries for critical systems
    max_age_minutes=30      # More aggressive cleanup
)
```

## Monitoring and Alerts

### Key Metrics to Monitor
1. **Memory Usage**:
   - RSS (Resident Set Size)
   - VMS (Virtual Memory Size)
   - Memory percentage of system

2. **Database Connections**:
   - Pool size and usage
   - Connection overflow events
   - Connection timeouts

3. **Background Tasks**:
   - Global dictionary sizes
   - Cleanup frequency and effectiveness
   - Task completion memory delta

### Alert Thresholds
- Memory usage > 80% of available
- Database pool overflow > 50% of max
- Global dictionary size > 80% of limit
- Memory increase > 20% between checkpoints

## Next Steps

### Immediate (High Priority)
1. ✅ Create memory optimization utilities
2. [ ] Integrate cleanup into background tasks
3. [ ] Add memory monitoring to critical functions
4. [ ] Set up automated memory testing

### Short Term (Medium Priority)
1. [ ] Add production memory monitoring endpoints
2. [ ] Configure connection pooling in production
3. [ ] Set up alerting for memory thresholds
4. [ ] Create memory usage dashboard

### Long Term (Low Priority)
1. [ ] Implement predictive memory scaling
2. [ ] Add ML-based memory optimization
3. [ ] Create automated memory tuning
4. [ ] Comprehensive memory analytics

## Risk Mitigation

### Potential Issues
1. **Performance impact**: Memory monitoring overhead
2. **False alarms**: Temporary memory spikes
3. **Configuration errors**: Incorrect pool settings

### Mitigation Strategies
1. **Gradual rollout**: Enable monitoring incrementally
2. **Configurable thresholds**: Allow runtime adjustment
3. **Fallback mechanisms**: Disable monitoring if issues occur
4. **Comprehensive testing**: Test under load conditions

The memory optimization implementation provides a solid foundation for preventing memory leaks while maintaining performance and reliability.