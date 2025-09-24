# CLI Implementation Documentation

## Overview
Comprehensive command-line interface for Polly Discord poll management, system administration, and debugging operations.

## Directory Structure
```
cli/
├── __init__.py
├── main.py                 # Main CLI entry point
├── README.md              # Complete usage documentation
├── utils/
│   ├── __init__.py
│   └── cli_helpers.py     # Helper utilities and formatters
└── commands/
    ├── __init__.py
    ├── poll_commands.py    # Poll management commands
    ├── system_commands.py  # System monitoring and maintenance
    └── admin_commands.py   # Administrative operations
```

## Architecture

### Main Entry Point (`cli/main.py`)
- **PollyCI Class**: Main CLI controller with argument parsing and command routing
- **Argument Parser**: Comprehensive argparse configuration with subcommands
- **Command Routing**: Routes commands to appropriate handler modules
- **Global Options**: `--verbose`, `--json`, `--no-color` flags
- **Error Handling**: Graceful error handling with appropriate exit codes

### Helper Utilities (`cli/utils/cli_helpers.py`)
- **CLIHelpers Class**: Output formatting, progress bars, user confirmation
- **DatabaseHelper Class**: Database connection management for CLI operations
- **RedisHelper Class**: Redis connection and basic operations
- **Formatting Functions**: Date/time, duration, byte size, text truncation
- **Color Support**: ANSI color codes with automatic terminal detection

### Command Modules

#### Poll Commands (`cli/commands/poll_commands.py`)
**Commands Implemented:**
- `show <poll_id>` - Display detailed poll information with vote statistics
- `list` - List polls with filtering (status, guild, author, limit, sort)
- `force-update <poll_id>` - Force Discord message synchronization
- `search <query>` - Search polls by text in title/description/options
- `close <poll_id>` - Manually close polls with reason tracking
- `reopen <poll_id>` - Reopen closed polls with optional new duration
- `validate` - Check poll data integrity and fix issues

**Key Features:**
- Comprehensive poll information display
- Vote statistics and individual vote tracking
- Flexible filtering and search capabilities
- Database-Discord synchronization
- Data integrity validation and repair

#### System Commands (`cli/commands/system_commands.py`)
**Commands Implemented:**
- `stats` - System health metrics (CPU, memory, database, Redis, Discord)
- `health` - Component health checks with status reporting
- `logs` - Application log viewing with filtering and tailing
- `cache stats/clear/clear-pattern` - Redis cache management
- `db backup/restore/migrate/vacuum` - Database maintenance operations

**Key Features:**
- Real-time system monitoring
- Component health verification
- Cache statistics and cleanup
- Database backup and maintenance
- Log analysis and monitoring

#### Admin Commands (`cli/commands/admin_commands.py`)
**Commands Implemented:**
- `user show/list` - User activity analysis and management
- `bulk close` - Mass poll closure with filtering
- `export` - Poll data export (JSON/CSV formats)
- `import` - Poll data import with validation

**Key Features:**
- User activity tracking and analysis
- Bulk operations with safety checks
- Data export/import capabilities
- Administrative oversight tools

## Technical Implementation

### Database Integration
- **Async Session Management**: Proper async database session handling
- **Query Optimization**: Efficient queries with proper joins and filtering
- **Error Handling**: Graceful database error handling and recovery

### Output Formatting
- **Multiple Formats**: Human-readable and JSON output modes
- **Color Support**: Conditional ANSI color codes
- **Table Formatting**: Dynamic column width calculation
- **Progress Indicators**: Progress bars for long operations

### Safety Features
- **Dry Run Support**: Preview operations before execution
- **User Confirmation**: Interactive confirmation for destructive operations
- **Comprehensive Validation**: Data integrity checks before operations
- **Error Recovery**: Graceful error handling with detailed messages

## Usage Patterns

### Daily Administration
```bash
python -m cli.main health              # System health check
python -m cli.main stats --detailed    # Comprehensive metrics
python -m cli.main list --limit 10     # Recent activity
python -m cli.main logs --tail 50      # Recent logs
```

### Troubleshooting
```bash
python -m cli.main show 123                    # Poll details
python -m cli.main force-update 123 --dry-run  # Preview Discord sync
python -m cli.main validate --fix              # Fix data issues
python -m cli.main health --component redis    # Component check
```

### Maintenance Operations
```bash
python -m cli.main bulk close --older-than 30 --dry-run  # Preview cleanup
python -m cli.main cache clear-pattern "expired:*"       # Cache cleanup
python -m cli.main db backup                             # Database backup
python -m cli.main export monthly_backup.json            # Data export
```

### Data Analysis
```bash
python -m cli.main --json user list > users.json                    # User export
python -m cli.main --json list --status closed --limit 100 > closed.json  # Closed polls
python -m cli.main search "survey" --json > survey_polls.json       # Survey analysis
```

## Integration Points

### Existing Services
- **Poll Edit Service**: Uses `polly/services/poll/poll_edit_service.py`
- **Poll Closure Service**: Integrates with `polly/services/poll/poll_closure_service.py`
- **Discord Utils**: Uses Discord message update functions
- **Database Layer**: Direct integration with Polly database models

### Error Handling
- **Service Layer**: Proper error propagation from service layer
- **Database Errors**: Connection and query error handling
- **Discord API**: Bot availability and API error handling
- **File Operations**: File I/O error handling for import/export

## Configuration

### Environment Variables
- Database: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`
- Redis: `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`
- Discord: `DISCORD_TOKEN`

### Dependencies
- **Core**: `asyncio`, `argparse`, `logging`, `json`, `csv`
- **System**: `psutil`, `subprocess`, `os`, `sys`
- **Display**: `colorama` for cross-platform color support
- **Database**: Uses existing Polly database models and connections

## Security Considerations

### Access Control
- Requires direct database access
- No built-in authentication (relies on system access)
- Administrative operations require confirmation

### Data Protection
- Dry-run capabilities for destructive operations
- Comprehensive validation before data modification
- Backup recommendations before major operations

### Operational Security
- Limited access to production environments recommended
- Audit logging for administrative operations
- Safe defaults for bulk operations

## Performance Characteristics

### Query Optimization
- Efficient database queries with proper indexing usage
- Pagination support for large result sets
- Selective loading with joinedload for related data

### Resource Management
- Proper async session management
- Memory-efficient processing for large datasets
- Connection pooling through existing infrastructure

### Scalability
- Handles large poll datasets efficiently
- Streaming output for large operations
- Progress indicators for long-running tasks

## Error Codes and Exit Status
- **0**: Success
- **1**: General error or operation failed
- **Ctrl+C**: Graceful interruption handling

## Future Enhancements

### Planned Features
- Real-time log following implementation
- Enhanced export formats (Excel, XML)
- Automated maintenance scheduling
- Integration with monitoring systems

### Extensibility
- Modular command structure for easy extension
- Plugin architecture for custom commands
- Configuration file support
- API integration capabilities

## Maintenance Notes

### Regular Updates
- Keep helper functions in sync with database schema changes
- Update command documentation as features evolve
- Maintain compatibility with service layer changes

### Testing Considerations
- CLI operations should be tested in development environment
- Dry-run capabilities should be used for production testing
- Database backup recommended before major operations

## Documentation Status
- ✅ Complete CLI implementation
- ✅ Comprehensive usage documentation
- ✅ Command reference with examples
- ✅ Integration with existing services
- ✅ Error handling and safety features
- ✅ Performance optimization
- ✅ Security considerations documented