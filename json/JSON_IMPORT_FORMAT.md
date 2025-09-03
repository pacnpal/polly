# Poll JSON Import Format

This document describes the JSON format for importing polls into Polly.

## Required Fields

- **name** (string): The name/title of the poll (3-255 characters)
- **question** (string): The poll question (5-2000 characters)
- **options** (array of strings): List of poll options (2-10 options allowed, each up to 500 characters)

## Optional Fields

- **emojis** (array of strings): Custom emojis for each option (will use defaults if not provided)
- **server_id** (string): Discord server ID where the poll will be posted (leave empty to select manually)
- **channel_id** (string): Discord channel ID where the poll will be posted (leave empty to select manually)
- **multiple_choice** (boolean): Allow multiple selections (default: false)
- **anonymous** (boolean): Hide voter identities (default: false)
- **ping_role_enabled** (boolean): Enable role pinging when poll opens/closes (default: false)
- **ping_role_id** (string): Discord role ID to ping (required if ping_role_enabled is true)
- **image_message_text** (string): Custom message text for the poll image (up to 2000 characters)
- **open_time** (string): When poll opens (ISO format: YYYY-MM-DDTHH:MM)
- **close_time** (string): When poll closes (ISO format: YYYY-MM-DDTHH:MM)
- **timezone** (string): Timezone for scheduling (e.g., "US/Eastern", "UTC", defaults to "US/Eastern")

## Examples

### Simple Poll (Required Fields Only)
```json
{
  "name": "Lunch Choice",
  "question": "Where should we go for lunch today?",
  "options": [
    "Pizza Palace",
    "Burger Barn", 
    "Taco Town",
    "Salad Station"
  ]
}
```

### Standard Poll with Common Options
```json
{
  "name": "Weekly Team Meeting Poll",
  "question": "What time works best for our weekly team meeting?",
  "options": [
    "Monday 9:00 AM EST",
    "Tuesday 2:00 PM EST", 
    "Wednesday 10:00 AM EST",
    "Thursday 3:00 PM EST",
    "Friday 11:00 AM EST"
  ],
  "emojis": [
    "📅",
    "⏰", 
    "🗓️",
    "⌚",
    "📆"
  ],
  "server_id": "",
  "channel_id": "",
  "multiple_choice": false,
  "anonymous": false,
  "ping_role_enabled": false,
  "ping_role_id": "",
  "image_message_text": "Please vote for your preferred meeting time! 🗳️",
  "open_time": "2025-01-20T09:00",
  "close_time": "2025-01-20T17:00",
  "timezone": "US/Eastern"
}
```

### Full Featured Poll with All Options
```json
{
  "name": "Annual Company Retreat Planning Poll",
  "question": "Help us plan the perfect company retreat! Which location and activities would you prefer for our 2025 annual retreat?",
  "options": [
    "Mountain Resort - Hiking, Team Building, Spa Activities",
    "Beach Resort - Water Sports, Volleyball, Sunset Dinners", 
    "City Hotel - Museums, Fine Dining, Urban Exploration",
    "Countryside Lodge - Fishing, Campfires, Nature Walks",
    "Adventure Camp - Rock Climbing, Zip Lines, Obstacle Courses"
  ],
  "emojis": [
    "🏔️",
    "🏖️",
    "🏙️", 
    "🌲",
    "🧗"
  ],
  "server_id": "123456789012345678",
  "channel_id": "987654321098765432",
  "multiple_choice": true,
  "anonymous": false,
  "ping_role_enabled": true,
  "ping_role_id": "456789012345678901",
  "image_message_text": "🎉 Help us plan an amazing retreat! Your input matters - vote for your top preferences! 🎉",
  "open_time": "2025-01-20T09:00",
  "close_time": "2025-01-27T17:00",
  "timezone": "US/Eastern"
}
```

## Validation Rules

1. **Name**: Must be 3-255 characters long
2. **Question**: Must be 5-2000 characters long
3. **Options**: Must have 2-10 options, each up to 500 characters
4. **Emojis**: If provided, must match the number of options exactly
5. **Server/Channel IDs**: Must be valid Discord snowflake IDs (18-19 digits) or empty strings
6. **Scheduling**: 
   - If open_time is provided, close_time is required and must be after open_time
   - Poll must run for at least 1 minute and no more than 30 days
   - Open time must be at least 1 minute in the future
7. **Timezone**: Must be a valid timezone identifier (e.g., "US/Eastern", "UTC", "Europe/London")
8. **Role Ping**: If ping_role_enabled is true, ping_role_id is required
9. **File Requirements**: 
   - JSON file must be under 8MB
   - File must be valid UTF-8 encoded JSON
   - File must have .json extension

## Field Notes

- **server_id/channel_id**: If left empty, you'll need to select them manually in the form after import
- **open_time/close_time**: If not provided, default times will be set (next day at midnight, running for 24 hours)
- **emojis**: Can be Unicode emojis (😀) or Discord custom emoji format (<:name:id>)
- **timezone**: Defaults to "US/Eastern" if not specified
- **image_message_text**: Only used if you also upload an image with the poll

## Error Handling

The import system provides detailed, categorized error messages for:

### File Format Issues
- Invalid JSON syntax
- File encoding problems
- Missing .json extension

### Required Fields Missing
- Missing name, question, or options
- Empty required fields

### Validation Errors
- Field length violations
- Invalid date/time formats
- Invalid timezone identifiers
- Scheduling conflicts

Each error includes helpful suggestions for fixing the issue.

## Usage

1. Create a JSON file following the format above
2. Click the "Import JSON" button in the Polly web interface
3. Select your JSON file
4. Review any error messages and fix issues if needed
5. The system will parse your data and redirect to the create form
6. Review the pre-filled form and make any final adjustments
7. Submit to create the poll

The system validates all fields and provides detailed feedback before allowing poll creation.

## Common Timezone Values

- **US Timezones**: US/Eastern, US/Central, US/Mountain, US/Pacific
- **International**: UTC, Europe/London, Europe/Paris, Asia/Tokyo, Australia/Sydney
- **Full List**: Any valid IANA timezone identifier is supported

## Tips for Success

1. **Start Simple**: Begin with just the required fields and add optional ones as needed
2. **Test Your JSON**: Use a JSON validator to check syntax before importing
3. **Use Descriptive Names**: Make poll names clear and searchable
4. **Plan Your Schedule**: Consider your audience's timezone and availability
5. **Emoji Selection**: Choose emojis that relate to your options for better visual appeal
