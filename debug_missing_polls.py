#!/usr/bin/env python3
"""
Quick diagnostic script for missing polls issue
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from polly.database import get_db_session, Poll, TypeSafeColumn

def check_user_polls(user_id: str):
    """Check what polls a user actually has"""
    db = get_db_session()
    try:
        polls = db.query(Poll).filter(Poll.creator_id == user_id).all()
        
        print(f"\n🔍 USER {user_id} POLL ANALYSIS:")
        print(f"Total polls: {len(polls)}")
        
        if not polls:
            print("❌ No polls found for this user")
            return
        
        # Group by status
        status_counts = {}
        for poll in polls:
            status = TypeSafeColumn.get_string(poll, "status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print(f"Status breakdown: {status_counts}")
        
        # Show recent polls
        print(f"\n📋 Recent polls:")
        for i, poll in enumerate(polls[:5]):
            poll_id = TypeSafeColumn.get_int(poll, "id")
            poll_name = TypeSafeColumn.get_string(poll, "name")
            poll_status = TypeSafeColumn.get_string(poll, "status")
            created_at = TypeSafeColumn.get_datetime(poll, "created_at")
            
            print(f"  {i+1}. Poll {poll_id}: '{poll_name}' - Status: {poll_status} - Created: {created_at}")
        
        # Check for data integrity issues
        print(f"\n🔧 Data integrity check:")
        issues = []
        for poll in polls:
            poll_id = TypeSafeColumn.get_int(poll, "id")
            try:
                options = poll.options
                emojis = poll.emojis
                if not options:
                    issues.append(f"Poll {poll_id}: No options")
                if len(options) != len(emojis):
                    issues.append(f"Poll {poll_id}: Options/emojis mismatch ({len(options)} vs {len(emojis)})")
            except Exception as e:
                issues.append(f"Poll {poll_id}: Error accessing data - {e}")
        
        if issues:
            print("❌ Issues found:")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print("✅ All polls have valid data")
            
    finally:
        db.close()

def check_all_users():
    """Check poll distribution across all users"""
    db = get_db_session()
    try:
        polls = db.query(Poll).all()
        
        print(f"\n🌍 GLOBAL POLL ANALYSIS:")
        print(f"Total polls in database: {len(polls)}")
        
        # Group by user
        user_counts = {}
        status_counts = {}
        
        for poll in polls:
            creator_id = TypeSafeColumn.get_string(poll, "creator_id")
            status = TypeSafeColumn.get_string(poll, "status", "unknown")
            
            user_counts[creator_id] = user_counts.get(creator_id, 0) + 1
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print(f"Users with polls: {len(user_counts)}")
        print(f"Status distribution: {status_counts}")
        
        # Show top users
        top_users = sorted(user_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        print(f"\nTop users by poll count:")
        for user_id, count in top_users:
            print(f"  {user_id}: {count} polls")
            
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        user_id = sys.argv[1]
        check_user_polls(user_id)
    else:
        check_all_users()
        print("\nUsage: python debug_missing_polls.py <user_id>")
        print("Example: python debug_missing_polls.py 796749752133091339")
