#!/bin/bash
set -e

echo "Starting Polly Discord Bot..."

# Run database migration if needed
echo "Running database migration..."
uv run migrate_database.py

# Running final dependency checks
echo "Running final dependency checks..."
uv sync

# Start the application
echo "Starting application..."
exec uv run -m polly.main
