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

### ⏰ Smart Scheduling
- Calendar and time picker for precise scheduling
- Automatic poll opening and closing
- Timezone-aware scheduling system
- Background job processing with APScheduler

### 🌐 Web Dashboard
- Beautiful Bootstrap-based interface
- Create and manage polls from the web
- View poll history and results
- Responsive design for mobile and desktop

### ⚡ Lightning Fast
- Built with modern Python stack (FastAPI + discord.py)
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
2. **Dashboard** - View and manage your polls
3. **Create Poll** - Use the web form for advanced options:
   - Named polls
   - Custom scheduling
   - Image uploads
   - Server selection

### Poll Features

- **Voting** - Users vote by clicking emoji reactions
- **Real-time Results** - Poll embeds update with vote counts
- **Auto-close** - Polls automatically close at scheduled time
- **Admin Only** - Only server admins can create polls

## Architecture

### Technology Stack
- **Backend**: Python 3.11+, FastAPI, discord.py
- **Database**: SQLite with SQLAlchemy ORM
- **Frontend**: Bootstrap 5, Vanilla JavaScript
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
│   └── auth.py            # Authentication logic
├── templates/             # HTML templates
│   ├── index.html         # Landing page
│   └── dashboard.html     # Admin dashboard
├── static/uploads/        # Image storage
├── cline_docs/           # Project documentation
├── pyproject.toml        # Dependencies and config
├── .env.example          # Environment template
└── README.md             # This file
```

## Development

### Running in Development
```bash
# Install dependencies
uv sync

# Run with auto-reload
uv run uvicorn polly.main:app --reload --host 0.0.0.0 --port 8000
```

### Database Management
The SQLite database is automatically created and initialized on first run. No migrations needed for the MVP.

### Adding Features
1. Update database models in `polly/database.py`
2. Add API endpoints in `polly/main.py`
3. Update web interface in `templates/`
4. Test with Discord bot commands

## Deployment

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
