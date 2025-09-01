#!/usr/bin/env python3
"""
Database migration script to add image_message_text column to polls table.
Run this script to update existing databases with the new bulletproof operations feature.
"""

import sqlite3
import os
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate_database():
    """Add image_message_text column to polls table if it doesn't exist"""
    db_path = "polly.db"

    if not os.path.exists(db_path):
        logger.info(f"Database {db_path} does not exist. No migration needed.")
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if column already exists
        cursor.execute("PRAGMA table_info(polls)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'image_message_text' in columns:
            logger.info(
                "Column 'image_message_text' already exists. No migration needed.")
            return

        # Add the new column
        logger.info("Adding 'image_message_text' column to polls table...")
        cursor.execute("ALTER TABLE polls ADD COLUMN image_message_text TEXT")

        conn.commit()
        logger.info(
            "Successfully added 'image_message_text' column to polls table.")

    except Exception as e:
        logger.error(f"Error during migration: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate_database()
