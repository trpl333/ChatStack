# ChatStack System Status Dashboard

This adds live health monitoring for the four-service ecosystem:
- ChatStack (Flask/FastAPI)
- AI-Memory
- NeuroSphere SendText
- LeadFlowTracker

It checks HTTP endpoints, port reachability, systemd state, and Python processes. It writes a consolidated JSON file consumed by the admin panel.

## Files

- scripts/status_monitor.py — background monitor daemon
- config/monitor.yml — service definitions
- app/status_routes.py — Flask Blueprint exposing GET /api/status
- static/admin_status.html — standalone admin page (can embed pieces into your admin.html)
- static/js/status.js — reusable UI widget for any page
- deploy/systemd/status_monitor.service — systemd unit
- scripts/install_status_monitor.sh — installer script

## Install

1) Dependencies:

```
pip install psutil pyyaml requests
```

2) Register routes in your Flask app (app.py or main entry):

```python
from app.status_routes import status_bp
app.register_blueprint(status_bp)
```

3) Install systemd unit (on DigitalOcean droplet):

```
sudo bash scripts/install_status_monitor.sh /opt/ChatStack
```

4) Verify:

```
systemctl status status_monitor
journalctl -fu status_monitor
curl http://localhost:5000/api/status
```

5) Open the admin page:

- Standalone test: GET /static/admin_status.html
- Or embed `static/js/status.js` and call `SystemStatus.mount('#system-status')` in your existing admin panel.

## Configuration

Edit `config/monitor.yml` to adjust service URLs, ports, and systemd unit names.

Environment overrides:

- CHATSTACK_STATUS_FILE — where JSON is written (default /var/lib/chatstack/status.json)
- CHATSTACK_STATUS_STALE — stale age in seconds (default 90)

## Auto-Healing

On two consecutive failures for a service with a systemd unit, the monitor attempts a `systemctl restart <unit>`. Disable with `--no-restart`.

## Security

- Keep /api/status internal (admin-only). Add auth to your Flask app if needed.
- The monitor writes to /var/lib/chatstack; ensure permissions are restricted.

## Notes

- For LeadFlowTracker hosted on Replit, `systemd` and `port` checks are not applicable. HTTP health is used for status.
- You can extend alerting (Slack/Twilio) by adding webhooks or a notifier into the monitor later.