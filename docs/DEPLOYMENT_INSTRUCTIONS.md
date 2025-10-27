# Notion Dashboard Integration - Deployment Instructions

## Summary of Changes

Successfully integrated Notion CRM dashboard for centralized call tracking. The system now logs every call to a Notion database with:

✅ **Call SID** - Twilio identifier
✅ **Transcript URL** - Link to full transcript file
✅ **Audio URL** - Link to recording file
✅ **Status** - New/Read/Completed (defaults to "New")
✅ **Assigned Agent** - Unassigned/John/Milissa/Colin/Samantha (defaults to "Unassigned")
✅ **Full Transcript** - Complete conversation in Transcript column
✅ **Brief Summary** - 200-char preview in Summary column
✅ **Phone Number** - Caller's number
✅ **Call Date** - Timestamp (sorted newest first)

## Files Modified

1. `.notion_backup_replit/notion-sync.js` - Added new schema fields
2. `.notion_backup_replit/notion-api-server.js` - Updated API endpoint
3. `.notion_backup_replit/notion_client.py` - Enhanced Python client
4. `app/notion_client.py` - Copied client to app directory
5. `app/main.py` - Integrated Notion logging after each call

## Deployment Steps

### 1. Update Notion Database Schema (One-time setup)

You'll need to manually add these fields to your Notion "Calls" database:

- **Call SID**: Text property
- **Transcript URL**: URL property
- **Audio URL**: URL property
- **Status**: Select property with options: New, Read, Completed
- **Assigned Agent**: Select property with options: Unassigned, John, Milissa, Colin, Samantha

### 2. Deploy to Production (DigitalOcean)

```bash
# SSH into your DigitalOcean droplet
ssh root@your-droplet-ip

# Navigate to ChatStack directory
cd /opt/ChatStack

# Pull latest code from your repository

# Copy new Notion client to app directory
cp .notion_backup_replit/notion_client.py app/

# Rebuild orchestrator-worker service (CRITICAL!)
docker-compose up -d --build orchestrator-worker

# Restart Notion API server (if running)
# Check if it's running on port 8200
lsof -i :8200

# If needed, restart it
cd .notion_backup_replit
pm2 restart notion-api-server  # Or however you're running it
```

### 3. Verify Services

```bash
# Check orchestrator is running
docker-compose ps

# Check Notion API server
curl http://localhost:8200/health

# Check logs
docker-compose logs -f orchestrator-worker
```

## Testing

1. **Make a test call** to your Twilio number
2. **Check logs** for Notion logging confirmation:
   - `📊 Logging call to Notion: CAxxxxx`
   - `✅ Call logged to Notion dashboard: CAxxxxx`
3. **Verify Notion** shows:
   - New entry with Status="New"
   - Assigned Agent="Unassigned"
   - Full transcript in Transcript column
   - Brief summary in Summary column
   - Working URLs for transcript and audio
4. **Check SMS** still works (should receive brief summary)

## Architecture Notes

- **Non-blocking**: Notion logging uses try/except, won't break calls if Notion is down
- **Health checks**: Verifies Notion service is available before sending
- **SMS preserved**: Still sends SMS with brief summary for immediate alerts
- **Centralized dashboard**: All call data now in one Notion database
- **Sortable**: Notion automatically sorts by Call Date (newest first)

## Next Steps

After successful deployment:
1. Monitor first few calls to ensure Notion entries are created
2. Update Assigned Agent manually in Notion for existing calls
3. Use Status field to track call follow-ups (New → Read → Completed)
