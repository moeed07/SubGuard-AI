import React from 'react';
import { confirmedWindow, money, nameOf } from '../portfolio.js';

const indicators = [
  ['paid_minor', 'Paid during the scan window', 'Payments actually collected in the emails scanned.'],
  ['monthly_equivalent_minor', 'Forward monthly equivalent', 'Paid renewing plans expressed as a monthly cost.'],
  ['next_7d_minor', 'Confirmed due in the next 7 days', 'Charges dated in email from today through day seven.'],
];

export function DashboardOverview({ portfolio }) {
  const days = confirmedWindow(portfolio);
  const count = portfolio.subscriptions?.length ?? 0;
  const trialCount = days.flat().filter((due) => due.kind === 'trial_conversion').length;
  const verdict = `${count} ${count === 1 ? 'subscription' : 'subscriptions'} tracked${trialCount ?
    `, with ${trialCount} ${trialCount === 1 ? 'trial converting' : 'trials converting'} in the next seven days` : ''}.`;
  const bands = Object.entries(portfolio.totals || {});

  return (
    <div className="overview">
      <h1 className="verdict">{verdict}</h1>
      <div className="kpi-bands" aria-label="Billing totals by currency">
        {bands.map(([currency, totals]) => (
          <section className="ledger-card kpi-band" key={currency} aria-label={`${currency} billing totals`}>
            <dl className="kpi-grid">
              {indicators.map(([key, label, definition]) => (
                <div key={key} className="metric">
                  <dt>{label}</dt>
                  <dd className="money kpi-number">{money(currency, totals[key])}</dd>
                  <dd className="caption">{definition}</dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
      </div>
      <section className="ledger-card due-rail" aria-labelledby="confirmed-dates-heading">
        <h2 id="confirmed-dates-heading" className="panel-title">Confirmed in the next 7 days</h2>
        <div className="timeline-scroll" tabIndex={0} aria-label="Confirmed charges by day">
          <ol className="timeline-days">
            {days.map((entries, day) => (
              <li key={day} className="timeline-day">
                <span className="day-label">{day ? `+${day}` : 'Today'}</span>
                <span className={`day-marker${entries.length ? ' has-charge' : ''}`} aria-hidden="true" />
                {entries.map((entry) => (
                  <div key={`${entry.subscription_key}:${entry.kind}:${entry.currency}`} className="timeline-charge">
                    <span className="money">{money(entry.currency, entry.amount_minor)}</span>
                    <span>{nameOf(entry.subscription_key)}</span>
                  </div>
                ))}
              </li>
            ))}
          </ol>
        </div>
        {!days.some((entries) => entries.length) && <p className="caption">No confirmed charges in this window.</p>}
      </section>
    </div>
  );
}

export function ScanState({ data }) {
  const messages = {
    never: ['No scan yet', 'Refresh to search for billing emails.'],
    empty: ['No matching mail', 'The scan did not find any billing emails in the search window.'],
    zero_results: ['No subscriptions found', 'The scan completed without finding subscription billing events.'],
    failed: ['Scan failed', 'Refresh to try again. Previously saved results are shown when available.'],
    partial: ['Partial scan', 'Some mail could not be checked. Refresh to try again.'],
  };
  const entry = messages[data.scan_status] || (data.partial ? messages.partial : null);
  if (!entry) return null;
  return (
    <div className="ledger-card scan-notice" role={data.scan_status === 'failed' ? 'alert' : 'status'}>
      <p className="status-title">{entry[0]}</p>
      <p className="caption">{entry[1]}</p>
      {data.partial && !['failed', 'partial'].includes(data.scan_status) && <p className="caption">This scan was partial.</p>}
    </div>
  );
}
