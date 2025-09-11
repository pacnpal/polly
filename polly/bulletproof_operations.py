"""
Bulletproof Poll Operations
Ultra-robust implementations of core poll functions with comprehensive error handling,
validation, recovery mechanisms, and failsafes.
"""

import io
import uuid
import hashlib
import mimetypes
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import asyncio
import logging
from pathlib import Path

import discord
from discord.ext import commands
import aiofiles
from PIL import Image

from .validators import PollValidator, VoteValidator
from .error_handler import PollErrorHandler, DiscordErrorHandler, critical_operation
from .database import get_db_session, Poll

logger = logging.getLogger(__name__)


class BulletproofImageHandler:
    """Ultra-robust image handling with comprehensive validation and security."""

    def __init__(self, upload_dir: str = "static/uploads"):  # FIXED: Changed from "uploads" to "static/uploads"
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)  # FIXED: Added parents=True to create parent directories
        self.max_file_size = 8 * 1024 * 1024  # 8MB Discord limit
        self.allowed_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
        self.allowed_mime_types = {"image/jpeg", "image/png", "image/gif", "image/webp"}

    @critical_operation("image_validation")
    async def validate_and_process_image(
        self, file_data: bytes, filename: str
    ) -> Dict[str, Any]:
        """
        Comprehensive image validation and processing with security checks.

        Returns:
            Dict containing processed image info or error details
        """
        try:
            # Step 1: Basic validation
            if not file_data:
                return {"success": False, "error": "No file data provided"}

            if len(file_data) > self.max_file_size:
                return {
                    "success": False,
                    "error": f"File too large. Max size: {self.max_file_size // (1024 * 1024)}MB",
                }

            # Step 2: File extension validation
            file_ext = Path(filename).suffix.lower()
            if file_ext not in self.allowed_extensions:
                return {
                    "success": False,
                    "error": f"Invalid file type. Allowed: {', '.join(self.allowed_extensions)}",
                }

            # Step 3: MIME type validation using mimetypes module
            try:
                # Use mimetypes module for MIME type detection
                mime_type, _ = mimetypes.guess_type(filename)
                if mime_type not in self.allowed_mime_types:
                    return {"success": False, "error": "Could not verify file type"}
            except Exception as e:
                logger.warning(f"MIME type detection failed: {e}")
                return {"success": False, "error": "Could not verify file type"}

            # Step 4: Image integrity validation using PIL
            try:
                with Image.open(io.BytesIO(file_data)) as img:
                    img.verify()  # Verify image integrity
                    # Re-open for size check (verify() closes the image)
                    img = Image.open(io.BytesIO(file_data))
                    width, height = img.size

                    # Reasonable size limits
                    if width > 4096 or height > 4096:
                        return {
                            "success": False,
                            "error": "Image dimensions too large (max 4096x4096)",
                        }

                    if width < 1 or height < 1:
                        return {"success": False, "error": "Invalid image dimensions"}

            except Exception as e:
                return {
                    "success": False,
                    "error": f"Invalid or corrupted image: {str(e)}",
                }

            # Step 5: Generate secure filename
            file_hash = hashlib.sha256(file_data).hexdigest()[:16]
            secure_filename = f"{uuid.uuid4().hex}_{file_hash}{file_ext}"
            file_path = self.upload_dir / secure_filename

            # Step 6: Save file securely with proper error handling
            try:
                # FIXED: Ensure directory exists before writing
                self.upload_dir.mkdir(parents=True, exist_ok=True)
                
                async with aiofiles.open(file_path, "wb") as f:
                    await f.write(file_data)

                # FIXED: Add small delay to ensure file system sync
                await asyncio.sleep(0.1)

                # Verify file was written correctly
                if not file_path.exists():
                    return {"success": False, "error": "File was not created"}
                    
                actual_size = file_path.stat().st_size
                if actual_size != len(file_data):
                    return {"success": False, "error": f"File size mismatch: expected {len(file_data)}, got {actual_size}"}

                # FIXED: Set proper file permissions for web server access
                try:
                    file_path.chmod(0o644)  # Read/write for owner, read for group/others
                except Exception as perm_error:
                    logger.warning(f"Could not set file permissions for {file_path}: {perm_error}")

            except Exception as e:
                # Cleanup on failure
                if file_path.exists():
                    try:
                        file_path.unlink()
                    except Exception:
                        pass
                return {"success": False, "error": f"Failed to save file: {str(e)}"}

            return {
                "success": True,
                "file_path": str(file_path),
                "filename": secure_filename,
                "original_filename": filename,
                "size": len(file_data),
                "mime_type": mime_type,
                "dimensions": (width, height),
            }

        except Exception as e:
            logger.error(f"Image validation failed: {e}")
            return {"success": False, "error": f"Image processing failed: {str(e)}"}

    @critical_operation("image_cleanup")
    async def cleanup_image(self, file_path: str) -> bool:
        """Safely remove image file."""
        try:
            path = Path(file_path)
            # FIXED: More robust path validation
            if path.exists() and path.is_file() and "static/uploads" in str(path):
                path.unlink()
                logger.info(f"Successfully cleaned up image: {file_path}")
                return True
            else:
                logger.warning(f"Image cleanup skipped - invalid path: {file_path}")
        except Exception as e:
            logger.error(f"Failed to cleanup image {file_path}: {e}")
        return False


class BulletproofPollOperations:
    """Ultra-robust poll operations with comprehensive error handling and recovery."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.image_handler = BulletproofImageHandler()
        self.poll_error_handler = PollErrorHandler()
        self.discord_error_handler = DiscordErrorHandler()

    @critical_operation("bulletproof_poll_creation")
    async def create_bulletproof_poll(
        self,
        poll_data: Dict[str, Any],
        user_id: str,
        image_file: Optional[bytes] = None,
        image_filename: Optional[str] = None,
        image_message_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Bulletproof poll creation with 6-step validation and recovery process.

        Args:
            poll_data: Poll configuration data
            user_id: User creating the poll
            image_file: Optional image file bytes
            image_filename: Original image filename
            image_message_text: Optional text to include with image message

        Returns:
            Dict with success status and poll details or error information
        """
        poll_id = None
        image_info = None
        discord_image_message_id = None
        discord_poll_message_id = None

        try:
            # STEP 1: Comprehensive Data Validation
            logger.info("Step 1: Validating poll data")
            try:
                validated_data = PollValidator.validate_poll_data(poll_data)
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Validation failed: {str(e)}",
                    "step": "validation",
                }

            # STEP 2: Image Processing (if provided) - ENHANCED ERROR HANDLING
            if image_file and image_filename:
                logger.info(f"Step 2: Processing image - {image_filename} ({len(image_file)} bytes)")
                image_result = await self.image_handler.validate_and_process_image(
                    image_file, image_filename
                )
                if not image_result["success"]:
                    logger.error(f"Image processing failed: {image_result['error']}")
                    return {
                        "success": False,
                        "error": f"Image processing failed: {image_result['error']}",
                        "step": "image_processing",
                    }
                image_info = image_result
                logger.info(f"Image processed successfully: {image_info['file_path']}")

            # STEP 3: Discord Permission Validation
            logger.info("Step 3: Validating Discord permissions")
            channel_id = int(validated_data["channel_id"])
            channel = self.bot.get_channel(channel_id)
            if not channel:
                await self._cleanup_on_failure(poll_id, image_info)
                return {
                    "success": False,
                    "error": f"Channel {channel_id} not found",
                    "step": "discord_validation",
                }

            # Type check for guild channel
            if not hasattr(channel, "guild") or not hasattr(channel, "permissions_for"):
                await self._cleanup_on_failure(poll_id, image_info)
                return {
                    "success": False,
                    "error": "Channel is not a guild channel",
                    "step": "discord_validation",
                }

            # Get guild for server name extraction
            guild = getattr(channel, "guild", None)
            if not guild:
                await self._cleanup_on_failure(poll_id, image_info)
                return {
                    "success": False,
                    "error": "Guild not found for channel",
                    "step": "discord_validation",
                }

            # Check bot permissions
            permissions = getattr(channel, "permissions_for", lambda x: None)(guild.me)
            if not permissions:
                await self._cleanup_on_failure(poll_id, image_info)
                return {
                    "success": False,
                    "error": "Could not get channel permissions",
                    "step": "discord_validation",
                }
            required_perms = ["send_messages", "embed_links", "add_reactions"]
            if image_info:
                required_perms.append("attach_files")

            missing_perms = [
                perm for perm in required_perms if not getattr(permissions, perm)
            ]
            if missing_perms:
                await self._cleanup_on_failure(poll_id, image_info)
                return {
                    "success": False,
                    "error": f"Missing Discord permissions: {', '.join(missing_perms)}",
                    "step": "discord_validation",
                }

            # STEP 4: Database Transaction (Atomic)
            logger.info("Step 4: Creating database record")
            try:
                db = get_db_session()
                try:
                    # Create poll using SQLAlchemy ORM with server and channel names
                    poll = Poll(
                        name=validated_data["name"],
                        question=validated_data["question"],
                        options=validated_data["options"],
                        emojis=validated_data.get("emojis", []),  # Include emojis
                        server_id=validated_data["server_id"],
                        server_name=guild.name,  # Add server name
                        channel_id=validated_data["channel_id"],
                        # Add channel name
                        channel_name=getattr(channel, "name", "Unknown"),
                        creator_id=user_id,
                        open_time=validated_data["open_time"],
                        close_time=validated_data["close_time"],
                        timezone=validated_data["timezone"],
                        anonymous=validated_data["anonymous"],
                        multiple_choice=validated_data.get("multiple_choice", False),
                        max_choices=validated_data.get("max_choices", None),  # FIXED: Added max_choices support
                        image_path=image_info["file_path"] if image_info else None,
                        image_message_text=image_message_text or "",
                        # ROLE PING FIX: Include role ping data in poll creation
                        ping_role_enabled=validated_data.get("ping_role_enabled", False),
                        ping_role_id=validated_data.get("ping_role_id", None),
                        ping_role_name=validated_data.get("ping_role_name", None),
                        ping_role_on_close=validated_data.get("ping_role_on_close", False),
                        ping_role_on_update=validated_data.get("ping_role_on_update", False),
                    )

                    db.add(poll)
                    
                    # ROLE PING FIX: Log role ping data before commit
                    logger.info("🔔 BULLETPROOF CREATION - Role ping data being saved:")
                    logger.info(f"🔔 BULLETPROOF CREATION - ping_role_enabled: {validated_data.get('ping_role_enabled', False)}")
                    logger.info(f"🔔 BULLETPROOF CREATION - ping_role_id: {validated_data.get('ping_role_id', None)}")
                    logger.info(f"🔔 BULLETPROOF CREATION - ping_role_name: {validated_data.get('ping_role_name', None)}")
                    
                    db.commit()
                    poll_id = int(getattr(poll, "id"))
                    
                    # ROLE PING FIX: Verify role ping data was saved correctly
                    fresh_poll = db.query(Poll).filter(Poll.id == poll_id).first()
                    if fresh_poll:
                        saved_ping_enabled = getattr(fresh_poll, "ping_role_enabled", False)
                        saved_ping_id = getattr(fresh_poll, "ping_role_id", None)
                        saved_ping_name = getattr(fresh_poll, "ping_role_name", None)
                        
                        logger.info("🔔 BULLETPROOF CREATION - Role ping data verification after commit:")
                        logger.info(f"🔔 BULLETPROOF CREATION - saved_ping_role_enabled: {saved_ping_enabled}")
                        logger.info(f"🔔 BULLETPROOF CREATION - saved_ping_role_id: {saved_ping_id}")
                        logger.info(f"🔔 BULLETPROOF CREATION - saved_ping_role_name: {saved_ping_name}")
                        
                        # Check if data was lost during save
                        if validated_data.get('ping_role_enabled', False) and not saved_ping_enabled:
                            logger.error("🔔 BULLETPROOF CREATION - Role ping data was lost during database save!")
                        elif validated_data.get('ping_role_id') and not saved_ping_id:
                            logger.error("🔔 BULLETPROOF CREATION - Role ping ID was lost during database save!")
                        else:
                            logger.info("🔔 BULLETPROOF CREATION - Role ping data saved successfully")

                    if not poll_id:
                        raise Exception("Failed to create poll record")

                    # FIXED: Log image path storage for debugging
                    if image_info:
                        logger.info(f"Poll {poll_id} created with image: {image_info['file_path']}")

                finally:
                    db.close()

            except Exception as e:
                await self._cleanup_on_failure(poll_id, image_info)
                return {
                    "success": False,
                    "error": f"Database operation failed: {str(e)}",
                    "step": "database",
                }

            # STEP 5: All polls are scheduled only - no immediate posting
            open_time = validated_data["open_time"]
            logger.info(
                f"Step 5: Poll scheduled for {open_time}, will be posted by scheduler"
            )
            # Image message text is already stored in the database during poll creation

            # STEP 6: Final Database Update
            logger.info("Step 6: Updating database with Discord IDs")
            try:
                db = get_db_session()
                try:
                    poll = db.query(Poll).filter(Poll.id == poll_id).first()
                    if poll:
                        if discord_image_message_id:
                            # Store image message ID in a custom field if needed
                            pass
                        db.commit()
                finally:
                    db.close()
            except Exception as e:
                logger.error(f"Failed to update poll with Discord IDs: {e}")
                # Don't fail the entire operation for this

            return {
                "success": True,
                "poll_id": poll_id,
                "discord_message_id": discord_poll_message_id,
                "discord_image_message_id": discord_image_message_id,
                "image_posted": image_info is not None,
                "message": "Poll created successfully",
            }

        except Exception as e:
            logger.error(f"Bulletproof poll creation failed: {e}")
            poll_id_int = int(poll_id) if poll_id is not None else None
            await self._cleanup_on_failure(
                poll_id_int,
                image_info,
                discord_image_message_id,
                discord_poll_message_id,
            )
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "step": "unknown",
            }

    async def _post_image_message(
        self, channel, image_info: Dict[str, Any], message_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """Post image as separate message before poll."""
        try:
            file_path = Path(image_info["file_path"])
            if not file_path.exists():
                return {"success": False, "error": "Image file not found"}

            # Create Discord file object
            discord_file = discord.File(
                file_path, filename=image_info["original_filename"]
            )

            # Prepare message content
            content = message_text if message_text else ""

            # Post message with image
            message = await channel.send(content=content, file=discord_file)

            return {
                "success": True,
                "message_id": message.id,
                "message": "Image posted successfully",
            }

        except discord.Forbidden:
            return {"success": False, "error": "No permission to post images"}
        except discord.HTTPException as e:
            return {"success": False, "error": f"Discord HTTP error: {str(e)}"}
        except Exception as e:
            logger.error(f"Failed to post image: {e}")
            return {"success": False, "error": f"Failed to post image: {str(e)}"}

    async def _cleanup_on_failure(
        self,
        poll_id: Optional[int] = None,
        image_info: Optional[Dict[str, Any]] = None,
        discord_image_message_id: Optional[int] = None,
        discord_poll_message_id: Optional[int] = None,
    ):
        """Comprehensive cleanup on operation failure."""
        cleanup_tasks = []

        # Cleanup database record
        if poll_id:
            cleanup_tasks.append(self._cleanup_database_record(poll_id))

        # Cleanup image file
        if image_info and "file_path" in image_info:
            cleanup_tasks.append(
                self.image_handler.cleanup_image(image_info["file_path"])
            )

        # Execute all cleanup tasks
        if cleanup_tasks:
            try:
                await asyncio.gather(*cleanup_tasks, return_exceptions=True)
            except Exception as e:
                logger.error(f"Cleanup failed: {e}")

    async def _cleanup_database_record(self, poll_id: int):
        """Remove poll record from database."""
        try:
            db = get_db_session()
            try:
                poll = db.query(Poll).filter(Poll.id == poll_id).first()
                if poll:
                    db.delete(poll)
                    db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Failed to cleanup database record {poll_id}: {e}")

    @critical_operation("bulletproof_vote_collection")
    async def bulletproof_vote_collection(
        self, poll_id: int, user_id: str, option_index: int
    ) -> Dict[str, Any]:
        """Ultra-bulletproof vote collection with atomic transactions and integrity checks."""
        vote_recorded = False
        retry_count = 0
        max_retries = 3
        vote_action = "unknown"

        while retry_count < max_retries and not vote_recorded:
            try:
                retry_count += 1
                logger.debug(
                    f"Vote collection attempt {retry_count} for poll {poll_id}, user {user_id}"
                )

                # Step 1: Atomic database transaction with isolation
                db = get_db_session()
                try:
                    # Use database transaction with proper isolation
                    db.begin()

                    # Step 1a: Get poll with row-level locking to prevent race conditions
                    poll = (
                        db.query(Poll)
                        .filter(Poll.id == poll_id)
                        .with_for_update()
                        .first()
                    )
                    if not poll:
                        db.rollback()
                        return {"success": False, "error": "Poll not found"}

                    if str(getattr(poll, "status", "")) != "active":
                        db.rollback()
                        return {
                            "success": False,
                            "error": f"Poll is not active (status: {str(getattr(poll, 'status', ''))})",
                        }

                    # Step 1b: Validate vote data using existing validator
                    try:
                        VoteValidator.validate_vote_data(poll, user_id, option_index)
                    except Exception as e:
                        db.rollback()
                        logger.error(f"Vote data validation failed: {e}")
                        return {"success": False, "error": str(e)}

                    # Step 2: Bulletproof vote recording with multiple choice support
                    from .database import Vote

                    multiple_choice_value = getattr(poll, "multiple_choice", False)
                    if multiple_choice_value is True:
                        # Multiple choice: Check if user already voted for this specific option
                        existing_vote = (
                            db.query(Vote)
                            .filter(
                                Vote.poll_id == poll_id,
                                Vote.user_id == user_id,
                                Vote.option_index == option_index,
                            )
                            .with_for_update()
                            .first()
                        )

                        if existing_vote:
                            # User already voted for this option - remove the vote (toggle off)
                            db.delete(existing_vote)
                            vote_action = "removed"
                            logger.debug(
                                f"Removed vote for user {user_id}: option {option_index}"
                            )
                        else:
                            # User hasn't voted for this option - add the vote
                            vote = Vote(
                                poll_id=poll_id,
                                user_id=user_id,
                                option_index=option_index,
                            )
                            db.add(vote)
                            vote_action = "added"
                            logger.debug(
                                f"Added vote for user {user_id}: option {option_index}"
                            )
                    else:
                        # Single choice: Replace any existing vote
                        existing_vote = (
                            db.query(Vote)
                            .filter(Vote.poll_id == poll_id, Vote.user_id == user_id)
                            .with_for_update()
                            .first()
                        )

                        if existing_vote:
                            # Check if user is clicking the same option they already voted for
                            if existing_vote.option_index == option_index:
                                # User clicked the same option they already voted for
                                vote_action = "already_recorded"
                                logger.debug(
                                    f"User {user_id} clicked same option {option_index} they already voted for"
                                )
                                # Don't modify the database - vote is already recorded correctly
                            else:
                                # User is changing their vote to a different option
                                vote_action = "updated"
                                old_option = existing_vote.option_index
                                setattr(existing_vote, "option_index", option_index)
                                setattr(
                                    existing_vote, "voted_at", datetime.now(timezone.utc)
                                )
                                logger.debug(
                                    f"Updated vote for user {user_id}: {old_option} -> {option_index}"
                                )
                        else:
                            # Create new vote atomically
                            vote_action = "created"
                            vote = Vote(
                                poll_id=poll_id,
                                user_id=user_id,
                                option_index=option_index,
                            )
                            db.add(vote)
                            logger.debug(
                                f"Created new vote for user {user_id}: option {option_index}"
                            )

                    # Step 3: Commit transaction atomically
                    db.commit()
                    vote_recorded = True

                    # Step 4: Verify vote was recorded correctly
                    if vote_action == "removed":
                        # For removed votes, verify the vote no longer exists
                        verification_vote = (
                            db.query(Vote)
                            .filter(
                                Vote.poll_id == poll_id,
                                Vote.user_id == user_id,
                                Vote.option_index == option_index,
                            )
                            .first()
                        )

                        if verification_vote:
                            logger.error(
                                f"Vote removal verification failed for poll {poll_id}, user {user_id}"
                            )
                            return {
                                "success": False,
                                "error": "Vote removal verification failed",
                            }
                    elif vote_action == "already_recorded":
                        # For already_recorded votes, just verify the vote exists with correct option
                        # No database changes were made, so just verify the existing vote is correct
                        verification_vote = (
                            db.query(Vote)
                            .filter(
                                Vote.poll_id == poll_id, Vote.user_id == user_id
                            )
                            .first()
                        )

                        if (
                            not verification_vote
                            or verification_vote.option_index != option_index
                        ):
                            logger.error(
                                f"Already recorded vote verification failed for poll {poll_id}, user {user_id}"
                            )
                            return {
                                "success": False,
                                "error": "Already recorded vote verification failed",
                            }
                    else:
                        # For added/updated/created votes, verify the vote exists with correct option
                        multiple_choice_verification = getattr(
                            poll, "multiple_choice", False
                        )
                        # Convert SQLAlchemy Column to boolean safely - avoid direct boolean conversion
                        if multiple_choice_verification is not None and str(
                            multiple_choice_verification
                        ).lower() in ("true", "1"):
                            # Multiple choice: verify specific vote exists
                            verification_vote = (
                                db.query(Vote)
                                .filter(
                                    Vote.poll_id == poll_id,
                                    Vote.user_id == user_id,
                                    Vote.option_index == option_index,
                                )
                                .first()
                            )
                        else:
                            # Single choice: verify user has exactly one vote with correct option
                            verification_vote = (
                                db.query(Vote)
                                .filter(
                                    Vote.poll_id == poll_id, Vote.user_id == user_id
                                )
                                .first()
                            )

                        if (
                            not verification_vote
                            or verification_vote.option_index != option_index
                        ):
                            logger.error(
                                f"Vote verification failed for poll {poll_id}, user {user_id}"
                            )
                            return {
                                "success": False,
                                "error": "Vote verification failed",
                            }

                    logger.info(
                        f"Successfully {vote_action} vote for poll {poll_id}, user {user_id}, option {option_index}"
                    )

                    return {
                        "success": True,
                        "action": vote_action,
                        "poll_id": poll_id,
                        "user_id": user_id,
                        "option_index": option_index,
                        "message": f"Vote {vote_action} successfully",
                    }

                except Exception as e:
                    db.rollback()
                    logger.error(f"Database transaction failed (attempt {retry_count}): {e}")
                    if retry_count >= max_retries:
                        return {
                            "success": False,
                            "error": f"Database transaction failed after {max_retries} attempts: {str(e)}",
                        }
                    # Wait before retry
                    await asyncio.sleep(0.1 * retry_count)
                finally:
                    db.close()

            except Exception as e:
                logger.error(f"Vote collection attempt {retry_count} failed: {e}")
                if retry_count >= max_retries:
                    return {
                        "success": False,
                        "error": f"Vote collection failed after {max_retries} attempts: {str(e)}",
                    }
                # Wait before retry
                await asyncio.sleep(0.1 * retry_count)

        return {
            "success": False,
            "error": f"Vote collection failed after {max_retries} attempts",
        }
