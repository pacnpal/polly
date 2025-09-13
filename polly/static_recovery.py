"""
Static Content Recovery Module
Handles generation of static content for existing closed polls and recovery scenarios.
"""

import asyncio
import logging
from typing import Dict, Any, Optional

try:
    from .database import get_db_session, Poll, TypeSafeColumn
    from .static_page_generator import get_static_page_generator
except ImportError:
    from database import get_db_session, Poll, TypeSafeColumn  # type: ignore
    from static_page_generator import get_static_page_generator  # type: ignore


logger = logging.getLogger(__name__)


class StaticContentRecovery:
    """Handles recovery and batch generation of static content for existing polls"""
    
    def __init__(self):
        self.generator = get_static_page_generator()
        
    async def generate_for_existing_closed_polls(self, bot=None, limit: Optional[int] = None) -> Dict[str, Any]:
        """Generate static content for all existing closed polls that don't have it"""
        logger.info("🔄 STATIC RECOVERY - Starting generation for existing closed polls")
        
        results = {
            "total_closed_polls": 0,
            "polls_needing_static": 0,
            "successful_generations": 0,
            "failed_generations": 0,
            "processed_polls": [],
            "errors": []
        }
        
        db = get_db_session()
        try:
            # Get all closed polls
            query = db.query(Poll).filter(Poll.status == "closed")
            if limit:
                query = query.limit(limit)
            
            closed_polls = query.all()
            results["total_closed_polls"] = len(closed_polls)
            
            logger.info(f"📊 STATIC RECOVERY - Found {len(closed_polls)} closed polls")
            
            if not closed_polls:
                logger.info("✅ STATIC RECOVERY - No closed polls found")
                return results
            
            # Check which polls need static content generation
            polls_needing_static = []
            
            for poll in closed_polls:
                poll_id = TypeSafeColumn.get_int(poll, "id")
                poll_name = TypeSafeColumn.get_string(poll, "name", "Unknown")
                
                # Check if static content already exists
                details_exists = self.generator.static_page_exists(poll_id, "details")
                data_exists = self.generator._get_static_data_path(poll_id).exists()
                
                if not (details_exists and data_exists):
                    polls_needing_static.append({
                        "poll": poll,
                        "poll_id": poll_id,
                        "poll_name": poll_name,
                        "missing_details": not details_exists,
                        "missing_data": not data_exists
                    })
                    logger.info(f"📝 STATIC RECOVERY - Poll {poll_id} '{poll_name}' needs static content (details: {not details_exists}, data: {not data_exists})")
                else:
                    logger.debug(f"✅ STATIC RECOVERY - Poll {poll_id} '{poll_name}' already has static content")
            
            results["polls_needing_static"] = len(polls_needing_static)
            
            if not polls_needing_static:
                logger.info("✅ STATIC RECOVERY - All closed polls already have static content")
                return results
            
            logger.info(f"🔧 STATIC RECOVERY - Generating static content for {len(polls_needing_static)} polls")
            
            # Generate static content for each poll
            for poll_info in polls_needing_static:
                poll_id = poll_info["poll_id"]
                poll_name = poll_info["poll_name"]
                
                try:
                    logger.info(f"🔧 STATIC RECOVERY - Processing poll {poll_id}: '{poll_name}'")
                    
                    # Generate all static content
                    generation_results = await self.generator.generate_all_static_content(poll_id, bot)
                    
                    if all(generation_results.values()):
                        results["successful_generations"] += 1
                        logger.info(f"✅ STATIC RECOVERY - Successfully generated static content for poll {poll_id}")
                        
                        results["processed_polls"].append({
                            "poll_id": poll_id,
                            "poll_name": poll_name,
                            "status": "success",
                            "generated": generation_results
                        })
                    else:
                        results["failed_generations"] += 1
                        error_msg = f"Partial failure: {generation_results}"
                        results["errors"].append(f"Poll {poll_id}: {error_msg}")
                        logger.error(f"❌ STATIC RECOVERY - Partial failure for poll {poll_id}: {generation_results}")
                        
                        results["processed_polls"].append({
                            "poll_id": poll_id,
                            "poll_name": poll_name,
                            "status": "partial_failure",
                            "generated": generation_results,
                            "error": error_msg
                        })
                    
                    # Small delay to avoid overwhelming the system
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    results["failed_generations"] += 1
                    error_msg = f"Exception during generation: {str(e)}"
                    results["errors"].append(f"Poll {poll_id}: {error_msg}")
                    logger.error(f"❌ STATIC RECOVERY - Error generating static content for poll {poll_id}: {e}")
                    
                    results["processed_polls"].append({
                        "poll_id": poll_id,
                        "poll_name": poll_name,
                        "status": "error",
                        "error": error_msg
                    })
            
            logger.info(f"🎉 STATIC RECOVERY - Completed! Success: {results['successful_generations']}, Failed: {results['failed_generations']}")
            
        except Exception as e:
            logger.error(f"❌ STATIC RECOVERY - Critical error during recovery: {e}")
            results["errors"].append(f"Critical error: {str(e)}")
        finally:
            db.close()
        
        return results
    
    async def regenerate_all_static_content(self, bot=None, force: bool = False) -> Dict[str, Any]:
        """Regenerate static content for all closed polls (force regeneration)"""
        logger.info(f"🔄 STATIC RECOVERY - Starting {'forced ' if force else ''}regeneration for all closed polls")
        
        results = {
            "total_closed_polls": 0,
            "successful_regenerations": 0,
            "failed_regenerations": 0,
            "processed_polls": [],
            "errors": []
        }
        
        db = get_db_session()
        try:
            # Get all closed polls
            closed_polls = db.query(Poll).filter(Poll.status == "closed").all()
            results["total_closed_polls"] = len(closed_polls)
            
            logger.info(f"📊 STATIC RECOVERY - Found {len(closed_polls)} closed polls for regeneration")
            
            if not closed_polls:
                logger.info("✅ STATIC RECOVERY - No closed polls found")
                return results
            
            # Regenerate static content for each poll
            for poll in closed_polls:
                poll_id = TypeSafeColumn.get_int(poll, "id")
                poll_name = TypeSafeColumn.get_string(poll, "name", "Unknown")
                
                try:
                    logger.info(f"🔧 STATIC RECOVERY - Regenerating poll {poll_id}: '{poll_name}'")
                    
                    # If force is True, delete existing files first
                    if force:
                        await self.generator.cleanup_static_files(poll_id)
                        logger.debug(f"🧹 STATIC RECOVERY - Cleaned up existing files for poll {poll_id}")
                    
                    # Generate all static content
                    generation_results = await self.generator.generate_all_static_content(poll_id, bot)
                    
                    if all(generation_results.values()):
                        results["successful_regenerations"] += 1
                        logger.info(f"✅ STATIC RECOVERY - Successfully regenerated static content for poll {poll_id}")
                        
                        results["processed_polls"].append({
                            "poll_id": poll_id,
                            "poll_name": poll_name,
                            "status": "success",
                            "generated": generation_results
                        })
                    else:
                        results["failed_regenerations"] += 1
                        error_msg = f"Partial failure: {generation_results}"
                        results["errors"].append(f"Poll {poll_id}: {error_msg}")
                        logger.error(f"❌ STATIC RECOVERY - Partial failure for poll {poll_id}: {generation_results}")
                        
                        results["processed_polls"].append({
                            "poll_id": poll_id,
                            "poll_name": poll_name,
                            "status": "partial_failure",
                            "generated": generation_results,
                            "error": error_msg
                        })
                    
                    # Small delay to avoid overwhelming the system
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    results["failed_regenerations"] += 1
                    error_msg = f"Exception during regeneration: {str(e)}"
                    results["errors"].append(f"Poll {poll_id}: {error_msg}")
                    logger.error(f"❌ STATIC RECOVERY - Error regenerating static content for poll {poll_id}: {e}")
                    
                    results["processed_polls"].append({
                        "poll_id": poll_id,
                        "poll_name": poll_name,
                        "status": "error",
                        "error": error_msg
                    })
            
            logger.info(f"🎉 STATIC RECOVERY - Regeneration completed! Success: {results['successful_regenerations']}, Failed: {results['failed_regenerations']}")
            
        except Exception as e:
            logger.error(f"❌ STATIC RECOVERY - Critical error during regeneration: {e}")
            results["errors"].append(f"Critical error: {str(e)}")
        finally:
            db.close()
        
        return results
    
    async def verify_static_content_integrity(self) -> Dict[str, Any]:
        """Verify the integrity of existing static content"""
        logger.info("🔍 STATIC RECOVERY - Starting static content integrity verification")
        
        results = {
            "total_closed_polls": 0,
            "polls_with_complete_static": 0,
            "polls_with_partial_static": 0,
            "polls_with_no_static": 0,
            "integrity_issues": [],
            "summary": {}
        }
        
        db = get_db_session()
        try:
            # Get all closed polls
            closed_polls = db.query(Poll).filter(Poll.status == "closed").all()
            results["total_closed_polls"] = len(closed_polls)
            
            logger.info(f"📊 STATIC RECOVERY - Verifying {len(closed_polls)} closed polls")
            
            for poll in closed_polls:
                poll_id = TypeSafeColumn.get_int(poll, "id")
                poll_name = TypeSafeColumn.get_string(poll, "name", "Unknown")
                
                # Check static file existence
                details_exists = self.generator.static_page_exists(poll_id, "details")
                data_exists = self.generator._get_static_data_path(poll_id).exists()
                
                # Get file info
                file_info = await self.generator.get_static_file_info(poll_id)
                
                if details_exists and data_exists:
                    results["polls_with_complete_static"] += 1
                    logger.debug(f"✅ STATIC RECOVERY - Poll {poll_id} has complete static content")
                elif details_exists or data_exists:
                    results["polls_with_partial_static"] += 1
                    results["integrity_issues"].append({
                        "poll_id": poll_id,
                        "poll_name": poll_name,
                        "issue": "partial_static_content",
                        "details_exists": details_exists,
                        "data_exists": data_exists,
                        "file_info": file_info
                    })
                    logger.warning(f"⚠️ STATIC RECOVERY - Poll {poll_id} has partial static content")
                else:
                    results["polls_with_no_static"] += 1
                    results["integrity_issues"].append({
                        "poll_id": poll_id,
                        "poll_name": poll_name,
                        "issue": "no_static_content",
                        "details_exists": False,
                        "data_exists": False,
                        "file_info": file_info
                    })
                    logger.warning(f"⚠️ STATIC RECOVERY - Poll {poll_id} has no static content")
            
            # Create summary
            results["summary"] = {
                "complete_percentage": (results["polls_with_complete_static"] / results["total_closed_polls"] * 100) if results["total_closed_polls"] > 0 else 0,
                "issues_found": len(results["integrity_issues"]),
                "needs_attention": results["polls_with_partial_static"] + results["polls_with_no_static"]
            }
            
            logger.info(f"📊 STATIC RECOVERY - Verification complete: {results['polls_with_complete_static']}/{results['total_closed_polls']} polls have complete static content ({results['summary']['complete_percentage']:.1f}%)")
            
        except Exception as e:
            logger.error(f"❌ STATIC RECOVERY - Error during integrity verification: {e}")
            results["errors"] = [f"Critical error: {str(e)}"]
        finally:
            db.close()
        
        return results
    
    async def get_static_content_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics about static content"""
        logger.info("📊 STATIC RECOVERY - Gathering static content statistics")
        
        stats = {
            "total_polls": 0,
            "closed_polls": 0,
            "active_polls": 0,
            "scheduled_polls": 0,
            "static_content": {
                "complete": 0,
                "partial": 0,
                "none": 0,
                "total_files": 0,
                "total_size_bytes": 0
            },
            "file_breakdown": {
                "details_pages": 0,
                "data_files": 0
            }
        }
        
        db = get_db_session()
        try:
            # Get poll counts by status
            all_polls = db.query(Poll).all()
            stats["total_polls"] = len(all_polls)
            
            for poll in all_polls:
                status = TypeSafeColumn.get_string(poll, "status")
                if status == "closed":
                    stats["closed_polls"] += 1
                elif status == "active":
                    stats["active_polls"] += 1
                elif status == "scheduled":
                    stats["scheduled_polls"] += 1
            
            # Check static content for closed polls
            closed_polls = db.query(Poll).filter(Poll.status == "closed").all()
            
            for poll in closed_polls:
                poll_id = TypeSafeColumn.get_int(poll, "id")
                
                # Check file existence
                details_exists = self.generator.static_page_exists(poll_id, "details")
                data_exists = self.generator._get_static_data_path(poll_id).exists()
                
                if details_exists and data_exists:
                    stats["static_content"]["complete"] += 1
                elif details_exists or data_exists:
                    stats["static_content"]["partial"] += 1
                else:
                    stats["static_content"]["none"] += 1
                
                # Count individual files and sizes
                if details_exists:
                    stats["file_breakdown"]["details_pages"] += 1
                    stats["static_content"]["total_files"] += 1
                    
                if data_exists:
                    stats["file_breakdown"]["data_files"] += 1
                    stats["static_content"]["total_files"] += 1
                
                # Get file sizes
                file_info = await self.generator.get_static_file_info(poll_id)
                stats["static_content"]["total_size_bytes"] += file_info.get("total_size", 0)
            
            # Add human-readable size
            stats["static_content"]["total_size_mb"] = stats["static_content"]["total_size_bytes"] / (1024 * 1024)
            
            logger.info(f"📊 STATIC RECOVERY - Statistics gathered: {stats['static_content']['complete']}/{stats['closed_polls']} closed polls have complete static content")
            
        except Exception as e:
            logger.error(f"❌ STATIC RECOVERY - Error gathering statistics: {e}")
            stats["error"] = str(e)
        finally:
            db.close()
        
        return stats


# Global recovery instance
_static_recovery: Optional[StaticContentRecovery] = None


def get_static_recovery() -> StaticContentRecovery:
    """Get or create static content recovery instance"""
    global _static_recovery
    
    if _static_recovery is None:
        _static_recovery = StaticContentRecovery()
    
    return _static_recovery


async def run_static_content_recovery(bot=None, limit: Optional[int] = None) -> Dict[str, Any]:
    """Convenience function to run static content recovery for existing polls"""
    recovery = get_static_recovery()
    return await recovery.generate_for_existing_closed_polls(bot, limit)


async def run_static_content_regeneration(bot=None, force: bool = False) -> Dict[str, Any]:
    """Convenience function to regenerate all static content"""
    recovery = get_static_recovery()
    return await recovery.regenerate_all_static_content(bot, force)


async def verify_static_integrity() -> Dict[str, Any]:
    """Convenience function to verify static content integrity"""
    recovery = get_static_recovery()
    return await recovery.verify_static_content_integrity()


async def get_static_stats() -> Dict[str, Any]:
    """Convenience function to get static content statistics"""
    recovery = get_static_recovery()
    return await recovery.get_static_content_stats()
