const TOKEN_KEY = "tradeshield_access_token";

const els = {
  btnRefreshOps: document.getElementById("btnRefreshOps"),
  opsMetrics: document.getElementById("opsMetrics"),
  cooldowns: document.getElementById("cooldowns"),
  runs: document.getElementById("runs"),
  opsStatus: document.getElementById("opsStatus"),
};

function setStatus(message) {
  els.opsStatus.textContent = message;
}

async function fetchJson(url) {
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) {
    throw new Error("Sign in from the dashboard first.");
  }
  const response = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json();
}

function renderMetrics(metrics, overview) {
  const items = [
    ["Runs (24h)", metrics.run_count_24h],
    ["Success Rate", `${Math.round(metrics.success_rate_24h * 100)}%`],
    ["Avg Duration", `${metrics.avg_run_duration_seconds_24h}s`],
    ["P95 Duration", `${metrics.p95_run_duration_seconds_24h}s`],
    ["Delivered Alerts", metrics.delivered_alerts_24h],
    ["Failed Alerts", metrics.failed_alerts_24h],
    ["Queued Alerts", overview.queued_alerts],
    ["Retrying Alerts", overview.retrying_alerts],
  ];
  els.opsMetrics.innerHTML = items
    .map(
      ([label, value]) => `
      <div class="metric-card">
        <div class="metric-label">${label}</div>
        <div class="metric-value">${value}</div>
      </div>`
    )
    .join("");
}

function renderCooldowns(sourceHealth) {
  const cooling = (sourceHealth || []).filter((item) => item.last_run_status === "backoff" && item.backoff_until);
  if (!cooling.length) {
    els.cooldowns.innerHTML = `<div class="empty-state">No sources are currently in cooldown.</div>`;
    return;
  }
  els.cooldowns.innerHTML = cooling
    .map(
      (item) => `
      <div class="source-row">
        <div>
          <strong>${item.source_name}</strong>
          <span>Backoff until ${new Date(item.backoff_until).toLocaleString()}</span>
        </div>
        <span class="badge high">backoff</span>
      </div>`
    )
    .join("");
}

function renderRuns(runs) {
  if (!runs.length) {
    els.runs.innerHTML = `<div class="empty-state">No ingestion runs yet.</div>`;
    return;
  }
  els.runs.innerHTML = runs
    .slice(0, 10)
    .map((run) => {
      const start = new Date(run.started_at).getTime();
      const end = run.finished_at ? new Date(run.finished_at).getTime() : start;
      const duration = Math.max(0, Math.round((end - start) / 1000));
      return `
      <div class="source-row">
        <div>
          <strong>${run.status}</strong>
          <span>${new Date(run.started_at).toLocaleString()} | ${duration}s | inserted ${run.inserted_count} | updated ${run.updated_count}</span>
        </div>
        <span class="badge ${run.status === "completed" ? "low" : "high"}">${run.trigger}</span>
      </div>`;
    })
    .join("");
}

async function refreshOps() {
  try {
    setStatus("Loading ops data...");
    const [metrics, overview, runs] = await Promise.all([
      fetchJson("/v1/ops/metrics"),
      fetchJson("/v1/ops/overview"),
      fetchJson("/v1/ops/ingestion/runs?limit=20"),
    ]);
    renderMetrics(metrics, overview);
    renderCooldowns(overview.source_health || []);
    renderRuns(runs || []);
    setStatus(`Updated ${new Date().toLocaleTimeString()}`);
  } catch (err) {
    setStatus(`Unable to load ops page: ${err.message}`);
  }
}

els.btnRefreshOps.addEventListener("click", refreshOps);
refreshOps();
