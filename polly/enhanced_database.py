"""
Enhanced Database Module with Memory Optimization
Provides optimized database connection management with pooling and monitoring.
"""

import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
from contextlib import contextmanager
from decouple import config
from typing import Generator

logger = logging.getLogger(__name__)

# Enhanced database configuration with connection pooling
class DatabaseConfig:
    """Database configuration with memory optimization settings"""
    
    def __init__(self):
        self.database_url = config("DATABASE_URL", default="sqlite:///./db/polly.db")
        
        # Connection pool settings for memory optimization
        self.pool_size = config("DB_POOL_SIZE", default=5, cast=int)
        self.max_overflow = config("DB_MAX_OVERFLOW", default=10, cast=int)
        self.pool_timeout = config("DB_POOL_TIMEOUT", default=30, cast=int)
        self.pool_recycle = config("DB_POOL_RECYCLE", default=3600, cast=int)  # 1 hour
        
        # Memory optimization settings
        self.echo_sql = config("DB_ECHO", default=False, cast=bool)
        
    def create_engine(self):
        """Create optimized database engine with connection pooling"""
        
        if self.database_url.startswith("sqlite"):
            # SQLite-specific optimizations
            engine = create_engine(
                self.database_url,
                connect_args={
                    "check_same_thread": False,
                    "timeout": 20,  # Prevent hanging connections
                },
                poolclass=QueuePool,
                pool_size=self.pool_size,
                max_overflow=self.max_overflow,
                pool_timeout=self.pool_timeout,
                pool_recycle=self.pool_recycle,
                pool_pre_ping=True,  # Verify connections before use
                echo=self.echo_sql,
            )
        else:
            # PostgreSQL/MySQL optimizations
            engine = create_engine(
                self.database_url,
                poolclass=QueuePool,
                pool_size=self.pool_size,
                max_overflow=self.max_overflow,
                pool_timeout=self.pool_timeout,
                pool_recycle=self.pool_recycle,
                pool_pre_ping=True,
                echo=self.echo_sql,
            )
        
        logger.info(f"🔧 DATABASE ENGINE - Created with pool_size={self.pool_size}, "
                   f"max_overflow={self.max_overflow}, recycle={self.pool_recycle}s")
        
        return engine


# Global database configuration
db_config = DatabaseConfig()
optimized_engine = db_config.create_engine()
OptimizedSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=optimized_engine)


@contextmanager
def get_optimized_db_session() -> Generator:
    """
    Get an optimized database session with automatic cleanup
    
    Usage:
        with get_optimized_db_session() as db:
            # Use db session
            pass
    """
    session = OptimizedSessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Database session error: {e}")
        raise
    finally:
        session.close()


class DatabaseMonitor:
    """Monitor database connection pool and memory usage"""
    
    def __init__(self, engine):
        self.engine = engine
        
    def get_pool_status(self) -> dict:
        """Get current connection pool status"""
        try:
            pool = self.engine.pool
            return {
                "pool_size": pool.size(),
                "checked_in": pool.checkedin(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow(),
                "invalid": pool.invalid(),
            }
        except Exception as e:
            logger.error(f"Error getting pool status: {e}")
            return {}
    
    def log_pool_status(self):
        """Log current pool status for monitoring"""
        status = self.get_pool_status()
        if status:
            logger.info(f"🔍 DB POOL STATUS - Size: {status.get('pool_size', 0)}, "
                       f"In: {status.get('checked_in', 0)}, "
                       f"Out: {status.get('checked_out', 0)}, "
                       f"Overflow: {status.get('overflow', 0)}")
    
    def cleanup_connections(self):
        """Force cleanup of idle connections"""
        try:
            # Dispose of current connection pool and recreate
            self.engine.dispose()
            logger.info("🧹 DB CLEANUP - Connection pool disposed and recreated")
        except Exception as e:
            logger.error(f"Error cleaning up connections: {e}")


# Global database monitor
db_monitor = DatabaseMonitor(optimized_engine)


def optimize_database_memory():
    """Perform database memory optimization"""
    try:
        logger.info("🧠 DB MEMORY OPTIMIZATION - Starting database optimization")
        
        # Log current pool status
        db_monitor.log_pool_status()
        
        # Clean up idle connections
        db_monitor.cleanup_connections()
        
        logger.info("✅ DB MEMORY OPTIMIZATION - Database optimization completed")
        
    except Exception as e:
        logger.error(f"❌ DB MEMORY OPTIMIZATION - Error during optimization: {e}")


# Backward compatibility - use optimized session by default
def get_db_session():
    """Get a database session - uses optimized connection pooling"""
    return OptimizedSessionLocal()