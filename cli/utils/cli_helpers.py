"""
CLI helper utilities for output formatting, logging, and common operations
"""

import sys
import json
import logging
import os
from typing import Any, Optional
from datetime import datetime
import colorama
from colorama import Fore, Style

# Set the base directory for .env file loading
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def setup_logging(verbose: bool = False):
    """Setup logging configuration for CLI"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stderr)
        ]
    )


class CLIHelpers:
    """Helper class for CLI operations"""
    
    def __init__(self):
        self.use_json = False
        self.use_color = True
        colorama.init()
    
    def setup_output_format(self, use_json: bool = False, use_color: bool = True):
        """Configure output formatting"""
        self.use_json = use_json
        self.use_color = use_color and sys.stdout.isatty()
    
    def output(self, data: Any, success: bool = True):
        """Output data in the configured format"""
        if self.use_json:
            result = {
                "success": success,
                "data": data,
                "timestamp": datetime.utcnow().isoformat()
            }
            print(json.dumps(result, indent=2, default=str))
        else:
            if isinstance(data, dict):
                self._print_dict(data)
            elif isinstance(data, list):
                self._print_list(data)
            else:
                print(str(data))
    
    def success(self, message: str):
        """Print success message"""
        if self.use_json:
            self.output({"message": message}, success=True)
        else:
            color = Fore.GREEN if self.use_color else ""
            reset = Style.RESET_ALL if self.use_color else ""
            print(f"{color}✓ {message}{reset}")
    
    def info(self, message: str):
        """Print info message"""
        if self.use_json:
            self.output({"message": message}, success=True)
        else:
            color = Fore.BLUE if self.use_color else ""
            reset = Style.RESET_ALL if self.use_color else ""
            print(f"{color}ℹ {message}{reset}")
    
    def warning(self, message: str):
        """Print warning message"""
        if self.use_json:
            self.output({"message": message, "level": "warning"}, success=True)
        else:
            color = Fore.YELLOW if self.use_color else ""
            reset = Style.RESET_ALL if self.use_color else ""
            print(f"{color}⚠ {message}{reset}")
    
    def error(self, message: str):
        """Print error message"""
        if self.use_json:
            self.output({"message": message, "level": "error"}, success=False)
        else:
            color = Fore.RED if self.use_color else ""
            reset = Style.RESET_ALL if self.use_color else ""
            print(f"{color}✗ {message}{reset}", file=sys.stderr)
    
    def table(self, headers: list, rows: list, title: Optional[str] = None):
        """Print a formatted table"""
        if self.use_json:
            self.output({
                "title": title,
                "headers": headers,
                "rows": rows
            })
            return
        
        if title:
            self._print_title(title)
        
        if not rows:
            self.info("No data to display")
            return
        
        # Calculate column widths
        widths = [len(str(h)) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], len(str(cell)))
        
        # Print header
        header_line = " | ".join(h.ljust(w) for h, w in zip(headers, widths))
        separator = "-+-".join("-" * w for w in widths)
        
        if self.use_color:
            print(f"{Fore.CYAN}{header_line}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}{separator}{Style.RESET_ALL}")
        else:
            print(header_line)
            print(separator)
        
        # Print rows
        for row in rows:
            row_line = " | ".join(str(cell).ljust(w) for cell, w in zip(row, widths))
            print(row_line)
    
    def _print_title(self, title: str):
        """Print a section title"""
        if self.use_color:
            print(f"\n{Fore.MAGENTA}{Style.BRIGHT}{title}{Style.RESET_ALL}")
            print(f"{Fore.MAGENTA}{'=' * len(title)}{Style.RESET_ALL}")
        else:
            print(f"\n{title}")
            print("=" * len(title))
    
    def _print_dict(self, data: dict, indent: int = 0):
        """Print a dictionary with formatting"""
        indent_str = "  " * indent
        for key, value in data.items():
            if isinstance(value, dict):
                key_color = Fore.YELLOW if self.use_color else ""
                reset = Style.RESET_ALL if self.use_color else ""
                print(f"{indent_str}{key_color}{key}:{reset}")
                self._print_dict(value, indent + 1)
            elif isinstance(value, list):
                key_color = Fore.YELLOW if self.use_color else ""
                reset = Style.RESET_ALL if self.use_color else ""
                print(f"{indent_str}{key_color}{key}:{reset}")
                self._print_list(value, indent + 1)
            else:
                key_color = Fore.YELLOW if self.use_color else ""
                value_color = Fore.WHITE if self.use_color else ""
                reset = Style.RESET_ALL if self.use_color else ""
                print(f"{indent_str}{key_color}{key}:{reset} {value_color}{value}{reset}")
    
    def _print_list(self, data: list, indent: int = 0):
        """Print a list with formatting"""
        indent_str = "  " * indent
        for i, item in enumerate(data):
            if isinstance(item, dict):
                print(f"{indent_str}- Item {i + 1}:")
                self._print_dict(item, indent + 1)
            elif isinstance(item, list):
                print(f"{indent_str}- List {i + 1}:")
                self._print_list(item, indent + 1)
            else:
                bullet_color = Fore.CYAN if self.use_color else ""
                reset = Style.RESET_ALL if self.use_color else ""
                print(f"{indent_str}{bullet_color}-{reset} {item}")
    
    def confirm(self, message: str, default: bool = False) -> bool:
        """Ask for user confirmation"""
        if self.use_json:
            # In JSON mode, assume yes for automation
            return True
        
        suffix = "[Y/n]" if default else "[y/N]"
        response = input(f"{message} {suffix}: ").strip().lower()
        
        if not response:
            return default
        
        return response.startswith('y')
    
    def progress_bar(self, current: int, total: int, prefix: str = "", length: int = 50):
        """Display a progress bar"""
        if self.use_json:
            return  # Skip progress bars in JSON mode
        
        percent = (current / total) * 100
        filled_length = int(length * current // total)
        bar = '█' * filled_length + '-' * (length - filled_length)
        
        if self.use_color:
            bar_color = Fore.GREEN if current == total else Fore.YELLOW
            reset = Style.RESET_ALL
            print(f'\r{prefix}{bar_color}|{bar}|{reset} {percent:.1f}% ({current}/{total})', end='')
        else:
            print(f'\r{prefix}|{bar}| {percent:.1f}% ({current}/{total})', end='')
        
        if current == total:
            print()  # New line when complete


class DatabaseHelper:
    """Helper for database operations in CLI"""
    
    @staticmethod
    async def get_db_session():
        """Get database session for CLI operations"""
        try:
            from polly.database import get_db_session
            async with get_db_session() as session:
                yield session
        except Exception as e:
            logging.error(f"Failed to get database session: {e}")
            raise
    
    @staticmethod
    async def test_connection() -> bool:
        """Test database connection"""
        try:
            async for session in DatabaseHelper.get_db_session():
                return True
        except Exception as e:
            logging.error(f"Database connection failed: {e}")
            return False


class RedisHelper:
    """Helper for Redis operations in CLI"""
    
    @staticmethod
    def get_redis_client():
        """Get Redis client for CLI operations"""
        try:
            from polly.services.cache.cache_service import get_redis_client
            return get_redis_client()
        except Exception as e:
            logging.error(f"Failed to get Redis client: {e}")
            return None
    
    @staticmethod
    async def test_connection() -> bool:
        """Test Redis connection"""
        try:
            redis_client = RedisHelper.get_redis_client()
            if redis_client and hasattr(redis_client, '_client'):
                await redis_client._client.ping()
                return True
            return False
        except Exception as e:
            logging.error(f"Redis connection failed: {e}")
            return False


def format_datetime(dt: Optional[datetime]) -> str:
    """Format datetime for display"""
    if dt is None:
        return "Never"
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def format_duration(seconds: Optional[int]) -> str:
    """Format duration in seconds to human readable"""
    if seconds is None:
        return "Unknown"
    
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        remaining_seconds = seconds % 60
        return f"{minutes}m {remaining_seconds}s"
    else:
        hours = seconds // 3600
        remaining_minutes = (seconds % 3600) // 60
        return f"{hours}h {remaining_minutes}m"


def format_bytes(bytes_count: int) -> str:
    """Format bytes to human readable size"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_count < 1024.0:
            return f"{bytes_count:.1f} {unit}"
        bytes_count /= 1024.0
    return f"{bytes_count:.1f} PB"


def truncate_text(text: str, max_length: int = 50) -> str:
    """Truncate text with ellipsis"""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."