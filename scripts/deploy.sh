#!/bin/bash
set -e

echo "🚀 Polly Complete Deployment Script"
echo "==================================="

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
        --help|-h)
            echo "Usage: $0 [options]"
            echo "Options:"
            echo "  --skip-git        Skip git operations, just rebuild containers"
            echo "  --all             Rebuild both Polly and Redis containers"
            echo "  --branch, -b      Specify git branch to pull (default: main)"
            echo "  --stash           Stash local changes before pulling"
            echo "  --force           Force pull even with local changes"
            echo "  --help, -h        Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                    # Pull main branch and update Polly"
            echo "  $0 --all             # Pull and rebuild everything"
            echo "  $0 --branch develop  # Pull develop branch"
            echo "  $0 --stash           # Stash changes first"
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Check if we're in a git repository
if [ ! -d ".git" ] && [ "$SKIP_GIT" = false ]; then
    print_error "Not in a git repository! Use --skip-git to deploy without git operations."
    exit 1
fi

# Check if docker compose.yml exists
if [ ! -f "docker compose.yml" ]; then
    print_error "docker compose.yml not found! Make sure you're in the project root."
    exit 1
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    print_error ".env file not found! Please create it from .env.example"
    exit 1
fi

print_status "Starting deployment process..."

# Git operations
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
    
    # Fetch latest changes
    print_status "Fetching latest changes..."
    git fetch origin
    
    # Get current branch if no branch specified and we're not on main
    if [ "$BRANCH" = "main" ]; then
        CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
        if [ "$CURRENT_BRANCH" != "main" ]; then
            BRANCH="$CURRENT_BRANCH"
            print_status "Using current branch: $BRANCH"
        fi
    fi
    
    # Check if branch exists
    if ! git show-ref --verify --quiet refs/heads/$BRANCH && ! git show-ref --verify --quiet refs/remotes/origin/$BRANCH; then
        print_error "Branch '$BRANCH' does not exist!"
        exit 1
    fi
    
    # Switch to target branch if needed
    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
    if [ "$CURRENT_BRANCH" != "$BRANCH" ]; then
        print_status "Switching to branch: $BRANCH"
        git checkout $BRANCH
    fi
    
    # Pull latest changes
    print_status "Pulling latest changes from origin/$BRANCH..."
    if git pull origin $BRANCH; then
        print_success "✅ Code updated successfully"
    else
        print_error "❌ Failed to pull changes"
        exit 1
    fi
    
    # Show what changed
    print_status "Recent commits:"
    git log --oneline -5
else
    print_status "⏭️  Skipping git operations"
fi

echo ""
print_status "🐳 Updating Docker containers..."

# Show current container status
print_status "Current container status:"
docker compose ps

echo ""

# Deployment strategy
if [ "$REBUILD_ALL" = true ]; then
    print_status "🔄 Rebuilding all containers..."
    docker compose down
    docker compose build --no-cache
    docker compose up -d
    DEPLOYMENT_TYPE="Full rebuild"
else
    print_status "🔄 Updating Polly container only (Redis will remain unchanged)..."
    docker compose stop polly
    docker compose build --no-cache polly
    docker compose up -d
    DEPLOYMENT_TYPE="Polly update"
fi

# Wait for services to be ready
print_status "⏳ Waiting for services to start..."
sleep 10

# Health checks
print_status "🩺 Running health checks..."

# Check Redis
REDIS_STATUS="❌ Down"
if docker compose ps redis | grep -q "Up"; then
    REDIS_STATUS="✅ Running"
fi

# Check Polly
POLLY_STATUS="❌ Down"
POLLY_HEALTH="❌ Unhealthy"
if docker compose ps polly | grep -q "Up"; then
    POLLY_STATUS="✅ Running"
    
    # Test health endpoint
    print_status "Testing Polly health endpoint..."
    for i in {1..6}; do
        if curl -f -s http://localhost:8000/health > /dev/null; then
            POLLY_HEALTH="✅ Healthy"
            break
        else
            if [ $i -eq 6 ]; then
                POLLY_HEALTH="⚠️  Health check failed (may still be starting)"
            else
                print_status "Health check attempt $i/6..."
                sleep 5
            fi
        fi
    done
fi

# Final status report
echo ""
print_success "🎉 Deployment completed!"
echo ""
print_status "📊 Deployment Summary:"
echo "======================"
echo "Deployment type: $DEPLOYMENT_TYPE"
echo "Git branch: ${BRANCH:-N/A}"
echo "Redis: $REDIS_STATUS"
echo "Polly: $POLLY_STATUS"
echo "Health: $POLLY_HEALTH"

# Show final container status
echo ""
print_status "📋 Final container status:"
docker compose ps

echo ""
print_status "💡 Useful post-deployment commands:"
echo "  docker compose logs -f polly    # Follow Polly logs"
echo "  docker compose logs -f          # Follow all logs" 
echo "  make status                     # Check detailed status"
echo "  curl http://localhost:8000/health # Manual health check"

# Optional: Show recent logs
echo ""
read -p "🔍 Show recent Polly logs? (y/N): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_status "Recent Polly logs:"
    docker compose logs --tail=20 polly
fi

print_success "🚀 Deployment complete! Polly is ready to serve requests."
