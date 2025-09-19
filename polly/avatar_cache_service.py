"""
Avatar Cache Service Module
Handles Discord user avatar caching with space optimization and deduplication.
"""

import asyncio
import logging
import aiohttp
import aiofiles
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse
try:
    from .enhanced_cache_service import get_enhanced_cache_service
except ImportError:
    from enhanced_cache_service import get_enhanced_cache_service  # type: ignore

logger = logging.getLogger(__name__)

# Image processing imports (optional dependencies)
try:
    from PIL import Image, ImageOps
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("PIL/Pillow not available - avatar image optimization disabled")


class AvatarCacheService:
    """
    Avatar caching service with advanced space optimization and deduplication
    
    Features:
    - Deduplication based on Discord avatar hashes
    - Image compression and format optimization
    - Size limits and cleanup
    - Efficient storage management
    - Cache statistics and monitoring
    """
    
    def __init__(self):
        self.cache_dir = Path("static/avatars")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Shared avatars directory for deduplication
        self.shared_dir = self.cache_dir / "shared"
        self.shared_dir.mkdir(exist_ok=True)
        
        # User-specific avatars directory (for non-deduplicated storage)
        self.users_dir = self.cache_dir / "users"
        self.users_dir.mkdir(exist_ok=True)
        
        self.enhanced_cache = get_enhanced_cache_service()
        
        # Configuration
        # Note: No file size limit for avatar downloads as per user requirement
        self.compression_quality = 85  # JPEG quality for compression
        self.enable_webp = True  # Convert to WebP for better compression
        self.enable_deduplication = True  # Enable deduplication by hash
        self.download_timeout = 30  # HTTP download timeout in seconds
        self.max_concurrent_downloads = 5  # Maximum concurrent downloads
        
        # Supported formats
        self.supported_formats = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
        
        # Download semaphore to limit concurrent downloads
        self._download_semaphore = asyncio.Semaphore(self.max_concurrent_downloads)
        
    def _extract_avatar_hash_from_url(self, avatar_url: str) -> Optional[str]:
        """
        Extract Discord avatar hash from URL for deduplication
        
        Discord avatar URLs follow patterns like:
        - https://cdn.discordapp.com/avatars/USER_ID/AVATAR_HASH.png
        - https://cdn.discordapp.com/avatars/USER_ID/a_AVATAR_HASH.gif (animated)
        """
        try:
            if not avatar_url or 'cdn.discordapp.com' not in avatar_url:
                return None
                
            # Parse URL path
            parsed = urlparse(avatar_url)
            path_parts = parsed.path.strip('/').split('/')
            
            # Expected format: ['avatars', 'user_id', 'avatar_hash.extension']
            if len(path_parts) >= 3 and path_parts[0] == 'avatars':
                avatar_filename = path_parts[2]
                # Remove extension and animated prefix
                avatar_hash = avatar_filename.split('.')[0]
                if avatar_hash.startswith('a_'):
                    avatar_hash = avatar_hash[2:]  # Remove animated prefix
                return avatar_hash
                
            return None
            
        except Exception as e:
            logger.warning(f"Error extracting avatar hash from URL {avatar_url}: {e}")
            return None
    
    def _get_optimal_format(self, original_format: str, is_animated: bool = False) -> str:
        """Determine optimal format for avatar storage"""
        if is_animated:
            return 'gif'  # Keep animated avatars as GIF
        elif self.enable_webp and PIL_AVAILABLE:
            return 'webp'  # WebP for best compression
        elif original_format.lower() in ['png', 'jpg', 'jpeg']:
            return 'jpg'  # JPEG for good compression
        else:
            return 'png'  # PNG as fallback
    
    def _get_avatar_path(self, avatar_hash: str, format: str, use_shared: bool = True) -> Path:
        """Get file path for avatar storage"""
        filename = f"{avatar_hash}.{format}"
        
        if use_shared and self.enable_deduplication:
            return self.shared_dir / filename
        else:
            return self.users_dir / filename
    
    async def _download_avatar(self, avatar_url: str) -> Optional[bytes]:
        """Download avatar image from Discord CDN"""
        async with self._download_semaphore:
            try:
                logger.debug(f"🔽 AVATAR DOWNLOAD - Starting download: {avatar_url}")
                
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.download_timeout)) as session:
                    async with session.get(avatar_url) as response:
                        if response.status == 200:
                            content = await response.read()
                            
                            # Log download size (no size limit enforced)
                            size_mb = len(content) / (1024 * 1024)
                            logger.info(f"✅ AVATAR DOWNLOAD - Downloaded {size_mb:.1f}MB: {avatar_url}")
                            return content
                        else:
                            logger.warning(f"⚠️ AVATAR DOWNLOAD - HTTP {response.status}: {avatar_url}")
                            return None
                            
            except asyncio.TimeoutError:
                logger.warning(f"⏰ AVATAR DOWNLOAD - Timeout downloading: {avatar_url}")
                return None
            except Exception as e:
                logger.error(f"❌ AVATAR DOWNLOAD - Error downloading {avatar_url}: {e}")
                return None
    
    async def _optimize_avatar_image(self, image_data: bytes, target_format: str) -> Optional[bytes]:
        """Optimize avatar image with compression and resizing"""
        if not PIL_AVAILABLE:
            return image_data  # Return original if PIL not available
        
        try:
            # Load image
            from io import BytesIO
            image_buffer = BytesIO(image_data)
            
            with Image.open(image_buffer) as img:
                # Handle transparency and animation
                is_animated = getattr(img, 'is_animated', False)
                
                if is_animated and target_format != 'gif':
                    # For animated images, keep as GIF or extract first frame
                    if target_format in ['webp', 'png']:
                        # WebP supports animation, PNG doesn't
                        if target_format == 'webp':
                            target_format = 'gif'  # Keep as GIF for compatibility
                        else:
                            # Extract first frame for static formats
                            img.seek(0)
                
                # Auto-orient based on EXIF
                img = ImageOps.exif_transpose(img)
                
                # Resize if too large
                if img.width > self.max_dimension or img.height > self.max_dimension:
                    img.thumbnail((self.max_dimension, self.max_dimension), Image.Resampling.LANCZOS)
                    logger.debug(f"📏 AVATAR RESIZE - Resized to {img.size}")
                
                # Convert format if needed
                if target_format == 'webp':
                    if img.mode in ('RGBA', 'LA'):
                        # Keep transparency for WebP
                        pass
                    elif img.mode == 'P':
                        img = img.convert('RGBA')
                elif target_format in ['jpg', 'jpeg']:
                    if img.mode in ('RGBA', 'LA', 'P'):
                        # Convert to RGB with white background for JPEG
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        if img.mode == 'P':
                            img = img.convert('RGBA')
                        background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                        img = background
                
                # Save optimized image
                output_buffer = BytesIO()
                
                if target_format == 'webp':
                    img.save(output_buffer, format='WebP', quality=self.compression_quality, optimize=True)
                elif target_format in ['jpg', 'jpeg']:
                    img.save(output_buffer, format='JPEG', quality=self.compression_quality, optimize=True)
                elif target_format == 'png':
                    img.save(output_buffer, format='PNG', optimize=True)
                elif target_format == 'gif':
                    img.save(output_buffer, format='GIF', optimize=True)
                else:
                    # Fallback to original format
                    img.save(output_buffer, format=img.format or 'PNG', optimize=True)
                
                optimized_data = output_buffer.getvalue()
                
                original_size = len(image_data)
                optimized_size = len(optimized_data)
                compression_ratio = ((original_size - optimized_size) / original_size * 100) if original_size > 0 else 0
                
                logger.info(f"🗜️ AVATAR OPTIMIZE - {original_size/1024:.1f}KB -> {optimized_size/1024:.1f}KB ({compression_ratio:.1f}% reduction)")
                
                return optimized_data
                
        except Exception as e:
            logger.error(f"❌ AVATAR OPTIMIZE - Error optimizing image: {e}")
            return image_data  # Return original on error
    
    async def cache_user_avatar(self, user_id: str, avatar_url: str, username: str = None) -> Optional[str]:
        """
        Cache a user's avatar with deduplication and optimization
        
        Args:
            user_id: Discord user ID
            avatar_url: Discord avatar URL
            username: Optional username for logging
            
        Returns:
            Local URL path to cached avatar, or None if failed
        """
        try:
            logger.info(f"👤 AVATAR CACHE - Caching avatar for user {user_id} ({username or 'Unknown'})")
            
            # Check if we already have this user's avatar cached
            cached_metadata = await self.enhanced_cache.get_cached_avatar_metadata(user_id)
            if cached_metadata and cached_metadata.get("avatar_url") == avatar_url:
                cached_path = cached_metadata.get("cached_path")
                if cached_path and Path(cached_path).exists():
                    logger.info(f"♻️ AVATAR CACHE - Using existing cached avatar for user {user_id}")
                    return f"/static/avatars/{Path(cached_path).relative_to(self.cache_dir)}"
            
            # Extract avatar hash for deduplication
            avatar_hash = self._extract_avatar_hash_from_url(avatar_url)
            if not avatar_hash:
                logger.warning(f"⚠️ AVATAR CACHE - Could not extract hash from URL: {avatar_url}")
                return None
            
            # Check if we already have this avatar hash cached (deduplication)
            if self.enable_deduplication:
                hash_mapping = await self.enhanced_cache.get_cached_avatar_hash_mapping(avatar_hash)
                if hash_mapping:
                    local_path = hash_mapping.get("local_path")
                    if local_path and Path(local_path).exists():
                        # Add this user to the hash mapping
                        await self.enhanced_cache.add_user_to_avatar_hash(avatar_hash, user_id)
                        
                        # Update user's avatar metadata
                        avatar_metadata = {
                            "avatar_url": avatar_url,
                            "avatar_hash": avatar_hash,
                            "cached_path": local_path,
                            "file_size": hash_mapping.get("file_size", 0),
                            "format": hash_mapping.get("format", "unknown"),
                            "username": username or "Unknown"
                        }
                        await self.enhanced_cache.cache_avatar_metadata(user_id, avatar_metadata)
                        
                        logger.info(f"♻️ AVATAR CACHE - Using deduplicated avatar for user {user_id} (hash: {avatar_hash})")
                        return f"/static/avatars/{Path(local_path).relative_to(self.cache_dir)}"
            
            # Download avatar
            image_data = await self._download_avatar(avatar_url)
            if not image_data:
                logger.error(f"❌ AVATAR CACHE - Failed to download avatar for user {user_id}")
                return None
            
            # Determine optimal format
            is_animated = avatar_url.lower().endswith('.gif') or 'a_' in avatar_url
            original_format = avatar_url.split('.')[-1].lower() if '.' in avatar_url else 'png'
            target_format = self._get_optimal_format(original_format, is_animated)
            
            # Optimize image
            optimized_data = await self._optimize_avatar_image(image_data, target_format)
            if not optimized_data:
                logger.error(f"❌ AVATAR CACHE - Failed to optimize avatar for user {user_id}")
                return None
            
            # Save to disk
            avatar_path = self._get_avatar_path(avatar_hash, target_format, self.enable_deduplication)
            
            async with aiofiles.open(avatar_path, 'wb') as f:
                await f.write(optimized_data)
            
            file_size = len(optimized_data)
            logger.info(f"💾 AVATAR CACHE - Saved avatar: {avatar_path} ({file_size/1024:.1f}KB)")
            
            # Update cache metadata
            avatar_metadata = {
                "avatar_url": avatar_url,
                "avatar_hash": avatar_hash,
                "cached_path": str(avatar_path),
                "file_size": file_size,
                "format": target_format,
                "username": username or "Unknown"
            }
            await self.enhanced_cache.cache_avatar_metadata(user_id, avatar_metadata)
            
            # Update hash mapping for deduplication
            if self.enable_deduplication:
                hash_info = {
                    "local_path": str(avatar_path),
                    "file_size": file_size,
                    "format": target_format,
                    "users": [user_id]
                }
                await self.enhanced_cache.cache_avatar_hash_mapping(avatar_hash, hash_info)
            
            # Return URL path
            relative_path = avatar_path.relative_to(self.cache_dir)
            return f"/static/avatars/{relative_path}"
            
        except Exception as e:
            logger.error(f"❌ AVATAR CACHE - Error caching avatar for user {user_id}: {e}")
            return None
    
    async def get_cached_avatar_url(self, user_id: str) -> Optional[str]:
        """Get cached avatar URL for a user"""
        try:
            cached_metadata = await self.enhanced_cache.get_cached_avatar_metadata(user_id)
            if not cached_metadata:
                return None
            
            cached_path = cached_metadata.get("cached_path")
            if not cached_path or not Path(cached_path).exists():
                # File doesn't exist, invalidate cache
                await self.enhanced_cache.invalidate_user_avatar_cache(user_id)
                return None
            
            # Return URL path
            relative_path = Path(cached_path).relative_to(self.cache_dir)
            return f"/static/avatars/{relative_path}"
            
        except Exception as e:
            logger.error(f"Error getting cached avatar for user {user_id}: {e}")
            return None
    
    async def cache_user_avatar_with_fallback(self, user_id: str, discord_user, default_avatar_url: str = None) -> str:
        """
        Cache user avatar with fallback to default avatar
        
        Args:
            user_id: Discord user ID
            discord_user: Discord user object (can be None)
            default_avatar_url: Fallback avatar URL
            
        Returns:
            Avatar URL (cached or fallback)
        """
        try:
            # Try to get cached avatar first
            cached_url = await self.get_cached_avatar_url(user_id)
            if cached_url:
                return cached_url
            
            # Try to cache from Discord user
            if discord_user and discord_user.avatar:
                avatar_url = str(discord_user.avatar.url)
                username = discord_user.display_name or discord_user.name
                
                cached_url = await self.cache_user_avatar(user_id, avatar_url, username)
                if cached_url:
                    return cached_url
            
            # Try default avatar URL
            if default_avatar_url:
                cached_url = await self.cache_user_avatar(user_id, default_avatar_url, "Default")
                if cached_url:
                    return cached_url
            
            # Final fallback - return Discord's default avatar or a placeholder
            if discord_user:
                return str(discord_user.default_avatar.url)
            else:
                return "/static/images/default_avatar.png"  # Placeholder
                
        except Exception as e:
            logger.error(f"Error caching avatar with fallback for user {user_id}: {e}")
            return "/static/images/default_avatar.png"  # Placeholder
    
    async def bulk_cache_avatars(self, user_data_list: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Cache multiple avatars concurrently
        
        Args:
            user_data_list: List of dicts with keys: user_id, avatar_url, username
            
        Returns:
            Dictionary mapping user_id to cached avatar URL
        """
        results = {}
        
        # Create tasks for concurrent processing
        tasks = []
        for user_data in user_data_list:
            user_id = user_data.get("user_id")
            avatar_url = user_data.get("avatar_url")
            username = user_data.get("username")
            
            if user_id and avatar_url:
                task = self.cache_user_avatar(user_id, avatar_url, username)
                tasks.append((user_id, task))
        
        # Execute tasks concurrently
        if tasks:
            logger.info(f"🔄 BULK AVATAR CACHE - Processing {len(tasks)} avatars concurrently")
            
            for user_id, task in tasks:
                try:
                    cached_url = await task
                    if cached_url:
                        results[user_id] = cached_url
                except Exception as e:
                    logger.error(f"Error in bulk avatar caching for user {user_id}: {e}")
        
        logger.info(f"✅ BULK AVATAR CACHE - Cached {len(results)}/{len(user_data_list)} avatars")
        return results
    
    async def cleanup_old_avatars(self, max_age_days: int = 30) -> Dict[str, int]:
        """
        Clean up old avatar files and cache entries
        
        Args:
            max_age_days: Maximum age in days before cleanup
            
        Returns:
            Cleanup statistics
        """
        stats = {
            "files_checked": 0,
            "files_deleted": 0,
            "cache_entries_cleaned": 0,
            "storage_freed_bytes": 0,
            "errors": 0
        }
        
        try:
            cutoff_time = datetime.now() - timedelta(days=max_age_days)
            
            # Clean up files in both shared and users directories
            for directory in [self.shared_dir, self.users_dir]:
                if not directory.exists():
                    continue
                
                for file_path in directory.iterdir():
                    if not file_path.is_file():
                        continue
                    
                    stats["files_checked"] += 1
                    
                    try:
                        # Check file age
                        file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                        
                        if file_mtime < cutoff_time:
                            file_size = file_path.stat().st_size
                            file_path.unlink()
                            
                            stats["files_deleted"] += 1
                            stats["storage_freed_bytes"] += file_size
                            
                            logger.info(f"🧹 AVATAR CLEANUP - Deleted old avatar: {file_path}")
                            
                    except Exception as e:
                        logger.error(f"Error cleaning up avatar file {file_path}: {e}")
                        stats["errors"] += 1
            
            # Clean up orphaned cache entries
            cache_cleanup = await self.enhanced_cache.cleanup_orphaned_avatars(max_age_days * 24)
            stats["cache_entries_cleaned"] = cache_cleanup.get("orphaned_hashes_cleaned", 0)
            
            logger.info(f"🧹 AVATAR CLEANUP - Cleaned {stats['files_deleted']} files, {stats['cache_entries_cleaned']} cache entries, freed {stats['storage_freed_bytes']/1024/1024:.1f}MB")
            
        except Exception as e:
            logger.error(f"Error during avatar cleanup: {e}")
            stats["error"] = str(e)
        
        return stats
    
    async def get_storage_stats(self) -> Dict[str, Any]:
        """Get comprehensive avatar storage statistics"""
        stats = {
            "local_files": {
                "shared_count": 0,
                "users_count": 0,
                "total_size_bytes": 0,
                "formats": {}
            },
            "cache_stats": {},
            "deduplication_enabled": self.enable_deduplication,
            "max_file_size_mb": None,  # No file size limit for avatar downloads
            "max_dimension": self.max_dimension,
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            # Count local files
            for directory, key in [(self.shared_dir, "shared_count"), (self.users_dir, "users_count")]:
                if directory.exists():
                    for file_path in directory.iterdir():
                        if file_path.is_file() and file_path.suffix.lower() in self.supported_formats:
                            stats["local_files"][key] += 1
                            
                            file_size = file_path.stat().st_size
                            stats["local_files"]["total_size_bytes"] += file_size
                            
                            format_ext = file_path.suffix.lower()
                            stats["local_files"]["formats"][format_ext] = stats["local_files"]["formats"].get(format_ext, 0) + 1
            
            # Get cache statistics
            stats["cache_stats"] = await self.enhanced_cache.get_avatar_storage_stats()
            
            logger.info(f"📊 AVATAR STORAGE - Local: {stats['local_files']['shared_count'] + stats['local_files']['users_count']} files, {stats['local_files']['total_size_bytes']/1024/1024:.1f}MB")
            
        except Exception as e:
            logger.error(f"Error gathering avatar storage stats: {e}")
            stats["error"] = str(e)
        
        return stats


# Global avatar cache service instance
_avatar_cache_service: Optional[AvatarCacheService] = None


def get_avatar_cache_service() -> AvatarCacheService:
    """Get or create avatar cache service instance"""
    global _avatar_cache_service
    
    if _avatar_cache_service is None:
        _avatar_cache_service = AvatarCacheService()
    
    return _avatar_cache_service


async def cache_user_avatar_safe(user_id: str, discord_user, username: str = None) -> str:
    """
    Convenience function to safely cache a user's avatar
    
    Args:
        user_id: Discord user ID
        discord_user: Discord user object (can be None)
        username: Optional username for fallback
        
    Returns:
        Avatar URL (cached or fallback)
    """
    try:
        avatar_service = get_avatar_cache_service()
        return await avatar_service.cache_user_avatar_with_fallback(user_id, discord_user)
    except Exception as e:
        logger.error(f"Error in safe avatar caching for user {user_id}: {e}")
        return "/static/images/default_avatar.png"
