#!/bin/bash
# Start Notion sync service

echo "🚀 Starting Notion API Server..."

# Check if Node.js is available
if ! command -v node &> /dev/null; then
    echo "❌ Node.js not found"
    exit 1
fi

# Start the server
cd /app
node services/notion-api-server.js
