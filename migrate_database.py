#!/usr/bin/env python3
"""
Database Migration Script
Updates the database schema to match the current models.
"""

import sqlite3
import os
import shutil
from pathlib import Path
from decouple import config


DB_PATH = config("DB_PATH", "./db/polly.db")


def migrate_database():
    """Migrate database to current schema"""
    db_path = DB_PATH

    if not os.path.exists(db_path):
        print("Database file not found. Please run the application first to create it.")
        return

    # Clean up cache directory before migration
    cache_dir = Path(".cache")
    if cache_dir.exists() and cache_dir.is_dir():
        try:
            shutil.rmtree(cache_dir)
            print("🗑️ Removed .cache directory before migration")
        except Exception as e:
            print(f"⚠️ Failed to remove .cache directory: {e}")

    print(f"Migrating database: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check current schema
        cursor.execute("PRAGMA table_info(polls)")
        columns = [row[1] for row in cursor.fetchall()]
        print(f"Current columns: {columns}")

        # Add missing columns to polls table
        migrations = []

        if "emojis_json" not in columns:
            migrations.append("ALTER TABLE polls ADD COLUMN emojis_json TEXT")

        if "server_name" not in columns:
            migrations.append("ALTER TABLE polls ADD COLUMN server_name VARCHAR(255)")

        if "channel_name" not in columns:
            migrations.append("ALTER TABLE polls ADD COLUMN channel_name VARCHAR(255)")

        if "timezone" not in columns:
            migrations.append(
                "ALTER TABLE polls ADD COLUMN timezone VARCHAR(50) DEFAULT 'UTC'"
            )

        if "anonymous" not in columns:
            migrations.append(
                "ALTER TABLE polls ADD COLUMN anonymous BOOLEAN DEFAULT 0"
            )

        # Execute migrations
        for migration in migrations:
            print(f"Executing: {migration}")
            cursor.execute(migration)

        # Create missing tables if they don't exist

        # Check if user_preferences table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='user_preferences'"
        )
        if not cursor.fetchone():
            print("Creating user_preferences table...")
            cursor.execute("""
                CREATE TABLE user_preferences (
                    id INTEGER NOT NULL PRIMARY KEY,
                    default_timezone VARCHAR(50) DEFAULT 'UTC',
                    last_server_id VARCHAR(50),
                    last_channel_id VARCHAR(50),
                    default_timezone VARCHAR(50) DEFAULT 'US/Eastern',
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users (id)
                )
            """)
            cursor.execute(
                "CREATE INDEX ix_user_preferences_id ON user_preferences (id)"
            )

        # Check if guilds table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='guilds'"
        )
        if not cursor.fetchone():
            print("Creating guilds table...")
            cursor.execute("""
                CREATE TABLE guilds (
                    id VARCHAR(50) NOT NULL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    icon VARCHAR(500),
                    owner_id VARCHAR(50) NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

        # Check if channels table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='channels'"
        )
        if not cursor.fetchone():
            print("Creating channels table...")
            cursor.execute("""
                CREATE TABLE channels (
                    id VARCHAR(50) NOT NULL PRIMARY KEY,
                    guild_id VARCHAR(50) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    type VARCHAR(50) NOT NULL,
                    position INTEGER DEFAULT 0,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(guild_id) REFERENCES guilds (id)
                )
            """)

        conn.commit()
        print("Database migration completed successfully!")

        # Show updated schema
        cursor.execute("PRAGMA table_info(polls)")
        columns = [row[1] for row in cursor.fetchall()]
        print(f"Updated columns: {columns}")

    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate_database()
