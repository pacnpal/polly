# Nginx Setup for Polly Discord Poll Bot

This guide explains how to set up Nginx as a reverse proxy for the Polly Discord Poll Bot running at `polly.pacnp.al`.

## Files Included

- `nginx.conf` - Production configuration with SSL/HTTPS
- `nginx-dev.conf` - Development configuration (HTTP only)

## Prerequisites

1. Nginx installed on your server
2. Domain `polly.pacnp.al` pointing to your server's IP
3. Polly app running on `localhost:8000`

## Installation Steps

### 1. Install Nginx (if not already installed)

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install nginx

# CentOS/RHEL
sudo yum install nginx
# or for newer versions:
sudo dnf install nginx
```

### 2. Copy Configuration

For development (HTTP only):
```bash
sudo cp /home/xyn0th/polly/nginx-dev.conf /etc/nginx/sites-available/polly.pacnp.al
```

For production (HTTPS):
```bash
sudo cp /home/xyn0th/polly/nginx.conf /etc/nginx/sites-available/polly.pacnp.al
```

### 3. Enable the Site

```bash
# Create symlink to enable the site
sudo ln -s /etc/nginx/sites-available/polly.pacnp.al /etc/nginx/sites-enabled/

# Remove default site (optional)
sudo rm /etc/nginx/sites-enabled/default
```

### 4. Test Configuration

```bash
sudo nginx -t
```

### 5. For Production (HTTPS Setup)

Install Certbot and get SSL certificates:

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx

# Get SSL certificate
sudo certbot --nginx -d polly.pacnp.al

# Or manually if you prefer:
sudo certbot certonly --webroot -w /var/www/html -d polly.pacnp.al
```

### 6. Set Permissions

Ensure Nginx can access the static files:

```bash
# Make sure the static directory exists and has proper permissions
chmod 755 /home/xyn0th/polly/static
chmod -R 644 /home/xyn0th/polly/static/*
```

### 7. Start/Restart Services

```bash
# Restart Nginx
sudo systemctl restart nginx

# Enable Nginx to start on boot
sudo systemctl enable nginx

# Check status
sudo systemctl status nginx
```

### 8. Start Your Polly App

Make sure your Polly app is running:

```bash
cd /home/xyn0th/polly
uv run python -m polly.main
```

## Configuration Features

### Production Configuration (`nginx.conf`)
- ✅ HTTPS with SSL termination
- ✅ HTTP to HTTPS redirect
- ✅ Security headers (HSTS, XSS protection, etc.)
- ✅ Gzip compression
- ✅ Static file serving with long cache times
- ✅ API endpoint optimization
- ✅ Error handling
- ✅ Comprehensive logging

### Development Configuration (`nginx-dev.conf`)
- ✅ HTTP only (simpler setup)
- ✅ Basic security headers
- ✅ Gzip compression
- ✅ Static file serving
- ✅ Basic logging

## Troubleshooting

### Check Nginx Status
```bash
sudo systemctl status nginx
sudo nginx -t
```

### Check Logs
```bash
# Nginx error log
sudo tail -f /var/log/nginx/error.log

# Site-specific logs
sudo tail -f /var/log/nginx/polly.pacnp.al.error.log
sudo tail -f /var/log/nginx/polly.pacnp.al.access.log
```

### Common Issues

1. **502 Bad Gateway**: Polly app is not running on port 8000
2. **403 Forbidden**: Permission issues with static files
3. **SSL Certificate errors**: Run `sudo certbot renew` to refresh certificates

### Firewall Configuration

Make sure ports 80 and 443 are open:

```bash
# UFW (Ubuntu)
sudo ufw allow 'Nginx Full'

# iptables
sudo iptables -A INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 443 -j ACCEPT
```

## Testing

1. Test HTTP (development): `curl -I http://polly.pacnp.al`
2. Test HTTPS (production): `curl -I https://polly.pacnp.al`
3. Test API: `curl -I https://polly.pacnp.al/api/polls`
4. Test static files: `curl -I https://polly.pacnp.al/static/`

## Maintenance

### SSL Certificate Renewal
Certificates will auto-renew, but you can manually renew:
```bash
sudo certbot renew
sudo systemctl reload nginx
```

### Log Rotation
Logs are automatically rotated by logrotate. Check configuration:
```bash
sudo cat /etc/logrotate.d/nginx
```
