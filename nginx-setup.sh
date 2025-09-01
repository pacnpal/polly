#!/bin/bash
set -e

echo "Setting up Nginx configuration for Polly..."

# Create nginx directories if they don't exist
mkdir -p nginx/sites-available
mkdir -p nginx/sites-enabled

# Check if the site configuration exists
if [ ! -f "nginx/sites-available/polly.conf" ]; then
    echo "Error: nginx/sites-available/polly.conf not found!"
    echo "Please ensure the site configuration file exists."
    exit 1
fi

# Create the symlink in sites-enabled (remove existing first)
if [ -L "nginx/sites-enabled/polly.conf" ]; then
    echo "Removing existing symlink..."
    unlink nginx/sites-enabled/polly.conf
fi

if [ -f "nginx/sites-enabled/polly.conf" ]; then
    echo "Removing existing file (should be symlink)..."
    rm nginx/sites-enabled/polly.conf
fi

echo "Creating symlink from sites-available to sites-enabled..."
cd nginx/sites-enabled
ln -s ../sites-available/polly.conf polly.conf
cd ../..

echo "Verifying nginx configuration structure..."
if [ -L "nginx/sites-enabled/polly.conf" ]; then
    echo "✅ Symlink created successfully"
    ls -la nginx/sites-enabled/polly.conf
else
    echo "❌ Failed to create symlink"
    exit 1
fi

# Test nginx configuration if nginx is available
if command -v nginx &> /dev/null; then
    echo "Testing nginx configuration..."
    nginx -t -c "$(pwd)/nginx/nginx.conf"
    if [ $? -eq 0 ]; then
        echo "✅ Nginx configuration is valid"
    else
        echo "❌ Nginx configuration has errors"
        exit 1
    fi
else
    echo "⚠️  Nginx not installed locally, skipping configuration test"
    echo "Configuration will be tested when Docker container starts"
fi

echo "✅ Nginx setup complete!"
echo ""
echo "Directory structure:"
echo "nginx/"
echo "├── nginx.conf (main configuration)"
echo "├── sites-available/"
echo "│   └── polly.conf (site configuration)"
echo "└── sites-enabled/"
echo "    └── polly.conf -> ../sites-available/polly.conf (symlink)"
echo ""
echo "You can now run: docker-compose up --build -d"
