# Poll Edit Service Enhancement Analysis

## 🎯 **TASK**: Enhance Poll Edit Service for Discord Messages and Scheduler Integration

### 📊 **ANALYSIS OF CURRENT IMPLEMENTATION GAPS**

#### **1. Discord Message Update Issues**
**Current Implementation in [`polly/services/poll/poll_edit_service.py`](polly/services/poll/poll_edit_service.py:277-302):**
- **Line 284**: Only updates Discord message if `description` was changed
- **Line 295**: Calls non-existent function `update_poll_message_content()`
- **Gap**: Should update message for ALL relevant edits (options, close_time, etc.)

#### **2. Missing Function: `update_poll_message_content()`**
**Current State:**
- Function doesn't exist in [`polly/discord_utils.py`](polly/discord_utils.py)
- Poll edit service tries to import it but it's missing
- **Existing Function**: `update_poll_message()` (line 816) handles full message updates

#### **3. Scheduler Integration Issues**
**Current Implementation:**
- No scheduler update when `close_time` is changed
- **Gap**: When close_time changes, existing scheduler jobs should be updated
- **Risk**: Polls may close at old time instead of new edited time

#### **4. Fields That Should Trigger Discord Updates**
```python
# Current: Only description triggers update
"description" in edit_data

# Should Trigger Updates:
- "description"     # Content changes
- "options"         # New voting options added
- "close_time"      # Time extension announcements
- "name"            # Poll title changes (for scheduled polls)
```

### 🔧 **REQUIRED ENHANCEMENTS**

#### **Enhancement 1: Complete Discord Message Update Function**
**File**: [`polly/discord_utils.py`](polly/discord_utils.py)
- **Create**: `update_poll_message_content()` function
- **Logic**: Wrapper around existing `update_poll_message()` but for edit contexts
- **Return**: Proper success/error response format

#### **Enhancement 2: Expanded Discord Update Triggers**
**File**: [`polly/services/poll/poll_edit_service.py`](polly/services/poll/poll_edit_service.py:277-302)
- **Current**: Line 284 only checks for `description`
- **Enhanced**: Check for multiple fields that require Discord updates
- **Fields**: `description`, `options`, `close_time`, `name` (for scheduled polls)

#### **Enhancement 3: Scheduler Integration for close_time Changes**
**File**: [`polly/services/poll/poll_edit_service.py`](polly/services/poll/poll_edit_service.py)
- **Add**: Scheduler update logic after database commit
- **Integration**: Use [`TimezoneAwareScheduler`](polly/timezone_scheduler_fix.py:15) like other services
- **Process**: Remove old close job, add new close job with updated time

#### **Enhancement 4: Active Poll-Specific Logic**
**Current Active Poll Restrictions** (Lines 28-35):
- ✅ `description` - Safe content updates
- ✅ `close_time` - Time extensions only
- ✅ `options` - Adding new options only
- ✅ Role permissions and ping settings

**Enhancement**: Ensure scheduler updates respect these restrictions

### 📋 **IMPLEMENTATION PLAN**

#### **Step 1**: Create Missing `update_poll_message_content()` Function
```python
# In discord_utils.py
async def update_poll_message_content(bot: commands.Bot, poll_id: int) -> Dict[str, Any]:
    """Update poll message content after editing - wrapper for poll edit contexts"""
    # Implementation details in code
```

#### **Step 2**: Enhance Discord Update Logic
```python
# In poll_edit_service.py _update_discord_message()
# Current: Only checks "description"
# Enhanced: Check multiple fields that need Discord updates
update_fields = ["description", "options", "close_time"]
if any(field in edit_data for field in update_fields):
    # Update Discord message
```

#### **Step 3**: Add Scheduler Integration
```python
# In poll_edit_service.py after database commit
if "close_time" in valid_edits and changes_made:
    await _update_scheduler_for_close_time(poll_id, valid_edits["close_time"])
```

#### **Step 4**: Implement Scheduler Update Helper
```python
# New helper function in poll_edit_service.py
async def _update_scheduler_for_close_time(poll_id: int, new_close_time: datetime):
    """Update scheduler jobs when close_time is edited"""
    # Remove existing close job
    # Add new close job with updated time
```

### 🚀 **TECHNICAL INTEGRATION POINTS**

#### **Existing Scheduler Pattern** (from other services):
```python
from ...background_tasks import get_scheduler
from ...timezone_scheduler_fix import TimezoneAwareScheduler

scheduler = get_scheduler()
tz_scheduler = TimezoneAwareScheduler(scheduler)
success = tz_scheduler.schedule_poll_closing(poll_id, close_time, timezone, close_poll)
```

#### **Existing Discord Update Pattern**:
```python
from ...discord_utils import update_poll_message
result = await update_poll_message(bot_instance, poll)
```

### 💡 **KEY DECISIONS**

#### **Why Create `update_poll_message_content()` vs Use Existing**:
- **Existing**: `update_poll_message()` expects Poll object
- **Edit Context**: We have poll_id and need different error handling
- **Solution**: Create wrapper that fetches poll and calls existing function

#### **Why Scheduler Integration is Critical**:
- **Risk**: Without scheduler updates, polls close at old time
- **User Expectation**: Extended polls should close at new time
- **System Integrity**: Scheduler jobs must match database state

#### **Discord Update Triggers**:
- **Description**: Content changes visible to voters
- **Options**: New choices available for voting
- **Close Time**: Users should see updated deadline
- **Name**: Title changes (for scheduled polls)

---
**Analysis Completed**: 2025-01-24 18:15 UTC  
**Next**: Implement enhancements to poll edit service