# Quick Fix for Deployment Issues

Run these commands on your DigitalOcean server to fix the deployment:

## Step 1: Update Environment Variables

The issue is that `drizzle.config.ts` looks for `DATABASE_URL`, but we set `DO_DATABASE_URL`. 
Let's update the .env file to use `DATABASE_URL` for production:

```bash
cd /opt/LeadFlowTracker

# Update .env file
cat > .env << 'EOF'
DATABASE_URL=postgresql://doadmin:AVBL_u0StE4lNxN7w7hsU8L_NLE6@db-memory-do-user-17481003-0.c.db.ondigitalocean.com:25061/ai-memory-pool?sslmode=require
DO_DATABASE_URL=postgresql://doadmin:AVBL_u0StE4lNxN7w7hsU8L_NLE6@db-memory-do-user-17481003-0.c.db.ondigitalocean.com:25061/ai-memory-pool?sslmode=require
SESSION_SECRET=$(openssl rand -base64 32)
NODE_ENV=production
PORT=5001
EOF
```

## Step 2: Push Database Schema

```bash
npm run db:push
```

If that fails with data loss warning:
```bash
npm run db:push --force
```

## Step 3: Fix Nginx Config (HTTP Only First)

Remove the old config and create HTTP-only version:

```bash
rm /etc/nginx/sites-enabled/leads.theinsurancedoctors.com
rm /etc/nginx/sites-available/leads.theinsurancedoctors.com

# Create HTTP-only config
cat > /etc/nginx/sites-available/leads.theinsurancedoctors.com << 'EOF'
server {
    listen 80;
    server_name leads.theinsurancedoctors.com;

    location / {
        proxy_pass http://localhost:5001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }

    access_log /var/log/nginx/leadflow-access.log;
    error_log /var/log/nginx/leadflow-error.log;
}
EOF

# Enable it
ln -s /etc/nginx/sites-available/leads.theinsurancedoctors.com /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx
```

## Step 4: Get SSL Certificate

Now certbot will automatically update the config:

```bash
certbot --nginx -d leads.theinsurancedoctors.com
```

## Step 5: Start the App with PM2

```bash
cd /opt/LeadFlowTracker

# Create log directory if not exists
mkdir -p /var/log/leadflow

# Start with PM2
pm2 start ecosystem.config.js
pm2 save

# Check status
pm2 status
pm2 logs leadflow-tracker --lines 50
```

## Step 6: Test

```bash
# Test locally
curl http://localhost:5001/api/leads

# Test from browser
# Visit: https://leads.theinsurancedoctors.com
```

## Troubleshooting

If the app won't start, check logs:
```bash
pm2 logs leadflow-tracker --err
```

If database connection fails:
```bash
# Verify environment variables
cat /opt/LeadFlowTracker/.env

# Test database connection
psql "$DO_DATABASE_URL" -c "SELECT current_database();"
```

If PM2 shows "out-of-date" warning:
```bash
pm2 update
```
