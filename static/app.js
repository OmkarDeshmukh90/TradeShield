const TOKEN_KEY = "tradeshield_access_token";
const API_BASE = (window.__TRADESHIELD_CONFIG__?.apiBaseUrl || "").replace(/\/+$/, "");
const OFFLINE_DEMO_FORCED =
  window.__TRADESHIELD_CONFIG__?.offlineDemo === true || new URLSearchParams(window.location.search).get("offline") === "1";
const nativeFetch = window.fetch.bind(window);
const BACKEND_WAKE_TIMEOUT_MS = 70000;
const BACKEND_WAKE_POLL_MS = 5000;
const BACKEND_HEALTH_PROBE_TIMEOUT_MS = 2500;
const DEFAULT_INDUSTRIES = [
  "Oil, Gas, and Petrochemicals",
  "Pharmaceuticals and APIs",
  "Electronics and Semiconductors",
  "Automotive and Auto Components",
  "Chemicals and Specialty Chemicals",
  "Fertilizers and Agri-inputs",
  "Food and Edible Oils",
  "Metals and Steel",
  "Textiles and Apparel",
  "Renewable Energy Equipment",
];
let backendWakePromise = null;
let offlineDataPromise = null;

const state = {
  accessToken: "",
  clientId: "",
  clientName: "",
  user: null,
  riskItems: [],
  playbookId: "",
  step: 1,
  industries: [...DEFAULT_INDUSTRIES],
  opsOverview: null,
  users: [],
  alertPolicies: [],
  supplyMap: null,
  currentEventId: "",
  demoMode: false,
  demoScenario: "all",
  currentView: "control",
  presentationMode: false,
  backendStatus: "sleeping",
  offlineDemoActive: false,
};

const els = {
  status: document.getElementById("status"),
  metrics: document.getElementById("metrics"),
  events: document.getElementById("events"),
  eventsSub: document.getElementById("eventsSub"),
  risk: document.getElementById("risk"),
  checklist: document.getElementById("checklist"),
  playbookPane: document.getElementById("playbookPane"),
  modal: document.getElementById("onboardingModal"),
  progressLabel: document.getElementById("progressLabel"),
  progressFill: document.getElementById("progressFill"),
  form: document.getElementById("onboardingForm"),
  industrySelect: document.getElementById("industrySelect"),
  btnPrevStep: document.getElementById("btnPrevStep"),
  btnNextStep: document.getElementById("btnNextStep"),
  loginEmail: document.getElementById("loginEmail"),
  loginPassword: document.getElementById("loginPassword"),
  btnLogoutTop: document.getElementById("btnLogoutTop"),
  opsSummary: document.getElementById("opsSummary"),
  sourceHealth: document.getElementById("sourceHealth"),
  teamList: document.getElementById("teamList"),
  teamForm: document.getElementById("teamForm"),
  teamName: document.getElementById("teamName"),
  teamEmail: document.getElementById("teamEmail"),
  teamRole: document.getElementById("teamRole"),
  teamPassword: document.getElementById("teamPassword"),
  btnRunIngestion: document.getElementById("btnRunIngestion"),
  btnDispatchAlerts: document.getElementById("btnDispatchAlerts"),
  btnAddUser: document.getElementById("btnAddUser"),
  demoBadge: document.getElementById("demoBadge"),
  demoScenarioSelect: document.getElementById("demoScenarioSelect"),
  btnToggleDemoMode: document.getElementById("btnToggleDemoMode"),
  explainabilityPane: document.getElementById("explainabilityPane"),
  supplyMapSummary: document.getElementById("supplyMapSummary"),
  supplyMapQuickForm: document.getElementById("supplyMapQuickForm"),
  quickSupplierName: document.getElementById("quickSupplierName"),
  quickSupplierCountry: document.getElementById("quickSupplierCountry"),
  quickSupplierRegion: document.getElementById("quickSupplierRegion"),
  quickSupplierCommodity: document.getElementById("quickSupplierCommodity"),
  quickLaneOrigin: document.getElementById("quickLaneOrigin"),
  quickLaneDestination: document.getElementById("quickLaneDestination"),
  quickSkuName: document.getElementById("quickSkuName"),
  quickSkuCategory: document.getElementById("quickSkuCategory"),
  btnLoadSupplyMap: document.getElementById("btnLoadSupplyMap"),
  supplyMapCsvForm: document.getElementById("supplyMapCsvForm"),
  csvSuppliers: document.getElementById("csvSuppliers"),
  csvLanes: document.getElementById("csvLanes"),
  csvSkuGroups: document.getElementById("csvSkuGroups"),
  policyList: document.getElementById("policyList"),
  policyForm: document.getElementById("policyForm"),
  policyChannel: document.getElementById("policyChannel"),
  policyTarget: document.getElementById("policyTarget"),
  policySeverity: document.getElementById("policySeverity"),
  policyRegions: document.getElementById("policyRegions"),
  policyIndustries: document.getElementById("policyIndustries"),
  policyActive: document.getElementById("policyActive"),
  workflowPane: document.getElementById("workflowPane"),
  heroKpis: document.getElementById("heroKpis"),
  viewTabs: Array.from(document.querySelectorAll(".tab-btn")),
  viewPanels: Array.from(document.querySelectorAll("[data-view-panel]")),
  btnPresentationMode: document.getElementById("btnPresentationMode"),
  wizardHint: document.getElementById("wizardHint"),
  btnPrefillSample: document.getElementById("btnPrefillSample"),
  opsLink: document.getElementById("opsLink"),
  btnWakeServer: document.getElementById("btnWakeServer"),
  backendStatusPill: document.getElementById("backendStatusPill"),
  offlineModeBadge: document.getElementById("offlineModeBadge"),
};

function withApiBase(url) {
  if (typeof url !== "string") return url;
  if (!API_BASE) return url;
  if (url.startsWith("http://") || url.startsWith("https://")) return url;
  if (!url.startsWith("/")) return `${API_BASE}/${url}`;
  return `${API_BASE}${url}`;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForBackendWake() {
  const deadline = Date.now() + BACKEND_WAKE_TIMEOUT_MS;
  while (Date.now() < deadline) {
    try {
      const res = await nativeFetch(withApiBase("/healthz"), { method: "GET" });
      if (res.status < 600) {
        return true;
      }
    } catch (_err) {
      // ignore and retry until timeout
    }
    await sleep(BACKEND_WAKE_POLL_MS);
  }
  return false;
}

async function probeBackendOnce() {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), BACKEND_HEALTH_PROBE_TIMEOUT_MS);
    const res = await nativeFetch(withApiBase("/healthz"), {
      method: "GET",
      signal: controller.signal,
    });
    clearTimeout(timeout);
    return res.status < 600;
  } catch (_err) {
    return false;
  }
}

function renderBackendStatus() {
  if (!els.backendStatusPill) return;
  const status = state.backendStatus || "sleeping";
  const label =
    status === "awake" ? "Backend: awake" : status === "waking" ? "Backend: waking..." : "Backend: sleeping";
  els.backendStatusPill.textContent = label;
  els.backendStatusPill.classList.remove("backend-pill-awake", "backend-pill-waking", "backend-pill-sleeping");
  els.backendStatusPill.classList.add(`backend-pill-${status}`);
  if (els.btnWakeServer) {
    const waking = status === "waking";
    const disabled = state.offlineDemoActive || waking;
    els.btnWakeServer.disabled = disabled;
    els.btnWakeServer.textContent = state.offlineDemoActive
      ? "Offline Active"
      : waking
      ? "Waking..."
      : status === "awake"
      ? "Wake Check"
      : "Wake Server";
  }
}

function setBackendStatus(status) {
  state.backendStatus = status;
  renderBackendStatus();
}

async function wakeBackend(trigger = "manual") {
  if (state.offlineDemoActive) {
    setBackendStatus("sleeping");
    if (trigger === "manual") {
      setStatus("Offline demo mode is active. Backend wake is not required.");
    }
    return true;
  }
  if (!API_BASE) {
    setBackendStatus("awake");
    return true;
  }
  const alreadyAwake = await probeBackendOnce();
  if (alreadyAwake) {
    setBackendStatus("awake");
    if (trigger === "manual") {
      setStatus("Backend is already awake.");
    }
    return true;
  }
  if (backendWakePromise) return backendWakePromise;
  backendWakePromise = (async () => {
    setBackendStatus("waking");
    if (trigger === "manual") {
      setStatus("Waking backend server...");
    }
    const woke = await waitForBackendWake();
    setBackendStatus(woke ? "awake" : "sleeping");
    if (trigger === "manual") {
      setStatus(woke ? "Backend is awake. You can continue." : "Backend did not wake yet. Retry in 30-60 seconds.");
    }
    return woke;
  })();
  try {
    return await backendWakePromise;
  } finally {
    backendWakePromise = null;
  }
}

function renderOfflineModeBadge() {
  if (!els.offlineModeBadge) return;
  els.offlineModeBadge.classList.toggle("hidden", !state.offlineDemoActive);
}

function deepClone(value) {
  return JSON.parse(JSON.stringify(value));
}

function offlineStorageKey() {
  return "tradeshield_offline_store_v1";
}

function readOfflineStore() {
  try {
    const raw = localStorage.getItem(offlineStorageKey());
    return raw ? JSON.parse(raw) : null;
  } catch (_err) {
    return null;
  }
}

function writeOfflineStore(value) {
  try {
    localStorage.setItem(offlineStorageKey(), JSON.stringify(value));
  } catch (_err) {
    // ignore storage write issues
  }
}

async function loadOfflineData() {
  if (offlineDataPromise) return offlineDataPromise;
  offlineDataPromise = (async () => {
    const response = await nativeFetch("./demo-fixtures/offline-demo.json");
    if (!response.ok) {
      throw new Error("Offline fixture file is missing.");
    }
    const base = await response.json();
    const stored = readOfflineStore();
    if (stored) return stored;
    const seeded = {
      ...base,
      demo: { demo_mode: true, demo_scenario: "all" },
      current_session: deepClone(base.session),
      current_playbook: null,
      workflow_state: deepClone(base.workflow),
      supply_map_state: deepClone(base.supply_map),
      policies_state: deepClone(base.policies || []),
      users_state: deepClone(base.users || []),
    };
    writeOfflineStore(seeded);
    return seeded;
  })();
  return offlineDataPromise;
}

async function getOfflineData() {
  const store = await loadOfflineData();
  if (!store.demo) store.demo = { demo_mode: true, demo_scenario: "all" };
  if (!store.workflow_state) store.workflow_state = deepClone(store.workflow || {});
  if (!store.supply_map_state) store.supply_map_state = deepClone(store.supply_map || {});
  if (!store.policies_state) store.policies_state = deepClone(store.policies || []);
  if (!store.users_state) store.users_state = deepClone(store.users || []);
  if (!store.current_session) store.current_session = deepClone(store.session || {});
  writeOfflineStore(store);
  return store;
}

function nowIso() {
  return new Date().toISOString();
}

function offlineDashboardSummary(store) {
  const events = store.events || [];
  const highestRisk = Math.max(...(store.risk_items || []).map((item) => Number(item.risk_score || 0)), 0);
  const avgSeverity =
    events.length > 0 ? events.reduce((acc, item) => acc + Number(item.severity || 0), 0) / events.length : 0;
  return {
    open_events: events.length,
    average_severity: avgSeverity,
    highest_risk_score: highestRisk,
    latest_events: events,
  };
}

function pickOfflinePlaybook(store, eventId) {
  const playbook = (store.playbooks || {})[eventId];
  if (!playbook) return null;
  const withClient = { ...playbook, client_id: store.current_session?.client?.id || "client-demo-001" };
  return deepClone(withClient);
}

function parseQuery(url) {
  const [, queryString = ""] = String(url).split("?");
  return new URLSearchParams(queryString);
}

async function offlineApi(url, options = {}) {
  const store = await getOfflineData();
  const method = String(options.method || "GET").toUpperCase();
  const path = String(url).split("?")[0];
  const payload = options.body ? JSON.parse(options.body) : null;
  const session = store.current_session || {};
  const clientId = session.client?.id || "client-demo-001";

  if (path === "/v1/industries" && method === "GET") {
    return { industries: store.industries || DEFAULT_INDUSTRIES };
  }
  if (path === "/v1/demo/status" && method === "GET") {
    return deepClone(store.demo);
  }
  if (path === "/v1/demo/status" && method === "POST") {
    store.demo.demo_mode = Boolean(payload?.demo_mode);
    store.demo.demo_scenario = payload?.demo_scenario || "all";
    writeOfflineStore(store);
    return deepClone(store.demo);
  }
  if (path === "/v1/auth/login" && method === "POST") {
    const email = String(payload?.email || "").toLowerCase();
    const user = (store.users_state || []).find((item) => String(item.email || "").toLowerCase() === email);
    if (!user) throw new Error("Invalid email or password.");
    store.current_session = {
      access_token: "offline-demo-token",
      client: deepClone(store.session.client),
      user: deepClone(user),
    };
    writeOfflineStore(store);
    return deepClone(store.current_session);
  }
  if (path === "/v1/auth/register" && method === "POST") {
    const fullName = payload?.full_name || "Demo User";
    const email = payload?.email || "demo.user@tradeshield.local";
    const createdUser = {
      id: `user-${Date.now()}`,
      full_name: fullName,
      email,
      role: "admin",
      is_active: true,
    };
    store.session.client.name = payload?.company_name || "Demo Workspace";
    store.session.client.industry = payload?.industry || store.session.client.industry;
    store.users_state.unshift(createdUser);
    store.current_session = {
      access_token: "offline-demo-token",
      client: deepClone(store.session.client),
      user: deepClone(createdUser),
    };
    writeOfflineStore(store);
    return deepClone(store.current_session);
  }
  if (path === "/v1/auth/me" && method === "GET") {
    return {
      client: deepClone(store.current_session.client || store.session.client),
      user: deepClone(store.current_session.user || store.session.user),
    };
  }
  if (path === "/v1/dashboard/summary" && method === "GET") {
    return offlineDashboardSummary(store);
  }
  if (path.startsWith(`/v1/clients/${clientId}/risk-scores`) && method === "GET") {
    return { items: deepClone(store.risk_items || []) };
  }
  if (path === "/v1/ops/overview" && method === "GET") {
    const ops = deepClone(store.ops_overview || {});
    ops.active_users = (store.users_state || []).filter((user) => user.is_active).length;
    return ops;
  }
  if (path === "/v1/users" && method === "GET") {
    return deepClone(store.users_state || []);
  }
  if (path === "/v1/users" && method === "POST") {
    const user = {
      id: `user-${Date.now()}`,
      full_name: payload?.full_name || "New User",
      email: payload?.email || "new.user@tradeshield.local",
      role: payload?.role || "viewer",
      is_active: true,
    };
    store.users_state.push(user);
    writeOfflineStore(store);
    return deepClone(user);
  }
  if (path === `/v1/clients/${clientId}/supply-map` && method === "GET") {
    return deepClone(store.supply_map_state);
  }
  if (path === `/v1/clients/${clientId}/supply-map` && method === "POST") {
    const map = store.supply_map_state;
    map.supply_map_version = Number(map.supply_map_version || 1) + 1;
    map.suppliers = [...(map.suppliers || []), ...(payload?.suppliers || []).map((item, idx) => ({ id: `sup-${Date.now()}-${idx}`, ...item }))];
    map.lanes = [...(map.lanes || []), ...(payload?.lanes || []).map((item, idx) => ({ id: `lane-${Date.now()}-${idx}`, ...item }))];
    map.sku_groups = [
      ...(map.sku_groups || []),
      ...(payload?.sku_groups || []).map((item, idx) => ({ id: `sku-${Date.now()}-${idx}`, ...item })),
    ];
    writeOfflineStore(store);
    return deepClone(map);
  }
  if (path === `/v1/clients/${clientId}/supply-map/import-csv` && method === "POST") {
    store.supply_map_state.supply_map_version = Number(store.supply_map_state.supply_map_version || 1) + 1;
    writeOfflineStore(store);
    return deepClone(store.supply_map_state);
  }
  if (path === "/v1/alerts/subscriptions" && method === "GET") {
    return deepClone(store.policies_state || []);
  }
  if (path === "/v1/alerts/subscriptions" && method === "POST") {
    const policy = { id: `pol-${Date.now()}`, ...payload };
    store.policies_state.push(policy);
    writeOfflineStore(store);
    return deepClone(policy);
  }
  if (path.startsWith("/v1/alerts/subscriptions/") && method === "PATCH") {
    const policyId = path.split("/").pop();
    const policy = (store.policies_state || []).find((item) => item.id === policyId);
    if (policy) Object.assign(policy, payload || {});
    writeOfflineStore(store);
    return deepClone(policy || {});
  }
  if (path.startsWith("/v1/alerts/subscriptions/") && method === "DELETE") {
    const policyId = path.split("/").pop();
    store.policies_state = (store.policies_state || []).filter((item) => item.id !== policyId);
    writeOfflineStore(store);
    return null;
  }
  if (path === "/v1/ingestion/run" && method === "POST") {
    store.ops_overview.latest_run = {
      status: "completed",
      started_at: nowIso(),
      finished_at: nowIso(),
    };
    store.ops_overview.queued_alerts = 2;
    writeOfflineStore(store);
    return { inserted_count: 1, updated_count: 1, queued_alerts: 2 };
  }
  if (path === "/v1/alerts/dispatch" && method === "POST") {
    store.ops_overview.queued_alerts = 0;
    writeOfflineStore(store);
    return { delivered_count: 2, retry_count: 0, failed_count: 0, blocked_count: 0 };
  }

  const playbookGenerateMatch = path.match(/^\/v1\/clients\/([^/]+)\/playbooks\/generate$/);
  if (playbookGenerateMatch && method === "POST") {
    const eventId = payload?.event_id;
    const playbook = pickOfflinePlaybook(store, eventId);
    if (!playbook) throw new Error("No offline playbook for this event.");
    store.current_playbook = playbook.id;
    writeOfflineStore(store);
    return playbook;
  }

  const playbookReadMatch = path.match(/^\/v1\/playbooks\/([^/]+)$/);
  if (playbookReadMatch && method === "GET") {
    const playbookId = playbookReadMatch[1];
    const found = Object.values(store.playbooks || {}).find((item) => item.id === playbookId);
    return deepClone(found || null);
  }

  const playbookBriefMatch = path.match(/^\/v1\/playbooks\/([^/]+)\/brief$/);
  if (playbookBriefMatch && method === "GET") {
    const playbookId = playbookBriefMatch[1];
    const found = Object.values(store.playbooks || {}).find((item) => item.id === playbookId);
    if (!found) return "No brief available.";
    return `Decision brief (offline demo)\nPlaybook: ${found.id}\nRecommended option: ${found.recommended_option}`;
  }

  const explainMatch = path.match(/^\/v1\/clients\/([^/]+)\/events\/([^/]+)\/explainability$/);
  if (explainMatch && method === "GET") {
    const eventId = explainMatch[2];
    return deepClone(store.explainability?.[eventId] || null);
  }

  const approvalsMatch = path.match(/^\/v1\/playbooks\/([^/]+)\/approvals$/);
  if (approvalsMatch && method === "GET") {
    const playbookId = approvalsMatch[1];
    return deepClone(store.workflow_state?.approvals_by_playbook?.[playbookId] || []);
  }

  const approvalPatchMatch = path.match(/^\/v1\/playbooks\/([^/]+)\/approvals\/([^/]+)$/);
  if (approvalPatchMatch && method === "PATCH") {
    const playbookId = approvalPatchMatch[1];
    const approvalId = approvalPatchMatch[2];
    const approvals = store.workflow_state?.approvals_by_playbook?.[playbookId] || [];
    const approval = approvals.find((item) => item.id === approvalId);
    if (approval) {
      approval.status = payload?.status || approval.status;
      approval.decision_note = payload?.decision_note || `Updated to ${approval.status}`;
    }
    writeOfflineStore(store);
    return deepClone(approval || {});
  }

  const commentsMatch = path.match(/^\/v1\/playbooks\/([^/]+)\/comments$/);
  if (commentsMatch && method === "GET") {
    const playbookId = commentsMatch[1];
    return deepClone(store.workflow_state?.comments_by_playbook?.[playbookId] || []);
  }
  if (commentsMatch && method === "POST") {
    const playbookId = commentsMatch[1];
    const comment = {
      id: `cmt-${Date.now()}`,
      comment: payload?.comment || "",
      created_at: nowIso(),
    };
    if (!store.workflow_state.comments_by_playbook[playbookId]) {
      store.workflow_state.comments_by_playbook[playbookId] = [];
    }
    store.workflow_state.comments_by_playbook[playbookId].push(comment);
    writeOfflineStore(store);
    return deepClone(comment);
  }

  const outcomeMatch = path.match(/^\/v1\/clients\/([^/]+)\/events\/([^/]+)\/outcome$/);
  if (outcomeMatch && method === "GET") {
    const eventId = outcomeMatch[2];
    return deepClone(store.workflow_state?.outcomes_by_event?.[eventId] || null);
  }
  if (outcomeMatch && method === "POST") {
    const eventId = outcomeMatch[2];
    store.workflow_state.outcomes_by_event[eventId] = {
      ...(store.workflow_state.outcomes_by_event[eventId] || {}),
      ...payload,
    };
    writeOfflineStore(store);
    return deepClone(store.workflow_state.outcomes_by_event[eventId]);
  }

  if (path.startsWith("/v1/clients/") && path.includes("/exposures") && method === "GET") {
    return { items: [] };
  }

  throw new Error(`Offline mode does not support: ${method} ${path}`);
}

function setStatus(message) {
  els.status.textContent = message;
}

function setWizardHint(message) {
  if (els.wizardHint) {
    els.wizardHint.textContent = message;
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function severityBand(value) {
  if (value >= 0.85) return "critical";
  if (value >= 0.65) return "high";
  if (value >= 0.45) return "medium";
  return "low";
}

function scoreToPercent(value) {
  return `${Math.round((value || 0) * 100)}%`;
}

function typeLabel(value) {
  const map = {
    "tariff/policy": "Tariff or policy change",
    "conflict/security": "Conflict or security risk",
    "disaster/weather": "Weather or natural hazard",
    "logistics congestion": "Logistics congestion",
    "sanctions/compliance": "Sanctions or compliance shift",
    "operational incidents": "Operational incident",
    other: "Market signal",
  };
  return map[value] || "Market signal";
}

function whyItMatters(type) {
  const map = {
    "tariff/policy": "May increase landed cost and delay customs clearance decisions.",
    "conflict/security": "May disrupt routes, insurance terms, and shipment reliability.",
    "disaster/weather": "May create immediate production or transport interruption.",
    "logistics congestion": "May increase queue time, lead time, and freight volatility.",
    "sanctions/compliance": "May require urgent supplier and counterparty checks.",
    "operational incidents": "May impact availability from specific suppliers or facilities.",
    other: "May affect planning certainty across your supply chain.",
  };
  return map[type] || map.other;
}

function firstMove(type) {
  const map = {
    "tariff/policy": "Review alternate sourcing and rework landed-cost assumptions.",
    "conflict/security": "Prepare alternate lane booking and secure contingency capacity.",
    "disaster/weather": "Prioritize critical SKUs and increase near-term buffer inventory.",
    "logistics congestion": "Re-sequence shipments by customer criticality and ETA risk.",
    "sanctions/compliance": "Run supplier compliance checks before next release cycle.",
    "operational incidents": "Validate supplier recovery timeline and backup production options.",
    other: "Escalate to planning lead and monitor confidence updates.",
  };
  return map[type] || map.other;
}

function priorityText(score) {
  if (score >= 0.8) return "Immediate executive decision recommended";
  if (score >= 0.65) return "Priority action needed in this shift";
  if (score >= 0.45) return "Monitor closely and prepare fallback options";
  return "Low urgency, keep under watch";
}

function formatDate(value) {
  return new Date(value).toLocaleString();
}

function hasSession() {
  return Boolean(state.accessToken && state.clientId);
}

function canRunOps() {
  return hasSession() && ["admin", "analyst"].includes(state.user?.role);
}

function canManageUsers() {
  return hasSession() && state.user?.role === "admin";
}

function saveSession(authResponse) {
  state.accessToken = authResponse.access_token;
  state.clientId = authResponse.client.id;
  state.clientName = authResponse.client.name;
  state.user = authResponse.user;
  localStorage.setItem(TOKEN_KEY, state.accessToken);
  updateAuthUi();
}

function clearSession() {
  state.accessToken = "";
  state.clientId = "";
  state.clientName = "";
  state.user = null;
  state.riskItems = [];
  state.playbookId = "";
  state.opsOverview = null;
  state.users = [];
  state.alertPolicies = [];
  state.supplyMap = null;
  state.demoMode = false;
  state.demoScenario = "all";
  state.currentView = "control";
  state.presentationMode = false;
  localStorage.removeItem(TOKEN_KEY);
  els.loginPassword.value = "";
  updateAuthUi();
  renderDemoStatus();
  applyView();
  applyPresentationMode();
}

function applyView() {
  els.viewTabs.forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.view === state.currentView);
  });
  els.viewPanels.forEach((panel) => {
    const views = (panel.dataset.viewPanel || "")
      .split(" ")
      .map((item) => item.trim())
      .filter(Boolean);
    const shouldShow = !views.length || views.includes(state.currentView);
    panel.classList.toggle("hidden", !shouldShow);
  });
}

function applyPresentationMode() {
  document.body.classList.toggle("presentation-mode", state.presentationMode);
  if (els.btnPresentationMode) {
    els.btnPresentationMode.textContent = state.presentationMode ? "Exit Presentation" : "Presentation Mode";
  }
}

function updateAuthUi() {
  els.btnLogoutTop.classList.toggle("hidden", !hasSession());
  els.btnRunIngestion.disabled = !canRunOps();
  els.btnDispatchAlerts.disabled = !canRunOps();

  const teamFormFields = [els.teamName, els.teamEmail, els.teamRole, els.teamPassword, els.btnAddUser];
  teamFormFields.forEach((field) => {
    field.disabled = !canManageUsers();
  });

  const supplyMapControls = [
    els.btnLoadSupplyMap,
    els.quickSupplierName,
    els.quickSupplierCountry,
    els.quickSupplierRegion,
    els.quickSupplierCommodity,
    els.quickLaneOrigin,
    els.quickLaneDestination,
    els.quickSkuName,
    els.quickSkuCategory,
    els.csvSuppliers,
    els.csvLanes,
    els.csvSkuGroups,
  ];
  supplyMapControls.forEach((field) => {
    field.disabled = !hasSession();
  });

  const policyControls = [
    els.policyChannel,
    els.policyTarget,
    els.policySeverity,
    els.policyRegions,
    els.policyIndustries,
    els.policyActive,
  ];
  policyControls.forEach((field) => {
    field.disabled = !canManageUsers();
  });
  els.btnToggleDemoMode.disabled = !canManageUsers();
  els.demoScenarioSelect.disabled = !canManageUsers();
  if (els.btnWakeServer) {
    els.btnWakeServer.disabled = state.offlineDemoActive;
  }
}

function fieldLabel(field) {
  const labels = {
    password: "Password",
    email: "Email",
    full_name: "Full name",
    company_name: "Company name",
  };
  return labels[field] || field.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function parseApiError(status, text) {
  let payload = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch (_err) {
    payload = null;
  }

  if (payload?.detail && typeof payload.detail === "string") {
    return payload.detail;
  }

  if (Array.isArray(payload?.detail) && payload.detail.length > 0) {
    const first = payload.detail[0];
    const field = Array.isArray(first?.loc) ? first.loc[first.loc.length - 1] : "field";
    const label = fieldLabel(String(field));
    if (first?.type === "string_too_short" && first?.ctx?.min_length) {
      return `${label} must be at least ${first.ctx.min_length} characters.`;
    }
    if (first?.type === "value_error.missing") {
      return `${label} is required.`;
    }
    if (first?.msg) {
      return `${label}: ${first.msg}`;
    }
  }

  if (status === 401) return "Invalid email or password.";
  if (status === 403) return "You do not have permission to do this action.";
  if (status === 404) return "Requested record was not found.";
  if (status === 409) return "A record with this information already exists.";
  if (status === 422) return "Some input values are invalid. Please review and try again.";
  if (status >= 500) return "Server error. Please try again in a moment.";

  return text || "Request failed";
}

async function fetchJson(url, options = {}) {
  if (state.offlineDemoActive) {
    return offlineApi(url, options);
  }
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (state.accessToken) {
    headers.Authorization = `Bearer ${state.accessToken}`;
  }
  const method = String(options.method || "GET").toUpperCase();
  const canRetryAfterWake = method === "GET" || method === "HEAD";
  let response;
  try {
    response = await nativeFetch(withApiBase(url), { ...options, headers });
  } catch (_error) {
    if (OFFLINE_DEMO_FORCED) {
      state.offlineDemoActive = true;
      renderOfflineModeBadge();
      setBackendStatus("sleeping");
      setStatus("Offline demo mode active. Showing simulated data.");
      return offlineApi(url, options);
    }
    if (canRetryAfterWake) {
      setBackendStatus("waking");
      setStatus("Backend is waking up. Please wait...");
      const woke = await wakeBackend("auto");
      if (woke) {
        setBackendStatus("awake");
        response = await nativeFetch(withApiBase(url), { ...options, headers });
      } else {
        setBackendStatus("sleeping");
        throw new Error("Backend is sleeping or unavailable. Wait 30-60 seconds and retry.");
      }
    } else {
      setBackendStatus("sleeping");
      throw new Error("Backend is sleeping or unavailable. Wait 30-60 seconds and retry.");
    }
  }
  if (API_BASE) {
    setBackendStatus("awake");
  }
  if (!response.ok) {
    const text = await response.text();
    if (response.status === 401 && state.accessToken) {
      clearSession();
    }
    throw new Error(parseApiError(response.status, text));
  }
  if (response.status === 204) {
    return null;
  }
  const text = await response.text();
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch (_err) {
    return text;
  }
}

function renderMetrics(summary) {
  const avgSeverity = summary?.average_severity || 0;
  const highestRisk = summary?.highest_risk_score || 0;
  const cards = [
    {
      label: "Workspace",
      value: hasSession() ? state.clientName || "Connected" : "Sign in required",
      note: hasSession() ? `Signed in as ${state.user?.full_name || "user"}` : "Create an account or sign in to see personalized intelligence",
      spark: hasSession() ? 0.82 : 0.2,
    },
    {
      label: "Disruptions Tracked",
      value: String(summary?.open_events ?? 0),
      note: "Signals from conflict, policy, weather, and logistics sources",
      spark: Math.min(1, (summary?.open_events || 0) / 10),
    },
    {
      label: "Average Disruption Intensity",
      value: severityBand(avgSeverity),
      note: `Current average severity: ${scoreToPercent(avgSeverity)}`,
      spark: avgSeverity,
    },
    {
      label: "Highest Risk In View",
      value: scoreToPercent(highestRisk),
      note: hasSession() ? "Calculated for your workspace only" : "Available after sign in",
      spark: highestRisk,
    },
  ];

  els.metrics.innerHTML = cards
    .map(
      (card) => `
        <div class="metric-card">
          <div class="metric-label">${escapeHtml(card.label)}</div>
          <div class="metric-value">${escapeHtml(card.value)}</div>
          <div class="metric-spark"><span style="width:${Math.max(8, Math.round((card.spark || 0) * 100))}%"></span></div>
          <div class="metric-note">${escapeHtml(card.note)}</div>
        </div>
      `
    )
    .join("");

  if (els.heroKpis) {
    els.heroKpis.innerHTML = `
      <div class="hero-kpi"><span>Open disruptions</span><strong>${escapeHtml(String(summary?.open_events ?? 0))}</strong></div>
      <div class="hero-kpi"><span>Avg severity</span><strong>${escapeHtml(scoreToPercent(avgSeverity))}</strong></div>
      <div class="hero-kpi"><span>Highest risk</span><strong>${escapeHtml(scoreToPercent(highestRisk))}</strong></div>
    `;
  }
}

function renderChecklist() {
  const items = [
    {
      done: hasSession(),
      title: "Secure workspace created",
      detail: "Your tenant, admin user, and signed session are active.",
    },
    {
      done: hasSession(),
      title: "Supply map basics added",
      detail: "At least one supplier, route, and product group is on file.",
    },
    {
      done: state.riskItems.length > 0,
      title: "Priority insights generated",
      detail: "TradeShield has calculated current exposures for your workspace.",
    },
    {
      done: Boolean(state.playbookId),
      title: "First action plan generated",
      detail: "You have a recommended response with next actions.",
    },
  ];

  els.checklist.innerHTML = items
    .map(
      (item) => `
      <div class="check-item ${item.done ? "done" : "pending"}">
        <span class="check-icon">${item.done ? "OK" : "."}</span>
        <div class="check-text">
          <strong>${escapeHtml(item.title)}</strong>
          <span>${escapeHtml(item.detail)}</span>
        </div>
      </div>
    `
    )
    .join("");
}

function renderEvents(events) {
  if (!hasSession()) {
    els.eventsSub.textContent = "Sign in to see your workspace feed.";
    els.events.innerHTML = `<div class="empty-state">No tenant data is shown until you sign in.</div>`;
    return;
  }

  if (!events.length) {
    els.eventsSub.textContent = "No current disruptions in your recent event window.";
    els.events.innerHTML = `<div class="empty-state">No disruptions found in the current window. Pull the latest signals or wait for the next worker cycle.</div>`;
    return;
  }

  els.eventsSub.textContent = `${events.length} recent disruptions connected to your planning view.`;
  els.events.innerHTML = events
    .slice(0, 8)
    .map((event) => {
      const band = severityBand(event.severity || 0);
      return `
      <div class="event-card">
        <div class="event-head">
          <div class="event-title">${escapeHtml(event.title)}</div>
          <span class="badge ${band}">${band}</span>
        </div>
        <div class="item-line"><strong>Category:</strong> ${escapeHtml(typeLabel(event.type))}</div>
        <div class="item-line"><strong>Why this matters:</strong> ${escapeHtml(whyItMatters(event.type))}</div>
        <div class="item-line"><strong>First move:</strong> ${escapeHtml(firstMove(event.type))}</div>
        <div class="item-line"><strong>Detected:</strong> ${escapeHtml(formatDate(event.detected_at))}</div>
      </div>
      `;
    })
    .join("");
}

function renderRisk(items) {
  if (!hasSession()) {
    els.risk.innerHTML = `<div class="empty-state">Sign in to see prioritized risks and action plans for your workspace.</div>`;
    return;
  }

  if (!items.length) {
    els.risk.innerHTML = `<div class="empty-state">No personalized priorities yet. Add more supply map coverage or wait for new events.</div>`;
    return;
  }

  els.risk.innerHTML = items
    .slice(0, 6)
    .map((item) => {
      const band = severityBand(item.risk_score || 0);
      return `
      <div class="risk-card">
        <div class="risk-head">
          <div class="risk-title">${escapeHtml(item.event_title)}</div>
          <span class="badge ${band}">${escapeHtml(item.revenue_risk_band || band)}</span>
        </div>
        <div class="item-line"><strong>Risk level:</strong> ${scoreToPercent(item.risk_score || 0)} (${escapeHtml(priorityText(item.risk_score || 0))})</div>
        <div class="item-line"><strong>Signal type:</strong> ${escapeHtml(typeLabel(item.event_type))}</div>
        <div class="risk-actions">
          <button class="btn btn-ghost" data-event-id="${escapeHtml(item.event_id)}">Generate Action Plan</button>
        </div>
      </div>
      `;
    })
    .join("");
}

function renderPlaybook(playbook, briefText) {
  const optionsHtml = (playbook.options || [])
    .map((option) => {
      const actions = (option.actions || []).map((action) => `<li>${escapeHtml(action)}</li>`).join("");
      return `
      <div class="playbook-card">
        <div class="event-head">
          <div class="event-title">${escapeHtml(option.name)}</div>
          <span class="badge ${option.name === playbook.recommended_option ? "high" : "low"}">${
            option.name === playbook.recommended_option ? "Recommended" : "Alternative"
          }</span>
        </div>
        <div class="item-line"><strong>Goal:</strong> ${escapeHtml(option.objective || "")}</div>
        <div class="item-line"><strong>Expected outcome:</strong> ${escapeHtml(option.expected_outcome || "")}</div>
        <div class="item-line"><strong>Trade-off:</strong> ${escapeHtml(option.tradeoffs || "")}</div>
        <div class="item-line"><strong>Actions:</strong></div>
        <ul>${actions}</ul>
      </div>
      `;
    })
    .join("");

  els.playbookPane.innerHTML = `
    <div class="playbook-card">
      <div class="event-title">Recommended path: ${escapeHtml(playbook.recommended_option)}</div>
      <div class="item-line"><strong>Model version:</strong> ${escapeHtml(playbook.model_version || "MVP")}</div>
      <div class="item-line"><strong>Playbook ID:</strong> ${escapeHtml(playbook.id)}</div>
    </div>
    ${optionsHtml}
    ${
      briefText
        ? `<div class="playbook-card"><div class="item-line"><strong>Decision Brief:</strong></div><pre>${escapeHtml(briefText)}</pre></div>`
        : ""
    }
  `;
}

function renderExplainability(payload) {
  if (!payload) {
    els.explainabilityPane.innerHTML = `<div class="empty-state">Generate a playbook to see weighted factors, assumptions, and override impact.</div>`;
    return;
  }
  const bars = (payload.factors || [])
    .map(
      (factor) => `
      <div class="item-line">
        <strong>${escapeHtml(factor.name)}</strong> value ${Math.round(factor.value * 100)}%, weight ${Math.round(
        factor.weight * 100
      )}%.
        <div class="progress-track"><div class="progress-fill" style="width:${Math.round(factor.contribution * 100)}%"></div></div>
      </div>
    `
    )
    .join("");
  const overrideBlock = payload.override_estimate
    ? `<div class="playbook-card">
        <div class="item-line"><strong>Override estimate:</strong> risk ${scoreToPercent(
          payload.override_estimate.risk_score
        )}, lead +${payload.override_estimate.lead_time_delta_days}d, cost +${payload.override_estimate.cost_delta_pct}%</div>
        <div class="item-line"><strong>Delta:</strong> risk ${payload.delta?.risk_score_delta}, lead ${
        payload.delta?.lead_time_delta_days_delta
      }d, cost ${payload.delta?.cost_delta_pct_delta}%</div>
      </div>`
    : `<div class="item-line"><strong>Override:</strong> no active analyst override.</div>`;

  els.explainabilityPane.innerHTML = `
    <div class="playbook-card">
      <div class="event-title">Why this recommendation</div>
      <div class="item-line"><strong>Base estimate:</strong> risk ${scoreToPercent(
        payload.base_estimate.risk_score
      )}, lead +${payload.base_estimate.lead_time_delta_days}d, cost +${payload.base_estimate.cost_delta_pct}%</div>
      <div class="item-line"><strong>Confidence:</strong> ${payload.base_estimate.confidence} (${escapeHtml(
    payload.confidence_note || ""
  )})</div>
      ${bars}
      <div class="item-line"><strong>Assumptions:</strong> ${(payload.assumptions || []).map(escapeHtml).join(" | ")}</div>
      <div class="item-line"><strong>Top rationale:</strong> ${(payload.top_rationale || []).map(escapeHtml).join(" | ")}</div>
    </div>
    ${overrideBlock}
  `;
}

function renderDemoStatus() {
  const modeText = state.offlineDemoActive ? "offline" : state.demoMode ? "on" : "off";
  els.demoBadge.textContent = `Demo Mode: ${modeText} (${state.demoScenario})`;
  els.demoScenarioSelect.value = state.demoScenario;
  els.btnToggleDemoMode.textContent = state.demoMode ? "Disable Demo Mode" : "Enable Demo Mode";
  renderOfflineModeBadge();
}

function renderOps(overview) {
  if (!hasSession()) {
    els.opsSummary.innerHTML = `<div class="empty-state">Sign in to see pipeline health and delivery status.</div>`;
    els.sourceHealth.innerHTML = "";
    return;
  }

  if (!canRunOps()) {
    els.opsSummary.innerHTML = `<div class="empty-state">Operations controls are available to admins and analysts.</div>`;
    els.sourceHealth.innerHTML = "";
    return;
  }

  if (!overview) {
    els.opsSummary.innerHTML = `<div class="empty-state">No worker activity recorded yet. Pull the latest signals to create the first ingestion run.</div>`;
    els.sourceHealth.innerHTML = "";
    return;
  }

  const latestRun = overview.latest_run;
  els.opsSummary.innerHTML = `
    <div class="ops-card">
      <div class="ops-grid">
        <div class="ops-metric">
          <strong>Latest run</strong>
          <span>${escapeHtml(latestRun ? latestRun.status : "Not started")}</span>
        </div>
        <div class="ops-metric">
          <strong>Queued alerts</strong>
          <span>${escapeHtml(String(overview.queued_alerts || 0))}</span>
        </div>
        <div class="ops-metric">
          <strong>Retry or failed</strong>
          <span>${escapeHtml(String((overview.retrying_alerts || 0) + (overview.failed_alerts || 0)))}</span>
        </div>
        <div class="ops-metric">
          <strong>Active users</strong>
          <span>${escapeHtml(String(overview.active_users || 0))}</span>
        </div>
      </div>
      ${
        latestRun
          ? `<div class="item-line"><strong>Last completed:</strong> ${escapeHtml(formatDate(latestRun.finished_at || latestRun.started_at))}</div>`
          : ""
      }
    </div>
  `;

  const sources = overview.source_health || [];
  els.sourceHealth.innerHTML = sources.length
    ? sources
        .map(
          (source) => `
        <div class="source-row">
          <div>
            <strong>${escapeHtml(source.source_name)}</strong>
            <span>Last run: ${escapeHtml(source.last_run_at ? formatDate(source.last_run_at) : "Not yet run")}</span>
          </div>
          <span class="badge ${source.last_run_status === "ok" ? "low" : "high"}">${escapeHtml(source.last_run_status)}</span>
        </div>
      `
        )
        .join("")
    : `<div class="empty-state">No source-health data yet.</div>`;
}

function renderTeam(users) {
  if (!hasSession()) {
    els.teamList.innerHTML = `<div class="empty-state">Sign in to manage your workspace team.</div>`;
    els.teamForm.classList.add("hidden");
    return;
  }

  if (!["admin", "analyst"].includes(state.user?.role || "")) {
    els.teamList.innerHTML = `<div class="empty-state">Team management visibility is limited to admins and analysts.</div>`;
    els.teamForm.classList.add("hidden");
    return;
  }

  els.teamForm.classList.toggle("hidden", !canManageUsers());
  els.teamList.innerHTML = users.length
    ? users
        .map(
          (user) => `
        <div class="team-card">
          <div class="team-row">
            <div>
              <strong>${escapeHtml(user.full_name)}</strong>
              <span>${escapeHtml(user.email)}</span>
            </div>
            <span class="badge ${user.is_active ? "low" : "high"}">${escapeHtml(user.role)}</span>
          </div>
          <div class="muted-note">${user.is_active ? "Active" : "Inactive"}${
            user.id === state.user?.id ? " - you" : ""
          }</div>
        </div>
      `
        )
        .join("")
    : `<div class="empty-state">No additional users yet.</div>`;
}

function parseCsvList(value) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function renderSupplyMap(map) {
  if (!hasSession()) {
    els.supplyMapSummary.innerHTML = `<div class="empty-state">Sign in to load and edit your supply map.</div>`;
    return;
  }
  if (!map) {
    els.supplyMapSummary.innerHTML = `<div class="empty-state">Load your current supply map to view supplier/lane/SKU coverage.</div>`;
    return;
  }
  els.supplyMapSummary.innerHTML = `
    <div class="ops-card">
      <div class="ops-grid">
        <div class="ops-metric"><strong>Version</strong><span>${escapeHtml(String(map.supply_map_version || 1))}</span></div>
        <div class="ops-metric"><strong>Suppliers</strong><span>${escapeHtml(String((map.suppliers || []).length))}</span></div>
        <div class="ops-metric"><strong>Lanes</strong><span>${escapeHtml(String((map.lanes || []).length))}</span></div>
        <div class="ops-metric"><strong>SKU groups</strong><span>${escapeHtml(String((map.sku_groups || []).length))}</span></div>
      </div>
    </div>
  `;
}

function renderPolicies(policies) {
  if (!hasSession()) {
    els.policyList.innerHTML = `<div class="empty-state">Sign in to configure alert policies.</div>`;
    return;
  }
  if (!["admin", "analyst"].includes(state.user?.role || "")) {
    els.policyList.innerHTML = `<div class="empty-state">Policy visibility is limited to admins and analysts.</div>`;
    return;
  }
  if (!policies.length) {
    els.policyList.innerHTML = `<div class="empty-state">No saved policies yet.</div>`;
    return;
  }
  els.policyList.innerHTML = policies
    .map(
      (policy) => `
      <div class="team-card">
        <div class="team-row">
          <div>
            <strong>${escapeHtml(policy.channel)} -> ${escapeHtml(policy.target)}</strong>
            <span>Min severity ${escapeHtml(String(policy.min_severity))} | Active: ${policy.active ? "Yes" : "No"}</span>
          </div>
          <span class="badge ${policy.active ? "low" : "high"}">${policy.active ? "active" : "paused"}</span>
        </div>
        <div class="inline-actions">
          ${
            canManageUsers()
              ? `<button class="btn btn-ghost btn-xs" data-policy-action="toggle" data-policy-id="${escapeHtml(policy.id)}">${
                  policy.active ? "Pause" : "Activate"
                }</button>
                 <button class="btn btn-ghost btn-xs" data-policy-action="delete" data-policy-id="${escapeHtml(policy.id)}">Delete</button>`
              : ""
          }
        </div>
      </div>
    `
    )
    .join("");
}

function renderWorkflow(payload) {
  if (!hasSession()) {
    els.workflowPane.innerHTML = `<div class="empty-state">Sign in to use approvals, notes, and outcomes.</div>`;
    return;
  }
  if (!payload) {
    els.workflowPane.innerHTML = `<div class="empty-state">Generate an action plan to start approvals, notes, and outcome tracking.</div>`;
    return;
  }

  const approvalsHtml = (payload.approvals || [])
    .map(
      (approval) => `
    <div class="approval-row">
      <strong>Step ${escapeHtml(String(approval.step_order))}: ${escapeHtml(approval.step_name)}</strong>
      <div class="item-line"><strong>Status:</strong> ${escapeHtml(approval.status)}</div>
      <div class="item-line"><strong>Note:</strong> ${escapeHtml(approval.decision_note || "No decision note yet.")}</div>
      ${
        canRunOps()
          ? `<div class="approval-actions">
              <button class="btn btn-ghost btn-xs" data-approval-action="pending" data-approval-id="${escapeHtml(approval.id)}">Set Pending</button>
              <button class="btn btn-ghost btn-xs" data-approval-action="approved" data-approval-id="${escapeHtml(approval.id)}">Approve</button>
              <button class="btn btn-ghost btn-xs" data-approval-action="rejected" data-approval-id="${escapeHtml(approval.id)}">Reject</button>
            </div>`
          : ""
      }
    </div>
  `
    )
    .join("");

  const commentsHtml = (payload.comments || [])
    .map(
      (comment) => `
      <div class="comment-item">
        <div class="item-line"><strong>Comment:</strong> ${escapeHtml(comment.comment)}</div>
        <div class="item-line"><strong>Added:</strong> ${escapeHtml(formatDate(comment.created_at))}</div>
      </div>
    `
    )
    .join("");

  const outcome = payload.outcome;
  els.workflowPane.innerHTML = `
    <div class="workflow-grid">
      <div>
        <h4>Approvals</h4>
        ${approvalsHtml || `<div class="empty-state">No approval steps.</div>`}
      </div>
      <div>
        <h4>Notes and Outcome</h4>
        <div class="comment-feed">${commentsHtml || `<div class="empty-state">No comments yet.</div>`}</div>
        <form id="commentForm" class="team-form">
          <label>Add note<input id="commentInput" placeholder="Add analyst note or decision context" /></label>
          <div class="inline-actions"><button class="btn btn-primary" type="submit">Add Note</button></div>
        </form>
        <form id="outcomeForm" class="team-form">
          <label>
            Outcome status
            <select id="outcomeStatus">
              <option value="open">Open</option>
              <option value="monitoring">Monitoring</option>
              <option value="mitigated">Mitigated</option>
              <option value="resolved">Resolved</option>
            </select>
          </label>
          <label>Summary<input id="outcomeSummary" placeholder="What changed and what is next?" /></label>
          <label>ETA recovery hours<input id="outcomeEta" type="number" min="0" placeholder="48" /></label>
          <div class="inline-actions"><button class="btn btn-secondary" type="submit">Save Outcome</button></div>
        </form>
      </div>
    </div>
  `;

  const statusSelect = document.getElementById("outcomeStatus");
  const summaryInput = document.getElementById("outcomeSummary");
  const etaInput = document.getElementById("outcomeEta");
  if (statusSelect && outcome?.status) statusSelect.value = outcome.status;
  if (summaryInput && outcome?.summary) summaryInput.value = outcome.summary;
  if (etaInput && Number.isFinite(outcome?.eta_recovery_hours)) etaInput.value = String(outcome.eta_recovery_hours);
}

function populateIndustries(options) {
  els.industrySelect.innerHTML = options.map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join("");
}

async function loadIndustries() {
  try {
    const data = await fetchJson("/v1/industries");
    if (Array.isArray(data.industries) && data.industries.length > 0) {
      state.industries = data.industries;
    }
  } catch (_err) {
    state.industries = [...DEFAULT_INDUSTRIES];
  }
  populateIndustries(state.industries);
}

function openModal() {
  state.step = 1;
  els.modal.classList.remove("hidden");
  els.modal.setAttribute("aria-hidden", "false");
  renderStep();
}

function closeModal() {
  els.modal.classList.add("hidden");
  els.modal.setAttribute("aria-hidden", "true");
}

function renderStep() {
  const steps = Array.from(document.querySelectorAll(".wizard-step"));
  steps.forEach((stepEl) => {
    const thisStep = Number(stepEl.dataset.step);
    stepEl.classList.toggle("hidden", thisStep !== state.step);
  });
  const pct = (state.step / 3) * 100;
  els.progressFill.style.width = `${pct}%`;
  els.progressLabel.textContent = `Step ${state.step} of 3`;
  els.btnPrevStep.disabled = state.step === 1;
  if (state.step === 1) {
    els.btnNextStep.textContent = "Next: Supply Inputs";
    setWizardHint("Step 1/3: Add workspace identity. Use sample inputs for a quick demo.");
  } else if (state.step === 2) {
    els.btnNextStep.textContent = "Next: Alerts";
    setWizardHint("Step 2/3: Add one critical supplier, lane, and SKU to personalize risk scoring.");
  } else {
    els.btnNextStep.textContent = "Finish Setup";
    setWizardHint("Step 3/3: Configure alerts and complete onboarding.");
  }
}

function getValue(id) {
  const element = document.getElementById(id);
  return (element?.value || "").trim();
}

function validateCurrentStep() {
  if (state.step === 1) {
    if (!getValue("companyName") || !getValue("adminFullName") || !getValue("adminEmail") || !getValue("adminPassword")) {
      setStatus("Please complete the company and admin account fields.");
      setWizardHint("Complete company, admin name, email, and password to continue.");
      return false;
    }
    if (getValue("adminPassword").length < 10) {
      setStatus("Password must be at least 10 characters.");
      setWizardHint("Password requires at least 10 characters.");
      return false;
    }
  }
  if (state.step === 2) {
    const required = [
      "supplierName",
      "supplierCountry",
      "supplierRegion",
      "supplierCommodity",
      "laneOrigin",
      "laneDestination",
      "skuName",
      "skuCategory",
    ];
    if (required.some((id) => !getValue(id))) {
      setStatus("Please complete all required supply-chain fields.");
      setWizardHint("Fill all required supplier/lane/SKU fields before continuing.");
      return false;
    }
  }
  return true;
}

async function refreshDashboard() {
  renderChecklist();
  if (!hasSession()) {
    renderMetrics(null);
    renderEvents([]);
    renderRisk([]);
    renderOps(null);
    renderTeam([]);
    renderSupplyMap(null);
    renderPolicies([]);
    renderWorkflow(null);
    renderExplainability(null);
    setStatus("Create an account or sign in to access your workspace.");
    return;
  }

  try {
    setStatus("Refreshing latest insights...");
    els.events.innerHTML = `<div class="empty-state loading">Loading event feed...</div>`;
    els.risk.innerHTML = `<div class="empty-state loading">Calculating priorities...</div>`;
    if (canRunOps()) {
      const demo = await fetchJson("/v1/demo/status");
      state.demoMode = Boolean(demo?.demo_mode);
      state.demoScenario = demo?.demo_scenario || "all";
      renderDemoStatus();
    }
    const summary = await fetchJson("/v1/dashboard/summary");
    renderMetrics(summary);
    renderEvents(summary.latest_events || []);

    const risk = await fetchJson(`/v1/clients/${state.clientId}/risk-scores?window=168`);
    state.riskItems = risk.items || [];
    renderRisk(state.riskItems);

    if (canRunOps()) {
      state.opsOverview = await fetchJson("/v1/ops/overview");
      renderOps(state.opsOverview);
      state.users = await fetchJson("/v1/users");
      renderTeam(state.users);
    } else {
      state.opsOverview = null;
      state.users = [];
      renderOps(null);
      renderTeam([]);
    }

    state.supplyMap = await fetchJson(`/v1/clients/${state.clientId}/supply-map`);
    renderSupplyMap(state.supplyMap);

    if (["admin", "analyst"].includes(state.user?.role || "")) {
      state.alertPolicies = await fetchJson("/v1/alerts/subscriptions");
      renderPolicies(state.alertPolicies);
    } else {
      state.alertPolicies = [];
      renderPolicies([]);
    }

    renderChecklist();
    setStatus(`Updated at ${new Date().toLocaleTimeString()}`);
  } catch (err) {
    renderRisk([]);
    renderOps(state.opsOverview);
    renderTeam(state.users);
    renderSupplyMap(state.supplyMap);
    renderPolicies(state.alertPolicies);
    setStatus(`Unable to refresh dashboard: ${err.message}`);
  }
}

async function toggleDemoMode() {
  if (!canManageUsers()) {
    setStatus("Only admins can toggle demo mode.");
    return;
  }
  try {
    const payload = {
      demo_mode: !state.demoMode,
      demo_scenario: els.demoScenarioSelect.value || state.demoScenario || "all",
    };
    const updated = await fetchJson("/v1/demo/status", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.demoMode = Boolean(updated.demo_mode);
    state.demoScenario = updated.demo_scenario;
    renderDemoStatus();
    setStatus(`Demo mode updated: ${state.demoMode ? "enabled" : "disabled"} (${state.demoScenario}).`);
  } catch (err) {
    setStatus(`Could not toggle demo mode: ${err.message}`);
  }
}

function prefillOnboardingSample() {
  const sample = {
    companyName: "Astra Mobility India",
    adminFullName: "Riya Sen",
    adminEmail: "riya.sen@astramobility.in",
    adminPassword: "StrongPass123",
    supplierName: "Jade Components",
    supplierCountry: "China",
    supplierRegion: "South China",
    supplierCommodity: "power electronics",
    laneOrigin: "Shanghai",
    laneDestination: "Nhava Sheva",
    laneChokepoint: "Strait of Malacca",
    skuName: "EV Drive Module",
    skuCategory: "power electronics",
  };
  Object.entries(sample).forEach(([id, value]) => {
    const field = document.getElementById(id);
    if (field) field.value = value;
  });
  setWizardHint("Sample inputs applied. Continue with Next to complete setup.");
}

async function signIn() {
  if (!els.loginEmail.value.trim() || !els.loginPassword.value) {
    setStatus("Please enter your email and password.");
    return;
  }
  if (els.loginPassword.value.length < 10) {
    setStatus("Password must be at least 10 characters.");
    return;
  }
  try {
    if (API_BASE && state.backendStatus !== "awake") {
      const woke = await wakeBackend("auto");
      if (!woke) {
        throw new Error("Backend is sleeping or unavailable. Wait 30-60 seconds and retry.");
      }
    }
    setStatus("Signing in...");
    const auth = await fetchJson("/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({
        email: els.loginEmail.value.trim(),
        password: els.loginPassword.value,
      }),
    });
    saveSession(auth);
    await refreshDashboard();
    setStatus("Signed in successfully.");
  } catch (err) {
    setStatus(`Sign-in failed: ${err.message}`);
  }
}

async function submitOnboarding() {
  const nextButton = els.btnNextStep;
  const prevButton = els.btnPrevStep;
  try {
    nextButton.disabled = true;
    prevButton.disabled = true;
    if (API_BASE) {
      const woke = await wakeBackend("auto");
      if (!woke) {
        throw new Error("Backend is sleeping or unavailable. Wait 30-60 seconds and retry.");
      }
    }
    setStatus("Creating your secure workspace...");

    const auth = await fetchJson("/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({
        company_name: getValue("companyName"),
        industry: getValue("industrySelect"),
        country: "India",
        preferences: {
          objective: getValue("objectiveSelect"),
          freshness_sla_minutes: 15,
        },
        full_name: getValue("adminFullName"),
        email: getValue("adminEmail"),
        password: getValue("adminPassword"),
      }),
    });
    saveSession(auth);

    await fetchJson(`/v1/clients/${state.clientId}/supply-map`, {
      method: "POST",
      body: JSON.stringify({
        suppliers: [
          {
            name: getValue("supplierName"),
            country: getValue("supplierCountry"),
            region: getValue("supplierRegion"),
            commodity: getValue("supplierCommodity"),
            criticality: 0.85,
            substitution_score: 0.4,
            lead_time_sensitivity: 0.7,
            inventory_buffer_days: 14,
          },
        ],
        lanes: [
          {
            origin: getValue("laneOrigin"),
            destination: getValue("laneDestination"),
            mode: "sea",
            chokepoint: getValue("laneChokepoint"),
            importance: 0.85,
          },
        ],
        sku_groups: [
          {
            name: getValue("skuName"),
            category: getValue("skuCategory"),
            monthly_volume: 10000,
            margin_sensitivity: 0.7,
          },
        ],
      }),
    });

    const minSeverity = Number(getValue("severitySelect") || "0.55");
    await fetchJson("/v1/alerts/subscriptions", {
      method: "POST",
      body: JSON.stringify({
        channel: "dashboard",
        target: "control-tower",
        min_severity: minSeverity,
        regions: [],
        industries: [getValue("industrySelect")],
        active: true,
      }),
    });

    const email = getValue("alertEmail") || getValue("adminEmail");
    if (email) {
      await fetchJson("/v1/alerts/subscriptions", {
        method: "POST",
        body: JSON.stringify({
          channel: "email",
          target: email,
          min_severity: minSeverity,
          regions: [],
          industries: [getValue("industrySelect")],
          active: true,
        }),
      });
    }

    const whatsapp = getValue("alertWhatsapp");
    if (whatsapp) {
      await fetchJson("/v1/alerts/subscriptions", {
        method: "POST",
        body: JSON.stringify({
          channel: "whatsapp",
          target: whatsapp,
          min_severity: minSeverity,
          regions: [],
          industries: [getValue("industrySelect")],
          active: true,
        }),
      });
    }

    closeModal();
    els.loginEmail.value = getValue("adminEmail");
    els.loginPassword.value = "";
    setStatus("Workspace setup complete. Pull the latest signals to start seeing live risk events.");
    await refreshDashboard();
  } catch (err) {
    clearSession();
    setStatus(`Setup failed: ${err.message}`);
  } finally {
    nextButton.disabled = false;
    prevButton.disabled = false;
  }
}

async function hydrateSession() {
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) {
    return;
  }
  state.accessToken = token;
  try {
    const sessionData = await fetchJson("/v1/auth/me");
    state.clientId = sessionData.client.id;
    state.clientName = sessionData.client.name;
    state.user = sessionData.user;
    updateAuthUi();
  } catch (_err) {
    clearSession();
  }
}

async function generatePlaybook(eventId) {
  if (!hasSession()) {
    setStatus("Sign in first to generate an action plan.");
    return;
  }
  try {
    setStatus("Building action plan...");
    const playbook = await fetchJson(`/v1/clients/${state.clientId}/playbooks/generate`, {
      method: "POST",
      body: JSON.stringify({ event_id: eventId }),
    });
    state.playbookId = playbook.id;
    state.currentEventId = eventId;
    let briefText = "";
    try {
      if (state.offlineDemoActive) {
        briefText = await offlineApi(`/v1/playbooks/${playbook.id}/brief`, { method: "GET" });
      } else {
        const response = await nativeFetch(withApiBase(`/v1/playbooks/${playbook.id}/brief`), {
          headers: { Authorization: `Bearer ${state.accessToken}` },
        });
        if (response.ok) {
          briefText = await response.text();
        }
      }
    } catch (_err) {
      briefText = "";
    }
    renderPlaybook(playbook, briefText);
    const explainability = await fetchJson(`/v1/clients/${state.clientId}/events/${eventId}/explainability`);
    renderExplainability(explainability);
    await loadWorkflow(playbook.id, eventId);
    renderChecklist();
    setStatus("Action plan ready.");
  } catch (err) {
    renderExplainability(null);
    setStatus(`Could not generate plan: ${err.message}`);
  }
}

async function loadWorkflow(playbookId, eventId) {
  if (!playbookId || !eventId) {
    renderWorkflow(null);
    return;
  }
  try {
    const [approvals, comments, outcome] = await Promise.all([
      fetchJson(`/v1/playbooks/${playbookId}/approvals`),
      fetchJson(`/v1/playbooks/${playbookId}/comments`),
      fetchJson(`/v1/clients/${state.clientId}/events/${eventId}/outcome`),
    ]);
    renderWorkflow({ approvals, comments, outcome, playbookId, eventId });
  } catch (err) {
    setStatus(`Unable to load workflow details: ${err.message}`);
  }
}

async function saveQuickSupplyMap(event) {
  event.preventDefault();
  if (!hasSession()) {
    setStatus("Sign in first.");
    return;
  }
  const payload = {
    suppliers: [],
    lanes: [],
    sku_groups: [],
  };
  if (els.quickSupplierName.value.trim()) {
    payload.suppliers.push({
      name: els.quickSupplierName.value.trim(),
      country: els.quickSupplierCountry.value.trim() || "India",
      region: els.quickSupplierRegion.value.trim() || "Unknown",
      commodity: els.quickSupplierCommodity.value.trim() || "general",
      criticality: 0.7,
      substitution_score: 0.5,
      lead_time_sensitivity: 0.6,
      inventory_buffer_days: 14,
    });
  }
  if (els.quickLaneOrigin.value.trim() && els.quickLaneDestination.value.trim()) {
    payload.lanes.push({
      origin: els.quickLaneOrigin.value.trim(),
      destination: els.quickLaneDestination.value.trim(),
      mode: "sea",
      importance: 0.7,
      chokepoint: null,
    });
  }
  if (els.quickSkuName.value.trim()) {
    payload.sku_groups.push({
      name: els.quickSkuName.value.trim(),
      category: els.quickSkuCategory.value.trim() || "general",
      monthly_volume: 0,
      margin_sensitivity: 0.6,
    });
  }
  if (!payload.suppliers.length && !payload.lanes.length && !payload.sku_groups.length) {
    setStatus("Add at least one supplier, lane, or SKU row to save.");
    return;
  }
  try {
    setStatus("Saving supply map update...");
    await fetchJson(`/v1/clients/${state.clientId}/supply-map`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.supplyMap = await fetchJson(`/v1/clients/${state.clientId}/supply-map`);
    renderSupplyMap(state.supplyMap);
    setStatus("Supply map updated.");
  } catch (err) {
    setStatus(`Could not save supply map: ${err.message}`);
  }
}

async function importSupplyMapCsv(event) {
  event.preventDefault();
  if (!hasSession()) {
    setStatus("Sign in first.");
    return;
  }
  if (!els.csvSuppliers.value.trim() || !els.csvLanes.value.trim() || !els.csvSkuGroups.value.trim()) {
    setStatus("Provide all three CSV blocks (suppliers, lanes, SKU groups).");
    return;
  }
  try {
    setStatus("Importing CSV into supply map...");
    await fetchJson(`/v1/clients/${state.clientId}/supply-map/import-csv`, {
      method: "POST",
      body: JSON.stringify({
        suppliers_csv: els.csvSuppliers.value,
        lanes_csv: els.csvLanes.value,
        sku_groups_csv: els.csvSkuGroups.value,
      }),
    });
    state.supplyMap = await fetchJson(`/v1/clients/${state.clientId}/supply-map`);
    renderSupplyMap(state.supplyMap);
    setStatus("CSV import complete.");
  } catch (err) {
    setStatus(`CSV import failed: ${err.message}`);
  }
}

async function createPolicy(event) {
  event.preventDefault();
  if (!canManageUsers()) {
    setStatus("Only admins can save policies.");
    return;
  }
  if (!els.policyTarget.value.trim()) {
    setStatus("Policy target is required.");
    return;
  }
  try {
    setStatus("Saving alert policy...");
    await fetchJson("/v1/alerts/subscriptions", {
      method: "POST",
      body: JSON.stringify({
        channel: els.policyChannel.value,
        target: els.policyTarget.value.trim(),
        min_severity: Number(els.policySeverity.value),
        regions: parseCsvList(els.policyRegions.value),
        industries: parseCsvList(els.policyIndustries.value),
        active: els.policyActive.value === "true",
      }),
    });
    state.alertPolicies = await fetchJson("/v1/alerts/subscriptions");
    renderPolicies(state.alertPolicies);
    setStatus("Alert policy saved.");
  } catch (err) {
    setStatus(`Could not save policy: ${err.message}`);
  }
}

async function applyPolicyAction(action, policyId) {
  if (!canManageUsers()) {
    setStatus("Only admins can modify policies.");
    return;
  }
  try {
    if (action === "delete") {
      await fetchJson(`/v1/alerts/subscriptions/${policyId}`, { method: "DELETE" });
    } else if (action === "toggle") {
      const policy = (state.alertPolicies || []).find((item) => item.id === policyId);
      if (!policy) return;
      await fetchJson(`/v1/alerts/subscriptions/${policyId}`, {
        method: "PATCH",
        body: JSON.stringify({ active: !policy.active }),
      });
    }
    state.alertPolicies = await fetchJson("/v1/alerts/subscriptions");
    renderPolicies(state.alertPolicies);
    setStatus("Policy updated.");
  } catch (err) {
    setStatus(`Could not update policy: ${err.message}`);
  }
}

async function updateApprovalStatus(approvalId, statusValue) {
  if (!canRunOps() || !state.playbookId) {
    setStatus("Generate a playbook first.");
    return;
  }
  try {
    await fetchJson(`/v1/playbooks/${state.playbookId}/approvals/${approvalId}`, {
      method: "PATCH",
      body: JSON.stringify({ status: statusValue, decision_note: `Set via dashboard as ${statusValue}` }),
    });
    await loadWorkflow(state.playbookId, state.currentEventId);
    setStatus("Approval step updated.");
  } catch (err) {
    setStatus(`Could not update approval: ${err.message}`);
  }
}

async function addWorkflowComment(event) {
  event.preventDefault();
  const input = document.getElementById("commentInput");
  if (!input || !input.value.trim() || !state.playbookId) {
    setStatus("Add a comment after generating a playbook.");
    return;
  }
  try {
    await fetchJson(`/v1/playbooks/${state.playbookId}/comments`, {
      method: "POST",
      body: JSON.stringify({ comment: input.value.trim() }),
    });
    await loadWorkflow(state.playbookId, state.currentEventId);
    setStatus("Comment added.");
  } catch (err) {
    setStatus(`Could not add comment: ${err.message}`);
  }
}

async function saveOutcome(event) {
  event.preventDefault();
  if (!state.currentEventId || !state.playbookId) {
    setStatus("Generate a playbook first.");
    return;
  }
  const statusInput = document.getElementById("outcomeStatus");
  const summaryInput = document.getElementById("outcomeSummary");
  const etaInput = document.getElementById("outcomeEta");
  try {
    await fetchJson(`/v1/clients/${state.clientId}/events/${state.currentEventId}/outcome`, {
      method: "POST",
      body: JSON.stringify({
        playbook_id: state.playbookId,
        status: statusInput?.value || "open",
        summary: summaryInput?.value || "",
        actions_taken: [],
        eta_recovery_hours: etaInput?.value ? Number(etaInput.value) : null,
      }),
    });
    await loadWorkflow(state.playbookId, state.currentEventId);
    setStatus("Outcome updated.");
  } catch (err) {
    setStatus(`Could not save outcome: ${err.message}`);
  }
}

async function runIngestion() {
  if (!canRunOps()) {
    setStatus("Only admins and analysts can pull new signals.");
    return;
  }
  try {
    setStatus("Pulling the latest external signals...");
    const result = await fetchJson("/v1/ingestion/run", { method: "POST" });
    await refreshDashboard();
    setStatus(
      `Latest pull complete. Inserted ${result.inserted_count}, updated ${result.updated_count}, queued ${result.queued_alerts} alerts.`
    );
  } catch (err) {
    setStatus(`Could not pull signals: ${err.message}`);
  }
}

async function dispatchAlerts() {
  if (!canRunOps()) {
    setStatus("Only admins and analysts can process alert delivery.");
    return;
  }
  try {
    setStatus("Processing queued alerts...");
    const result = await fetchJson("/v1/alerts/dispatch", { method: "POST" });
    await refreshDashboard();
    setStatus(
      `Alert queue processed. Delivered ${result.delivered_count}, retrying ${result.retry_count}, failed ${result.failed_count + result.blocked_count}.`
    );
  } catch (err) {
    setStatus(`Could not process alerts: ${err.message}`);
  }
}

async function addUser(event) {
  event.preventDefault();
  if (!canManageUsers()) {
    setStatus("Only admins can add team members.");
    return;
  }

  const fullName = els.teamName.value.trim();
  const email = els.teamEmail.value.trim();
  const role = els.teamRole.value;
  const password = els.teamPassword.value;
  if (!fullName || !email || !password) {
    setStatus("Please complete the team member form.");
    return;
  }
  if (password.length < 10) {
    setStatus("Team member password must be at least 10 characters.");
    return;
  }

  try {
    setStatus("Adding team member...");
    await fetchJson("/v1/users", {
      method: "POST",
      body: JSON.stringify({
        full_name: fullName,
        email,
        role,
        password,
      }),
    });
    els.teamName.value = "";
    els.teamEmail.value = "";
    els.teamPassword.value = "";
    await refreshDashboard();
    setStatus("Team member added.");
  } catch (err) {
    setStatus(`Could not add team member: ${err.message}`);
  }
}

function bindEvents() {
  document.getElementById("btnRefreshTop").addEventListener("click", refreshDashboard);
  document.getElementById("btnOpenOnboarding").addEventListener("click", openModal);
  document.getElementById("btnFocusLogin").addEventListener("click", () => els.loginEmail.focus());
  document.getElementById("btnSignIn").addEventListener("click", signIn);
  if (els.btnWakeServer) {
    els.btnWakeServer.addEventListener("click", async () => {
      await wakeBackend("manual");
    });
  }
  els.viewTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      state.currentView = tab.dataset.view || "control";
      applyView();
    });
  });
  els.btnPresentationMode.addEventListener("click", () => {
    state.presentationMode = !state.presentationMode;
    applyPresentationMode();
  });
  els.btnToggleDemoMode.addEventListener("click", toggleDemoMode);
  els.demoScenarioSelect.addEventListener("change", async () => {
    if (!canManageUsers()) return;
    try {
      const updated = await fetchJson("/v1/demo/status", {
        method: "POST",
        body: JSON.stringify({
          demo_mode: state.demoMode,
          demo_scenario: els.demoScenarioSelect.value,
        }),
      });
      state.demoMode = Boolean(updated.demo_mode);
      state.demoScenario = updated.demo_scenario;
      renderDemoStatus();
    } catch (err) {
      setStatus(`Could not update demo scenario: ${err.message}`);
    }
  });
  document.getElementById("btnCloseModal").addEventListener("click", closeModal);
  if (els.btnPrefillSample) {
    els.btnPrefillSample.addEventListener("click", prefillOnboardingSample);
  }
  els.btnLogoutTop.addEventListener("click", async () => {
    clearSession();
    els.playbookPane.innerHTML = `<div class="empty-state">Sign in and select a priority item to generate an action plan.</div>`;
    renderExplainability(null);
    await refreshDashboard();
  });

  els.btnPrevStep.addEventListener("click", () => {
    state.step = Math.max(1, state.step - 1);
    renderStep();
  });

  els.btnNextStep.addEventListener("click", async () => {
    if (!validateCurrentStep()) return;
    if (state.step < 3) {
      state.step += 1;
      renderStep();
      return;
    }
    await submitOnboarding();
  });

  els.risk.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-event-id]");
    if (!button) return;
    const eventId = button.getAttribute("data-event-id");
    if (!eventId) return;
    await generatePlaybook(eventId);
  });

  els.btnRunIngestion.addEventListener("click", runIngestion);
  els.btnDispatchAlerts.addEventListener("click", dispatchAlerts);
  els.teamForm.addEventListener("submit", addUser);
  els.btnLoadSupplyMap.addEventListener("click", async () => {
    if (!hasSession()) {
      setStatus("Sign in first.");
      return;
    }
    try {
      state.supplyMap = await fetchJson(`/v1/clients/${state.clientId}/supply-map`);
      renderSupplyMap(state.supplyMap);
      setStatus("Loaded current supply map.");
    } catch (err) {
      setStatus(`Could not load supply map: ${err.message}`);
    }
  });
  els.supplyMapQuickForm.addEventListener("submit", saveQuickSupplyMap);
  els.supplyMapCsvForm.addEventListener("submit", importSupplyMapCsv);
  els.policyForm.addEventListener("submit", createPolicy);

  els.policyList.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-policy-action]");
    if (!button) return;
    const action = button.getAttribute("data-policy-action");
    const policyId = button.getAttribute("data-policy-id");
    if (!action || !policyId) return;
    await applyPolicyAction(action, policyId);
  });

  els.workflowPane.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-approval-action]");
    if (!button) return;
    const statusValue = button.getAttribute("data-approval-action");
    const approvalId = button.getAttribute("data-approval-id");
    if (!statusValue || !approvalId) return;
    await updateApprovalStatus(approvalId, statusValue);
  });

  els.workflowPane.addEventListener("submit", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLFormElement)) return;
    if (target.id === "commentForm") {
      await addWorkflowComment(event);
      return;
    }
    if (target.id === "outcomeForm") {
      await saveOutcome(event);
    }
  });

  els.loginPassword.addEventListener("keydown", async (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      await signIn();
    }
  });

  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeModal();
    }
  });

  els.form.addEventListener("submit", (event) => event.preventDefault());
}

async function init() {
  bindEvents();
  renderBackendStatus();
  if (OFFLINE_DEMO_FORCED) {
    state.offlineDemoActive = true;
    setBackendStatus("sleeping");
    renderOfflineModeBadge();
    setStatus("Offline demo mode active. Backend is optional for this walkthrough.");
  } else if (API_BASE) {
    const alive = await probeBackendOnce();
    if (alive) {
      setBackendStatus("awake");
    } else {
      wakeBackend("auto");
    }
  }
  await loadIndustries();
  await hydrateSession();
  renderChecklist();
  renderOps(null);
  renderTeam([]);
  renderSupplyMap(null);
  renderPolicies([]);
  renderWorkflow(null);
  renderDemoStatus();
  renderExplainability(null);
  applyView();
  applyPresentationMode();
  if (els.opsLink) {
    els.opsLink.href = withApiBase("/ops");
  }
  setWizardHint("Tip: this takes about 3 minutes with sample data.");
  await refreshDashboard();
}

init();
