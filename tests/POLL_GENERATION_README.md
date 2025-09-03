# Comprehensive Poll Generation Scripts

This directory contains powerful scripts for generating comprehensive test polls that cover every possible combination of poll options and configurations.

## Scripts Overview

### 1. `generate_comprehensive_polls.py`
**Purpose**: Creates polls systematically covering all possible combinations of poll features with real generated test images.

**Features Tested**:
- Option counts: 2, 3, 4, 5, 6, 7, 8, 9, 10 options
- Poll types: single choice, multiple choice
- Visibility: anonymous, public
- Media: with images, without images
- Role pings: enabled, disabled
- Emojis: default Unicode, custom Discord emojis, mixed types
- Scheduling: immediate, future, far future
- Timezones: UTC, US/Eastern, US/Central, US/Mountain, US/Pacific, Europe/London, Europe/Paris, Asia/Tokyo, Australia/Sydney
- Edge cases and boundary conditions

**Usage**:
```bash
# Generate all possible poll combinations (1000+ polls)
python tests/generate_comprehensive_polls.py

# Dry run to see what would be created without actually creating polls
python tests/generate_comprehensive_polls.py --dry-run

# Limit the number of polls created
python tests/generate_comprehensive_polls.py --limit 50

# Export poll combinations to JSON for analysis
python tests/generate_comprehensive_polls.py --export-json
```

**Generated Combinations**:
- **Base combinations**: 9 option counts × 2 anonymous × 2 multiple choice × 2 role ping × 2 image × 4 emoji types × 3 schedule types = 864 combinations
- **Edge cases**: Additional 20+ edge cases for boundary testing
- **Total**: 880+ unique poll combinations

### 2. `poll_creation_scenarios.py`
**Purpose**: Tests specific poll creation scenarios and edge cases that might cause issues.

**Scenarios Tested**:
- **Boundary Conditions**: Minimum/maximum values, limits testing
- **Error Conditions**: Invalid data, recovery scenarios
- **Unicode Stress**: Heavy emoji usage, multilingual content, special characters
- **Timing Edge Cases**: Short/long durations, timezone transitions, DST
- **Emoji Combinations**: Various emoji types and modifiers
- **Large Content**: Testing system limits with large text
- **Concurrent Creation**: Multiple polls created simultaneously
- **Malformed Data**: Invalid input handling
- **Database Stress**: Rapid poll creation testing

**Usage**:
```bash
# Run all scenarios
python tests/poll_creation_scenarios.py

# Run specific scenario
python tests/poll_creation_scenarios.py --scenario boundary_conditions
python tests/poll_creation_scenarios.py --scenario unicode_stress
python tests/poll_creation_scenarios.py --scenario concurrent_creation
```

**Available Scenarios**:
- `boundary_conditions`
- `error_conditions`
- `unicode_stress`
- `timing_edge_cases`
- `emoji_combinations`
- `large_content`
- `concurrent_creation`
- `malformed_data`
- `database_stress`
- `all_scenarios`

## Poll Configuration Matrix

### Option Counts Tested
- 2 options (minimum)
- 3 options
- 4 options
- 5 options
- 6 options
- 7 options
- 8 options
- 9 options
- 10 options (maximum)

### Poll Types
- **Single Choice**: Users can select only one option
- **Multiple Choice**: Users can select multiple options

### Visibility Options
- **Public**: Results visible during voting
- **Anonymous**: Results hidden until poll closes

### Media Options
- **With Images**: Polls include uploaded images
- **Without Images**: Text-only polls

### Role Ping Options
- **Enabled**: Pings specified role when poll opens/closes
- **Disabled**: No role pinging

### Emoji Types
- **Default**: Standard Unicode letter emojis (🇦, 🇧, 🇨...)
- **Unicode**: Various Unicode emojis (😀, 😃, 😄...)
- **Symbols**: Symbol emojis (⭐, ❤️, 🔥...)
- **Mixed**: Combination of different emoji types
- **Custom**: Discord server custom emojis (requires bot access)

### Scheduling Types
- **Immediate**: Opens in 1 minute, runs for 1 hour
- **Future**: Opens in 1 hour, runs for 2 hours
- **Far Future**: Opens in 1 day, runs for 1 day

### Timezone Testing
- UTC
- US/Eastern
- US/Central
- US/Mountain
- US/Pacific
- Europe/London
- Europe/Paris
- Asia/Tokyo
- Australia/Sydney

## Edge Cases Covered

### Boundary Testing
- Minimum field lengths (name: 3 chars, question: 5 chars)
- Maximum field lengths (name: 255 chars, question: 2000 chars)
- Minimum options (2)
- Maximum options (10)
- Minimum duration (1 minute)
- Maximum duration (30 days)

### Content Testing
- Empty strings
- Very long content
- Special characters: `!@#$%^&*()_+-=[]{}|;':\",./<>?`
- Unicode characters: `àáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ`
- Mathematical symbols: `∀∂∃∄∅∆∇∈∉∊∋∌∍∎∏∐∑`
- Zero-width characters: `\u200b\u200c\u200d\ufeff`
- Multilingual content (Japanese, Russian, Arabic)

### Emoji Testing
- Standard Unicode emojis
- Flag emojis (🇺🇸, 🇬🇧, 🇯🇵)
- Complex emojis with modifiers (👨‍💻, 👩‍🚀)
- Skin tone modifiers (👍🏻, 👍🏼, 👍🏽)
- Mixed emoji types

### Timing Testing
- Very short durations (1 minute)
- Very long durations (30 days)
- Different timezones
- DST transition periods
- Leap year edge cases

### Error Conditions
- Invalid data types
- Missing required fields
- Past scheduling times
- Close time before open time
- Malformed data structures

## Output and Logging

Both scripts provide comprehensive logging:

### Success Indicators
- ✅ Successful operations
- 📊 Statistics and summaries
- 🎉 Completion messages

### Warning Indicators
- ⚠️ Unexpected successes (for error tests)
- 📝 Non-critical issues

### Error Indicators
- ❌ Failed operations
- 🚨 Critical errors
- 💥 Exceptions

### Information
- 🔍 Test progress
- 📈 Statistics
- 🚀 Starting operations

## Generated Data Analysis

### JSON Export Format
When using `--export-json`, the comprehensive generator creates a JSON file with:
```json
{
  "name": "Poll Name",
  "question": "Poll Question",
  "options": ["Option 1", "Option 2"],
  "emojis": ["🇦", "🇧"],
  "server_id": "123...",
  "channel_id": "456...",
  "open_time": "2024-01-01T12:00:00+00:00",
  "close_time": "2024-01-01T13:00:00+00:00",
  "timezone": "UTC",
  "anonymous": false,
  "multiple_choice": false,
  "ping_role_enabled": false,
  "ping_role_id": null,
  "creator_id": "789...",
  "combination_id": 123,
  "combination_config": {
    "id": 123,
    "option_count": 3,
    "anonymous": false,
    "multiple_choice": false,
    "ping_role_enabled": false,
    "has_image": false,
    "emoji_type": "default",
    "schedule_type": "immediate",
    "timezone": "UTC"
  }
}
```

### Statistics Provided
- Total combinations generated
- Success/failure rates
- Breakdown by option count
- Breakdown by emoji type
- Breakdown by schedule type
- Performance metrics

## Integration with Test Suite

These scripts integrate with the main test suite:

```bash
# Run comprehensive poll generation as part of testing
python tests/run_tests.py --category comprehensive

# Run specific poll generation tests
pytest tests/test_poll_generation.py -v
```

## Performance Considerations

### Resource Usage
- **Memory**: Each poll combination uses minimal memory
- **Database**: Creates actual database records
- **Network**: May make Discord API calls for custom emojis
- **Time**: Full comprehensive generation can take 10-30 minutes

### Optimization Features
- Small delays between creations to avoid overwhelming the system
- Concurrent creation testing with controlled parallelism
- Dry run mode for testing without database writes
- Limit parameter to control scope

### Cleanup
- Failed polls are automatically cleaned up
- Image files are properly managed
- Database transactions are properly handled

## Troubleshooting

### Common Issues

**Bot Not Available**
```
Error: Bot instance is None
```
- Ensure Discord bot is properly configured
- Check bot token and permissions

**Database Connection Issues**
```
Error: Database connection failed
```
- Ensure database is initialized: `python -c "from polly.database import init_database; init_database()"`
- Check database file permissions

**Rate Limiting**
```
Warning: Rate limited by Discord API
```
- Increase delays between operations
- Use `--limit` parameter to reduce load

**Memory Issues**
```
Error: Out of memory
```
- Use `--limit` parameter
- Run in smaller batches
- Use `--dry-run` for testing

### Debug Mode
Enable debug logging:
```bash
export PYTHONPATH=/path/to/polly
python -c "import logging; logging.basicConfig(level=logging.DEBUG)"
python tests/generate_comprehensive_polls.py --dry-run --limit 10
```

## Contributing

When adding new poll features:

1. **Update Comprehensive Generator**:
   - Add new feature to combination matrix
   - Update edge cases
   - Add to JSON export format

2. **Update Scenario Tester**:
   - Add specific scenario for new feature
   - Include boundary testing
   - Add error condition testing

3. **Update Documentation**:
   - Add feature to this README
   - Update configuration matrix
   - Add troubleshooting notes

## Examples

### Quick Test Run
```bash
# Test 10 polls with dry run
python tests/generate_comprehensive_polls.py --dry-run --limit 10
```

### Full Comprehensive Test
```bash
# Generate all combinations (warning: creates 880+ polls)
python tests/generate_comprehensive_polls.py
```

### Specific Scenario Testing
```bash
# Test Unicode handling
python tests/poll_creation_scenarios.py --scenario unicode_stress

# Test concurrent creation
python tests/poll_creation_scenarios.py --scenario concurrent_creation
```

### Analysis and Export
```bash
# Export combinations for analysis
python tests/generate_comprehensive_polls.py --export-json --limit 100

# Analyze the generated JSON
python -c "
import json
with open('poll_combinations.json') as f:
    data = json.load(f)
    print(f'Generated {len(data)} combinations')
    option_counts = {}
    for item in data:
        count = len(item['options'])
        option_counts[count] = option_counts.get(count, 0) + 1
    print('Option count distribution:', option_counts)
"
```

This comprehensive testing approach ensures that the Polly Discord Poll Bot can handle any combination of poll configurations and edge cases that users might encounter in real-world usage.
