const dom = (id) => document.getElementById(id);
const state = { snapshot: null, walletRevealed: false };

const fmtMoney = (value, currency = "USD") => {
  if (typeof value !== "number") return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency, minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
};

const fmtNumber = (value, suffix = "") => typeof value === "number" ? `${new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value)}${suffix}` : "—";
const fmtDifficulty = (value) => {
  if (typeof value !== "number") return "—";
  if (value === 0) return "0";
  return value < 0.01 ? value.toExponential(2) : fmtNumber(value);
};
const fmtDate = (value) => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
};
const safe = (value, fallback = "—") => value === null || value === undefined || value === "" ? fallback : value;
const initials = (value) => String(value || "AI").slice(0, 2).toUpperCase();
const setText = (id, value) => { const element = dom(id); if (element) element.textContent = safe(value); };
const esc = (value) => String(safe(value)).replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character]));

function showToast(message) {
  const toast = dom("toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 2600);
}

function displayState(value) {
  return String(value || "UNKNOWN").replaceAll("_", " ");
}

function renderTopology(snapshot) {
  const mission = snapshot.mission || {};
  const worker = snapshot.worker || {};
  const agents = snapshot.agents || [];
  const finance = snapshot.finance || {};
  setText("topologyManager", displayState(snapshot.status));
  setText("topologyAgent", agents.length ? `${agents.length} ready` : "none connected");
  setText("topologyWorker", displayState(worker.state));
  setText("topologyEvidence", `${(snapshot.events || []).length} events`);
  setText("topologyTreasury", finance.visibility === "private" ? "private" : fmtMoney(finance.reserve_amount, finance.currency));
  document.querySelectorAll(".topology-node").forEach((node) => {
    const nodeKey = node.dataset.node;
    const value = nodeKey === "worker" ? worker.state : nodeKey === "agent" ? (agents.length ? "READY" : "EMPTY") : nodeKey === "evidence" ? "PUBLISHED" : nodeKey === "treasury" ? finance.visibility : snapshot.status;
    node.classList.toggle("node-active", ["RUNNING", "READY", "PUBLISHED", "public_exact", "public_rounded"].includes(value));
  });
}

function renderPackets(packets = []) {
  const list = dom("packetList");
  dom("packetCount").textContent = `${packets.length} recorded`;
  if (!packets.length) {
    list.innerHTML = '<div class="empty-row">No work packets have been published yet. A live worker will populate this with actual jobs, shares, tests, and outcomes.</div>';
    return;
  }
  list.innerHTML = packets.map((packet) => `
    <article class="packet">
      <div class="packet-top"><h3>${esc(packet.title || "Untitled packet")}</h3><span class="packet-state">${esc(displayState(packet.state))}</span></div>
      <p>${esc(packet.output_summary || "No output summary published.")}</p>
      <div class="packet-meta"><span>${esc(packet.kind || "work")}</span><span>${esc(packet.actor || "unknown actor")}</span><span>${esc(packet.evidence_event_id || "unlinked")}</span></div>
    </article>`).join("");
}

function renderAgents(agents = []) {
  const list = dom("agentList");
  dom("agentCount").textContent = `${agents.length} registered`;
  if (!agents.length) {
    list.innerHTML = '<div class="empty-row">No agents are registered in this snapshot.</div>';
    return;
  }
  list.innerHTML = agents.map((agent) => `
    <article class="agent">
      <div class="agent-top"><div class="agent-top-left"><span class="agent-avatar">${esc(initials(agent.agent_id))}</span><div><h3>${esc(agent.role || "Agent")}</h3><div class="agent-meta"><span>${esc(agent.provider)}</span><span>${esc(agent.model)}</span></div></div></div><span class="packet-state">${esc(displayState(agent.state))}</span></div>
      <p>${esc(agent.current_action || "No current action published.")}</p>
      <div class="agent-meta"><span>${esc(fmtNumber(agent.work_packets))} packets</span><span>${esc(agent.capability_basis || "unknown basis")}</span></div>
    </article>`).join("");
}

function renderMachine(machine = {}) {
  setText("machineQuality", safe(machine.evidence_quality, "sanitized telemetry").replaceAll("_", " "));
  setText("gpuUtil", fmtNumber(machine.gpu_utilization_pct, "%"));
  setText("gpuTemp", fmtNumber(machine.gpu_temperature_c, "°C"));
  setText("gpuPower", fmtNumber(machine.gpu_power_w, " W"));
  setText("gpuVram", fmtNumber(machine.vram_used_gb, " GB"));
  setText("gpuVramSub", typeof machine.vram_total_gb === "number" ? `of ${fmtNumber(machine.vram_total_gb, " GB")}` : "memory signal");
  setText("cpuUtil", fmtNumber(machine.cpu_utilization_pct, "%"));
  setText("machineUptime", typeof machine.uptime_hours === "number" ? `${fmtNumber(machine.uptime_hours)} h` : "—");
}

function renderWorker(worker = {}) {
  setText("workerType", safe(worker.worker_type, "No worker connected"));
  setText("workerNote", safe(worker.note, "No worker note published."));
  setText("workerRate", worker.rate === null || worker.rate === undefined ? "—" : `${fmtNumber(worker.rate)} ${safe(worker.rate_unit, "")}`);
  setText("hashesAttempted", fmtNumber(worker.hashes_attempted));
  setText("bestShareDifficulty", fmtDifficulty(worker.best_share_difficulty));
  setText("acceptedShares", fmtNumber(worker.accepted_shares));
  setText("rejectedShares", fmtNumber(worker.rejected_shares));
  setText("recoveryCount", fmtNumber(worker.recovery_count, ""));
}

function renderFinance(finance = {}) {
  const currency = finance.currency || "USD";
  const target = typeof finance.target_amount === "number" ? finance.target_amount : null;
  const reserve = typeof finance.reserve_amount === "number" ? finance.reserve_amount : null;
  const progress = target && reserve !== null ? Math.min(100, Math.max(0, (reserve / target) * 100)) : 0;
  setText("goalCurrent", fmtMoney(reserve, currency));
  setText("goalTarget", fmtMoney(target, currency));
  setText("goalPercent", finance.visibility === "private" ? "Private" : `${Math.round(progress)}%`);
  setText("goalQuality", finance.visibility === "private" ? "Finance view is private" : safe(finance.cost_quality, "awaiting payout evidence").replaceAll("_", " "));
  dom("goalProgress").style.width = `${progress}%`;
  setText("estimatedCredit", fmtMoney(finance.estimated_credit, currency));
  setText("confirmedPayout", fmtMoney(finance.confirmed_payout, currency));
  setText("moneyReceived", fmtMoney(finance.money_received, currency));
  setText("reserveAmount", fmtMoney(reserve, currency));
  setText("walletVisibility", displayState(finance.visibility));
  const wallet = finance.wallet;
  const walletAvailable = wallet && typeof wallet === "object";
  setText("walletLabel", walletAvailable && wallet.label ? wallet.label : "No receiving wallet connected");
  setText("walletBalance", walletAvailable && wallet.balance !== null && wallet.balance !== undefined ? fmtNumber(wallet.balance, " BTC") : "—");
  setText("lastPayout", walletAvailable ? fmtDate(wallet.last_payout_at) : "—");
  const addressElement = dom("walletAddress");
  const toggle = dom("walletToggle");
  if (!walletAvailable || !wallet.address) {
    addressElement.textContent = finance.visibility === "private" ? "Private finance view" : "Not connected";
    toggle.hidden = true;
  } else {
    const isMasked = wallet.address.includes("...");
    addressElement.textContent = state.walletRevealed && !isMasked ? wallet.address : (isMasked ? wallet.address : "Public address hidden");
    toggle.hidden = isMasked;
    toggle.textContent = state.walletRevealed ? "Hide" : "Reveal";
  }
  setText("costQuality", safe(finance.cost_quality, "unknown").replaceAll("_", " "));
  const receipts = finance.receipts || [];
  const receiptList = dom("receiptList");
  if (!receipts.length) {
    receiptList.innerHTML = '<div class="empty-row">No receipts observed.</div>';
  } else {
    receiptList.innerHTML = receipts.map((receipt) => `
      <div class="receipt-row"><div><strong>${esc(receipt.amount === null ? "Amount hidden" : `${fmtNumber(receipt.amount)} ${receipt.asset || ""}`)}</strong><small>${esc((receipt.classification || "observed").replaceAll("_", " "))} · ${esc(receipt.status || "unverified")}</small></div><code>${esc(receipt.txid || "no txid")}</code></div>`).join("");
  }
}

function renderEvents(events = []) {
  const list = dom("evidenceList");
  setText("eventCount", `${events.length} published events`);
  if (!events.length) {
    list.innerHTML = '<div class="empty-row">No public events have been published yet.</div>';
    return;
  }
  list.innerHTML = [...events].reverse().map((event) => `
    <article class="evidence-item">
      <time class="evidence-time">${esc(fmtDate(event.timestamp))}</time>
      <div><h3>${esc((event.event_type || "event").replaceAll("_", " "))} <span style="color:var(--cyan)">· ${esc(event.actor)}</span></h3><p>${esc(event.public_summary || event.outcome || event.action || "No public summary.")}</p></div>
      <span class="evidence-badge">${esc(event.source || "local")}</span>
    </article>`).join("");
}

function renderReferences(references = []) {
  dom("referenceRow").innerHTML = references.map((reference) => `<span>${esc(reference.title)} · review ${esc(fmtDate(reference.review_by))}</span>`).join("");
}

function render(snapshot) {
  state.snapshot = snapshot;
  const mission = snapshot.mission || {};
  const worker = snapshot.worker || {};
  const agents = snapshot.agents || [];
  const finance = snapshot.finance || {};
  dom("modeBadge").innerHTML = `<i></i> ${esc(displayState(snapshot.status || snapshot.mode))}`;
  dom("updatedLabel").textContent = snapshot.updated_at ? `Updated ${fmtDate(snapshot.updated_at)}` : "No timestamp";
  setText("systemState", displayState(snapshot.status || "UNKNOWN"));
  setText("systemMessage", snapshot.mode === "design-preview" ? "This is an honest design preview. Live worker evidence has not been connected yet." : "Current state is sourced from the latest sanitized projection.");
  setText("signalWorker", displayState(worker.state));
  setText("signalMission", displayState(mission.state));
  setText("signalEvidence", `${(snapshot.events || []).length} events`);
  setText("missionState", displayState(mission.state));
  setText("missionName", mission.name);
  setText("missionObjective", mission.objective);
  setText("missionLane", mission.lane);
  setText("missionSuccess", mission.success_measure);
  renderTopology(snapshot);
  renderPackets(snapshot.work_packets);
  renderAgents(agents);
  renderMachine(snapshot.machine || {});
  renderWorker(worker);
  renderFinance(finance);
  renderEvents(snapshot.events);
  renderReferences(snapshot.references);
}

async function loadSnapshot(showMessage = false) {
  const button = dom("refreshButton");
  button.disabled = true;
  try {
    const cacheBust = `?t=${Date.now()}`;
    const response = await fetch(`data/latest.json${cacheBust}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    render(await response.json());
    if (showMessage) showToast("Latest evidence projection loaded.");
  } catch (error) {
    dom("systemState").textContent = "OFFLINE";
    dom("systemMessage").textContent = "The public projection could not be loaded. Try Refresh when the host is available.";
    dom("modeBadge").innerHTML = "<i></i> Projection unavailable";
    if (showMessage) showToast("The evidence projection is unavailable.");
    console.error(error);
  } finally {
    button.disabled = false;
  }
}

dom("refreshButton").addEventListener("click", () => loadSnapshot(true));
dom("walletToggle").addEventListener("click", () => { state.walletRevealed = !state.walletRevealed; if (state.snapshot) renderFinance(state.snapshot.finance || {}); });
document.querySelectorAll(".section-nav a").forEach((link) => link.addEventListener("click", () => {
  document.querySelectorAll(".section-nav a").forEach((item) => item.classList.toggle("active", item === link));
}));

loadSnapshot();
