#!/usr/bin/env python3
"""
Add multiple_choice column to polls table
"""

import sqlite3
import sys
from pathlib import Path


def add_multiple_choice_column():
    """Add multiple_choice column to polls table"""
    db_path = Path("polly.db")

    if not db_path.exists():
        print("❌ Database file polly.db not found!")
        return False

    conn = None
    try:
        # Connect to database
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Check if column already exists
        cursor.execute("PRAGMA table_info(polls)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'multiple_choice' in columns:
            print("✅ multiple_choice column already exists")
            return True

        # Add the column
        print("📝 Adding multiple_choice column to polls table...")
        cursor.execute("""
            ALTER TABLE polls 
            ADD COLUMN multiple_choice BOOLEAN DEFAULT FALSE
        """)

        # Commit changes
        conn.commit()
        print("✅ Successfully added multiple_choice column")

        # Verify the column was added
        cursor.execute("PRAGMA table_info(polls)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'multiple_choice' in columns:
            print("✅ Column addition verified")
            return True
        else:
            print("❌ Column addition verification failed")
            return False

    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    print("🔄 Adding multiple_choice column to polls table...")
    success = add_multiple_choice_column()

    if success:
        print("🎉 Migration completed successfully!")
        sys.exit(0)
    else:
        print("💥 Migration failed!")
        sys.exit(1)
