# 🚀 Polly Deployment Guide - Hetzner + Docker + GitHub

Deploy Polly Discord Bot to Hetzner Cloud in minutes!

## Prerequisites

1. **Hetzner Cloud Server** (Ubuntu 22.04 LTS recommended)
2. **Domain name** pointed to your server IP
3. **Discord Bot** configured with tokens
4. **GitHub repository** with your Polly code

## Quick Deployment

### 1. Server Setup

```bash
# SSH into your Hetzner server
ssh root@your-server-ip

# Run the deployment script
curl -sSL https://raw.githubusercontent.com/pacnpal/polly/main/deploy.sh | bash
```

### 2. Manual Deployment (Alternative)

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install Git
sudo apt install -y git

# Clone repository
git clone https://github.com/pacnpal/polly.git
cd polly

# Configure environment
cp .env.example .env
nano .env  # Edit with your Discord credentials

# Deploy with Docker
docker compose up -d
```

## Environment Configuration

Edit `.env` file with your Discord bot credentials:

```env
DISCORD_TOKEN=your_discord_bot_token_here
DISCORD_CLIENT_ID=your_discord_client_id_here
DISCORD_CLIENT_SECRET=your_discord_client_secret_here
DISCORD_REDIRECT_URI=https://your-domain.com/auth/callback
SECRET_KEY=your-random-secret-key-here
```

## SSL Certificate Setup

```bash
# Install Certbot
sudo apt install -y certbot

# Get SSL certificate
sudo certbot certonly --standalone -d your-domain.com

# Update nginx config
sed -i 's/your-domain.com/your-actual-domain.com/g' nginx.conf

# Restart services
docker compose restart
```

## Discord Bot Setup

1. **Create Discord Application**
   - Go to https://discord.com/developers/applications
   - Create new application named "Polly"

2. **Create Bot**
   - Go to "Bot" section
   - Create bot and copy token to `.env`

3. **Configure OAuth2**
   - Go to "OAuth2" section
   - Add redirect URI: `https://your-domain.com/auth/callback`
   - Copy Client ID and Secret to `.env`

4. **Invite Bot**
   - Go to "OAuth2" > "URL Generator"
   - Select scopes: `bot`, `applications.commands`
   - Select permissions: `Send Messages`, `Add Reactions`, `Use Slash Commands`
   - Use generated URL to invite bot to servers

## Management Commands

```bash
# Check status
docker compose ps
docker compose logs -f polly

# Restart services
docker compose restart

# Update deployment
git pull
docker compose build
docker compose up -d

# View logs
docker compose logs -f polly
docker compose logs -f nginx

# Stop services
docker compose down
```

## Monitoring & Maintenance

### Health Checks
```bash
# Check if services are running
curl -f http://localhost:8000/
curl -f https://your-domain.com/

# Check Docker containers
docker compose ps
```

### Log Management
```bash
# View real-time logs
docker compose logs -f

# View specific service logs
docker compose logs polly
docker compose logs nginx
```

### SSL Certificate Renewal
```bash
# Manual renewal
sudo certbot renew

# Auto-renewal is set up via cron job
sudo crontab -l
```

### Backup Database
```bash
# Backup SQLite database
cp data/polly.db data/polly.db.backup.$(date +%Y%m%d)

# Backup uploaded images
tar -czf uploads-backup-$(date +%Y%m%d).tar.gz static/uploads/
```

## Troubleshooting

### Common Issues

1. **Bot not responding**
   ```bash
   docker compose logs polly
   # Check Discord token in .env
   ```

2. **Web interface not accessible**
   ```bash
   docker compose logs nginx
   # Check domain DNS settings
   # Verify SSL certificate
   ```

3. **Database errors**
   ```bash
   # Recreate database
   docker compose down
   rm -f data/polly.db
   docker compose up -d
   ```

4. **Permission denied errors**
   ```bash
   # Fix file permissions
   sudo chown -R $USER:$USER .
   chmod +x deploy.sh
   ```

### Performance Optimization

1. **Enable Docker logging limits**
   ```bash
   # Add to docker-compose.yml
   logging:
     driver: "json-file"
     options:
       max-size: "10m"
       max-file: "3"
   ```

2. **Monitor resource usage**
   ```bash
   docker stats
   htop
   df -h
   ```

## Security Considerations

1. **Firewall Setup**
   ```bash
   sudo ufw allow 22    # SSH
   sudo ufw allow 80    # HTTP
   sudo ufw allow 443   # HTTPS
   sudo ufw enable
   ```

2. **Regular Updates**
   ```bash
   # Update system packages
   sudo apt update && sudo apt upgrade -y
   
   # Update Docker images
   docker compose pull
   docker compose up -d
   ```

3. **Secure Environment Variables**
   - Never commit `.env` file to Git
   - Use strong, random SECRET_KEY
   - Rotate Discord tokens periodically

## Scaling & High Availability

For high-traffic deployments:

1. **Load Balancer** - Use Hetzner Load Balancer
2. **Database** - Migrate to PostgreSQL
3. **File Storage** - Use object storage for uploads
4. **Monitoring** - Add Prometheus + Grafana
5. **Backup** - Automated database backups

## Support

- **Documentation**: Check README.md
- **Issues**: GitHub Issues
- **Logs**: `docker compose logs -f polly`

---

**🎉 Your Polly Discord Bot is now deployed and ready to use!**

Visit `https://your-domain.com` to access the web interface and start creating polls!
