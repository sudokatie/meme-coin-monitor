#!/bin/bash
# Deploy meme-coin-monitor with automatic cache busting

set -e

# Bump version numbers in HTML
VERSION=$(date +%s)
echo "Bumping cache version to $VERSION"

# Update version in index.html
sed -i '' "s/style.css?v=[0-9]*/style.css?v=$VERSION/" dashboard/index.html
sed -i '' "s/app.js?v=[0-9]*/app.js?v=$VERSION/" dashboard/index.html

# Commit the version bump
git add dashboard/index.html
git commit -m "Bump cache version to $VERSION" || true

# Deploy to server
echo "Deploying to katie-server..."
rsync -avz --delete \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.env' \
    --exclude='venv' \
    --exclude='logs' \
    --exclude='data' \
    ./ katie-server:/opt/meme-coin-monitor/

# Restart the service
echo "Restarting service..."
ssh katie-server "sudo systemctl restart meme-coin-monitor"

echo "Deploy complete! Cache version: $VERSION"
