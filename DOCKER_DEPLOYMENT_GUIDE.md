# NeuroSphere Voice - Unified Docker Deployment Guide

**Date:** October 31, 2025  
**Version:** 2.0 - Unified Docker Compose Architecture

---

## 🎯 Overview

This guide walks you through deploying the unified Docker Compose setup for NeuroSphere Voice / ChatStack. All services (Nginx, Flask Web, FastAPI Orchestrator, AI-Memory, and Status Monitor) now run in a **single Docker network** for consistent communication and simplified management.

---

## 📋 Prerequisites

- DigitalOcean droplet (209.38.143.71) with Docker and Docker Compose installed
- SSH access to the droplet
- SSL certificates already configured at `/etc/letsencrypt/live/voice.theinsurancedoctors.com/`
- All secrets configured in `/opt/ChatStack/.env`

---

## 🚨 CRITICAL: Stop Host-Level Services First

Before deploying the Docker setup, you **MUST** stop the host-level Nginx service to free up ports 80 and 443:

```bash
ssh root@209.38.143.71

# Stop and disable host-level Nginx
sudo systemctl stop nginx
sudo systemctl disable nginx

# Verify Nginx is stopped
sudo systemctl status nginx
# Should show "inactive (dead)"

# Verify ports 80 and 443 are free
sudo netstat -tulpn | grep -E ':80|:443'
# Should return nothing
```

---

## 📦 Step 1: Deploy to Production

### 1.1 SSH into Production Server

```bash
ssh root@209.38.143.71
cd /opt/ChatStack
```

### 1.2 Pull Latest Code

```bash
git pull origin main
```

### 1.3 Verify Configuration Files Exist

```bash
# Check docker-compose.yml
ls -la docker-compose.yml

# Check Nginx config
ls -la deploy/nginx/voice-theinsurancedoctors-com.conf

# Check monitor config
ls -la config/monitor.yml

# Verify .env has all required secrets
cat .env | grep -E "DATABASE_URL|JWT_SECRET_KEY|OPENAI_API_KEY|TWILIO"
```

### 1.4 Stop Existing Docker Containers (if any)

```bash
# Stop old containers from separate compose projects
cd /opt/ChatStack
docker-compose down

# If ai-memory was in separate compose project
cd /opt/ai-memory
docker-compose -f docker-compose-ai.yml down 2>/dev/null || true

# Return to ChatStack
cd /opt/ChatStack
```

### 1.5 Build and Start All Services

```bash
# Build and start everything in one unified network
docker-compose up -d --build

# This will create:
# - chatstack-nginx (port 80/443)
# - chatstack-web (port 5000)
# - chatstack-orchestrator (port 8001)
# - ai-memory (port 8100)
# - chatstack-status-monitor
```

### 1.6 Verify All Containers Are Running

```bash
docker ps

# You should see 5 containers:
# chatstack-nginx
# chatstack-web
# chatstack-orchestrator
# ai-memory
# chatstack-status-monitor
```

---

## ✅ Step 2: Verify Deployment

### 2.1 Check Container Status

```bash
docker-compose ps

# All services should show "Up"
```

### 2.2 Check Container Logs

```bash
# View all logs
docker-compose logs -f

# View specific service logs
docker logs chatstack-nginx
docker logs chatstack-web
docker logs chatstack-orchestrator
docker logs ai-memory
docker logs chatstack-status-monitor
```

### 2.3 Test Health Endpoints (Internal)

```bash
# Test from inside the Docker network
docker exec chatstack-orchestrator curl http://web:5000/health
docker exec chatstack-orchestrator curl http://orchestrator:8001/health
docker exec chatstack-orchestrator curl http://ai-memory:8100/health
```

### 2.4 Test External HTTPS Access

```bash
# From your local machine (or from the droplet)
curl -k https://voice.theinsurancedoctors.com/health

# Should return: {"status": "healthy"}
```

### 2.5 Test Admin Panel

Visit in your browser:
```
https://voice.theinsurancedoctors.com/admin.html
```

You should see:
- ✅ Admin panel loads
- ✅ System Status tab shows all services healthy
- ✅ Profile save/update works (no 403 errors)
- ✅ Memory retrieval works

---

## 🔧 Step 3: Common Management Tasks

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f orchestrator

# Last 100 lines
docker-compose logs --tail=100
```

### Restart Services

```bash
# Restart all services
docker-compose restart

# Restart specific service
docker-compose restart orchestrator

# Rebuild and restart after code changes
docker-compose up -d --build
```

### Stop Services

```bash
# Stop all services (keeps data)
docker-compose stop

# Stop and remove containers (keeps images)
docker-compose down

# Stop and remove everything (including volumes)
docker-compose down -v
```

### Check Service Health

```bash
# View container health
docker ps

# Inspect specific container
docker inspect chatstack-orchestrator

# View resource usage
docker stats
```

---

## 📊 Step 4: Monitor and Debug

### Check Docker Network

```bash
# List networks
docker network ls

# Inspect chatstack-network
docker network inspect chatstack-network

# Should show all 5 containers connected
```

### Test Inter-Service Communication

```bash
# From orchestrator, test connectivity to other services
docker exec chatstack-orchestrator curl http://web:5000/health
docker exec chatstack-orchestrator curl http://ai-memory:8100/health

# From web, test connectivity to orchestrator
docker exec chatstack-web curl http://orchestrator:8001/health

# From web, test connectivity to ai-memory
docker exec chatstack-web curl http://ai-memory:8100/health
```

### Debug Nginx Routing

```bash
# Check Nginx config syntax
docker exec chatstack-nginx nginx -t

# View Nginx logs
docker logs chatstack-nginx

# View Nginx access logs
docker exec chatstack-nginx tail -f /var/log/nginx/voice_access.log

# View Nginx error logs
docker exec chatstack-nginx tail -f /var/log/nginx/voice_error.log
```

---

## 🚨 Troubleshooting

### Port 80/443 Already in Use

```bash
# Find what's using the port
sudo netstat -tulpn | grep -E ':80|:443'

# If it's host-level Nginx
sudo systemctl stop nginx
sudo systemctl disable nginx

# If it's another Docker container
docker ps | grep ":80\|:443"
docker stop <container_id>
```

### Container Won't Start

```bash
# View detailed logs
docker logs <container_name>

# Check if volume mounts exist
ls -la /opt/ChatStack/static
ls -la /etc/letsencrypt/live/voice.theinsurancedoctors.com/

# Rebuild from scratch
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### AI-Memory Connection Issues

```bash
# Verify ai-memory is running
docker ps | grep ai-memory

# Test connection from orchestrator
docker exec chatstack-orchestrator curl -v http://ai-memory:8100/health

# Check ai-memory logs for errors
docker logs ai-memory
```

### 403 Errors in Admin Panel

```bash
# Verify JWT_SECRET_KEY matches in .env
cat /opt/ChatStack/.env | grep JWT_SECRET_KEY

# Verify ai-memory is accessible
docker exec chatstack-web curl http://ai-memory:8100/health

# Check web service logs
docker logs chatstack-web
```

---

## 🔄 Updating the System

### Code Updates

```bash
cd /opt/ChatStack
git pull origin main
docker-compose up -d --build
```

### Environment Variable Changes

```bash
# Edit .env
nano /opt/ChatStack/.env

# Restart services to pick up new env vars
docker-compose restart
```

### Nginx Config Changes

```bash
# Edit nginx config
nano /opt/ChatStack/deploy/nginx/voice-theinsurancedoctors-com.conf

# Test config syntax
docker exec chatstack-nginx nginx -t

# Reload nginx (no downtime)
docker exec chatstack-nginx nginx -s reload

# Or restart container
docker-compose restart nginx
```

---

## 📝 Architecture Summary

### Docker Compose Services

| Container | Role | Port | Docker DNS |
|-----------|------|------|------------|
| `chatstack-nginx` | Reverse proxy + SSL | 80, 443 | `nginx` |
| `chatstack-web` | Flask admin panel | 5000 | `web` |
| `chatstack-orchestrator` | FastAPI phone AI | 8001 | `orchestrator` |
| `ai-memory` | Memory microservice | 8100 | `ai-memory` |
| `chatstack-status-monitor` | Health checker | - | - |

### Network Communication

All services communicate via Docker DNS names instead of `127.0.0.1`:

```
http://web:5000           → Flask admin panel
http://orchestrator:8001  → FastAPI orchestrator
http://ai-memory:8100     → Memory service
```

### External Access

- **HTTPS**: `https://voice.theinsurancedoctors.com` → Nginx → Services
- **Admin Panel**: `https://voice.theinsurancedoctors.com/admin.html`
- **Twilio WebSocket**: `wss://voice.theinsurancedoctors.com/phone/media-stream`

---

## 🎉 Success Criteria

Your deployment is successful when:

1. ✅ All 5 Docker containers are running (`docker ps`)
2. ✅ Admin panel loads at `https://voice.theinsurancedoctors.com/admin.html`
3. ✅ System Status tab shows all services healthy
4. ✅ Profile save/update returns HTTP 200 (no 403 errors)
5. ✅ AI-Memory endpoints respond correctly
6. ✅ Twilio phone calls work end-to-end
7. ✅ Call recordings and transcripts are saved
8. ✅ Memory persistence works (caller names, history)

---

## 📞 Support

If you encounter issues:

1. Check container logs: `docker-compose logs -f`
2. Verify network connectivity: Use test commands in Step 4
3. Review troubleshooting section above
4. Check `MULTI_PROJECT_ARCHITECTURE.md` for architecture details

---

**Last Updated:** October 31, 2025  
**Maintained by:** NeuroSphere Development Team
