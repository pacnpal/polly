#!/usr/bin/env python3
"""
Generate One-Time Authenticated Poll URL
Creates a secure, one-time-use URL for viewing poll details that can be shared.
"""

import asyncio
import sys
import os
from datetime import datetime

# Add the project directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from polly.database import get_db_session, Poll, TypeSafeColumn
from polly.web_app import create_screenshot_token

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
            
        # Create secure one-time token
        token = await create_screenshot_token(poll_id, creator_id)
        
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
    print("🚀 POLL URL GENERATOR - One-Time Authenticated URL Creator")
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
