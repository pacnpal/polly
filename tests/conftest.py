"""
Pytest configuration and fixtures for Polly tests.
"""

import pytest
import asyncio
import tempfile
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, MagicMock
import pytz
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import discord
from fastapi.testclient import TestClient

# Import Polly modules
from polly.database import Base, Poll, Vote, User, UserPreference, Guild, Channel, get_db_session
from polly.web_app import create_app
from polly.auth import DiscordUser


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name
    
    # Create engine and tables
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    
    # Create session factory
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    yield TestSessionLocal, db_path
    
    # Cleanup
    os.unlink(db_path)


@pytest.fixture
def db_session(temp_db):
    """Create a database session for testing."""
    TestSessionLocal, _ = temp_db
    session = TestSessionLocal()
    yield session
    session.close()


@pytest.fixture
def mock_bot():
    """Create a mock Discord bot instance."""
    bot = Mock()
    bot.user = Mock()
    bot.user.id = "123456789"
    bot.user.name = "TestBot"
    bot.get_guild = Mock()
    bot.get_channel = Mock()
    bot.get_user = Mock()
    bot.fetch_user = AsyncMock()
    bot.is_closed = Mock(return_value=False)
    return bot


@pytest.fixture
def mock_discord_guild():
    """Create a mock Discord guild."""
    guild = Mock()
    guild.id = 987654321
    guild.name = "Test Server"
    guild.icon = "test_icon_hash"
    guild.owner_id = "111111111"
    guild.channels = []
    guild.roles = []
    guild.emojis = []
    return guild


@pytest.fixture
def mock_discord_channel():
    """Create a mock Discord channel."""
    channel = Mock()
    channel.id = 555555555
    channel.name = "test-channel"
    channel.type = discord.ChannelType.text
    channel.guild = Mock()
    channel.guild.id = 987654321
    channel.send = AsyncMock()
    channel.fetch_message = AsyncMock()
    return channel


@pytest.fixture
def mock_discord_user():
    """Create a mock Discord user."""
    user = Mock()
    user.id = "222222222"
    user.name = "TestUser"
    user.display_name = "Test User"
    user.avatar = Mock()
    user.avatar.url = "https://example.com/avatar.png"
    user.bot = False
    user.guild_permissions = Mock()
    user.guild_permissions.administrator = True
    user.guild_permissions.manage_guild = True
    user.guild_permissions.manage_channels = True
    return user


@pytest.fixture
def mock_discord_message():
    """Create a mock Discord message."""
    message = Mock()
    message.id = 777777777
    message.content = "Test message"
    message.author = Mock()
    message.channel = Mock()
    message.guild = Mock()
    message.add_reaction = AsyncMock()
    message.remove_reaction = AsyncMock()
    message.edit = AsyncMock()
    message.delete = AsyncMock()
    return message


@pytest.fixture
def mock_discord_reaction():
    """Create a mock Discord reaction."""
    reaction = Mock()
    reaction.emoji = "🇦"
    reaction.count = 1
    reaction.message = Mock()
    reaction.remove = AsyncMock()
    return reaction


@pytest.fixture
def sample_poll_data():
    """Sample poll data for testing."""
    return {
        "name": "Test Poll",
        "question": "What is your favorite color?",
        "options": ["Red", "Blue", "Green", "Yellow"],
        "emojis": ["🔴", "🔵", "🟢", "🟡"],
        "server_id": "987654321",
        "channel_id": "555555555",
        "creator_id": "222222222",
        "open_time": datetime.now(pytz.UTC) + timedelta(hours=1),
        "close_time": datetime.now(pytz.UTC) + timedelta(hours=25),
        "timezone": "UTC",
        "anonymous": False,
        "multiple_choice": False,
        "image_path": None,
        "image_message_text": "",
        "ping_role_enabled": False,
        "ping_role_id": None,
        "ping_role_name": None
    }


@pytest.fixture
def sample_poll(db_session, sample_poll_data):
    """Create a sample poll in the database."""
    poll = Poll(
        name=sample_poll_data["name"],
        question=sample_poll_data["question"],
        options=sample_poll_data["options"],
        emojis=sample_poll_data["emojis"],
        server_id=sample_poll_data["server_id"],
        server_name="Test Server",
        channel_id=sample_poll_data["channel_id"],
        channel_name="test-channel",
        creator_id=sample_poll_data["creator_id"],
        open_time=sample_poll_data["open_time"],
        close_time=sample_poll_data["close_time"],
        timezone=sample_poll_data["timezone"],
        anonymous=sample_poll_data["anonymous"],
        multiple_choice=sample_poll_data["multiple_choice"],
        status="scheduled"
    )
    db_session.add(poll)
    db_session.commit()
    db_session.refresh(poll)
    return poll


@pytest.fixture
def sample_user(db_session):
    """Create a sample user in the database."""
    user = User(
        id="222222222",
        username="TestUser",
        avatar="test_avatar_hash"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def sample_discord_user():
    """Create a sample DiscordUser for authentication."""
    return DiscordUser(
        id="222222222",
        username="TestUser",
        avatar="test_avatar_hash"
    )


@pytest.fixture
def sample_vote(db_session, sample_poll, sample_user):
    """Create a sample vote in the database."""
    vote = Vote(
        poll_id=sample_poll.id,
        user_id=sample_user.id,
        option_index=0
    )
    db_session.add(vote)
    db_session.commit()
    db_session.refresh(vote)
    return vote


@pytest.fixture
def web_client():
    """Create a FastAPI test client."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def mock_scheduler():
    """Create a mock APScheduler instance."""
    scheduler = Mock()
    scheduler.add_job = Mock()
    scheduler.remove_job = Mock()
    scheduler.get_job = Mock()
    scheduler.modify_job = Mock()
    scheduler.start = Mock()
    scheduler.shutdown = Mock()
    return scheduler


@pytest.fixture
def mock_emoji_handler():
    """Create a mock emoji handler."""
    handler = Mock()
    handler.process_poll_emojis = AsyncMock(return_value=["🇦", "🇧", "🇨", "🇩"])
    handler.prepare_emoji_for_reaction = Mock(side_effect=lambda x: x)
    handler.is_unicode_emoji = Mock(return_value=True)
    handler.is_custom_discord_emoji = Mock(return_value=False)
    return handler


@pytest.fixture
def mock_file_upload():
    """Create a mock file upload."""
    file = Mock()
    file.filename = "test_image.png"
    file.content_type = "image/png"
    file.size = 1024 * 1024  # 1MB
    file.read = AsyncMock(return_value=b"fake_image_data")
    return file


@pytest.fixture
def edge_case_strings():
    """Collection of edge case strings for testing."""
    return {
        "empty": "",
        "whitespace": "   \t\n  ",
        "very_long": "x" * 10000,
        "unicode": "🎉🌟✨💫🔥💯🚀⭐🎊🎈",
        "mixed_unicode": "Hello 🌍 World! 🎉",
        "sql_injection": "'; DROP TABLE polls; --",
        "xss": "<script>alert('xss')</script>",
        "html_entities": "&lt;script&gt;alert('test')&lt;/script&gt;",
        "null_bytes": "test\x00null",
        "control_chars": "test\x01\x02\x03control",
        "rtl_override": "test\u202eoverride",
        "zero_width": "test\u200bzero\u200cwidth\u200djoiner",
        "combining_chars": "e\u0301\u0302\u0303\u0304",
        "surrogate_pairs": "𝕳𝖊𝖑𝖑𝖔 𝖂𝖔𝖗𝖑𝖉",
        "emoji_sequences": "👨‍👩‍👧‍👦👩‍💻🏳️‍🌈",
        "newlines": "line1\nline2\r\nline3\rline4",
        "tabs": "col1\tcol2\tcol3",
        "quotes": "single'quote\"double'mixed",
        "backslashes": "path\\to\\file\\with\\backslashes",
        "unicode_normalization": "café vs café",  # Different Unicode representations
        "bidi_text": "English العربية English",
        "mathematical": "∑∫∂∆∇∞±≤≥≠≈∝∈∉∪∩⊂⊃",
        "currency": "$€£¥₹₽₿¢",
        "special_spaces": "normal\u00A0non-breaking\u2000en-quad\u2003em-space"
    }


@pytest.fixture
def malicious_inputs():
    """Collection of malicious inputs for security testing."""
    return {
        "path_traversal": "../../../etc/passwd",
        "command_injection": "; rm -rf /",
        "format_string": "%s%s%s%s%s%s%s%s%s%s",
        "buffer_overflow": "A" * 100000,
        "unicode_overflow": "🎉" * 10000,
        "json_injection": '{"test": "value", "admin": true}',
        "ldap_injection": "admin)(|(password=*))",
        "xpath_injection": "' or '1'='1",
        "nosql_injection": '{"$ne": null}',
        "template_injection": "{{7*7}}",
        "ssti": "${7*7}",
        "prototype_pollution": "__proto__.admin",
        "deserialization": "rO0ABXNyABNqYXZhLnV0aWwuQXJyYXlMaXN0",
        "xxe": '<?xml version="1.0"?><!DOCTYPE root [<!ENTITY test SYSTEM "file:///etc/passwd">]><root>&test;</root>',
        "polyglot": "javascript:/*--></title></style></textarea></script></xmp><svg/onload='+/\"/+/onmouseover=1/+/[*/[]/+alert(1)//'>",
    }


@pytest.fixture
def timezone_test_cases():
    """Collection of timezone test cases."""
    return [
        "UTC",
        "US/Eastern",
        "US/Central", 
        "US/Mountain",
        "US/Pacific",
        "Europe/London",
        "Europe/Paris",
        "Asia/Tokyo",
        "Australia/Sydney",
        "America/New_York",
        "America/Los_Angeles",
        "Pacific/Honolulu",
        "GMT",
        "EST",
        "PST",
        "Invalid/Timezone",
        "",
        None,
        "UTC+5",
        "GMT-8"
    ]


@pytest.fixture
def datetime_edge_cases():
    """Collection of datetime edge cases."""
    now = datetime.now(pytz.UTC)
    return {
        "past": now - timedelta(days=1),
        "very_past": now - timedelta(days=365),
        "near_future": now + timedelta(minutes=1),
        "far_future": now + timedelta(days=365),
        "very_far_future": now + timedelta(days=10000),
        "leap_year": datetime(2024, 2, 29, tzinfo=pytz.UTC),
        "year_2038": datetime(2038, 1, 19, 3, 14, 7, tzinfo=pytz.UTC),
        "year_1970": datetime(1970, 1, 1, tzinfo=pytz.UTC),
        "dst_transition": datetime(2024, 3, 10, 2, 30, tzinfo=pytz.timezone('US/Eastern')),
        "new_year": datetime(2024, 1, 1, tzinfo=pytz.UTC),
        "christmas": datetime(2024, 12, 25, tzinfo=pytz.UTC),
        "midnight": now.replace(hour=0, minute=0, second=0, microsecond=0),
        "noon": now.replace(hour=12, minute=0, second=0, microsecond=0),
        "end_of_day": now.replace(hour=23, minute=59, second=59, microsecond=999999)
    }


@pytest.fixture
def emoji_test_cases():
    """Collection of emoji test cases including edge cases."""
    return {
        "basic_unicode": ["😀", "😃", "😄", "😁"],
        "unicode_with_variation": ["🐈️", "🖤️", "🤍️", "🤎️"],
        "custom_discord": ["<:custom:123456789>", "<a:animated:987654321>"],
        "mixed": ["😀", "<:custom:123456789>", "🎉", "<a:party:555555555>"],
        "invalid_custom": ["<:invalid>", "<:missing:>", "<::123>"],
        "complex_unicode": ["👨‍👩‍👧‍👦", "🏳️‍🌈", "👩‍💻", "🧑‍🚀"],
        "skin_tones": ["👋🏻", "👋🏼", "👋🏽", "👋🏾", "👋🏿"],
        "flags": ["🇺🇸", "🇬🇧", "🇫🇷", "🇩🇪", "🇯🇵"],
        "numbers": ["0️⃣", "1️⃣", "2️⃣", "3️⃣", "4️⃣"],
        "symbols": ["⚠️", "✅", "❌", "🔥", "💯"],
        "empty": ["", " ", "\t"],
        "non_emoji": ["a", "1", "@", "#"],
        "too_many": ["😀"] * 20,
        "duplicate": ["😀", "😀", "😃", "😃"],
        "malformed": ["😀😃", "🎉🔥", "mixed😀text"]
    }


# Monkey patch the database session for testing
@pytest.fixture(autouse=True)
def patch_db_session(monkeypatch, temp_db):
    """Automatically patch database sessions for all tests."""
    TestSessionLocal, _ = temp_db
    
    def mock_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()
    
    def mock_get_db_session():
        return TestSessionLocal()
    
    monkeypatch.setattr("polly.database.get_db", mock_get_db)
    monkeypatch.setattr("polly.database.get_db_session", mock_get_db_session)
    monkeypatch.setattr("polly.database.SessionLocal", TestSessionLocal)


# Confidence level: 10/10 - Comprehensive fixtures covering all testing scenarios
