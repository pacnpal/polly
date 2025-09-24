"""
Poll Edit Service
Unified poll editing service with status-appropriate restrictions.
Allows limited editing of active polls while maintaining data integrity.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List
import pytz

from ...database import get_db_session, Poll, TypeSafeColumn

logger = logging.getLogger(__name__)


class PollEditService:
    """Unified service for editing polls with status-appropriate restrictions"""

    # Define what fields can be edited for each poll status
    EDITABLE_FIELDS_BY_STATUS = {
        "scheduled": [
            # Scheduled polls can be fully edited
            "name", "description", "options", "emojis", "image_path", "image_message_text",
            "open_time", "close_time", "timezone", "channel_id", "server_id",
            "ping_role_enabled", "ping_role_id", "ping_role_name", "allowed_role_ids"
        ],
        "active": [
            # Active polls have limited editing to prevent vote invalidation
            "description",  # Safe - doesn't affect voting
            "close_time",   # Common admin need - extend poll time
            "options",      # Safe - adding new options doesn't invalidate existing votes
            "allowed_role_ids",  # Permission changes are safe
            "ping_role_enabled", "ping_role_id", "ping_role_name"  # Role ping settings
        ],
        "closed": [
            # Closed polls cannot be edited (use reopen service instead)
        ]
    }

    @staticmethod
    async def edit_poll_unified(
        poll_id: int,
        edit_data: Dict[str, Any],
        editor_user_id: str,
        editor_type: str = "user",  # "user", "admin", "super_admin"
        reason: str = "manual_edit"
    ) -> Dict[str, Any]:
        """
        Unified poll editing with appropriate restrictions based on poll status
        
        Args:
            poll_id: ID of the poll to edit
            edit_data: Dictionary of fields to update
            editor_user_id: ID of the user making the edit
            editor_type: Type of editor ("user", "admin", "super_admin")
            reason: Reason for editing
            
        Returns:
            Dict with success status and details
        """
        try:
            logger.info(f"✏️ UNIFIED EDIT {poll_id} - Starting poll edit by {editor_type} {editor_user_id}")
            
            # STEP 1: Get poll and validate access
            db = get_db_session()
            poll = None
            try:
                poll = db.query(Poll).filter(Poll.id == poll_id).first()
                if not poll:
                    logger.error(f"❌ UNIFIED EDIT {poll_id} - Poll not found")
                    return {"success": False, "error": "Poll not found"}

                current_status = TypeSafeColumn.get_string(poll, "status")
                poll_name = TypeSafeColumn.get_string(poll, "name", "Unknown")
                creator_id = TypeSafeColumn.get_string(poll, "creator_id")
                
                logger.info(f"📊 UNIFIED EDIT {poll_id} - Poll '{poll_name}' found, status: {current_status}")

                # STEP 2: Validate editor permissions
                if editor_type == "user":
                    if creator_id != editor_user_id:
                        logger.warning(f"❌ UNIFIED EDIT {poll_id} - Access denied: user {editor_user_id} is not poll creator")
                        return {"success": False, "error": "Access denied: you are not the poll creator"}
                # Admin and super_admin can edit any poll

                # STEP 3: Validate poll status allows editing
                if current_status not in PollEditService.EDITABLE_FIELDS_BY_STATUS:
                    logger.error(f"❌ UNIFIED EDIT {poll_id} - Invalid poll status for editing: {current_status}")
                    return {"success": False, "error": f"Polls with status '{current_status}' cannot be edited"}

                allowed_fields = PollEditService.EDITABLE_FIELDS_BY_STATUS[current_status]
                if not allowed_fields:
                    logger.error(f"❌ UNIFIED EDIT {poll_id} - No fields can be edited for status '{current_status}'")
                    return {"success": False, "error": f"Polls with status '{current_status}' cannot be edited"}

                # STEP 4: Validate requested edits against allowed fields
                restricted_fields = []
                valid_edits = {}
                
                for field, value in edit_data.items():
                    if field in allowed_fields:
                        valid_edits[field] = value
                    else:
                        restricted_fields.append(field)

                if restricted_fields:
                    logger.warning(f"⚠️ UNIFIED EDIT {poll_id} - Restricted fields for {current_status} polls: {restricted_fields}")
                    if not valid_edits:  # No valid edits at all
                        return {
                            "success": False, 
                            "error": f"Cannot edit {', '.join(restricted_fields)} on {current_status} polls",
                            "allowed_fields": allowed_fields,
                            "restricted_fields": restricted_fields
                        }

                # STEP 5: Validate specific field constraints
                validation_result = await PollEditService._validate_edit_data(
                    poll, valid_edits, current_status
                )
                if not validation_result["success"]:
                    return validation_result

                # STEP 6: Apply edits to database
                changes_made = []
                try:
                    for field, new_value in valid_edits.items():
                        old_value = getattr(poll, field, None)
                        if old_value != new_value:
                            setattr(poll, field, new_value)
                            changes_made.append(f"{field}: '{old_value}' → '{new_value}'")
                    
                    if changes_made:
                        db.commit()
                        logger.info(f"✅ UNIFIED EDIT {poll_id} - Database updated with {len(changes_made)} changes")
                    else:
                        logger.info(f"ℹ️ UNIFIED EDIT {poll_id} - No changes needed")

                except Exception as e:
                    db.rollback()
                    logger.error(f"❌ UNIFIED EDIT {poll_id} - Database update failed: {e}")
                    return {"success": False, "error": f"Database update failed: {str(e)}"}

            finally:
                db.close()

            # STEP 7: Handle Discord message updates for active polls
            discord_updated = False
            if current_status == "active" and changes_made:
                try:
                    discord_result = await PollEditService._update_discord_message(
                        poll_id, valid_edits
                    )
                    discord_updated = discord_result["success"]
                    if not discord_updated:
                        logger.warning(f"⚠️ UNIFIED EDIT {poll_id} - Discord update failed: {discord_result.get('error')}")
                except Exception as discord_error:
                    logger.error(f"❌ UNIFIED EDIT {poll_id} - Discord update error: {discord_error}")

            # STEP 8: Handle scheduler updates for close_time changes
            scheduler_updated = False
            if "close_time" in valid_edits and changes_made:
                try:
                    scheduler_result = await PollEditService._update_scheduler_for_close_time(
                        poll_id, valid_edits["close_time"], current_status
                    )
                    scheduler_updated = scheduler_result["success"]
                    if not scheduler_updated:
                        logger.warning(f"⚠️ UNIFIED EDIT {poll_id} - Scheduler update failed: {scheduler_result.get('error')}")
                except Exception as scheduler_error:
                    logger.error(f"❌ UNIFIED EDIT {poll_id} - Scheduler update error: {scheduler_error}")

            # STEP 9: Cache invalidation
            try:
                from ..cache.enhanced_cache_service import get_enhanced_cache_service
                
                enhanced_cache = get_enhanced_cache_service()
                if enhanced_cache and changes_made:
                    invalidated = await enhanced_cache.invalidate_poll_related_cache(poll_id)
                    logger.info(f"✅ UNIFIED EDIT {poll_id} - Invalidated {invalidated} cache entries")
                    
            except Exception as cache_error:
                logger.error(f"❌ UNIFIED EDIT {poll_id} - Cache invalidation error: {cache_error}")
                # Don't fail the edit if cache invalidation fails

            # Log the edit action
            logger.info(f"📝 Poll edit: poll_id={poll_id} editor_user_id={editor_user_id} editor_type={editor_type} reason={reason}")
            if changes_made:
                logger.info(f"📝 Changes made: {'; '.join(changes_made)}")

            result = {
                "success": True,
                "message": "Poll edited successfully" + (f" ({len(changes_made)} changes)" if changes_made else " (no changes)"),
                "poll_id": poll_id,
                "changes_made": len(changes_made),
                "changes_detail": changes_made,
                "discord_updated": discord_updated,
                "scheduler_updated": scheduler_updated if "close_time" in valid_edits else None,
                "poll_status": current_status,
                "editor_type": editor_type
            }

            if restricted_fields:
                result["warning"] = f"Some fields could not be edited: {', '.join(restricted_fields)}"
                result["restricted_fields"] = restricted_fields

            logger.info(f"🎉 UNIFIED EDIT {poll_id} - Poll edit process completed successfully")
            return result

        except Exception as e:
            logger.error(f"❌ UNIFIED EDIT {poll_id} - Unexpected error in poll editing: {str(e)}")
            return {
                "success": False,
                "error": f"Unexpected error during poll editing: {str(e)}",
                "poll_id": poll_id
            }

    @staticmethod
    async def _validate_edit_data(
        poll: Poll, 
        edit_data: Dict[str, Any], 
        current_status: str
    ) -> Dict[str, Any]:
        """Validate edit data for specific constraints"""
        try:
            errors = []

            # Validate close_time extension (common for active polls)
            if "close_time" in edit_data:
                new_close_time = edit_data["close_time"]
                if isinstance(new_close_time, datetime):
                    current_time = datetime.now(pytz.UTC)
                    if new_close_time <= current_time:
                        errors.append("Close time must be in the future")
                    
                    # For active polls, only allow extending time, not reducing it
                    if current_status == "active":
                        current_close_time = poll.close_time_aware
                        if current_close_time and new_close_time < current_close_time:
                            errors.append("Cannot reduce close time for active polls - only extensions allowed")

            # Validate description length
            if "description" in edit_data:
                description = edit_data["description"]
                if description and len(description) > 2000:
                    errors.append("Description cannot exceed 2000 characters")

            # Validate role permissions
            if "allowed_role_ids" in edit_data:
                role_ids = edit_data["allowed_role_ids"]
                if role_ids and not isinstance(role_ids, (list, str)):
                    errors.append("Allowed role IDs must be a list or string")

            # Validate options for active polls (only allow adding, not modifying/removing)
            if "options" in edit_data and current_status == "active":
                new_options = edit_data["options"]
                current_options = getattr(poll, "options", [])
                if isinstance(current_options, str):
                    import json
                    try:
                        current_options = json.loads(current_options)
                    except (json.JSONDecodeError, TypeError):
                        current_options = []
                current_options = current_options or []
                
                # Ensure all existing options are preserved
                if len(new_options) < len(current_options):
                    errors.append("Cannot remove options from active polls - only adding new options is allowed")
                else:
                    # Check that existing options haven't been modified
                    for i, current_option in enumerate(current_options):
                        if i >= len(new_options) or new_options[i] != current_option:
                            errors.append("Cannot modify existing options in active polls - only adding new options is allowed")
                            break
                    
                    # Log successful option addition
                    if len(new_options) > len(current_options):
                        added_count = len(new_options) - len(current_options)
                        logger.info(f"Adding {added_count} new options to active poll {poll.id}")

            if errors:
                return {"success": False, "error": "; ".join(errors), "validation_errors": errors}

            return {"success": True}

        except Exception as e:
            logger.error(f"Error validating edit data: {e}")
            return {"success": False, "error": f"Validation error: {str(e)}"}

    @staticmethod
    async def _update_discord_message(
        poll_id: int,
        edit_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update Discord message for polls when edited"""
        try:
            # Define fields that require Discord message updates
            discord_update_fields = ["description", "options", "close_time", "name"]
            
            # Check if any field requiring Discord update was changed
            needs_discord_update = any(field in edit_data for field in discord_update_fields)
            
            if not needs_discord_update:
                logger.info(f"📝 DISCORD UPDATE {poll_id} - No fields requiring Discord update were changed")
                return {"success": True, "message": "No Discord update needed"}

            logger.info(f"🔄 DISCORD UPDATE {poll_id} - Discord update needed for: {[f for f in discord_update_fields if f in edit_data]}")

            # Get bot instance
            from ...discord_bot import get_bot_instance
            bot_instance = get_bot_instance()
            
            if not bot_instance:
                logger.error(f"❌ DISCORD UPDATE {poll_id} - Bot instance not available")
                return {"success": False, "error": "Bot instance not available"}

            # Update the poll message using the newly created function
            from ...discord_utils import update_poll_message_content
            
            result = await update_poll_message_content(bot_instance, poll_id)
            
            if result["success"]:
                logger.info(f"✅ DISCORD UPDATE {poll_id} - Discord message updated successfully")
            else:
                logger.warning(f"⚠️ DISCORD UPDATE {poll_id} - Discord update failed: {result.get('error')}")
                
            return result

        except Exception as e:
            logger.error(f"❌ DISCORD UPDATE {poll_id} - Error updating Discord message: {e}")
            return {"success": False, "error": f"Discord update failed: {str(e)}"}

    @staticmethod
    async def _update_scheduler_for_close_time(
        poll_id: int, 
        new_close_time: datetime, 
        poll_status: str
    ) -> Dict[str, Any]:
        """Update scheduler jobs when close_time is edited"""
        try:
            logger.info(f"🕒 SCHEDULER UPDATE {poll_id} - Starting scheduler update for new close time: {new_close_time}")
            
            # Only update scheduler for active and scheduled polls
            if poll_status not in ["active", "scheduled"]:
                logger.info(f"ℹ️ SCHEDULER UPDATE {poll_id} - No scheduler update needed for {poll_status} polls")
                return {"success": True, "message": f"No scheduler update needed for {poll_status} polls"}
            
            # Get scheduler instance
            from ...background_tasks import get_scheduler
            scheduler = get_scheduler()
            
            if not scheduler:
                logger.error(f"❌ SCHEDULER UPDATE {poll_id} - Scheduler instance not available")
                return {"success": False, "error": "Scheduler instance not available"}
                
            if not scheduler.running:
                logger.error(f"❌ SCHEDULER UPDATE {poll_id} - Scheduler is not running")
                return {"success": False, "error": "Scheduler is not running"}
            
            # Import required modules
            from ...timezone_scheduler_fix import TimezoneAwareScheduler
            from ...background_tasks import close_poll
            
            # Get poll timezone from database
            db = get_db_session()
            try:
                poll = db.query(Poll).filter(Poll.id == poll_id).first()
                if not poll:
                    logger.error(f"❌ SCHEDULER UPDATE {poll_id} - Poll not found")
                    return {"success": False, "error": "Poll not found"}
                    
                poll_timezone = TypeSafeColumn.get_string(poll, "timezone", "UTC")
                
            finally:
                db.close()
            
            # Remove existing close job if it exists
            close_job_id = f"close_poll_{poll_id}"
            existing_job = scheduler.get_job(close_job_id)
            if existing_job:
                scheduler.remove_job(close_job_id)
                logger.info(f"🗑️ SCHEDULER UPDATE {poll_id} - Removed existing close job")
            
            # Check if new close time is in the future
            current_time = datetime.now(pytz.UTC)
            if new_close_time <= current_time:
                logger.warning(f"⚠️ SCHEDULER UPDATE {poll_id} - New close time {new_close_time} is in the past")
                return {
                    "success": False, 
                    "error": "Cannot schedule poll closing in the past",
                    "new_close_time": new_close_time.isoformat()
                }
            
            # Schedule new close job using timezone-aware scheduler
            tz_scheduler = TimezoneAwareScheduler(scheduler)
            success = tz_scheduler.schedule_poll_closing(
                poll_id, new_close_time, poll_timezone, close_poll
            )
            
            if success:
                logger.info(f"✅ SCHEDULER UPDATE {poll_id} - Successfully scheduled new close time: {new_close_time}")
                return {
                    "success": True,
                    "message": f"Poll {poll_id} rescheduled to close at {new_close_time}",
                    "new_close_time": new_close_time.isoformat(),
                    "timezone": poll_timezone
                }
            else:
                logger.error(f"❌ SCHEDULER UPDATE {poll_id} - Failed to schedule new close job")
                return {
                    "success": False,
                    "error": f"Failed to schedule new close time for poll {poll_id}",
                    "new_close_time": new_close_time.isoformat()
                }
                
        except Exception as e:
            logger.error(f"❌ SCHEDULER UPDATE {poll_id} - Error updating scheduler: {e}")
            return {
                "success": False, 
                "error": f"Scheduler update failed: {str(e)}",
                "poll_id": poll_id
            }

    @staticmethod
    def get_editable_fields(poll_status: str) -> List[str]:
        """Get list of fields that can be edited for a given poll status"""
        return PollEditService.EDITABLE_FIELDS_BY_STATUS.get(poll_status, [])

    @staticmethod
    def can_edit_field(poll_status: str, field_name: str) -> bool:
        """Check if a specific field can be edited for a given poll status"""
        allowed_fields = PollEditService.EDITABLE_FIELDS_BY_STATUS.get(poll_status, [])
        return field_name in allowed_fields


# Global service instance
poll_edit_service = PollEditService()