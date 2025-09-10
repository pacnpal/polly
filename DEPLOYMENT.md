# 🚀 Polly Deployment Commands

Quick reference for deploying Polly with git pull + container updates.

## ⚡ One-Command Deployments

### Super Simple
```bash
./deploy                    # Git pull + update Polly container
./deploy --all              # Git pull + rebuild everything
```

### Make Commands  
```bash
make deploy                 # Git pull + update Polly (most common)
make deploy-all             # Git pull + rebuild all containers
make deploy-clean           # Deploy with automatic Docker image cleanup
```

### Script Options
```bash
./scripts/update.sh         # Quick update (no prompts)
./scripts/deploy.sh         # Full deployment with options
./scripts/deploy-clean.sh   # Deployment with automatic cleanup
```

## 🎯 Common Scenarios

### Production Deployment
```bash
# Standard deployment
make deploy

# Deploy specific branch
./scripts/deploy.sh --branch production

# Stash local changes and deploy
./scripts/deploy.sh --stash
```

### Development Updates
```bash
# Test local changes (no git pull)
make update

# Deploy latest from git
make deploy
```

### Emergency Deployment
```bash
# Force deployment with conflicts
./scripts/deploy.sh --force

# Full rebuild everything
make deploy-all
```

## 🔧 What Each Command Does

| Command | Git Pull | Rebuild Polly | Rebuild Redis | Cleanup | Speed |
|---------|----------|---------------|---------------|---------|--------|
| `make deploy` | ✅ | ✅ | ❌ | ❌ | Fast |
| `make deploy-clean` | ✅ | ✅ | ❌ | ✅ | Fast |
| `make deploy-all` | ✅ | ✅ | ✅ | ❌ | Slow |
| `make update` | ❌ | ✅ | ❌ | ❌ | Fastest |
| `./deploy` | ✅ | ✅ | ❌ | ❌ | Fast |

## 📋 Available Options

### `./scripts/deploy.sh` Options
- `--skip-git` - Skip git operations
- `--all` - Rebuild all containers  
- `--branch <name>` - Deploy specific branch
- `--stash` - Stash local changes first
- `--force` - Force pull with conflicts
- `--no-cleanup` - Skip Docker image cleanup
- `--aggressive-cleanup` - Deep clean (removes more images)
- `--help` - Show all options

### Examples
```bash
# Deploy development branch
./scripts/deploy.sh --branch develop

# Stash changes and deploy
./scripts/deploy.sh --stash

# Full rebuild from main branch  
./scripts/deploy.sh --all

# Deploy without git operations
./scripts/deploy.sh --skip-git

# Deploy with cleanup disabled (faster)
./scripts/deploy-clean.sh --no-cleanup

# Deploy with aggressive cleanup (more disk space freed)
./scripts/deploy-clean.sh --aggressive-cleanup
```

## 🧹 Docker Image Management

### Check Disk Usage
```bash
./scripts/docker-size.sh   # Show Docker disk usage report
make clean-images          # Clean old images and build cache
```

### Cleanup Strategies
- **Safe Cleanup**: `make clean-images` - Removes dangling images and old build cache
- **Deploy with Cleanup**: `make deploy-clean` - Automatic cleanup during deployment  
- **Aggressive Cleanup**: `./scripts/deploy-clean.sh --aggressive-cleanup` - Deep clean (slower future builds)

## 🎉 Benefits

✅ **One Command**: Git pull + container update in single command  
✅ **Preserved Cache**: Redis data stays intact during Polly updates  
✅ **Smart Defaults**: Automatically handles most common scenarios  
✅ **Safe**: Checks for uncommitted changes and conflicts  
✅ **Fast**: Only rebuilds what changed (usually just Polly)  
✅ **Flexible**: Advanced options available when needed  

Perfect for both development iteration and production deployments!
