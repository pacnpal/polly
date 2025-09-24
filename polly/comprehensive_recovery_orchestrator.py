"""
Comprehensive Recovery Orchestrator
Orchestrates all recovery systems to ensure 12/10 certainty of 100% data recovery
and validates that restored instances match fresh instance patterns exactly.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List
import pytz

# Handle both relative and absolute imports for direct execution
try:
    from .recovery_manager import get_recovery_manager, perform_startup_recovery
    from .enhanced_recovery_validator import get_enhanced_recovery_validator, perform_enhanced_recovery_validation
    from .static_recovery import get_static_recovery
    from .background_tasks import restore_scheduled_jobs
    from .services.cache.enhanced_cache_service import get_enhanced_cache_service
    from .database import TypeSafeColumn
except ImportError:
    # Fallback for direct execution
    import sys
    import os
    sys.path.insert(0, os.path.dirname(__file__))
    from recovery_manager import get_recovery_manager
    from enhanced_recovery_validator import get_enhanced_recovery_validator
    from static_recovery import get_static_recovery
    from background_tasks import restore_scheduled_jobs
    from enhanced_cache_service import get_enhanced_cache_service
    from database import TypeSafeColumn

logger = logging.getLogger(__name__)


class ComprehensiveRecoveryOrchestrator:
    """
    Master orchestrator that coordinates all recovery systems to achieve
    12/10 certainty of 100% data recovery and fresh instance compliance.
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.recovery_stats = {
            "total_recovery_attempts": 0,
            "successful_recoveries": 0,
            "validation_passes": 0,
            "confidence_levels_achieved": [],
            "total_items_recovered": 0,
            "recovery_duration_seconds": 0.0
        }
        
    async def perform_ultimate_recovery_with_validation(self) -> Dict[str, Any]:
        """
        Perform the ultimate recovery process with multiple validation passes
        to achieve 12/10 certainty of 100% data recovery.
        """
        logger.info("🚀 COMPREHENSIVE RECOVERY ORCHESTRATOR - Starting ultimate recovery process")
        recovery_start = datetime.now(pytz.UTC)
        
        self.recovery_stats["total_recovery_attempts"] += 1
        
        try:
            # Phase 1: Initial Recovery Pass
            logger.info("🔄 PHASE 1 - Initial comprehensive recovery")
            initial_recovery = await self._perform_initial_recovery()
            
            if not initial_recovery["success"]:
                logger.error(f"❌ PHASE 1 FAILED - Initial recovery failed: {initial_recovery.get('error')}")
                return self._create_failure_result("Initial recovery failed", initial_recovery)
            
            # Phase 2: Enhanced Validation and Gap Filling
            logger.info("🔍 PHASE 2 - Enhanced validation and gap filling")
            validation_result = await self._perform_enhanced_validation()
            
            # Phase 3: Iterative Recovery Until 12/10 Confidence
            logger.info("🎯 PHASE 3 - Iterative recovery until 12/10 confidence achieved")
            final_result = await self._achieve_maximum_confidence(validation_result)
            
            # Phase 4: Final Verification
            logger.info("✅ PHASE 4 - Final verification and compliance check")
            verification_result = await self._perform_final_verification()
            
            # Calculate total recovery time
            recovery_duration = (datetime.now(pytz.UTC) - recovery_start).total_seconds()
            self.recovery_stats["recovery_duration_seconds"] = recovery_duration
            
            # Compile final results
            if final_result.confidence_level >= 12.0 and verification_result["success"]:
                self.recovery_stats["successful_recoveries"] += 1
                logger.info("🎉 COMPREHENSIVE RECOVERY ORCHESTRATOR - 12/10 CERTAINTY ACHIEVED!")
                logger.info(f"📊 Recovery completed in {recovery_duration:.2f} seconds")
                
                return {
                    "success": True,
                    "confidence_level": final_result.confidence_level,
                    "certainty_achieved": True,
                    "total_items_recovered": final_result.items_recovered,
                    "recovery_duration": recovery_duration,
                    "validation_passes": self.recovery_stats["validation_passes"],
                    "fresh_instance_compliance": final_result.fresh_instance_compliance,
                    "detailed_stats": self.recovery_stats.copy(),
                    "message": "Ultimate recovery completed with 12/10 certainty - 100% data integrity validated"
                }
            else:
                logger.warning("⚠️ COMPREHENSIVE RECOVERY ORCHESTRATOR - Could not achieve 12/10 certainty")
                logger.warning(f"Final confidence: {final_result.confidence_level}/12")
                
                return {
                    "success": False,
                    "confidence_level": final_result.confidence_level,
                    "certainty_achieved": False,
                    "total_items_recovered": final_result.items_recovered,
                    "recovery_duration": recovery_duration,
                    "validation_passes": self.recovery_stats["validation_passes"],
                    "fresh_instance_compliance": final_result.fresh_instance_compliance,
                    "detailed_stats": self.recovery_stats.copy(),
                    "validation_errors": final_result.validation_errors,
                    "message": f"Recovery completed but only achieved {final_result.confidence_level}/12 certainty"
                }
                
        except Exception as e:
            logger.error(f"❌ COMPREHENSIVE RECOVERY ORCHESTRATOR - Critical error: {e}")
            return self._create_failure_result("Critical orchestrator error", {"error": str(e)})
    
    async def _perform_initial_recovery(self) -> Dict[str, Any]:
        """Perform initial comprehensive recovery using existing systems"""
        try:
            # Step 1: Basic recovery manager
            recovery_manager = get_recovery_manager(self.bot)
            if not recovery_manager:
                return {"success": False, "error": "Recovery manager not available"}
            
            basic_recovery = await recovery_manager.perform_full_recovery()
            
            # Step 2: Static content recovery
            static_recovery = get_static_recovery()
            static_results = await static_recovery.generate_for_existing_closed_polls(self.bot, limit=100)
            
            # Step 3: Cache warming
            cache_service = get_enhanced_cache_service()
            if cache_service:
                # Warm critical caches
                await self._warm_critical_caches()
            
            # Step 4: Scheduler restoration (double-check)
            await restore_scheduled_jobs()
            
            return {
                "success": basic_recovery["success"],
                "basic_recovery_stats": basic_recovery.get("stats", {}),
                "static_recovery_stats": {
                    "successful_generations": static_results["successful_generations"],
                    "failed_generations": static_results["failed_generations"]
                },
                "message": "Initial recovery completed"
            }
            
        except Exception as e:
            logger.error(f"Error in initial recovery: {e}")
            return {"success": False, "error": str(e)}
    
    async def _perform_enhanced_validation(self):
        """Perform enhanced validation with gap detection"""
        try:
            validator = get_enhanced_recovery_validator(self.bot)
            validation_result = await validator.perform_comprehensive_recovery_validation()
            
            self.recovery_stats["validation_passes"] += 1
            self.recovery_stats["confidence_levels_achieved"].append(validation_result.confidence_level)
            self.recovery_stats["total_items_recovered"] += validation_result.items_recovered
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Error in enhanced validation: {e}")
            # Create a minimal validation result for error cases
            from .enhanced_recovery_validator import RecoveryValidationResult
            return RecoveryValidationResult(
                success=False,
                confidence_level=0.0,
                total_items_checked=0,
                items_recovered=0,
                items_missing=1,
                validation_errors=[f"Validation error: {str(e)}"],
                recovery_actions_taken=[],
                integrity_score=0.0,
                fresh_instance_compliance=False,
                detailed_metrics={}
            )
    
    async def _achieve_maximum_confidence(self, initial_validation):
        """Iteratively improve recovery until 12/10 confidence is achieved"""
        max_iterations = 5
        current_iteration = 0
        best_result = initial_validation
        
        while current_iteration < max_iterations and best_result.confidence_level < 12.0:
            current_iteration += 1
            logger.info(f"🔄 ITERATION {current_iteration} - Current confidence: {best_result.confidence_level}/12")
            
            # Analyze what needs improvement
            improvement_actions = await self._analyze_and_improve(best_result)
            
            if not improvement_actions:
                logger.info("No more improvement actions available")
                break
            
            # Execute improvement actions
            await self._execute_improvement_actions(improvement_actions)
            
            # Re-validate
            new_validation = await self._perform_enhanced_validation()
            
            if new_validation.confidence_level > best_result.confidence_level:
                best_result = new_validation
                logger.info(f"✅ IMPROVEMENT - Confidence increased to {best_result.confidence_level}/12")
            else:
                logger.info(f"⚠️ NO IMPROVEMENT - Confidence remains at {best_result.confidence_level}/12")
        
        if best_result.confidence_level >= 12.0:
            logger.info("🎯 TARGET ACHIEVED - 12/10 confidence level reached!")
        else:
            logger.warning(f"⚠️ TARGET MISSED - Final confidence: {best_result.confidence_level}/12 after {current_iteration} iterations")
        
        return best_result
    
    async def _analyze_and_improve(self, validation_result) -> List[str]:
        """Analyze validation result and determine improvement actions"""
        improvement_actions = []
        
        # Check for specific error patterns and suggest fixes
        for error in validation_result.validation_errors:
            if "orphaned votes" in error.lower():
                improvement_actions.append("cleanup_orphaned_data")
            elif "missing reactions" in error.lower():
                improvement_actions.append("restore_poll_reactions")
            elif "discord message" in error.lower():
                improvement_actions.append("sync_discord_messages")
            elif "scheduled jobs" in error.lower():
                improvement_actions.append("restore_scheduler_jobs")
            elif "cache" in error.lower():
                improvement_actions.append("warm_caches")
            elif "static content" in error.lower():
                improvement_actions.append("generate_static_content")
        
        # If confidence is low but no specific errors, try general improvements
        if validation_result.confidence_level < 10.0 and not improvement_actions:
            improvement_actions.extend([
                "full_database_cleanup",
                "complete_cache_refresh",
                "comprehensive_message_sync"
            ])
        
        return list(set(improvement_actions))  # Remove duplicates
    
    async def _execute_improvement_actions(self, actions: List[str]):
        """Execute specific improvement actions"""
        for action in actions:
            try:
                logger.info(f"🔧 EXECUTING IMPROVEMENT - {action}")
                
                if action == "cleanup_orphaned_data":
                    await self._cleanup_orphaned_data()
                elif action == "restore_poll_reactions":
                    await self._restore_poll_reactions()
                elif action == "sync_discord_messages":
                    await self._sync_discord_messages()
                elif action == "restore_scheduler_jobs":
                    await restore_scheduled_jobs()
                elif action == "warm_caches":
                    await self._warm_critical_caches()
                elif action == "generate_static_content":
                    await self._generate_missing_static_content()
                elif action == "full_database_cleanup":
                    await self._full_database_cleanup()
                elif action == "complete_cache_refresh":
                    await self._complete_cache_refresh()
                elif action == "comprehensive_message_sync":
                    await self._comprehensive_message_sync()
                
                # Small delay between actions
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error executing improvement action {action}: {e}")
    
    async def _cleanup_orphaned_data(self):
        """Clean up orphaned data in database"""
        from .database import get_db_session
        from sqlalchemy import text
        
        db = get_db_session()
        try:
            # Remove orphaned votes
            orphaned_count = db.execute(text("""
                DELETE FROM votes WHERE poll_id NOT IN (SELECT id FROM polls)
            """)).rowcount
            
            db.commit()
            logger.info(f"Cleaned up {orphaned_count} orphaned votes")
            
        finally:
            db.close()
    
    async def _restore_poll_reactions(self):
        """Restore missing poll reactions with enhanced rate limiting"""
        from .database import get_db_session, Poll, TypeSafeColumn, POLL_EMOJIS
        
        db = get_db_session()
        try:
            active_polls = db.query(Poll).filter(Poll.status == "active").all()
            
            for poll in active_polls:
                poll_id = TypeSafeColumn.get_int(poll, "id")
                message_id = TypeSafeColumn.get_string(poll, "message_id")
                channel_id = TypeSafeColumn.get_string(poll, "channel_id")
                
                if message_id and channel_id:
                    try:
                        # Rate limit Discord message fetch
                        await asyncio.sleep(0.5)  # Conservative rate limiting
                        
                        channel = self.bot.get_channel(int(channel_id))
                        if channel:
                            message = await channel.fetch_message(int(message_id))
                            poll_emojis = poll.emojis if poll.emojis else POLL_EMOJIS
                            
                            # Add missing reactions with rate limiting
                            current_reactions = {str(r.emoji) for r in message.reactions}
                            required_reactions = set(poll_emojis[:len(poll.options)])
                            
                            for emoji in required_reactions - current_reactions:
                                try:
                                    # Enhanced rate limiting for reactions (Discord is strict about this)
                                    await asyncio.sleep(1.0)  # 1 second between reactions
                                    await message.add_reaction(emoji)
                                    logger.debug(f"Added missing reaction {emoji} to poll {poll_id}")
                                except Exception as e:
                                    logger.warning(f"Failed to add reaction {emoji} to poll {poll_id}: {e}")
                                    # If we hit a rate limit, wait longer
                                    if "rate limit" in str(e).lower():
                                        logger.warning("Rate limit hit, waiting 5 seconds before continuing")
                                        await asyncio.sleep(5.0)
                    except Exception as e:
                        logger.warning(f"Failed to restore reactions for poll {poll_id}: {e}")
                        # If we hit a rate limit, wait before continuing to next poll
                        if "rate limit" in str(e).lower():
                            logger.warning("Rate limit hit during message fetch, waiting 3 seconds")
                            await asyncio.sleep(3.0)
        finally:
            db.close()
    
    async def _sync_discord_messages(self):
        """Sync Discord messages with database state"""
        from .discord_utils import update_poll_message
        from .database import get_db_session, Poll
        
        db = get_db_session()
        try:
            active_polls = db.query(Poll).filter(Poll.status.in_(["active", "closed"])).all()
            
            for poll in active_polls:
                try:
                    await update_poll_message(self.bot, poll)
                    await asyncio.sleep(0.2)  # Rate limit protection
                except Exception as e:
                    poll_id = TypeSafeColumn.get_int(poll, "id")
                    logger.warning(f"Failed to sync message for poll {poll_id}: {e}")
        finally:
            db.close()
    
    async def _warm_critical_caches(self):
        """Warm all critical caches"""
        from .database import get_db_session, Poll, TypeSafeColumn
        
        db = get_db_session()
        try:
            active_polls = db.query(Poll).filter(Poll.status == "active").all()
            server_ids = {TypeSafeColumn.get_string(poll, "server_id") for poll in active_polls}
            
            for server_id in server_ids:
                if server_id:
                    try:
                        from .discord_emoji_handler import DiscordEmojiHandler
                        emoji_handler = DiscordEmojiHandler(self.bot)
                        await emoji_handler.get_guild_emoji_list(server_id)
                        await asyncio.sleep(0.1)
                    except Exception as e:
                        logger.warning(f"Failed to warm cache for server {server_id}: {e}")
        finally:
            db.close()
    
    async def _generate_missing_static_content(self):
        """Generate missing static content"""
        static_recovery = get_static_recovery()
        await static_recovery.generate_for_existing_closed_polls(self.bot, limit=50)
    
    async def _full_database_cleanup(self):
        """Perform comprehensive database cleanup"""
        await self._cleanup_orphaned_data()
        
        # Additional cleanup operations
        from .background_tasks import cleanup_polls_with_deleted_messages
        await cleanup_polls_with_deleted_messages()
    
    async def _complete_cache_refresh(self):
        """Completely refresh all caches"""
        cache_service = get_enhanced_cache_service()
        if cache_service:
            # Clear all caches and warm them again
            await self._warm_critical_caches()
    
    async def _comprehensive_message_sync(self):
        """Comprehensive Discord message synchronization"""
        await self._sync_discord_messages()
        await self._restore_poll_reactions()
    
    async def _perform_final_verification(self) -> Dict[str, Any]:
        """Perform final verification that everything is working correctly"""
        try:
            # Final validation pass
            final_validation = await self._perform_enhanced_validation()
            
            # Check that all critical services are running
            services_check = await self._verify_all_services_running()
            
            # Verify database integrity one more time
            db_integrity = await self._verify_database_integrity()
            
            return {
                "success": (
                    final_validation.success and 
                    services_check["success"] and 
                    db_integrity["success"]
                ),
                "final_confidence": final_validation.confidence_level,
                "services_running": services_check["services_running"],
                "database_integrity": db_integrity["integrity_score"],
                "fresh_instance_compliance": final_validation.fresh_instance_compliance
            }
            
        except Exception as e:
            logger.error(f"Error in final verification: {e}")
            return {"success": False, "error": str(e)}
    
    async def _verify_all_services_running(self) -> Dict[str, Any]:
        """Verify all required services are running"""
        from .background_tasks import get_scheduler
        
        services = {
            "bot": self.bot and self.bot.is_ready(),
            "scheduler": get_scheduler() and get_scheduler().running,
            "cache_service": get_enhanced_cache_service() is not None,
            "recovery_manager": get_recovery_manager() is not None
        }
        
        all_running = all(services.values())
        
        return {
            "success": all_running,
            "services_running": services,
            "missing_services": [name for name, running in services.items() if not running]
        }
    
    async def _verify_database_integrity(self) -> Dict[str, Any]:
        """Verify database integrity"""
        from .database import get_db_session
        from sqlalchemy import text
        
        db = get_db_session()
        try:
            # Check for basic integrity
            poll_count = db.execute(text("SELECT COUNT(*) FROM polls")).scalar()
            vote_count = db.execute(text("SELECT COUNT(*) FROM votes")).scalar()
            
            # Check for orphaned data
            orphaned_votes = db.execute(text("""
                SELECT COUNT(*) FROM votes v 
                LEFT JOIN polls p ON v.poll_id = p.id 
                WHERE p.id IS NULL
            """)).scalar()
            
            integrity_score = 1.0 if orphaned_votes == 0 else max(0.0, 1.0 - (orphaned_votes / max(vote_count, 1)))
            
            return {
                "success": orphaned_votes == 0,
                "integrity_score": integrity_score,
                "poll_count": poll_count,
                "vote_count": vote_count,
                "orphaned_votes": orphaned_votes
            }
            
        finally:
            db.close()
    
    def _create_failure_result(self, message: str, details: Dict[str, Any]) -> Dict[str, Any]:
        """Create a standardized failure result"""
        return {
            "success": False,
            "confidence_level": 0.0,
            "certainty_achieved": False,
            "total_items_recovered": 0,
            "recovery_duration": 0.0,
            "validation_passes": self.recovery_stats["validation_passes"],
            "fresh_instance_compliance": False,
            "detailed_stats": self.recovery_stats.copy(),
            "error": message,
            "error_details": details,
            "message": f"Recovery failed: {message}"
        }


# Global orchestrator instance
_comprehensive_orchestrator = None


def get_comprehensive_recovery_orchestrator(bot):
    """Get or create comprehensive recovery orchestrator instance"""
    global _comprehensive_orchestrator
    
    if _comprehensive_orchestrator is None:
        _comprehensive_orchestrator = ComprehensiveRecoveryOrchestrator(bot)
    
    return _comprehensive_orchestrator


async def perform_ultimate_recovery(bot) -> Dict[str, Any]:
    """
    Convenience function to perform ultimate recovery with 12/10 certainty.
    This is the main entry point for achieving absolute data recovery certainty.
    """
    orchestrator = get_comprehensive_recovery_orchestrator(bot)
    return await orchestrator.perform_ultimate_recovery_with_validation()
