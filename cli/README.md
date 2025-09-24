# Polly CLI - Comprehensive Command-Line Interface

A powerful command-line interface for managing Polly Discord polls, system administration, and debugging operations.

## Installation & Setup

### Prerequisites
- Python 3.8+
- uv (Python package manager)
- Access to Polly database and Redis
- Discord bot token (for some operations)
- `.env` file configured in project root

### Installation

From the project root directory:

```bash
# Install dependencies with uv
uv sync

# Or install specific CLI dependencies
uv add python-decouple colorama psutil
```

### Configuration

The CLI uses python-decouple to read configuration from the `.env` file in the project root:

```bash
# .env file example
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=your_password
DB_NAME=polly

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=your_redis_password

DISCORD_TOKEN=your_bot_token
```

### Running the CLI

From the project root directory:

```bash
# Using uv (recommended)
uv run python -m cli.main [command] [options]

# Or with direct python (ensure dependencies are installed)
python -m cli.main [command] [options]

# With verbose output
uv run python -m cli.main -v [command] [options]

# JSON output format
uv run python -m cli.main --json [command] [options]

# No colored output
uv run python -m cli.main --no-color [command] [options]
```

## Command Categories

### 🗳️ Poll Management Commands

#### Show Poll Details
Display comprehensive information about a specific poll:

```bash
# Basic poll information
python -m cli.main show 123

# Include detailed vote information
python -m cli.main show 123 --include-votes
```

**Output includes:**
- Poll metadata (ID, title, description, status)
- Author and server information
- Created/updated timestamps
- Open/close times
- Vote counts and percentages
- Individual votes (with --include-votes)

#### List Polls
List polls with various filters:

```bash
# List recent polls (default: 20 most recent)
python -m cli.main list

# Filter by status
python -m cli.main list --status active
python -m cli.main list --status closed
python -m cli.main list --status scheduled

# Filter by guild (server)
python -m cli.main list --guild 1234567890

# Filter by author
python -m cli.main list --author 9876543210

# Limit results and sort
python -m cli.main list --limit 50 --sort closes_at

# Combine filters
python -m cli.main list --status active --guild 1234567890 --limit 10
```

#### Force Update Discord Message
Synchronize Discord message with database state:

```bash
# Update Discord message for poll
python -m cli.main force-update 123

# Preview what would be updated (dry run)
python -m cli.main force-update 123 --dry-run
```

**Use cases:**
- Message was deleted but poll is still active
- Database was updated but Discord message is stale
- Manual synchronization after system issues

#### Search Polls
Search polls by text content:

```bash
# Search in titles and descriptions
python -m cli.main search "favorite food"

# Search only in titles
python -m cli.main search "movie night" --fields title

# Search in poll options
python -m cli.main search "pizza" --fields title description options
```

#### Close Poll
Manually close a poll before its scheduled end time:

```bash
# Close a poll with confirmation
python -m cli.main close 123

# Close with custom reason
python -m cli.main close 123 --reason "Early closure due to spam"

# Force close already closed poll
python -m cli.main close 123 --force
```

#### Reopen Poll
Reopen a closed poll:

```bash
# Reopen with original close time
python -m cli.main reopen 123

# Reopen with new duration (30 minutes from now)
python -m cli.main reopen 123 --duration 30
```

#### Validate Polls
Check poll data integrity and fix issues:

```bash
# Validate all polls
python -m cli.main validate

# Validate specific poll
python -m cli.main validate --poll-id 123

# Validate and attempt fixes
python -m cli.main validate --fix
```

**Checks performed:**
- Missing required fields
- Date consistency (opens_at < closes_at)
- Status consistency with current time
- Orphaned poll options
- Data integrity issues

### 🖥️ System Management Commands

#### System Statistics
Display comprehensive system health metrics:

```bash
# Basic system stats
python -m cli.main stats

# Detailed statistics with additional metrics
python -m cli.main stats --detailed
```

**Metrics include:**
- CPU, memory, and disk usage
- Database connection and poll counts
- Redis connection and cache stats
- Discord bot status and guild counts

#### Health Check
Verify system component health:

```bash
# Check all components
python -m cli.main health

# Check specific component
python -m cli.main health --component database
python -m cli.main health --component redis
python -m cli.main health --component discord
```

**Components checked:**
- Database connectivity and response time
- Redis connectivity and basic operations
- Discord bot connection and readiness

#### View Logs
Access application logs with filtering:

```bash
# Show recent log entries (default: 100)
python -m cli.main logs

# Show more entries
python -m cli.main logs --tail 500

# Filter by log level
python -m cli.main logs --level ERROR
python -m cli.main logs --level WARNING

# Follow logs in real-time
python -m cli.main logs --follow
```

#### Cache Management
Manage Redis cache operations:

```bash
# Show cache statistics
python -m cli.main cache stats

# Clear all cache (with confirmation)
python -m cli.main cache clear

# Clear cache keys matching pattern
python -m cli.main cache clear-pattern "poll:*"
python -m cli.main cache clear-pattern "user:123:*"
```

#### Database Operations
Perform database maintenance tasks:

```bash
# Create database backup
python -m cli.main db backup

# Restore from backup
python -m cli.main db restore polly_backup_20240124_143022.sql

# Run database migrations
python -m cli.main db migrate

# Vacuum database (cleanup and optimization)
python -m cli.main db vacuum
```

### 👨‍💼 Admin Commands

#### User Management
Manage and analyze user activity:

```bash
# Show detailed user information
python -m cli.main user show 1234567890

# List all active users
python -m cli.main user list

# Filter users by role (if role system implemented)
python -m cli.main user list --role admin

# Filter users by guild
python -m cli.main user list --guild 9876543210
```

**User information includes:**
- Total polls created
- Polls by status (active, scheduled, closed)
- Total votes cast
- Activity timeline
- Recent polls

#### Bulk Operations
Perform operations on multiple polls:

```bash
# Bulk close active polls (with confirmation)
python -m cli.main bulk close --status active

# Bulk close polls older than 30 days
python -m cli.main bulk close --older-than 30

# Bulk close polls in specific guild
python -m cli.main bulk close --guild 1234567890

# Preview bulk operation (dry run)
python -m cli.main bulk close --status active --dry-run

# Combine filters
python -m cli.main bulk close --status active --guild 1234567890 --older-than 7
```

#### Data Export/Import
Export and import poll data:

```bash
# Export all polls to JSON
python -m cli.main export polls_backup.json

# Export specific polls
python -m cli.main export selected_polls.json --poll-ids 123 456 789

# Export to CSV format
python -m cli.main export polls_data.csv --format csv

# Import polls from JSON
python -m cli.main import polls_backup.json

# Validate import without applying changes
python -m cli.main import polls_backup.json --dry-run
```

## Output Formats

### Standard Output
Human-readable format with colors and formatting:
```
✓ Successfully updated Discord message for poll 123
ℹ Poll 456 is already closed
⚠ Rate limit approaching for user 789
✗ Failed to connect to Redis
```

### JSON Output
Machine-readable format for automation:
```bash
python -m cli.main --json show 123
```

```json
{
  "success": true,
  "data": {
    "ID": 123,
    "Title": "Favorite Programming Language",
    "Status": "active",
    "Total Votes": 42
  },
  "timestamp": "2024-01-24T14:30:22Z"
}
```

## Common Use Cases

### Daily Administration
```bash
# Morning health check
python -m cli.main health

# Check system stats
python -m cli.main stats

# Review recent activity
python -m cli.main list --limit 10
python -m cli.main logs --tail 50
```

### Troubleshooting
```bash
# Poll not updating in Discord
python -m cli.main show 123
python -m cli.main force-update 123

# Find problematic polls
python -m cli.main validate
python -m cli.main list --status active

# Check system health
python -m cli.main health
python -m cli.main cache stats
```

### Maintenance Tasks
```bash
# Weekly cleanup
python -m cli.main bulk close --older-than 30 --dry-run
python -m cli.main cache clear-pattern "old:*"
python -m cli.main db vacuum

# Monthly backup
python -m cli.main db backup
python -m cli.main export monthly_backup.json
```

### Data Analysis
```bash
# User activity report
python -m cli.main user list --json > users.json

# Poll analysis
python -m cli.main list --status closed --limit 100 --json > closed_polls.json
python -m cli.main search "survey" --json > survey_polls.json
```

## Error Handling

The CLI provides detailed error messages and appropriate exit codes:

- **Exit Code 0**: Success
- **Exit Code 1**: General error or operation failed
- **Ctrl+C**: Graceful interruption handling

### Common Error Messages

```bash
✗ Poll 123 not found
✗ Database connection failed: Connection timeout
✗ Redis not available
✗ Discord bot not ready
⚠ Poll 456 is already closed. Use --force to force close.
ℹ No polls found matching criteria
```

## Configuration Management

The CLI uses python-decouple to read configuration from the `.env` file in the project root. This provides secure and flexible configuration management:

```bash
# .env file in project root
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=your_password
DB_NAME=polly

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=your_redis_password

DISCORD_TOKEN=your_bot_token

# Optional settings with defaults
DEBUG=False
LOG_LEVEL=INFO
```

### Configuration Precedence
1. Environment variables (highest priority)
2. `.env` file values
3. Default values in code (lowest priority)

## Automation & Scripting

### Bash Scripts
```bash
#!/bin/bash
# Daily maintenance script

echo "Running daily Polly maintenance..."

# Health check
if ! uv run python -m cli.main health; then
    echo "Health check failed, sending alert..."
    # Send notification
fi

# Close old polls
uv run python -m cli.main bulk close --older-than 30 --dry-run
uv run python -m cli.main cache clear-pattern "expired:*"

echo "Maintenance complete"
```

### Cron Jobs
```bash
# Daily health check at 9 AM
0 9 * * * cd /path/to/polly && uv run python -m cli.main health >> /var/log/polly-health.log

# Weekly backup on Sundays at 2 AM
0 2 * * 0 cd /path/to/polly && uv run python -m cli.main db backup
```

### JSON Processing
```bash
# Get active poll count
active_count=$(uv run python -m cli.main --json list --status active | jq '.data | length')
echo "Active polls: $active_count"

# Export user data for analysis
uv run python -m cli.main --json user list > users.json
```

## Performance Considerations

- Large poll lists: Use `--limit` to reduce query time
- JSON output: More efficient for programmatic processing
- Bulk operations: Always use `--dry-run` first
- Cache operations: Be cautious with `clear` command
- Database backups: Can take time with large datasets

## Security Notes

- CLI requires direct database access
- Some operations require administrative privileges
- Always use `--dry-run` for bulk operations first
- Backup before major operations
- Limit access to production CLI usage

## Troubleshooting

### Common Issues

**"Import could not be resolved" errors:**
- Ensure you're running from the project root
- Check Python path and virtual environment

**Database connection errors:**
- Verify environment variables
- Check database server status
- Confirm network connectivity

**Redis connection errors:**
- Verify Redis server is running
- Check Redis configuration and password

**Discord bot errors:**
- Verify bot token is valid
- Check bot permissions in guilds
- Ensure bot is online

### Getting Help

```bash
# Command help
python -m cli.main --help
python -m cli.main show --help
python -m cli.main bulk --help

# Verbose output for debugging
python -m cli.main -v command_here
```

For additional support, check the application logs and system health status before reporting issues.