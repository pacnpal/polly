#!/bin/bash
set -e

# Super simple update script - git pull + container update in one command
# No prompts, just does the most common deployment scenario

echo "🚀 Quick Update: Git Pull + Container Rebuild"
echo "============================================="

# Check if we have uncommitted changes
if [ -n "$(git status --porcelain)" ]; then
    echo "⚠️  You have uncommitted changes. Stashing them..."
    git stash push -m "Auto-stash before quick update $(date)"
fi

# Pull latest changes  
echo "📥 Pulling latest changes..."
git pull

# Update container
echo "🐳 Updating Polly container..."
docker compose stop polly
docker compose build --no-cache polly
docker compose up -d

# Quick health check
echo "🩺 Health check..."
sleep 5
if curl -f -s http://localhost:8000/health > /dev/null; then
    echo "✅ Update complete! Polly is healthy and ready."
else
    echo "⚠️  Update complete but health check failed. Check logs with: docker compose logs polly"
fi
