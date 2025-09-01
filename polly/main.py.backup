"""
Polly Main Application
Discord bot + FastAPI web server with admin-only poll creation.
"""

import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional
import uuid

import discord
from discord.ext import commands
from fastapi import FastAPI, Request, Depends, HTTPException, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
import uvicorn
from dotenv import load_dotenv

from .database import init_database, get_db_session, Poll, Vote, POLL_EMOJIS
from .auth import (
    is_admin, save_user_to_db, get_discord_oauth_url, exchange_code_for_token,
    get_discord_user, create_access_token, require_auth, DiscordUser
)

# Load environment variables
load_dotenv()

# Configuration
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN environment variable is required")

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize database
init_database()

# Create directories
os.makedirs("static/uploads", exist_ok=True)
os.makedirs("templates", exist_ok=True)

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.reactions = True

bot = commands.Bot(command_prefix='!', intents=intents)

# FastAPI setup
app = FastAPI(title="Polly - Discord Poll Bot", version="0.1.0")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Scheduler for poll timing
scheduler = AsyncIOScheduler()


@bot.event
async def on_ready():
    """Bot ready event"""
    logger.info(f'{bot.user} has connected to Discord!')

    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} command(s)")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")


@bot.tree.command(name="poll", description="Create a quick poll")
async def create_poll_command(
    interaction: discord.Interaction,
    question: str,
    option1: str,
    option2: str,
    option3: str = None,
    option4: str = None,
    option5: str = None
):
    """Create a poll via Discord slash command"""
    # Check if user has admin permissions
    if not interaction.user.guild_permissions.administrator and not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message(
            "❌ You need Administrator or Manage Server permissions to create polls.",
            ephemeral=True
        )
        return

    # Collect options
    options = [option1, option2]
    for opt in [option3, option4, option5]:
        if opt:
            options.append(opt)

    if len(options) > 10:
        await interaction.response.send_message(
            "❌ Maximum 10 poll options allowed.",
            ephemeral=True
        )
        return

    # Create poll in database
    db = get_db_session()
    try:
        poll = Poll(
            name=f"Quick Poll - {question[:50]}",
            question=question,
            options=options,
            server_id=str(interaction.guild_id),
            channel_id=str(interaction.channel_id),
            creator_id=str(interaction.user.id),
            open_time=datetime.utcnow(),
            close_time=datetime.utcnow() + timedelta(hours=24),
            status="active"
        )
        db.add(poll)
        db.commit()
        db.refresh(poll)

        # Create embed
        embed = discord.Embed(
            title=f"📊 {poll.name}",
            description=question,
            color=0x00ff00,
            timestamp=datetime.utcnow()
        )

        # Add options
        option_text = ""
        for i, option in enumerate(options):
            emoji = POLL_EMOJIS[i]
            option_text += f"{emoji} {option}\n"

        embed.add_field(name="Options", value=option_text, inline=False)
        embed.add_field(name="Votes", value="0 votes", inline=True)
        embed.add_field(name="Closes", value="<t:{}:R>".format(
            int(poll.close_time.timestamp())), inline=True)
        embed.set_footer(text=f"Poll ID: {poll.id}")

        await interaction.response.send_message(embed=embed)

        # Get the message and add reactions
        message = await interaction.original_response()
        poll.message_id = str(message.id)
        db.commit()

        # Add reaction emojis
        for i in range(len(options)):
            await message.add_reaction(POLL_EMOJIS[i])

        # Schedule poll closure
        scheduler.add_job(
            close_poll,
            DateTrigger(run_date=poll.close_time),
            args=[poll.id],
            id=f"close_poll_{poll.id}"
        )

    except Exception as e:
        logger.error(f"Error creating poll: {e}")
        await interaction.followup.send("❌ Error creating poll. Please try again.", ephemeral=True)
    finally:
        db.close()


@bot.event
async def on_reaction_add(reaction, user):
    """Handle poll voting via reactions"""
    if user.bot:
        return

    # Check if this is a poll message
    db = get_db_session()
    try:
        poll = db.query(Poll).filter(Poll.message_id ==
                                     str(reaction.message.id)).first()
        if not poll or poll.status != "active":
            return

        # Check if emoji is valid poll option
        if str(reaction.emoji) not in POLL_EMOJIS:
            return

        option_index = POLL_EMOJIS.index(str(reaction.emoji))
        if option_index >= len(poll.options):
            return

        # Check if user already voted
        existing_vote = db.query(Vote).filter(
            Vote.poll_id == poll.id,
            Vote.user_id == str(user.id)
        ).first()

        if existing_vote:
            # Update existing vote
            existing_vote.option_index = option_index
            existing_vote.voted_at = datetime.utcnow()
        else:
            # Create new vote
            vote = Vote(
                poll_id=poll.id,
                user_id=str(user.id),
                option_index=option_index
            )
            db.add(vote)

        db.commit()

        # Update poll embed with new results
        await update_poll_message(poll.id)

    except Exception as e:
        logger.error(f"Error handling vote: {e}")
    finally:
        db.close()


async def update_poll_message(poll_id: int):
    """Update poll message with current results"""
    db = get_db_session()
    try:
        poll = db.query(Poll).filter(Poll.id == poll_id).first()
        if not poll or not poll.message_id:
            return

        # Get the message
        channel = bot.get_channel(int(poll.channel_id))
        if not channel:
            return

        try:
            message = await channel.fetch_message(int(poll.message_id))
        except discord.NotFound:
            return

        # Get results
        results = poll.get_results()
        total_votes = poll.get_total_votes()

        # Create updated embed
        embed = discord.Embed(
            title=f"📊 {poll.name}",
            description=poll.question,
            color=0x00ff00 if poll.status == "active" else 0xff0000,
            timestamp=datetime.utcnow()
        )

        # Add options with vote counts
        option_text = ""
        for i, option in enumerate(poll.options):
            emoji = POLL_EMOJIS[i]
            votes = results.get(i, 0)
            percentage = (votes / total_votes * 100) if total_votes > 0 else 0
            option_text += f"{emoji} {option} - {votes} votes ({percentage:.1f}%)\n"

        embed.add_field(name="Results", value=option_text, inline=False)
        embed.add_field(name="Total Votes", value=str(
            total_votes), inline=True)

        if poll.status == "active":
            embed.add_field(name="Closes", value="<t:{}:R>".format(
                int(poll.close_time.timestamp())), inline=True)
        else:
            embed.add_field(name="Status", value="Closed", inline=True)

        embed.set_footer(text=f"Poll ID: {poll.id}")

        await message.edit(embed=embed)

    except Exception as e:
        logger.error(f"Error updating poll message: {e}")
    finally:
        db.close()


async def close_poll(poll_id: int):
    """Close a poll and update the message"""
    db = get_db_session()
    try:
        poll = db.query(Poll).filter(Poll.id == poll_id).first()
        if poll:
            poll.status = "closed"
            db.commit()
            await update_poll_message(poll_id)
            logger.info(f"Closed poll {poll_id}")
    except Exception as e:
        logger.error(f"Error closing poll {poll_id}: {e}")
    finally:
        db.close()

# Web routes


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/login")
async def login():
    """Redirect to Discord OAuth"""
    oauth_url = get_discord_oauth_url()
    return RedirectResponse(url=oauth_url)


@app.get("/auth/callback")
async def auth_callback(code: str):
    """Handle Discord OAuth callback"""
    try:
        # Exchange code for token
        token_data = await exchange_code_for_token(code)
        access_token = token_data["access_token"]

        # Get user info
        discord_user = await get_discord_user(access_token)

        # Save user to database
        save_user_to_db(discord_user)

        # Create JWT token
        jwt_token = create_access_token(discord_user)

        # Redirect to dashboard with token
        response = RedirectResponse(url="/dashboard")
        response.set_cookie(key="access_token", value=jwt_token, httponly=True)
        return response

    except Exception as e:
        logger.error(f"Auth callback error: {e}")
        return HTMLResponse("Authentication failed", status_code=400)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, current_user: DiscordUser = Depends(require_auth)):
    """User dashboard"""
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": current_user
    })


@app.get("/api/polls")
async def get_polls(current_user: DiscordUser = Depends(require_auth)):
    """Get user's polls"""
    db = get_db_session()
    try:
        polls = db.query(Poll).filter(Poll.creator_id == current_user.id).all()
        return [
            {
                "id": poll.id,
                "name": poll.name,
                "question": poll.question,
                "status": poll.status,
                "total_votes": poll.get_total_votes(),
                "created_at": poll.created_at.isoformat()
            }
            for poll in polls
        ]
    finally:
        db.close()


async def start_bot():
    """Start the Discord bot"""
    await bot.start(DISCORD_TOKEN)


async def start_scheduler():
    """Start the job scheduler"""
    scheduler.start()
    logger.info("Scheduler started")


def run_app():
    """Run the application"""
    # Start scheduler
    asyncio.create_task(start_scheduler())

    # Start bot in background
    asyncio.create_task(start_bot())

    # Run FastAPI server
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run_app()
