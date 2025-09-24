# Background Tasks Closure Bug Fix

## 🎯 **CURRENT TASK**: Fix SonarQube Closure Issue in background_tasks.py

### 🐛 **PROBLEM IDENTIFIED**
- **File**: `polly/background_tasks.py`
- **Line**: 654 (within loop starting at line 594)
- **SonarQube Rule**: python:S1515
- **Issue**: Variable `poll_opening_service` captured in closure may change at next loop iteration

### 🔍 **ROOT CAUSE ANALYSIS**
The problem occurs in the scheduler restoration function:

```python
# Line 594: for poll in scheduled_polls:
for poll in scheduled_polls:
    # ... loop body ...
    
    # Line 650: Import inside loop
    from .services.poll.poll_open_service import poll_opening_service
    
    # Line 652: Function definition inside loop creates closure
    async def open_poll_scheduled(bot_instance, poll_id):
        """Wrapper function for scheduled poll opening"""
        result = await poll_opening_service.open_poll_unified(  # ← CLOSURE ISSUE
            poll_id=poll_id,
            reason="scheduled", 
            bot_instance=bot_instance
        )
        # ... rest of function
```

**Why This Is A Problem:**
1. `poll_opening_service` is imported inside the loop
2. `open_poll_scheduled` function is defined inside the loop
3. The function captures a reference to `poll_opening_service` 
4. If the import somehow changes between iterations, all previously created functions would use the new value
5. This creates unpredictable behavior

### 🔧 **SOLUTION STRATEGY**
1. **Move import outside the loop** - Import `poll_opening_service` once before the loop
2. **Add parameter with default value** - Pass `poll_opening_service` as a parameter with default value to capture current value
3. **Maintain functionality** - Ensure the fix doesn't break existing behavior

### 📝 **IMPLEMENTATION PLAN**
1. Move the import statement to before the loop (around line 590)
2. Modify `open_poll_scheduled` function to accept `poll_opening_service` as parameter with default value
3. This captures the current value at function definition time, preventing closure issues

### ✅ **EXPECTED OUTCOME**
- SonarQube warning resolved
- More robust and predictable code behavior  
- Better performance (import only happens once)
- Follows Python best practices for imports

### ✅ **IMPLEMENTATION COMPLETED**

#### **🔧 CHANGES MADE**

1. **Moved Import Outside Loop** (Line 590-591):
```python
# Import poll opening service once before loop to avoid closure issues
from .services.poll.poll_open_service import poll_opening_service
```

2. **Added Parameter with Default Value** (Line 653):
```python
# BEFORE (CLOSURE ISSUE):
async def open_poll_scheduled(bot_instance, poll_id):
    result = await poll_opening_service.open_poll_unified(...)

# AFTER (FIXED):
async def open_poll_scheduled(bot_instance, poll_id, service=poll_opening_service):
    result = await service.open_poll_unified(...)
```

3. **Removed Duplicate Import** - Eliminated the import inside the loop that caused the closure issue

#### **🎯 RESULTS ACHIEVED**
- ✅ SonarQube python:S1515 warning resolved for background_tasks.py:654
- ✅ More robust and predictable code behavior  
- ✅ Better performance (import only happens once)
- ✅ Follows Python best practices for imports
- ✅ Maintains exact same functionality without breaking changes

#### **🔍 ADDITIONAL FINDINGS**
Found 2 similar closure issues in `htmx_endpoints.py`:
- Line 3925: Same pattern in `open_poll_scheduled_wrapper` function
- Line 5435: Same pattern in another `open_poll_scheduled_wrapper` function

These were not part of the current task but could be fixed using the same approach if needed.

#### **🧪 VERIFICATION**
- The fix preserves the exact same functionality
- The function signature is backward-compatible 
- The default parameter captures the service instance at definition time
- No breaking changes to existing code that calls this function

---

**STATUS: COMPLETE** ✅  
**Task**: Fix SonarQube Closure Issue python:S1515 in background_tasks.py:654  
**Resolution**: Successfully implemented parameter with default value solution