"""
Enhanced Super Admin Endpoints with Improved Error Handling and Bulk Operations
Provides comprehensive bulk operation capabilities and standardized error responses.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import Request, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, validator

from .super_admin import require_super_admin, super_admin_service, DiscordUser
from .super_admin_error_handler import (
    handle_super_admin_errors, SuperAdminValidator, SuperAdminErrorType,
    super_admin_error_handler, SuperAdminError
)
from .super_admin_bulk_operations import (
    bulk_operation_service, BulkOperationType, BulkOperationRequest
)
from .database import get_db_session

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="templates")


# Pydantic models for request validation
class BulkOperationRequestModel(BaseModel):
    """Request model for bulk operations"""
    operation_type: str
    poll_ids: List[int]
    parameters: Dict[str, Any] = {}
    confirmation_code: Optional[str] = None
    
    @validator('operation_type')
    def validate_operation_type(cls, v):
        valid_types = [op.value for op in BulkOperationType]
        if v not in valid_types:
            raise ValueError(f"Invalid operation type. Must be one of: {valid_types}")
        return v
    
    @validator('poll_ids')
    def validate_poll_ids(cls, v):
        if not v:
            raise ValueError("At least one poll ID must be provided")
        if len(v) > 1000:
            raise ValueError("Maximum 1000 poll IDs allowed per operation")
        for poll_id in v:
            if not isinstance(poll_id, int) or poll_id <= 0:
                raise ValueError(f"Invalid poll ID: {poll_id}")
        return v


class SelectionUpdateModel(BaseModel):
    """Request model for selection updates"""
    action: str  # add, remove, set, clear
    poll_ids: Optional[List[int]] = None
    
    @validator('action')
    def validate_action(cls, v):
        valid_actions = ['add', 'remove', 'set', 'clear']
        if v not in valid_actions:
            raise ValueError(f"Invalid action. Must be one of: {valid_actions}")
        return v


class FilterSelectionModel(BaseModel):
    """Request model for filter-based selection"""
    status: Optional[str] = None
    server_id: Optional[str] = None
    creator_id: Optional[str] = None
    limit: Optional[int] = 1000


# In-memory selection store (in production, use Redis)
class SelectionManager:
    def __init__(self):
        self._selections: Dict[str, set] = {}
    
    def get_selection(self, admin_user_id: str) -> set:
        return self._selections.get(admin_user_id, set())
    
    def update_selection(self, admin_user_id: str, action: str, poll_ids: Optional[List[int]] = None):
        current_selection = self.get_selection(admin_user_id)
        
        if action == "clear":
            self._selections[admin_user_id] = set()
        elif action == "set" and poll_ids:
            self._selections[admin_user_id] = set(poll_ids)
        elif action == "add" and poll_ids:
            current_selection.update(poll_ids)
            self._selections[admin_user_id] = current_selection
        elif action == "remove" and poll_ids:
            current_selection.difference_update(poll_ids)
            self._selections[admin_user_id] = current_selection
        
        return self.get_selection(admin_user_id)


selection_manager = SelectionManager()


# Enhanced endpoints with improved error handling

@handle_super_admin_errors(operation_name="get_enhanced_dashboard")
async def get_enhanced_super_admin_dashboard(
    request: Request, 
    current_user: DiscordUser = Depends(require_super_admin)
) -> HTMLResponse:
    """Enhanced super admin dashboard with bulk operations support"""
    
    # Get dashboard stats with enhanced error handling
    db = get_db_session()
    try:
        stats = super_admin_service.get_system_stats(db)
        
        # Get queue status for bulk operations
        queue_status = await bulk_operation_service.get_queue_status()
        
        # Get recent operations for this admin
        recent_operations = await bulk_operation_service.list_operations(
            admin_user_id=current_user.id, 
            limit=10
        )
        
        # Get current selection count
        selection_count = len(selection_manager.get_selection(current_user.id))
        
        return templates.TemplateResponse(
            "super_admin_dashboard_enhanced.html",
            {
                "request": request,
                "user": current_user,
                "stats": stats,
                "queue_status": queue_status,
                "recent_operations": recent_operations,
                "selection_count": selection_count,
                "is_super_admin": True
            }
        )
    finally:
        db.close()


@handle_super_admin_errors(operation_name="start_bulk_operation")
async def start_bulk_operation_api(
    request: Request,
    bulk_request: BulkOperationRequestModel,
    background_tasks: BackgroundTasks,
    current_user: DiscordUser = Depends(require_super_admin)
) -> JSONResponse:
    """Start a new bulk operation with comprehensive validation"""
    
    # Additional validation for destructive operations
    if bulk_request.operation_type in ["delete_polls"] and not bulk_request.confirmation_code:
        raise SuperAdminError(
            error_type=SuperAdminErrorType.VALIDATION,
            code="CONFIRMATION_REQUIRED",
            message="Confirmation code is required for destructive operations",
            details={
                "field": "confirmation_code",
                "required_for": bulk_request.operation_type
            },
            suggestions=["Provide confirmation code to proceed with destructive operations"]
        )
    
    # Create bulk operation request
    operation_request = BulkOperationRequest(
        operation_type=BulkOperationType(bulk_request.operation_type),
        poll_ids=bulk_request.poll_ids,
        parameters=bulk_request.parameters,
        admin_user_id=current_user.id,
        confirmation_code=bulk_request.confirmation_code
    )
    
    try:
        operation_id = await bulk_operation_service.start_bulk_operation(operation_request)
        
        logger.info(
            f"Bulk operation started: operation_id={operation_id} "
            f"type={bulk_request.operation_type} admin_user_id={current_user.id} "
            f"poll_count={len(bulk_request.poll_ids)}"
        )
        
        return {
            "operation_id": operation_id,
            "status": "started",
            "poll_count": len(bulk_request.poll_ids),
            "operation_type": bulk_request.operation_type
        }
        
    except Exception as e:
        raise SuperAdminError(
            error_type=SuperAdminErrorType.SYSTEM,
            code="BULK_OPERATION_START_FAILED",
            message=f"Failed to start bulk operation: {str(e)}",
            original_error=str(e),
            suggestions=[
                "Check system capacity and try again",
                "Reduce the number of polls in the operation"
            ]
        )


@handle_super_admin_errors(operation_name="get_bulk_operation_progress")
async def get_bulk_operation_progress_api(
    operation_id: str,
    request: Request,
    current_user: DiscordUser = Depends(require_super_admin)
) -> JSONResponse:
    """Get progress for a specific bulk operation"""
    
    progress = await bulk_operation_service.get_operation_progress(operation_id)
    
    if not progress:
        raise SuperAdminError(
            error_type=SuperAdminErrorType.NOT_FOUND,
            code="OPERATION_NOT_FOUND",
            message=f"Bulk operation {operation_id} not found",
            details={
                "operation_id": operation_id
            },
            suggestions=["Verify the operation ID is correct"]
        )
    
    # Check if user has permission to view this operation
    if progress.admin_user_id != current_user.id:
        raise SuperAdminError(
            error_type=SuperAdminErrorType.PERMISSION,
            code="OPERATION_ACCESS_DENIED",
            message="You don't have permission to view this operation",
            details={
                "operation_id": operation_id
            }
        )
    
    return {
        "operation_id": progress.operation_id,
        "operation_type": progress.operation_type.value,
        "status": progress.status.value,
        "total_items": progress.total_items,
        "processed_items": progress.processed_items,
        "successful_items": progress.successful_items,
        "failed_items": progress.failed_items,
        "progress_percentage": progress.progress_percentage,
        "success_rate": progress.success_rate,
        "current_item_id": progress.current_item_id,
        "current_item_name": progress.current_item_name,
        "start_time": progress.start_time.isoformat(),
        "estimated_completion_time": progress.estimated_completion_time.isoformat() if progress.estimated_completion_time else None,
        "completion_time": progress.completion_time.isoformat() if progress.completion_time else None,
        "errors": [
            {
                "item_id": error.item_id,
                "error_code": error.error_code,
                "message": error.message,
                "timestamp": error.timestamp.isoformat()
            }
            for error in progress.errors[-10:]  # Last 10 errors
        ]
    }


@handle_super_admin_errors(operation_name="cancel_bulk_operation")
async def cancel_bulk_operation_api(
    operation_id: str,
    request: Request,
    current_user: DiscordUser = Depends(require_super_admin)
) -> JSONResponse:
    """Cancel a running bulk operation"""
    
    success = await bulk_operation_service.cancel_operation(operation_id, current_user.id)
    
    if not success:
        raise SuperAdminError(
            error_type=SuperAdminErrorType.CONFLICT,
            code="OPERATION_CANCEL_FAILED",
            message="Unable to cancel operation",
            details={
                "operation_id": operation_id
            },
            suggestions=[
                "Operation may have already completed",
                "You may not have permission to cancel this operation"
            ]
        )
    
    return {
        "operation_id": operation_id,
        "status": "cancelled",
        "cancelled_by": current_user.id,
        "cancelled_at": datetime.now().isoformat()
    }


@handle_super_admin_errors(operation_name="list_bulk_operations")
async def list_bulk_operations_api(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    current_user: DiscordUser = Depends(require_super_admin)
) -> JSONResponse:
    """List bulk operations for the current admin"""
    
    operations = await bulk_operation_service.list_operations(
        admin_user_id=current_user.id,
        limit=limit
    )
    
    return [
        {
            "operation_id": op.operation_id,
            "operation_type": op.operation_type.value,
            "status": op.status.value,
            "total_items": op.total_items,
            "successful_items": op.successful_items,
            "failed_items": op.failed_items,
            "progress_percentage": op.progress_percentage,
            "start_time": op.start_time.isoformat(),
            "completion_time": op.completion_time.isoformat() if op.completion_time else None
        }
        for op in operations
    ]


@handle_super_admin_errors(operation_name="get_selection")
async def get_selection_api(
    request: Request,
    current_user: DiscordUser = Depends(require_super_admin)
) -> JSONResponse:
    """Get current poll selection for the admin"""
    
    selection = selection_manager.get_selection(current_user.id)
    
    return {
        "selected_poll_ids": list(selection),
        "selection_count": len(selection)
    }


@handle_super_admin_errors(operation_name="update_selection")
async def update_selection_api(
    request: Request,
    selection_update: SelectionUpdateModel,
    current_user: DiscordUser = Depends(require_super_admin)
) -> JSONResponse:
    """Update poll selection for the admin"""
    
    updated_selection = selection_manager.update_selection(
        admin_user_id=current_user.id,
        action=selection_update.action,
        poll_ids=selection_update.poll_ids
    )
    
    return {
        "action": selection_update.action,
        "selected_poll_ids": list(updated_selection),
        "selection_count": len(updated_selection)
    }


@handle_super_admin_errors(operation_name="select_by_filter")
async def select_by_filter_api(
    request: Request,
    filter_request: FilterSelectionModel,
    current_user: DiscordUser = Depends(require_super_admin)
) -> JSONResponse:
    """Select polls based on filters"""
    
    db = get_db_session()
    try:
        # Get polls matching the filter
        result = super_admin_service.get_all_polls(
            db,
            status_filter=filter_request.status,
            server_filter=filter_request.server_id,
            creator_filter=filter_request.creator_id,
            limit=filter_request.limit or 1000,
            offset=0
        )
        
        poll_ids = [poll["id"] for poll in result["polls"]]
        
        # Update selection
        updated_selection = selection_manager.update_selection(
            admin_user_id=current_user.id,
            action="set",
            poll_ids=poll_ids
        )
        
        return {
            "filter_applied": {
                "status": filter_request.status,
                "server_id": filter_request.server_id,
                "creator_id": filter_request.creator_id
            },
            "polls_found": len(poll_ids),
            "selected_poll_ids": list(updated_selection),
            "selection_count": len(updated_selection)
        }
        
    finally:
        db.close()


@handle_super_admin_errors(operation_name="get_enhanced_polls_table", return_html=True)
async def get_enhanced_polls_htmx(
    request: Request,
    status: Optional[str] = Query(None),
    server: Optional[str] = Query(None),
    creator: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    current_user: DiscordUser = Depends(require_super_admin)
) -> HTMLResponse:
    """Enhanced HTMX endpoint for polls table with bulk selection support"""
    
    # Validate pagination
    validation_error = SuperAdminValidator.validate_pagination_params(25, (page - 1) * 25)
    if validation_error:
        raise validation_error
    
    db = get_db_session()
    try:
        limit = 25
        offset = (page - 1) * limit
        
        result = super_admin_service.get_all_polls(
            db,
            status_filter=status,
            server_filter=server,
            creator_filter=creator,
            limit=limit,
            offset=offset,
            sort_by="created_at",
            sort_order="desc"
        )
        
        # Get current selection
        selected_polls = selection_manager.get_selection(current_user.id)
        
        # Add selection status to polls
        for poll in result["polls"]:
            poll["is_selected"] = poll["id"] in selected_polls
            poll["creator_username"] = f"User {poll['creator_id'][:8]}..." if poll["creator_id"] else "Unknown"
        
        return templates.TemplateResponse(
            "htmx/super_admin_polls_table_enhanced.html",
            {
                "request": request,
                "polls": result["polls"],
                "total_count": result["total_count"],
                "current_page": page,
                "has_more": result["has_more"],
                "selection_count": len(selected_polls),
                "filters": {
                    "status": status,
                    "server": server,
                    "creator": creator
                }
            }
        )
        
    finally:
        db.close()


@handle_super_admin_errors(operation_name="get_queue_status")
async def get_queue_status_api(
    request: Request,
    current_user: DiscordUser = Depends(require_super_admin)
) -> JSONResponse:
    """Get current bulk operations queue status"""
    
    queue_status = await bulk_operation_service.get_queue_status()
    
    return queue_status


def add_enhanced_super_admin_routes(app):
    """Add enhanced super admin routes to the FastAPI app"""
    
    # Enhanced dashboard
    @app.get("/super-admin-enhanced", response_class=HTMLResponse)
    async def enhanced_super_admin_dashboard(
        request: Request, current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await get_enhanced_super_admin_dashboard(request, current_user)
    
    # Bulk operations
    @app.post("/super-admin/api/bulk/operation")
    async def start_bulk_operation(
        request: Request,
        bulk_request: BulkOperationRequestModel,
        background_tasks: BackgroundTasks,
        current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await start_bulk_operation_api(request, bulk_request, background_tasks, current_user)
    
    @app.get("/super-admin/api/bulk/operation/{operation_id}/progress")
    async def get_bulk_operation_progress(
        operation_id: str,
        request: Request,
        current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await get_bulk_operation_progress_api(operation_id, request, current_user)
    
    @app.post("/super-admin/api/bulk/operation/{operation_id}/cancel")
    async def cancel_bulk_operation(
        operation_id: str,
        request: Request,
        current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await cancel_bulk_operation_api(operation_id, request, current_user)
    
    @app.get("/super-admin/api/bulk/operations")
    async def list_bulk_operations(
        request: Request,
        limit: int = Query(50, ge=1, le=200),
        current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await list_bulk_operations_api(request, limit, current_user)
    
    # Selection management
    @app.get("/super-admin/api/bulk/selection")
    async def get_selection(
        request: Request,
        current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await get_selection_api(request, current_user)
    
    @app.post("/super-admin/api/bulk/selection")
    async def update_selection(
        request: Request,
        selection_update: SelectionUpdateModel,
        current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await update_selection_api(request, selection_update, current_user)
    
    @app.post("/super-admin/api/bulk/selection/filter")
    async def select_by_filter(
        request: Request,
        filter_request: FilterSelectionModel,
        current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await select_by_filter_api(request, filter_request, current_user)
    
    # Enhanced HTMX endpoints
    @app.get("/super-admin/htmx/polls-enhanced", response_class=HTMLResponse)
    async def enhanced_polls_htmx_main(
        request: Request,
        status: Optional[str] = Query(None),
        server: Optional[str] = Query(None),
        creator: Optional[str] = Query(None),
        page: int = Query(1, ge=1),
        current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await get_enhanced_polls_htmx(request, status, server, creator, page, current_user)
    
    @app.get("/super-admin-enhanced/htmx/polls", response_class=HTMLResponse)
    async def enhanced_polls_htmx(
        request: Request,
        status: Optional[str] = Query(None),
        server: Optional[str] = Query(None),
        creator: Optional[str] = Query(None),
        page: int = Query(1, ge=1),
        current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await get_enhanced_polls_htmx(request, status, server, creator, page, current_user)
    
    # Queue status
    @app.get("/super-admin/api/bulk/queue/status")
    async def get_queue_status(
        request: Request,
        current_user: DiscordUser = Depends(require_super_admin)
    ):
        return await get_queue_status_api(request, current_user)