# Docker Setup Guide

This document explains the optimized Docker configuration for the Polly Discord Bot application.

## Overview

The Docker setup has been cleaned up and optimized for:
- Proper volume mounting for persistent data
- Efficient build caching
- Security best practices
- Development and production environments

## Files Structure

### Core Docker Files

- `Dockerfile` - Optimized multi-stage build
- `docker-compose.yml` - Production configuration with named volumes
- `docker-compose.dev.yml` - Development configuration with live code mounting
- `docker-entrypoint.sh` - Application startup script
- `.dockerignore` - Comprehensive build context exclusions

## Volume Strategy

### Production Volumes (Named Volumes)

The production setup uses Docker named volumes for data persistence:

```yaml
volumes:
  polly_db:/app/db          # Database files
  polly_data:/app/data      # Application data
  polly_logs:/app/logs      # Log files
  polly_static:/app/static  # Static files (uploads, avatars, etc.)
  redis_data:/data          # Redis persistence
```

**Benefits:**
- Data persists across container restarts
- Better performance than bind mounts
- Managed by Docker
- Portable across environments

### Development Volumes (Bind Mounts)

The development setup uses bind mounts for live code editing:

```yaml
volumes:
  # Live code mounting (read-only)
  - ./polly:/app/polly:ro
  - ./templates:/app/templates:ro
  - ./migrate_database.py:/app/migrate_database.py:ro
  - ./pyproject.toml:/app/pyproject.toml:ro
  - ./uv.lock:/app/uv.lock:ro
  
  # Persistent data (bind mounts for easy access)
  - ./db:/app/db
  - ./data:/app/data
  - ./logs:/app/logs
  - ./static:/app/static
```

**Benefits:**
- Live code reloading during development
- Easy access to logs and data files
- No need to rebuild container for code changes

## Usage

### Production Deployment

```bash
# Build and start services
docker compose up -d

# View logs
docker compose logs -f polly

# Stop services
docker compose down
```

### Development

```bash
# Build and start development environment
docker compose -f docker-compose.dev.yml up -d

# View logs with live updates
docker compose -f docker-compose.dev.yml logs -f polly

# Stop development environment
docker compose -f docker-compose.dev.yml down
```

## Security Features

### Non-Root User
- Application runs as user `polly` (UID 1000)
- Reduces security risks
- Proper file permissions

### Network Isolation
- Services communicate through dedicated Docker network
- Redis only accessible from application container
- Application only exposed to localhost

### Environment Variables
- Sensitive data passed through environment variables
- Uses `.env` file for configuration
- No secrets in Docker images

## Dockerfile Optimizations

### Layer Caching
1. Dependencies installed first (changes less frequently)
2. Application code copied last (changes more frequently)
3. Efficient use of Docker layer caching

### Build Size
- Uses Python slim image
- Excludes unnecessary files via `.dockerignore`
- Single-stage build for simplicity

### Security
- Non-root user execution
- Minimal attack surface
- No unnecessary packages

## Volume Mount Details

### What Gets Mounted

| Directory | Purpose | Production | Development |
|-----------|---------|------------|-------------|
| `/app/db` | SQLite database files | Named volume | Bind mount |
| `/app/data` | Application data | Named volume | Bind mount |
| `/app/logs` | Log files | Named volume | Bind mount |
| `/app/static` | Static files, uploads | Named volume | Bind mount |
| `/app/polly` | Application code | Built-in | Live mount (RO) |
| `/app/templates` | HTML templates | Built-in | Live mount (RO) |

### What Doesn't Get Mounted

- Python dependencies (installed in image)
- System files and configurations
- Temporary files and caches
- Build artifacts

## Troubleshooting

### Permission Issues
If you encounter permission issues:

```bash
# Fix ownership of mounted directories
sudo chown -R 1000:1000 ./db ./data ./logs ./static
```

### Volume Data Access
To access data in named volumes:

```bash
# List volumes
docker volume ls

# Inspect volume
docker volume inspect polly_polly_db

# Access volume data (create temporary container)
docker run --rm -v polly_polly_db:/data alpine ls -la /data
```

### Development Hot Reload
For development with live code changes:

1. Use `docker-compose.dev.yml`
2. Code changes are reflected immediately
3. No container rebuild required
4. Database and logs accessible in local directories

## Best Practices

1. **Use named volumes for production** - Better performance and management
2. **Use bind mounts for development** - Live code editing capability
3. **Keep sensitive data in environment variables** - Never in images
4. **Regular volume backups** - Especially for database volumes
5. **Monitor volume usage** - Clean up unused volumes periodically

## Maintenance

### Backup Volumes
```bash
# Backup database volume
docker run --rm -v polly_polly_db:/data -v $(pwd):/backup alpine tar czf /backup/db-backup.tar.gz -C /data .

# Restore database volume
docker run --rm -v polly_polly_db:/data -v $(pwd):/backup alpine tar xzf /backup/db-backup.tar.gz -C /data
```

### Clean Up
```bash
# Remove unused volumes
docker volume prune

# Remove all project volumes (DESTRUCTIVE)
docker compose down -v
