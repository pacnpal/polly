"""
Tests for polly/migrations.py helpers.
Covers the _sqlite_path_from_url utility and the SQLAlchemyMigrator
that powers the PostgreSQL / MariaDB migration path.
"""

from unittest.mock import MagicMock, patch
from datetime import datetime

import sqlite3
import tempfile
import os

from polly.migrations import (
    _sqlite_path_from_url,
    DatabaseMigrator,
    SQLAlchemyMigrator,
    migrate_database_if_needed,
    initialize_database_if_missing,
)


# ---------------------------------------------------------------------------
# _sqlite_path_from_url
# ---------------------------------------------------------------------------

class TestSqlitePathFromUrl:
    """Unit tests for _sqlite_path_from_url()."""

    def test_relative_path(self):
        assert _sqlite_path_from_url("sqlite:///relative.db") == "relative.db"

    def test_relative_path_with_leading_dot(self):
        assert _sqlite_path_from_url("sqlite:///./db/polly.db") == "./db/polly.db"

    def test_absolute_path(self):
        # Four slashes → absolute path, one slash remains after stripping prefix
        assert _sqlite_path_from_url("sqlite:////absolute/path.db") == "/absolute/path.db"

    def test_memory_database(self):
        assert _sqlite_path_from_url("sqlite:///:memory:") == ":memory:"

    def test_default_db_path(self):
        """The default DATABASE_URL matches the expected default db_path."""
        result = _sqlite_path_from_url("sqlite:///./db/polly.db")
        assert result == "./db/polly.db"

    def test_pysqlite_driver_variant(self):
        """sqlite+pysqlite:// dialect+driver form is parsed correctly."""
        assert _sqlite_path_from_url("sqlite+pysqlite:///relative.db") == "relative.db"

    def test_pysqlite_absolute_path(self):
        """sqlite+pysqlite:// dialect+driver form parses absolute paths correctly."""
        assert _sqlite_path_from_url("sqlite+pysqlite:////absolute/path.db") == "/absolute/path.db"


# ---------------------------------------------------------------------------
# :memory: fast-fail tests
# ---------------------------------------------------------------------------

class TestMemoryDatabaseRejection:
    """sqlite:///:memory: must be rejected before touching DatabaseMigrator."""

    @staticmethod
    def _mock_config_with_memory_db(key, default=""):
        """Side-effect for patching decouple.config to return :memory: for DATABASE_URL."""
        if key == "DATABASE_URL":
            return "sqlite:///:memory:"
        return default

    def test_migrate_database_if_needed_rejects_memory(self):
        with patch("polly.migrations.config", side_effect=self._mock_config_with_memory_db):
            result = migrate_database_if_needed()
        assert result is False

    def test_initialize_database_if_missing_rejects_memory(self):
        with patch("polly.migrations.config", side_effect=self._mock_config_with_memory_db):
            result = initialize_database_if_missing()
        assert result is False


# ---------------------------------------------------------------------------
# DatabaseMigrator.is_database_initialized (SQLite path)
# ---------------------------------------------------------------------------

class TestDatabaseMigratorIsInitialized:
    """DatabaseMigrator.is_database_initialized() must require all four core
    tables including user_preferences."""

    def _make_db_with_tables(self, tables):
        """Create a temporary SQLite DB with the given tables and return its path."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        conn = sqlite3.connect(path)
        for table in tables:
            conn.execute(f"CREATE TABLE IF NOT EXISTS {table} (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()
        return path

    def test_all_four_tables_present(self):
        path = self._make_db_with_tables(["polls", "votes", "users", "user_preferences"])
        try:
            assert DatabaseMigrator(path).is_database_initialized() is True
        finally:
            os.unlink(path)

    def test_missing_user_preferences_returns_false(self):
        path = self._make_db_with_tables(["polls", "votes", "users"])
        try:
            assert DatabaseMigrator(path).is_database_initialized() is False
        finally:
            os.unlink(path)

    def test_missing_users_returns_false(self):
        path = self._make_db_with_tables(["polls", "votes", "user_preferences"])
        try:
            assert DatabaseMigrator(path).is_database_initialized() is False
        finally:
            os.unlink(path)

    def test_empty_db_returns_false(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            assert DatabaseMigrator(path).is_database_initialized() is False
        finally:
            os.unlink(path)



class TestSQLAlchemyMigratorUnit:
    """Fast unit tests that mock the SQLAlchemy engine."""

    def _make_test_migrator(self):
        return SQLAlchemyMigrator("postgresql://polly:pass@localhost/polly")

    # _record_migration stores naive UTC and does not commit ----------------

    def test_record_migration_stores_naive_utc(self):
        """_record_migration must not pass a tz-aware datetime to the DB."""
        migrator = self._make_test_migrator()
        mock_conn = MagicMock()
        migrator._record_migration(mock_conn, 1, "initial_schema")

        # Extract the 't' parameter passed to conn.execute
        call_args = mock_conn.execute.call_args
        bound_params = call_args[0][1]  # second positional arg is the params dict
        ts = bound_params["t"]

        assert isinstance(ts, datetime)
        assert ts.tzinfo is None, "timestamp must be naive (no tzinfo) to match TIMESTAMP column"

    def test_record_migration_does_not_commit(self):
        """_record_migration must not call conn.commit(); the caller owns the transaction."""
        migrator = self._make_test_migrator()
        mock_conn = MagicMock()
        migrator._record_migration(mock_conn, 2, "some_migration")
        mock_conn.commit.assert_not_called()

    # is_database_initialized checks polls, votes, users, and user_preferences

    def test_is_database_initialized_all_four_tables(self):
        migrator = self._make_test_migrator()
        mock_conn = MagicMock()
        # All four tables present → initialized
        migrator._table_exists = MagicMock(return_value=True)
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        with patch.object(migrator, "_make_engine", return_value=mock_engine):
            result = migrator.is_database_initialized()
        assert result is True

    def test_is_database_initialized_missing_users(self):
        migrator = self._make_test_migrator()
        # polls and votes present, users absent
        def table_exists_side_effect(conn, table_name):
            return table_name != "users"

        mock_conn = MagicMock()
        migrator._table_exists = MagicMock(side_effect=table_exists_side_effect)
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        with patch.object(migrator, "_make_engine", return_value=mock_engine):
            result = migrator.is_database_initialized()
        assert result is False

    def test_is_database_initialized_missing_user_preferences(self):
        migrator = self._make_test_migrator()
        # polls/votes/users present, user_preferences absent
        def table_exists_side_effect(conn, table_name):
            return table_name != "user_preferences"

        mock_conn = MagicMock()
        migrator._table_exists = MagicMock(side_effect=table_exists_side_effect)
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        with patch.object(migrator, "_make_engine", return_value=mock_engine):
            result = migrator.is_database_initialized()
        assert result is False

    # run_migrations() redirects to initialize_database on partial schema ---

    def test_run_migrations_partial_schema_calls_initialize(self):
        """If any core table is missing, run_migrations() must delegate to
        initialize_database() rather than attempting incremental ALTER TABLE."""
        migrator = self._make_test_migrator()

        # polls exists but users is missing → partial schema
        def table_exists_side_effect(conn, table_name):
            return table_name == "polls"

        mock_conn = MagicMock()
        migrator._table_exists = MagicMock(side_effect=table_exists_side_effect)
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        with patch.object(migrator, "_make_engine", return_value=mock_engine):
            with patch.object(migrator, "initialize_database", return_value=True) as mock_init:
                result = migrator.run_migrations()

        mock_init.assert_called_once()
        assert result is True

    def test_run_migrations_missing_user_preferences_calls_initialize(self):
        """If user_preferences is missing while polls/votes/users exist,
        run_migrations() must delegate to initialize_database()."""
        migrator = self._make_test_migrator()

        # polls/votes/users exist but user_preferences is missing
        def table_exists_side_effect(conn, table_name):
            return table_name != "user_preferences"

        mock_conn = MagicMock()
        migrator._table_exists = MagicMock(side_effect=table_exists_side_effect)
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        with patch.object(migrator, "_make_engine", return_value=mock_engine):
            with patch.object(migrator, "initialize_database", return_value=True) as mock_init:
                result = migrator.run_migrations()

        mock_init.assert_called_once()
        assert result is True


# ---------------------------------------------------------------------------
# Exception-logging helpers
# ---------------------------------------------------------------------------

class TestSQLAlchemyMigratorExceptionLogging:
    """Verify that _get_applied_version and _get_existing_columns log
    exceptions rather than silently swallowing them."""

    def _make_test_migrator(self):
        return SQLAlchemyMigrator("postgresql://polly:pass@localhost/polly")

    def test_get_applied_version_logs_on_exception(self):
        """_get_applied_version must log a warning when the query fails."""
        migrator = self._make_test_migrator()
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = Exception("table does not exist")

        with patch("polly.migrations.logger") as mock_logger:
            result = migrator._get_applied_version(mock_conn)

        assert result == 0
        mock_logger.warning.assert_called_once()
        warning_msg = mock_logger.warning.call_args[0][0]
        assert "schema_migrations" in warning_msg

    def test_get_existing_columns_logs_on_exception(self):
        """_get_existing_columns must log a warning when introspection fails."""
        migrator = self._make_test_migrator()
        mock_conn = MagicMock()

        mock_inspector = MagicMock()
        mock_inspector.get_columns.side_effect = Exception("permission denied")

        with patch("polly.migrations.logger") as mock_logger:
            with patch("sqlalchemy.inspect", return_value=mock_inspector):
                result = migrator._get_existing_columns(mock_conn, "polls")

        assert result == []
        mock_logger.warning.assert_called_once()
        warning_msg = mock_logger.warning.call_args[0][0]
        assert "polls" in warning_msg


# ---------------------------------------------------------------------------
# Shared helper for tests that need a non-SQLite DATABASE_URL
# ---------------------------------------------------------------------------

def _mock_config_postgres(key, default=""):
    """Side-effect for patching decouple.config to return a PostgreSQL URL."""
    if key == "DATABASE_URL":
        return "postgresql://polly:pass@localhost/polly"
    return default


# ---------------------------------------------------------------------------
# migrate_database_if_needed: schema-current-but-not-initialized guard
# ---------------------------------------------------------------------------

class TestMigrateDatabaseIfNeededInitCheck:
    """migrate_database_if_needed() must reinitialize when the schema version
    is current but core tables are absent."""

    def test_reinitializes_when_schema_current_but_not_initialized(self):
        """When needs_migration() is False but is_database_initialized() is False,
        migrate_database_if_needed() must call initialize_database()."""
        mock_migrator = MagicMock()
        mock_migrator.needs_migration.return_value = False
        mock_migrator.is_database_initialized.return_value = False
        mock_migrator.initialize_database.return_value = True

        with patch("polly.migrations.config", side_effect=_mock_config_postgres):
            with patch("polly.migrations.SQLAlchemyMigrator", return_value=mock_migrator):
                result = migrate_database_if_needed()

        mock_migrator.initialize_database.assert_called_once()
        assert result is True

    def test_no_reinit_when_schema_current_and_initialized(self):
        """When needs_migration() is False and is_database_initialized() is True,
        migrate_database_if_needed() must return True without calling initialize_database()."""
        mock_migrator = MagicMock()
        mock_migrator.needs_migration.return_value = False
        mock_migrator.is_database_initialized.return_value = True

        with patch("polly.migrations.config", side_effect=_mock_config_postgres):
            with patch("polly.migrations.SQLAlchemyMigrator", return_value=mock_migrator):
                result = migrate_database_if_needed()

        mock_migrator.initialize_database.assert_not_called()
        assert result is True


# ---------------------------------------------------------------------------
# initialize_database_if_missing: fallthrough guard
# ---------------------------------------------------------------------------

class TestInitializeDatabaseIfMissingFallthrough:
    """initialize_database_if_missing() must reinitialize when the DB exists,
    no version-based migrations are pending, but core tables are absent."""

    def test_reinitializes_when_db_exists_but_not_initialized(self):
        """When DB exists, needs_migration()=False, is_database_initialized()=False,
        initialize_database_if_missing() must call initialize_database()."""
        mock_migrator = MagicMock()
        mock_migrator.is_database_initialized.return_value = False
        mock_migrator.needs_migration.return_value = False
        mock_migrator.database_exists.return_value = True
        mock_migrator.initialize_database.return_value = True

        with patch("polly.migrations.config", side_effect=_mock_config_postgres):
            with patch("polly.migrations.SQLAlchemyMigrator", return_value=mock_migrator):
                result = initialize_database_if_missing()

        mock_migrator.initialize_database.assert_called_once()
        assert result is True

    def test_no_reinit_when_db_initialized_and_current(self):
        """When DB is fully initialized and up-to-date, initialize_database()
        must not be called."""
        mock_migrator = MagicMock()
        mock_migrator.is_database_initialized.return_value = True
        mock_migrator.needs_migration.return_value = False

        with patch("polly.migrations.config", side_effect=_mock_config_postgres):
            with patch("polly.migrations.SQLAlchemyMigrator", return_value=mock_migrator):
                result = initialize_database_if_missing()

        mock_migrator.initialize_database.assert_not_called()
        assert result is True
