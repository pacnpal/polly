"""
Super Admin Bulk Operations Service
Provides comprehensive bulk operation capabilities for managing multiple polls with progress tracking.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass
from collections import deque

from ...super_admin_error_handler import (
    SuperAdminError, SuperAdminErrorType, super_admin_error_handler, SuperAdminValidator
)
from ...database import get_db_session

logger = logging.getLogger(__name__)


class BulkOperationType(Enum):
    """Types of bulk operations supported"""
    CLOSE_POLLS = "close_polls"
    DELETE_POLLS = "delete_polls"
    REOPEN_POLLS = "reopen_polls"
    UPDATE_STATUS = "update_status"
    UPDATE_SETTINGS = "update_settings"
    EXPORT_POLLS = "export_polls"


class BulkOperationStatus(Enum):
    """Status of bulk operations"""
    STARTING = "starting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


@dataclass
class BulkOperationItemResult:
    """Result for individual item in bulk operation"""
    item_id: int
    success: bool
    message: str
    error_code: Optional[str] = None
    processing_time_ms: Optional[int] = None
    retry_count: int = 0


@dataclass
class BulkOperationError:
    """Error information for bulk operations"""
    item_id: int
    error_code: str
    message: str
    timestamp: datetime
    retry_count: int = 0


@dataclass
class BulkOperationProgress:
    """Progress tracking for bulk operations"""
    operation_id: str
    operation_type: BulkOperationType
    status: BulkOperationStatus
    total_items: int
    processed_items: int
    successful_items: int
    failed_items: int
    current_item_id: Optional[int]
    current_item_name: Optional[str]
    start_time: datetime
    last_update_time: datetime
    estimated_completion_time: Optional[datetime]
    completion_time: Optional[datetime]
    errors: List[BulkOperationError]
    admin_user_id: str
    parameters: Dict[str, Any]
    
    @property
    def progress_percentage(self) -> float:
        if self.total_items == 0:
            return 0.0
        return (self.processed_items / self.total_items) * 100
    
    @property
    def success_rate(self) -> float:
        if self.processed_items == 0:
            return 0.0
        return (self.successful_items / self.processed_items) * 100
    
    @property
    def is_complete(self) -> bool:
        return self.status in [BulkOperationStatus.COMPLETED, BulkOperationStatus.FAILED, BulkOperationStatus.CANCELLED]


@dataclass
class BulkOperationRequest:
    """Request structure for bulk operations"""
    operation_type: BulkOperationType
    poll_ids: List[int]
    parameters: Dict[str, Any]
    admin_user_id: str
    confirmation_code: Optional[str] = None  # For destructive operations


@dataclass
class BulkOperationResult:
    """Final result of bulk operation"""
    operation_id: str
    operation_type: BulkOperationType
    total_items: int
    successful_items: List[BulkOperationItemResult]
    failed_items: List[BulkOperationItemResult]
    overall_status: BulkOperationStatus
    start_time: datetime
    end_time: datetime
    processing_duration_seconds: float
    admin_user_id: str
    parameters: Dict[str, Any]
    
    @property
    def success_count(self) -> int:
        return len(self.successful_items)
    
    @property
    def failure_count(self) -> int:
        return len(self.failed_items)
    
    @property
    def success_rate(self) -> float:
        if self.total_items == 0:
            return 0.0
        return (self.success_count / self.total_items) * 100


class BulkOperationQueue:
    """Queue manager for bulk operations to prevent system overload"""
    
    def __init__(self, max_concurrent_operations: int = 3):
        self.max_concurrent = max_concurrent_operations
        self.running_operations: Set[str] = set()
        self.queued_operations: deque = deque()
        self._lock = asyncio.Lock()
    
    async def can_start_operation(self) -> bool:
        """Check if a new operation can be started"""
        async with self._lock:
            return len(self.running_operations) < self.max_concurrent
    
    async def register_operation(self, operation_id: str) -> bool:
        """Register a new operation"""
        async with self._lock:
            if len(self.running_operations) < self.max_concurrent:
                self.running_operations.add(operation_id)
                return True
            return False
    
    async def complete_operation(self, operation_id: str):
        """Mark operation as completed"""
        async with self._lock:
            self.running_operations.discard(operation_id)
    
    async def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status"""
        async with self._lock:
            return {
                "running_operations": len(self.running_operations),
                "max_concurrent": self.max_concurrent,
                "queued_operations": len(self.queued_operations),
                "can_accept_new": len(self.running_operations) < self.max_concurrent
            }


class BulkOperationProgressStore:
    """In-memory store for operation progress (in production, use Redis)"""
    
    def __init__(self):
        self._progress_store: Dict[str, BulkOperationProgress] = {}
        self._lock = asyncio.Lock()
    
    async def store_progress(self, progress: BulkOperationProgress):
        """Store operation progress"""
        async with self._lock:
            self._progress_store[progress.operation_id] = progress
    
    async def get_progress(self, operation_id: str) -> Optional[BulkOperationProgress]:
        """Get operation progress"""
        async with self._lock:
            return self._progress_store.get(operation_id)
    
    async def list_operations(self, admin_user_id: Optional[str] = None) -> List[BulkOperationProgress]:
        """List operations, optionally filtered by admin user"""
        async with self._lock:
            operations = list(self._progress_store.values())
            if admin_user_id:
                operations = [op for op in operations if op.admin_user_id == admin_user_id]
            return sorted(operations, key=lambda x: x.start_time, reverse=True)
    
    async def cleanup_old_operations(self, max_age_hours: int = 24):
        """Clean up old completed operations"""
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        async with self._lock:
            to_remove = [
                op_id for op_id, progress in self._progress_store.items()
                if progress.is_complete and progress.start_time < cutoff_time
            ]
            for op_id in to_remove:
                del self._progress_store[op_id]


class BulkOperationService:
    """Main service for handling bulk operations"""
    
    def __init__(self):
        self.queue = BulkOperationQueue()
        self.progress_store = BulkOperationProgressStore()
        self._operation_handlers = {
            BulkOperationType.CLOSE_POLLS: self._handle_bulk_close,
            BulkOperationType.DELETE_POLLS: self._handle_bulk_delete,
            BulkOperationType.REOPEN_POLLS: self._handle_bulk_reopen,
            BulkOperationType.UPDATE_STATUS: self._handle_bulk_update_status,
            BulkOperationType.UPDATE_SETTINGS: self._handle_bulk_update_settings,
            BulkOperationType.EXPORT_POLLS: self._handle_bulk_export,
        }
    
    async def validate_bulk_request(self, request: BulkOperationRequest) -> Optional[SuperAdminError]:
        """Validate bulk operation request"""
        
        # Validate poll IDs
        error = SuperAdminValidator.validate_poll_ids_list(request.poll_ids)
        if error:
            return error
        
        # Validate operation-specific parameters
        if request.operation_type == BulkOperationType.DELETE_POLLS:
            # Require confirmation for destructive operations
            if not request.confirmation_code:
                return super_admin_error_handler.create_error(
                    error_type=SuperAdminErrorType.VALIDATION,
                    code="CONFIRMATION_REQUIRED",
                    message="Confirmation code is required for delete operations",
                    details={
                        "field": "confirmation_code",
                        "expected": "confirmation string"
                    },
                    suggestions=["Provide confirmation code to proceed with deletion"]
                )
        
        # Check if polls exist and are valid for the operation
        db = get_db_session()
        try:
            from .super_admin import super_admin_service
            
            invalid_polls = []
            for poll_id in request.poll_ids:
                poll_details = super_admin_service.get_poll_details(db, poll_id)
                if not poll_details:
                    invalid_polls.append(poll_id)
                elif not self._can_perform_operation(poll_details["poll"], request.operation_type):
                    invalid_polls.append(poll_id)
            
            if invalid_polls:
                return super_admin_error_handler.create_error(
                    error_type=SuperAdminErrorType.VALIDATION,
                    code="INVALID_POLLS_FOR_OPERATION",
                    message=f"Some polls cannot be processed: {invalid_polls[:5]}{'...' if len(invalid_polls) > 5 else ''}",
                    details={
                        "invalid_poll_ids": invalid_polls,
                        "total_invalid": len(invalid_polls)
                    },
                    suggestions=[
                        "Remove invalid polls from the selection",
                        "Check poll status and permissions"
                    ]
                )
        
        finally:
            db.close()
        
        return None
    
    def _can_perform_operation(self, poll: Dict[str, Any], operation_type: BulkOperationType) -> bool:
        """Check if operation can be performed on the poll"""
        poll_status = poll.get("status", "")
        
        if operation_type == BulkOperationType.CLOSE_POLLS:
            return poll_status in ["active", "scheduled"]
        elif operation_type == BulkOperationType.REOPEN_POLLS:
            return poll_status == "closed"
        elif operation_type == BulkOperationType.DELETE_POLLS:
            return True  # Can delete any poll
        elif operation_type in [BulkOperationType.UPDATE_STATUS, BulkOperationType.UPDATE_SETTINGS]:
            return True  # Can update any poll
        
        return True
    
    async def start_bulk_operation(self, request: BulkOperationRequest) -> str:
        """Start a new bulk operation"""
        
        # Validate request
        validation_error = await self.validate_bulk_request(request)
        if validation_error:
            raise Exception(f"Validation failed: {validation_error.message}")
        
        # Check queue capacity
        if not await self.queue.can_start_operation():
            raise Exception("System is at capacity. Please try again later.")
        
        # Generate operation ID
        operation_id = str(uuid.uuid4())
        
        # Register operation in queue
        if not await self.queue.register_operation(operation_id):
            raise Exception("Failed to register operation in queue")
        
        # Initialize progress tracking
        progress = BulkOperationProgress(
            operation_id=operation_id,
            operation_type=request.operation_type,
            status=BulkOperationStatus.STARTING,
            total_items=len(request.poll_ids),
            processed_items=0,
            successful_items=0,
            failed_items=0,
            current_item_id=None,
            current_item_name=None,
            start_time=datetime.now(),
            last_update_time=datetime.now(),
            estimated_completion_time=None,
            completion_time=None,
            errors=[],
            admin_user_id=request.admin_user_id,
            parameters=request.parameters
        )
        
        await self.progress_store.store_progress(progress)
        
        # Start background task
        asyncio.create_task(self._execute_bulk_operation(operation_id, request))
        
        return operation_id
    
    async def _execute_bulk_operation(self, operation_id: str, request: BulkOperationRequest):
        """Execute bulk operation in background"""
        
        try:
            # Get progress
            progress = await self.progress_store.get_progress(operation_id)
            if not progress:
                logger.error(f"Progress not found for operation {operation_id}")
                return
            
            # Update status to running
            progress.status = BulkOperationStatus.RUNNING
            progress.last_update_time = datetime.now()
            await self.progress_store.store_progress(progress)
            
            # Get operation handler
            handler = self._operation_handlers.get(request.operation_type)
            if not handler:
                raise Exception(f"No handler for operation type: {request.operation_type}")
            
            # Execute operation
            successful_items = []
            failed_items = []
            
            for i, poll_id in enumerate(request.poll_ids):
                try:
                    # Update current item
                    progress.current_item_id = poll_id
                    progress.last_update_time = datetime.now()
                    
                    # Get poll name for display
                    db = get_db_session()
                    try:
                        from .super_admin import super_admin_service
                        poll_details = super_admin_service.get_poll_details(db, poll_id)
                        progress.current_item_name = poll_details["poll"]["name"] if poll_details else f"Poll {poll_id}"
                    finally:
                        db.close()
                    
                    # Estimate completion time
                    if i > 0:
                        elapsed = (datetime.now() - progress.start_time).total_seconds()
                        avg_time_per_item = elapsed / i
                        remaining_items = len(request.poll_ids) - i
                        progress.estimated_completion_time = datetime.now() + timedelta(seconds=remaining_items * avg_time_per_item)
                    
                    await self.progress_store.store_progress(progress)
                    
                    # Execute operation on individual poll
                    start_time = datetime.now()
                    result = await handler(poll_id, request.parameters, request.admin_user_id)
                    processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
                    
                    # Store result
                    item_result = BulkOperationItemResult(
                        item_id=poll_id,
                        success=result.get("success", False),
                        message=result.get("message", "Operation completed"),
                        error_code=result.get("error_code"),
                        processing_time_ms=processing_time
                    )
                    
                    if item_result.success:
                        successful_items.append(item_result)
                        progress.successful_items += 1
                    else:
                        failed_items.append(item_result)
                        progress.failed_items += 1
                        
                        # Add to errors list
                        error = BulkOperationError(
                            item_id=poll_id,
                            error_code=result.get("error_code", "UNKNOWN_ERROR"),
                            message=result.get("message", "Unknown error"),
                            timestamp=datetime.now()
                        )
                        progress.errors.append(error)
                    
                    progress.processed_items += 1
                    
                except Exception as e:
                    # Handle individual item failure
                    logger.error(f"Error processing poll {poll_id} in bulk operation {operation_id}: {e}")
                    
                    item_result = BulkOperationItemResult(
                        item_id=poll_id,
                        success=False,
                        message=f"Unexpected error: {str(e)}",
                        error_code="PROCESSING_ERROR"
                    )
                    
                    failed_items.append(item_result)
                    progress.failed_items += 1
                    progress.processed_items += 1
                    
                    error = BulkOperationError(
                        item_id=poll_id,
                        error_code="PROCESSING_ERROR",
                        message=f"Unexpected error: {str(e)}",
                        timestamp=datetime.now()
                    )
                    progress.errors.append(error)
                
                # Small delay to prevent overwhelming the system
                await asyncio.sleep(0.1)
            
            # Mark operation as completed
            progress.status = BulkOperationStatus.COMPLETED
            progress.completion_time = datetime.now()
            progress.current_item_id = None
            progress.current_item_name = None
            
            await self.progress_store.store_progress(progress)
            
            logger.info(
                f"Bulk operation {operation_id} completed: "
                f"{progress.successful_items} successful, {progress.failed_items} failed"
            )
            
        except Exception as e:
            logger.error(f"Bulk operation {operation_id} failed: {e}")
            
            # Mark operation as failed
            progress = await self.progress_store.get_progress(operation_id)
            if progress:
                progress.status = BulkOperationStatus.FAILED
                progress.completion_time = datetime.now()
                await self.progress_store.store_progress(progress)
        
        finally:
            # Remove from queue
            await self.queue.complete_operation(operation_id)
    
    async def _handle_bulk_close(self, poll_id: int, parameters: Dict[str, Any], admin_user_id: str) -> Dict[str, Any]:
        """Handle bulk close operation for individual poll"""
        try:
            db = get_db_session()
            try:
                from .super_admin import super_admin_service
                result = await super_admin_service.force_close_poll(db, poll_id, admin_user_id)
                return result
            finally:
                db.close()
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to close poll: {str(e)}",
                "error_code": "CLOSE_FAILED"
            }
    
    async def _handle_bulk_delete(self, poll_id: int, parameters: Dict[str, Any], admin_user_id: str) -> Dict[str, Any]:
        """Handle bulk delete operation for individual poll"""
        try:
            db = get_db_session()
            try:
                from .super_admin import super_admin_service
                result = super_admin_service.delete_poll(db, poll_id, admin_user_id)
                return result
            finally:
                db.close()
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to delete poll: {str(e)}",
                "error_code": "DELETE_FAILED"
            }
    
    async def _handle_bulk_reopen(self, poll_id: int, parameters: Dict[str, Any], admin_user_id: str) -> Dict[str, Any]:
        """Handle bulk reopen operation for individual poll"""
        try:
            db = get_db_session()
            try:
                from .super_admin import super_admin_service
                
                # Extract reopen parameters
                extend_hours = parameters.get("extend_hours")
                reset_votes = parameters.get("reset_votes", False)
                new_close_time = parameters.get("new_close_time")
                
                result = await super_admin_service.reopen_poll(
                    db, poll_id, admin_user_id,
                    new_close_time=new_close_time,
                    extend_hours=extend_hours,
                    reset_votes=reset_votes
                )
                return result
            finally:
                db.close()
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to reopen poll: {str(e)}",
                "error_code": "REOPEN_FAILED"
            }
    
    async def _handle_bulk_update_status(self, poll_id: int, parameters: Dict[str, Any], admin_user_id: str) -> Dict[str, Any]:
        """Handle bulk status update operation for individual poll"""
        try:
            new_status = parameters.get("new_status")
            if not new_status:
                return {
                    "success": False,
                    "message": "New status not specified",
                    "error_code": "MISSING_STATUS"
                }
            
            db = get_db_session()
            try:
                from .database import Poll
                poll = db.query(Poll).filter(Poll.id == poll_id).first()
                if not poll:
                    return {
                        "success": False,
                        "message": "Poll not found",
                        "error_code": "POLL_NOT_FOUND"
                    }
                
                old_status = poll.status
                poll.status = new_status
                db.commit()
                
                logger.info(f"Admin {admin_user_id} updated poll {poll_id} status: {old_status} → {new_status}")
                
                return {
                    "success": True,
                    "message": f"Status updated from {old_status} to {new_status}"
                }
            finally:
                db.close()
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to update status: {str(e)}",
                "error_code": "UPDATE_STATUS_FAILED"
            }
    
    async def _handle_bulk_update_settings(self, poll_id: int, parameters: Dict[str, Any], admin_user_id: str) -> Dict[str, Any]:
        """Handle bulk settings update operation for individual poll"""
        try:
            db = get_db_session()
            try:
                from .super_admin import super_admin_service
                
                # Use existing update_poll method
                result = super_admin_service.update_poll(db, poll_id, parameters, admin_user_id)
                return result
            finally:
                db.close()
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to update settings: {str(e)}",
                "error_code": "UPDATE_SETTINGS_FAILED"
            }
    
    async def _handle_bulk_export(self, poll_id: int, parameters: Dict[str, Any], admin_user_id: str) -> Dict[str, Any]:
        """Handle bulk export operation for individual poll"""
        try:
            db = get_db_session()
            try:
                from .super_admin import super_admin_service
                poll_details = super_admin_service.get_poll_details(db, poll_id)
                
                if not poll_details:
                    return {
                        "success": False,
                        "message": "Poll not found",
                        "error_code": "POLL_NOT_FOUND"
                    }
                
                # Store poll data for export (would be collected and exported as a batch)
                return {
                    "success": True,
                    "message": "Poll data prepared for export",
                    "data": poll_details
                }
            finally:
                db.close()
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to export poll: {str(e)}",
                "error_code": "EXPORT_FAILED"
            }
    
    async def get_operation_progress(self, operation_id: str) -> Optional[BulkOperationProgress]:
        """Get progress for a specific operation"""
        return await self.progress_store.get_progress(operation_id)
    
    async def cancel_operation(self, operation_id: str, admin_user_id: str) -> bool:
        """Cancel a running operation"""
        progress = await self.progress_store.get_progress(operation_id)
        if not progress:
            return False
        
        if progress.admin_user_id != admin_user_id:
            return False  # Only the creator can cancel
        
        if progress.status not in [BulkOperationStatus.RUNNING, BulkOperationStatus.STARTING]:
            return False  # Can only cancel running operations
        
        progress.status = BulkOperationStatus.CANCELLED
        progress.completion_time = datetime.now()
        await self.progress_store.store_progress(progress)
        
        logger.info(f"Bulk operation {operation_id} cancelled by admin {admin_user_id}")
        return True
    
    async def list_operations(self, admin_user_id: Optional[str] = None, limit: int = 50) -> List[BulkOperationProgress]:
        """List bulk operations, optionally filtered by admin user"""
        operations = await self.progress_store.list_operations(admin_user_id)
        return operations[:limit]
    
    async def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status"""
        return await self.queue.get_queue_status()


# Global service instance
bulk_operation_service = BulkOperationService()