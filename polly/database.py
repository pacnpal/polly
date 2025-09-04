"""
Polly Database Models
SQLite database with SQLAlchemy ORM for polls, votes, and users.
"""

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    Boolean,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.sql import func
from typing import List, Optional
from decouple import config
import json


class TypeSafeColumn:
    """Type-safe column access for SQLAlchemy models"""

    @staticmethod
    def get_string(obj, column_name: str, default: str = "") -> str:
        """Safely get string value from SQLAlchemy column"""
        try:
            value = getattr(obj, column_name, default)
            return str(value) if value is not None else default
        except (AttributeError, TypeError):
            return default

    @staticmethod
    def get_int(obj, column_name: str, default: int = 0) -> int:
        """Safely get integer value from SQLAlchemy column"""
        try:
            value = getattr(obj, column_name, default)
            return int(value) if value is not None else default
        except (AttributeError, TypeError, ValueError):
            return default

    @staticmethod
    def get_bool(obj, column_name: str, default: bool = False) -> bool:
        """Safely get boolean value from SQLAlchemy column"""
        try:
            value = getattr(obj, column_name, default)
            if value is None:
                return default
            # Handle SQLAlchemy boolean columns that might return 0/1
            if isinstance(value, (int, str)):
                return bool(int(value))
            return bool(value)
        except (AttributeError, TypeError, ValueError):
            return default

    @staticmethod
    def get_datetime(obj, column_name: str, default: Optional[object] = None):
        """Safely get datetime value from SQLAlchemy column"""
        try:
            value = getattr(obj, column_name, default)
            return value if value is not None else default
        except AttributeError:
            return default


# Database setup
DATABASE_URL = config("DATABASE_URL", default="sqlite:///./db/polly.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Poll(Base):
    """Poll model with name, question, options, and scheduling"""

    __tablename__ = "polls"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    question = Column(Text, nullable=False)
    options_json = Column(Text, nullable=False)  # JSON array of poll options
    emojis_json = Column(Text, nullable=True)  # JSON array of poll emojis
    image_path = Column(String(500), nullable=True)  # Path to uploaded image
    # Optional text for image message
    image_message_text = Column(Text, nullable=True)
    server_id = Column(String(50), nullable=False)  # Discord server ID
    server_name = Column(String(255), nullable=True)  # Discord server name
    channel_id = Column(String(50), nullable=False)  # Discord channel ID
    channel_name = Column(String(255), nullable=True)  # Discord channel name
    creator_id = Column(String(50), nullable=False)  # Discord user ID
    # Discord message ID when posted
    message_id = Column(String(50), nullable=True)
    # Role to ping when poll opens/closes
    ping_role_id = Column(String(50), nullable=True)
    # Role name for display
    ping_role_name = Column(String(255), nullable=True)
    # Whether to ping role when poll opens and closes
    ping_role_enabled = Column(Boolean, default=False)
    open_time = Column(DateTime, nullable=False)  # When poll opens
    close_time = Column(DateTime, nullable=False)  # When poll closes
    timezone = Column(String(50), default="UTC")  # Timezone for scheduling
    anonymous = Column(Boolean, default=False)  # Hide results until poll ends
    # Allow multiple selections
    multiple_choice = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    status = Column(String(20), default="scheduled")  # scheduled/active/closed

    # Relationship to votes
    votes = relationship("Vote", back_populates="poll", cascade="all, delete-orphan")

    @property
    def options(self) -> List[str]:
        """Get poll options as Python list"""
        options_str = getattr(self, "options_json", None)
        if options_str:
            return json.loads(options_str)
        return []

    @options.setter
    def options(self, value: List[str]) -> None:
        """Set poll options from Python list"""
        self.options_json = json.dumps(value)

    @property
    def emojis(self) -> List[str]:
        """Get poll emojis as Python list"""
        emojis_str = getattr(self, "emojis_json", None)
        if emojis_str:
            return json.loads(emojis_str)
        return []

    @emojis.setter
    def emojis(self, value: List[str]) -> None:
        """Set poll emojis from Python list"""
        self.emojis_json = json.dumps(value)

    def get_results(self):
        """Get vote counts for each option"""
        results = {i: 0 for i in range(len(self.options))}
        for vote in self.votes:
            if vote.option_index in results:
                results[vote.option_index] += 1
        return results

    def get_total_votes(self):
        """Get total number of votes (unique users for multiple choice, total votes for single choice)"""
        if bool(self.multiple_choice):
            # For multiple choice, count unique users who voted
            unique_users = set(vote.user_id for vote in self.votes)
            return len(unique_users)
        else:
            # For single choice, count total votes
            return len(self.votes)

    def get_total_vote_count(self):
        """Get total number of individual votes cast (regardless of poll type)"""
        return len(self.votes)

    def get_winner(self):
        """Get winning option(s)"""
        results = self.get_results()
        if not results:
            return None

        max_votes = max(results.values())
        winners = [i for i, votes in results.items() if votes == max_votes]
        return winners

    def should_show_results(self):
        """Determine if results should be shown based on anonymous setting and status"""
        if not bool(self.anonymous):
            return True
        return self.status == "closed"


class Vote(Base):
    """Vote model linking users to poll options"""

    __tablename__ = "votes"

    id = Column(Integer, primary_key=True, index=True)
    poll_id = Column(Integer, ForeignKey("polls.id"), nullable=False)
    user_id = Column(String(50), nullable=False)  # Discord user ID
    option_index = Column(Integer, nullable=False)  # Index of chosen option
    voted_at = Column(DateTime, default=func.now())

    # Relationship to poll
    poll = relationship("Poll", back_populates="votes")


class User(Base):
    """User model for web authentication"""

    __tablename__ = "users"

    id = Column(String(50), primary_key=True)  # Discord user ID as primary key
    username = Column(String(100), nullable=False)
    avatar = Column(String(500), nullable=True)  # Avatar hash
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class UserPreference(Base):
    """User preferences for poll creation"""

    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), ForeignKey("users.id"), nullable=False)
    last_server_id = Column(String(50), nullable=True)  # Last selected server
    # Last selected channel
    last_channel_id = Column(String(50), nullable=True)
    # Last selected role for pinging
    last_role_id = Column(String(50), nullable=True)
    default_timezone = Column(String(50), default="US/Eastern")  # Default timezone
    # Track if user has explicitly set their timezone preference
    timezone_explicitly_set = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationship to user
    user = relationship("User")


class Guild(Base):
    """Cache Discord guild information"""

    __tablename__ = "guilds"

    id = Column(String(50), primary_key=True)  # Discord guild ID
    name = Column(String(255), nullable=False)
    icon = Column(String(500), nullable=True)
    owner_id = Column(String(50), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class Channel(Base):
    """Cache Discord channel information"""

    __tablename__ = "channels"

    id = Column(String(50), primary_key=True)  # Discord channel ID
    guild_id = Column(String(50), ForeignKey("guilds.id"), nullable=False)
    name = Column(String(255), nullable=False)
    type = Column(String(50), nullable=False)  # text, voice, etc.
    position = Column(Integer, default=0)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationship to guild
    guild = relationship("Guild")


# Database utility functions


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_database():
    """Initialize database tables using migration system"""
    from .migrations import initialize_database_if_missing

    success = initialize_database_if_missing()
    if success:
        print("Database initialized successfully!")
    else:
        print("Database initialization failed!")
        raise RuntimeError("Failed to initialize database")


def get_db_session():
    """Get a database session for direct use"""
    return SessionLocal()


# Emoji mapping for poll reactions
POLL_EMOJIS = ["🇦", "🇧", "🇨", "🇩", "🇪", "🇫", "🇬", "🇭", "🇮", "🇯"]


def get_poll_emoji(option_index):
    """Get emoji for poll option index"""
    if 0 <= option_index < len(POLL_EMOJIS):
        return POLL_EMOJIS[option_index]
    return "❓"
