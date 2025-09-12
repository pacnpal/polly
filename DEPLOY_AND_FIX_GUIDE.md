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

After the deployment is complete, you have several options to fix the existing poll:

### Option A: Use the Standalone Fix Script (Recommended)

1. Run the standalone fix script that creates its own bot connection:
```bash
# Run the script to update existing closed polls
python fix_existing_poll.py
```

Or inside Docker:
```bash
# Execute the fix script inside the running Polly container
docker compose exec polly python /app/fix_existing_poll.py
```

### Option B: Use the Simple Fix Script (While Polly is Running)

If Polly is already running, you can use the simpler script that connects to the existing bot:

```bash
# Fix all closed polls
python fix_poll_simple.py

# Or fix a specific poll by ID
python fix_poll_simple.py 1
```

Or inside Docker:
```bash
# Fix all closed polls
docker compose exec polly python /app/fix_poll_simple.py

# Or fix a specific poll by ID  
docker compose exec polly python /app/fix_poll_simple.py 1
```

### Option C: Manual Database Fix

If you need to manually trigger the fix, you can run this command:

```bash
# Connect to the running container and run Python commands
docker compose exec polly python -c "
import asyncio
from polly.database import get_db_session, Poll
from polly.discord_bot import get_bot_instance
from polly.discord_utils import update_poll_message
from sqlalchemy.orm import joinedload

async def fix_poll():
    bot = get_bot_instance()
    if not bot or not bot.is_ready():
        print('Bot not ready')
        return
    
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
