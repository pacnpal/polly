# Poll URL Generator

A CLI script to generate one-time authenticated URLs for viewing poll dashboards.

## Usage

### Command Line Mode
```bash
# Generate URL for poll ID 21
python3 generate_poll_url.py 21

# Generate URL with custom base URL
python3 generate_poll_url.py 21 https://polly.pacnp.al
```

### Interactive Mode
```bash
# Run without arguments for interactive input
python3 generate_poll_url.py
```

## Features

- **Secure Authentication**: Uses the existing screenshot token system
- **One-Time Use**: Each URL can only be accessed once
- **Time-Limited**: URLs expire after 5 minutes
- **Full Dashboard Access**: Shows complete poll results with usernames and avatars
- **Any Poll Status**: Works with active, scheduled, or closed polls

## Security Notes

- URLs are generated using cryptographically secure tokens
- Tokens are tied to the specific poll and creator
- After viewing, the URL becomes permanently invalid
- No authentication cookies or sessions required

## Example Output

```
🚀 POLL URL GENERATOR - One-Time Authenticated URL Creator
⏰ Started at: 2025-01-10 18:54:00

🎯 Target Poll ID: 21
🌐 Base URL: https://polly.pacnp.al

🔧 POLL URL - Generating authenticated URL for poll 21...
📊 POLL URL - Found poll: 'Test Poll' (Status: closed)
✅ POLL URL - Generated authenticated URL for poll 21
🔐 POLL URL - Token expires in 5 minutes and is single-use only

================================================================================
🔗 ONE-TIME AUTHENTICATED URL:

https://polly.pacnp.al/screenshot/poll/21/dashboard?token=abc123def456...

================================================================================

⚠️  IMPORTANT NOTES:
   • This URL expires in 5 minutes
   • This URL can only be used ONCE
   • After viewing, the URL becomes invalid
   • The URL provides full access to the poll dashboard

✅ URL generated successfully!
```

## Use Cases

- Sharing poll results with external users
- Debugging poll display issues
- Creating screenshots of poll dashboards
- Providing temporary access without authentication
