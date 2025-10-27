// Reusable module to render system status into any container on admin pages.
// Usage:
//   <div id="system-status"></div>
//   <script src="/static/js/status.js"></script>
//   <script>SystemStatus.mount('#system-status');</script>
window.SystemStatus = (() => {
  const tplCard = (s) => {
    const http = s.http || {};
    const port = s.port || {};
    const sysd = s.systemd || {};
    const proc = s.process || {};
    return `
      <div class="cs-card ${s.ok ? 'ok' : 'fail'}">
        <div class="cs-head">
          <div><strong>${s.name}</strong><div class="cs-sub">${s.key}</div></div>
          <span class="cs-pill ${s.ok ? 'ok' : 'fail'}">${s.ok ? 'OK' : 'ISSUE'}</span>
        </div>
        <div class="cs-kv">HTTP: ${http.ok === null ? 'n/a' : (http.ok ? '200 OK' : (http.status_code || 'ERR'))} • ${http.latency_ms ?? '—'} ms</div>
        <div class="cs-kv">Port: ${port.ok === null ? 'n/a' : (port.ok ? 'open' : 'closed')}</div>
        <div class="cs-kv">Systemd: ${sysd.state ?? 'n/a'}</div>
        <div class="cs-kv">Processes: ${proc.count ?? 'n/a'}</div>
        <div class="cs-kv">Checked: ${s.last_checked ? new Date(s.last_checked).toLocaleTimeString() : '—'}</div>
      </div>
    `;
  };

  const styles = `
    .cs-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(240px,1fr)); gap:12px; }
    .cs-card { border-radius:12px; padding:12px; background:#111927; border:1px solid #1f2a3a; color:#e6eef8; }
    .cs-card.ok { border-color:#1f6f43; background:#0e1d17; }
    .cs-card.fail { border-color:#7a1f1f; background:#1a0f12; }
    .cs-head { display:flex; align-items:center; justify-content:space-between; margin-bottom:6px; }
    .cs-sub { font-size:12px; color:#9fb3c8; }
    .cs-kv { font-family:ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; font-size:12px; color:#cfe6ff; }
    .cs-pill { display:inline-block; padding:2px 8px; border-radius:999px; font-size:12px; font-weight:600; }
    .cs-pill.ok { background:#0a3; color:#eafff3; }
    .cs-pill.fail { background:#a00; color:#ffecec; }
  `;

  const mount = async (selector, opts = {}) => {
    const root = document.querySelector(selector);
    if (!root) return;
    const style = document.createElement('style');
    style.innerHTML = styles;
    document.head.appendChild(style);

    const grid = document.createElement('div');
    grid.className = 'cs-grid';
    root.appendChild(grid);

    const load = async () => {
      try {
        const res = await fetch('/api/status', { cache: 'no-store' });
        const data = await res.json();
        const svcs = Object.values(data.services || {});
        svcs.sort((a,b) => a.name.localeCompare(b.name));
        grid.innerHTML = svcs.map(tplCard).join('');
      } catch (e) {
        grid.innerHTML = '<div class="cs-card fail">Failed to load /api/status</div>';
        console.error(e);
      }
    };

    await load();
    const interval = opts.intervalMs || 15000;
    setInterval(load, interval);
  };

  return { mount };
})();