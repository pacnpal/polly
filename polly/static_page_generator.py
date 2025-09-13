"""
Static Page Generator Module
Generates static HTML pages for closed polls to reduce API load and improve caching.
"""

import json
import logging
import shutil
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

try:
    from .htmx_endpoints import format_datetime_for_user
    from .database import get_db_session, Poll, Vote, TypeSafeColumn
    from .enhanced_cache_service import get_enhanced_cache_service
    from .avatar_cache_service import get_avatar_cache_service
    from .data_utils import sanitize_data_for_json
except ImportError:
    from htmx_endpoints import format_datetime_for_user  # type: ignore
    from database import get_db_session, Poll, Vote, TypeSafeColumn  # type: ignore
    from enhanced_cache_service import get_enhanced_cache_service  # type: ignore
    from avatar_cache_service import get_avatar_cache_service  # type: ignore
    from data_utils import sanitize_data_for_json  # type: ignore
logger = logging.getLogger(__name__)

# Image compression imports (optional dependencies)
try:
    from PIL import Image, ImageOps
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("PIL/Pillow not available - image compression disabled")

# Browser automation imports for dashboard screenshots (optional dependencies)
# DISABLED: Screenshot functionality completely disabled per user request
# try:
#     from playwright.async_api import async_playwright
#     PLAYWRIGHT_AVAILABLE = True
# except ImportError:
#     PLAYWRIGHT_AVAILABLE = False
#     logger.warning("Playwright not available - dashboard screenshot capture disabled")

PLAYWRIGHT_AVAILABLE = False  # FORCE DISABLED - Screenshots not to be used at all

# print(f"📸 PLAYWRIGHT DEBUG - PLAYWRIGHT_AVAILABLE: {PLAYWRIGHT_AVAILABLE}")
class StaticPageGenerator:
    """Generates static HTML pages for closed polls"""
    
    def __init__(self):
        self.static_dir = Path("static/polls")
        self.static_dir.mkdir(parents=True, exist_ok=True)
        
        # Create images directory for static content
        self.images_dir = Path("static/images")
        self.images_dir.mkdir(parents=True, exist_ok=True)
        
        # Shared images directory for deduplication
        self.shared_images_dir = self.images_dir / "shared"
        self.shared_images_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup Jinja2 environment for static page generation
        self.jinja_env = Environment(
            loader=FileSystemLoader("templates"),
            autoescape=select_autoescape(['html', 'xml'])
        )
        
        self.enhanced_cache = get_enhanced_cache_service()
        
        # Image optimization settings
        self.max_image_size_mb = 5  # Maximum image size to keep
        self.supported_formats = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
        self.enable_deduplication = True  # Enable image deduplication
        
        # Image compression settings
        self.enable_compression = PIL_AVAILABLE  # Enable compression if PIL is available
        self.compression_quality = 80  # JPEG quality (1-100) - reduced for better compression
        self.max_width = 1200  # Maximum width for images - reduced for web optimization
        self.max_height = 800  # Maximum height for images - reduced for web optimization
        self.png_optimize = True  # Optimize PNG files
        self.webp_quality = 85  # WebP quality for modern browsers
        self.enable_webp_conversion = True  # Convert images to WebP when possible
        self.progressive_jpeg = True  # Enable progressive JPEG for better loading
        
        # Dashboard screenshot settings
        self.enable_dashboard_screenshots = PLAYWRIGHT_AVAILABLE  # Enable dashboard screenshots if Playwright is available
        self.screenshot_width = 1920  # Screenshot viewport width
        self.screenshot_height = 1080  # Screenshot viewport height
        self.screenshot_quality = 90  # Screenshot JPEG quality
        self.screenshot_timeout = 30000  # Screenshot timeout in milliseconds
        
    def _get_static_page_path(self, poll_id: int, page_type: str = "results") -> Path:
        """Get the file path for a static page"""
        filename = f"poll_{poll_id}_{page_type}.html"
        return self.static_dir / filename
        
    def _get_static_data_path(self, poll_id: int) -> Path:
        """Get the file path for static poll data JSON"""
        filename = f"poll_{poll_id}_data.json"
        return self.static_dir / filename
        
    async def generate_static_poll_details(self, poll_id: int, bot=None) -> bool:
        """Generate static poll details page (identical to current details page with dashboard)"""
        try:
            logger.info(f"🔧 STATIC GEN - Generating static poll details page for poll {poll_id}")
            
            db = get_db_session()
            try:
                poll = db.query(Poll).filter(Poll.id == poll_id).first()
                if not poll:
                    logger.error(f"❌ STATIC GEN - Poll {poll_id} not found")
                    return False
                    
                poll_status = TypeSafeColumn.get_string(poll, "status")
                if poll_status != "closed":
                    logger.warning(f"⚠️ STATIC GEN - Poll {poll_id} is not closed (status: {poll_status})")
                    return False
                    
                # Process images first to get mappings
                image_mappings = await self._process_poll_images(poll_id)
                
                # Get all votes for this poll
                votes = db.query(Vote).filter(Vote.poll_id == poll_id).order_by(Vote.voted_at.desc()).all()
                
                # Get poll data
                options = poll.options
                emojis = poll.emojis
                is_anonymous = TypeSafeColumn.get_bool(poll, "anonymous", False)
                
                # Prepare vote data with real Discord usernames and cached avatars (never anonymize for static pages)
                vote_data = []
                unique_users = set()
                avatar_cache = get_avatar_cache_service()
                
                for vote in votes:
                    try:
                        user_id = TypeSafeColumn.get_string(vote, "user_id")
                        option_index = TypeSafeColumn.get_int(vote, "option_index")
                        voted_at = TypeSafeColumn.get_datetime(vote, "voted_at")
                        
                        # Always fetch real Discord username for static pages (never anonymize)
                        username = "Unknown User"
                        avatar_url = None
                        
                        if bot and user_id:
                            try:
                                # Check if bot is ready before attempting to fetch user
                                if hasattr(bot, 'is_ready') and bot.is_ready():
                                    # Additional rate limiting protection in static generator
                                    import asyncio
                                    await asyncio.sleep(0.1)  # Extra 100ms delay for safety
                                    
                                    discord_user = await bot.fetch_user(int(user_id))
                                    if discord_user:
                                        username = discord_user.display_name or discord_user.name
                                        # Get cached avatar URL
                                        if discord_user.avatar:
                                            original_avatar_url = discord_user.avatar.url
                                            cached_avatar_url = await avatar_cache.cache_user_avatar(
                                                user_id, original_avatar_url, username
                                            )
                                            avatar_url = cached_avatar_url or original_avatar_url
                                else:
                                    logger.warning(f"Discord bot not ready, using fallback username for user {user_id}")
                                    username = f"User {user_id[:8]}..."
                            except Exception as e:
                                logger.warning(f"Could not fetch Discord user {user_id} for static generation: {e}")
                                username = f"User {user_id[:8]}..."
                        elif user_id:
                            username = f"User {user_id[:8]}..."
                        
                        # Get option details
                        option_text = options[option_index] if option_index < len(options) else "Unknown Option"
                        emoji = emojis[option_index] if option_index < len(emojis) else "📊"
                        
                        vote_data.append({
                            "username": username,
                            "avatar_url": avatar_url,
                            "option_index": option_index,
                            "option_text": option_text,
                            "emoji": emoji,
                            "voted_at": voted_at,
                            "is_unique": user_id not in unique_users
                        })
                        
                        unique_users.add(user_id)
                        
                    except Exception as e:
                        logger.error(f"Error processing vote data for static generation: {e}")
                        continue
                
                # Get summary statistics
                total_votes = len(votes)
                unique_voters = len(unique_users)
                results = poll.get_results()
                
                # DISABLED: Screenshot functionality completely disabled per user request
                # Check if dashboard screenshot exists
                dashboard_screenshot_url = None
                # screenshot_path = self._get_dashboard_screenshot_path(poll_id)
                # if screenshot_path.exists():
                #     dashboard_screenshot_url = f"/static/images/shared/{screenshot_path.name}"
                #     print(f"✅ SCREENSHOT DETECTED - Found existing screenshot for poll {poll_id}: {screenshot_path.name}")
                # else:
                #     print(f"⚠️ NO SCREENSHOT - No screenshot found for poll {poll_id}, using HTML fallback")
                # Generate static HTML using the component template
                template = self.jinja_env.get_template("static/poll_details_static_component.html")
                html_content = template.render(
                    poll=poll,
                    vote_data=vote_data,
                    total_votes=total_votes,
                    unique_voters=unique_voters,
                    results=results,
                    options=options,
                    emojis=emojis,
                    is_anonymous=is_anonymous,
                    generated_at=datetime.now(),
                    is_static=True,
                    show_usernames_to_creator=True,  # Always show real usernames in static pages
                    image_mappings=image_mappings,  # Pass image mappings to template
                    dashboard_screenshot_url=dashboard_screenshot_url,  # Pass screenshot URL to template
                    format_datetime_for_user=format_datetime_for_user,
                )
                
                # Update HTML content to use static image URLs
                if image_mappings:
                    html_content = self._update_html_image_references(html_content, image_mappings)
                    logger.info(f"📷 STATIC GEN - Updated {len(image_mappings)} image references in HTML")
                
                # Save static HTML file
                static_path = self._get_static_page_path(poll_id, "details")
                with open(static_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                    
                logger.info(f"✅ STATIC GEN - Generated static poll details page: {static_path}")
                return True
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"❌ STATIC GEN - Error generating static poll details for poll {poll_id}: {e}")
            logger.exception("Full traceback for static generation error:")
            return False
            
    async def generate_static_poll_dashboard(self, poll_id: int, bot=None) -> bool:
        """Generate static dashboard page for a closed poll"""
        try:
            logger.info(f"🔧 STATIC GEN - Generating static dashboard page for poll {poll_id}")
            
            db = get_db_session()
            try:
                poll = db.query(Poll).filter(Poll.id == poll_id).first()
                if not poll:
                    logger.error(f"❌ STATIC GEN - Poll {poll_id} not found")
                    return False
                    
                poll_status = TypeSafeColumn.get_string(poll, "status")
                if poll_status != "closed":
                    logger.warning(f"⚠️ STATIC GEN - Poll {poll_id} is not closed (status: {poll_status})")
                    return False
                    
                # Get all votes for this poll
                votes = db.query(Vote).filter(Vote.poll_id == poll_id).order_by(Vote.voted_at.desc()).all()
                
                # Get poll data
                options = poll.options
                emojis = poll.emojis
                is_anonymous = TypeSafeColumn.get_bool(poll, "anonymous", False)
                
                # Prepare vote data with real Discord usernames and cached avatars (never anonymize for static pages)
                vote_data = []
                unique_users = set()
                avatar_cache = get_avatar_cache_service()
                
                for vote in votes:
                    try:
                        user_id = TypeSafeColumn.get_string(vote, "user_id")
                        option_index = TypeSafeColumn.get_int(vote, "option_index")
                        voted_at = TypeSafeColumn.get_datetime(vote, "voted_at")
                        
                        # Always fetch real Discord username for static pages (never anonymize)
                        username = "Unknown User"
                        avatar_url = None
                        
                        if bot and user_id:
                            try:
                                # Check if bot is ready before attempting to fetch user
                                if hasattr(bot, 'is_ready') and bot.is_ready():
                                    # Additional rate limiting protection in static generator
                                    import asyncio
                                    await asyncio.sleep(0.1)  # Extra 100ms delay for safety
                                    
                                    discord_user = await bot.fetch_user(int(user_id))
                                    if discord_user:
                                        username = discord_user.display_name or discord_user.name
                                        # Get cached avatar URL
                                        if discord_user.avatar:
                                            original_avatar_url = discord_user.avatar.url
                                            cached_avatar_url = await avatar_cache.cache_user_avatar(
                                                user_id, original_avatar_url, username
                                            )
                                            avatar_url = cached_avatar_url or original_avatar_url
                                else:
                                    logger.warning(f"Discord bot not ready, using fallback username for user {user_id}")
                                    username = f"User {user_id[:8]}..."
                            except Exception as e:
                                logger.warning(f"Could not fetch Discord user {user_id} for static generation: {e}")
                                username = f"User {user_id[:8]}..."
                        elif user_id:
                            username = f"User {user_id[:8]}..."
                        
                        # Get option details
                        option_text = options[option_index] if option_index < len(options) else "Unknown Option"
                        emoji = emojis[option_index] if option_index < len(emojis) else "📊"
                        
                        vote_data.append({
                            "username": username,
                            "avatar_url": avatar_url,
                            "option_index": option_index,
                            "option_text": option_text,
                            "emoji": emoji,
                            "voted_at": voted_at,
                            "is_unique": user_id not in unique_users
                        })
                        
                        unique_users.add(user_id)
                        
                    except Exception as e:
                        logger.error(f"Error processing vote data for static generation: {e}")
                        continue
                
                # Get summary statistics
                total_votes = len(votes)
                unique_voters = len(unique_users)
                results = poll.get_results()
                
                # Generate static HTML using the dashboard component template
                template = self.jinja_env.get_template("htmx/components/poll_dashboard.html")
                html_content = template.render(
                    poll=poll,
                    vote_data=vote_data,
                    total_votes=total_votes,
                    unique_voters=unique_voters,
                    results=results,
                    options=options,
                    emojis=emojis,
                    is_anonymous=is_anonymous,
                    generated_at=datetime.now(),
                    is_static=True,
                    show_usernames_to_creator=True,  # Always show real usernames in static pages
                    format_datetime_for_user=format_datetime_for_user,
                )
                
                # Save static HTML file
                static_path = self._get_static_page_path(poll_id, "dashboard")
                with open(static_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                    
                logger.info(f"✅ STATIC GEN - Generated static dashboard page: {static_path}")
                return True
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"❌ STATIC GEN - Error generating static dashboard for poll {poll_id}: {e}")
            logger.exception("Full traceback for static dashboard generation error:")
            return False
            
    async def generate_static_poll_data(self, poll_id: int) -> bool:
        """Generate static JSON data file for a closed poll"""
        try:
            logger.info(f"🔧 STATIC GEN - Generating static data file for poll {poll_id}")
            
            db = get_db_session()
            try:
                poll = db.query(Poll).filter(Poll.id == poll_id).first()
                if not poll:
                    logger.error(f"❌ STATIC GEN - Poll {poll_id} not found")
                    return False
                    
                poll_status = TypeSafeColumn.get_string(poll, "status")
                if poll_status != "closed":
                    logger.warning(f"⚠️ STATIC GEN - Poll {poll_id} is not closed (status: {poll_status})")
                    return False
                    
                # Get all votes
                votes = db.query(Vote).filter(Vote.poll_id == poll_id).all()
                
                # Prepare static data
                static_data = {
                    "poll_id": poll_id,
                    "name": TypeSafeColumn.get_string(poll, "name", "Unknown Poll"),
                    "question": TypeSafeColumn.get_string(poll, "question", ""),
                    "options": poll.options,
                    "emojis": poll.emojis,
                    "total_votes": len(votes),
                    "unique_voters": len(set(TypeSafeColumn.get_string(vote, "user_id") for vote in votes)),
                    "results": poll.get_results(),
                    "is_anonymous": TypeSafeColumn.get_bool(poll, "anonymous", False),
                    "multiple_choice": TypeSafeColumn.get_bool(poll, "multiple_choice", False),
                    "close_time": TypeSafeColumn.get_datetime(poll, "close_time").isoformat() if TypeSafeColumn.get_datetime(poll, "close_time") is not None else None,
                    "generated_at": datetime.now().isoformat(),
                    "is_static": True
                }
                
                # Sanitize data for JSON serialization
                sanitized_data = sanitize_data_for_json(static_data)
                
                # Save static JSON file
                static_path = self._get_static_data_path(poll_id)
                with open(static_path, 'w', encoding='utf-8') as f:
                    json.dump(sanitized_data, f, indent=2, ensure_ascii=False)
                    
                logger.info(f"✅ STATIC GEN - Generated static data file: {static_path}")
                return True
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"❌ STATIC GEN - Error generating static data for poll {poll_id}: {e}")
            logger.exception("Full traceback for static data generation error:")
            return False
            
    async def generate_all_static_content(self, poll_id: int, bot=None) -> Dict[str, bool]:
        """Generate all static content for a closed poll - SCREENSHOTS FIRST, then HTML"""
        logger.info(f"🔧 STATIC GEN - Generating all static content with SCREENSHOT-FIRST approach for poll {poll_id}")
        
        # PHASE 1: Generate screenshot FIRST
        print(f"📸 PHASE 1 - Generating screenshot for poll {poll_id} (before HTML)")
        screenshot_success = await self.generate_dashboard_with_screenshot(poll_id, bot)
        
        # PHASE 2: Generate HTML details page AFTER screenshot (so it can reference it)
        print(f"📄 PHASE 2 - Generating HTML details page for poll {poll_id} (after screenshot)")
        details_success = await self.generate_static_poll_details(poll_id, bot)
        
        # PHASE 3: Generate JSON data file
        print(f"📊 PHASE 3 - Generating JSON data for poll {poll_id}")
        data_success = await self.generate_static_poll_data(poll_id)
        
        results = {
            "details_page": details_success,
            "dashboard_screenshot": screenshot_success,
            "data_file": data_success
        }
        
        success_count = sum(1 for success in results.values() if success)
        logger.info(f"✅ STATIC GEN - Generated {success_count}/3 static files for poll {poll_id} using SCREENSHOT-FIRST approach")
        
        return results
        
    def static_page_exists(self, poll_id: int, page_type: str = "results") -> bool:
        """Check if a static page exists for a poll"""
        static_path = self._get_static_page_path(poll_id, page_type)
        return static_path.exists()
        
    def get_static_page_url(self, poll_id: int, page_type: str = "results") -> str:
        """Get the URL for a static page"""
        filename = f"poll_{poll_id}_{page_type}.html"
        return f"/static/polls/{filename}"
        
    def get_static_data_url(self, poll_id: int) -> str:
        """Get the URL for static poll data"""
        filename = f"poll_{poll_id}_data.json"
        return f"/static/polls/{filename}"
        
    async def cleanup_static_files(self, poll_id: int) -> int:
        """Clean up static files for a poll (when poll is deleted)"""
        try:
            files_removed = 0
            
            # Remove results page
            results_path = self._get_static_page_path(poll_id, "results")
            if results_path.exists():
                results_path.unlink()
                files_removed += 1
                
            # Remove dashboard page
            dashboard_path = self._get_static_page_path(poll_id, "dashboard")
            if dashboard_path.exists():
                dashboard_path.unlink()
                files_removed += 1
                
            # Remove data file
            data_path = self._get_static_data_path(poll_id)
            if data_path.exists():
                data_path.unlink()
                files_removed += 1
            
            # Clean up poll-specific images (not shared ones)
            images_removed = await self._cleanup_poll_images(poll_id)
            files_removed += images_removed
                
            logger.info(f"🧹 STATIC GEN - Cleaned up {files_removed} static files (including {images_removed} images) for poll {poll_id}")
            return files_removed
            
        except Exception as e:
            logger.error(f"❌ STATIC GEN - Error cleaning up static files for poll {poll_id}: {e}")
            return 0
            
    async def get_static_file_info(self, poll_id: int) -> Dict[str, Any]:
        """Get information about static files for a poll"""
        info = {
            "poll_id": poll_id,
            "files": {},
            "total_size": 0
        }
        
        file_types = ["results", "dashboard", "data"]
        
        for file_type in file_types:
            if file_type == "data":
                path = self._get_static_data_path(poll_id)
            else:
                path = self._get_static_page_path(poll_id, file_type)
                
            if path.exists():
                stat = path.stat()
                info["files"][file_type] = {
                    "exists": True,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "url": self.get_static_data_url(poll_id) if file_type == "data" else self.get_static_page_url(poll_id, file_type)
                }
                info["total_size"] += stat.st_size
            else:
                info["files"][file_type] = {"exists": False}
                
        return info
        
    async def regenerate_static_content_if_needed(self, poll_id: int, bot=None) -> bool:
        """Regenerate static content if files are missing or outdated"""
        try:
            db = get_db_session()
            try:
                poll = db.query(Poll).filter(Poll.id == poll_id).first()
                if not poll or TypeSafeColumn.get_string(poll, "status") != "closed":
                    return False
                    
                # Check if any static files are missing
                results_exists = self.static_page_exists(poll_id, "results")
                dashboard_exists = self.static_page_exists(poll_id, "dashboard")
                data_exists = self._get_static_data_path(poll_id).exists()
                
                if not (results_exists and dashboard_exists and data_exists):
                    logger.info(f"🔄 STATIC GEN - Regenerating missing static content for poll {poll_id}")
                    results = await self.generate_all_static_content(poll_id, bot)
                    return all(results.values())
                    
                return True
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"❌ STATIC GEN - Error checking/regenerating static content for poll {poll_id}: {e}")
            return False

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of a file for deduplication"""
        try:
            hash_sha256 = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception as e:
            logger.error(f"❌ IMAGE HASH - Error calculating hash for {file_path}: {e}")
            return ""

    def _get_image_size_mb(self, file_path: Path) -> float:
        """Get file size in MB"""
        try:
            return file_path.stat().st_size / (1024 * 1024)
        except Exception:
            return 0.0

    def _is_supported_image(self, file_path: Path) -> bool:
        """Check if file is a supported image format"""
        return file_path.suffix.lower() in self.supported_formats

    async def _copy_image_with_optimization(self, source_path: Path, poll_id: int) -> Optional[str]:
        """
        Copy image to static storage with optimization strategies:
        1. Size filtering (skip images > max_image_size_mb)
        2. Deduplication (use shared storage for identical images)
        3. Format validation (only supported formats)
        4. Image compression and resizing (if PIL available)
        
        Returns: Static URL path if successful, None if skipped/failed
        """
        try:
            if not source_path.exists():
                logger.warning(f"⚠️ IMAGE COPY - Source image not found: {source_path}")
                return None
                
            if not self._is_supported_image(source_path):
                logger.info(f"📷 IMAGE COPY - Unsupported format, skipping: {source_path}")
                return None
                
            # Check file size
            size_mb = self._get_image_size_mb(source_path)
            if size_mb > self.max_image_size_mb:
                logger.info(f"📷 IMAGE COPY - Image too large ({size_mb:.1f}MB > {self.max_image_size_mb}MB), skipping: {source_path}")
                return None
                
            # Calculate hash for deduplication (before compression to avoid duplicate processing)
            file_hash = self._calculate_file_hash(source_path)
            if not file_hash:
                logger.error(f"❌ IMAGE COPY - Could not calculate hash for: {source_path}")
                return None
                
            # Generate filename with hash for deduplication
            file_extension = source_path.suffix.lower()
            
            # Determine optimal output format for compression
            if self.enable_compression and PIL_AVAILABLE:
                if self.enable_webp_conversion and file_extension in ['.png', '.jpg', '.jpeg', '.bmp', '.tiff']:
                    # WebP provides best compression for most images
                    compressed_extension = '.webp'
                elif file_extension in ['.png', '.bmp', '.tiff']:
                    # Convert to JPEG for better compression of non-transparent images
                    compressed_extension = '.jpg'
                else:
                    compressed_extension = file_extension
            else:
                compressed_extension = file_extension
                
            shared_filename = f"{file_hash}{compressed_extension}"
            shared_path = self.shared_images_dir / shared_filename
            
            # Check if image already exists in shared storage (deduplication)
            if shared_path.exists():
                logger.info(f"♻️ IMAGE COPY - Using existing deduplicated image: {shared_filename}")
                return f"/static/images/shared/{shared_filename}"
            
            # Determine destination path
            if self.enable_deduplication:
                dest_path = shared_path
                url_path = f"/static/images/shared/{shared_filename}"
            else:
                # Copy to poll-specific directory (no deduplication)
                poll_images_dir = self.images_dir / f"poll_{poll_id}"
                poll_images_dir.mkdir(exist_ok=True)
                
                dest_filename = f"{file_hash}{compressed_extension}"
                dest_path = poll_images_dir / dest_filename
                url_path = f"/static/images/poll_{poll_id}/{dest_filename}"
            
            # Copy and optionally compress image
            if self.enable_compression and PIL_AVAILABLE:
                success = await self._compress_and_copy_image(source_path, dest_path, file_extension)
                if success:
                    new_size_mb = self._get_image_size_mb(dest_path)
                    compression_ratio = ((size_mb - new_size_mb) / size_mb * 100) if size_mb > 0 else 0
                    logger.info(f"✅ IMAGE COPY - Compressed and copied image: {dest_path.name} ({size_mb:.1f}MB -> {new_size_mb:.1f}MB, {compression_ratio:.1f}% reduction)")
                    return url_path
                else:
                    logger.warning("⚠️ IMAGE COPY - Compression failed, falling back to direct copy")
                    
            # Fallback: direct copy without compression
            shutil.copy2(source_path, dest_path)
            logger.info(f"✅ IMAGE COPY - Copied image without compression: {dest_path.name} ({size_mb:.1f}MB)")
            return url_path
                
        except Exception as e:
            logger.error(f"❌ IMAGE COPY - Error copying image {source_path}: {e}")
            return None

    async def _compress_and_copy_image(self, source_path: Path, dest_path: Path, original_extension: str) -> bool:
        """
        Enhanced image compression with WebP support and better optimization
        
        Returns: True if successful, False if failed
        """
        if not PIL_AVAILABLE:
            return False
            
        try:
            # Open image
            with Image.open(source_path) as img:
                # Handle transparency for different formats
                has_transparency = img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info)
                
                # Convert image mode for optimal compression
                if self.enable_webp_conversion and dest_path.suffix.lower() == '.webp':
                    # WebP supports transparency, keep RGBA if needed
                    if img.mode == 'P':
                        img = img.convert('RGBA' if has_transparency else 'RGB')
                    elif img.mode not in ('RGBA', 'RGB', 'L'):
                        img = img.convert('RGBA' if has_transparency else 'RGB')
                elif dest_path.suffix.lower() in ['.jpg', '.jpeg']:
                    # JPEG doesn't support transparency, convert to RGB with white background
                    if has_transparency:
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        if img.mode == 'P':
                            img = img.convert('RGBA')
                        background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                        img = background
                    elif img.mode not in ('RGB', 'L'):
                        img = img.convert('RGB')
                elif dest_path.suffix.lower() == '.png':
                    # PNG supports transparency, preserve it
                    if img.mode == 'P':
                        img = img.convert('RGBA' if has_transparency else 'RGB')
                    elif img.mode not in ('RGBA', 'RGB', 'L'):
                        img = img.convert('RGBA' if has_transparency else 'RGB')
                
                # Auto-orient image based on EXIF data
                if PIL_AVAILABLE:
                    img = ImageOps.exif_transpose(img)
                
                # Resize if image is too large
                original_size = img.size
                if img.width > self.max_width or img.height > self.max_height:
                    # Use high-quality resampling
                    img.thumbnail((self.max_width, self.max_height), Image.Resampling.LANCZOS)
                    logger.info(f"📏 IMAGE RESIZE - Resized from {original_size} to {img.size}")
                
                # Determine save format and options based on destination extension
                dest_extension = dest_path.suffix.lower()
                
                if dest_extension == '.webp' and self.enable_webp_conversion:
                    # WebP format - excellent compression with quality
                    save_format = 'WebP'
                    save_options = {
                        'quality': self.webp_quality,
                        'method': 6,  # Compression method (0-6, higher = better compression)
                        'lossless': False,  # Use lossy compression for better file size
                        'optimize': True
                    }
                elif dest_extension in ['.jpg', '.jpeg']:
                    # JPEG format - good compression for photos
                    save_format = 'JPEG'
                    save_options = {
                        'quality': self.compression_quality,
                        'optimize': True,
                        'progressive': self.progressive_jpeg,
                        'subsampling': 0,  # Better quality subsampling
                        'qtables': 'web_high'  # Optimized quantization tables
                    }
                elif dest_extension == '.png':
                    # PNG format - lossless with optimization
                    save_format = 'PNG'
                    save_options = {
                        'optimize': self.png_optimize,
                        'compress_level': 9  # Maximum PNG compression (0-9)
                    }
                else:
                    # Fallback to original format
                    save_format = img.format or 'JPEG'
                    save_options = {'optimize': True}
                
                # Save compressed image
                img.save(dest_path, format=save_format, **save_options)
                
                logger.info(f"🗜️ IMAGE COMPRESS - Compressed {source_path.name} -> {dest_path.name} (format: {save_format})")
                return True
                
        except Exception as e:
            logger.error(f"❌ IMAGE COMPRESS - Error compressing image {source_path}: {e}")
            return False

    async def _process_poll_images(self, poll_id: int) -> Dict[str, str]:
        """
        Process and copy all images associated with a poll.
        
        Returns: Dictionary mapping original paths to static URLs
        """
        image_mappings = {}
        
        try:
            # Get poll from database to check for image references
            db = get_db_session()
            try:
                poll = db.query(Poll).filter(Poll.id == poll_id).first()
                if not poll:
                    return image_mappings
                
                # Check for images in poll data
                images_to_process = []
                
                # Check for image_path field (this is where poll images are actually stored)
                image_path = TypeSafeColumn.get_string(poll, "image_path")
                if image_path:
                    # Convert path to URL format for mapping
                    if image_path.startswith('static/uploads/'):
                        image_url = f"/{image_path}"  # Add leading slash for URL
                        local_path = Path(image_path)
                        if local_path.exists():
                            images_to_process.append((image_url, local_path))
                    elif image_path.startswith('/static/uploads/'):
                        # Already has leading slash
                        local_path = Path(image_path[1:])  # Remove leading slash for file path
                        if local_path.exists():
                            images_to_process.append((image_path, local_path))
                
                # Check for images in poll question or description
                question = TypeSafeColumn.get_string(poll, "question", "")
                description = TypeSafeColumn.get_string(poll, "description", "")
                
                # Look for image references in text (basic pattern matching)
                import re
                image_pattern = r'/static/uploads/[^\s\'"<>]+'
                
                for text in [question, description]:
                    if text:
                        matches = re.findall(image_pattern, text)
                        for match in matches:
                            local_path = Path(match[1:])  # Remove leading slash
                            if local_path.exists():
                                images_to_process.append((match, local_path))
                
                logger.info(f"📷 IMAGE PROCESS - Found {len(images_to_process)} images to process for poll {poll_id}")
                
                # Process each image
                for original_url, source_path in images_to_process:
                    static_url = await self._copy_image_with_optimization(source_path, poll_id)
                    if static_url:
                        image_mappings[original_url] = static_url
                        logger.info(f"📷 IMAGE PROCESS - Mapped {original_url} -> {static_url}")
                
                # Update database with compressed image paths
                if image_mappings:
                    await self._update_database_image_paths(poll_id, image_mappings)
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"❌ IMAGE PROCESS - Error processing images for poll {poll_id}: {e}")
        
        return image_mappings

    def _update_html_image_references(self, html_content: str, image_mappings: Dict[str, str]) -> str:
        """Update HTML content to use static image URLs"""
        updated_content = html_content
        
        for original_url, static_url in image_mappings.items():
            # Replace in src attributes
            updated_content = updated_content.replace(f'src="{original_url}"', f'src="{static_url}"')
            updated_content = updated_content.replace(f"src='{original_url}'", f"src='{static_url}'")
            
            # Replace in CSS background-image
            updated_content = updated_content.replace(f'url({original_url})', f'url({static_url})')
            updated_content = updated_content.replace(f'url("{original_url}")', f'url("{static_url}")')
            updated_content = updated_content.replace(f"url('{original_url}')", f"url('{static_url}')")
            
            # Replace direct references
            updated_content = updated_content.replace(original_url, static_url)
        
        return updated_content

    async def _update_database_image_paths(self, poll_id: int, image_mappings: Dict[str, str]) -> bool:
        """Update database with compressed image paths"""
        try:
            db = get_db_session()
            try:
                poll = db.query(Poll).filter(Poll.id == poll_id).first()
                if not poll:
                    logger.error(f"❌ DB UPDATE - Poll {poll_id} not found for image path update")
                    return False
                
                updated_fields = []
                
                # Update image_path field if it was compressed
                current_image_path = TypeSafeColumn.get_string(poll, "image_path")
                if current_image_path:
                    # Convert to URL format for mapping lookup
                    if current_image_path.startswith('static/uploads/'):
                        current_url = f"/{current_image_path}"
                    elif current_image_path.startswith('/static/uploads/'):
                        current_url = current_image_path
                    else:
                        current_url = current_image_path
                    
                    if current_url in image_mappings:
                        # Update to compressed image path (remove leading slash for database storage)
                        new_path = image_mappings[current_url]
                        if new_path.startswith('/'):
                            new_path = new_path[1:]  # Remove leading slash
                        
                        poll.image_path = new_path
                        updated_fields.append(f"image_path: {current_image_path} -> {new_path}")
                
                # Update question field if it contains image references
                question = TypeSafeColumn.get_string(poll, "question", "")
                if question:
                    updated_question = question
                    for original_url, compressed_url in image_mappings.items():
                        updated_question = updated_question.replace(original_url, compressed_url)
                    
                    if updated_question != question:
                        poll.question = updated_question
                        updated_fields.append("question field image references")
                
                if updated_fields:
                    db.commit()
                    logger.info(f"✅ DB UPDATE - Updated poll {poll_id} database fields: {', '.join(updated_fields)}")
                    return True
                else:
                    logger.info(f"📷 DB UPDATE - No database updates needed for poll {poll_id}")
                    return True
                    
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"❌ DB UPDATE - Error updating database image paths for poll {poll_id}: {e}")
            return False

    async def _cleanup_poll_images(self, poll_id: int) -> int:
        """Clean up images for a specific poll (non-shared images only)"""
        try:
            images_removed = 0
            
            # Only clean up poll-specific images, not shared ones
            poll_images_dir = self.images_dir / f"poll_{poll_id}"
            
            if poll_images_dir.exists():
                for image_file in poll_images_dir.iterdir():
                    if image_file.is_file():
                        image_file.unlink()
                        images_removed += 1
                
                # Remove directory if empty
                try:
                    poll_images_dir.rmdir()
                except OSError:
                    pass  # Directory not empty, that's fine
                    
                logger.info(f"🧹 IMAGE CLEANUP - Removed {images_removed} poll-specific images for poll {poll_id}")
            
            return images_removed
            
        except Exception as e:
            logger.error(f"❌ IMAGE CLEANUP - Error cleaning up images for poll {poll_id}: {e}")
            return 0

    def _get_dashboard_screenshot_path(self, poll_id: int) -> Path:
        """Get the file path for a dashboard screenshot"""
        filename = f"poll_{poll_id}_dashboard_screenshot.jpg"
        return self.shared_images_dir / filename
        
    # DISABLED: Screenshot functionality completely disabled per user request
    # async def capture_dashboard_screenshot(self, poll_id: int, creator_id: str, base_url: str = "https://polly.pacnp.al") -> Optional[str]:
    #     logger.info(f"📸 DEBUG - Starting capture_dashboard_screenshot for poll {poll_id}, creator_id: {creator_id}")
    #     print(f"📸 PRINT DEBUG - Starting capture_dashboard_screenshot for poll {poll_id}")
    #     """
    #     Capture a screenshot of the complete dashboard using headless browser with secure one-time token
    #     
    #     Args:
    #         poll_id: The poll ID
    #         creator_id: The poll creator's user ID
    #         base_url: Base URL of the application
    #         
    #     Returns: Static URL path to screenshot if successful, None if failed
    #     """
    #     if not self.enable_dashboard_screenshots:
    #         logger.warning(f"📸 SCREENSHOT - Playwright not available, skipping dashboard screenshot for poll {poll_id}")
    #         return None
    #         
    #     try:
    #         logger.info(f"📸 SCREENSHOT - Starting secure dashboard screenshot capture for poll {poll_id}")
    #         
    #         screenshot_path = self._get_dashboard_screenshot_path(poll_id)
    #         
    #         # Check if screenshot already exists
    #         if screenshot_path.exists():
    #             logger.info(f"📸 SCREENSHOT - Using existing dashboard screenshot for poll {poll_id}")
    #             return f"/static/images/shared/{screenshot_path.name}"
    #         
    #         # Create secure one-time token for authentication
    #         logger.info(f"📸 DEBUG - About to import create_screenshot_token and create token for poll {poll_id}")
    #         from .web_app import create_screenshot_token
    #         print(f"📸 PRINT DEBUG - About to create token for poll {poll_id}")
    #         token = await create_screenshot_token(poll_id, creator_id)
    #         logger.info(f"📸 DEBUG - Successfully imported create_screenshot_token, about to call it")
    #         print(f"🔑 DEBUG - Generated screenshot token: {token}")
    #         
    #         # Construct secure dashboard URL with token
    #         secure_dashboard_url = f"{base_url}/screenshot/poll/{poll_id}/dashboard?token={token}"
    #         print(f"🌐 DEBUG - Secure dashboard URL: {secure_dashboard_url}")
    #         
    #         logger.info(f"📸 SCREENSHOT - Using secure authenticated URL for poll {poll_id}")
    #         
    #         async with async_playwright() as p:
    #             # Launch headless browser (works without GUI)
    #             browser = await p.chromium.launch(
    #                 headless=True,  # Always headless for server environments
    #                 args=[
    #                     '--no-sandbox',
    #                     '--disable-setuid-sandbox',
    #                     '--disable-dev-shm-usage',
    #                     '--disable-gpu',
    #                     '--no-first-run',
    #                     '--no-default-browser-check',
    #                     '--disable-background-timer-throttling',
    #                     '--disable-backgrounding-occluded-windows',
    #                     '--disable-renderer-backgrounding'
    #                 ]
    #             )
    #             
    #             try:
    #                 # Create new page with specific viewport
    #                 page = await browser.new_page(
    #                     viewport={
    #                         'width': self.screenshot_width,
    #                         'height': self.screenshot_height
    #                     }
    #                 )
    #                 
    #                 # Set longer timeout for complex dashboards
    #                 page.set_default_timeout(self.screenshot_timeout)
    #                 
    #                 logger.info(f"📸 SCREENSHOT - Navigating to secure dashboard URL for poll {poll_id}")
    #                 
    #                 # Enable JavaScript (should be enabled by default, but make sure)
    #                 await page.add_init_script("console.log('JavaScript enabled for Polly screenshots');")
    #                 print("📸 DEBUG - JavaScript initialization script added")

    #                 # Navigate to secure dashboard
    #                 await page.goto(secure_dashboard_url, wait_until='networkidle')
    #                 
    #                 logger.info(f"📸 DEBUG - Page loaded successfully for poll {poll_id}, checking for dashboard content")
    #                 # Debug: Save page content for debugging
    #                 page_content = await page.content()
    #                 logger.info(f"📸 DEBUG - Page title: {await page.title()}")
    #                 logger.info(f"📸 DEBUG - Page content length: {len(page_content)} chars")
    #                 # Wait for dashboard content to load
    #                 # Wait for JavaScript to render dashboard content
    #                 print("📸 DEBUG - Waiting for JavaScript to render dashboard content...")
    #                 
    #                 # Execute JavaScript to wait for content to be truly visible
    #                 content_visible = await page.evaluate("""
    #                 async () => {
    #                     const maxWait = 20000; // 20 seconds max wait
    #                     const startTime = Date.now();
    #                     
    #                     while (Date.now() - startTime < maxWait) {
    #                         // Look for the dashboard content
    #                         const chartIcon = document.querySelector(".fas.fa-chart-bar");
    #                         if (chartIcon) {
    #                             const style = window.getComputedStyle(chartIcon);
    #                             const rect = chartIcon.getBoundingClientRect();
    #                             
    #                             // Check if element is truly visible (not hidden by CSS and has dimensions)
    #                             if (style.display !== "none" && 
    #                                 style.visibility !== "hidden" && 
    #                                 style.opacity !== "0" &&
    #                                 rect.width > 0 && 
    #                                 rect.height > 0) {
    #                                 return true;
    #                             }
    #                         }
    #                         
    #                         # Also check for any dashboard content cards
    #                         const dashboardCards = document.querySelectorAll(".card, [class*=dashboard]");
    #                         for (const card of dashboardCards) {
    #                             const style = window.getComputedStyle(card);
    #                             const rect = card.getBoundingClientRect();
    #                             if (style.display !== "none" && 
    #                                 style.visibility !== "hidden" && 
    #                                 rect.width > 0 && rect.height > 0) {
    #                                 return true;
    #                             }
    #                         }
    #                         
    #                         await new Promise(resolve => setTimeout(resolve, 200)); // Wait 200ms
    #                     }
    #                     return false;
    #                 }
    #                 """)
    #                 
    #                 if not content_visible:
    #                     print("⚠️  DEBUG - Dashboard content not visible after JavaScript wait, but continuing with screenshot")
    #                 else:
    #                     print("✅ DEBUG - Dashboard content is now visible!")

    #                 
    #                 # Wait for any images to load
    #                 await page.wait_for_load_state('networkidle')
    #                 
    #                 # Additional wait for Discord avatars and dynamic content
    #                 await page.wait_for_timeout(2000)
    #                 
    #                 logger.info("📸 SCREENSHOT - Capturing full page screenshot")
    #                 
    #                 # Capture full page screenshot
    #                 screenshot_bytes = await page.screenshot(
    #                     path=str(screenshot_path),
    #                     type='jpeg',
    #                     quality=self.screenshot_quality,
    #                     full_page=True
    #                 )
    #                 
    #                 logger.info(f"📸 SCREENSHOT - Successfully captured dashboard screenshot: {screenshot_path}")
    #                 
    #                 # Return static URL
    #                 return f"/static/images/shared/{screenshot_path.name}"
    #                 
    #             finally:
    #                 await browser.close()
    #                 
    #     except Exception as e:
    #         logger.error(f"❌ SCREENSHOT - Error capturing dashboard screenshot for poll {poll_id}: {e}")
    #         logger.exception("Full traceback for screenshot error:")
    #         return None
   # 
   # async def capture_dashboard_screenshot(self, poll_id: int, creator_id: str, base_url: str = "https://polly.pacnp.al") -> Optional[str]:
   #     """DISABLED: Screenshot functionality completely disabled per user request"""
   #     logger.info(f"📸 SCREENSHOT DISABLED - Skipping screenshot for poll {poll_id} (disabled per user request)")
   #     return None
   #         
   # async def generate_dashboard_with_screenshot(self, poll_id: int, bot=None, base_url: str = "https://polly.pacnp.al") -> bool:
   #     print(f"📸 PRINT DEBUG - Starting generate_dashboard_with_screenshot for poll {poll_id}")
   #     """
   #     Generate static dashboard with screenshot capture
   #     
   #     Args:
   #         poll_id: The poll ID
   #         bot: Discord bot instance
   #         base_url: Base URL of the application for screenshot capture
   #         
   #     Returns: True if successful, False if failed
   #     """
   #     try:
   #         logger.info(f"🔧 SCREENSHOT GEN - Generating dashboard with screenshot for poll {poll_id}")
   #         
   #         # First generate the regular static dashboard
   #         dashboard_success = await self.generate_static_poll_dashboard(poll_id, bot)
   #         if not dashboard_success:
   #             logger.error(f"❌ SCREENSHOT GEN - Failed to generate static dashboard for poll {poll_id}")
   #             return False
   #         
   #         # Get poll creator ID for secure token generation
   #         db = get_db_session()
   #         try:
   #             poll = db.query(Poll).filter(Poll.id == poll_id).first()
   #             if not poll:
   #                 logger.error(f"❌ SCREENSHOT GEN - Poll {poll_id} not found for screenshot")
   #                 return False
   #             
   #             creator_id = TypeSafeColumn.get_string(poll, "creator_id")
   #             logger.info(f"🔍 DEBUG - Poll {poll_id} creator_id: {creator_id}")
   #             if not creator_id:
   #                 logger.error(f"❌ SCREENSHOT GEN - No creator_id found for poll {poll_id}")
   #                 return False
   #                 
   #         finally:
   #             db.close()
   #         
   #         # Capture dashboard screenshot with secure token
   #         screenshot_url = await self.capture_dashboard_screenshot(poll_id, creator_id, base_url)
   #         print(f"📸 PRINT DEBUG - About to call capture_dashboard_screenshot for poll {poll_id}")
   #         
   #         if screenshot_url:
   #             logger.info(f"✅ SCREENSHOT GEN - Successfully generated dashboard with screenshot for poll {poll_id}")
   #             return True
   #         else:
   #             logger.warning(f"⚠️ SCREENSHOT GEN - Dashboard generated but screenshot failed for poll {poll_id}")
   #             return True  # Still consider success since we have the HTML
   #             
   #     except Exception as e:
   #         logger.error(f"❌ SCREENSHOT GEN - Error generating dashboard with screenshot for poll {poll_id}: {e}")
   #         return False

    async def get_image_storage_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics about image storage"""
        stats = {
            "shared_images": {
                "count": 0,
                "total_size_mb": 0.0,
                "formats": {}
            },
            "poll_specific_images": {
                "count": 0,
                "total_size_mb": 0.0,
                "polls_with_images": 0
            },
            "total_storage_mb": 0.0,
            "deduplication_enabled": self.enable_deduplication,
            "max_image_size_mb": self.max_image_size_mb,
            "supported_formats": list(self.supported_formats)
        }
        
        try:
            # Count shared images
            if self.shared_images_dir.exists():
                for image_file in self.shared_images_dir.iterdir():
                    if image_file.is_file() and self._is_supported_image(image_file):
                        stats["shared_images"]["count"] += 1
                        size_mb = self._get_image_size_mb(image_file)
                        stats["shared_images"]["total_size_mb"] += size_mb
                        
                        # Count by format
                        format_ext = image_file.suffix.lower()
                        stats["shared_images"]["formats"][format_ext] = stats["shared_images"]["formats"].get(format_ext, 0) + 1
            
            # Count poll-specific images
            if self.images_dir.exists():
                for poll_dir in self.images_dir.iterdir():
                    if poll_dir.is_dir() and poll_dir.name.startswith("poll_"):
                        poll_image_count = 0
                        for image_file in poll_dir.iterdir():
                            if image_file.is_file() and self._is_supported_image(image_file):
                                stats["poll_specific_images"]["count"] += 1
                                size_mb = self._get_image_size_mb(image_file)
                                stats["poll_specific_images"]["total_size_mb"] += size_mb
                                poll_image_count += 1
                        
                        if poll_image_count > 0:
                            stats["poll_specific_images"]["polls_with_images"] += 1
            
            # Calculate total storage
            stats["total_storage_mb"] = stats["shared_images"]["total_size_mb"] + stats["poll_specific_images"]["total_size_mb"]
            
            logger.info(f"📊 IMAGE STATS - Total: {stats['total_storage_mb']:.1f}MB, Shared: {stats['shared_images']['count']}, Poll-specific: {stats['poll_specific_images']['count']}")
            
        except Exception as e:
            logger.error(f"❌ IMAGE STATS - Error gathering image statistics: {e}")
            stats["error"] = str(e)
        
        return stats


# Global static page generator instance
_static_page_generator: Optional[StaticPageGenerator] = None


def get_static_page_generator() -> StaticPageGenerator:
    """Get or create static page generator instance"""
    global _static_page_generator
    
    if _static_page_generator is None:
        _static_page_generator = StaticPageGenerator()
        
    return _static_page_generator


async def generate_static_content_on_poll_close(poll_id: int, bot=None) -> bool:
    """Convenience function to generate static content when a poll closes"""
    generator = get_static_page_generator()
    results = await generator.generate_all_static_content(poll_id, bot)
    
    # Also update cache with long TTL for closed polls
    enhanced_cache = get_enhanced_cache_service()
    await enhanced_cache.invalidate_poll_related_cache(poll_id)
    
    return all(results.values())
