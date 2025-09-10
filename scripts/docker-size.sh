#!/bin/bash

echo "🐳 Docker Disk Usage Report"
echo "==========================="

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    echo "❌ Docker daemon is not running or not accessible"
    exit 1
fi

# Show overall Docker disk usage
echo "📊 Overall Docker Disk Usage:"
docker system df

echo ""
echo "🏷️  Docker Images:"
echo "Repository                    Tag        Image ID       Size"
echo "------------------------------------------------------------"
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}" | head -20

echo ""
echo "💨 Dangling Images (can be safely removed):"
DANGLING_COUNT=$(docker images -f 'dangling=true' -q | wc -l | tr -d ' ')
if [ "$DANGLING_COUNT" -gt 0 ]; then
    echo "Found $DANGLING_COUNT dangling images:"
    docker images -f 'dangling=true' --format "table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}"
else
    echo "✅ No dangling images found"
fi

echo ""
echo "🗄️  Build Cache Usage:"
docker system df | grep "Build Cache" || echo "Build cache information not available"

echo ""
echo "📋 Polly-specific Images:"
PROJECT_NAME=$(basename "$(pwd)" | tr '[:upper:]' '[:lower:]')
POLLY_IMAGES=$(docker images "${PROJECT_NAME}-polly" --format "table {{.Repository}}:{{.Tag}}\t{{.ID}}\t{{.CreatedAt}}\t{{.Size}}" | tail -n +2)

if [ -n "$POLLY_IMAGES" ]; then
    echo "$POLLY_IMAGES"
else
    echo "No Polly images found with name '${PROJECT_NAME}-polly'"
    echo "Checking for any polly-related images..."
    docker images | grep -i polly || echo "No polly-related images found"
fi

echo ""
echo "🧹 Cleanup Suggestions:"
echo "======================"

if [ "$DANGLING_COUNT" -gt 0 ]; then
    echo "1. Remove dangling images: make clean-images"
fi

TOTAL_SIZE=$(docker system df --format "table {{.Type}}\t{{.TotalCount}}\t{{.Size}}" | grep "Images" | awk '{print $3}')
echo "2. Current total image size: $TOTAL_SIZE"

echo "3. Available cleanup commands:"
echo "   make clean-images        # Safe cleanup (dangling images + old build cache)"
echo "   make deploy-clean        # Deploy with automatic cleanup"
echo "   ./scripts/deploy-clean.sh --aggressive-cleanup  # Deep clean (use with caution)"

echo ""
echo "💡 Disk Space Tips:"
echo "- Dangling images are safe to remove (untagged/orphaned images)"
echo "- Keep 1-2 recent Polly images for quick rollback"
echo "- Build cache helps speed up rebuilds, but can be cleaned if space is tight"
echo "- Use 'make deploy-clean' for automatic cleanup with deployments"
