# Poll Edit Service Design - Unified Poll Editing Architecture

## Current Task: CREATE UNIFIED POLL EDIT SERVICE & REORGANIZE SERVICES
**Date**: 2025-09-24
**Status**: IN PROGRESS

---

## Current State Analysis

### Existing Poll Edit Functionality
Currently, poll editing is scattered across multiple files with inconsistent patterns:

#### Current Edit Locations:
1. **[`polly/htmx_endpoints.py`](polly/htmx_endpoints.py:5015-5200)**
   - `get_poll_edit_form()` - Shows edit form for **scheduled polls only**
   - `update_poll_htmx()` - Updates scheduled polls
   - **Limitation**: Only allows editing of `status="scheduled"` polls

2. **[`polly/super_admin_endpoints.py`](polly/super_admin_endpoints.py:710-785)**
   - `get_poll_edit_form_htmx()` - Super admin edit form
   - **Limitation**: Super admin only, inconsistent with user editing

3. **Current Edit Restrictions**:
   - **Scheduled polls**: Full editing allowed
   - **Active polls**: NO editing allowed
   - **Closed polls**: NO editing allowed

### Current Service Architecture
The project has several service files scattered in the main `polly/` directory:

#### Existing Services:
1. **[`polly/poll_open_service.py`](polly/poll_open_service.py)** - Unified poll opening
2. **[`polly/poll_reopen_service.py`](polly/poll_reopen_service.py)** - Unified poll reopening  
3. **[`polly/poll_closure_service.py`](polly/poll_closure_service.py)** - Unified poll closure
4. **[`polly/cache_service.py`](polly/cache_service.py)** - Basic caching
5. **[`polly/enhanced_cache_service.py`](polly/enhanced_cache_service.py)** - Advanced caching
6. **[`polly/avatar_cache_service.py`](polly/avatar_cache_service.py)** - Avatar caching
7. **[`polly/super_admin_bulk_operations.py`](polly/super_admin_bulk_operations.py)** - Bulk operations service

---

## New Unified Poll Edit Service Design

### Core Requirements:
1. **UNIFIED editing interface** for all poll types with appropriate restrictions
2. **Limited editing of ACTIVE polls** - allow safe modifications
3. **Service consolidation** - move all services to dedicated `services/` directory
4. **Consistent patterns** - follow existing service architecture (open/reopen/closure services)

### Limited Active Poll Editing Rules:
For **active polls**, allow editing of:
- ✅ **Poll description** (safe - doesn't affect voting)
- ✅ **Close time extension** (common admin need)
- ✅ **Allowed roles** (permission changes)
- ❌ **Poll title** (would confuse voters)
- ❌ **Poll options** (would invalidate existing votes)
- ❌ **Open time** (poll is already active)
- ❌ **Emojis/reactions** (would break existing reactions)

### Service Directory Structure:
```
polly/
├── services/                    # NEW: Consolidated services directory
│   ├── __init__.py
│   ├── poll/                    # Poll-related services
│   │   ├── __init__.py
│   │   ├── poll_edit_service.py     # NEW: Unified poll editing
│   │   ├── poll_open_service.py     # MOVED from polly/
│   │   ├── poll_reopen_service.py   # MOVED from polly/
│   │   └── poll_closure_service.py  # MOVED from polly/
│   ├── cache/                   # Cache-related services
│   │   ├── __init__.py
│   │   ├── cache_service.py         # MOVED from polly/
│   │   ├── enhanced_cache_service.py # MOVED from polly/
│   │   └── avatar_cache_service.py  # MOVED from polly/
│   └── admin/                   # Admin-related services
│       ├── __init__.py
│       └── bulk_operations_service.py # MOVED from polly/super_admin_bulk_operations.py
```

---

## Unified Poll Edit Service Architecture

### Service Class: `PollEditService`
Following the pattern of existing services (`PollOpeningService`, `PollReopeningService`, etc.):

```python
class PollEditService:
    """Unified service for editing polls with status-appropriate restrictions"""
    
    @staticmethod
    async def edit_poll_unified(
        poll_id: int,
        edit_data: Dict[str, Any],
        editor_user_id: str,
        editor_type: str = "user"  # "user", "admin", "super_admin"
    ) -> Dict[str, Any]:
        """
        Unified poll editing with appropriate restrictions based on poll status
        """
```

### Edit Capabilities by Status:
1. **Scheduled Polls**: Full editing (existing behavior)
2. **Active Polls**: Limited editing (NEW capability)
3. **Closed Polls**: No editing (existing behavior)

### Integration Points:
- **HTMX Endpoints**: Update to use unified service
- **Super Admin**: Update to use unified service  
- **Bulk Operations**: Update to use unified service
- **Cache Management**: Integrated cache invalidation
- **Discord Updates**: Update Discord messages when needed

---

## Implementation Plan

### Phase 1: Service Directory Setup
1. Create `polly/services/` directory structure
2. Move existing services to appropriate subdirectories
3. Update all imports across the codebase

### Phase 2: Unified Poll Edit Service
1. Create `PollEditService` class
2. Implement status-based editing restrictions
3. Integrate with existing Discord/cache systems

### Phase 3: Update Endpoints
1. Update HTMX endpoints to use unified service
2. Update super admin endpoints
3. Test all editing workflows

### Phase 4: Testing & Documentation
1. Test limited active poll editing
2. Verify all import updates work
3. Update memory bank with final implementation

---

## Technical Decisions

### Why Limited Active Poll Editing?
- **User Need**: Common request to extend poll time or update description
- **Safety**: Only allow changes that don't invalidate existing votes
- **Consistency**: Aligns with super admin capabilities

### Why Service Directory Reorganization?
- **Organization**: 7+ service files cluttering main directory
- **Maintainability**: Logical grouping by functionality
- **Scalability**: Room for future service expansion
- **Pattern**: Follows common Python project structure

### Why Unified Service Pattern?
- **Consistency**: Matches existing `poll_open_service`, `poll_reopen_service` patterns
- **Maintainability**: Single source of truth for editing logic
- **Testing**: Easier to test comprehensive editing scenarios
- **Cache Management**: Centralized cache invalidation

---

## Status: READY FOR IMPLEMENTATION
Next step: Begin Phase 1 - Service Directory Setup