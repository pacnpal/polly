#!/usr/bin/env python3
"""
Simple migration to add emojis_json column to polls table
"""

import sqlite3
import sys
import json


def migrate():
    try:
        # Connect to database
        conn = sqlite3.connect("polls.db")
        cursor = conn.cursor()

        # Check if column already exists
        cursor.execute("PRAGMA table_info(polls)")
        columns = [row[1] for row in cursor.fetchall()]

        if "emojis_json" not in columns:
            print("Adding emojis_json column to polls table...")

            # Add the new column
            cursor.execute("ALTER TABLE polls ADD COLUMN emojis_json TEXT")

            # Set default emojis for existing polls based on their options count
            cursor.execute("SELECT id, options_json FROM polls")
            polls = cursor.fetchall()

            default_emojis = ["🇦", "🇧", "🇨", "🇩", "🇪", "🇫", "🇬", "🇭", "🇮", "🇯"]

            for poll_id, options_json in polls:
                if options_json:
                    options = json.loads(options_json)
                    emojis = default_emojis[: len(options)]
                    emojis_json = json.dumps(emojis)

                    cursor.execute(
                        "UPDATE polls SET emojis_json = ? WHERE id = ?",
                        (emojis_json, poll_id),
                    )
                    print(f"Updated poll {poll_id} with {len(emojis)} emojis")

            conn.commit()
            print("Migration completed successfully!")
        else:
            print("Column emojis_json already exists, skipping migration.")

    except Exception as e:
        print(f"Migration failed: {e}")
        return False
    finally:
        conn.close()

    return True


if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)
