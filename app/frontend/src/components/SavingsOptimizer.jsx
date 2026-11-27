import React, { useState } from 'react';
import { request } from '../api.js';
import { money } from '../portfolio.js';

const metrics = [
  ['current_monthly_minor', 'Current monthly cost'],
  ['minimum_monthly_minor', 'Minimum monthly cost'],
  ['monthly_reduction_minor', 'Potential monthly savings'],
];

const planNames = (ids) => ids.map((id) => `Plan ${id}`).join(', ');

export default function SavingsOptimizer({ csrf }) {
  const [data, setData] = useState(null);
  const [action, setAction] = useState(null);
  const [error, setError] = useState('');

  async function run(withGemini) {
    setError('');
    setAction(withGemini ? 'gemini' : 'calculate');
    try {
      setData(await request('/api/optimizer', {
        method: 'POST', csrf, body: { run_with_gemini: withGemini },
      }));
    } catch (error) {
      setError(error.message);
    } finally {
      setAction(null);
    }
  }

  return (
    <section className="ledger-card savings-panel" aria-labelledby="savings-title" aria-busy={Boolean(action)}>
      <h2 className="panel-title" id="savings-title">Subscription savings</h2>
      <p className="caption">Compare fictional plans at the lowest monthly cost while keeping every listed feature.</p>
      <div className="action-row savings-actions">
        <button type="button" className="button button-secondary" disabled={Boolean(action)} onClick={() => run(false)}>
          {action === 'calculate' ? 'Calculating…' : 'Find savings'}
        </button>
        {data && <button type="button" className="quiet-button" disabled={Boolean(action)} onClick={() => run(true)}>
          {action === 'gemini' ? 'Running with Gemini…' : 'Run with Gemini'}
        </button>}
      </div>
      {error && <p className="rail-notice" role="alert">{error}</p>}
      {data && <div className="savings-results" aria-live="polite">
        {Object.entries(data.result.currencies).map(([currency, result]) => (
          <div className="savings-result" key={currency}>
            {result.status === 'complete' ? <>
              <dl className="savings-metrics">{metrics.map(([field, label]) => <div key={field}>
                <dt className="caption">{label}</dt><dd className="money">{money(currency, result[field])}</dd>
              </div>)}</dl>
              <dl className="savings-decision">
                <div><dt>Keep</dt><dd>{planNames(result.retained_plan_ids)}</dd></div>
                <div><dt>Removal candidates</dt><dd>{planNames(result.removal_candidate_ids) || 'None'}</dd></div>
                <div><dt>Features preserved</dt><dd>{result.retained_features.join(', ')}</dd></div>
              </dl>
            </> : <p className="caption">A complete comparison is unavailable for {currency}.</p>}
          </div>
        ))}
        <details className="review-steps">
          <summary>Fictional plan catalog</summary>
          <ul className="savings-catalog">{data.plans.map((plan) => (
            <li key={plan.plan_id}><span>Plan {plan.plan_id} · {plan.features.join(', ')}</span><span className="money">{money(plan.currency, plan.monthly_cost_minor)}/month</span></li>
          ))}</ul>
        </details>
        {data.agent && <div className="rail-notice">
          <p>{data.agent.completed ? 'Gemini completed the optimizer call over MCP.' : 'The Gemini check did not complete. The calculated savings are still shown.'}</p>
          {data.agent.trace.length > 0 && <details className="trace-details">
            <summary>Optimizer tool-call trace</summary>
            <ol className="trace-list">{data.agent.trace.slice(0, 6).map((call, index) => <li key={`${call.tool}:${index}`}>
              <code>{call.outcome === 'ok' ? '✓' : '✗'} {call.tool}</code>
            </li>)}</ol>
          </details>}
        </div>}
        <p className="caption review-footer">Savings depend on this catalog. No plans are changed.</p>
      </div>}
    </section>
  );
}
