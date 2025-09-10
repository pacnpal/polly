#!/bin/bash
set -e

echo "🚀 Polly Docker Deployment Script"
echo "================================="

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

# Check if .env file exists
if [ ! -f .env ]; then
    print_error ".env file not found! Please create it from .env.example"
    exit 1
fi

print_status "Checking .env file..."
print_success ".env file found"

# Parse command line arguments
REBUILD_ALL=false
REBUILD_POLLY=true
REBUILD_REDIS=false
SKIP_BUILD=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --all)
            REBUILD_ALL=true
            REBUILD_REDIS=true
            shift
            ;;
        --redis-only)
            REBUILD_POLLY=false
            REBUILD_REDIS=true
            shift
            ;;
        --no-build)
            SKIP_BUILD=true
            REBUILD_POLLY=false
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo "Options:"
            echo "  --all         Rebuild both Polly and Redis containers"
            echo "  --redis-only  Rebuild only Redis container"  
            echo "  --no-build    Skip building, just restart existing containers"
            echo "  --help, -h    Show this help message"
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Show what will be done
print_status "Deployment plan:"
if [ "$SKIP_BUILD" = true ]; then
    echo "  - Skip building containers"
    echo "  - Restart existing containers"
elif [ "$REBUILD_ALL" = true ]; then
    echo "  - Rebuild Polly container"
    echo "  - Rebuild Redis container"
elif [ "$REBUILD_POLLY" = true ] && [ "$REBUILD_REDIS" = false ]; then
    echo "  - Rebuild Polly container"
    echo "  - Keep Redis container unchanged"
elif [ "$REBUILD_REDIS" = true ] && [ "$REBUILD_POLLY" = false ]; then
    echo "  - Keep Polly container unchanged"
    echo "  - Rebuild Redis container"
fi

echo ""
read -p "Continue with deployment? (y/N): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_warning "Deployment cancelled by user"
    exit 0
fi

# Stop services first
print_status "Stopping existing containers..."
docker compose down

if [ "$SKIP_BUILD" = true ]; then
    print_status "Starting containers without building..."
    docker compose up -d
else
    # Build and start services based on options
    if [ "$REBUILD_ALL" = true ]; then
        print_status "Building all containers..."
        docker compose build --no-cache
        docker compose up -d
    elif [ "$REBUILD_POLLY" = true ]; then
        print_status "Building only Polly container..."
        docker compose build --no-cache polly
        docker compose up -d
    elif [ "$REBUILD_REDIS" = true ]; then
        print_status "Building only Redis container (pulling latest image)..."
        docker compose pull redis
        docker compose up -d
    fi
fi

# Wait for services to be ready
print_status "Waiting for services to be ready..."
sleep 5

# Check service health
print_status "Checking service health..."

# Check Redis
if docker compose ps redis | grep -q "Up"; then
    print_success "✅ Redis container is running"
else
    print_error "❌ Redis container is not running"
fi

# Check Polly
if docker compose ps polly | grep -q "Up"; then
    print_success "✅ Polly container is running"
    
    # Test health endpoint
    print_status "Testing Polly health endpoint..."
    sleep 10  # Give app time to start
    
    if curl -f -s http://localhost:8000/health > /dev/null; then
        print_success "✅ Polly health check passed"
    else
        print_warning "⚠️ Polly health check failed (app might still be starting)"
    fi
else
    print_error "❌ Polly container is not running"
fi

print_success "🎉 Deployment completed!"
print_status "You can check logs with:"
echo "  docker compose logs -f polly    # Polly logs"
echo "  docker compose logs -f redis    # Redis logs"
echo "  docker compose logs -f          # All logs"

print_status "You can check status with:"
echo "  docker compose ps              # Container status"
echo "  docker compose top             # Process status"
