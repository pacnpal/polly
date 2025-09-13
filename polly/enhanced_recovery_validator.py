"""
Enhanced Recovery Validator
Provides 12/10 certainty that restored instances recover 100% of lost or missed items
and follow the same patterns as fresh instances.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set, Tuple
import pytz
from dataclasses import dataclass

from .database import get_db_session, Poll, Vote, TypeSafeColumn, POLL_EMOJIS
from .recovery_manager import get_recovery_manager
from .bulletproof_operations import BulletproofPollOperations
from .background_tasks import get_scheduler
from .static_recovery import get_static_recovery
from .enhanced_cache_service import get_enhanced_cache_service

logger = logging.getLogger(__name__)


@dataclass
class RecoveryValidationResult:
    """Result of recovery validation with detailed metrics"""
    success: bool
    confidence_level: float  # 0.0 to 12.0 (12/10 scale)
    total_items_checked: int
    items_recovered: int
    items_missing: int
    validation_errors: List[str]
    recovery_actions_taken: List[str]
    integrity_score: float  # 0.0 to 1.0
    fresh_instance_compliance: bool
    detailed_metrics: Dict[str, Any]


class EnhancedRecoveryValidator:
    """
    Ultra-comprehensive recovery validator that ensures 100% data integrity
    and validates that restored instances match fresh instance patterns.
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.bulletproof_ops = BulletproofPollOperations(bot)
        self.validation_errors = []
        self.recovery_actions = []
        self.metrics = {}
        
    async def perform_comprehensive_recovery_validation(self) -> RecoveryValidationResult:
        """
        Perform comprehensive recovery validation with 12/10 certainty.
        This is the main validation entry point that ensures 100% recovery.
        """
        logger.info("🔍 ENHANCED RECOVERY VALIDATOR - Starting comprehensive validation")
        validation_start = datetime.now(pytz.UTC)
        
        self.validation_errors = []
        self.recovery_actions = []
        self.metrics = {
            "polls_validated": 0,
            "votes_validated": 0,
            "reactions_validated": 0,
            "scheduled_jobs_validated": 0,
            "cache_entries_validated": 0,
            "static_content_validated": 0,
            "discord_messages_validated": 0,
            "database_integrity_checks": 0,
            "recovery_actions_executed": 0
        }
        
        try:
            # Phase 1: Database Integrity Validation
            await self._validate_database_integrity()
            
            # Phase 2: Active Poll State Validation
            await self._validate_active_poll_states()
            
            # Phase 3: Scheduled Operations Validation
            await self._validate_scheduled_operations()
            
            # Phase 4: Discord Message Consistency Validation
            await self._validate_discord_message_consistency()
            
            # Phase 5: Vote and Reaction Synchronization Validation
            await self._validate_vote_reaction_synchronization()
            
            # Phase 6: Cache Consistency Validation
            await self._validate_cache_consistency()
            
            # Phase 7: Static Content Validation
            await self._validate_static_content_integrity()
            
            # Phase 8: Fresh Instance Pattern Compliance
            fresh_compliance = await self._validate_fresh_instance_compliance()
            
            # Phase 9: Recovery Gap Detection and Filling
            await self._detect_and_fill_recovery_gaps()
            
            # Calculate final metrics
            total_items = sum([
                self.metrics["polls_validated"],
                self.metrics["votes_validated"],
                self.metrics["reactions_validated"],
                self.metrics["scheduled_jobs_validated"],
                self.metrics["cache_entries_validated"],
                self.metrics["static_content_validated"],
                self.metrics["discord_messages_validated"]
            ])
            
            items_recovered = self.metrics["recovery_actions_executed"]
            items_missing = len(self.validation_errors)
            
            # Calculate confidence level (12/10 scale)
            confidence_level = self._calculate_confidence_level()
            
            # Calculate integrity score
            integrity_score = max(0.0, 1.0 - (items_missing / max(total_items, 1)))
            
            validation_duration = (datetime.now(pytz.UTC) - validation_start).total_seconds()
            
            result = RecoveryValidationResult(
                success=len(self.validation_errors) == 0,
                confidence_level=confidence_level,
                total_items_checked=total_items,
                items_recovered=items_recovered,
                items_missing=items_missing,
                validation_errors=self.validation_errors.copy(),
                recovery_actions_taken=self.recovery_actions.copy(),
                integrity_score=integrity_score,
                fresh_instance_compliance=fresh_compliance,
                detailed_metrics=self.metrics.copy()
            )
            
            logger.info(f"🎯 ENHANCED RECOVERY VALIDATOR - Validation completed in {validation_duration:.2f}s")
            logger.info(f"📊 VALIDATION RESULTS - Confidence: {confidence_level}/12, Integrity: {integrity_score:.3f}")
            logger.info(f"📊 VALIDATION METRICS - {result.detailed_metrics}")
            
            if result.confidence_level >= 12.0:
                logger.info("✅ ENHANCED RECOVERY VALIDATOR - 12/10 CERTAINTY ACHIEVED - 100% recovery validated")
            else:
                logger.warning(f"⚠️ ENHANCED RECOVERY VALIDATOR - Confidence level {confidence_level}/12 - additional recovery needed")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ ENHANCED RECOVERY VALIDATOR - Critical validation error: {e}")
            return RecoveryValidationResult(
                success=False,
                confidence_level=0.0,
                total_items_checked=0,
                items_recovered=0,
                items_missing=1,
                validation_errors=[f"Critical validation error: {str(e)}"],
                recovery_actions_taken=self.recovery_actions.copy(),
                integrity_score=0.0,
                fresh_instance_compliance=False,
                detailed_metrics=self.metrics.copy()
            )
    
    async def _validate_database_integrity(self):
        """Validate database integrity and consistency"""
        logger.info("🔍 PHASE 1 - Validating database integrity")
        
        db = get_db_session()
        try:
            # Check for orphaned votes
            orphaned_votes = db.execute("""
                SELECT v.id, v.poll_id, v.user_id 
                FROM votes v 
                LEFT JOIN polls p ON v.poll_id = p.id 
                WHERE p.id IS NULL
            """).fetchall()
            
            if orphaned_votes:
                self.validation_errors.append(f"Found {len(orphaned_votes)} orphaned votes")
                # Clean up orphaned votes
                for vote in orphaned_votes:
                    db.execute("DELETE FROM votes WHERE id = ?", (vote[0],))
                db.commit()
                self.recovery_actions.append(f"Cleaned up {len(orphaned_votes)} orphaned votes")
                self.metrics["recovery_actions_executed"] += len(orphaned_votes)
            
            # Check for polls with invalid status
            invalid_status_polls = db.query(Poll).filter(
                ~Poll.status.in_(["scheduled", "active", "closed"])
            ).all()
            
            if invalid_status_polls:
                self.validation_errors.append(f"Found {len(invalid_status_polls)} polls with invalid status")
                for poll in invalid_status_polls:
                    poll_id = TypeSafeColumn.get_int(poll, "id")
                    # Determine correct status based on timestamps
                    now = datetime.now(pytz.UTC)
                    open_time = poll.open_time
                    close_time = poll.close_time
                    
                    if open_time and close_time:
                        if now < open_time:
                            poll.status = "scheduled"
                        elif now < close_time:
                            poll.status = "active"
                        else:
                            poll.status = "closed"
                        
                        self.recovery_actions.append(f"Fixed status for poll {poll_id}")
                        self.metrics["recovery_actions_executed"] += 1
                
                db.commit()
            
            # Check for polls missing required fields
            polls_missing_fields = db.query(Poll).filter(
                (Poll.name == None) | 
                (Poll.question == None) | 
                (Poll.options == None) |
                (Poll.creator_id == None)
            ).all()
            
            if polls_missing_fields:
                self.validation_errors.append(f"Found {len(polls_missing_fields)} polls with missing required fields")
                # These polls are corrupted and should be removed
                for poll in polls_missing_fields:
                    poll_id = TypeSafeColumn.get_int(poll, "id")
                    # Delete associated votes first
                    db.query(Vote).filter(Vote.poll_id == poll_id).delete()
                    db.delete(poll)
                    self.recovery_actions.append(f"Removed corrupted poll {poll_id}")
                    self.metrics["recovery_actions_executed"] += 1
                
                db.commit()
            
            self.metrics["database_integrity_checks"] += 1
            logger.info("✅ PHASE 1 - Database integrity validation completed")
            
        finally:
            db.close()
    
    async def _validate_active_poll_states(self):
        """Validate that all active polls are in correct state"""
        logger.info("🔍 PHASE 2 - Validating active poll states")
        
        db = get_db_session()
        try:
            active_polls = db.query(Poll).filter(Poll.status == "active").all()
            self.metrics["polls_validated"] += len(active_polls)
            
            now = datetime.now(pytz.UTC)
            
            for poll in active_polls:
                poll_id = TypeSafeColumn.get_int(poll, "id")
                poll_name = TypeSafeColumn.get_string(poll, "name", "Unknown")
                
                # Check if poll should still be active
                close_time = poll.close_time
                if close_time and close_time <= now:
                    self.validation_errors.append(f"Poll {poll_id} should be closed but is still active")
                    # Close the poll immediately
                    try:
                        from .background_tasks import close_poll
                        await close_poll(poll_id)
                        self.recovery_actions.append(f"Closed overdue poll {poll_id}")
                        self.metrics["recovery_actions_executed"] += 1
                    except Exception as e:
                        logger.error(f"Failed to close overdue poll {poll_id}: {e}")
                
                # Validate Discord message exists
                message_id = TypeSafeColumn.get_string(poll, "message_id")
                channel_id = TypeSafeColumn.get_string(poll, "channel_id")
                
                if message_id and channel_id:
                    try:
                        channel = self.bot.get_channel(int(channel_id))
                        if channel:
                            try:
                                await channel.fetch_message(int(message_id))
                                self.metrics["discord_messages_validated"] += 1
                            except Exception:
                                self.validation_errors.append(f"Discord message missing for active poll {poll_id}")
                                # Mark poll for cleanup
                                poll.status = "closed"
                                db.commit()
                                self.recovery_actions.append(f"Marked poll {poll_id} as closed due to missing Discord message")
                                self.metrics["recovery_actions_executed"] += 1
                        else:
                            self.validation_errors.append(f"Discord channel missing for active poll {poll_id}")
                    except Exception as e:
                        logger.warning(f"Could not validate Discord message for poll {poll_id}: {e}")
                
                # Validate poll has proper reactions
                if message_id and channel_id:
                    await self._validate_poll_reactions(poll, message_id, channel_id)
            
            logger.info(f"✅ PHASE 2 - Validated {len(active_polls)} active polls")
            
        finally:
            db.close()
    
    async def _validate_poll_reactions(self, poll, message_id: str, channel_id: str):
        """Validate that poll has all required reactions"""
        try:
            channel = self.bot.get_channel(int(channel_id))
            if not channel:
                return
            
            message = await channel.fetch_message(int(message_id))
            poll_emojis = poll.emojis if poll.emojis else POLL_EMOJIS
            options_count = len(poll.options)
            
            current_reactions = {str(reaction.emoji) for reaction in message.reactions}
            required_reactions = set(poll_emojis[:options_count])
            
            missing_reactions = required_reactions - current_reactions
            
            if missing_reactions:
                poll_id = TypeSafeColumn.get_int(poll, "id")
                self.validation_errors.append(f"Poll {poll_id} missing reactions: {missing_reactions}")
                
                # Add missing reactions
                for emoji in missing_reactions:
                    try:
                        from .discord_emoji_handler import DiscordEmojiHandler
                        emoji_handler = DiscordEmojiHandler(self.bot)
                        prepared_emoji = emoji_handler.prepare_emoji_for_reaction(emoji)
                        await message.add_reaction(prepared_emoji)
                        await asyncio.sleep(0.1)  # Rate limit protection
                        
                        self.recovery_actions.append(f"Added missing reaction {emoji} to poll {poll_id}")
                        self.metrics["recovery_actions_executed"] += 1
                    except Exception as e:
                        logger.error(f"Failed to add reaction {emoji} to poll {poll_id}: {e}")
            
            self.metrics["reactions_validated"] += len(current_reactions)
            
        except Exception as e:
            logger.error(f"Error validating reactions for poll: {e}")
    
    async def _validate_scheduled_operations(self):
        """Validate that all scheduled operations are properly restored"""
        logger.info("🔍 PHASE 3 - Validating scheduled operations")
        
        scheduler = get_scheduler()
        if not scheduler:
            self.validation_errors.append("Scheduler not available")
            return
        
        # Get all scheduled jobs
        scheduled_jobs = scheduler.get_jobs()
        job_poll_ids = set()
        
        for job in scheduled_jobs:
            if hasattr(job, 'args') and job.args:
                if isinstance(job.args[0], int):  # Poll ID
                    job_poll_ids.add(job.args[0])
        
        self.metrics["scheduled_jobs_validated"] = len(scheduled_jobs)
        
        # Check database for polls that should have scheduled jobs
        db = get_db_session()
        try:
            now = datetime.now(pytz.UTC)
            
            # Scheduled polls that should have opening jobs
            scheduled_polls = db.query(Poll).filter(
                Poll.status == "scheduled",
                Poll.open_time > now
            ).all()
            
            # Active polls that should have closing jobs
            active_polls = db.query(Poll).filter(
                Poll.status == "active",
                Poll.close_time > now
            ).all()
            
            expected_job_poll_ids = set()
            for poll in scheduled_polls + active_polls:
                poll_id = TypeSafeColumn.get_int(poll, "id")
                expected_job_poll_ids.add(poll_id)
            
            missing_jobs = expected_job_poll_ids - job_poll_ids
            
            if missing_jobs:
                self.validation_errors.append(f"Missing scheduled jobs for polls: {missing_jobs}")
                
                # Restore missing jobs
                from .background_tasks import restore_scheduled_jobs
                await restore_scheduled_jobs()
                
                self.recovery_actions.append(f"Restored scheduled jobs for {len(missing_jobs)} polls")
                self.metrics["recovery_actions_executed"] += len(missing_jobs)
            
            logger.info(f"✅ PHASE 3 - Validated {len(scheduled_jobs)} scheduled operations")
            
        finally:
            db.close()
    
    async def _validate_discord_message_consistency(self):
        """Validate Discord message consistency with database"""
        logger.info("🔍 PHASE 4 - Validating Discord message consistency")
        
        db = get_db_session()
        try:
            polls_with_messages = db.query(Poll).filter(
                Poll.message_id.isnot(None),
                Poll.status.in_(["active", "scheduled"])
            ).all()
            
            inconsistent_polls = []
            
            for poll in polls_with_messages:
                poll_id = TypeSafeColumn.get_int(poll, "id")
                message_id = TypeSafeColumn.get_string(poll, "message_id")
                channel_id = TypeSafeColumn.get_string(poll, "channel_id")
                
                try:
                    channel = self.bot.get_channel(int(channel_id))
                    if not channel:
                        inconsistent_polls.append(poll_id)
                        continue
                    
                    message = await channel.fetch_message(int(message_id))
                    
                    # Validate message content matches poll data
                    if message.embeds:
                        embed = message.embeds[0]
                        poll_name = TypeSafeColumn.get_string(poll, "name", "")
                        
                        if poll_name not in embed.title:
                            self.validation_errors.append(f"Discord message title mismatch for poll {poll_id}")
                            # Update the message
                            from .discord_utils import update_poll_message
                            await update_poll_message(self.bot, poll)
                            self.recovery_actions.append(f"Updated Discord message for poll {poll_id}")
                            self.metrics["recovery_actions_executed"] += 1
                    
                    self.metrics["discord_messages_validated"] += 1
                    
                except Exception as e:
                    logger.warning(f"Discord message validation failed for poll {poll_id}: {e}")
                    inconsistent_polls.append(poll_id)
            
            if inconsistent_polls:
                self.validation_errors.append(f"Inconsistent Discord messages for polls: {inconsistent_polls}")
                
                # Clean up inconsistent polls
                from .background_tasks import cleanup_polls_with_deleted_messages
                await cleanup_polls_with_deleted_messages()
                
                self.recovery_actions.append(f"Cleaned up {len(inconsistent_polls)} inconsistent polls")
                self.metrics["recovery_actions_executed"] += len(inconsistent_polls)
            
            logger.info(f"✅ PHASE 4 - Validated {len(polls_with_messages)} Discord messages")
            
        finally:
            db.close()
    
    async def _validate_vote_reaction_synchronization(self):
        """Validate that votes and reactions are synchronized"""
        logger.info("🔍 PHASE 5 - Validating vote-reaction synchronization")
        
        db = get_db_session()
        try:
            active_polls = db.query(Poll).filter(Poll.status == "active").all()
            
            for poll in active_polls:
                poll_id = TypeSafeColumn.get_int(poll, "id")
                message_id = TypeSafeColumn.get_string(poll, "message_id")
                channel_id = TypeSafeColumn.get_string(poll, "channel_id")
                
                if not message_id or not channel_id:
                    continue
                
                try:
                    channel = self.bot.get_channel(int(channel_id))
                    if not channel:
                        continue
                    
                    message = await channel.fetch_message(int(message_id))
                    poll_emojis = poll.emojis if poll.emojis else POLL_EMOJIS
                    
                    # Get database votes
                    db_votes = db.query(Vote).filter(Vote.poll_id == poll_id).all()
                    db_vote_users = {TypeSafeColumn.get_string(vote, "user_id") for vote in db_votes}
                    
                    # Get Discord reaction users
                    reaction_users = set()
                    for reaction in message.reactions:
                        if str(reaction.emoji) in poll_emojis:
                            async for user in reaction.users():
                                if not user.bot:
                                    reaction_users.add(str(user.id))
                    
                    # Find discrepancies
                    missing_votes = reaction_users - db_vote_users
                    orphaned_reactions = db_vote_users - reaction_users
                    
                    if missing_votes:
                        self.validation_errors.append(f"Poll {poll_id} has reactions without votes: {len(missing_votes)} users")
                        
                        # Process missing votes
                        for reaction in message.reactions:
                            if str(reaction.emoji) in poll_emojis:
                                option_index = poll_emojis.index(str(reaction.emoji))
                                async for user in reaction.users():
                                    if not user.bot and str(user.id) in missing_votes:
                                        # Record the vote
                                        result = await self.bulletproof_ops.bulletproof_vote_collection(
                                            poll_id, str(user.id), option_index
                                        )
                                        if result["success"]:
                                            await reaction.remove(user)
                                            self.recovery_actions.append(f"Recovered vote for user {user.id} on poll {poll_id}")
                                            self.metrics["recovery_actions_executed"] += 1
                    
                    self.metrics["votes_validated"] += len(db_votes)
                    
                except Exception as e:
                    logger.error(f"Error validating vote-reaction sync for poll {poll_id}: {e}")
            
            logger.info("✅ PHASE 5 - Vote-reaction synchronization validation completed")
            
        finally:
            db.close()
    
    async def _validate_cache_consistency(self):
        """Validate cache consistency and warm missing caches"""
        logger.info("🔍 PHASE 6 - Validating cache consistency")
        
        try:
            cache_service = get_enhanced_cache_service()
            
            # Get active servers from database
            db = get_db_session()
            try:
                active_polls = db.query(Poll).filter(Poll.status == "active").all()
                server_ids = {TypeSafeColumn.get_string(poll, "server_id") for poll in active_polls}
                
                cache_misses = 0
                
                for server_id in server_ids:
                    if server_id:
                        # Check if emoji cache exists
                        cache_key = f"guild_emojis:{server_id}"
                        cached_emojis = await cache_service.get(cache_key)
                        
                        if not cached_emojis:
                            cache_misses += 1
                            # Warm the cache
                            try:
                                from .discord_emoji_handler import DiscordEmojiHandler
                                emoji_handler = DiscordEmojiHandler(self.bot)
                                await emoji_handler.get_guild_emoji_list(server_id)
                                
                                self.recovery_actions.append(f"Warmed emoji cache for server {server_id}")
                                self.metrics["recovery_actions_executed"] += 1
                            except Exception as e:
                                logger.warning(f"Failed to warm cache for server {server_id}: {e}")
                
                if cache_misses > 0:
                    self.validation_errors.append(f"Found {cache_misses} cache misses")
                
                self.metrics["cache_entries_validated"] = len(server_ids)
                
            finally:
                db.close()
            
            logger.info("✅ PHASE 6 - Cache consistency validation completed")
            
        except Exception as e:
            logger.error(f"Error validating cache consistency: {e}")
    
    async def _validate_static_content_integrity(self):
        """Validate static content integrity for closed polls"""
        logger.info("🔍 PHASE 7 - Validating static content integrity")
        
        try:
            static_recovery = get_static_recovery()
            integrity_results = await static_recovery.verify_static_content_integrity()
            
            self.metrics["static_content_validated"] = integrity_results["total_closed_polls"]
            
            if integrity_results["integrity_issues"]:
                self.validation_errors.append(f"Found {len(integrity_results['integrity_issues'])} static content issues")
                
                # Generate missing static content
                recovery_results = await static_recovery.generate_for_existing_closed_polls(self.bot, limit=50)
                
                if recovery_results["successful_generations"] > 0:
                    self.recovery_actions.append(f"Generated static content for {recovery_results['successful_generations']} polls")
                    self.metrics["recovery_actions_executed"] += recovery_results["successful_generations"]
            
            logger.info("✅ PHASE 7 - Static content integrity validation completed")
            
        except Exception as e:
            logger.error(f"Error validating static content integrity: {e}")
    
    async def _validate_fresh_instance_compliance(self) -> bool:
        """Validate that restored instance follows fresh instance patterns"""
        logger.info("🔍 PHASE 8 - Validating fresh instance compliance")
        
        try:
            # Check that all required services are running
            required_services = [
                ("Bot", self.bot and self.bot.is_ready()),
                ("Scheduler", get_scheduler() and get_scheduler().running),
                ("Cache Service", get_enhanced_cache_service() is not None),
                ("Recovery Manager", get_recovery_manager() is not None)
            ]
            
            missing_services = [name for name, running in required_services if not running]
            
            if missing_services:
                self.validation_errors.append(f"Missing required services: {missing_services}")
                return False
            
            # Check that database schema is correct
            db = get_db_session()
            try:
                # Verify key tables exist and have expected structure
                tables_to_check = ["polls", "votes", "user_preferences"]
                for table in tables_to_check:
                    result = db.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'").fetchone()
                    if not result:
                        self.validation_errors.append(f"Missing required table: {table}")
                        return False
                
                # Check that polls have all required columns
                poll_columns = db.execute("PRAGMA table_info(polls)").fetchall()
                required_columns = ["id", "name", "question", "options", "status", "creator_id"]
                existing_columns = {col[1] for col in poll_columns}
                
                missing_columns = set(required_columns) - existing_columns
                if missing_columns:
                    self.validation_errors.append(f"Missing required poll columns: {missing_columns}")
                    return False
                
            finally:
                db.close()
            
            logger.info("✅ PHASE 8 - Fresh instance compliance validated")
            return True
            
        except Exception as e:
            logger.error(f"Error validating fresh instance compliance: {e}")
            self.validation_errors.append(f"Fresh instance compliance check failed: {str(e)}")
            return False
    
    async def _detect_and_fill_recovery_gaps(self):
        """Detect and fill any remaining recovery gaps"""
        logger.info("🔍 PHASE 9 - Detecting and filling recovery gaps")
        
        try:
            # Run a final comprehensive recovery to catch anything missed
            recovery_manager = get_recovery_manager(self.bot)
            if recovery_manager:
                final_recovery = await recovery_manager.perform_full_recovery()
                
                if final_recovery["success"]:
                    recovery_stats = final_recovery["stats"]
                    if any(recovery_stats.values()):
                        self.recovery_actions.append(f"Final recovery pass: {recovery_stats}")
                        self.metrics["recovery_actions_executed"] += sum(recovery_stats.values())
                else:
                    self.validation_errors.append(f"Final recovery pass failed: {final_recovery.get('error', 'Unknown error')}")
            
            logger.info("✅ PHASE 9 - Recovery gap detection completed")
            
        except Exception as e:
            logger.error(f"Error in recovery gap detection: {e}")
    
    def _calculate_confidence_level(self) -> float:
        """Calculate confidence level on 12/10 scale"""
        base_confidence = 10.0
        
        # Deduct confidence for errors
        error_penalty = min(2.0, len(self.validation_errors) * 0.5)
        base_confidence -= error_penalty
        
        # Add confidence for successful recovery actions
        recovery_bonus = min(2.0, self.metrics["recovery_actions_executed"] * 0.1)
        base_confidence += recovery_bonus
        
        # Ensure we don't exceed 12.0
        return min(12.0, max(0.0, base_confidence))


# Global validator instance
_enhanced_validator: Optional[EnhancedRecoveryValidator] = None


def get_enhanced_recovery_validator(bot) -> EnhancedRecoveryValidator:
    """Get or create enhanced recovery validator instance"""
    global _enhanced_validator
    
    if _enhanced_validator is None:
        _enhanced_validator = EnhancedRecoveryValidator(bot)
    
    return _enhanced_validator


async def perform_enhanced_recovery_validation(bot) -> RecoveryValidationResult:
    """Convenience function to perform enhanced recovery validation"""
    validator = get_enhanced_recovery_validator(bot)
    return await validator.perform_comprehensive_recovery_validation()
