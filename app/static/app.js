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

  // Render portfolio.needs_confirmation ("Is this a subscription?")
  const needsConfirmation = portfolio.needs_confirmation || [];
  for (const item of needsConfirmation) {
    const ev = evidenceMap.get(item.source_id);
    const firstEvent = (item.events && item.events[0]) || {};
    const amt =
      firstEvent.amount_minor !== null && firstEvent.amount_minor !== undefined && firstEvent.currency
        ? formatMoney(firstEvent.currency, firstEvent.amount_minor)
        : "Amount not stated";
    const srcLabel = ev ? `${ev.sender_domain} — ${ev.subject}` : item.source_id;
    const card = document.createElement("div");
    card.className = "item-row";
    card.style.borderColor = "#fcd34d";
    card.style.background = "#fffbeb";
    card.innerHTML = `
      <div class="item-head">
        <strong>${item.subscription_key}</strong>
        <span class="badge badge-warn">Needs confirmation</span>
      </div>
      <div class="small">Detected charge: <strong>${amt}</strong> (${firstEvent.event_date || "date unknown"})</div>
      <div class="small muted" style="margin-top:4px;">Source: <a href="/api/evidence/${encodeURIComponent(item.source_id)}" target="_blank" rel="noopener noreferrer">${srcLabel}</a></div>
      <div style="margin-top:8px; padding-top:8px; border-top:1px dashed #fcd34d;">
        <div class="small"><strong>Is this a recurring subscription?</strong></div>
        <div class="cta-row" style="margin-top:6px;">
          <button class="btn btn-small btn-primary" onclick="confirmSubscription('${item.source_id}', true)">Yes, it's a subscription</button>
          <button class="btn btn-small btn-secondary" onclick="confirmSubscription('${item.source_id}', false)">No, one-time / ignore</button>
        </div>
      </div>
    `;
    subsList.appendChild(card);
  }

  const dueMap = new Map();
  for (const d of portfolio.due || []) {
    dueMap.set(d.subscription_key, d);
  }
  const billingPrompts = portfolio.billing_prompts || {};
  for (const sub of portfolio.subscriptions || []) {
    const key = sub.subscription_key;
    const due = dueMap.get(key);
    const userChoice = (data.user_estimates || {})[key];
    const prompt = billingPrompts[key];
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
      const dueAmount = due.amount_minor === null || due.amount_minor === undefined ? "Amount unknown" : formatMoney(due.currency, due.amount_minor);
      dueHtml = `<div class="small">Next charge: <strong>${dueAmount}</strong> on <strong>${due.date}</strong> <span class="badge ${due.date_basis === "confirmed" ? "badge-ok" : "badge-warn"}">${due.date_basis}${basisNote}</span></div>`;
    } else if (userChoice && userChoice.estimate && userChoice.estimate.date) {
      const e = userChoice.estimate;
      const amount = e.amount_minor === null || e.amount_minor === undefined ? "Amount unknown" : formatMoney(e.currency, e.amount_minor);
      const label = userChoice.cycle ? `you chose ${userChoice.cycle}` : "your entered date";
      dueHtml = `<div class="small">Next charge: <strong>${amount}</strong> on <strong>${e.date}</strong> <span class="badge badge-warn">estimated (${label})</span></div>`;
    } else if (userChoice && userChoice.cycle) {
      dueHtml = `<div class="small muted">You chose <strong>${userChoice.cycle}</strong>; enter the next billing date below to schedule reminders.</div>`;
    } else {
      dueHtml = `<div class="small muted">Next charge date unknown</div>`;
    }

    const effectiveDate = (due && due.date) || (userChoice && userChoice.estimate && userChoice.estimate.date) || null;
    const isCancelled = sub.auto_renew === false || sub.status === "canceled" || sub.status === "cancelled" || sub.status === "suspended";
    const subReminders = (data.reminders || []).filter((r) => r.subscription_key === key);
    const remindersSummary = subReminders.length
      ? `<div class="small muted" style="margin-top:4px;">Scheduled reminders (${data.smtp_configured ? "Gmail email + in-app" : "in-app; set SMTP_EMAIL & SMTP_APP_PASSWORD in .env for Gmail email"}): ${subReminders.map((r) => `${r.reminder_type} (${r.status}, ${formatKarachi(r.due_at)})`).join(" · ")}</div>`
      : "";
    const remindHtml =
      effectiveDate && !isCancelled
        ? `<div class="cta-row">
             <button class="btn btn-small btn-secondary" onclick="scheduleReminder('${key}', 'five_days')">Remind 5d before</button>
             <button class="btn btn-small btn-secondary" onclick="scheduleReminder('${key}', 'one_day')">Remind 1d before</button>
             <button class="btn btn-small btn-primary" onclick="scheduleReminder('${key}', 'one_minute')">Test reminder (1 min)</button>
           </div>`
        : "";

    const chosen = userChoice && userChoice.cycle ? userChoice.cycle : "";
    const savedDate = (userChoice && userChoice.next_charge_date) || "";
    let promptHtml = "";
    if (prompt && prompt.field === "cycle") {
      const needDateInput = !prompt.can_estimate_from_payment || (chosen && !(userChoice && userChoice.estimate && userChoice.estimate.date));
      promptHtml = `<div style="margin-top:8px; padding-top:8px; border-top:1px dashed var(--border);">
        <div class="small muted">The email doesn't say how often this renews. Is it monthly or yearly?</div>
        <div class="cta-row" style="margin-top:6px;">
          <button class="btn btn-small ${chosen === "monthly" ? "btn-primary" : "btn-secondary"}" onclick="saveCycleChoice('${key}', 'monthly')">Monthly</button>
          <button class="btn btn-small ${chosen === "annual" ? "btn-primary" : "btn-secondary"}" onclick="saveCycleChoice('${key}', 'annual')">Annual</button>
          ${needDateInput ? `<input type="date" id="next-date-${key}" value="${savedDate}" class="btn btn-small" />
          <button class="btn btn-small btn-secondary" onclick="saveNextDate('${key}')">Save next date</button>` : ""}
          ${chosen || savedDate ? `<button class="btn btn-small btn-secondary" onclick="saveCycleChoice('${key}', 'clear')">Clear</button>` : ""}
        </div>
      </div>`;
    } else if (prompt && prompt.field === "next_charge_date") {
      promptHtml = `<div style="margin-top:8px; padding-top:8px; border-top:1px dashed var(--border);">
        <div class="small muted">Billing cycle is known, but the next charge date isn't in recent emails. Enter next renewal date:</div>
        <div class="cta-row" style="margin-top:6px;">
          <input type="date" id="next-date-${key}" value="${savedDate}" class="btn btn-small" />
          <button class="btn btn-small btn-primary" onclick="saveNextDate('${key}')">Save next date</button>
          ${savedDate ? `<button class="btn btn-small btn-secondary" onclick="saveCycleChoice('${key}', 'clear')">Clear</button>` : ""}
        </div>
      </div>`;
    }

    row.innerHTML = `
      <div class="item-head">
        <strong>${key}</strong>
        <span class="badge">${sub.status || "unknown"}</span>
      </div>
      <div class="small muted">Auto-renew: ${sub.auto_renew === null ? "Unknown" : sub.auto_renew} · Paid through: ${sub.paid_through || "—"}</div>
      ${dueHtml}
      <div class="small muted" style="margin-top:4px;">Source: ${sourcesHtml || "—"}</div>
      ${remindersSummary}
      ${remindHtml}
      ${promptHtml}
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

async function saveNextDate(subscriptionKey) {
  clearAlert();
  const input = document.getElementById(`next-date-${subscriptionKey}`);
  const val = input ? input.value : "";
  if (!val) {
    showAlert("Please pick a valid next renewal date.");
    return;
  }
  try {
    await apiFetch("/api/cycle-choice", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subscription_key: subscriptionKey, next_charge_date: val }),
    });
    await loadDashboard();
  } catch (err) {
    showAlert(err.message);
  }
}

async function confirmSubscription(sourceId, isSubscription) {
  clearAlert();
  try {
    await apiFetch("/api/confirm-subscription", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source_id: sourceId, is_subscription: isSubscription }),
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
    if (mode === "one_minute") {
      setTimeout(async () => {
        try {
          await apiFetch("/api/reminders/deliver", { method: "POST" });
          await loadDashboard();
        } catch {}
      }, 61000);
    }
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
    document.getElementById("optimizer-result").classList.add("hidden");
    document.getElementById("optimizer-result").innerHTML = "";
    await loadDashboard();
  } catch (err) {
    showAlert(err.message);
  }
});

document.getElementById("btn-find-savings").addEventListener("click", async () => {
  clearAlert();
  const btn = document.getElementById("btn-find-savings");
  const box = document.getElementById("optimizer-result");
  btn.disabled = true;
  btn.textContent = "Finding savings...";
  box.classList.remove("hidden");
  box.innerHTML = '<p class="muted small">Running Gemini + stdio MCP optimizer on the fictional plan catalog...</p>';
  try {
    const res = await apiFetch("/api/optimize-demo", { method: "POST" });
    const opt = res.optimization || {};
    const currencies = opt.currencies || {};
    const review = res.review || {};
    const catalogHtml = (res.plans || [])
      .map((p) => `<li><strong>Plan ${p.plan_id}</strong>: ${formatMoney(p.currency, p.monthly_cost_minor)}/mo — features: ${(p.features || []).join(", ")}</li>`)
      .join("");
    const currencyCards = Object.entries(currencies)
      .map(([cur, g]) => `
        <div class="item-row" style="background:#f0fdf4; border-color:#bbf7d0;">
          <div class="item-head">
            <strong>Plans to keep (${cur}): ${(g.retained_plan_ids || []).join(", ") || "—"}</strong>
            <span class="badge badge-ok">Save ${formatMoney(cur, g.monthly_reduction_minor)}/mo</span>
          </div>
          <div class="small" style="margin-top:4px;">
            Monthly cost: <strong>${formatMoney(cur, g.current_monthly_minor)}</strong> → <strong>${formatMoney(cur, g.minimum_monthly_minor)}</strong>
            · Estimated monthly savings: <strong>${formatMoney(cur, g.monthly_reduction_minor)}</strong>
          </div>
          <div class="small muted" style="margin-top:4px;">
            Preserved features: ${(g.retained_features || []).join(", ") || "—"} · Removable (what-if): ${(g.removal_candidate_ids || []).join(", ") || "None"}
          </div>
        </div>
      `)
      .join("");
    const traceHtml = (review.trace || [])
      .map((tr) => `<li>${tr.tool || "tool"}: ${tr.outcome || "ok"}</li>`)
      .join("");
    box.innerHTML = `
      <details class="trace-box">
        <summary>Fictional plan catalog (${(res.plans || []).length} plans)</summary>
        <ul class="list small">${catalogHtml}</ul>
      </details>
      ${currencyCards}
      <div class="item-row">
        <div class="item-head">
          <strong>Gemini + MCP Recommendation</strong>
          <span class="badge ${review.status === "complete" ? "badge-ok" : "badge-warn"}">${review.status || "unknown"}</span>
        </div>
        <p class="small" style="margin:6px 0 0 0;">${review.summary || "No agent summary returned."}</p>
        <details class="trace-box" open>
          <summary>Optimizer MCP tool trace</summary>
          <ul class="list small">${traceHtml || "<li>No tool calls recorded</li>"}</ul>
        </details>
      </div>
    `;
  } catch (err) {
    box.innerHTML = `<p class="small" style="color:var(--danger);">${err.message}</p>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Find savings";
  }
});

const params = new URLSearchParams(window.location.search);
const initialAuthError = params.get("auth_error");
if (initialAuthError) {
  window.history.replaceState({}, "", "/");
}

loadDashboard().then(() => {
  if (initialAuthError && document.getElementById("dashboard-view").classList.contains("hidden")) {
    showAlert(`Gmail connection did not complete (${initialAuthError}). You can retry anytime.`);
  }
});
