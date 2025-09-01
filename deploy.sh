#!/bin/bash

# Polly Discord Bot - Hetzner Deployment Script
# Run this on your Hetzner Ubuntu server

set -e

echo "🚀 Deploying Polly Discord Bot to Hetzner..."

# Update system
echo "📦 Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install Docker and Docker Compose
echo "🐳 Installing Docker..."
sudo apt install -y apt-transport-https ca-certificates curl software-properties-common
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Add user to docker group
sudo usermod -aG docker $USER

# Install Git
echo "📥 Installing Git..."
sudo apt install -y git

# Clone repository
echo "📂 Cloning Polly repository..."
if [ -d "polly" ]; then
    cd polly
    git pull
else
    git clone https://github.com/pacnpal/polly.git
    cd polly
fi

# Create environment file
echo "⚙️ Setting up environment..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "🔧 Please edit .env file with your Discord bot credentials:"
    echo "   nano .env"
    echo ""
    echo "Required variables:"
    echo "   DISCORD_TOKEN=your_bot_token"
    echo "   DISCORD_CLIENT_ID=your_client_id"
    echo "   DISCORD_CLIENT_SECRET=your_client_secret"
    echo "   DISCORD_REDIRECT_URI=https://your-domain.com/auth/callback"
    echo "   SECRET_KEY=your_random_secret_key"
    echo ""
    read -p "Press Enter after editing .env file..."
fi

# Create data directories
echo "📁 Creating data directories..."
mkdir -p data static/uploads

# Install Certbot for SSL
echo "🔒 Installing Certbot for SSL..."
sudo apt install -y certbot

# Get domain name
echo ""
read -p "Enter your domain name (e.g., polly.yourdomain.com): " DOMAIN_NAME

# Update nginx config with domain
echo "🌐 Updating nginx configuration..."
sed -i "s/your-domain.com/$DOMAIN_NAME/g" nginx.conf

# Get SSL certificate
echo "🔐 Getting SSL certificate..."
sudo certbot certonly --standalone -d $DOMAIN_NAME

# Build and start services
echo "🏗️ Building and starting services..."
docker compose build
docker compose up -d

# Setup auto-renewal for SSL
echo "🔄 Setting up SSL auto-renewal..."
echo "0 12 * * * /usr/bin/certbot renew --quiet && docker compose restart nginx" | sudo crontab -

# Setup log rotation
echo "📝 Setting up log rotation..."
sudo tee /etc/logrotate.d/polly > /dev/null <<EOF
/var/lib/docker/containers/*/*-json.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 644 root root
}
EOF

# Show status
echo ""
echo "✅ Deployment complete!"
echo ""
echo "🌐 Your Polly bot is now running at: https://$DOMAIN_NAME"
echo ""
echo "📊 Check status:"
echo "   docker compose ps"
echo "   docker compose logs -f polly"
echo ""
echo "🔧 Manage services:"
echo "   docker compose restart"
echo "   docker compose stop"
echo "   docker compose up -d"
echo ""
echo "📱 Don't forget to:"
echo "   1. Update Discord OAuth redirect URI to: https://$DOMAIN_NAME/auth/callback"
echo "   2. Invite your bot to Discord servers"
echo "   3. Test the web interface and Discord commands"
echo ""
