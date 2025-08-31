"""
Discord OAuth Authentication
Only allows server administrators to create polls.
"""

import os
import httpx
from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer
from jose import jwt, JWTError
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import discord
from .database import get_db_session, User

# Discord OAuth settings
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
DISCORD_REDIRECT_URI = os.getenv(
    "DISCORD_REDIRECT_URI", "http://localhost:8000/auth/callback")
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this")

# Discord API endpoints
DISCORD_API_BASE = "https://discord.com/api/v10"
DISCORD_OAUTH_URL = f"{DISCORD_API_BASE}/oauth2/authorize"
DISCORD_TOKEN_URL = f"{DISCORD_API_BASE}/oauth2/token"
DISCORD_USER_URL = f"{DISCORD_API_BASE}/users/@me"
DISCORD_GUILDS_URL = f"{DISCORD_API_BASE}/users/@me/guilds"

security = HTTPBearer(auto_error=False)


class DiscordUser:
    """Discord user with admin permissions"""

    def __init__(self, user_data: Dict[str, Any], guilds: List[Dict[str, Any]]):
        self.id = user_data["id"]
        self.username = user_data["username"]
        self.avatar = user_data.get("avatar")
        self.avatar_url = self.get_avatar_url()
        self.admin_guilds = self.get_admin_guilds(guilds)

    def get_avatar_url(self) -> Optional[str]:
        """Get Discord avatar URL"""
        if self.avatar:
            return f"https://cdn.discordapp.com/avatars/{self.id}/{self.avatar}.png"
        return None

    def get_admin_guilds(self, guilds: List[Dict[str, Any]]) -> List[str]:
        """Get list of guild IDs where user has admin permissions"""
        admin_guilds = []
        for guild in guilds:
            permissions = int(guild.get("permissions", 0))
            # Check for Administrator permission (0x8) or Manage Server (0x20)
            if permissions & (0x8 | 0x20):
                admin_guilds.append(guild["id"])
        return admin_guilds

    def can_manage_server(self, server_id: str) -> bool:
        """Check if user can manage the specified server"""
        return server_id in self.admin_guilds


def get_discord_oauth_url() -> str:
    """Generate Discord OAuth URL"""
    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify guilds"
    }

    query_string = "&".join([f"{k}={v}" for k, v in params.items()])
    return f"{DISCORD_OAUTH_URL}?{query_string}"


async def exchange_code_for_token(code: str) -> Dict[str, Any]:
    """Exchange OAuth code for access token"""
    data = {
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": DISCORD_REDIRECT_URI
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    async with httpx.AsyncClient() as client:
        response = await client.post(DISCORD_TOKEN_URL, data=data, headers=headers)

        if response.status_code != 200:
            raise HTTPException(
                status_code=400, detail="Failed to exchange code for token")

        return response.json()


async def get_discord_user(access_token: str) -> DiscordUser:
    """Get Discord user info and guilds"""
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient() as client:
        # Get user info
        user_response = await client.get(DISCORD_USER_URL, headers=headers)
        if user_response.status_code != 200:
            raise HTTPException(
                status_code=400, detail="Failed to get user info")

        user_data = user_response.json()

        # Get user guilds
        guilds_response = await client.get(DISCORD_GUILDS_URL, headers=headers)
        if guilds_response.status_code != 200:
            raise HTTPException(
                status_code=400, detail="Failed to get user guilds")

        guilds_data = guilds_response.json()

        return DiscordUser(user_data, guilds_data)


def create_access_token(user: DiscordUser) -> str:
    """Create JWT access token"""
    expire = datetime.utcnow() + timedelta(hours=24)
    to_encode = {
        "sub": user.id,
        "username": user.username,
        "admin_guilds": user.admin_guilds,
        "exp": expire
    }

    return jwt.encode(to_encode, SECRET_KEY, algorithm="HS256")


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except JWTError:
        return None


async def get_current_user(request: Request, token=Depends(security)) -> Optional[DiscordUser]:
    """Get current authenticated user"""
    if not token:
        return None

    payload = verify_token(token.credentials)
    if not payload:
        return None

    # Create DiscordUser from token payload
    user_data = {
        "id": payload["sub"],
        "username": payload["username"]
    }

    # Mock guilds data from token
    guilds_data = [{"id": guild_id, "permissions": "32"}
                   for guild_id in payload.get("admin_guilds", [])]

    return DiscordUser(user_data, guilds_data)


async def require_auth(current_user: Optional[DiscordUser] = Depends(get_current_user)) -> DiscordUser:
    """Require authentication"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return current_user


async def require_server_admin(server_id: str, current_user: DiscordUser = Depends(require_auth)) -> DiscordUser:
    """Require server admin permissions"""
    if not current_user.can_manage_server(server_id):
        raise HTTPException(
            status_code=403,
            detail=f"Admin permissions required for server {server_id}"
        )
    return current_user


def save_user_to_db(user: DiscordUser):
    """Save or update user in database"""
    db = get_db_session()
    try:
        db_user = db.query(User).filter(User.discord_id == user.id).first()

        if db_user:
            # Update existing user
            db_user.username = user.username
            db_user.avatar_url = user.avatar_url
            db_user.last_login = datetime.utcnow()
        else:
            # Create new user
            db_user = User(
                discord_id=user.id,
                username=user.username,
                avatar_url=user.avatar_url,
                last_login=datetime.utcnow()
            )
            db.add(db_user)

        db.commit()
    finally:
        db.close()


async def get_bot_guilds(bot_token: str) -> List[Dict[str, Any]]:
    """Get guilds where the bot is present"""
    headers = {"Authorization": f"Bot {bot_token}"}

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{DISCORD_API_BASE}/users/@me/guilds", headers=headers)

        if response.status_code != 200:
            return []

        return response.json()
