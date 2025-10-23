#!/bin/bash

# ai-memory Database Health Check Script
# Run this on your DigitalOcean droplet to test database connectivity

echo "🏥 ai-memory Database Health Check"
echo "===================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

DB_HOST="db-memory-do-user-17481003-0.c.db.ondigitalocean.com"
DB_PORT="25061"
DB_NAME="ai-memory-pool"
DB_USER="doadmin"
DB_PASS="AVBL_u0StE4lNxN7w7hsU8L_NLE6"

# Test 1: DNS Resolution
echo -e "${BLUE}Test 1: DNS Resolution${NC}"
echo "Resolving $DB_HOST..."
if nslookup $DB_HOST > /dev/null 2>&1; then
    IP=$(nslookup $DB_HOST | grep -A1 "Name:" | grep "Address:" | awk '{print $2}')
    echo -e "${GREEN}✅ DNS Resolution: SUCCESS${NC}"
    echo "   Resolved to: $IP"
else
    echo -e "${RED}❌ DNS Resolution: FAILED${NC}"
    echo "   Cannot resolve hostname"
fi
echo ""

# Test 2: Network Connectivity (Port Check)
echo -e "${BLUE}Test 2: Network Connectivity${NC}"
echo "Testing connection to $DB_HOST:$DB_PORT..."
if timeout 5 bash -c "cat < /dev/null > /dev/tcp/$DB_HOST/$DB_PORT" 2>/dev/null; then
    echo -e "${GREEN}✅ Port $DB_PORT: REACHABLE${NC}"
    echo "   Network connection successful"
else
    echo -e "${RED}❌ Port $DB_PORT: NOT REACHABLE${NC}"
    echo "   Possible causes:"
    echo "   - Database firewall blocking this IP"
    echo "   - VPC-only access configured"
    echo "   - Incorrect network settings"
fi
echo ""

# Test 3: Server Information
echo -e "${BLUE}Test 3: Server Information${NC}"
echo "Current server IP: $(curl -s ifconfig.me)"
echo "Current hostname: $(hostname)"
echo ""

# Test 4: PostgreSQL Connection Test
echo -e "${BLUE}Test 4: PostgreSQL Connection & Query${NC}"
echo "Attempting to connect to database..."

# Check if psql is installed
if ! command -v psql &> /dev/null; then
    echo -e "${YELLOW}⚠️  psql not installed. Installing postgresql-client...${NC}"
    apt-get update -qq && apt-get install -y -qq postgresql-client > /dev/null 2>&1
fi

# Try to connect and run simple query
CONNECTION_STRING="postgresql://$DB_USER:$DB_PASS@$DB_HOST:$DB_PORT/$DB_NAME?sslmode=require"

if psql "$CONNECTION_STRING" -c "SELECT version();" 2>/dev/null | grep -q "PostgreSQL"; then
    echo -e "${GREEN}✅ Database Connection: SUCCESS${NC}"
    echo ""
    
    # Get PostgreSQL version
    echo "PostgreSQL Version:"
    psql "$CONNECTION_STRING" -t -c "SELECT version();" 2>/dev/null | head -1
    echo ""
    
    # Check current database
    echo "Current Database:"
    psql "$CONNECTION_STRING" -t -c "SELECT current_database();" 2>/dev/null
    echo ""
    
    # List all tables
    echo "Existing Tables:"
    psql "$CONNECTION_STRING" -c "\dt" 2>/dev/null
    echo ""
    
    # Check if 'leads' table exists
    if psql "$CONNECTION_STRING" -t -c "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'leads');" 2>/dev/null | grep -q "t"; then
        echo -e "${GREEN}✅ 'leads' table: EXISTS${NC}"
        
        # Count records in leads table
        LEAD_COUNT=$(psql "$CONNECTION_STRING" -t -c "SELECT COUNT(*) FROM leads;" 2>/dev/null)
        echo "   Total leads: $LEAD_COUNT"
        echo ""
        
        # Show table structure
        echo "Leads table structure:"
        psql "$CONNECTION_STRING" -c "\d leads" 2>/dev/null
    else
        echo -e "${YELLOW}⚠️  'leads' table: DOES NOT EXIST${NC}"
        echo "   Run 'npm run db:push' to create it"
    fi
    echo ""
    
    # Show all tables with row counts
    echo "All Tables with Row Counts:"
    psql "$CONNECTION_STRING" -c "
        SELECT 
            schemaname,
            tablename,
            (SELECT COUNT(*) FROM information_schema.tables t WHERE t.table_name = pg_tables.tablename) as count
        FROM pg_tables 
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
        ORDER BY tablename;
    " 2>/dev/null
    
else
    echo -e "${RED}❌ Database Connection: FAILED${NC}"
    echo ""
    echo "Error details:"
    psql "$CONNECTION_STRING" -c "SELECT 1;" 2>&1 | head -5
    echo ""
    echo -e "${YELLOW}Troubleshooting steps:${NC}"
    echo "1. Check DigitalOcean database settings"
    echo "2. Go to: https://cloud.digitalocean.com/databases"
    echo "3. Click: db-memory"
    echo "4. Settings → Trusted Sources"
    echo "5. Add this server's IP: $(curl -s ifconfig.me)"
    echo ""
fi

echo "===================================="
echo "🏁 Health Check Complete"
echo "===================================="
