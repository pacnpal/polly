"""
System management commands for Polly CLI
"""

import logging
import os
import sys
import subprocess
from typing import Optional
from datetime import datetime, timedelta
import psutil
from decouple import config

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from cli.utils.cli_helpers import CLIHelpers, DatabaseHelper, RedisHelper, format_bytes, format_duration


class SystemCommands:
    """System management command handlers"""
    
    def __init__(self):
        self.helpers = CLIHelpers()
        self.logger = logging.getLogger(__name__)
    
    async def handle_command(self, args) -> int:
        """Route system commands to appropriate handlers"""
        try:
            if args.command == 'stats':
                return await self.show_stats(args.detailed)
            elif args.command == 'health':
                return await self.health_check(args.component)
            elif args.command == 'logs':
                return await self.view_logs(args.tail, args.level, args.follow)
            elif args.command == 'cache':
                return await self.cache_operations(args)
            elif args.command == 'db':
                return await self.database_operations(args)
            else:
                self.helpers.error(f"Unknown system command: {args.command}")
                return 1
        except Exception as e:
            self.helpers.error(f"System command failed: {str(e)}")
            self.logger.exception("System command error")
            return 1
    
    async def show_stats(self, detailed: bool = False) -> int:
        """Show system statistics"""
        try:
            stats = {}
            
            # System stats
            stats["System"] = {
                "CPU Usage": f"{psutil.cpu_percent(interval=1):.1f}%",
                "Memory Usage": f"{psutil.virtual_memory().percent:.1f}%",
                "Disk Usage": f"{psutil.disk_usage('/').percent:.1f}%",
                "Load Average": f"{os.getloadavg()[0]:.2f}" if hasattr(os, 'getloadavg') else "N/A"
            }
            
            # Database stats
            try:
                async for session in DatabaseHelper.get_db_session():
                    from polly.database import Poll, Vote
                    from sqlalchemy import func, text
                    
                    # Poll counts by status
                    poll_counts = await session.execute(
                        session.query(Poll.status, func.count(Poll.id))
                        .group_by(Poll.status)
                    )
                    
                    poll_stats = dict(poll_counts.fetchall())
                    total_polls = sum(poll_stats.values())
                    
                    # Vote counts
                    vote_count = await session.execute(
                        session.query(func.count(Vote.id))
                    )
                    total_votes = vote_count.scalar()
                    
                    stats["Database"] = {
                        "Total Polls": total_polls,
                        "Active Polls": poll_stats.get('active', 0),
                        "Scheduled Polls": poll_stats.get('scheduled', 0),
                        "Closed Polls": poll_stats.get('closed', 0),
                        "Total Votes": total_votes,
                        "Connection": "✓ Connected"
                    }
                    
                    if detailed:
                        # Database size info
                        try:
                            db_size = await session.execute(text("SELECT pg_database_size(current_database())"))
                            size_bytes = db_size.scalar()
                            stats["Database"]["Size"] = format_bytes(size_bytes)
                        except:
                            pass
                            
            except Exception as e:
                stats["Database"] = {"Connection": f"✗ Error: {str(e)}"}
            
            # Redis stats
            try:
                redis_client = RedisHelper.get_redis_client()
                if redis_client and hasattr(redis_client, '_client'):
                    info = await redis_client._client.info()
                    stats["Redis"] = {
                        "Connection": "✓ Connected",
                        "Used Memory": format_bytes(info.get('used_memory', 0)),
                        "Connected Clients": info.get('connected_clients', 0),
                        "Total Commands": info.get('total_commands_processed', 0),
                        "Keyspace Hits": info.get('keyspace_hits', 0),
                        "Keyspace Misses": info.get('keyspace_misses', 0)
                    }
                    
                    if detailed:
                        stats["Redis"]["Version"] = info.get('redis_version', 'Unknown')
                        stats["Redis"]["Uptime"] = format_duration(info.get('uptime_in_seconds', 0))
                else:
                    stats["Redis"] = {"Connection": "✗ Not available"}
            except Exception as e:
                stats["Redis"] = {"Connection": f"✗ Error: {str(e)}"}
            
            # Discord bot stats (if available)
            try:
                from polly.discord_bot import get_bot_instance
                bot = get_bot_instance()
                if bot:
                    stats["Discord Bot"] = {
                        "Status": "✓ Connected" if bot.is_ready() else "⚠ Not ready",
                        "Guilds": len(bot.guilds),
                        "Users": sum(guild.member_count for guild in bot.guilds),
                        "Latency": f"{bot.latency * 1000:.1f}ms"
                    }
                else:
                    stats["Discord Bot"] = {"Status": "✗ Not available"}
            except Exception as e:
                stats["Discord Bot"] = {"Status": f"✗ Error: {str(e)}"}
            
            self.helpers.output(stats)
            return 0
            
        except Exception as e:
            self.helpers.error(f"Failed to get system stats: {str(e)}")
            return 1
    
    async def health_check(self, component: str = 'all') -> int:
        """Check system health"""
        try:
            health_status = {}
            overall_healthy = True
            
            components_to_check = ['database', 'redis', 'discord'] if component == 'all' else [component]
            
            for comp in components_to_check:
                if comp == 'database':
                    try:
                        is_healthy = await DatabaseHelper.test_connection()
                        health_status['Database'] = "✓ Healthy" if is_healthy else "✗ Unhealthy"
                        if not is_healthy:
                            overall_healthy = False
                    except Exception as e:
                        health_status['Database'] = f"✗ Error: {str(e)}"
                        overall_healthy = False
                
                elif comp == 'redis':
                    try:
                        is_healthy = await RedisHelper.test_connection()
                        health_status['Redis'] = "✓ Healthy" if is_healthy else "✗ Unhealthy"
                        if not is_healthy:
                            overall_healthy = False
                    except Exception as e:
                        health_status['Redis'] = f"✗ Error: {str(e)}"
                        overall_healthy = False
                
                elif comp == 'discord':
                    try:
                        from polly.discord_bot import get_bot_instance
                        bot = get_bot_instance()
                        is_healthy = bot is not None and bot.is_ready()
                        health_status['Discord Bot'] = "✓ Healthy" if is_healthy else "✗ Unhealthy"
                        if not is_healthy:
                            overall_healthy = False
                    except Exception as e:
                        health_status['Discord Bot'] = f"✗ Error: {str(e)}"
                        overall_healthy = False
            
            health_status['Overall'] = "✓ All systems healthy" if overall_healthy else "⚠ Issues detected"
            
            self.helpers.output(health_status)
            return 0 if overall_healthy else 1
            
        except Exception as e:
            self.helpers.error(f"Health check failed: {str(e)}")
            return 1
    
    async def view_logs(self, tail_lines: int = 100, level: Optional[str] = None, follow: bool = False) -> int:
        """View application logs"""
        try:
            # For now, this is a placeholder - in a real implementation, you'd read from log files
            # or integrate with your logging system
            
            if follow:
                self.helpers.info("Following logs (Ctrl+C to stop)...")
                # In a real implementation, you'd tail the log file
                self.helpers.warning("Log following not implemented - showing recent entries instead")
            
            # Simulate reading logs - replace with actual log reading logic
            sample_logs = [
                {"timestamp": datetime.utcnow() - timedelta(minutes=5), "level": "INFO", "message": "Poll 123 opened"},
                {"timestamp": datetime.utcnow() - timedelta(minutes=3), "level": "INFO", "message": "Vote received for poll 123"},
                {"timestamp": datetime.utcnow() - timedelta(minutes=1), "level": "WARNING", "message": "Rate limit approaching for user 456"},
                {"timestamp": datetime.utcnow(), "level": "INFO", "message": "Poll 123 closed automatically"}
            ]
            
            # Filter by level if specified
            if level:
                sample_logs = [log for log in sample_logs if log['level'] == level]
            
            # Apply tail limit
            recent_logs = sample_logs[-tail_lines:]
            
            if not recent_logs:
                self.helpers.info("No logs found matching criteria")
                return 0
            
            self.helpers._print_title(f"Recent Logs (last {len(recent_logs)} entries)")
            
            for log in recent_logs:
                timestamp = log['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
                level_color = {
                    'DEBUG': '\033[36m',  # Cyan
                    'INFO': '\033[32m',   # Green
                    'WARNING': '\033[33m', # Yellow
                    'ERROR': '\033[31m',  # Red
                    'CRITICAL': '\033[35m' # Magenta
                }.get(log['level'], '')
                
                reset_color = '\033[0m' if self.helpers.use_color else ''
                
                print(f"{timestamp} {level_color}[{log['level']}]{reset_color} {log['message']}")
            
            return 0
            
        except Exception as e:
            self.helpers.error(f"Failed to view logs: {str(e)}")
            return 1
    
    async def cache_operations(self, args) -> int:
        """Handle cache operations"""
        try:
            if not hasattr(args, 'cache_action') or not args.cache_action:
                self.helpers.error("No cache action specified")
                return 1
            
            redis_client = RedisHelper.get_redis_client()
            if not redis_client or not hasattr(redis_client, '_client'):
                self.helpers.error("Redis not available")
                return 1
            
            if args.cache_action == 'stats':
                info = await redis_client._client.info()
                cache_stats = {
                    "Memory Usage": format_bytes(info.get('used_memory', 0)),
                    "Max Memory": format_bytes(info.get('maxmemory', 0)) if info.get('maxmemory') else "No limit",
                    "Connected Clients": info.get('connected_clients', 0),
                    "Keyspace Hits": info.get('keyspace_hits', 0),
                    "Keyspace Misses": info.get('keyspace_misses', 0),
                    "Hit Rate": f"{(info.get('keyspace_hits', 0) / max(info.get('keyspace_hits', 0) + info.get('keyspace_misses', 0), 1)) * 100:.1f}%"
                }
                
                self.helpers.output(cache_stats)
                return 0
            
            elif args.cache_action == 'clear':
                if not self.helpers.confirm("Clear all cache data?"):
                    self.helpers.info("Operation cancelled")
                    return 0
                
                await redis_client._client.flushdb()
                self.helpers.success("Cache cleared successfully")
                return 0
            
            elif args.cache_action == 'clear-pattern':
                pattern = args.pattern
                keys = await redis_client._client.keys(pattern)
                
                if not keys:
                    self.helpers.info(f"No keys found matching pattern '{pattern}'")
                    return 0
                
                if not self.helpers.confirm(f"Clear {len(keys)} keys matching '{pattern}'?"):
                    self.helpers.info("Operation cancelled")
                    return 0
                
                deleted = await redis_client._client.delete(*keys)
                self.helpers.success(f"Cleared {deleted} cache keys")
                return 0
            
            else:
                self.helpers.error(f"Unknown cache action: {args.cache_action}")
                return 1
                
        except Exception as e:
            self.helpers.error(f"Cache operation failed: {str(e)}")
            return 1
    
    async def database_operations(self, args) -> int:
        """Handle database operations"""
        try:
            if not hasattr(args, 'db_action') or not args.db_action:
                self.helpers.error("No database action specified")
                return 1
            
            if args.db_action == 'backup':
                timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
                backup_file = f"polly_backup_{timestamp}.sql"
                
                self.helpers.info(f"Creating database backup: {backup_file}")
                
                # In a real implementation, you'd use pg_dump or similar
                # This is a placeholder showing the structure
                try:
                    cmd = [
                        'pg_dump',
                        '-h', config('DB_HOST', default='localhost'),
                        '-U', config('DB_USER', default='postgres'),
                        '-d', config('DB_NAME', default='polly'),
                        '-f', backup_file
                    ]
                    
                    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                    self.helpers.success(f"Database backup created: {backup_file}")
                    return 0
                    
                except subprocess.CalledProcessError as e:
                    self.helpers.error(f"Backup failed: {e.stderr}")
                    return 1
                except FileNotFoundError:
                    self.helpers.error("pg_dump not found. Please install PostgreSQL client tools.")
                    return 1
            
            elif args.db_action == 'restore':
                backup_file = args.backup_file
                
                if not os.path.exists(backup_file):
                    self.helpers.error(f"Backup file not found: {backup_file}")
                    return 1
                
                if not self.helpers.confirm(f"Restore database from '{backup_file}'? This will overwrite current data!"):
                    self.helpers.info("Operation cancelled")
                    return 0
                
                # In a real implementation, you'd use psql to restore
                self.helpers.warning("Database restore not fully implemented - use psql manually")
                return 1
            
            elif args.db_action == 'migrate':
                self.helpers.info("Running database migrations...")
                
                try:
                    # Import and run migrations
                    from polly.migrations import run_migrations
                    await run_migrations()
                    self.helpers.success("Database migrations completed")
                    return 0
                except Exception as e:
                    self.helpers.error(f"Migration failed: {str(e)}")
                    return 1
            
            elif args.db_action == 'vacuum':
                self.helpers.info("Vacuuming database...")
                
                try:
                    async for session in DatabaseHelper.get_db_session():
                        from sqlalchemy import text
                        await session.execute(text("VACUUM ANALYZE"))
                        await session.commit()
                    
                    self.helpers.success("Database vacuum completed")
                    return 0
                except Exception as e:
                    self.helpers.error(f"Vacuum failed: {str(e)}")
                    return 1
            
            else:
                self.helpers.error(f"Unknown database action: {args.db_action}")
                return 1
                
        except Exception as e:
            self.helpers.error(f"Database operation failed: {str(e)}")
            return 1