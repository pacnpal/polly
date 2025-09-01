#!/bin/bash

# Polly Deployment Script
# This script sets up Nginx configuration and systemd service for Polly

set -e

echo "🚀 Deploying Polly Discord Poll Bot..."

# Configuration
DOMAIN="polly.pacnp.al"
APP_DIR="/home/xyn0th/polly"
NGINX_SITES_AVAILABLE="/etc/nginx/sites-available"
NGINX_SITES_ENABLED="/etc/nginx/sites-enabled"
SYSTEMD_DIR="/etc/systemd/system"

# Check if running as root for system operations
if [[ $EUID -eq 0 ]]; then
    echo "⚠️  Running as root. This script will set up system services."
    SUDO=""
else
    echo "ℹ️  Running as regular user. Will use sudo for system operations."
    SUDO="sudo"
fi

# Create static directory if it doesn't exist
echo "📁 Creating static directory..."
mkdir -p "$APP_DIR/static"
mkdir -p "$APP_DIR/templates"

# Ask user which configuration to use
echo ""
echo "Which configuration would you like to deploy?"
echo "1) Development (HTTP only)"
echo "2) Production (HTTPS with SSL)"
read -p "Enter choice [1-2]: " config_choice

case $config_choice in
    1)
        CONFIG_FILE="nginx-dev.conf"
        echo "📝 Using development configuration (HTTP only)"
        ;;
    2)
        CONFIG_FILE="nginx.conf"
        echo "📝 Using production configuration (HTTPS)"
        ;;
    *)
        echo "❌ Invalid choice. Exiting."
        exit 1
        ;;
esac

# Copy Nginx configuration
echo "📋 Copying Nginx configuration..."
$SUDO cp "$APP_DIR/$CONFIG_FILE" "$NGINX_SITES_AVAILABLE/$DOMAIN"

# Enable the site
echo "🔗 Enabling Nginx site..."
$SUDO ln -sf "$NGINX_SITES_AVAILABLE/$DOMAIN" "$NGINX_SITES_ENABLED/$DOMAIN"

# Test Nginx configuration
echo "✅ Testing Nginx configuration..."
$SUDO nginx -t

# Set up systemd service
echo "⚙️  Setting up systemd service..."
$SUDO cp "$APP_DIR/polly.service" "$SYSTEMD_DIR/polly.service"

echo ""
echo "⚠️  IMPORTANT: Edit the systemd service file to add your actual Discord token:"
echo "   $SUDO nano $SYSTEMD_DIR/polly.service"
echo ""
read -p "Have you updated the Discord token in the service file? [y/N]: " token_updated

if [[ ! $token_updated =~ ^[Yy]$ ]]; then
    echo "⏸️  Please update the Discord token in the service file and run this script again."
    echo "   $SUDO nano $SYSTEMD_DIR/polly.service"
    exit 1
fi

# Reload systemd and start services
echo "🔄 Reloading systemd daemon..."
$SUDO systemctl daemon-reload

echo "🚀 Starting Polly service..."
$SUDO systemctl enable polly
$SUDO systemctl start polly

echo "🔄 Restarting Nginx..."
$SUDO systemctl restart nginx

# Set up SSL certificates if production
if [[ $config_choice -eq 2 ]]; then
    echo ""
    echo "🔒 SSL Certificate Setup"
    echo "To complete the HTTPS setup, run:"
    echo "   $SUDO apt install certbot python3-certbot-nginx"
    echo "   $SUDO certbot --nginx -d $DOMAIN"
    echo ""
fi

# Check service status
echo "🏥 Checking service status..."
echo ""
echo "Polly service status:"
$SUDO systemctl status polly --no-pager -l

echo ""
echo "Nginx status:"
$SUDO systemctl status nginx --no-pager -l

echo ""
echo "✅ Deployment complete!"
echo ""
echo "🌐 Your Polly bot should now be accessible at:"
if [[ $config_choice -eq 1 ]]; then
    echo "   http://$DOMAIN"
else
    echo "   https://$DOMAIN (after SSL setup)"
fi
echo ""
echo "📊 Useful commands:"
echo "   Check logs: $SUDO journalctl -u polly -f"
echo "   Restart app: $SUDO systemctl restart polly"
echo "   Restart nginx: $SUDO systemctl restart nginx"
echo "   Check nginx config: $SUDO nginx -t"
