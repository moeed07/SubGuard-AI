import React, { useCallback, useEffect, useRef, useState } from 'react';
import { request } from './api.js';
import { subscriptionRows, timestamp } from './portfolio.js';
import ConnectScreen, { Brand } from './components/ConnectScreen.jsx';
import { DashboardOverview, ScanState } from './components/Dashboard.jsx';
import Subscriptions from './components/Subscriptions.jsx';
import AgentReview from './components/AgentReview.jsx';
import Notifications from './components/Notifications.jsx';
import SavingsOptimizer from './components/SavingsOptimizer.jsx';

const tabs = [['dashboard', 'Dashboard'], ['subscriptions', 'Subscriptions'], ['agent-review', 'Agent Review'], ['notifications', 'Notifications']];

function currentTab() {
  const tab = window.location.hash.slice(1);
  return tabs.some(([id]) => id === tab) ? tab : 'dashboard';
}

export default function App() {
  const [data, setData] = useState(null);
  const [loaded, setLoaded] = useState(false);
  const [view, setView] = useState(currentTab);
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const latestRequest = useRef(0);
  const lastReviewTrace = useRef([]);

  const load = useCallback(async (signal) => {
    const id = ++latestRequest.current;
    const next = await request('/api/dashboard', { signal });
    if (signal?.aborted || id !== latestRequest.current) return next;
    if (!next.connected) lastReviewTrace.current = [];
    else if (next.review?.status === 'complete') lastReviewTrace.current = next.review.trace || [];
    setData(next);
    return next;
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal).catch(() => {
      if (!controller.signal.aborted) setNotice({ error: true, text: 'Couldn’t load SubGuard. Refresh this page to retry.' });
    }).finally(() => { if (!controller.signal.aborted) setLoaded(true); });
    const navigate = () => { setView(currentTab()); setConfirmDelete(false); };
    window.addEventListener('hashchange', navigate);
    return () => {
      controller.abort();
      window.removeEventListener('hashchange', navigate);
    };
  }, [load]);

  useEffect(() => {
    if (!data?.connected || view !== 'notifications' || busy) return;
    const controller = new AbortController();
    const check = () => { if (!document.hidden) load(controller.signal).catch(() => {}); };
    check();
    const timer = setInterval(check, 15_000);
    document.addEventListener('visibilitychange', check);
    return () => { controller.abort(); clearInterval(timer); document.removeEventListener('visibilitychange', check); };
  }, [data?.connected, view, busy, load]);

  useEffect(() => {
    document.title = `${data?.connected ? tabs.find(([id]) => id === view)[1] : 'Connect Gmail'} · SubGuard AI`;
  }, [data?.connected, view]);

  const cancellationShown = Boolean(data?.is_demo && data.evidence?.some((source) => source.source_id === 'm8'));
  const timezone = data?.timezone || data?.portfolio?.timezone || 'Asia/Karachi';

  async function mutate(path, { method = 'POST', body, label, onSuccess }) {
    setBusy(label);
    setNotice(null);
    try {
      const response = await request(path, { method, body, csrf: data.csrf_token });
      await load();
      onSuccess?.(response);
    } catch (error) {
      setNotice({ error: true, text: error.message, reconnect: error.reconnectRequired });
    } finally {
      setBusy('');
    }
  }

  const refresh = (applyCancellation = false) => mutate('/api/refresh', {
    body: data.is_demo ? { include_m8: applyCancellation || cancellationShown } : {},
    label: 'Refreshing…',
  });

  const remind = (subscriptionKey, mode) => mutate('/api/reminders', {
    body: { subscription_key: subscriptionKey, mode }, label: 'Saving reminder…',
    onSuccess: ({ job }) => {
      if (job) setNotice({ text: `Reminder saved for ${timestamp(job.due_at, timezone)} (${timezone}).` });
      if (mode === 'one_minute') {
        setTimeout(() => {
          request('/api/reminders/deliver', { method: 'POST', csrf: data.csrf_token })
            .then(() => load())
            .catch(() => {});
        }, 61_000);
      }
    },
  });

  function leave(deleteData) {
    mutate(deleteData ? '/api/data' : '/api/disconnect', {
      method: deleteData ? 'DELETE' : 'POST', label: deleteData ? 'Deleting data…' : 'Disconnecting…',
      onSuccess: () => { setConfirmDelete(false); window.history.replaceState(null, '', '/'); setView('dashboard'); },
    });
  }

  if (!loaded) return <div className="boot"><Brand /><p className="caption" role="status">Loading SubGuard…</p></div>;
  if (!data?.connected || new URLSearchParams(window.location.search).has('auth_error')) return (
    <ConnectScreen dashboard={data} dashboardError={notice?.error ? notice.text : ''} />
  );

  const portfolio = data.portfolio || {};
  const rows = subscriptionRows(portfolio, data.user_estimates || {});
  const sources = new Map((data.evidence || []).map((source) => [source.source_id, source]));
  const shared = { rows, sources, timezone, busy: Boolean(busy), onRemind: remind };
  const subscriptions = (standalone) => <Subscriptions {...shared} standalone={standalone}
    pending={portfolio.needs_confirmation || []} reminders={data.reminders || []}
    onChoice={(subscriptionKey, choice) => mutate('/api/cycle-choice', { label: 'Saving billing details…', body: { subscription_key: subscriptionKey, ...choice } })}
    onConfirm={(sourceId, isSubscription) => mutate('/api/confirm-subscription', { label: 'Saving classification…', body: { source_id: sourceId, is_subscription: isSubscription } })} />;
  const review = (standalone) => <AgentReview {...shared} standalone={standalone}
    review={{ ...data.review, trace: data.review?.trace?.length ? data.review.trace : lastReviewTrace.current }} onRetry={() => refresh()} />;

  return (
    <>
      <a className="skip-link" href="#app-content">Skip to content</a>
      <header className="masthead border-b border-hairline">
        <div className="page-wrap shell-bar">
          <a href="#dashboard" aria-label="SubGuard AI dashboard"><Brand /></a>
          <nav className="tab-nav" aria-label="SubGuard views">{tabs.map(([id, label]) => (
            <a href={`#${id}`} key={id} aria-current={id === view ? 'page' : undefined}>{label}</a>
          ))}</nav>
          <details className="account-menu">
            <summary>{data.is_demo ? 'Demo account' : 'Gmail account'}</summary>
            <div className="account-actions">
              <button className="quiet-button" disabled={Boolean(busy)} onClick={() => leave(false)}>Disconnect</button>
              <button className="quiet-button" disabled={Boolean(busy)} onClick={() => setConfirmDelete(true)}>Delete data</button>
            </div>
          </details>
        </div>
      </header>
      {data.is_demo && <div className="demo-banner">Fictional example data</div>}
      <main className="page-wrap shell-main" id="app-content" tabIndex={-1} aria-busy={Boolean(busy)}>
        {view === 'dashboard' && data.portfolio && <DashboardOverview portfolio={portfolio} />}
        <div className="scan-toolbar">
          <p className="caption">Last successful scan: {data.last_successful_scan ? <time dateTime={data.last_successful_scan}>
            {timestamp(data.last_successful_scan, timezone)} ({timezone})</time> : 'No successful scan yet'}</p>
          <div className="action-row"><button className="button button-secondary" disabled={Boolean(busy)} onClick={() => refresh()}>{busy === 'Refreshing…' ? busy : 'Refresh'}</button>
            {data.is_demo && !cancellationShown && <button className="quiet-button" disabled={Boolean(busy)} onClick={() => refresh(true)}>Apply fictional cancellation</button>}</div>
        </div>
        {notice && <div className="ledger-card scan-notice" role={notice.error ? 'alert' : 'status'}>{notice.text}
          {notice.reconnect && <a className="button button-primary" href="/auth/google/start">Reconnect Gmail</a>}
        </div>}
        {confirmDelete && <div className="ledger-card scan-notice" role="group" aria-label="Confirm delete data">
          <p className="status-title">Delete SubGuard data for this account?</p>
          <p className="caption">This removes your saved scans, reminders, and notifications from SubGuard.</p>
          <div className="action-row"><button className="button button-secondary" disabled={Boolean(busy)} onClick={() => leave(true)}>Delete my data</button>
            <button className="quiet-button" onClick={() => setConfirmDelete(false)}>Keep my data</button></div>
        </div>}
        <ScanState data={data} />
        {view === 'dashboard' && <div className="ledger-columns">{subscriptions(false)}{review(false)}</div>}
        {view === 'subscriptions' && subscriptions(true)}
        {view === 'agent-review' && <div className="review-tools">
          {review(true)}
          <SavingsOptimizer
            csrf={data.csrf_token}
            isDemo={Boolean(data.is_demo)}
            realPlans={data.real_optimizer_plans || []}
            onSaved={() => load()}
          />
        </div>}
        {view === 'notifications' && <Notifications records={data.notifications || []} timezone={timezone} />}
      </main>
    </>
  );
}
