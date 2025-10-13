#!/bin/bash
echo "This script should be run on DigitalOcean to check Docker logs:"
echo ""
echo "# Check if Flask loaded the personality endpoints:"
echo "docker logs chatstack-web-1 2>&1 | tail -50"
echo ""
echo "# Force rebuild without cache:"
echo "docker-compose build --no-cache web"
echo "docker-compose up -d web"
