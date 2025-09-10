#!/bin/bash
set -e

echo "🚀 Polly Deployment with Automatic Cleanup"
echo "==========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Parse command line arguments
SKIP_GIT=false
REBUILD_ALL=false
BRANCH="main"
STASH_CHANGES=false
FORCE_PULL=false
CLEANUP_IMAGES=true
AGGRESSIVE_CLEANUP=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-git)
            SKIP_GIT=true
            shift
            ;;
        --all)
            REBUILD_ALL=true
            shift
            ;;
        --branch|-b)
            BRANCH="$2"
            shift 2
            ;;
        --stash)
            STASH_CHANGES=true
            shift
            ;;
        --force)
            FORCE_PULL=true
            shift
            ;;
        --no-cleanup)
            CLEANUP_IMAGES=false
            shift
            ;;
        --aggressive-cleanup)
            AGGRESSIVE_CLEANUP=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo "Options:"
            echo "  --skip-git        Skip git operations, just rebuild containers"
            echo "  --all             Rebuild both Polly and Redis containers"
            echo "  --branch, -b      Specify git branch to pull (default: main)"
            echo "  --stash           Stash local changes before pulling"
            echo "  --force           Force pull even with local changes"
            echo "  --no-cleanup      Skip Docker image cleanup (faster but uses more disk)"
            echo "  --aggressive-cleanup  Remove more images and cache (use with caution)"
            echo "  --help, -h        Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                    # Pull main branch and update Polly with cleanup"
            echo "  $0 --all             # Pull and rebuild everything with cleanup"
            echo "  $0 --no-cleanup      # Deploy without cleaning up old images"
            echo "  $0 --aggressive-cleanup # Deep clean (removes more images)"
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Show disk usage before deployment
print_status "📊 Docker disk usage before deployment:"
docker system df 2>/dev/null || echo "Could not check Docker disk usage"

# Check Docker daemon
if ! docker info >/dev/null 2>&1; then
    print_error "Docker daemon is not running or not accessible"
    exit 1
fi

# Check if we're in a git repository
if [ ! -d ".git" ] && [ "$SKIP_GIT" = false ]; then
    print_error "Not in a git repository! Use --skip-git to deploy without git operations."
    exit 1
fi

# Git operations (reusing existing logic from deploy.sh)
if [ "$SKIP_GIT" = false ]; then
    print_status "📥 Updating code from git..."
    
    # Check for uncommitted changes
    if [ -n "$(git status --porcelain)" ]; then
        if [ "$STASH_CHANGES" = true ]; then
            print_warning "Stashing local changes..."
            git stash push -m "Auto-stash before deployment $(date)"
            print_success "Local changes stashed"
        elif [ "$FORCE_PULL" = true ]; then
            print_warning "Forcing pull with local changes (may cause conflicts)"
        else
            print_error "You have uncommitted changes. Options:"
            echo "  1. Commit your changes first"
            echo "  2. Use --stash to automatically stash them"  
            echo "  3. Use --force to pull anyway (may cause conflicts)"
            echo "  4. Use --skip-git to deploy without pulling"
            exit 1
        fi
    fi
    
    # Fetch and pull
    git fetch origin
    git pull origin $BRANCH && print_success "✅ Code updated successfully"
else
    print_status "⏭️  Skipping git operations"
fi

echo ""

# ========================================
# PROACTIVE DOCKER CLEANUP - BEFORE BUILD
# ========================================
if [ "$CLEANUP_IMAGES" = true ]; then
    print_status "🧹 Pre-deployment Docker cleanup to prevent errors..."
    
    # Stop containers first to free up references to images
    print_status "🛑 Stopping containers to release image references..."
    if [ "$REBUILD_ALL" = true ]; then
        docker compose down
    else
        docker compose stop polly 2>/dev/null || true
    fi
    
    # Remove any containers that might be referencing old images
    DANGLING_CONTAINERS=$(docker ps -aq --filter "status=exited" --filter "status=created")
    if [ -n "$DANGLING_CONTAINERS" ]; then
        echo "$DANGLING_CONTAINERS" | xargs docker rm 2>/dev/null || true
        print_status "Removed stopped/created containers"
    fi
    
    # Clean up problematic and dangling images BEFORE building
    print_status "🗑️  Removing dangling and problematic images..."
    DANGLING_IMAGES=$(docker images -f 'dangling=true' -q)
    if [ -n "$DANGLING_IMAGES" ]; then
        echo "$DANGLING_IMAGES" | xargs docker rmi -f 2>/dev/null || true
        print_status "Removed dangling images"
    fi
    
    # Get the project name for targeted cleanup
    PROJECT_NAME=$(basename "$(pwd)" | tr '[:upper:]' '[:lower:]')
    
    # Remove old Polly images (keep only the most recent 1 to prevent conflicts)
    print_status "🗑️  Removing old ${PROJECT_NAME}_polly images to prevent ContainerConfig errors..."
    OLD_POLLY_IMAGES=$(docker images "${PROJECT_NAME}_polly" --format "table {{.ID}}\t{{.CreatedAt}}" | tail -n +2 | sort -k2 -r | tail -n +2 | awk '{print $1}')
    
    if [ -n "$OLD_POLLY_IMAGES" ]; then
        echo "$OLD_POLLY_IMAGES" | xargs docker rmi -f 2>/dev/null || true
        print_status "Removed old ${PROJECT_NAME}_polly images"
    fi
    
    # Also clean up any <none>:<none> images that might be corrupted
    NONE_IMAGES=$(docker images --filter "dangling=true" --filter "reference=*/*:*" -q)
    if [ -n "$NONE_IMAGES" ]; then
        echo "$NONE_IMAGES" | xargs docker rmi -f 2>/dev/null || true
        print_status "Removed <none>:<none> images"
    fi
    
    # Clean build cache before building
    docker builder prune -f --filter="until=24h" 2>/dev/null || true
    print_status "Cleaned build cache"
    
    if [ "$AGGRESSIVE_CLEANUP" = true ]; then
        print_warning "🔥 Performing aggressive pre-build cleanup..."
        # Remove all unused images (not just dangling)
        docker image prune -af --filter="until=24h" 2>/dev/null || true
        # Clean all build cache
        docker builder prune -af 2>/dev/null || true
        # Clean system (containers, networks, etc.)
        docker system prune -f 2>/dev/null || true
        print_warning "⚠️  Aggressive pre-build cleanup completed"
    fi
    
    print_success "✅ Pre-deployment cleanup completed - ready for clean build"
else
    print_status "⏭️  Skipping Docker cleanup"
fi

echo ""
print_status "🐳 Building and starting Docker containers..."

# Deployment strategy - now with clean slate
if [ "$REBUILD_ALL" = true ]; then
    print_status "🔄 Rebuilding all containers..."
    docker compose build --no-cache
    docker compose up -d
    DEPLOYMENT_TYPE="Full rebuild"
else
    print_status "🔄 Building and starting Polly container..."
    docker compose build --no-cache polly
    docker compose up -d
    DEPLOYMENT_TYPE="Polly update"
fi

# Post-deployment cleanup (lighter since we cleaned before)
if [ "$CLEANUP_IMAGES" = true ]; then
    echo ""
    print_status "🧹 Post-deployment cleanup..."
    
    # Just remove any new dangling images created during build
    DANGLING_IMAGES=$(docker images -f 'dangling=true' -q)
    if [ -n "$DANGLING_IMAGES" ]; then
        echo "$DANGLING_IMAGES" | xargs docker rmi 2>/dev/null || true
        print_status "Removed new dangling images"
    fi
    
    print_success "✅ Docker cleanup completed"
fi

# Wait for services and health checks
print_status "⏳ Waiting for services to start..."
sleep 10

# Quick health check
POLLY_HEALTHY=false
for i in {1..6}; do
    if curl -f -s http://localhost:8000/health > /dev/null 2>&1; then
        POLLY_HEALTHY=true
        break
    else
        sleep 5
    fi
done

# Final status
echo ""
print_success "🎉 Deployment completed!"

# Show disk usage after cleanup
if [ "$CLEANUP_IMAGES" = true ]; then
    echo ""
    print_status "📊 Docker disk usage after cleanup:"
    docker system df 2>/dev/null || echo "Could not check Docker disk usage"
fi

echo ""
print_status "📋 Deployment Summary:"
echo "======================"
echo "Deployment type: $DEPLOYMENT_TYPE"
echo "Git branch: ${BRANCH:-N/A}"
echo "Image cleanup: $([ "$CLEANUP_IMAGES" = true ] && echo "✅ Enabled" || echo "❌ Disabled")"
echo "Polly health: $([ "$POLLY_HEALTHY" = true ] && echo "✅ Healthy" || echo "❌ Check logs")"

print_status "Container status:"
docker compose ps

print_success "🚀 Deployment complete!"
