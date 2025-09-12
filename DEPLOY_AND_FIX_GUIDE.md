# Deploy and Fix Existing Poll Guide

## Step 1: Deploy the Fixes to Remote Server

SSH into your remote server and navigate to your Polly project directory, then run:

```bash
# Pull the latest changes
git pull origin main

# Deploy the updated code using the quick update script
./scripts/quick-update.sh
```

This will:
- Stop the Polly container
- Rebuild it with the new fixes
- Start it back up
- Keep Redis running (no data loss)

## Step 2: Fix the Existing Closed Poll

After the deployment is complete, you have two options to fix the existing poll:

### Option A: Use the Fix Script (Recommended)

1. Copy the fix script to your remote server:
```bash
# If you're on the remote server, the script should already be there after git pull
# Make it executable
chmod +x fix_existing_poll.py
```

2. Run the fix script:
```bash
# Run the script to update existing closed polls
python fix_existing_poll.py
```

### Option B: Manual Fix via Docker

If the script doesn't work, you can run it inside the Docker container:

```bash
# Execute the fix script inside the running Polly container
docker compose exec polly python /app/fix_existing_poll.py
```

### Option C: Manual Database Fix

If you need to manually trigger the fix, you can run this command:

```bash
# Connect to the running container and run Python commands
docker compose exec polly python -c "
import asyncio
from polly.database import get_db_session, Poll
from polly.discord_bot import bot
from polly.discord_utils import update_poll_message
from sqlalchemy.orm import joinedload

async def fix_poll():
    if not bot.is_ready():
        await bot.wait_until_ready()
    
    db = get_db_session()
    try:
        poll = db.query(Poll).options(joinedload(Poll.votes)).filter(Poll.status == 'closed').first()
        if poll and poll.message_id:
            success = await update_poll_message(bot, poll)
            print(f'Poll {poll.id} update: {\"success\" if success else \"failed\"}')
        else:
            print('No closed poll with message_id found')
    finally:
        db.close()

asyncio.run(fix_poll())
"
```

## Step 3: Verify the Fix

1. Check the Discord channel where your poll was posted
2. The poll message should now show:
   - 🏁 Red color and "closed" status
   - Full results with vote counts and percentages
   - Winner announcement
   - No more reaction emojis

## Step 4: Monitor Logs

To see detailed logs of what's happening:

```bash
# Follow the Polly container logs
docker compose logs -f polly
```

Look for log messages like:
- `🔄 UPDATE MESSAGE - Starting update for poll X`
- `🏁 UPDATE MESSAGE - Poll X is closed, FORCING show_results=True`
- `✅ UPDATE MESSAGE - Successfully updated message for poll X`

## Troubleshooting

If the fix doesn't work:

1. **Check bot permissions**: Make sure the bot has permission to edit messages in the Discord channel
2. **Check message exists**: Verify the Discord message hasn't been deleted
3. **Check logs**: Look at the container logs for specific error messages
4. **Manual retry**: You can run the fix script multiple times - it's safe to run repeatedly

## What Was Fixed

The fixes ensure that:
1. When polls close, Discord messages are updated BEFORE reactions are cleared
2. Closed polls ALWAYS show results, even if they were anonymous
3. Better error handling and logging for debugging
4. Proper order of operations in the poll closure process

Your existing poll should now display the final results properly in Discord!
