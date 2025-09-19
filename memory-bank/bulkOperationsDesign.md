# Bulk Operations Architecture Design

## Overview

Design comprehensive bulk operation capabilities for super admin to efficiently manage multiple polls and perform batch operations with proper progress tracking, error handling, and user feedback.

## Core Requirements

### Functional Requirements
1. **Bulk Poll Operations**
   - Bulk close polls (force close multiple polls)
   - Bulk delete polls (with confirmation)
   - Bulk reopen polls (with options)
   - Bulk status change (active → scheduled, etc.)
   - Bulk setting updates (timezone, anonymous, etc.)

2. **Bulk Selection Interface**
   - Select individual polls via checkboxes
   - Select all polls on current page
   - Select all polls matching current filters
   - Clear all selections
   - Selection persistence across page navigation

3. **Progress Tracking**
   - Real-time progress indicators
   - Operation status updates
   - Partial success/failure reporting
   - Detailed operation logs

4. **Confirmation and Safety**
   - Confirmation dialogs for destructive operations
   - Preview of affected items
   - Rollback capabilities where possible
   - Operation history tracking

### Non-Functional Requirements
1. **Performance**: Handle up to 1000 polls in a single bulk operation
2. **Reliability**: Graceful handling of partial failures
3. **Usability**: Clear progress feedback and error reporting
4. **Safety**: Multiple confirmation layers for destructive operations

## Architecture Components

### 1. Backend Service Layer

#### BulkOperationService Class
Central service for managing bulk operations with the following responsibilities:

```python
class BulkOperationService:
    async def execute_bulk_operation(
        self,
        operation_type: BulkOperationType,
        poll_ids: List[int],
        parameters: Dict[str, Any],
        admin_user_id: str,
        progress_callback: Optional[Callable] = None
    ) -> BulkOperationResult
```

#### Operation Types
```python
class BulkOperationType(Enum):
    CLOSE_POLLS = "close_polls"
    DELETE_POLLS = "delete_polls"
    REOPEN_POLLS = "reopen_polls"
    UPDATE_STATUS = "update_status"
    UPDATE_SETTINGS = "update_settings"
    EXPORT_POLLS = "export_polls"
```

#### Progress Tracking System
```python
class BulkOperationProgress:
    operation_id: str
    operation_type: BulkOperationType
    total_items: int
    processed_items: int
    successful_items: int
    failed_items: int
    current_item: Optional[str]
    start_time: datetime
    estimated_completion: Optional[datetime]
    status: BulkOperationStatus
    errors: List[BulkOperationError]
```

### 2. API Endpoints

#### Core Bulk Operation Endpoints

```python
# Start bulk operation
POST /super-admin/api/bulk/operation
{
    "operation_type": "close_polls",
    "poll_ids": [1, 2, 3, ...],
    "parameters": {
        "reason": "admin_cleanup",
        "notification": true
    }
}

# Get operation progress
GET /super-admin/api/bulk/operation/{operation_id}/progress

# Cancel running operation
POST /super-admin/api/bulk/operation/{operation_id}/cancel

# Get operation history
GET /super-admin/api/bulk/operations?limit=50&offset=0
```

#### Selection Management Endpoints

```python
# Get current selection
GET /super-admin/api/bulk/selection

# Update selection
POST /super-admin/api/bulk/selection
{
    "action": "add|remove|set|clear",
    "poll_ids": [1, 2, 3, ...]
}

# Select by filter
POST /super-admin/api/bulk/selection/filter
{
    "status": "active",
    "server_id": "123456789",
    "creator_id": "987654321"
}
```

### 3. Background Task Management

#### Async Task Processing
Use FastAPI background tasks with progress tracking:

```python
from fastapi import BackgroundTasks

@app.post("/super-admin/api/bulk/operation")
async def start_bulk_operation(
    request: BulkOperationRequest,
    background_tasks: BackgroundTasks,
    current_user: DiscordUser = Depends(require_super_admin)
):
    operation_id = generate_operation_id()
    
    # Initialize progress tracking
    progress = BulkOperationProgress(
        operation_id=operation_id,
        operation_type=request.operation_type,
        total_items=len(request.poll_ids),
        status=BulkOperationStatus.STARTING
    )
    
    # Store progress in Redis
    await store_operation_progress(operation_id, progress)
    
    # Start background task
    background_tasks.add_task(
        execute_bulk_operation_async,
        operation_id,
        request,
        current_user.id
    )
    
    return {"operation_id": operation_id, "status": "started"}
```

#### Operation Queue
Implement operation queue to prevent overwhelming the system:

```python
class BulkOperationQueue:
    def __init__(self, max_concurrent_operations: int = 3):
        self.max_concurrent = max_concurrent_operations
        self.running_operations = set()
        self.queued_operations = deque()
    
    async def enqueue_operation(self, operation_id: str, operation_func: Callable):
        if len(self.running_operations) < self.max_concurrent:
            await self.start_operation(operation_id, operation_func)
        else:
            self.queued_operations.append((operation_id, operation_func))
```

### 4. Frontend UI Components

#### Selection Interface
```html
<!-- Bulk operation toolbar -->
<div id="bulk-operations-toolbar" class="hidden">
    <div class="selection-info">
        <span id="selected-count">0</span> polls selected
    </div>
    <div class="bulk-actions">
        <button onclick="bulkOperation('close')" class="btn btn-warning">
            Close Selected
        </button>
        <button onclick="bulkOperation('delete')" class="btn btn-danger">
            Delete Selected
        </button>
        <button onclick="bulkOperation('reopen')" class="btn btn-success">
            Reopen Selected
        </button>
        <button onclick="clearSelection()" class="btn btn-secondary">
            Clear Selection
        </button>
    </div>
</div>

<!-- Poll table with checkboxes -->
<table id="polls-table">
    <thead>
        <tr>
            <th>
                <input type="checkbox" id="select-all" onchange="toggleSelectAll()">
            </th>
            <th>Poll Name</th>
            <th>Status</th>
            <!-- ... other columns ... -->
        </tr>
    </thead>
    <tbody>
        <!-- Poll rows with checkboxes -->
    </tbody>
</table>
```

#### Progress Modal
```html
<div id="bulk-operation-progress-modal" class="modal">
    <div class="modal-content">
        <h3 id="operation-title">Processing Bulk Operation</h3>
        
        <div class="progress-container">
            <div class="progress-bar">
                <div id="progress-fill" class="progress-fill"></div>
            </div>
            <div id="progress-text">0 / 0 completed</div>
        </div>
        
        <div id="current-item">Processing: Poll Name</div>
        
        <div id="results-summary" class="hidden">
            <div class="success-count">✅ <span id="success-count">0</span> successful</div>
            <div class="error-count">❌ <span id="error-count">0</span> failed</div>
        </div>
        
        <div id="error-details" class="error-list hidden">
            <!-- Error details here -->
        </div>
        
        <div class="modal-actions">
            <button id="cancel-operation" class="btn btn-secondary">Cancel</button>
            <button id="close-modal" class="btn btn-primary hidden">Close</button>
        </div>
    </div>
</div>
```

#### JavaScript Management
```javascript
class BulkOperationManager {
    constructor() {
        this.selectedPollIds = new Set();
        this.currentOperation = null;
        this.progressInterval = null;
    }
    
    // Selection management
    togglePollSelection(pollId) {
        if (this.selectedPollIds.has(pollId)) {
            this.selectedPollIds.delete(pollId);
        } else {
            this.selectedPollIds.add(pollId);
        }
        this.updateUI();
    }
    
    // Start bulk operation
    async startBulkOperation(operationType, parameters = {}) {
        const pollIds = Array.from(this.selectedPollIds);
        
        if (pollIds.length === 0) {
            showAlert('No polls selected', 'warning');
            return;
        }
        
        // Show confirmation for destructive operations
        if (['delete', 'close'].includes(operationType)) {
            const confirmed = await showConfirmationDialog(
                `Are you sure you want to ${operationType} ${pollIds.length} polls?`,
                'This action cannot be undone.'
            );
            if (!confirmed) return;
        }
        
        try {
            const response = await fetch('/super-admin/api/bulk/operation', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    operation_type: operationType,
                    poll_ids: pollIds,
                    parameters: parameters
                })
            });
            
            const result = await response.json();
            
            if (result.operation_id) {
                this.currentOperation = result.operation_id;
                this.startProgressTracking();
                showProgressModal();
            }
        } catch (error) {
            showAlert('Failed to start bulk operation', 'error');
        }
    }
    
    // Progress tracking
    startProgressTracking() {
        this.progressInterval = setInterval(async () => {
            await this.updateProgress();
        }, 1000);
    }
    
    async updateProgress() {
        if (!this.currentOperation) return;
        
        try {
            const response = await fetch(
                `/super-admin/api/bulk/operation/${this.currentOperation}/progress`
            );
            const progress = await response.json();
            
            updateProgressUI(progress);
            
            if (progress.status === 'completed' || progress.status === 'failed') {
                clearInterval(this.progressInterval);
                this.currentOperation = null;
                showOperationResults(progress);
            }
        } catch (error) {
            console.error('Failed to fetch progress:', error);
        }
    }
}
```

### 5. Error Handling and Recovery

#### Partial Failure Handling
```python
class BulkOperationResult:
    operation_id: str
    total_items: int
    successful_items: List[BulkOperationItemResult]
    failed_items: List[BulkOperationItemResult]
    overall_status: BulkOperationStatus
    start_time: datetime
    end_time: datetime
    errors: List[str]
    
    @property
    def success_rate(self) -> float:
        return len(self.successful_items) / self.total_items * 100
```

#### Error Recovery Strategies
1. **Retry Failed Items**: Ability to retry only the failed items from a bulk operation
2. **Rollback Support**: For reversible operations, provide rollback capability
3. **Detailed Error Reporting**: Specific error messages for each failed item
4. **Export Results**: Export operation results for further analysis

### 6. Safety and Validation

#### Pre-Operation Validation
```python
async def validate_bulk_operation(
    operation_type: BulkOperationType,
    poll_ids: List[int],
    parameters: Dict[str, Any]
) -> ValidationResult:
    """
    Validate bulk operation before execution:
    - Check if all polls exist
    - Validate state transitions
    - Check permissions
    - Validate parameters
    """
    validation_errors = []
    
    # Check poll existence and permissions
    for poll_id in poll_ids:
        poll = await get_poll(poll_id)
        if not poll:
            validation_errors.append(f"Poll {poll_id} not found")
        elif not can_perform_operation(poll, operation_type):
            validation_errors.append(f"Cannot {operation_type} poll {poll_id} in status {poll.status}")
    
    return ValidationResult(
        is_valid=len(validation_errors) == 0,
        errors=validation_errors
    )
```

#### Operation Limits
```python
class BulkOperationLimits:
    MAX_POLLS_PER_OPERATION = 1000
    MAX_CONCURRENT_OPERATIONS_PER_USER = 2
    OPERATION_TIMEOUT_MINUTES = 30
    MIN_CONFIRMATION_DELAY_SECONDS = 5  # For destructive operations
```

### 7. Monitoring and Analytics

#### Operation Metrics
- Total bulk operations executed
- Success/failure rates by operation type
- Average processing time per item
- Most common error types
- Peak operation volumes

#### Audit Trail
```python
class BulkOperationAudit:
    operation_id: str
    admin_user_id: str
    operation_type: BulkOperationType
    affected_poll_ids: List[int]
    parameters: Dict[str, Any]
    start_time: datetime
    end_time: datetime
    result_summary: Dict[str, Any]
    ip_address: str
    user_agent: str
```

## Implementation Plan

### Phase 1: Core Infrastructure (Week 1)
1. Implement BulkOperationService class
2. Create basic API endpoints for operation management
3. Set up progress tracking with Redis
4. Implement background task processing

### Phase 2: UI Components (Week 2)
1. Add selection interface to polls table
2. Create progress modal and feedback systems
3. Implement JavaScript bulk operation manager
4. Add confirmation dialogs for destructive operations

### Phase 3: Operation Types (Week 3)
1. Implement bulk close operations
2. Implement bulk delete operations
3. Implement bulk reopen operations
4. Add bulk status update operations

### Phase 4: Safety and Polish (Week 4)
1. Add comprehensive validation
2. Implement error recovery mechanisms
3. Add operation history and audit trail
4. Performance testing and optimization

## Testing Strategy

### Unit Tests
- BulkOperationService methods
- Progress tracking functionality
- Validation logic
- Error handling scenarios

### Integration Tests
- End-to-end bulk operation flows
- UI interaction testing
- Progress tracking accuracy
- Error recovery mechanisms

### Performance Tests
- Large bulk operation handling (1000+ polls)
- Concurrent operation management
- Memory usage under load
- Database performance impact

### User Acceptance Tests
- UI usability testing
- Error message clarity
- Progress feedback effectiveness
- Recovery procedure validation

## Success Metrics
- **Efficiency**: 90%+ reduction in time for bulk operations vs individual operations
- **Reliability**: 99%+ success rate for individual items in bulk operations
- **Usability**: Clear progress feedback and error reporting
- **Safety**: Zero data loss incidents from bulk operations
- **Performance**: Handle 1000 polls in under 60 seconds for most operations