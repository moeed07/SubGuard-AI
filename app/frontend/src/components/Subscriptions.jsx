import React, { useState } from 'react';
import Evidence from './Evidence.jsx';
import { logoForSubscription } from '../logos.js';
import { calendarDate, hasPricedAmount, money, nameOf, timestamp } from '../portfolio.js';

const stoppedNames = { suspended: 'Suspended', canceled: 'Canceled', cancelled: 'Canceled' };

function SubscriptionTile({ subscriptionKey, name }) {
  const logo = logoForSubscription(subscriptionKey);
  const [failedSrc, setFailedSrc] = useState(null);
  const showLogo = Boolean(logo && failedSrc !== logo);
  return (
    <span className="initial-tile" aria-hidden="true">
      {showLogo ? (
        <img
          src={logo}
          alt=""
          className="initial-tile-logo"
          onError={() => setFailedSrc(logo)}
        />
      ) : name[0]}
    </span>
  );
}

function DateStatus({ row }) {
  if (row.stopped) return <span className="caption">{stoppedNames[row.status] || 'Auto-renewal off'}{row.paid_through && ` · Access through ${calendarDate(row.paid_through)}`}</span>;
  if (!row.due?.date) return <span className="unknown-date"><span aria-hidden="true">?</span> Date unknown — no date in email</span>;
  if (row.due.date_basis === 'confirmed') return <span className="date-pill confirmed"><span aria-hidden="true">✓</span> Confirmed</span>;
  if (row.due.date_basis !== 'estimated') return <span className="unknown-date"><span aria-hidden="true">?</span> Date unknown — no date in email</span>;
  const reason = row.due.cycle_basis === 'payment_history' ? 'Based on the interval between past payments.'
    : row.due.cycle_basis === 'user_selected' ? row.choice?.next_charge_date ? 'Based on the date you entered.' : 'Based on the billing cycle you selected.'
      : `Based on ${row.cycle ? `${row.cycle} billing` : 'billing cadence'} and the last payment.`;
  return <><span className="date-pill estimated"><span aria-hidden="true">~</span> Estimated</span><span className="caption estimate-reason">{reason}</span></>;
}

function BillingChoice({ row, onChoice, busy }) {
  const [cycle, setCycle] = useState(row.choice?.cycle || '');
  const [date, setDate] = useState(row.choice?.next_charge_date || '');
  return (
    <form className="choice-form" onSubmit={(event) => {
      event.preventDefault();
      if (cycle || date) onChoice(row.key, { ...(cycle && { cycle }), ...(date && { next_charge_date: date }) });
    }}>
      {row.prompt.field === 'cycle' && <label>Billing cycle<select value={cycle} onChange={(event) => setCycle(event.target.value)}>
        <option value="">Unknown</option><option value="monthly">Monthly</option><option value="annual">Annual</option>
      </select></label>}
      <label>Next charge date <input type="date" value={date} onChange={(event) => setDate(event.target.value)} /></label>
      <button className="button button-secondary" disabled={busy || (!cycle && !date)}>Save billing details</button>
      {(row.choice?.cycle || row.choice?.next_charge_date) && <button type="button" className="quiet-button" disabled={busy}
        onClick={() => { setCycle(''); setDate(''); onChoice(row.key, { cycle: 'clear' }); }}>Clear saved choice</button>}
    </form>
  );
}

function SubscriptionRow({ row, sources, timezone, busy, onChoice, onRemind, reminders }) {
  const [expanded, setExpanded] = useState(false);
  const name = nameOf(row.key);
  const dueHasAmount = hasPricedAmount(row.due);
  const upcomingEntries = row.stopped ? [] : (row.upcoming || []);
  const priced = [row.due, ...upcomingEntries, row.lastPayment].find(hasPricedAmount) || row.due || row.lastPayment;
  const date = ['estimated', 'confirmed'].includes(row.due?.date_basis) ? calendarDate(row.due.date) : null;
  const fallbackFromLastPayment = Boolean(date && !dueHasAmount && priced === row.lastPayment && hasPricedAmount(priced));
  const topSource = row.evidence.find((id) => sources.has(id));
  const payments = row.timeline.filter((event) => event.kind === 'payment').toReversed();
  return (
    <li className="subscription-row">
      <button type="button" className="subscription-toggle" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
        <SubscriptionTile subscriptionKey={row.key} name={name} />
        <span className="subscription-name"><strong>{name}</strong><span className="caption">{row.cycle ? nameOf(row.cycle) : 'Cadence not stated'}{row.status === 'payment_failed' && ' · Payment failed'}</span></span>
        <span className="subscription-price"><strong className="money">{money(priced?.currency, priced?.amount_minor)}</strong>
          <span className="caption">{date ? (fallbackFromLastPayment ? `Last collected · Next ${date}` : `${row.due.kind === 'trial_conversion' ? 'First charge' : 'Next charge'} · ${date}`) : row.lastPayment ? 'Last collected' : 'No dated charge'}</span>
        </span>
        <span className="row-chevron" aria-hidden="true">{expanded ? '−' : '+'}</span>
      </button>
      <div className="subscription-meta"><DateStatus row={row} /><Evidence ids={topSource ? [topSource] : []} sources={sources} timezone={timezone} /></div>
      {expanded && <div className="subscription-detail">
        <h3>Payment history</h3>
        {payments.length ? <ul className="payment-list">{payments.map((payment) => (
          <li key={payment.event_id}><time dateTime={payment.event_date || payment.received_at}>{calendarDate(payment.event_date) || timestamp(payment.received_at, timezone, true) || 'Date unknown'}</time>
            <span className="money">{money(payment.currency, payment.amount_minor)}</span>
            <Evidence ids={[payment.source_id]} sources={sources} timezone={timezone} />
          </li>
        ))}</ul> : <p className="caption">No collected payments in the scan window.</p>}
        {row.evidence.length > 1 && <div className="detail-evidence"><Evidence ids={row.evidence} sources={sources} timezone={timezone} /></div>}
        {reminders.length > 0 && <ul className="reminders-inline">{reminders.map((job) => (
          <li key={job.job_id}>{nameOf(job.status)} reminder · {timestamp(job.due_at, timezone)}</li>
        ))}</ul>}
        {row.prompt && <BillingChoice row={row} onChoice={onChoice} busy={busy} />}
        {!row.stopped && row.due?.date && <div className="action-row" style={{ marginTop: '10px', flexWrap: 'wrap' }}>
          {!row.prompt && row.due?.date_basis === 'confirmed' && (
            <button type="button" className="button button-primary" disabled={busy} onClick={() => onRemind(row.key, 'default')}>Remind me</button>
          )}
          <button type="button" className="button button-secondary" disabled={busy} onClick={() => onRemind(row.key, 'five_days')}>Remind 5d before</button>
          <button type="button" className="button button-secondary" disabled={busy} onClick={() => onRemind(row.key, 'one_day')}>Remind 1d before</button>
          <button type="button" className="button button-primary" disabled={busy} onClick={() => onRemind(row.key, 'one_minute')}>Test reminder (1 min)</button>
        </div>}
        {!row.prompt && !row.due?.date && topSource && (
          <a className="button button-secondary inline-flex items-center" href={`/api/evidence/${encodeURIComponent(topSource)}`}
            target="_blank" rel="noopener noreferrer">Open source email</a>
        )}
      </div>}
    </li>
  );
}

export default function Subscriptions({ rows, pending, reminders, sources, timezone, busy, onChoice, onConfirm, onRemind, standalone }) {
  const trials = rows.filter((row) => row.status === 'trial' || row.due?.kind === 'trial_conversion');
  const trialKeys = new Set(trials.map((row) => row.key));
  const paid = rows.filter((row) => !trialKeys.has(row.key));
  const Heading = standalone ? 'h1' : 'h2';
  const props = { sources, timezone, busy, onChoice, onRemind };
  return (
    <section className="ledger-card subscription-panel" aria-labelledby="subscriptions-heading">
      <Heading className="panel-title" id="subscriptions-heading">Subscriptions</Heading>
      {pending.length > 0 && <div className="subscription-group">
        <h3>Receipts to check</h3>
        {pending.map((receipt) => {
          const event = receipt.events?.[0];
          return <div className="receipt" key={receipt.source_id}>
            <p>Is this payment a subscription? <strong className="money">{money(event?.currency, event?.amount_minor)}</strong></p>
            <Evidence ids={[receipt.source_id]} sources={sources} timezone={timezone} />
            <div className="action-row"><button className="button button-secondary" disabled={busy} onClick={() => onConfirm(receipt.source_id, true)}>Yes, subscription</button>
              <button className="quiet-button" disabled={busy} onClick={() => onConfirm(receipt.source_id, false)}>One-time purchase</button></div>
          </div>;
        })}
      </div>}
      {[['Trial conversions', trials], ['Plans and renewals', paid]].map(([heading, list]) => list.length > 0 && (
        <div className="subscription-group" key={heading}>
          <h3>{heading}</h3>
          <ul>{list.map((row) => <SubscriptionRow key={row.key} row={row} {...props} reminders={reminders.filter((job) => job.subscription_key === row.key && job.status !== 'canceled')} />)}</ul>
        </div>
      ))}
      {!rows.length && !pending.length && <p className="caption empty-list">No subscriptions to show.</p>}
    </section>
  );
}
