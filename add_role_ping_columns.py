#!/usr/bin/env python3
"""
Database migration script to add role ping columns to existing Polly database.
Run this script to add the new role ping functionality to existing installations.
"""

import sqlite3
import os
import sys
from datetime import datetime

def migrate_database():
    """Add role ping columns to existing database"""
    db_path = "polly.db"
    
    if not os.path.exists(db_path):
        print(f"Database file {db_path} not found. No migration needed for new installations.")
        return True
    
    print("Starting database migration for role ping feature...")
    print(f"Database: {db_path}")
    print(f"Time: {datetime.now()}")
    
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(polls)")
        columns = [column[1] for column in cursor.fetchall()]
        
        polls_columns_to_add = []
        if 'ping_role_id' not in columns:
            polls_columns_to_add.append('ping_role_id')
        if 'ping_role_name' not in columns:
            polls_columns_to_add.append('ping_role_name')
        if 'ping_role_enabled' not in columns:
            polls_columns_to_add.append('ping_role_enabled')
        
        # Add columns to polls table
        if polls_columns_to_add:
            print(f"Adding columns to polls table: {polls_columns_to_add}")
            
            if 'ping_role_id' in polls_columns_to_add:
                cursor.execute("ALTER TABLE polls ADD COLUMN ping_role_id VARCHAR(50)")
                print("✅ Added ping_role_id column to polls table")
            
            if 'ping_role_name' in polls_columns_to_add:
                cursor.execute("ALTER TABLE polls ADD COLUMN ping_role_name VARCHAR(255)")
                print("✅ Added ping_role_name column to polls table")
            
            if 'ping_role_enabled' in polls_columns_to_add:
                cursor.execute("ALTER TABLE polls ADD COLUMN ping_role_enabled BOOLEAN DEFAULT 0")
                print("✅ Added ping_role_enabled column to polls table")
        else:
            print("✅ All polls table columns already exist")
        
        # Check user_preferences table
        cursor.execute("PRAGMA table_info(user_preferences)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'last_role_id' not in columns:
            print("Adding last_role_id column to user_preferences table")
            cursor.execute("ALTER TABLE user_preferences ADD COLUMN last_role_id VARCHAR(50)")
            print("✅ Added last_role_id column to user_preferences table")
        else:
            print("✅ user_preferences table already has last_role_id column")
        
        # Commit changes
        conn.commit()
        print("✅ Database migration completed successfully!")
        
        # Verify the changes
        cursor.execute("PRAGMA table_info(polls)")
        polls_columns = [column[1] for column in cursor.fetchall()]
        
        cursor.execute("PRAGMA table_info(user_preferences)")
        prefs_columns = [column[1] for column in cursor.fetchall()]
        
        print("\nVerification:")
        print(f"Polls table columns: {len(polls_columns)} total")
        print(f"User preferences columns: {len(prefs_columns)} total")
        
        required_polls_columns = ['ping_role_id', 'ping_role_name', 'ping_role_enabled']
        missing_polls = [col for col in required_polls_columns if col not in polls_columns]
        
        required_prefs_columns = ['last_role_id']
        missing_prefs = [col for col in required_prefs_columns if col not in prefs_columns]
        
        if missing_polls or missing_prefs:
            print("❌ Migration incomplete!")
            if missing_polls:
                print(f"Missing polls columns: {missing_polls}")
            if missing_prefs:
                print(f"Missing user_preferences columns: {missing_prefs}")
            return False
        else:
            print("✅ All required columns present")
            return True
        
    except sqlite3.Error as e:
        print(f"❌ Database error during migration: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error during migration: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    print("Polly Database Migration - Role Ping Feature")
    print("=" * 50)
    
    success = migrate_database()
    
    if success:
        print("\n🎉 Migration completed successfully!")
        print("You can now use the role ping feature in Polly.")
        sys.exit(0)
    else:
        print("\n❌ Migration failed!")
        print("Please check the error messages above and try again.")
        sys.exit(1)
