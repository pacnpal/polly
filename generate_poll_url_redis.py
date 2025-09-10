#!/usr/bin/env python3
"""
Generate One-Time Authenticated Poll URL (Redis-based Secure Version)
Creates a secure, one-time-use URL for viewing poll details that can be shared.
This version uses Redis for secure token storage shared with the web application.
"""

import asyncio
import sys
import os
import secrets
import hashlib
from datetime import datetime, timedelta
import pytz

# Add the project directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from polly.database import get_db_session, Poll, TypeSafeColumn
from polly.redis_client import get_redis_client

class SecureScreenshotToken:
    """Secure one-time-use token for dashboard screenshots with Redis storage"""
    
    def __init__(self, poll_id: int, creator_id: str, expires_in_minutes: int = 5):
        self.poll_id = poll_id
        self.creator_id = creator_id
        # Generate cryptographically secure token
        self.token = secrets.token_urlsafe(32)  # 256-bit secure random token
        self.created_at = datetime.now(pytz.UTC)
        self.expires_at = self.created_at + timedelta(minutes=expires_in_minutes)
        self.used = False
        self.used_at = None
        
        # Create secure hash for additional validation
        self.token_hash = hashlib.sha256(
            f"{self.token}:{poll_id}:{creator_id}:{self.created_at.isoformat()}".encode()
        ).hexdigest()
        
    def is_valid(self) -> bool:
        """Check if token is still valid (not used and not expired)"""
        now = datetime.now(pytz.UTC)
        return not self.used and now < self.expires_at
        
    def mark_used(self) -> None:
        """Mark token as used (one-time use)"""
        self.used = True
        self.used_at = datetime.now(pytz.UTC)
        
    def to_dict(self) -> dict:
        """Convert to dictionary for Redis storage"""
        return {
            "poll_id": self.poll_id,
            "creator_id": self.creator_id,
            "token": self.token,
            "token_hash": self.token_hash,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "used": self.used,
            "used_at": self.used_at.isoformat() if self.used_at else None
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'SecureScreenshotToken':
        """Create token object from Redis data"""
        token_obj = cls.__new__(cls)  # Create without calling __init__
        token_obj.poll_id = data["poll_id"]
        token_obj.creator_id = data["creator_id"]
        token_obj.token = data["token"]
        token_obj.token_hash = data["token_hash"]
        token_obj.created_at = datetime.fromisoformat(data["created_at"])
        token_obj.expires_at = datetime.fromisoformat(data["expires_at"])
        token_obj.used = data["used"]
        token_obj.used_at = datetime.fromisoformat(data["used_at"]) if data["used_at"] else None
        return token_obj

async def create_secure_screenshot_token(poll_id: int, creator_id: str) -> str:
    """Create a secure one-time-use token for dashboard screenshots using Redis"""
    try:
        # Get Redis client
        redis_client = await get_redis_client()
        if not redis_client.is_connected:
            raise Exception("Redis connection not available")
        
        # Clean up expired tokens first
        await cleanup_expired_screenshot_tokens_redis(redis_client)
        
        # Create new secure token
        token_obj = SecureScreenshotToken(poll_id, creator_id)
        token_key = f"screenshot_token:{token_obj.token}"
        
        # Store token in Redis with TTL (expires in 5 minutes + 30 seconds buffer)
        token_data = token_obj.to_dict()
        ttl_seconds = 330  # 5.5 minutes
        
        success = await redis_client.set(token_key, token_data, ttl=ttl_seconds)
        if not success:
            raise Exception("Failed to store token in Redis")
        
        # Also store a reverse lookup for cleanup (poll_id -> token)
        cleanup_key = f"screenshot_cleanup:{poll_id}:{token_obj.token}"
        await redis_client.set(cleanup_key, token_obj.token, ttl=ttl_seconds)
        
        print(f"🔐 SECURE TOKEN - Created Redis-backed token for poll {poll_id} by user {creator_id}")
        print(f"🔐 SECURE TOKEN - Token expires at {token_obj.expires_at} (TTL: {ttl_seconds}s)")
        print(f"🔐 SECURE TOKEN - Token hash: {token_obj.token_hash[:16]}...")
        
        return token_obj.token
        
    except Exception as e:
        print(f"❌ SECURE TOKEN - Error creating token: {e}")
        raise

async def cleanup_expired_screenshot_tokens_redis(redis_client):
    """Clean up expired screenshot tokens from Redis"""
    try:
        # Redis TTL will automatically handle expiration, but we can do additional cleanup
        # Get all screenshot token keys
        pattern = "screenshot_token:*"
        keys_to_check = []
        
        # Use scan_iter to avoid blocking Redis with large key sets
        if hasattr(redis_client._client, 'scan_iter'):
            async for key in redis_client._client.scan_iter(match=pattern, count=100):
                keys_to_check.append(key)
        
        if not keys_to_check:
            return
        
        # Check each token and remove if expired
        now = datetime.now(pytz.UTC)
        expired_keys = []
        
        for key in keys_to_check:
            try:
                token_data = await redis_client.get(key)
                if token_data and isinstance(token_data, dict):
                    expires_at = datetime.fromisoformat(token_data["expires_at"])
                    if now > expires_at:
                        expired_keys.append(key)
                        # Also remove cleanup key
                        poll_id = token_data["poll_id"]
                        token = token_data["token"]
                        cleanup_key = f"screenshot_cleanup:{poll_id}:{token}"
                        expired_keys.append(cleanup_key)
            except Exception as e:
                print(f"⚠️ SECURE TOKEN - Error checking token expiry for {key}: {e}")
                # If we can't parse the token, consider it expired
                expired_keys.append(key)
        
        if expired_keys:
            deleted = await redis_client.delete(*expired_keys)
            print(f"🔐 SECURE TOKEN - Cleaned up {deleted} expired Redis token entries")
            
    except Exception as e:
        print(f"❌ SECURE TOKEN - Error during Redis token cleanup: {e}")

async def generate_poll_url(poll_id: int, base_url: str = "https://polly.pacnp.al") -> str | None:
    """Generate a one-time authenticated URL for a poll using secure Redis tokens"""
    
    print(f"🔧 SECURE POLL URL - Generating authenticated URL for poll {poll_id}...")
    
    db = get_db_session()
    try:
        # Get poll from database
        poll = db.query(Poll).filter(Poll.id == poll_id).first()
        if not poll:
            print(f"❌ SECURE POLL URL - Poll {poll_id} not found")
            return None
            
        # Get poll details
        poll_name = TypeSafeColumn.get_string(poll, "name", "Unknown Poll")
        poll_status = TypeSafeColumn.get_string(poll, "status")
        creator_id = TypeSafeColumn.get_string(poll, "creator_id")
        
        print(f"📊 SECURE POLL URL - Found poll: '{poll_name}' (Status: {poll_status})")
        
        if not creator_id:
            print(f"❌ SECURE POLL URL - No creator_id found for poll {poll_id}")
            return None
            
        # Validate creator_id format (should be Discord user ID - numeric string)
        if not creator_id.isdigit():
            print(f"❌ SECURE POLL URL - Invalid creator_id format: {creator_id}")
            return None
            
        # Create secure one-time token using Redis
        token = await create_secure_screenshot_token(poll_id, creator_id)
        
        # Generate the authenticated URL
        auth_url = f"{base_url}/screenshot/poll/{poll_id}/dashboard?token={token}"
        
        print(f"✅ SECURE POLL URL - Generated authenticated URL for poll {poll_id}")
        print("🔐 SECURE POLL URL - Token expires in 5 minutes and is single-use only")
        print("🔐 SECURE POLL URL - Using Redis-backed secure token storage")
        
        return auth_url
        
    except Exception as e:
        print(f"❌ SECURE POLL URL - Error generating URL for poll {poll_id}: {e}")
        return None
    finally:
        db.close()

async def main():
    """Main CLI interface"""
    print("🚀 SECURE POLL URL GENERATOR - Redis-backed One-Time Authenticated URL Creator")
    print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("🔐 Using Redis for secure token storage")
    print()
    
    # Test Redis connection first
    try:
        redis_client = await get_redis_client()
        if not redis_client.is_connected:
            print("❌ Redis connection failed - tokens will not work with web application")
            print("   Please ensure Redis is running and accessible")
            sys.exit(1)
        else:
            print("✅ Redis connection successful")
    except Exception as e:
        print(f"❌ Redis connection error: {e}")
        sys.exit(1)
    
    # Get poll ID from command line argument or user input
    poll_id = None
    
    if len(sys.argv) > 1:
        try:
            poll_id = int(sys.argv[1])
        except ValueError:
            print(f"❌ Invalid poll ID: {sys.argv[1]}")
            sys.exit(1)
    else:
        # Interactive mode
        try:
            poll_id_input = input("Enter Poll ID: ").strip()
            poll_id = int(poll_id_input)
        except (ValueError, KeyboardInterrupt):
            print("\n❌ Invalid input or cancelled")
            sys.exit(1)
    
    # Get base URL (optional)
    base_url = "https://polly.pacnp.al"
    if len(sys.argv) > 2:
        base_url = sys.argv[2]
    
    print(f"🎯 Target Poll ID: {poll_id}")
    print(f"🌐 Base URL: {base_url}")
    print()
    
    # Generate the authenticated URL
    auth_url = await generate_poll_url(poll_id, base_url)
    
    if auth_url:
        print()
        print("=" * 80)
        print("🔗 SECURE ONE-TIME AUTHENTICATED URL:")
        print()
        print(auth_url)
        print()
        print("=" * 80)
        print()
        print("⚠️  SECURITY FEATURES:")
        print("   • Cryptographically secure 256-bit random token")
        print("   • SHA-256 hash validation for additional security")
        print("   • Redis-backed storage shared with web application")
        print("   • Automatic TTL expiration (5 minutes)")
        print("   • One-time use only (token consumed after access)")
        print("   • Creator ID validation and verification")
        print()
        print("⚠️  IMPORTANT NOTES:")
        print("   • This URL expires in 5 minutes")
        print("   • This URL can only be used ONCE")
        print("   • After viewing, the URL becomes invalid")
        print("   • The URL provides full access to the poll dashboard")
        print()
        print("✅ Secure URL generated successfully!")
    else:
        print()
        print("❌ Failed to generate authenticated URL")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)
