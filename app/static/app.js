let csrfToken = "";

function showAlert(msg, isInfo = false) {
  const el = document.getElementById("alert-banner");
  el.textContent = msg;
  el.classList.toggle("info", isInfo);
  el.classList.remove("hidden");
}

function clearAlert() {
  document.getElementById("alert-banner").classList.add("hidden");
}

function formatMoney(currency, minor) {
  if (minor === null || minor === undefined) return "—";
  const amount = (Number(minor) / 100).toLocaleString("en-US", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
  return `${currency} ${amount}`;
}

function formatKarachi(isoStr) {
  if (!isoStr) return "—";
  try {
    return new Date(isoStr).toLocaleString("en-GB", {
      timeZone: "Asia/Karachi",
      dateStyle: "medium",
      timeStyle: "short",
    }) + " (Asia/Karachi)";
  } catch {
    return isoStr;
  }
}

async function apiFetch(url, options = {}) {
  const headers = Object.assign({}, options.headers || {});
  if (options.method && options.method !== "GET" && csrfToken) {
    headers["X-CSRF-Token"] = csrfToken;
  }
  const resp = await fetch(url, Object.assign({}, options, { headers }));
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(data.detail || `Request failed (${resp.status})`);
  }
  return data;
}

function renderDashboard(data) {
  csrfToken = data.csrf_token || "";
  const connectView = document.getElementById("connect-view");
  const dashView = document.getElementById("dashboard-view");
  const topActions = document.getElementById("topbar-actions");
  const modeBadge = document.getElementById("mode-badge");
  const oauthHint = document.getElementById("oauth-hint");

  oauthHint.classList.toggle("hidden", Boolean(data.oauth_configured));

  if (!data.connected) {
    connectView.classList.remove("hidden");
    dashView.classList.add("hidden");
    topActions.classList.add("hidden");
    modeBadge.classList.add("hidden");
    return;
  }

  connectView.classList.add("hidden");
  dashView.classList.remove("hidden");
  topActions.classList.remove("hidden");
  modeBadge.classList.remove("hidden");
  modeBadge.textContent = data.is_demo ? `Fictional Example (${data.demo_date})` : "Live Gmail";

  document.getElementById("scan-status").textContent = data.scan_status || "unknown";
  document.getElementById("partial-badge").classList.toggle("hidden", !data.partial);
  document.getElementById("last-scan").textContent = data.last_successful_scan
    ? formatKarachi(data.last_successful_scan)
    : "Never";

  if (data.scan_error) {
    showAlert(`Scan issue: ${data.scan_error}`);
  }

  // Notifications
  const notifSec = document.getElementById("notifications-section");
  const notifList = document.getElementById("notifications-list");
  notifList.innerHTML = "";
  if (data.notifications && data.notifications.length > 0) {
    notifSec.classList.remove("hidden");
    for (const n of data.notifications) {
      const li = document.createElement("li");
      li.textContent = `${n.message} — ${formatKarachi(n.created_at)}`;
      notifList.appendChild(li);
    }
  } else {
    notifSec.classList.add("hidden");
  }

  // Totals per currency
  const totalsGrid = document.getElementById("totals-grid");
  totalsGrid.innerHTML = "";
  const totals = (data.portfolio && data.portfolio.totals) || {};
  const currencies = Object.keys(totals);
  if (currencies.length === 0) {
    totalsGrid.innerHTML = '<p class="muted">No billing totals yet.</p>';
  } else {
    for (const cur of currencies) {
      const t = totals[cur];
      const box = document.createElement("div");
      box.className = "total-box";
      box.innerHTML = `
        <h3>${cur}</h3>
        <div class="metric"><span>Paid in scan window</span><strong>${formatMoney(cur, t.paid_minor)}</strong></div>
        <div class="metric"><span>Forward monthly equiv.</span><strong>${formatMoney(cur, t.monthly_equivalent_minor)}</strong></div>
        <div class="metric"><span>Confirmed due (7 days)</span><strong>${formatMoney(cur, t.next_7d_minor)}</strong></div>
      `;
      totalsGrid.appendChild(box);
    }
  }

  // Review items & trace
  const review = data.review || {};
  document.getElementById("review-summary").textContent =
    review.summary || (review.status === "failed" ? "Review agent failed; retry with Refresh." : "No review summary yet.");
  const reviewList = document.getElementById("review-items");
  reviewList.innerHTML = "";
  for (const item of review.items || []) {
    const row = document.createElement("div");
    row.className = "item-row";
    row.innerHTML = `
      <div class="item-head">
        <strong>${item.subscription_key} · ${item.kind}</strong>
        <span class="badge ${item.state === "open" ? "badge-warn" : "badge-ok"}">${item.state}</span>
      </div>
      <div class="small muted">Target date: ${item.target_date || "—"}</div>
      <p>${item.explanation || ""}</p>
    `;
    reviewList.appendChild(row);
  }
  const traceList = document.getElementById("trace-list");
  traceList.innerHTML = "";
  for (const tr of review.trace || []) {
    const li = document.createElement("li");
    const ids = tr.evidence_ids || tr.source_ids || [];
    li.textContent = `${tr.tool || "tool"}: ${tr.outcome || "ok"} (sources: ${ids.join(", ")})`;
    traceList.appendChild(li);
  }

  // Subscriptions & due charges
  const subsList = document.getElementById("subscriptions-list");
  subsList.innerHTML = "";
  const portfolio = data.portfolio || {};
  const evidenceMap = new Map();
  for (const ev of data.evidence || []) {
    evidenceMap.set(ev.source_id, ev);
  }
  const dueMap = new Map();
  for (const d of portfolio.due || []) {
    dueMap.set(d.subscription_key, d);
  }
  for (const sub of portfolio.subscriptions || []) {
    const key = sub.subscription_key;
    const due = dueMap.get(key);
    const timeline = (portfolio.timelines && portfolio.timelines[key]) || [];
    const userChoice = (data.user_estimates || {})[key];
    const sourcesHtml = (sub.evidence_ids || [])
      .map((sid) => {
        const ev = evidenceMap.get(sid);
        const label = ev ? `${ev.sender_domain} — ${ev.subject}` : sid;
        return `<a href="/api/evidence/${encodeURIComponent(sid)}" target="_blank" rel="noopener noreferrer">${label}</a>`;
      })
      .join("<br/>");
    const row = document.createElement("div");
    row.className = "item-row";

    let dueHtml;
    if (due && due.date) {
      const basisNote = due.cycle_basis === "payment_history" ? " (from payment history)" : "";
      dueHtml = `<div class="small">Next charge: <strong>${formatMoney(due.currency, due.amount_minor)}</strong> on <strong>${due.date}</strong> <span class="badge ${due.date_basis === "confirmed" ? "badge-ok" : "badge-warn"}">${due.date_basis}${basisNote}</span></div>`;
    } else if (userChoice && userChoice.estimate && userChoice.estimate.date) {
      const e = userChoice.estimate;
      const amount = e.amount_minor === null || e.amount_minor === undefined ? "Amount unknown" : formatMoney(e.currency, e.amount_minor);
      dueHtml = `<div class="small">Next charge: <strong>${amount}</strong> on <strong>${e.date}</strong> <span class="badge badge-warn">estimated (you chose ${userChoice.cycle})</span></div>`;
    } else if (userChoice) {
      dueHtml = `<div class="small muted">You chose <strong>${userChoice.cycle}</strong>, but no dated payment was found to calculate the next date.</div>`;
    } else {
      dueHtml = `<div class="small muted">Next charge date unknown</div>`;
    }

    const remindHtml =
      due && due.date_basis === "confirmed"
        ? `<div class="cta-row">
             <button class="btn btn-small btn-secondary" onclick="scheduleReminder('${key}', 'default')">Remind me (day before 09:00)</button>
             <button class="btn btn-small btn-primary" onclick="scheduleReminder('${key}', 'one_minute')">Test reminder (1 min)</button>
           </div>`
        : "";

    const hasPayment = timeline.some((e) => e.kind === "payment");
    const cycleKnown = timeline.some((e) => e.cycle === "monthly" || e.cycle === "annual");
    const askCycle = hasPayment && !cycleKnown && !(due && due.date && due.cycle_basis !== "user_selected");
    const chosen = userChoice ? userChoice.cycle : "";
    const cycleHtml = askCycle
      ? `<div style="margin-top:8px; padding-top:8px; border-top:1px dashed var(--border);">
           <div class="small muted">The email doesn't say how often this renews. Is it monthly or yearly?</div>
           <div class="cta-row" style="margin-top:6px;">
             <button class="btn btn-small ${chosen === "monthly" ? "btn-primary" : "btn-secondary"}" onclick="saveCycleChoice('${key}', 'monthly')">Monthly</button>
             <button class="btn btn-small ${chosen === "annual" ? "btn-primary" : "btn-secondary"}" onclick="saveCycleChoice('${key}', 'annual')">Annual</button>
             ${chosen ? `<button class="btn btn-small btn-secondary" onclick="saveCycleChoice('${key}', 'clear')">Clear</button>` : ""}
           </div>
         </div>`
      : "";

    row.innerHTML = `
      <div class="item-head">
        <strong>${key}</strong>
        <span class="badge">${sub.status || "unknown"}</span>
      </div>
      <div class="small muted">Auto-renew: ${sub.auto_renew === null ? "Unknown" : sub.auto_renew} · Paid through: ${sub.paid_through || "—"}</div>
      ${dueHtml}
      <div class="small muted" style="margin-top:4px;">Source: ${sourcesHtml || "—"}</div>
      ${remindHtml}
      ${cycleHtml}
    `;
    subsList.appendChild(row);
  }

  // Evidence
  const evList = document.getElementById("evidence-list");
  evList.innerHTML = "";
  for (const ev of data.evidence || []) {
    const li = document.createElement("li");
    const link = document.createElement("a");
    link.href = `/api/evidence/${encodeURIComponent(ev.source_id)}`;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = `${ev.subject} (${ev.sender_domain}, ${ev.received_at})`;
    li.appendChild(link);
    evList.appendChild(li);
  }
}

async function loadDashboard() {
  try {
    const data = await apiFetch("/api/dashboard");
    renderDashboard(data);
  } catch (err) {
    showAlert(err.message);
  }
}

async function saveCycleChoice(subscriptionKey, cycle) {
  clearAlert();
  try {
    await apiFetch("/api/cycle-choice", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subscription_key: subscriptionKey, cycle }),
    });
    await loadDashboard();
  } catch (err) {
    showAlert(err.message);
  }
}

async function scheduleReminder(subscriptionKey, mode) {
  clearAlert();
  try {
    const res = await apiFetch("/api/reminders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subscription_key: subscriptionKey, mode }),
    });
    showAlert(`Reminder saved for ${subscriptionKey} (${formatKarachi(res.job.due_at)}).`, true);
    await loadDashboard();
  } catch (err) {
    showAlert(err.message);
  }
}

document.getElementById("btn-demo").addEventListener("click", async () => {
  clearAlert();
  try {
    await apiFetch("/demo/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    await loadDashboard();
  } catch (err) {
    showAlert(err.message);
  }
});

document.getElementById("btn-refresh").addEventListener("click", async () => {
  clearAlert();
  try {
    await apiFetch("/api/refresh", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    await loadDashboard();
  } catch (err) {
    showAlert(err.message);
  }
});

document.getElementById("btn-disconnect").addEventListener("click", async () => {
  clearAlert();
  try {
    await apiFetch("/api/disconnect", { method: "POST" });
    await loadDashboard();
  } catch (err) {
    showAlert(err.message);
  }
});

document.getElementById("btn-delete").addEventListener("click", async () => {
  clearAlert();
  try {
    await apiFetch("/api/data", { method: "DELETE" });
    await loadDashboard();
  } catch (err) {
    showAlert(err.message);
  }
});

const params = new URLSearchParams(window.location.search);
if (params.get("auth_error")) {
  showAlert(`Gmail connection did not complete (${params.get("auth_error")}). You can retry anytime.`);
}

loadDashboard();
