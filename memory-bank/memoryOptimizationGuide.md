# Memory Optimization Guide & Best Practices

## Task Context
Optimize memory usage and prevent memory leaks in the Polly Python application.

## Memory Profiling Best Practices (from Memray)

### Key Tools & Techniques

#### 1. Memory Profiling with Memray
- **Install**: `pip install memray`
- **Basic profiling**: `python3 -m memray run my_script.py`
- **Live monitoring**: `memray run --live application.py`
- **Native tracking**: `memray run --native my_script.py`
- **Generate reports**: `memray flamegraph output.bin`

#### 2. Python Allocator Configuration
- **Disable pymalloc for accurate leak detection**: `export PYTHONMALLOC=malloc`
- **Development mode**: `python -Xdev your_script.py`
- **Trace Python allocators**: `memray run --trace-python-allocators your_script.py`

#### 3. Memory Optimization Patterns

##### Hidden Mutability Pattern
```python
def process_data():
    # Reuse variable instead of creating new ones
    data = load_data()
    data = transform_data(data)  # Reuse same variable
    data = process_data(data)    # Old data eligible for GC
    return data
```

##### Self-Contained Cache Pattern
```python
class MyClass:
    def __init__(self):
        self.cached_method = functools.cache(self._uncached_method)
    
    def _uncached_method(self, arg):
        # Cache tied to object lifecycle
        return expensive_computation(arg)
```

#### 4. Memory Leak Detection
- **Test memory limits**: `@pytest.mark.limit_memory("24 MB")`
- **Programmatic tracking**: 
```python
import memray
with memray.Tracker("output.bin"):
    # Code to analyze
    pass
```

## Common Memory Issues to Check

### 1. Unclosed Resources
- Database connections not properly closed
- File handles left open
- Network connections not cleaned up

### 2. Growing Collections
- Caches that grow indefinitely
- Lists/dictionaries that accumulate data
- Background task queues

### 3. Circular References
- Objects referencing each other preventing GC
- Event listeners not properly removed
- Callback functions holding references

### 4. Large Object Retention
- Loading entire files into memory
- Keeping large data structures longer than needed
- Memory-intensive operations without streaming

## Analysis Areas for Polly Project

### High Priority
1. **Background Tasks** - [`polly/background_tasks.py`](polly/background_tasks.py)
2. **Database Operations** - [`polly/database.py`](polly/database.py)
3. **Redis/Cache Services** - [`polly/cache_service.py`](polly/cache_service.py)
4. **Discord Bot** - [`polly/discord_bot.py`](polly/discord_bot.py)

### Medium Priority
5. **Avatar Cache** - [`polly/avatar_cache_service.py`](polly/avatar_cache_service.py)
6. **Web App** - [`polly/web_app.py`](polly/web_app.py)
7. **File Operations** - Image uploads, static recovery

### Memory Monitoring Implementation Plan
1. Add Memray profiling capabilities
2. Implement memory usage monitoring endpoints
3. Add resource cleanup validation
4. Create memory leak detection tests

## Next Steps
1. Analyze each high-priority file for memory issues
2. Implement fixes based on best practices
3. Add monitoring and profiling capabilities
4. Validate improvements with testing