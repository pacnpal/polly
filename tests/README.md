# Polly Test Suite

This directory contains a comprehensive test suite for the Polly Discord Poll Bot, covering all features, edge cases, and security scenarios.

## Overview

The test suite is designed to be **comprehensive**, **reliable**, and **maintainable**. It covers:

- **Unit Tests**: Individual component testing
- **Integration Tests**: Component interaction testing  
- **End-to-End Tests**: Complete workflow testing
- **Security Tests**: Malicious input and edge case handling
- **Performance Tests**: Load and stress testing
- **Error Handling Tests**: Failure scenario testing

## Test Structure

```
tests/
├── __init__.py                      # Test package initialization
├── conftest.py                      # Pytest fixtures and configuration
├── test_database.py                 # Database model tests
├── test_validators.py               # Validation logic tests
├── test_discord_bot.py              # Discord bot functionality tests
├── test_web_app.py                 # Web application tests
├── test_emoji_handler.py            # Emoji processing tests
├── test_background_tasks.py         # Background task tests
├── test_integration.py              # End-to-end integration tests
├── test_image_generator.py          # Image generation tests
├── run_tests.py                     # Test runner script
├── poll_creation_scenarios.py       # Poll creation test scenarios
├── generate_polls_with_real_images.py  # Real image poll generator
├── generate_comprehensive_polls.py  # Comprehensive poll generator
├── POLL_GENERATION_README.md        # Poll generation documentation
├── REAL_IMAGE_TESTING_README.md     # Real image testing documentation
└── README.md                       # This file
```

## Running Tests

### Prerequisites

Install test dependencies:
```bash
uv sync --dev
```

### Basic Usage

Run all tests:
```bash
python tests/run_tests.py
```

Run specific test categories:
```bash
python tests/run_tests.py unit          # Unit tests only
python tests/run_tests.py integration   # Integration tests only
python tests/run_tests.py fast          # Fast tests only
python tests/run_tests.py security      # Security tests only
```

### Using pytest directly

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_database.py

# Run tests with coverage
pytest tests/ --cov=polly --cov-report=html

# Run tests matching pattern
pytest tests/ -k "test_poll_creation"

# Run tests with specific markers
pytest tests/ -m "not slow"
pytest tests/ -m "security"
pytest tests/ -m "unit"
```

## Comprehensive Poll Generation

The test suite includes powerful poll generation tools for comprehensive testing:

### generate_comprehensive_polls.py

This script creates comprehensive test polls covering all possible combinations of features and configurations.

#### Basic Usage

```bash
# Standard comprehensive testing (~880+ polls)
uv run tests/generate_comprehensive_polls.py

# Dry run to see what would be created
uv run tests/generate_comprehensive_polls.py --dry-run

# Limit number of polls created
uv run tests/generate_comprehensive_polls.py --limit 100

# Export poll configurations to JSON for analysis
uv run tests/generate_comprehensive_polls.py --export-json
```

#### Discord Configuration

```bash
# Use specific Discord server and channel IDs
uv run tests/generate_comprehensive_polls.py --server-id "YOUR_SERVER_ID" --channel-id "YOUR_CHANNEL_ID"

# Use specific user and role IDs
uv run tests/generate_comprehensive_polls.py --user-id "YOUR_USER_ID" --role-id "YOUR_ROLE_ID"

# Complete Discord configuration
uv run tests/generate_comprehensive_polls.py \
  --server-id "987654321098765432" \
  --channel-id "111222333444555666" \
  --user-id "123456789012345678" \
  --role-id "777888999000111222"
```

#### Real Image Testing

```bash
# Use real images from sample-images repository
uv run tests/generate_comprehensive_polls.py --use-real-images

# Ultimate testing: create a poll for each real image (2000+ polls)
uv run tests/generate_comprehensive_polls.py --use-all-images

# Keep repository after testing (don't cleanup)
uv run tests/generate_comprehensive_polls.py --use-all-images --no-cleanup
```

#### What It Tests

The comprehensive poll generator covers:

- **Option Counts**: 2, 3, 4, 5, 6, 7, 8, 9, 10 options
- **Poll Types**: Single choice, multiple choice
- **Visibility**: Anonymous, public
- **Media**: With images, without images (including real images)
- **Role Pings**: Enabled, disabled
- **Emojis**: Default Unicode, custom Discord emojis, mixed, **random selection**
- **Scheduling**: Immediate, future scheduled, far future
- **Timezones**: All major timezones
- **Edge Cases**: Long content, special characters, Unicode
- **Random Combinations**: When using `--use-all-images`, each image gets a random combination of features
- **Random Emojis**: New "random" emoji type selects from extended emoji pools for variety

#### Output and Logging

The script provides detailed logging including:
- Progress updates during generation
- Success/failure rates
- Execution time statistics
- **Combination Usage Tallies**: Shows which feature combinations were used and how often
- Summary statistics

Example combination tally output:
```
COMBINATION USAGE TALLIES:
3opt_unicode_immediate_pub_single_noping: 45 polls
5opt_symbols_future_anon_multi_ping: 32 polls
2opt_default_immediate_pub_single_noping: 28 polls
...
Total unique combinations used: 156
```

#### Modes Explained

1. **Standard Mode**: Creates ~880+ systematic polls covering all combinations
2. **Real Images Mode** (`--use-real-images`): Uses real images from sample-images repository
3. **Ultimate Mode** (`--use-all-images`): Creates one poll per real image with random feature combinations (2000+ polls)
4. **Export Mode** (`--export-json`): Exports poll configurations to JSON without creating polls

#### Configuration Options

**Discord IDs**: By default, the script uses mock Discord IDs for testing. To use real Discord server/channel/user/role IDs:

- `--server-id`: Your Discord server (guild) ID where polls will be created
- `--channel-id`: Your Discord channel ID where polls will be posted  
- `--user-id`: Your Discord user ID (will be set as poll creator)
- `--role-id`: Your Discord role ID (used for role ping testing)

**Emoji Types**: The script now supports these emoji types:

- `default`: Letter emojis (🇦, 🇧, 🇨, etc.)
- `unicode`: Face emojis (😀, 😃, 😄, etc.)
- `symbols`: Symbol emojis (⭐, ❤️, 🔥, etc.)
- `mixed`: Combination of all types
- `random`: **NEW** - Randomly selects from extended emoji pools (50+ emojis per type)
- `custom`: Discord custom emojis (requires bot connection)

The `random` emoji type provides much more variety by selecting from extended pools of 40+ emojis in each category.

### Other Poll Generation Tools

```bash
# Generate polls with specific real images
uv run tests/generate_polls_with_real_images.py

# Run poll creation scenarios
uv run tests/poll_creation_scenarios.py
```

For detailed documentation on poll generation, see:
- `tests/POLL_GENERATION_README.md` - General poll generation guide
- `tests/REAL_IMAGE_TESTING_README.md` - Real image testing guide

## Test Categories

### Unit Tests (`test_database.py`, `test_validators.py`, `test_emoji_handler.py`)

Test individual components in isolation:
- Database models and relationships
- Validation functions
- Emoji processing logic
- Utility functions

**Coverage**: All public methods, edge cases, error conditions

### Integration Tests (`test_web_app.py`, `test_discord_bot.py`, `test_background_tasks.py`)

Test component interactions:
- Web routes and HTMX endpoints
- Discord bot event handling
- Background task scheduling
- Database operations

**Coverage**: API endpoints, event flows, task execution

### End-to-End Tests (`test_integration.py`)

Test complete workflows:
- Poll creation → Discord posting → Voting → Results
- User authentication → Poll management
- Error propagation across components
- Data consistency across systems

**Coverage**: Full user journeys, cross-component data flow

## Test Features

### Comprehensive Edge Case Testing

The test suite includes extensive edge case testing:

- **Unicode Handling**: Emojis, special characters, RTL text
- **Input Validation**: XSS, SQL injection, path traversal
- **Boundary Conditions**: Max/min values, empty inputs
- **Timezone Handling**: DST transitions, invalid timezones
- **Concurrent Operations**: Race conditions, deadlocks
- **Error Recovery**: Network failures, database errors

### Security Testing

Security-focused tests cover:
- **Input Sanitization**: Malicious payloads, script injection
- **Authorization**: Access control, privilege escalation
- **Data Validation**: Type confusion, buffer overflows
- **Rate Limiting**: Abuse prevention, DoS protection

### Performance Testing

Performance tests validate:
- **Large Datasets**: Many polls, votes, users
- **Concurrent Operations**: Multiple simultaneous requests
- **Memory Usage**: Memory leaks, resource cleanup
- **Response Times**: Acceptable performance thresholds

## Test Data and Fixtures

### Fixtures (`conftest.py`)

Comprehensive fixtures provide:
- **Database**: Temporary SQLite databases
- **Mock Objects**: Discord bot, users, messages, reactions
- **Test Data**: Sample polls, votes, users
- **Edge Cases**: Malicious inputs, extreme values
- **Utilities**: Helper functions, test utilities

### Test Data Categories

- **Valid Data**: Typical use cases, happy paths
- **Edge Cases**: Boundary conditions, unusual inputs
- **Malicious Data**: Security attack vectors
- **Performance Data**: Large datasets, stress scenarios

## Configuration

### Pytest Configuration (`pytest.ini`)

- **Test Discovery**: Automatic test detection
- **Markers**: Test categorization and filtering
- **Coverage**: Code coverage reporting
- **Logging**: Detailed test execution logs
- **Warnings**: Filtered noise, relevant alerts

### Environment Variables

Tests use these environment variables:
- `TESTING=1`: Enables test mode
- `DATABASE_URL=sqlite:///:memory:`: In-memory database
- `DISCORD_TOKEN=test_token`: Mock Discord token

## Best Practices

### Writing Tests

1. **Descriptive Names**: Clear test method names
2. **Single Responsibility**: One concept per test
3. **Arrange-Act-Assert**: Clear test structure
4. **Mock External Dependencies**: Isolate units under test
5. **Test Edge Cases**: Boundary conditions, error paths

### Test Organization

1. **Group Related Tests**: Use test classes
2. **Use Fixtures**: Reusable test data and setup
3. **Mark Tests**: Categorize with pytest markers
4. **Document Complex Tests**: Explain non-obvious logic

### Maintenance

1. **Keep Tests Updated**: Sync with code changes
2. **Remove Obsolete Tests**: Clean up unused tests
3. **Refactor Test Code**: Apply same standards as production
4. **Monitor Coverage**: Maintain high test coverage

## Troubleshooting

### Common Issues

**Import Errors**:
```bash
# Ensure dependencies are installed
uv sync --dev

# Check Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

**Database Errors**:
```bash
# Tests use in-memory SQLite by default
# Check DATABASE_URL environment variable
```

**Async Test Issues**:
```bash
# Ensure pytest-asyncio is installed
# Check asyncio_mode = auto in pytest.ini
```

**Mock Failures**:
```bash
# Verify mock objects match actual interfaces
# Check patch paths are correct
```

### Debug Mode

Run tests with debugging:
```bash
pytest tests/ -v -s --tb=long --log-cli-level=DEBUG
```

### Coverage Reports

Generate detailed coverage:
```bash
pytest tests/ --cov=polly --cov-report=html --cov-report=term-missing
open htmlcov/index.html  # View HTML report
```

## Contributing

When adding new features:

1. **Write Tests First**: TDD approach preferred
2. **Cover All Paths**: Happy path, error cases, edge cases
3. **Update Fixtures**: Add necessary test data
4. **Document Tests**: Explain complex test scenarios
5. **Run Full Suite**: Ensure no regressions

### Test Checklist

- [ ] Unit tests for new functions/methods
- [ ] Integration tests for new endpoints/workflows
- [ ] Edge case tests for input validation
- [ ] Security tests for user inputs
- [ ] Performance tests for data-heavy operations
- [ ] Error handling tests for failure scenarios
- [ ] Documentation updates for new test patterns

## Metrics

The test suite aims for:
- **Code Coverage**: >80% line coverage
- **Test Count**: >500 comprehensive tests
- **Edge Cases**: >100 edge case scenarios
- **Security Tests**: >50 security-focused tests
- **Performance**: Tests complete in <5 minutes

## Support

For test-related questions:
1. Check this README
2. Review existing test patterns
3. Examine fixture implementations
4. Consult pytest documentation
5. Ask the development team

---

**Remember**: Good tests are an investment in code quality, maintainability, and developer confidence. Write tests that you'd want to debug at 2 AM! 🧪✨
