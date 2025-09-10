#!/usr/bin/env python3
"""
Comprehensive Database Migration System for Polly
Handles full database initialization and incremental migrations.
"""

import sqlite3
import os
import json
import logging
from datetime import datetime
from decouple import config
from typing import List, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# Default database path
DEFAULT_DB_PATH = config("DB_PATH", default="./db/polly.db")

# Default emojis for polls
DEFAULT_POLL_EMOJIS = ["🇦", "🇧", "🇨", "🇩", "🇪", "🇫", "🇬", "🇭", "🇮", "🇯"]


class DatabaseMigrator:
    """Handles database migrations and initialization"""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self.migrations = self._get_migrations()

    def _get_migrations(self) -> List[Dict[str, Any]]:
        """Define all database migrations in order"""
        return [
            {
                "version": 1,
                "name": "initial_schema",
                "description": "Create initial database schema",
                "sql": self._get_initial_schema_sql(),
            },
            {
                "version": 2,
                "name": "add_emojis_column",
                "description": "Add emojis_json column to polls table",
                "sql": ["ALTER TABLE polls ADD COLUMN emojis_json TEXT"],
                "post_migration": self._populate_default_emojis,
            },
            {
                "version": 3,
                "name": "add_server_channel_names",
                "description": "Add server_name and channel_name columns",
                "sql": [
                    "ALTER TABLE polls ADD COLUMN server_name VARCHAR(255)",
                    "ALTER TABLE polls ADD COLUMN channel_name VARCHAR(255)",
                ],
            },
            {
                "version": 4,
                "name": "add_timezone_anonymous",
                "description": "Add timezone and anonymous columns",
                "sql": [
                    "ALTER TABLE polls ADD COLUMN timezone VARCHAR(50) DEFAULT 'UTC'",
                    "ALTER TABLE polls ADD COLUMN anonymous BOOLEAN DEFAULT 0",
                ],
            },
            {
                "version": 5,
                "name": "add_image_message_text",
                "description": "Add image_message_text column for bulletproof operations",
                "sql": ["ALTER TABLE polls ADD COLUMN image_message_text TEXT"],
            },
            {
                "version": 6,
                "name": "add_multiple_choice",
                "description": "Add multiple_choice column to polls table",
                "sql": [
                    "ALTER TABLE polls ADD COLUMN multiple_choice BOOLEAN DEFAULT 0"
                ],
            },
            {
                "version": 7,
                "name": "add_role_ping_columns",
                "description": "Add role ping functionality columns",
                "sql": [
                    "ALTER TABLE polls ADD COLUMN ping_role_id VARCHAR(50)",
                    "ALTER TABLE polls ADD COLUMN ping_role_name VARCHAR(255)",
                    "ALTER TABLE polls ADD COLUMN ping_role_enabled BOOLEAN DEFAULT 0",
                    "ALTER TABLE user_preferences ADD COLUMN last_role_id VARCHAR(50)",
                ],
            },
            {
                "version": 8,
                "name": "add_timezone_explicitly_set",
                "description": "Add timezone_explicitly_set column to track if user has set timezone preference",
                "sql": [
                    "ALTER TABLE user_preferences ADD COLUMN timezone_explicitly_set BOOLEAN DEFAULT 0"
                ],
            },
            {
                "version": 9,
                "name": "add_open_immediately",
                "description": "Add open_immediately column to support immediate poll opening",
                "sql": [
                    "ALTER TABLE polls ADD COLUMN open_immediately BOOLEAN DEFAULT 0"
                ],
            },
        ]

    def _get_initial_schema_sql(self) -> List[str]:
        """Get SQL statements for initial database schema"""
        return [
            # Create polls table
            """
            CREATE TABLE polls (
                id INTEGER NOT NULL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                question TEXT NOT NULL,
                options_json TEXT NOT NULL,
                image_path VARCHAR(500),
                server_id VARCHAR(50) NOT NULL,
                channel_id VARCHAR(50) NOT NULL,
                creator_id VARCHAR(50) NOT NULL,
                message_id VARCHAR(50),
                open_time DATETIME NOT NULL,
                close_time DATETIME NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                status VARCHAR(20) DEFAULT 'scheduled'
            )
            """,
            "CREATE INDEX ix_polls_id ON polls (id)",
            # Create votes table
            """
            CREATE TABLE votes (
                id INTEGER NOT NULL PRIMARY KEY,
                poll_id INTEGER NOT NULL,
                user_id VARCHAR(50) NOT NULL,
                option_index INTEGER NOT NULL,
                voted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(poll_id) REFERENCES polls (id)
            )
            """,
            "CREATE INDEX ix_votes_id ON votes (id)",
            # Create users table
            """
            CREATE TABLE users (
                id VARCHAR(50) NOT NULL PRIMARY KEY,
                username VARCHAR(100) NOT NULL,
                avatar VARCHAR(500),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # Create user_preferences table
            """
            CREATE TABLE user_preferences (
                id INTEGER NOT NULL PRIMARY KEY,
                user_id VARCHAR(50) NOT NULL,
                last_server_id VARCHAR(50),
                last_channel_id VARCHAR(50),
                default_timezone VARCHAR(50) DEFAULT 'US/Eastern',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users (id)
            )
            """,
            "CREATE INDEX ix_user_preferences_id ON user_preferences (id)",
            # Create guilds table
            """
            CREATE TABLE guilds (
                id VARCHAR(50) NOT NULL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                icon VARCHAR(500),
                owner_id VARCHAR(50) NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # Create channels table
            """
            CREATE TABLE channels (
                id VARCHAR(50) NOT NULL PRIMARY KEY,
                guild_id VARCHAR(50) NOT NULL,
                name VARCHAR(255) NOT NULL,
                type VARCHAR(50) NOT NULL,
                position INTEGER DEFAULT 0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(guild_id) REFERENCES guilds (id)
            )
            """,
            # Create migration tracking table
            """
            CREATE TABLE schema_migrations (
                version INTEGER NOT NULL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
        ]

    def _populate_default_emojis(self, cursor: sqlite3.Cursor) -> None:
        """Populate default emojis for existing polls"""
        cursor.execute("SELECT id, options_json FROM polls WHERE emojis_json IS NULL")
        polls = cursor.fetchall()

        for poll_id, options_json in polls:
            if options_json:
                try:
                    options = json.loads(options_json)
                    emojis = DEFAULT_POLL_EMOJIS[: len(options)]
                    emojis_json = json.dumps(emojis)

                    cursor.execute(
                        "UPDATE polls SET emojis_json = ? WHERE id = ?",
                        (emojis_json, poll_id),
                    )
                    logger.info(
                        f"Updated poll {poll_id} with {len(emojis)} default emojis"
                    )
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Could not parse options for poll {poll_id}: {e}")

    def database_exists(self) -> bool:
        """Check if database file exists"""
        return Path(self.db_path).exists()

    def is_database_initialized(self) -> bool:
        """Check if database is properly initialized"""
        if not self.database_exists():
            return False

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Check if core tables exist
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name IN ('polls', 'votes', 'users')
            """)
            tables = [row[0] for row in cursor.fetchall()]

            conn.close()
            return len(tables) >= 3
        except sqlite3.Error:
            return False

    def get_current_schema_version(self) -> int:
        """Get current schema version from database"""
        if not self.database_exists():
            return 0

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Check if migrations table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='schema_migrations'
            """)

            if not cursor.fetchone():
                # No migrations table, check if database has basic structure
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='polls'
                """)
                if cursor.fetchone():
                    # Database exists but no migration tracking
                    # Determine version by checking columns
                    cursor.execute("PRAGMA table_info(polls)")
                    columns = [row[1] for row in cursor.fetchall()]

                    # Determine version based on existing columns
                    if "ping_role_enabled" in columns:
                        version = 7
                    elif "multiple_choice" in columns:
                        version = 6
                    elif "image_message_text" in columns:
                        version = 5
                    elif "anonymous" in columns:
                        version = 4
                    elif "server_name" in columns:
                        version = 3
                    elif "emojis_json" in columns:
                        version = 2
                    else:
                        version = 1

                    # Create migrations table and record current version
                    cursor.execute("""
                        CREATE TABLE schema_migrations (
                            version INTEGER NOT NULL PRIMARY KEY,
                            name VARCHAR(255) NOT NULL,
                            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    """)

                    # Record all migrations up to current version
                    for migration in self.migrations[:version]:
                        cursor.execute(
                            """
                            INSERT INTO schema_migrations (version, name, applied_at)
                            VALUES (?, ?, ?)
                        """,
                            (migration["version"], migration["name"], datetime.now()),
                        )

                    conn.commit()
                    conn.close()
                    return version
                else:
                    conn.close()
                    return 0

            # Get latest migration version
            cursor.execute("SELECT MAX(version) FROM schema_migrations")
            result = cursor.fetchone()
            conn.close()

            return result[0] if result[0] is not None else 0

        except sqlite3.Error as e:
            logger.error(f"Error getting schema version: {e}")
            return 0

    def needs_migration(self) -> bool:
        """Check if database needs migration"""
        if not self.database_exists():
            return True

        current_version = self.get_current_schema_version()
        latest_version = max(migration["version"] for migration in self.migrations)

        return current_version < latest_version

    def run_migrations(self) -> bool:
        """Run all necessary migrations"""
        try:
            current_version = self.get_current_schema_version()
            latest_version = max(migration["version"] for migration in self.migrations)

            if current_version >= latest_version:
                logger.info("Database is up to date")
                return True

            logger.info(
                f"Migrating database from version {current_version} to {latest_version}"
            )

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Enable foreign keys
            cursor.execute("PRAGMA foreign_keys = ON")

            for migration in self.migrations:
                if migration["version"] <= current_version:
                    continue

                logger.info(
                    f"Applying migration {migration['version']}: {migration['name']}"
                )

                try:
                    # Execute SQL statements
                    sql_statements = migration["sql"]
                    if isinstance(sql_statements, str):
                        sql_statements = [sql_statements]

                    for sql in sql_statements:
                        # Skip if column already exists (for ALTER TABLE statements)
                        if "ALTER TABLE" in sql and "ADD COLUMN" in sql:
                            table_name = (
                                sql.split("ALTER TABLE")[1]
                                .split("ADD COLUMN")[0]
                                .strip()
                            )
                            column_name = sql.split("ADD COLUMN")[1].split()[0].strip()

                            # Check if table exists first
                            cursor.execute(
                                """
                                SELECT name FROM sqlite_master 
                                WHERE type='table' AND name=?
                            """,
                                (table_name,),
                            )

                            if not cursor.fetchone():
                                logger.warning(
                                    f"Table {table_name} does not exist, skipping column addition for {column_name}"
                                )
                                continue

                            cursor.execute(f"PRAGMA table_info({table_name})")
                            columns = [row[1] for row in cursor.fetchall()]

                            if column_name in columns:
                                logger.info(
                                    f"Column {column_name} already exists in {table_name}, skipping"
                                )
                                continue

                        cursor.execute(sql)

                    # Run post-migration function if exists
                    if "post_migration" in migration:
                        migration["post_migration"](cursor)

                    # Record migration
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO schema_migrations (version, name, applied_at)
                        VALUES (?, ?, ?)
                    """,
                        (migration["version"], migration["name"], datetime.now()),
                    )

                    conn.commit()
                    logger.info(
                        f"Successfully applied migration {migration['version']}"
                    )

                except sqlite3.Error as e:
                    logger.error(
                        f"Error applying migration {migration['version']}: {e}"
                    )
                    conn.rollback()
                    conn.close()
                    return False

            conn.close()
            logger.info("All migrations completed successfully")
            return True

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            return False

    def initialize_database(self) -> bool:
        """Initialize database from scratch"""
        try:
            logger.info(f"Initializing database: {self.db_path}")

            # Remove existing database if it exists
            if self.database_exists():
                backup_path = f"{self.db_path}.backup.{int(datetime.now().timestamp())}"
                os.rename(self.db_path, backup_path)
                logger.info(f"Backed up existing database to {backup_path}")

            # Run all migrations
            return self.run_migrations()

        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            return False


def migrate_database_if_needed(db_path: str = DEFAULT_DB_PATH) -> bool:
    """
    Migrate database only if needed.
    Returns True if database is ready, False if migration failed.
    """
    migrator = DatabaseMigrator(db_path)

    if not migrator.needs_migration():
        logger.info("Database is up to date, no migration needed")
        return True

    logger.info("Database migration needed")
    return migrator.run_migrations()


def initialize_database_if_missing(db_path: str = DEFAULT_DB_PATH) -> bool:
    """
    Initialize database only if it doesn't exist or is not properly initialized.
    Returns True if database is ready, False if initialization failed.
    """
    migrator = DatabaseMigrator(db_path)

    if migrator.is_database_initialized() and not migrator.needs_migration():
        logger.info("Database is already initialized and up to date")
        return True

    if not migrator.database_exists():
        logger.info("Database does not exist, initializing from scratch")
        return migrator.initialize_database()

    if migrator.needs_migration():
        logger.info("Database exists but needs migration")
        return migrator.run_migrations()

    return True


# Convenience functions for backward compatibility
def init_database(db_path: str = DEFAULT_DB_PATH) -> bool:
    """Initialize database (backward compatibility)"""
    return initialize_database_if_missing(db_path)


if __name__ == "__main__":
    # Command line usage
    import sys

    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        db_path = DEFAULT_DB_PATH

    print("Polly Database Migration Tool")
    print(f"Database: {db_path}")
    print("-" * 50)

    migrator = DatabaseMigrator(db_path)

    if migrator.needs_migration():
        print("Migration needed")
        success = migrator.run_migrations()
        if success:
            print("✅ Migration completed successfully!")
            sys.exit(0)
        else:
            print("❌ Migration failed!")
            sys.exit(1)
    else:
        print("✅ Database is up to date")
        sys.exit(0)
