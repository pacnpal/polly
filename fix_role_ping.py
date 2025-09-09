#!/usr/bin/env python3
"""
Fix for role ping functionality - adds missing ping_role_name population
"""

import asyncio
import logging
from polly.database import get_db_session, Poll
from polly.discord_bot import get_bot_instance

logger = logging.getLogger(__name__)

async def fix_existing_polls_role_names():
    """Fix existing polls that have ping_role_id but missing ping_role_name"""
    bot = get_bot_instance()
    if not bot:
        print("❌ Bot not available")
        return
    
    db = get_db_session()
    try:
        # Find polls with role ping enabled but missing role name
        polls_to_fix = db.query(Poll).filter(
            Poll.ping_role_enabled == True,
            Poll.ping_role_id.isnot(None),
            Poll.ping_role_name.is_(None)
        ).all()
        
        print(f"Found {len(polls_to_fix)} polls to fix")
        
        for poll in polls_to_fix:
            try:
                from polly.database import TypeSafeColumn
                
                server_id = TypeSafeColumn.get_string(poll, "server_id")
                role_id = TypeSafeColumn.get_string(poll, "ping_role_id")
                
                if not server_id or not role_id:
                    print(f"❌ Missing server_id or role_id for poll {poll.id}")
                    continue
                
                # Get the guild
                guild = bot.get_guild(int(server_id))
                if not guild:
                    print(f"❌ Guild {server_id} not found for poll {poll.id}")
                    continue
                
                # Get the role
                role = guild.get_role(int(role_id))
                if not role:
                    print(f"❌ Role {role_id} not found in guild {guild.name} for poll {poll.id}")
                    continue
                
                # Update the poll with the role name using setattr
                setattr(poll, "ping_role_name", role.name)
                print(f"✅ Fixed poll {poll.id}: set ping_role_name to '{role.name}'")
                
            except Exception as e:
                print(f"❌ Error fixing poll {poll.id}: {e}")
                continue
        
        # Commit all changes
        db.commit()
        print(f"✅ Successfully fixed {len(polls_to_fix)} polls")
        
    except Exception as e:
        print(f"❌ Critical error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("🔧 Fixing role ping functionality...")
    asyncio.run(fix_existing_polls_role_names())
