#!/bin/bash
set -e

echo "Starting Polly Discord Bot..."

# Ensure directories exist (volumes will be mounted here)
echo "Setting up directories..."
mkdir -p static/uploads static/avatars static/images static/polls logs data db || true

# Create cache directory for uv
mkdir -p .cache

# Run database migration if needed
echo "Running database migration..."
uv run migrate_database.py

# Running final dependency checks
echo "Running final dependency checks..."
uv sync

# Start the application
echo "Starting application..."
exec uv run -m polly.main
