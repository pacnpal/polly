#!/bin/bash
set -e

echo "Starting Polly Discord Bot..."

# Ensure directories exist and have proper permissions
echo "Setting up directories and permissions..."
mkdir -p static/uploads logs data || true
chmod 755 static 2>/dev/null || echo "Warning: Could not change static directory permissions (mounted volume)"
chmod 755 static/uploads 2>/dev/null || echo "Warning: Could not change uploads directory permissions (mounted volume)"  
chmod 755 logs 2>/dev/null || echo "Warning: Could not change logs directory permissions (mounted volume)"
chmod 755 data 2>/dev/null || echo "Warning: Could not change data directory permissions (mounted volume)"

# Ensure the application can write to these directories
# chown -R $(id -u):$(id -g) /app static/uploads logs data 

# Run database migration if needed
echo "Running database migration..."
mkdir .cache
uv run migrate_database.py

# Running final dependency checks
echo "Running final dependency checks..."
uv sync

# Start the application
echo "Starting application..."
exec uv run -m polly.main
