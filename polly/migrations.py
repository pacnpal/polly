#!/usr/bin/env python3
"""
Comprehensive Database Migration System for Polly
Handles full database initialization and incremental migrations.

Supports SQLite (default), PostgreSQL, and MariaDB/MySQL.
The backend is selected by the DATABASE_URL environment variable:
  sqlite:///./db/polly.db          (default)
  postgresql://user:pass@host/db
  mysql+pymysql://user:pass@host/db
"""

import sqlite3
import os
import json
import logging
import shutil
import pytz
from datetime import datetime
from decouple import config
from typing import List, Dict, Any, Union
from pathlib import Path
from sqlalchemy.engine import make_url

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
            {
                "version": 10,
                "name": "add_role_ping_notification_options",
                "description": "Add separate options for role ping on poll closure and updates",
                "sql": [
                    "ALTER TABLE polls ADD COLUMN ping_role_on_close BOOLEAN DEFAULT 0",
                    "ALTER TABLE polls ADD COLUMN ping_role_on_update BOOLEAN DEFAULT 0"
                ],
            },
            {
                "version": 11,
                "name": "add_max_choices",
                "description": "Add max_choices column for configurable multiple choice limits",
                "sql": [
                    "ALTER TABLE polls ADD COLUMN max_choices INTEGER"
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
            # Delete .cache directory if it exists before running migrations
            self._cleanup_cache_directory()
            
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

    def _cleanup_cache_directory(self) -> None:
        """Delete .cache directory if it exists to ensure fresh cache after migrations"""
        cache_dir = Path(".cache")
        if cache_dir.exists() and cache_dir.is_dir():
            try:
                shutil.rmtree(cache_dir)
                logger.info("Removed .cache directory before database migration")
            except Exception as e:
                logger.warning(f"Failed to remove .cache directory: {e}")

    def initialize_database(self) -> bool:
        """Initialize database from scratch"""
        try:
            logger.info(f"Initializing database: {self.db_path}")

            # Delete .cache directory if it exists before initialization
            self._cleanup_cache_directory()

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


def _sqlite_path_from_url(database_url: str) -> str:
    """Extract the filesystem path from a ``sqlite://`` URL.

    SQLAlchemy SQLite URLs use three slashes for relative paths and four for
    absolute paths::

        sqlite:///relative.db           →  relative.db
        sqlite:////absolute/path.db     →  /absolute/path.db
        sqlite:///:memory:              →  :memory:
        sqlite+pysqlite:///relative.db  →  relative.db

    Uses SQLAlchemy's ``make_url`` so that dialect+driver variants such as
    ``sqlite+pysqlite://`` are parsed correctly.
    """
    return make_url(database_url).database or ""


def _is_memory_db(sqlite_path: str) -> bool:
    """Return True and log an error if *sqlite_path* is ``:memory:``.

    ``:memory:`` databases do not persist between connections, so the
    ``DatabaseMigrator`` (which opens its own sqlite3 connection) would
    operate on a completely separate, transient in-memory store that the
    SQLAlchemy engine used by the app never sees.  When this function returns
    ``True``, callers should return ``False`` or exit immediately.
    """
    if sqlite_path == ":memory:":
        logger.error(
            "DATABASE_URL is sqlite:///:memory:; in-memory databases do not "
            "persist between connections — migrations/initialization cannot be "
            "applied. Use a file-based SQLite URL or a different database backend."
        )
        return True
    return False


def migrate_database_if_needed(db_path: str = DEFAULT_DB_PATH) -> bool:
    """
    Migrate database only if needed.
    Returns True if database is ready, False if migration failed.

    ``DATABASE_URL`` takes precedence over ``db_path``: when that environment
    variable is set it determines the target database (SQLite file path,
    PostgreSQL DSN, or MariaDB DSN).  ``db_path`` is only used to construct
    the default SQLite URL ``sqlite:///<db_path>`` when ``DATABASE_URL`` is
    absent.
    """
    database_url = config("DATABASE_URL", default=f"sqlite:///{db_path}")
    if not database_url.startswith("sqlite"):
        migrator = SQLAlchemyMigrator(database_url)
    else:
        # Parse the actual path from DATABASE_URL so the migrator and the
        # SQLAlchemy engine always target the same file.
        sqlite_path = _sqlite_path_from_url(database_url)
        if _is_memory_db(sqlite_path):
            return False
        migrator = DatabaseMigrator(sqlite_path)

    if not migrator.needs_migration():
        logger.info("Database is up to date, no migration needed")
        return True

    logger.info("Database migration needed")
    return migrator.run_migrations()


def initialize_database_if_missing(db_path: str = DEFAULT_DB_PATH) -> bool:
    """
    Initialize database only if it doesn't exist or is not properly initialized.
    Returns True if database is ready, False if initialization failed.

    For PostgreSQL and MariaDB the DATABASE_URL environment variable is used;
    db_path is only relevant when DATABASE_URL is absent and the default SQLite
    path is used.
    """
    database_url = config("DATABASE_URL", default=f"sqlite:///{db_path}")
    if not database_url.startswith("sqlite"):
        migrator: Union[DatabaseMigrator, SQLAlchemyMigrator] = SQLAlchemyMigrator(database_url)
    else:
        # Parse the actual path from DATABASE_URL so the migrator and the
        # SQLAlchemy engine always target the same file.
        sqlite_path = _sqlite_path_from_url(database_url)
        if _is_memory_db(sqlite_path):
            return False
        migrator = DatabaseMigrator(sqlite_path)

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


# ---------------------------------------------------------------------------
# SQLAlchemy-based migrator for PostgreSQL and MariaDB/MySQL
# ---------------------------------------------------------------------------

# Migrations expressed as (version, name, [sql, ...]) tuples.
# The SQL is standard enough to work on both PostgreSQL and MySQL/MariaDB.
# Version 1 is intentionally absent: the initial schema is created via
# SQLAlchemy metadata (Base.metadata.create_all) so that column types are
# generated correctly for the target database.
_SQLALCHEMY_MIGRATIONS: List[Dict[str, Any]] = [
    {
        "version": 2,
        "name": "add_emojis_column",
        "sql": ["ALTER TABLE polls ADD COLUMN emojis_json TEXT"],
    },
    {
        "version": 3,
        "name": "add_server_channel_names",
        "sql": [
            "ALTER TABLE polls ADD COLUMN server_name VARCHAR(255)",
            "ALTER TABLE polls ADD COLUMN channel_name VARCHAR(255)",
        ],
    },
    {
        "version": 4,
        "name": "add_timezone_anonymous",
        "sql": [
            "ALTER TABLE polls ADD COLUMN timezone VARCHAR(50) DEFAULT 'UTC'",
            "ALTER TABLE polls ADD COLUMN anonymous BOOLEAN DEFAULT FALSE",
        ],
    },
    {
        "version": 5,
        "name": "add_image_message_text",
        "sql": ["ALTER TABLE polls ADD COLUMN image_message_text TEXT"],
    },
    {
        "version": 6,
        "name": "add_multiple_choice",
        "sql": ["ALTER TABLE polls ADD COLUMN multiple_choice BOOLEAN DEFAULT FALSE"],
    },
    {
        "version": 7,
        "name": "add_role_ping_columns",
        "sql": [
            "ALTER TABLE polls ADD COLUMN ping_role_id VARCHAR(50)",
            "ALTER TABLE polls ADD COLUMN ping_role_name VARCHAR(255)",
            "ALTER TABLE polls ADD COLUMN ping_role_enabled BOOLEAN DEFAULT FALSE",
            "ALTER TABLE user_preferences ADD COLUMN last_role_id VARCHAR(50)",
        ],
    },
    {
        "version": 8,
        "name": "add_timezone_explicitly_set",
        "sql": [
            "ALTER TABLE user_preferences ADD COLUMN timezone_explicitly_set BOOLEAN DEFAULT FALSE"
        ],
    },
    {
        "version": 9,
        "name": "add_open_immediately",
        "sql": ["ALTER TABLE polls ADD COLUMN open_immediately BOOLEAN DEFAULT FALSE"],
    },
    {
        "version": 10,
        "name": "add_role_ping_notification_options",
        "sql": [
            "ALTER TABLE polls ADD COLUMN ping_role_on_close BOOLEAN DEFAULT FALSE",
            "ALTER TABLE polls ADD COLUMN ping_role_on_update BOOLEAN DEFAULT FALSE",
        ],
    },
    {
        "version": 11,
        "name": "add_max_choices",
        "sql": ["ALTER TABLE polls ADD COLUMN max_choices INTEGER"],
    },
]

_LATEST_VERSION = max(m["version"] for m in _SQLALCHEMY_MIGRATIONS)


class SQLAlchemyMigrator:
    """
    Database migrator for PostgreSQL and MariaDB/MySQL.

    Uses SQLAlchemy's ORM metadata for the initial schema creation (so column
    types are dialect-correct) and raw ``text()`` statements for subsequent
    ALTER TABLE migrations.
    """

    def __init__(self, database_url: str):
        self.database_url = database_url

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_engine(self):
        from sqlalchemy import create_engine

        return create_engine(self.database_url, pool_pre_ping=True)

    def _ensure_migrations_table(self, conn) -> None:
        """Create schema_migrations table if it does not yet exist."""
        from sqlalchemy import text

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER NOT NULL,
                name VARCHAR(255) NOT NULL,
                applied_at TIMESTAMP NOT NULL,
                PRIMARY KEY (version)
            )
        """))
        conn.commit()

    def _get_applied_version(self, conn) -> int:
        """Return the highest migration version that has been applied."""
        from sqlalchemy import text

        try:
            result = conn.execute(
                text("SELECT MAX(version) FROM schema_migrations")
            )
            row = result.fetchone()
            return row[0] if row and row[0] is not None else 0
        except Exception:
            return 0

    def _record_migration(self, conn, version: int, name: str) -> None:
        from sqlalchemy import text

        conn.execute(
            text(
                "INSERT INTO schema_migrations (version, name, applied_at) "
                "VALUES (:v, :n, :t)"
            ),
            # Store naive UTC so it is compatible with TIMESTAMP (without time
            # zone) on PostgreSQL and with the rest of the DateTime columns in
            # the schema.
            {"v": version, "n": name, "t": datetime.now(pytz.UTC).replace(tzinfo=None)},
        )
        conn.commit()

    def _get_existing_columns(self, conn, table_name: str) -> List[str]:
        from sqlalchemy import inspect

        insp = inspect(conn)
        try:
            return [c["name"] for c in insp.get_columns(table_name)]
        except Exception:
            return []

    def _table_exists(self, conn, table_name: str) -> bool:
        from sqlalchemy import inspect

        insp = inspect(conn)
        return table_name in insp.get_table_names()

    # ------------------------------------------------------------------
    # Public interface (mirrors DatabaseMigrator)
    # ------------------------------------------------------------------

    def database_exists(self) -> bool:
        """For server-based databases the server is assumed to be reachable."""
        engine = self._make_engine()
        try:
            with engine.connect():
                pass
            return True
        except Exception as exc:
            logger.warning(f"Cannot reach database server: {exc}")
            return False
        finally:
            engine.dispose()

    def is_database_initialized(self) -> bool:
        """Return True if the core tables (polls, votes, users) exist."""
        engine = self._make_engine()
        try:
            with engine.connect() as conn:
                return (
                    self._table_exists(conn, "polls")
                    and self._table_exists(conn, "votes")
                    and self._table_exists(conn, "users")
                )
        except Exception:
            return False
        finally:
            engine.dispose()

    def get_current_schema_version(self) -> int:
        engine = self._make_engine()
        try:
            with engine.connect() as conn:
                if not self._table_exists(conn, "schema_migrations"):
                    # Tables may exist from a manual setup — treat as version 1
                    if self._table_exists(conn, "polls"):
                        return 1
                    return 0
                return self._get_applied_version(conn)
        except Exception as exc:
            logger.error(f"Error getting schema version: {exc}")
            return 0
        finally:
            engine.dispose()

    def needs_migration(self) -> bool:
        if not self.database_exists():
            return True
        return self.get_current_schema_version() < _LATEST_VERSION

    def initialize_database(self) -> bool:
        """Create the full schema using SQLAlchemy metadata, then apply all migrations.

        ``Base.metadata.create_all`` creates any missing tables with the full
        current schema.  Existing tables are not modified by ``create_all``, so
        the same ``ALTER TABLE … ADD COLUMN`` logic used by ``run_migrations``
        is then executed for every migration (with column-existence checks to
        skip already-present columns).  This ensures that even if some tables
        already existed before this call they are brought fully up-to-date.
        """
        try:
            # Lazy import to avoid circular imports
            from polly.database import Base
            from sqlalchemy import text

            engine = self._make_engine()
            try:
                Base.metadata.create_all(engine)
                logger.info("Created all tables via SQLAlchemy metadata")

                with engine.connect() as conn:
                    self._ensure_migrations_table(conn)
                    # Fetch already-applied versions to avoid PRIMARY KEY
                    # conflicts when initialize_database() is called on a
                    # partially-initialized database that already has some
                    # schema_migrations rows.
                    result = conn.execute(
                        text("SELECT version FROM schema_migrations")
                    )
                    applied = {row[0] for row in result}

                    # Stamp version 1 (initial schema created by create_all)
                    if 1 not in applied:
                        self._record_migration(conn, 1, "initial_schema")

                    # Apply ALTER TABLE migrations idempotently.
                    # create_all() creates missing tables with the full current
                    # schema, but leaves existing tables unmodified.  If any
                    # core table already existed before this call it may be
                    # missing columns from later migrations.  Running the same
                    # ADD COLUMN logic as run_migrations() (with column-
                    # existence checks) ensures every table is fully up-to-date
                    # regardless of its prior state.
                    for migration in _SQLALCHEMY_MIGRATIONS:
                        if migration["version"] in applied:
                            continue

                        logger.info(
                            f"Applying migration {migration['version']}: "
                            f"{migration['name']}"
                        )

                        for sql in migration["sql"]:
                            if "ALTER TABLE" in sql and "ADD COLUMN" in sql:
                                parts = sql.split("ADD COLUMN", 1)
                                table_name = parts[0].replace(
                                    "ALTER TABLE", ""
                                ).strip()
                                column_name = parts[1].split()[0].strip()

                                if not self._table_exists(conn, table_name):
                                    logger.error(
                                        f"Table {table_name} does not exist; "
                                        f"cannot apply migration "
                                        f"{migration['version']} "
                                        f"(column {column_name})"
                                    )
                                    return False

                                existing = self._get_existing_columns(
                                    conn, table_name
                                )
                                if column_name in existing:
                                    logger.info(
                                        f"Column {column_name} already exists "
                                        f"in {table_name}, skipping"
                                    )
                                    continue

                            conn.execute(text(sql))

                        conn.commit()
                        self._record_migration(
                            conn, migration["version"], migration["name"]
                        )
                        logger.info(
                            f"Successfully applied migration "
                            f"{migration['version']}"
                        )
            finally:
                engine.dispose()

            logger.info("Database initialized successfully (PostgreSQL/MariaDB)")
            return True
        except Exception as exc:
            logger.error(f"Database initialization failed: {exc}")
            return False

    def run_migrations(self) -> bool:
        """Apply any pending migrations in order."""
        try:
            engine = self._make_engine()

            # Check whether the core schema is fully present in a short-lived
            # connection so the connection is fully released before we hand
            # control to initialize_database() (which creates its own engine +
            # connections).  We check all three required tables — not just
            # 'polls' — so that a partially-initialised database (e.g. polls
            # exists but votes/users are missing) is also redirected to
            # initialize_database(), which uses create_all() and is safe to
            # call on an incomplete schema.
            try:
                with engine.connect() as conn:
                    schema_complete = (
                        self._table_exists(conn, "polls")
                        and self._table_exists(conn, "votes")
                        and self._table_exists(conn, "users")
                    )
            finally:
                engine.dispose()

            if not schema_complete:
                return self.initialize_database()

            engine = self._make_engine()
            try:
                with engine.connect() as conn:
                    self._ensure_migrations_table(conn)
                    current_version = self._get_applied_version(conn)

                    if current_version >= _LATEST_VERSION:
                        logger.info("Database is up to date")
                        return True

                    logger.info(
                        f"Migrating database from version {current_version} "
                        f"to {_LATEST_VERSION}"
                    )

                    from sqlalchemy import text

                    for migration in _SQLALCHEMY_MIGRATIONS:
                        if migration["version"] <= current_version:
                            continue

                        logger.info(
                            f"Applying migration {migration['version']}: {migration['name']}"
                        )

                        sql_statements = migration["sql"]
                        for sql in sql_statements:
                            if "ALTER TABLE" in sql and "ADD COLUMN" in sql:
                                parts = sql.split("ADD COLUMN", 1)
                                table_name = parts[0].replace("ALTER TABLE", "").strip()
                                column_name = parts[1].split()[0].strip()

                                if not self._table_exists(conn, table_name):
                                    logger.error(
                                        f"Table {table_name} does not exist; "
                                        f"cannot apply migration {migration['version']} "
                                        f"(column {column_name})"
                                    )
                                    return False

                                existing = self._get_existing_columns(conn, table_name)
                                if column_name in existing:
                                    logger.info(
                                        f"Column {column_name} already exists in "
                                        f"{table_name}, skipping"
                                    )
                                    continue

                            conn.execute(text(sql))

                        conn.commit()
                        self._record_migration(
                            conn, migration["version"], migration["name"]
                        )
                        logger.info(
                            f"Successfully applied migration {migration['version']}"
                        )
            finally:
                engine.dispose()

            logger.info("All migrations completed successfully")
            return True

        except Exception as exc:
            logger.error(f"Migration failed: {exc}")
            return False


if __name__ == "__main__":
    # Command line usage
    import sys

    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        db_path = DEFAULT_DB_PATH

    print("Polly Database Migration Tool")
    print("-" * 50)

    database_url = config("DATABASE_URL", default=f"sqlite:///{db_path}")
    if not database_url.startswith("sqlite"):
        active_migrator: Union[DatabaseMigrator, SQLAlchemyMigrator] = SQLAlchemyMigrator(database_url)
        display_target = make_url(database_url).render_as_string(hide_password=True)
    else:
        # Parse the actual path from DATABASE_URL (not the CLI arg) so the
        # migrator and the SQLAlchemy engine always target the same file.
        sqlite_path = _sqlite_path_from_url(database_url)
        if _is_memory_db(sqlite_path):
            print("❌ DATABASE_URL is sqlite:///:memory: — cannot run migrations on an in-memory database.")
            sys.exit(1)
        active_migrator = DatabaseMigrator(sqlite_path)
        display_target = sqlite_path

    print(f"Database: {display_target}")

    if active_migrator.needs_migration():
        print("Migration needed")
        success = active_migrator.run_migrations()
        if success:
            print("✅ Migration completed successfully!")
            sys.exit(0)
        else:
            print("❌ Migration failed!")
            sys.exit(1)
    else:
        print("✅ Database is up to date")
        sys.exit(0)
