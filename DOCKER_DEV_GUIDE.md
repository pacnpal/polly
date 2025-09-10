# 🐳 Docker Development Guide

This guide shows you how to efficiently update Polly containers without rebuilding Redis.

## 🚀 Quick Deployment Methods (Git Pull + Container Update)

### Method 1: Using Make (Recommended)
```bash
# Git pull + update Polly (most common)
make deploy

# Git pull + rebuild everything
make deploy-all

# View available commands
make help
```

### Method 2: Direct Script
```bash
# Full deployment with options
./scripts/deploy.sh

# Quick update (no prompts)
./scripts/update.sh

# Ultra-simple
./deploy
```

## ⚡ Container-Only Updates (No Git Pull)

### Method 1: Using Make
```bash
# Update only Polly container
make update

# Update all containers
make update-all
```

### Method 2: Using Scripts
```bash
# Quick container-only update
./scripts/quick-update.sh
```

### Method 3: Manual Docker Compose Commands
```bash
# Update only Polly container
docker-compose stop polly
docker-compose build --no-cache polly
docker-compose up -d

# Or in one command (less control)
docker-compose up -d --build polly
```

## 📋 Common Development Workflows

### 1. Deploying Latest Changes (Most Common)
When you want to deploy the latest code from git:
```bash
make deploy
# or
./deploy
# or
./scripts/update.sh
```
**Result**: Pulls latest code, rebuilds Polly, Redis stays running with cache intact.

### 2. Local Code Changes (Development)
When you modify code locally and want to test:
```bash
make update
# or
./scripts/quick-update.sh
```
**Result**: Only rebuilds Polly with local changes, no git operations.

### 3. Dependency Changes
When dependencies change in the repo:
```bash
make deploy     # If committed to git
# or
make update     # If local changes only
```
**Result**: Polly rebuilds with new dependencies, Redis unaffected.

### 4. Configuration Changes
When you modify `.env` or `docker-compose.yml`:
```bash
make restart  # If only config changes
# or
make deploy   # If code also changed
```

### 5. Major Updates
When you want to update everything including Redis:
```bash
make deploy-all
```

## 🔍 Monitoring & Debugging

### Check Status
```bash
make status
# or
docker-compose ps
```

### View Logs
```bash
# All logs
make logs

# Just Polly logs
make logs-polly

# Just Redis logs  
make logs-redis
```

### Health Checks
```bash
make health
# or
curl http://localhost:8000/health
```

## 🎯 Why This Works

### Container Independence
- **Redis**: Uses official `redis:7-alpine` image (no custom build needed)
- **Polly**: Custom application container (rebuilds when code changes)
- **Separate Services**: Each service can be updated independently

### Persistent Data
- **Redis Data**: Stored in `redis_data` volume (survives container recreation)
- **Database**: Stored in `./db` host directory (persists across updates)
- **Static Files**: Mounted from host (no rebuild needed)

### Smart Dependencies
```yaml
depends_on:
  redis:
    condition: service_healthy
```
Polly waits for Redis to be healthy before starting.

## ⚡ Performance Tips

### 1. Layer Optimization
The Dockerfile is structured to maximize layer caching:
- Dependencies installed before code copy
- Only rebuilds when dependencies change

### 2. Development vs Production
For development, you can mount source code:
```yaml
volumes:
  - .:/app  # Mount entire project (development only)
```

### 3. Build Context
Use `.dockerignore` to exclude unnecessary files:
```
.git
node_modules
*.md
```

## 🛠️ Troubleshooting

### Redis Connection Issues
```bash
# Check Redis health
docker-compose exec redis redis-cli ping

# Check network connectivity
docker-compose exec polly ping redis
```

### Build Issues
```bash
# Force rebuild without cache
make update
# or
docker-compose build --no-cache polly
```

### Port Conflicts
If port 8000 is in use:
```bash
# Check what's using the port
lsof -i :8000

# Or change port in docker-compose.yml
ports:
  - "127.0.0.1:8001:8000"  # Use 8001 instead
```

## 📊 Development Workflow Examples

### Production Deployment
```bash
# Deploy latest from main branch
make deploy

# Deploy from specific branch  
./scripts/deploy.sh --branch develop

# Deploy with local changes stashed
./scripts/deploy.sh --stash
```

### Development Iteration
```bash
# 1. Initial setup
docker-compose up -d

# 2. Make code changes locally
vim polly/main.py

# 3. Test local changes
make update

# 4. Verify changes
curl http://localhost:8000/health

# 5. Commit and deploy
git add . && git commit -m "fix: update"
make deploy
```

## 🎉 Benefits

✅ **Fast Updates**: Only Polly rebuilds (30-60 seconds vs 5+ minutes)  
✅ **Preserved Cache**: Redis data remains intact between updates  
✅ **Simple Commands**: One command updates what you need  
✅ **Flexible**: Can still update everything when needed  
✅ **Safe**: Health checks ensure services are ready  

This approach gives you the speed of development with the reliability of containerized deployment!
