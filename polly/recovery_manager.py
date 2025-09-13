"""
Polly Recovery Manager
Comprehensive recovery system to ensure all operations recover properly after bot restarts.
Handles vote collection, database syncing, poll state restoration, and cache warming.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any
import pytz
import discord
from discord.ext import commands

# Handle both relative and absolute imports for direct execution
try:
    from .database import get_db_session, Poll, Vote, TypeSafeColumn, POLL_EMOJIS
    from .discord_utils import update_poll_message
    from .poll_operations import BulletproofPollOperations
    from .background_tasks import close_poll
except ImportError:
    # Fallback for direct execution
    import sys
    import os
    sys.path.insert(0, os.path.dirname(__file__))
    from database import get_db_session, Poll, Vote, TypeSafeColumn, POLL_EMOJIS
    from discord_utils import update_poll_message
    from poll_operations import BulletproofPollOperations
    from background_tasks import close_poll

logger = logging.getLogger(__name__)


class RecoveryManager:
    """Comprehensive recovery manager for bot restart scenarios"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bulletproof_ops = BulletproofPollOperations(bot)
        self.recovery_stats = {
            "polls_recovered": 0,
            "votes_synced": 0,
            "reactions_restored": 0,
            "jobs_scheduled": 0,
            "errors_encountered": 0,
            "cache_entries_warmed": 0
        }
    
    async def perform_full_recovery(self) -> Dict[str, Any]:
        """
        Perform comprehensive recovery after bot restart.
        This is the main entry point for all recovery operations.
        """
        logger.info("🔄 RECOVERY MANAGER - Starting comprehensive recovery process")
        recovery_start_time = datetime.now(pytz.UTC)
        
        try:
            # Step 1: Wait for bot to be fully ready
            await self._wait_for_bot_ready()
            
            # Step 2: Recover scheduled polls and jobs
            await self._recover_scheduled_operations()
            
            # Step 3: Recover active polls
            await self._recover_active_polls()
            
            # Step 4: Sync votes and reactions
            await self._sync_votes_and_reactions()
            
            # Step 5: Warm caches
            await self._warm_caches()
            
            # Step 6: Cleanup orphaned data
            await self._cleanup_orphaned_data()
            
            recovery_duration = (datetime.now(pytz.UTC) - recovery_start_time).total_seconds()
            
            logger.info(f"✅ RECOVERY MANAGER - Full recovery completed in {recovery_duration:.2f} seconds")
            logger.info(f"📊 RECOVERY STATS - {self.recovery_stats}")
            
            return {
                "success": True,
                "duration_seconds": recovery_duration,
                "stats": self.recovery_stats.copy(),
                "message": "Full recovery completed successfully"
            }
            
        except Exception as e:
            self.recovery_stats["errors_encountered"] += 1
            logger.error(f"❌ RECOVERY MANAGER - Full recovery failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "stats": self.recovery_stats.copy(),
                "message": "Recovery failed with errors"
            }
    
    async def _wait_for_bot_ready(self, max_wait_seconds: int = 30):
        """Wait for bot to be fully ready before starting recovery"""
        logger.info("⏳ RECOVERY MANAGER - Waiting for bot to be ready")
        
        wait_start = datetime.now(pytz.UTC)
        while not self.bot.is_ready():
            elapsed = (datetime.now(pytz.UTC) - wait_start).total_seconds()
            if elapsed > max_wait_seconds:
                raise Exception(f"Bot not ready after {max_wait_seconds} seconds")
            await asyncio.sleep(1)
        
        # Additional small delay to ensure full readiness
        await asyncio.sleep(2)
        logger.info("✅ RECOVERY MANAGER - Bot is ready")
    
    async def _recover_scheduled_operations(self):
        """Recover all scheduled poll operations"""
        logger.info("📅 RECOVERY MANAGER - Recovering scheduled operations")
        
        from .background_tasks import restore_scheduled_jobs
        
        try:
            # Use existing scheduler restoration logic
            await restore_scheduled_jobs()
            self.recovery_stats["jobs_scheduled"] += 1
            logger.info("✅ RECOVERY MANAGER - Scheduled operations recovered")
        except Exception as e:
            self.recovery_stats["errors_encountered"] += 1
            logger.error(f"❌ RECOVERY MANAGER - Failed to recover scheduled operations: {e}")
            raise
    
    async def _recover_active_polls(self):
        """Recover all active polls and ensure they have proper reactions"""
        logger.info("🗳️ RECOVERY MANAGER - Recovering active polls")
        
        db = get_db_session()
        try:
            # Get all active polls
            active_polls = db.query(Poll).filter(Poll.status == "active").all()
            logger.info(f"📊 RECOVERY MANAGER - Found {len(active_polls)} active polls to recover")
            
            for poll in active_polls:
                try:
                    await self._recover_single_poll(poll)
                    self.recovery_stats["polls_recovered"] += 1
                except Exception as e:
                    self.recovery_stats["errors_encountered"] += 1
                    poll_id = TypeSafeColumn.get_int(poll, "id")
                    logger.error(f"❌ RECOVERY MANAGER - Failed to recover poll {poll_id}: {e}")
                    continue
            
            logger.info(f"✅ RECOVERY MANAGER - Recovered {self.recovery_stats['polls_recovered']} active polls")
            
        finally:
            db.close()
    
    async def _recover_single_poll(self, poll: Poll):
        """Recover a single active poll"""
        poll_id = TypeSafeColumn.get_int(poll, "id")
        poll_name = TypeSafeColumn.get_string(poll, "name", "Unknown")
        message_id = TypeSafeColumn.get_string(poll, "message_id")
        channel_id = TypeSafeColumn.get_string(poll, "channel_id")
        
        logger.debug(f"🔄 RECOVERY MANAGER - Recovering poll {poll_id}: '{poll_name}'")
        
        # Check if poll should still be active
        now = datetime.now(pytz.UTC)
        close_time = poll.close_time
        
        if close_time and close_time <= now:
            # Poll should have closed - close it now
            logger.info(f"⏰ RECOVERY MANAGER - Poll {poll_id} is overdue, closing now")
            try:
                await close_poll(poll_id)
                return
            except Exception as e:
                logger.error(f"❌ RECOVERY MANAGER - Failed to close overdue poll {poll_id}: {e}")
                raise
        
        # Poll should still be active - ensure Discord message exists and has reactions
        if not message_id or not channel_id:
            logger.warning(f"⚠️ RECOVERY MANAGER - Poll {poll_id} missing message_id or channel_id")
            return
        
        try:
            # Get Discord channel and message
            channel = self.bot.get_channel(int(channel_id))
            if not channel:
                logger.warning(f"⚠️ RECOVERY MANAGER - Channel {channel_id} not found for poll {poll_id}")
                return
            
            if not isinstance(channel, discord.TextChannel):
                logger.warning(f"⚠️ RECOVERY MANAGER - Channel {channel_id} is not a text channel for poll {poll_id}")
                return
            
            try:
                message = await channel.fetch_message(int(message_id))
            except discord.NotFound:
                logger.warning(f"⚠️ RECOVERY MANAGER - Message {message_id} not found for poll {poll_id}")
                # Message was deleted - we'll let the cleanup process handle this
                return
            except Exception as e:
                logger.error(f"❌ RECOVERY MANAGER - Error fetching message {message_id} for poll {poll_id}: {e}")
                return
            
            # Ensure poll has proper reactions
            await self._ensure_poll_reactions(poll, message)
            
            # Update poll message to current state
            try:
                await update_poll_message(self.bot, poll)
                logger.debug(f"✅ RECOVERY MANAGER - Updated message for poll {poll_id}")
            except Exception as e:
                logger.warning(f"⚠️ RECOVERY MANAGER - Failed to update message for poll {poll_id}: {e}")
            
        except Exception as e:
            logger.error(f"❌ RECOVERY MANAGER - Error recovering poll {poll_id}: {e}")
            raise
    
    async def _ensure_poll_reactions(self, poll: Poll, message: discord.Message):
        """Ensure poll message has all required reactions"""
        poll_id = TypeSafeColumn.get_int(poll, "id")
        poll_emojis = poll.emojis if poll.emojis else POLL_EMOJIS
        options_count = len(poll.options)
        
        # Get current reactions on the message
        current_reactions = {str(reaction.emoji) for reaction in message.reactions}
        
        # Add missing reactions
        reactions_added = 0
        for i in range(min(options_count, len(poll_emojis))):
            emoji = poll_emojis[i]
            
            if emoji not in current_reactions:
                try:
                    # Prepare emoji for reaction (handles Unicode emoji variation selectors)
                    from .discord_emoji_handler import DiscordEmojiHandler
                    emoji_handler = DiscordEmojiHandler(self.bot)
                    prepared_emoji = emoji_handler.prepare_emoji_for_reaction(emoji)
                    
                    await message.add_reaction(prepared_emoji)
                    reactions_added += 1
                    logger.debug(f"➕ RECOVERY MANAGER - Added missing reaction {emoji} to poll {poll_id}")
                    
                    # Small delay to avoid rate limiting
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    logger.warning(f"⚠️ RECOVERY MANAGER - Failed to add reaction {emoji} to poll {poll_id}: {e}")
        
        if reactions_added > 0:
            self.recovery_stats["reactions_restored"] += reactions_added
            logger.info(f"✅ RECOVERY MANAGER - Added {reactions_added} missing reactions to poll {poll_id}")
    
    async def _sync_votes_and_reactions(self):
        """Sync votes with Discord reactions to catch any missed votes"""
        logger.info("🔄 RECOVERY MANAGER - Syncing votes and reactions")
        
        # Use the existing reaction safeguard logic but run it once for recovery
        
        try:
            # Create a modified version that runs once instead of continuously
            await self._single_reaction_sync_pass()
            logger.info("✅ RECOVERY MANAGER - Vote and reaction sync completed")
        except Exception as e:
            self.recovery_stats["errors_encountered"] += 1
            logger.error(f"❌ RECOVERY MANAGER - Vote sync failed: {e}")
    
    async def _single_reaction_sync_pass(self):
        """Single pass of reaction synchronization"""
        db = get_db_session()
        try:
            active_polls = db.query(Poll).filter(Poll.status == "active").all()
            
            for poll in active_polls:
                try:
                    poll_id = TypeSafeColumn.get_int(poll, "id")
                    message_id = TypeSafeColumn.get_string(poll, "message_id")
                    channel_id = TypeSafeColumn.get_string(poll, "channel_id")
                    
                    if not message_id or not channel_id:
                        continue
                    
                    # Get Discord message
                    channel = self.bot.get_channel(int(channel_id))
                    if not channel or not isinstance(channel, discord.TextChannel):
                        continue
                    
                    try:
                        message = await channel.fetch_message(int(message_id))
                    except discord.NotFound:
                        continue
                    except Exception:
                        continue
                    
                    # Process reactions
                    votes_synced = await self._sync_poll_reactions(poll, message)
                    self.recovery_stats["votes_synced"] += votes_synced
                    
                except Exception as e:
                    poll_id = TypeSafeColumn.get_int(poll, "id", 0) if poll else 0
                    logger.warning(f"⚠️ RECOVERY MANAGER - Error syncing poll {poll_id}: {e}")
                    continue
        
        finally:
            db.close()
    
    async def _sync_poll_reactions(self, poll: Poll, message: discord.Message) -> int:
        """Sync reactions for a single poll"""
        poll_id = TypeSafeColumn.get_int(poll, "id")
        poll_emojis = poll.emojis if poll.emojis else POLL_EMOJIS
        votes_synced = 0
        
        for reaction in message.reactions:
            try:
                if str(reaction.emoji) not in poll_emojis:
                    continue
                
                option_index = poll_emojis.index(str(reaction.emoji))
                if option_index >= len(poll.options):
                    continue
                
                # Check each user who reacted
                async for user in reaction.users():
                    if user.bot:
                        continue
                    
                    try:
                        # Check if vote is already recorded
                        db = get_db_session()
                        try:
                            existing_vote = (
                                db.query(Vote)
                                .filter(
                                    Vote.poll_id == poll_id,
                                    Vote.user_id == str(user.id),
                                )
                                .first()
                            )
                            
                            if not existing_vote:
                                # Vote missing - record it
                                result = await self.bulletproof_ops.bulletproof_vote_collection(
                                    poll_id, str(user.id), option_index
                                )
                                
                                if result["success"]:
                                    votes_synced += 1
                                    logger.debug(f"🔄 RECOVERY MANAGER - Synced missing vote for user {user.id} on poll {poll_id}")
                                    
                                    # Remove reaction after recording vote
                                    try:
                                        await reaction.remove(user)
                                    except Exception:
                                        pass
                        
                        finally:
                            db.close()
                    
                    except Exception as e:
                        logger.warning(f"⚠️ RECOVERY MANAGER - Error syncing vote for user {user.id}: {e}")
                        continue
            
            except Exception as e:
                logger.warning(f"⚠️ RECOVERY MANAGER - Error processing reaction {reaction.emoji}: {e}")
                continue
        
        return votes_synced
    
    async def _warm_caches(self):
        """Warm up Redis caches after restart"""
        logger.info("🔥 RECOVERY MANAGER - Warming caches")
        
        try:
            from .enhanced_cache_service import get_enhanced_cache_service
            cache_service = get_enhanced_cache_service()
            
            # Warm guild emoji caches for active polls
            db = get_db_session()
            try:
                active_polls = db.query(Poll).filter(Poll.status == "active").all()
                server_ids = set()
                
                for poll in active_polls:
                    server_id = TypeSafeColumn.get_string(poll, "server_id")
                    if server_id:
                        server_ids.add(server_id)
                
                # Pre-warm emoji caches for active servers
                for server_id in server_ids:
                    try:
                        from .discord_emoji_handler import DiscordEmojiHandler
                        emoji_handler = DiscordEmojiHandler(self.bot)
                        
                        # This will cache the emoji list
                        await emoji_handler.get_guild_emoji_list(server_id)
                        self.recovery_stats["cache_entries_warmed"] += 1
                        
                        logger.debug(f"🔥 RECOVERY MANAGER - Warmed emoji cache for server {server_id}")
                        
                    except Exception as e:
                        logger.warning(f"⚠️ RECOVERY MANAGER - Failed to warm cache for server {server_id}: {e}")
                
                logger.info(f"✅ RECOVERY MANAGER - Warmed {self.recovery_stats['cache_entries_warmed']} cache entries")
                
            finally:
                db.close()
                
        except Exception as e:
            self.recovery_stats["errors_encountered"] += 1
            logger.error(f"❌ RECOVERY MANAGER - Cache warming failed: {e}")
    
    async def _cleanup_orphaned_data(self):
        """Clean up any orphaned data after restart"""
        logger.info("🧹 RECOVERY MANAGER - Cleaning up orphaned data")
        
        try:
            # Use existing cleanup logic
            from .background_tasks import cleanup_polls_with_deleted_messages
            await cleanup_polls_with_deleted_messages()
            logger.info("✅ RECOVERY MANAGER - Orphaned data cleanup completed")
        except Exception as e:
            self.recovery_stats["errors_encountered"] += 1
            logger.error(f"❌ RECOVERY MANAGER - Cleanup failed: {e}")
    
    async def recover_specific_poll(self, poll_id: int) -> Dict[str, Any]:
        """Recover a specific poll by ID"""
        logger.info(f"🎯 RECOVERY MANAGER - Recovering specific poll {poll_id}")
        
        try:
            db = get_db_session()
            try:
                poll = db.query(Poll).filter(Poll.id == poll_id).first()
                if not poll:
                    return {"success": False, "error": "Poll not found"}
                
                await self._recover_single_poll(poll)
                
                return {
                    "success": True,
                    "message": f"Poll {poll_id} recovered successfully"
                }
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"❌ RECOVERY MANAGER - Failed to recover poll {poll_id}: {e}")
            return {"success": False, "error": str(e)}
    
    def get_recovery_stats(self) -> Dict[str, Any]:
        """Get current recovery statistics"""
        return self.recovery_stats.copy()


# Global recovery manager instance
_recovery_manager = None


def get_recovery_manager(bot: commands.Bot = None) -> RecoveryManager:
    """Get or create the global recovery manager instance"""
    global _recovery_manager
    
    if _recovery_manager is None and bot is not None:
        _recovery_manager = RecoveryManager(bot)
    
    return _recovery_manager


async def perform_startup_recovery(bot: commands.Bot) -> Dict[str, Any]:
    """Perform comprehensive recovery on startup"""
    recovery_manager = get_recovery_manager(bot)
    return await recovery_manager.perform_full_recovery()


async def recover_poll(bot: commands.Bot, poll_id: int) -> Dict[str, Any]:
    """Recover a specific poll"""
    recovery_manager = get_recovery_manager(bot)
    return await recovery_manager.recover_specific_poll(poll_id)
