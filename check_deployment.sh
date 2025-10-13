#!/bin/bash
echo "=== Checking if code is on GitHub ==="
git log --oneline -3

echo -e "\n=== Files that changed ==="
git diff --name-only HEAD~1 HEAD | head -20
