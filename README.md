# Polly - Discord Poll Bot

A comprehensive Discord poll bot with advanced scheduling, admin-only access, and a beautiful web interface for poll management.

## Features

### 🔐 Admin-Only Access
- Only server administrators can create polls
- Discord OAuth authentication with permission verification
- Secure JWT-based web sessions

### 📊 Advanced Poll Creation
- Named polls with custom options (up to 10)
- Full-size image uploads (not tiny thumbnails)
- Rich Discord embeds with real-time vote counts
- Emoji-based voting system (🇦 🇧 🇨 🇩 🇪 🇫 🇬 🇭 🇮 🇯)
- User preferences system - remembers last used server, channel, and timezone
- Anonymous polls option to hide results until poll ends

### ⏰ Smart Scheduling
- Calendar and time picker for precise scheduling
- Automatic poll opening and closing
- Timezone-aware scheduling system
- Background job processing with APScheduler

### 🌐 Web Dashboard
- Beautiful Bootstrap-based interface with HTMX (NO JavaScript)
- Create and manage polls from the web
- Live updates without page refreshes
- View poll history and results
- Responsive design for mobile and desktop

### 🕐 Timezone Support
- US/Eastern timezone as default
- Poll messages display times in selected timezone
- Timezone-aware scheduling system
- Support for major world timezones

### ⚡ Lightning Fast
- Built with modern Python stack (FastAPI + discord.py)
- HTMX for dynamic UI without JavaScript
- SQLite database for zero-configuration setup
- Single application deployment
- Managed with `uv` for blazing fast package management

## Quick Start

### Prerequisites
- Python 3.11+
- Discord Bot Token
- Discord Application Client ID & Secret

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd polly
   ```

2. **Install dependencies with uv**
   ```bash
   uv sync
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your Discord bot credentials
   ```

4. **Run the application**
   ```bash
   uv run python -m polly.main
   ```

5. **Access the web interface**
   - Open http://localhost:8000
   - Login with Discord
   - Start creating polls!

## Discord Bot Setup

1. **Create Discord Application**
   - Go to https://discord.com/developers/applications
   - Click "New Application"
   - Give it a name (e.g., "Polly")

2. **Create Bot**
   - Go to "Bot" section
   - Click "Add Bot"
   - Copy the bot token to your `.env` file

3. **Configure OAuth2**
   - Go to "OAuth2" section
   - Add redirect URI: `http://localhost:8000/auth/callback`
   - Copy Client ID and Client Secret to your `.env` file

4. **Invite Bot to Server**
   - Go to "OAuth2" > "URL Generator"
   - Select scopes: `bot`, `applications.commands`
   - Select permissions: `Send Messages`, `Add Reactions`, `Use Slash Commands`
   - Use generated URL to invite bot

## Environment Configuration

Create a `.env` file with the following variables:

```env
# Discord Bot Configuration
DISCORD_TOKEN=your_discord_bot_token_here
DISCORD_CLIENT_ID=your_discord_client_id_here
DISCORD_CLIENT_SECRET=your_discord_client_secret_here

# Web Application Configuration
DISCORD_REDIRECT_URI=http://localhost:8000/auth/callback
SECRET_KEY=your-secret-key-for-jwt-tokens-change-this
BASE_URL=http://localhost:8000
```

## Usage

### Discord Commands

- `/poll` - Create a quick poll with up to 5 options
  - Example: `/poll question:"What's your favorite color?" option1:"Red" option2:"Blue" option3:"Green"`

### Web Interface

1. **Login** - Authenticate with Discord OAuth
2. **Dashboard** - View and manage your polls with live statistics
3. **Create Poll** - Use the web form for advanced options:
   - Named polls with custom scheduling
   - Image uploads (up to 8MB)
   - Server and channel selection
   - Anonymous poll option
   - Timezone selection
4. **Poll Management** - Full CRUD operations:
   - Edit scheduled polls before they start
   - View detailed poll results and analytics
   - Manually close active polls
   - Delete polls (with automatic image cleanup)

### Poll Features

- **Live Vote Updates** - Poll embeds update in real-time as users vote
- **Smart User Preferences** - Remembers your last used server, channel, and timezone
- **Automatic Messaging** - Sends completion message to the same channel when polls end
- **Comprehensive Logging** - Full audit trail of all poll operations
- **Image Management** - Automatic cleanup of uploaded images when polls are deleted
- **Status-Based Actions** - Different management options based on poll status (scheduled/active/closed)
- **Admin Only** - Only server administrators can create and manage polls

## Architecture

### Technology Stack
- **Backend**: Python 3.11+, FastAPI, discord.py
- **Database**: SQLite with SQLAlchemy ORM
- **Frontend**: Bootstrap 5, HTMX (NO JavaScript)
- **Scheduling**: APScheduler
- **Authentication**: Discord OAuth2 + JWT
- **Package Management**: uv

### Project Structure
```
polly/
├── polly/                  # Main package
│   ├── __init__.py
│   ├── main.py            # Application entry point
│   ├── database.py        # Database models
│   ├── auth.py            # Authentication logic
│   └── discord_utils.py   # Discord bot utilities
├── templates/             # HTML templates
│   ├── index.html         # Landing page
│   ├── dashboard.html     # Admin dashboard (legacy)
│   ├── dashboard_htmx.html # HTMX-powered dashboard
│   └── htmx/              # HTMX partial templates
│       ├── polls.html     # Poll listing
│       ├── stats.html     # Dashboard stats
│       ├── create_form.html # Poll creation form
│       └── servers.html   # Server selection
├── static/uploads/        # Image storage
├── cline_docs/           # Project documentation
├── pyproject.toml        # Dependencies and config
├── .env.example          # Environment template
└── README.md             # This file
```

## Development

### Package Management with uv

This project uses [uv](https://docs.astral.sh/uv/) for blazing fast Python package management. Here are the essential commands:

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install all dependencies (creates virtual environment automatically)
uv sync

# Add a new dependency
uv add package-name

# Add a development dependency
uv add --dev package-name

# Remove a dependency
uv remove package-name

# Update all dependencies
uv sync --upgrade

# Run commands in the virtual environment
uv run python -m polly.main
uv run uvicorn polly.main:app --reload

# Activate the virtual environment manually (optional)
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate     # Windows
```

### Running in Development
```bash
# Install dependencies
uv sync

# Run with auto-reload
uv run uvicorn polly.main:app --reload --host 0.0.0.0 --port 8000

# Or run the main module directly
uv run python -m polly.main
```

### Database Management
The SQLite database is automatically created and initialized on first run. No migrations needed for the MVP.

### Adding Features
1. Update database models in `polly/database.py`
2. Add API endpoints in `polly/main.py`
3. Update web interface in `templates/`
4. Test with Discord bot commands

### Development Workflow
```bash
# Start development server
uv run uvicorn polly.main:app --reload

# Run tests (when available)
uv run pytest

# Format code
uv run black polly/
uv run isort polly/

# Type checking
uv run mypy polly/
```

## Deployment

### Docker Deployment (Recommended)

#### Option A — Prebuilt image from GitHub Container Registry (fastest)

Each push to `main` automatically publishes a fresh image to the GitHub Container Registry. You can run Polly without cloning the source or building anything locally.

1. **Create your working directory and configure environment**
   ```bash
   mkdir polly && cd polly
   curl -o .env https://raw.githubusercontent.com/pacnpal/polly/main/.env.example
   # Edit .env with your Discord bot credentials
   ```

2. **Create a `docker-compose.yml`** that references the prebuilt image:
   ```yaml
   services:
     redis:
       image: redis:7-alpine
       container_name: polly-redis
       command: redis-server --requirepass ${REDIS_PASSWORD:?Set REDIS_PASSWORD in .env}
       volumes:
         - redis_data:/data
       restart: unless-stopped
       healthcheck:
         test: ["CMD", "redis-cli", "--no-auth-warning", "-a", "${REDIS_PASSWORD}", "ping"]
         interval: 30s
         timeout: 10s
         retries: 3
       networks:
         - polly-network

     polly:
       image: ghcr.io/pacnpal/polly:main   # prebuilt image — no build step needed
       container_name: polly-app
       ports:
         - "127.0.0.1:8000:8000"
       env_file:
         - .env
       environment:
         - DISCORD_TOKEN=${DISCORD_TOKEN}
         - DISCORD_CLIENT_ID=${DISCORD_CLIENT_ID}
         - DISCORD_CLIENT_SECRET=${DISCORD_CLIENT_SECRET}
         - DISCORD_REDIRECT_URI=${DISCORD_REDIRECT_URI}
         - SECRET_KEY=${SECRET_KEY}
         - REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379
         - REDIS_HOST=redis
         - REDIS_PORT=6379
         - REDIS_PASSWORD=${REDIS_PASSWORD}
       volumes:
         - ./db:/app/db
         - ./data:/app/data
         - ./logs:/app/logs
         - ./static/uploads:/app/static/uploads   # user-uploaded poll images
         - ./static/avatars:/app/static/avatars   # cached Discord avatars
         - ./static/images:/app/static/images     # generated poll images
         - ./static/polls:/app/static/polls       # static closed-poll pages
       restart: unless-stopped
       depends_on:
         redis:
           condition: service_healthy
       healthcheck:
         test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
         interval: 30s
         timeout: 10s
         retries: 3
         start_period: 30s
       networks:
         - polly-network
       user: "1000:1000"

   volumes:
     redis_data:

   networks:
     polly-network:
       driver: bridge
   ```

3. **Prepare host directories** (required when using `user: "1000:1000"`):
   ```bash
   mkdir -p db data logs static/uploads static/avatars static/images static/polls
   sudo chown -R 1000:1000 db data logs static
   ```

4. **Pull and start**
   ```bash
   docker compose pull
   docker compose up -d
   ```

To pin to a specific release instead of always following `main`, replace the tag:
```yaml
image: ghcr.io/pacnpal/polly:v1.2.3   # replace with a real semver tag
```

---

#### Option B — Build from source

1. **Clone and Configure**
   ```bash
   git clone <repository-url>
   cd polly
   cp .env.example .env
   # Edit .env with your Discord bot credentials
   ```

2. **Build and Run with Docker Compose**
   ```bash
   docker-compose up -d
   ```

3. **Access the Application**
   - Web interface: http://localhost:8000
   - With nginx proxy: http://localhost (port 80)

The Docker setup includes:
- Polly application container
- Nginx reverse proxy (optional)
- Automatic restarts
- Health checks
- Volume mounts for data persistence

### Single Server Deployment
1. **Setup Environment**
   ```bash
   # On your server
   git clone <repository-url>
   cd polly
   uv sync
   cp .env.example .env
   # Configure .env with production values
   ```

2. **Create Systemd Service**
   ```ini
   # /etc/systemd/system/polly.service
   [Unit]
   Description=Polly Discord Poll Bot
   After=network.target

   [Service]
   Type=simple
   User=polly
   WorkingDirectory=/path/to/polly
   ExecStart=/path/to/polly/.venv/bin/python -m polly.main
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```

3. **Start Service**
   ```bash
   sudo systemctl enable polly
   sudo systemctl start polly
   ```

### Nginx Configuration (Optional)
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /static/ {
        alias /path/to/polly/static/;
    }
}
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support, please:
1. Check the documentation
2. Search existing issues
3. Create a new issue with detailed information

---

**Built with ❤️ for the Discord community**
