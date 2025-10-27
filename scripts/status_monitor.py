#!/usr/bin/env python3
"""
System Monitor for ChatStack multi-service platform.

Monitors:
- HTTP health endpoints for each service
- TCP port reachability
- systemd service state
- Python process matches

Writes:
- A consolidated JSON status file consumed by ChatStack's admin UI.

Auto-healing:
- Optional systemctl restart for failed services (on 2 consecutive failures).

Configuration:
- YAML file at config/monitor.yml
- CLI args: --config, --status-file, --interval, --no-restart

Dependencies:
- psutil, pyyaml, requests
"""

import argparse
import json
import os
import socket
import subprocess
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import psutil
import requests
import yaml

DEFAULT_INTERVAL = 30
DEFAULT_STATUS_FILE = os.environ.get("CHATSTACK_STATUS_FILE", "/var/lib/chatstack/status.json")
DEFAULT_CONFIG = os.environ.get("CHATSTACK_MONITOR_CONFIG", "config/monitor.yml")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def check_http(url: str, timeout: float = 3.0) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        r = requests.get(url, timeout=timeout)
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "ok": r.status_code == 200,
            "status_code": r.status_code,
            "latency_ms": latency_ms,
            "error": ""
        }
    except Exception as e:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "ok": False,
            "status_code": None,
            "latency_ms": latency_ms,
            "error": str(e)
        }


def check_port(host: str, port: int, timeout: float = 1.0) -> Dict[str, Any]:
    if not host or not port:
        return {"ok": None, "error": ""}
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, int(port)))
        s.close()
        return {"ok": True, "error": ""}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def systemctl_is_active(unit: str) -> Dict[str, Any]:
    if not unit:
        return {"state": None, "ok": None}
    try:
        res = subprocess.run(
            ["systemctl", "is-active", unit],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        state = res.stdout.strip()
        return {"state": state, "ok": state == "active"}
    except Exception as e:
        return {"state": "error", "ok": False, "error": str(e)}


def restart_service(unit: str) -> Dict[str, Any]:
    if not unit:
        return {"ok": False, "error": "no-unit"}
    try:
        res = subprocess.run(
            ["systemctl", "restart", unit],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        ok = res.returncode == 0
        return {"ok": ok, "stdout": res.stdout, "stderr": res.stderr}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def process_matches(patterns: Optional[List[str]]) -> Dict[str, Any]:
    if not patterns:
        return {"count": None, "pids": []}
    pids = []
    pats = [p for p in patterns if p]
    if not pats:
        return {"count": None, "pids": []}
    for proc in psutil.process_iter(attrs=["pid", "name", "cmdline"]):
        try:
            proc_name = (proc.info.get("name") or "").lower()
            cmdline = " ".join(proc.info.get("cmdline") or []).lower()
            for p in pats:
                pl = p.lower()
                if pl in proc_name or pl in cmdline:
                    pids.append(proc.info["pid"])
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return {"count": len(pids), "pids": pids[:20]}


def summarize_service(svc: Dict[str, Any]) -> bool:
    # Define overall OK as: http.ok is True AND (port.ok is True or None) AND (systemd.ok is True or None)
    http_ok = svc["http"]["ok"] is True
    port_ok = svc["port"]["ok"]
    sys_ok = svc["systemd"]["ok"]
    overall = http_ok and (port_ok in (True, None)) and (sys_ok in (True, None))
    return overall


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r") as f:
        cfg = yaml.safe_load(f) or {}
    if "services" not in cfg or not isinstance(cfg["services"], list):
        raise ValueError("Invalid monitor.yml: missing 'services' list.")
    return cfg


def parse_host_port_from_url(url: str) -> tuple[Optional[str], Optional[int]]:
    if not url:
        return None, None
    try:
        # http://127.0.0.1:5000/health -> host 127.0.0.1, port 5000
        without_scheme = url.split("://", 1)[1]
        host_port = without_scheme.split("/", 1)[0]
        if ":" in host_port:
            host, port = host_port.split(":")
            return host, int(port)
        return host_port, 80
    except Exception:
        return None, None


def main():
    parser = argparse.ArgumentParser(description="ChatStack system status monitor")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Path to config/monitor.yml")
    parser.add_argument("--status-file", default=DEFAULT_STATUS_FILE, help="Where to write consolidated status JSON")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL, help="Seconds between checks")
    parser.add_argument("--no-restart", action="store_true", help="Disable auto-restart on failures")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.status_file), exist_ok=True)

    cfg = load_config(args.config)
    fail_counts: Dict[str, int] = {}

    print(f"[monitor] starting with config={args.config}, status_file={args.status_file}, interval={args.interval}s")

    while True:
        cycle_started = utc_now_iso()
        services_out = {}
        ok_count = 0
        fail_count = 0

        for svc in cfg["services"]:
            key = svc["key"]
            url = svc.get("url")
            expected_http = int(svc.get("expected_http", 200)) if svc.get("expected_http") else 200
            port = svc.get("port")
            host = svc.get("host")
            systemd_unit = svc.get("systemd")
            proc_patterns = svc.get("process_match") or []
            if isinstance(proc_patterns, str):
                proc_patterns = [proc_patterns]

            http_res = {"ok": None, "status_code": None, "latency_ms": None, "error": ""}
            if url:
                http_res = check_http(url)

            # If port not explicitly provided, infer from URL
            port_res = {"ok": None, "error": ""}
            if port or url:
                if not host and url:
                    host, inf_port = parse_host_port_from_url(url)
                    port = port or inf_port
                if host and port:
                    port_res = check_port(host, port)

            sys_res = systemctl_is_active(systemd_unit)
            proc_res = process_matches(proc_patterns)

            svc_out = {
                "name": svc.get("name") or key,
                "key": key,
                "http": {
                    **http_res,
                    "expected_status": expected_http
                },
                "port": port_res,
                "systemd": sys_res,
                "process": proc_res,
                "last_checked": cycle_started
            }

            overall_ok = summarize_service(svc_out)
            svc_out["ok"] = overall_ok

            if overall_ok:
                ok_count += 1
                fail_counts[key] = 0
            else:
                fail_count += 1
                fail_counts[key] = fail_counts.get(key, 0) + 1
                # Auto-heal on 2 consecutive failures if allowed
                if not args.no_restart and systemd_unit and fail_counts[key] >= 2:
                    heal = restart_service(systemd_unit)
                    svc_out["auto_restart_attempted"] = True
                    svc_out["auto_restart_result"] = heal
                    # reset count post-attempt
                    fail_counts[key] = 0

            services_out[key] = svc_out

        out = {
            "generated_at": cycle_started,
            "ok_count": ok_count,
            "fail_count": fail_count,
            "total": len(cfg["services"]),
            "services": services_out,
            "host": os.uname().nodename if hasattr(os, "uname") else "",
            "version": "1.0.0"
        }

        tmp = args.status_file + ".tmp"
        with open(tmp, "w") as f:
            json.dump(out, f, indent=2)
        os.replace(tmp, args.status_file)

        print(f"[monitor] wrote {args.status_file} at {cycle_started} (ok={ok_count}, fail={fail_count})")
        time.sleep(max(5, args.interval))


if __name__ == "__main__":
    main()
