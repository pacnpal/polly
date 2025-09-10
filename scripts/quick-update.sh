#!/bin/bash

# Quick Polly Update Script
# Updates only the Polly container, leaving Redis untouched

set -e

echo "🚀 Quick Polly Update"
echo "===================="

# Check if docker compose.yml exists
if [ ! -f "docker compose.yml" ]; then
    echo "❌ docker compose.yml not found! Make sure you're in the project root."
    exit 1
fi

# Show current status
echo "📊 Current container status:"
docker compose ps

echo ""
echo "🔄 Updating Polly container only (Redis will remain unchanged)..."

# Stop only Polly service
echo "⏹️  Stopping Polly container..."
docker compose stop polly

# Rebuild Polly container
echo "🔨 Building new Polly container..."
docker compose build --no-cache polly

# Start all services (Redis should already be running)
echo "▶️  Starting services..."
docker compose up -d

# Wait a moment for services to start
echo "⏳ Waiting for services to start..."
sleep 5

# Show final status
echo "📊 Final container status:"
docker compose ps

echo ""
echo "✅ Polly update completed!"
echo ""
echo "💡 Useful commands:"
echo "   docker compose logs -f polly    # Follow Polly logs"
echo "   docker compose ps               # Check status"
echo "   curl http://localhost:8000/health # Health check"
