# ChatStack Scripts

Utility scripts for monitoring and managing the ChatStack system.

## Status Monitor

**File:** `status_monitor.py`

Monitors all services in the NeuroSphere platform and writes consolidated health status to a JSON file.

### Features

- ✅ HTTP health endpoint checks
- ✅ TCP port reachability tests
- ✅ systemd service state monitoring
- ✅ Python process detection
- ✅ Auto-healing (optional restart on failures)
- ✅ Consolidated JSON output for admin UI

### Usage

**Basic usage:**
```bash
python3 scripts/status_monitor.py
```

**Custom configuration:**
```bash
python3 scripts/status_monitor.py \
  --config config/monitor.yml \
  --status-file /var/lib/chatstack/status.json \
  --interval 30
```

**Disable auto-restart:**
```bash
python3 scripts/status_monitor.py --no-restart
```

### Configuration

Edit `config/monitor.yml` to define services to monitor:

```yaml
services:
  - key: chatstack_web
    name: "ChatStack Web"
    url: http://127.0.0.1:5000/health
    expected_http: 200
    systemd: chatstack-web.service
    process_match:
      - gunicorn
      - main:app
```

### Dependencies

```bash
pip install psutil pyyaml requests
```

### Production Deployment

Run as a systemd service:

```bash
# Create service file
sudo nano /etc/systemd/system/chatstack-monitor.service

# Add:
[Unit]
Description=ChatStack System Monitor
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/ChatStack
ExecStart=/usr/bin/python3 /opt/ChatStack/scripts/status_monitor.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable chatstack-monitor
sudo systemctl start chatstack-monitor
```

### Output Format

The monitor writes JSON to `/var/lib/chatstack/status.json`:

```json
{
  "generated_at": "2025-10-27T12:00:00Z",
  "ok_count": 3,
  "fail_count": 1,
  "total": 4,
  "services": {
    "chatstack_web": {
      "name": "ChatStack Web",
      "ok": true,
      "http": {
        "ok": true,
        "status_code": 200,
        "latency_ms": 45
      },
      "port": {"ok": true},
      "systemd": {"state": "active", "ok": true},
      "process": {"count": 2, "pids": [1234, 5678]}
    }
  }
}
```

This JSON can be consumed by the ChatStack admin UI to display service health.
