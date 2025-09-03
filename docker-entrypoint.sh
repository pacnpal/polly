#!/bin/bash
set -e

echo "Starting Polly Discord Bot..."

# Ensure directories exist and have proper permissions
echo "Setting up directories and permissions..."
mkdir -p static/uploads logs data
chmod 755 static/uploads
chmod 755 logs
chmod 755 data

# Ensure the application can write to these directories
chown -R $(id -u):$(id -g) static/uploads logs data 2>/dev/null || true

# Run database migration if needed
echo "Running database migration..."
uv run migrate_database.py

# Running final dependency checks
echo "Running final dependency checks..."
uv sync

# Start the application
echo "Starting application..."
exec uv run -m polly.main
