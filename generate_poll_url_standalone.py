#!/usr/bin/env python3
"""
Generate One-Time Authenticated Poll URL (Standalone Version)
Creates a secure, one-time-use URL for viewing poll details that can be shared.
This version avoids importing the full web app to prevent Discord bot initialization.
"""

import asyncio
import sys
import os
import secrets
from datetime import datetime, timedelta
import pytz
from decouple import config

# Add the project directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from polly.database import get_db_session, Poll, TypeSafeColumn

# Global storage for one-time screenshot tokens (same as web_app.py)
_screenshot_tokens = {}

class ScreenshotToken:
    """Secure one-time-use token for dashboard screenshots"""
    
    def __init__(self, poll_id: int, creator_id: str, expires_in_minutes: int = 5):
        self.poll_id = poll_id
        self.creator_id = creator_id
        self.token = secrets.token_urlsafe(32)  # 256-bit secure random token
        self.created_at = datetime.now(pytz.UTC)
        self.expires_at = self.created_at + timedelta(minutes=expires_in_minutes)
        self.used = False
        self.used_at = None
        
    def is_valid(self) -> bool:
        """Check if token is still valid (not used and not expired)"""
        now = datetime.now(pytz.UTC)
        return not self.used and now < self.expires_at
        
    def mark_used(self) -> None:
        """Mark token as used (one-time use)"""
        self.used = True
        self.used_at = datetime.now(pytz.UTC)
        
    def to_dict(self) -> dict:
        """Convert to dictionary for storage"""
        return {
            "poll_id": self.poll_id,
            "creator_id": self.creator_id,
            "token": self.token,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "used": self.used,
            "used_at": self.used_at.isoformat() if self.used_at else None
        }

async def create_screenshot_token_standalone(poll_id: int, creator_id: str) -> str:
    """Create a secure one-time-use token for dashboard screenshots (standalone version)"""
    # Clean up expired tokens first
    await cleanup_expired_screenshot_tokens()
    
    # Create new token
    token_obj = ScreenshotToken(poll_id, creator_id)
    token_key = token_obj.token
    
    # Store token (in production, use Redis with TTL)
    _screenshot_tokens[token_key] = token_obj
    
    print(f"🔐 SCREENSHOT TOKEN - Created token for poll {poll_id} by user {creator_id}, expires at {token_obj.expires_at}")
    
    return token_key

async def cleanup_expired_screenshot_tokens():
    """Clean up expired and used screenshot tokens"""
    try:
        now = datetime.now(pytz.UTC)
        tokens_to_remove = []
        
        for token_key, token_obj in _screenshot_tokens.items():
            # Remove if expired or used more than 1 hour ago
            if (now > token_obj.expires_at or 
                (token_obj.used and token_obj.used_at and 
                 now > token_obj.used_at + timedelta(hours=1))):
                tokens_to_remove.append(token_key)
                
        for token_key in tokens_to_remove:
            del _screenshot_tokens[token_key]
            
        if tokens_to_remove:
            print(f"🔐 SCREENSHOT TOKEN - Cleaned up {len(tokens_to_remove)} expired/used tokens")
            
    except Exception as e:
        print(f"🔐 SCREENSHOT TOKEN - Error during token cleanup: {e}")

async def generate_poll_url(poll_id: int, base_url: str = "https://polly.pacnp.al") -> str | None:
    """Generate a one-time authenticated URL for a poll"""
    
    print(f"🔧 POLL URL - Generating authenticated URL for poll {poll_id}...")
    
    db = get_db_session()
    try:
        # Get poll from database
        poll = db.query(Poll).filter(Poll.id == poll_id).first()
        if not poll:
            print(f"❌ POLL URL - Poll {poll_id} not found")
            return None
            
        # Get poll details
        poll_name = TypeSafeColumn.get_string(poll, "name", "Unknown Poll")
        poll_status = TypeSafeColumn.get_string(poll, "status")
        creator_id = TypeSafeColumn.get_string(poll, "creator_id")
        
        print(f"📊 POLL URL - Found poll: '{poll_name}' (Status: {poll_status})")
        
        if not creator_id:
            print(f"❌ POLL URL - No creator_id found for poll {poll_id}")
            return None
            
        # Create secure one-time token using standalone function
        token = await create_screenshot_token_standalone(poll_id, creator_id)
        
        # Generate the authenticated URL
        auth_url = f"{base_url}/screenshot/poll/{poll_id}/dashboard?token={token}"
        
        print(f"✅ POLL URL - Generated authenticated URL for poll {poll_id}")
        print(f"🔐 POLL URL - Token expires in 5 minutes and is single-use only")
        
        return auth_url
        
    except Exception as e:
        print(f"❌ POLL URL - Error generating URL for poll {poll_id}: {e}")
        return None
    finally:
        db.close()

async def main():
    """Main CLI interface"""
    print("🚀 POLL URL GENERATOR - One-Time Authenticated URL Creator (Standalone)")
    print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
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
        print("🔗 ONE-TIME AUTHENTICATED URL:")
        print()
        print(auth_url)
        print()
        print("=" * 80)
        print()
        print("⚠️  IMPORTANT NOTES:")
        print("   • This URL expires in 5 minutes")
        print("   • This URL can only be used ONCE")
        print("   • After viewing, the URL becomes invalid")
        print("   • The URL provides full access to the poll dashboard")
        print()
        print("✅ URL generated successfully!")
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
