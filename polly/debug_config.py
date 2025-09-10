"""
Polly Debug Configuration
Centralized debug mode configuration for consistent logging across frontend and backend.
"""

import os
import logging
from typing import Dict, Any
from decouple import config


class DebugConfig:
    """Centralized debug configuration manager"""
    
    def __init__(self):
        # Read DEBUG from environment with default False
        self._debug_mode = config("DEBUG", default=False, cast=bool)
        self._initialized = False
        self._original_loggers = {}
        
    @property
    def debug_mode(self) -> bool:
        """Get current debug mode status"""
        return self._debug_mode
    
    def set_debug_mode(self, enabled: bool):
        """Programmatically set debug mode"""
        self._debug_mode = enabled
        self._configure_logging()
    
    def _configure_logging(self):
        """Configure logging based on debug mode"""
        if self._debug_mode:
            # Enable debug logging
            logging.getLogger().setLevel(logging.DEBUG)
            logging.getLogger("polly").setLevel(logging.DEBUG)
            
            # Enable debug for commonly used libraries if needed
            # logging.getLogger("discord").setLevel(logging.DEBUG)
            # logging.getLogger("fastapi").setLevel(logging.DEBUG)
            
        else:
            # Standard logging level
            logging.getLogger().setLevel(logging.INFO)
            logging.getLogger("polly").setLevel(logging.INFO)
    
    def get_logger(self, name: str) -> logging.Logger:
        """Get a logger configured for debug mode"""
        logger = logging.getLogger(name)
        
        # Configure the logger for debug mode if enabled
        if self._debug_mode:
            logger.setLevel(logging.DEBUG)
        
        return logger
    
    def get_frontend_context(self) -> Dict[str, Any]:
        """Get context variables for frontend templates"""
        return {
            "debug_mode": self._debug_mode,
            "debug_enabled": self._debug_mode,  # Alternative name for templates
        }


# Global debug configuration instance
_debug_config = DebugConfig()

def get_debug_config() -> DebugConfig:
    """Get the global debug configuration instance"""
    return _debug_config

def is_debug_mode() -> bool:
    """Quick check if debug mode is enabled"""
    return _debug_config.debug_mode

def get_debug_logger(name: str) -> logging.Logger:
    """Get a debug-aware logger"""
    return _debug_config.get_logger(name)

def get_debug_context() -> Dict[str, Any]:
    """Get debug context for templates"""
    return _debug_config.get_frontend_context()

def configure_debug_logging():
    """Configure logging based on debug mode"""
    _debug_config._configure_logging()

def init_debug_config():
    """Initialize debug configuration (call once at startup)"""
    if not _debug_config._initialized:
        _debug_config._configure_logging()
        _debug_config._initialized = True
        
        # Log the debug mode status
        logger = get_debug_logger(__name__)
        if _debug_config.debug_mode:
            logger.info("🐛 DEBUG mode is ENABLED - Verbose logging active")
        else:
            logger.info("📊 DEBUG mode is disabled - Standard logging")
