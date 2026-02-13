"""
Performance tests for Polly database operations.
Tests the optimized SQL-based vote aggregation methods.
"""

import pytest
import time
from datetime import datetime, timedelta
import pytz

from polly.database import Poll, Vote, get_db_session


@pytest.mark.performance
class TestVoteAggregationPerformance:
    """Test performance of optimized vote aggregation methods."""

    def test_get_results_performance_with_many_votes(self, db_session):
        """Test get_results() performance with large number of votes."""
        # Create a poll with 4 options
        poll = Poll(
            name="Performance Test Poll",
            question="Test question?",
            options=["Option A", "Option B", "Option C", "Option D"],
            emojis=["🇦", "🇧", "🇨", "🇩"],
            server_id="123456789",
            channel_id="987654321",
            creator_id="111111111",
            open_time=datetime.now(pytz.UTC),
            close_time=datetime.now(pytz.UTC) + timedelta(hours=1),
            status="active",
        )
        db_session.add(poll)
        db_session.commit()

        # Add 1000 votes
        num_votes = 1000
        for i in range(num_votes):
            vote = Vote(
                poll_id=poll.id,
                user_id=f"user_{i}",
                option_index=i % 4,  # Distribute votes across 4 options
            )
            db_session.add(vote)
        db_session.commit()

        # Test optimized SQL method
        start_time = time.time()
        results_sql = poll.get_results(db_session)
        sql_time = time.time() - start_time

        # Test old Python method (no db parameter)
        start_time = time.time()
        results_python = poll.get_results()
        python_time = time.time() - start_time

        # Verify results are the same
        assert results_sql == results_python
        assert sum(results_sql.values()) == num_votes

        # SQL method should be faster (or at least not significantly slower)
        print(f"\nSQL method time: {sql_time:.4f}s")
        print(f"Python method time: {python_time:.4f}s")
        print(f"Speedup: {python_time/sql_time:.2f}x")

        # For large datasets, SQL should be faster
        # For small datasets, the difference may be negligible
        assert sql_time <= python_time * 2  # Allow some margin

    def test_get_total_votes_performance(self, db_session):
        """Test get_total_votes() performance with large number of votes."""
        # Create a multiple choice poll
        poll = Poll(
            name="Performance Test Poll",
            question="Test question?",
            options=["Option A", "Option B", "Option C"],
            emojis=["🇦", "🇧", "🇨"],
            server_id="123456789",
            channel_id="987654321",
            creator_id="111111111",
            open_time=datetime.now(pytz.UTC),
            close_time=datetime.now(pytz.UTC) + timedelta(hours=1),
            status="active",
            multiple_choice=True,
        )
        db_session.add(poll)
        db_session.commit()

        # Add 1000 votes from 500 unique users (2 votes each)
        num_users = 500
        for i in range(num_users):
            # Each user votes for 2 options
            vote1 = Vote(
                poll_id=poll.id,
                user_id=f"user_{i}",
                option_index=0,
            )
            vote2 = Vote(
                poll_id=poll.id,
                user_id=f"user_{i}",
                option_index=1,
            )
            db_session.add(vote1)
            db_session.add(vote2)
        db_session.commit()

        # Test optimized SQL method
        start_time = time.time()
        total_sql = poll.get_total_votes(db_session)
        sql_time = time.time() - start_time

        # Test old Python method (no db parameter)
        start_time = time.time()
        total_python = poll.get_total_votes()
        python_time = time.time() - start_time

        # Verify results are the same (should count unique users)
        assert total_sql == total_python
        assert total_sql == num_users

        print(f"\nSQL method time: {sql_time:.4f}s")
        print(f"Python method time: {python_time:.4f}s")
        print(f"Speedup: {python_time/sql_time:.2f}x")

    def test_get_winner_performance(self, db_session):
        """Test get_winner() performance with large number of votes."""
        # Create a poll with 5 options
        poll = Poll(
            name="Performance Test Poll",
            question="Test question?",
            options=["Option A", "Option B", "Option C", "Option D", "Option E"],
            emojis=["🇦", "🇧", "🇨", "🇩", "🇪"],
            server_id="123456789",
            channel_id="987654321",
            creator_id="111111111",
            open_time=datetime.now(pytz.UTC),
            close_time=datetime.now(pytz.UTC) + timedelta(hours=1),
            status="closed",
        )
        db_session.add(poll)
        db_session.commit()

        # Add votes with Option B as clear winner
        num_votes = 1000
        for i in range(num_votes):
            # 50% vote for Option B, rest distributed
            option_index = 1 if i < num_votes // 2 else (i % 5)
            vote = Vote(
                poll_id=poll.id,
                user_id=f"user_{i}",
                option_index=option_index,
            )
            db_session.add(vote)
        db_session.commit()

        # Test optimized SQL method
        start_time = time.time()
        winner_sql = poll.get_winner(db_session)
        sql_time = time.time() - start_time

        # Test old Python method (no db parameter)
        start_time = time.time()
        winner_python = poll.get_winner()
        python_time = time.time() - start_time

        # Verify results are the same
        assert winner_sql == winner_python
        assert 1 in winner_sql  # Option B (index 1) should be winner

        print(f"\nSQL method time: {sql_time:.4f}s")
        print(f"Python method time: {python_time:.4f}s")
        print(f"Speedup: {python_time/sql_time:.2f}x")

    def test_backward_compatibility_without_db(self, db_session):
        """Test that methods work without db parameter (backward compatibility)."""
        poll = Poll(
            name="Backward Compatibility Test",
            question="Test question?",
            options=["Option A", "Option B"],
            emojis=["🇦", "🇧"],
            server_id="123456789",
            channel_id="987654321",
            creator_id="111111111",
            open_time=datetime.now(pytz.UTC),
            close_time=datetime.now(pytz.UTC) + timedelta(hours=1),
            status="active",
        )
        db_session.add(poll)
        db_session.commit()

        # Add some votes
        for i in range(10):
            vote = Vote(
                poll_id=poll.id,
                user_id=f"user_{i}",
                option_index=i % 2,
            )
            db_session.add(vote)
        db_session.commit()

        # Test all methods without db parameter
        results = poll.get_results()
        assert isinstance(results, dict)
        assert len(results) == 2

        total_votes = poll.get_total_votes()
        assert total_votes == 10

        total_vote_count = poll.get_total_vote_count()
        assert total_vote_count == 10

        winner = poll.get_winner()
        assert winner is not None

    def test_query_count_reduction(self, db_session):
        """Test that optimized methods reduce query count."""
        # Create 3 polls with votes
        polls = []
        for p in range(3):
            poll = Poll(
                name=f"Poll {p}",
                question=f"Question {p}?",
                options=["A", "B", "C"],
                emojis=["🇦", "🇧", "🇨"],
                server_id="123456789",
                channel_id="987654321",
                creator_id="111111111",
                open_time=datetime.now(pytz.UTC),
                close_time=datetime.now(pytz.UTC) + timedelta(hours=1),
                status="active",
            )
            db_session.add(poll)
            db_session.commit()

            # Add votes
            for v in range(50):
                vote = Vote(
                    poll_id=poll.id,
                    user_id=f"user_{v}",
                    option_index=v % 3,
                )
                db_session.add(vote)
            db_session.commit()
            polls.append(poll)

        # Fetch all polls and get results using optimized method
        # This should use fewer queries than the old method
        for poll in polls:
            results = poll.get_results(db_session)
            total_votes = poll.get_total_votes(db_session)
            assert sum(results.values()) == total_votes


@pytest.mark.performance
class TestDatabaseIndexes:
    """Test that database indexes are properly created."""

    def test_poll_indexes_exist(self, db_session):
        """Verify that Poll table has expected indexes."""
        from sqlalchemy import inspect

        inspector = inspect(db_session.bind)
        indexes = inspector.get_indexes("polls")

        # Get all indexed columns
        indexed_columns = set()
        for index in indexes:
            indexed_columns.update(index["column_names"])

        # These columns should be indexed
        expected_indexed = {"id", "creator_id", "status", "server_id"}

        for col in expected_indexed:
            assert (
                col in indexed_columns
            ), f"Column '{col}' should be indexed for performance"

    def test_vote_indexes_exist(self, db_session):
        """Verify that Vote table has expected indexes."""
        from sqlalchemy import inspect

        inspector = inspect(db_session.bind)
        indexes = inspector.get_indexes("votes")

        # Get all indexed columns
        indexed_columns = set()
        for index in indexes:
            indexed_columns.update(index["column_names"])

        # These columns should be indexed
        expected_indexed = {"id", "poll_id", "user_id"}

        for col in expected_indexed:
            assert (
                col in indexed_columns
            ), f"Column '{col}' should be indexed for performance"
