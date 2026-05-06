"""
Tests for polly/migrations.py helpers.
Covers the _sqlite_path_from_url utility and the SQLAlchemyMigrator
that powers the PostgreSQL / MariaDB migration path.
"""

from unittest.mock import MagicMock, patch
from datetime import datetime

from polly.migrations import (
    _sqlite_path_from_url,
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
# SQLAlchemyMigrator unit tests (no real DB required)
# ---------------------------------------------------------------------------

class TestSQLAlchemyMigratorUnit:
    """Fast unit tests that mock the SQLAlchemy engine."""

    def _make_test_migrator(self):
        return SQLAlchemyMigrator("postgresql://polly:pass@localhost/polly")

    # _record_migration stores naive UTC -----------------------------------

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

    # is_database_initialized checks polls, votes, and users ----------------

    def test_is_database_initialized_all_three_tables(self):
        migrator = self._make_test_migrator()
        mock_conn = MagicMock()
        # All three tables present → initialized
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
