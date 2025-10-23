# LeadFlowTracker - DigitalOcean Deployment Guide

This guide explains how to deploy LeadFlowTracker to your DigitalOcean droplet alongside ChatStack and ai-memory.

## Architecture Overview

**Development (Replit):**
- Database: Replit PostgreSQL
- URL: https://[replit-workspace].repl.co
- Purpose: Development and testing

**Production (DigitalOcean):**
- Database: DigitalOcean ai-memory PostgreSQL
- URL: https://leads.theinsurancedoctors.com
- Purpose: Production use by sales team

## Prerequisites

- ✅ Code pushed to GitHub: https://github.com/trpl333/LeadFlowTracker
- ✅ DigitalOcean droplet with SSH access
- ✅ Node.js 20+ installed on droplet
- ✅ PM2 or systemd for process management
- ✅ Nginx for reverse proxy (if serving multiple apps)

## Deployment Steps

### 1. SSH into Your DigitalOcean Droplet

```bash
ssh root@209.38.143.71
# or your droplet IP
```

### 2. Clone the Repository

```bash
cd /opt  # or your preferred directory
git clone https://github.com/trpl333/LeadFlowTracker.git
cd LeadFlowTracker
```

### 3. Install Dependencies

```bash
npm install
```

### 4. Configure Environment Variables

Create a `.env` file in the project root:

```bash
nano .env
```

Add the following:

```env
# Database - Use DigitalOcean ai-memory database
DO_DATABASE_URL=postgresql://doadmin:AVBL_u0StE4lNxN7w7hsU8L_NLE6@db-memory-do-user-17481003-0.c.db.ondigitalocean.com:25061/ai-memory-pool?sslmode=require

# Session secret
SESSION_SECRET=your-production-secret-here

# Node environment
NODE_ENV=production

# Port (choose an unused port)
PORT=5001
```

**Important:** Choose a unique port that doesn't conflict with:
- ChatStack (if using port 5000/8000/8001)
- AI-Memory (port 8100)
- VoiceBridge (port 9100)

### 5. Setup Database Schema

```bash
# Push the schema to ai-memory database
npm run db:push

# If there are conflicts, force push:
npm run db:push --force
```

This creates the `leads` table in your ai-memory database.

### 6. Build the Application

```bash
npm run build
# This compiles the frontend into server/public
```

### 7. Set Up Process Manager (PM2)

Install PM2 if not already installed:

```bash
npm install -g pm2
```

Create PM2 ecosystem file:

```bash
nano ecosystem.config.js
```

Add:

```javascript
module.exports = {
  apps: [{
    name: 'leadflow-tracker',
    script: 'npm',
    args: 'start',
    cwd: '/opt/LeadFlowTracker',
    env: {
      NODE_ENV: 'production',
      PORT: 5001
    },
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: '500M',
    error_file: '/var/log/leadflow/error.log',
    out_file: '/var/log/leadflow/out.log',
    log_file: '/var/log/leadflow/combined.log',
    time: true
  }]
};
```

Create log directory:

```bash
mkdir -p /var/log/leadflow
```

Start the application:

```bash
pm2 start ecosystem.config.js
pm2 save
pm2 startup  # Enable auto-start on boot
```

### 8. Configure Nginx Reverse Proxy

Edit your Nginx configuration:

```bash
nano /etc/nginx/sites-available/leads.theinsurancedoctors.com
```

Add:

```nginx
server {
    listen 80;
    server_name leads.theinsurancedoctors.com;

    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name leads.theinsurancedoctors.com;

    # SSL certificates (Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/leads.theinsurancedoctors.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/leads.theinsurancedoctors.com/privkey.pem;

    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Proxy to Node.js app
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

    # Logs
    access_log /var/log/nginx/leadflow-access.log;
    error_log /var/log/nginx/leadflow-error.log;
}
```

Enable the site:

```bash
ln -s /etc/nginx/sites-available/leads.theinsurancedoctors.com /etc/nginx/sites-enabled/
nginx -t  # Test configuration
systemctl reload nginx
```

### 9. Set Up SSL Certificate (Let's Encrypt)

```bash
certbot --nginx -d leads.theinsurancedoctors.com
```

Follow the prompts. Certbot will automatically configure SSL.

### 10. Verify Deployment

Check PM2 status:

```bash
pm2 status
pm2 logs leadflow-tracker
```

Test the application:

```bash
curl http://localhost:5001/api/leads
```

Visit: https://leads.theinsurancedoctors.com

## Updating After Changes

When you make changes in Replit and push to GitHub:

```bash
cd /opt/LeadFlowTracker
git pull origin main
npm install  # If dependencies changed
npm run build  # Rebuild frontend
pm2 restart leadflow-tracker
```

## Environment-Specific Configuration

The app automatically detects which database to use:

- **Development (Replit):** Uses `DATABASE_URL` (Replit PostgreSQL)
- **Production (DO):** Uses `DO_DATABASE_URL` (ai-memory database)

## Database Schema

The app creates these tables in ai-memory database:

### `leads` table:
- `id` - Unique identifier
- `name` - Lead name
- `company` - Company name
- `phone` - Phone number
- `email` - Email address
- `source` - Lead source
- `current_stage` - Current pipeline stage
- `completed_milestones` - Array of completed stages
- `milestone_history` - JSON history with timestamps
- `notes` - Lead notes
- `created_at` - Creation timestamp
- `updated_at` - Last update timestamp
- `stage_entered_at` - When lead entered current stage

## Monitoring

### Check Logs

```bash
pm2 logs leadflow-tracker
tail -f /var/log/leadflow/error.log
tail -f /var/log/nginx/leadflow-error.log
```

### Check Status

```bash
pm2 status
systemctl status nginx
```

### Database Connection

```bash
# Test database connection
psql "postgresql://doadmin:PASSWORD@db-memory-do-user-17481003-0.c.db.ondigitalocean.com:25061/ai-memory-pool?sslmode=require"

# List tables
\dt

# View leads
SELECT * FROM leads LIMIT 5;
```

## Troubleshooting

### App Won't Start

```bash
pm2 logs leadflow-tracker --err
# Check for database connection errors
```

### Database Connection Failed

- Verify `DO_DATABASE_URL` in `.env` is correct
- Check if database is accessible from droplet
- Verify firewall rules allow connection to port 25061

### Port Already in Use

```bash
# Find what's using the port
lsof -i :5001
# Change PORT in .env and ecosystem.config.js
```

### SSL Certificate Issues

```bash
certbot renew --dry-run
certbot certificates
```

## Workflow Summary

```
┌─────────────┐      ┌─────────────┐      ┌──────────────────┐
│   Replit    │─────▶│   GitHub    │─────▶│  DigitalOcean   │
│ Development │ push │ LeadFlow    │ pull │   Production    │
│             │      │  Tracker    │      │                  │
└─────────────┘      └─────────────┘      └──────────────────┘
      │                                             │
      │                                             │
      ▼                                             ▼
┌─────────────┐                           ┌──────────────────┐
│  Replit DB  │                           │  ai-memory DB    │
│ PostgreSQL  │                           │  (DigitalOcean)  │
└─────────────┘                           └──────────────────┘
                                                    │
                                          ┌─────────┴─────────┐
                                          │                   │
                                          ▼                   ▼
                                    ┌──────────┐      ┌─────────────┐
                                    │ChatStack │      │NeuroSphere  │
                                    └──────────┘      └─────────────┘
```

## Security Notes

- ✅ Never commit `.env` file to GitHub
- ✅ Use strong `SESSION_SECRET`
- ✅ Keep database credentials secure
- ✅ Regular updates: `npm audit fix`
- ✅ Monitor logs for suspicious activity

## Support

For issues or questions, check:
1. PM2 logs: `pm2 logs leadflow-tracker`
2. Nginx logs: `/var/log/nginx/leadflow-error.log`
3. Database connection: Test with `psql` command above
