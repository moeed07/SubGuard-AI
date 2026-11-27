import React, { useState } from 'react';
import Evidence from './Evidence.jsx';
import { calendarDate, nameOf } from '../portfolio.js';

const outcomes = {
  get_portfolio: 'Read billing totals and upcoming charges',
  get_subscription_events: 'Checked the subscription’s billing history',
  upsert_review_item: 'Proposed a review for a confirmed charge',
  optimize_subscription_features: 'Compared plans and their verified features',
};

function ToolTrace({ calls, sources, timezone }) {
  if (!calls.length) return <p className="caption">No tool calls are available for this review.</p>;
  return (
    <details className="review-steps">
      <summary>Review steps</summary>
      <ol className="review-timeline">{calls.map((call, index) => (
        <li key={`${call.tool}:${index}`}>
          <span>{call.outcome === 'ok' ? outcomes[call.tool] || 'Completed this tool call' : 'This tool call did not complete'}</span>
          {call.evidence_ids?.length > 0 && <Evidence ids={call.evidence_ids} sources={sources} timezone={timezone} />}
        </li>
      ))}</ol>
      <details className="trace-details">
        <summary>Full tool-call trace</summary>
        <ol className="trace-list">{calls.map((call, index) => (
          <li key={`${call.tool}:${index}`}>
            <code>{call.outcome === 'ok' ? '✓' : '✗'} {call.tool}</code>
            <span>{call.outcome === 'ok' ? 'Succeeded' : 'Failed'}</span>
          </li>
        ))}</ol>
        <p className="caption">Timing isn’t included in this review.</p>
      </details>
    </details>
  );
}

function readDismissals() {
  try { return new Set(JSON.parse(sessionStorage.getItem('subguard-dismissed-proposals') || '[]')); }
  catch { return new Set(); }
}

export default function AgentReview({ review, rows, sources, timezone, busy, onRemind, onRetry, standalone }) {
  const [dismissed, setDismissed] = useState(readDismissals);
  const isRetry = ['failed', 'partial'].includes(review?.status);
  const calls = (review?.trace || []).slice(0, 6);
  const Heading = standalone ? 'h1' : 'h2';
  const eligible = (review?.items || []).filter((item) => item.state === 'open' && item.evidence_ids?.some((id) => sources.has(id)));
  const items = eligible.filter((item) => !dismissed.has(item.item_key));
  function saveDismissals(next) {
    setDismissed(next);
    try { sessionStorage.setItem('subguard-dismissed-proposals', JSON.stringify([...next])); } catch { /* Keep in-memory selection. */ }
  }
  return (
    <section className="ledger-card review-panel" aria-labelledby="agent-review-heading">
      <Heading id="agent-review-heading" className="panel-title">Agent review</Heading>
      <p className="caption review-intro">SubGuard never cancels or pays anything — it only reminds.</p>
      {isRetry && <div className="rail-notice" role="status">
        <p>Review incomplete. Previous proposals are shown when available.</p>
        <button className="quiet-button" disabled={busy} onClick={onRetry}>Retry review</button>
      </div>}
      {items.length > 0 ? <ul className="proposals">{items.map((item) => {
        const row = rows.find((candidate) => candidate.key === item.subscription_key);
        const canRemind = row && !row.stopped && row.due?.date_basis === 'confirmed' && row.due.date === item.target_date;
        const date = calendarDate(item.target_date);
        return <li key={item.item_key} className="proposal">
          <h3>{nameOf(item.subscription_key)}</h3>
          <p className="proposal-summary">{item.kind === 'trial_conversion' ? 'Trial converts to a paid plan' : 'Renewal is scheduled'}{date && ` on ${date}`}.</p>
          <div className="action-row proposal-actions">
            <button className="button button-primary" disabled={busy || !canRemind} onClick={() => onRemind(item.subscription_key, 'default')}>Remind me</button>
            <button className="quiet-button" onClick={() => saveDismissals(new Set([...dismissed, item.item_key]))}>Dismiss</button>
            <Evidence ids={item.evidence_ids} sources={sources} timezone={timezone} label="See evidence" />
          </div>
          {canRemind && <button className="quiet-button test-reminder" disabled={busy} onClick={() => onRemind(item.subscription_key, 'one_minute')}>Test reminder (1 minute)</button>}
        </li>;
      })}</ul> : <p className="caption empty-list">No open proposals.</p>}
      {eligible.length > items.length && <button className="quiet-button" onClick={() => saveDismissals(new Set([...dismissed].filter((key) => !eligible.some((item) => item.item_key === key))))}>Restore dismissed proposals</button>}
      <ToolTrace calls={calls} sources={sources} timezone={timezone} />
      <p className="caption review-footer">The review did not change any email or subscription.</p>
    </section>
  );
}
