#!/bin/bash

# Fix import.meta.dirname issue in production build
# This replaces undefined import.meta.dirname with a working alternative

echo "🔧 Fixing production build..."

cd /opt/LeadFlowTracker

# Replace the problematic line in dist/index.js
sed -i 's/import\.meta\.dirname/path.dirname(new URL(import.meta.url).pathname)/g' dist/index.js

echo "✅ Fixed! Starting app..."

# Start with PM2
pm2 start ecosystem.config.cjs
pm2 logs leadflow-tracker --lines 20
