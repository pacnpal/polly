"""
Polly Database Models
SQLite database with SQLAlchemy ORM for polls, votes, and users.
"""

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.sql import func
from datetime import datetime
from typing import List, Dict, Any
import json
import os

# Database setup
DATABASE_URL = "sqlite:///./polly.db"
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
    image_path = Column(String(500), nullable=True)  # Path to uploaded image
    server_id = Column(String(50), nullable=False)  # Discord server ID
    channel_id = Column(String(50), nullable=False)  # Discord channel ID
    creator_id = Column(String(50), nullable=False)  # Discord user ID
    # Discord message ID when posted
    message_id = Column(String(50), nullable=True)
    open_time = Column(DateTime, nullable=False)  # When poll opens
    close_time = Column(DateTime, nullable=False)  # When poll closes
    created_at = Column(DateTime, default=func.now())
    status = Column(String(20), default="scheduled")  # scheduled/active/closed

    # Relationship to votes
    votes = relationship("Vote", back_populates="poll",
                         cascade="all, delete-orphan")

    @property
    def options(self) -> List[str]:
        """Get poll options as Python list"""
        options_str = getattr(self, 'options_json', None)
        if options_str:
            return json.loads(options_str)
        return []

    @options.setter
    def options(self, value: List[str]) -> None:
        """Set poll options from Python list"""
        self.options_json = json.dumps(value)

    def get_results(self):
        """Get vote counts for each option"""
        results = {i: 0 for i in range(len(self.options))}
        for vote in self.votes:
            if vote.option_index in results:
                results[vote.option_index] += 1
        return results

    def get_total_votes(self):
        """Get total number of votes"""
        return len(self.votes)


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

    id = Column(Integer, primary_key=True, index=True)
    discord_id = Column(String(50), unique=True, nullable=False)
    username = Column(String(100), nullable=False)
    avatar_url = Column(String(500), nullable=True)
    last_login = Column(DateTime, default=func.now())

# Database utility functions


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_database():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)
    print("Database initialized successfully!")


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


if __name__ == "__main__":
    # Initialize database when run directly
    init_database()
