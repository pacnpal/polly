#!/usr/bin/env python3
"""
Polly CLI - Comprehensive command-line interface for poll management
Usage: python -m cli.main [command] [args]
"""

import sys
import os
import asyncio
import argparse
from typing import List

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Set environment configuration path to project root
os.environ.setdefault('DECOUPLE_ENCODING', 'utf-8')

from cli.commands.poll_commands import PollCommands
from cli.commands.system_commands import SystemCommands
from cli.commands.admin_commands import AdminCommands
from cli.utils.cli_helpers import CLIHelpers, setup_logging


class PollyCI:
    """Main CLI class for Polly management"""
    
    def __init__(self):
        self.poll_commands = PollCommands()
        self.system_commands = SystemCommands()
        self.admin_commands = AdminCommands()
        self.helpers = CLIHelpers()
        
    def create_parser(self) -> argparse.ArgumentParser:
        """Create the main argument parser"""
        parser = argparse.ArgumentParser(
            description="Polly CLI - Comprehensive Discord poll management",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  python -m cli.main show 123                    # Show poll details
  python -m cli.main list --status active        # List active polls
  python -m cli.main force-update 123            # Force Discord message update
  python -m cli.main stats                       # Show system stats
  python -m cli.main logs --tail 50              # Show recent logs
  python -m cli.main backup                      # Create database backup
            """
        )
        
        # Global options
        parser.add_argument('--verbose', '-v', action='store_true', 
                          help='Enable verbose output')
        parser.add_argument('--json', action='store_true',
                          help='Output in JSON format')
        parser.add_argument('--no-color', action='store_true',
                          help='Disable colored output')
        
        subparsers = parser.add_subparsers(dest='command', help='Available commands')
        
        # Poll management commands
        self._add_poll_commands(subparsers)
        
        # System commands
        self._add_system_commands(subparsers)
        
        # Admin commands  
        self._add_admin_commands(subparsers)
        
        return parser
    
    def _add_poll_commands(self, subparsers):
        """Add poll management commands"""
        
        # Show poll details
        show_parser = subparsers.add_parser('show', help='Show detailed poll information')
        show_parser.add_argument('poll_id', type=int, help='Poll ID to show')
        show_parser.add_argument('--include-votes', action='store_true',
                               help='Include detailed vote information')
        
        # List polls
        list_parser = subparsers.add_parser('list', help='List polls with filters')
        list_parser.add_argument('--status', choices=['scheduled', 'active', 'closed'],
                               help='Filter by poll status')
        list_parser.add_argument('--guild', type=int, help='Filter by guild ID')
        list_parser.add_argument('--author', type=int, help='Filter by author ID')
        list_parser.add_argument('--limit', type=int, default=20, help='Limit results')
        list_parser.add_argument('--sort', choices=['created', 'updated', 'closes_at'],
                               default='created', help='Sort order')
        
        # Force update Discord message
        update_parser = subparsers.add_parser('force-update', 
                                            help='Force Discord message update from database')
        update_parser.add_argument('poll_id', type=int, help='Poll ID to update')
        update_parser.add_argument('--dry-run', action='store_true',
                                 help='Show what would be updated without applying')
        
        # Search polls
        search_parser = subparsers.add_parser('search', help='Search polls by text')
        search_parser.add_argument('query', help='Search query')
        search_parser.add_argument('--fields', nargs='+', 
                                 choices=['title', 'description', 'options'],
                                 default=['title', 'description'],
                                 help='Fields to search in')
        
        # Close poll
        close_parser = subparsers.add_parser('close', help='Manually close a poll')
        close_parser.add_argument('poll_id', type=int, help='Poll ID to close')
        close_parser.add_argument('--reason', help='Reason for closing')
        close_parser.add_argument('--force', action='store_true',
                                help='Force close even if already closed')
        
        # Reopen poll
        reopen_parser = subparsers.add_parser('reopen', help='Reopen a closed poll')
        reopen_parser.add_argument('poll_id', type=int, help='Poll ID to reopen')
        reopen_parser.add_argument('--duration', type=int, 
                                 help='New duration in minutes from now')
        
        # Validate polls
        validate_parser = subparsers.add_parser('validate', 
                                              help='Validate poll data integrity')
        validate_parser.add_argument('--fix', action='store_true',
                                   help='Attempt to fix found issues')
        validate_parser.add_argument('--poll-id', type=int, 
                                   help='Validate specific poll only')
    
    def _add_system_commands(self, subparsers):
        """Add system management commands"""
        
        # System stats
        stats_parser = subparsers.add_parser('stats', help='Show system statistics')
        stats_parser.add_argument('--detailed', action='store_true',
                                help='Show detailed statistics')
        
        # Health check
        health_parser = subparsers.add_parser('health', help='Check system health')
        health_parser.add_argument('--component', 
                                 choices=['database', 'redis', 'discord', 'all'],
                                 default='all', help='Component to check')
        
        # View logs
        logs_parser = subparsers.add_parser('logs', help='View application logs')
        logs_parser.add_argument('--tail', type=int, default=100,
                               help='Number of recent log entries')
        logs_parser.add_argument('--level', 
                               choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                               help='Filter by log level')
        logs_parser.add_argument('--follow', '-f', action='store_true',
                               help='Follow log output (like tail -f)')
        
        # Cache operations
        cache_parser = subparsers.add_parser('cache', help='Cache management')
        cache_subparsers = cache_parser.add_subparsers(dest='cache_action')
        
        cache_subparsers.add_parser('stats', help='Show cache statistics')
        cache_subparsers.add_parser('clear', help='Clear all cache')
        
        clear_pattern = cache_subparsers.add_parser('clear-pattern', 
                                                  help='Clear cache by pattern')
        clear_pattern.add_argument('pattern', help='Cache key pattern to clear')
        
        # Database operations
        db_parser = subparsers.add_parser('db', help='Database operations')
        db_subparsers = db_parser.add_subparsers(dest='db_action')
        
        db_subparsers.add_parser('backup', help='Create database backup')
        
        restore_parser = db_subparsers.add_parser('restore', help='Restore database backup')
        restore_parser.add_argument('backup_file', help='Backup file to restore')
        
        db_subparsers.add_parser('migrate', help='Run database migrations')
        db_subparsers.add_parser('vacuum', help='Vacuum database (cleanup)')
    
    def _add_admin_commands(self, subparsers):
        """Add admin commands"""
        
        # User management
        user_parser = subparsers.add_parser('user', help='User management')
        user_subparsers = user_parser.add_subparsers(dest='user_action')
        
        show_user = user_subparsers.add_parser('show', help='Show user details')
        show_user.add_argument('user_id', type=int, help='User ID to show')
        
        list_users = user_subparsers.add_parser('list', help='List users')
        list_users.add_argument('--role', choices=['user', 'admin', 'super_admin'],
                              help='Filter by role')
        list_users.add_argument('--guild', type=int, help='Filter by guild')
        
        # Bulk operations
        bulk_parser = subparsers.add_parser('bulk', help='Bulk operations')
        bulk_subparsers = bulk_parser.add_subparsers(dest='bulk_action')
        
        bulk_close = bulk_subparsers.add_parser('close', help='Bulk close polls')
        bulk_close.add_argument('--status', choices=['active', 'scheduled'],
                              help='Status of polls to close')
        bulk_close.add_argument('--guild', type=int, help='Guild ID filter')
        bulk_close.add_argument('--older-than', type=int, 
                              help='Close polls older than N days')
        bulk_close.add_argument('--dry-run', action='store_true',
                              help='Show what would be closed')
        
        # Import/Export
        export_parser = subparsers.add_parser('export', help='Export poll data')
        export_parser.add_argument('output_file', help='Output file path')
        export_parser.add_argument('--format', choices=['json', 'csv'],
                                 default='json', help='Export format')
        export_parser.add_argument('--poll-ids', nargs='+', type=int,
                                 help='Specific poll IDs to export')
        
        import_parser = subparsers.add_parser('import', help='Import poll data')
        import_parser.add_argument('input_file', help='Input file path')
        import_parser.add_argument('--dry-run', action='store_true',
                                 help='Validate import without applying')
    
    async def run(self, args: List[str] = None) -> int:
        """Run the CLI with given arguments"""
        if args is None:
            args = sys.argv[1:]
        
        parser = self.create_parser()
        parsed_args = parser.parse_args(args)
        
        # Setup logging and output formatting
        setup_logging(parsed_args.verbose)
        self.helpers.setup_output_format(
            use_json=parsed_args.json,
            use_color=not parsed_args.no_color
        )
        
        if not parsed_args.command:
            parser.print_help()
            return 1
        
        try:
            # Route to appropriate command handler
            if parsed_args.command in ['show', 'list', 'force-update', 'search', 'close', 'reopen', 'validate']:
                return await self.poll_commands.handle_command(parsed_args)
            elif parsed_args.command in ['stats', 'health', 'logs', 'cache', 'db']:
                return await self.system_commands.handle_command(parsed_args)
            elif parsed_args.command in ['user', 'bulk', 'export', 'import']:
                return await self.admin_commands.handle_command(parsed_args)
            else:
                self.helpers.error(f"Unknown command: {parsed_args.command}")
                return 1
                
        except KeyboardInterrupt:
            self.helpers.info("\nOperation cancelled by user")
            return 1
        except Exception as e:
            self.helpers.error(f"Unexpected error: {str(e)}")
            if parsed_args.verbose:
                import traceback
                traceback.print_exc()
            return 1


def main():
    """Main entry point"""
    cli = PollyCI()
    exit_code = asyncio.run(cli.run())
    sys.exit(exit_code)


if __name__ == '__main__':
    main()