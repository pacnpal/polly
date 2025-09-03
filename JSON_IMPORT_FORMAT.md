# Poll JSON Import Format

This document describes the JSON format for importing polls into Polly.

## Required Fields

- **name** (string): The name/title of the poll
- **question** (string): The poll question
- **options** (array of strings): List of poll options (2-10 options allowed)

## Optional Fields

- **emojis** (array of strings): Custom emojis for each option (must match number of options)
- **server_id** (string): Discord server ID where the poll will be posted
- **channel_id** (string): Discord channel ID where the poll will be posted
- **multiple_choice** (boolean): Allow multiple selections (default: false)
- **anonymous** (boolean): Hide voter identities (default: false)
- **role_ping** (string): Role to ping when poll is posted (e.g., "@everyone", "@here")
- **image_message_text** (string): Custom message text for the poll image
- **scheduled_date** (string): Date to post the poll (YYYY-MM-DD format)
- **scheduled_time** (string): Time to post the poll (HH:MM format, 24-hour)
- **timezone** (string): Timezone for scheduling (e.g., "US/Eastern", "UTC")
- **description** (string): Additional description for the poll
- **metadata** (object): Custom metadata fields for organization

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

### Full Featured Poll
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
  "server_id": "123456789012345678",
  "channel_id": "987654321098765432",
  "multiple_choice": false,
  "anonymous": false,
  "role_ping": "@everyone",
  "image_message_text": "Please vote for your preferred meeting time! 🗳️",
  "scheduled_date": "2025-01-15",
  "scheduled_time": "09:00",
  "timezone": "US/Eastern",
  "description": "This poll will help us determine the best time for our weekly team meetings.",
  "metadata": {
    "created_by": "Team Lead",
    "department": "Engineering",
    "priority": "high"
  }
}
```

## Validation Rules

1. **Options**: Must have 2-10 options
2. **Emojis**: If provided, must match the number of options exactly
3. **Server/Channel IDs**: Must be valid Discord snowflake IDs (18-19 digits)
4. **Scheduling**: If scheduled_date is provided, scheduled_time is required
5. **Timezone**: Must be a valid timezone identifier
6. **File Size**: JSON file must be under 1MB
7. **Encoding**: File must be valid UTF-8 encoded JSON

## Error Handling

The import system provides detailed error messages for:
- Invalid JSON syntax
- Missing required fields
- Invalid field values
- Validation failures
- Discord server/channel verification issues

## Usage

1. Create a JSON file following the format above
2. Use the import feature in the Polly web interface
3. Upload your JSON file
4. Review the parsed poll data
5. Submit to create the poll

The system will validate all fields and provide feedback before creating the poll.
