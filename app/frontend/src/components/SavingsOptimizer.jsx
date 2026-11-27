import React, { useEffect, useState } from 'react';
import { request } from '../api.js';
import { money } from '../portfolio.js';

const metrics = [
  ['current_monthly_minor', 'Current monthly cost'],
  ['minimum_monthly_minor', 'Minimum monthly cost'],
  ['monthly_reduction_minor', 'Potential monthly savings'],
];

const planNames = (ids) => ids.map((id) => `Plan ${id}`).join(', ');

function toDraftRows(realPlans) {
  return (realPlans || []).map((p) => ({
    plan_id: p.plan_id,
    currency: p.currency || 'PKR',
    monthly_cost:
      p.monthly_cost_minor !== null && p.monthly_cost_minor !== undefined
        ? String(p.monthly_cost_minor / 100)
        : '',
    features: Array.isArray(p.features) ? p.features.join(', ') : '',
  }));
}

function OptimizerOutput({ plans, result, agent, review, isFictional }) {
  const currencies = result?.currencies || {};
  const missingByPlan = result?.missing_fields_by_plan || {};
  const trace = agent?.trace || review?.trace || [];
  const completed = agent ? agent.completed : review?.status === 'complete';

  return (
    <div className="savings-results" aria-live="polite">
      {Object.keys(missingByPlan).length > 0 && (
        <div className="rail-notice" role="status">
          <strong>Missing fields:</strong>{' '}
          {Object.entries(missingByPlan)
            .map(([planId, fields]) => `${planId} (${fields.join(', ')})`)
            .join(' · ')}
        </div>
      )}
      {Object.entries(currencies).map(([currency, group]) => (
        <div className="savings-result" key={currency}>
          {group.status === 'complete' ? (
            <>
              <dl className="savings-metrics">
                {metrics.map(([field, label]) => (
                  <div key={field}>
                    <dt className="caption">{label}</dt>
                    <dd className="money">{money(currency, group[field])}</dd>
                  </div>
                ))}
              </dl>
              <dl className="savings-decision">
                <div>
                  <dt>Keep</dt>
                  <dd>{isFictional ? planNames(group.retained_plan_ids) : group.retained_plan_ids.join(', ')}</dd>
                </div>
                <div>
                  <dt>Removal candidates</dt>
                  <dd>
                    {group.removal_candidate_ids.length
                      ? isFictional
                        ? planNames(group.removal_candidate_ids)
                        : group.removal_candidate_ids.join(', ')
                      : 'None'}
                  </dd>
                </div>
                <div>
                  <dt>Features preserved</dt>
                  <dd>{group.retained_features.join(', ') || '—'}</dd>
                </div>
              </dl>
            </>
          ) : (
            <p className="caption">
              Complete comparison unavailable for {currency} — fill in missing prices/features below (
              {(group.missing_plan_ids || []).join(', ') || group.reason || 'incomplete'}).
            </p>
          )}
        </div>
      ))}
      <details className="review-steps">
        <summary>{isFictional ? 'Fictional plan catalog' : 'Active subscriptions compared'}</summary>
        <ul className="savings-catalog">
          {(plans || []).map((plan) => (
            <li key={plan.plan_id}>
              <span>
                {isFictional ? `Plan ${plan.plan_id}` : plan.plan_id} ·{' '}
                {Array.isArray(plan.features) && plan.features.length ? plan.features.join(', ') : 'features missing'}
              </span>
              <span className="money">
                {plan.currency && plan.monthly_cost_minor !== null && plan.monthly_cost_minor !== undefined
                  ? `${money(plan.currency, plan.monthly_cost_minor)}/month`
                  : 'price missing'}
              </span>
            </li>
          ))}
        </ul>
      </details>
      {(agent || review) && (
        <div className="rail-notice">
          <p>
            {completed
              ? 'Gemini completed the optimizer call over MCP.'
              : 'The Gemini check did not complete. Calculated results are still shown.'}
          </p>
          {review?.summary && <p className="caption">{review.summary}</p>}
          {trace.length > 0 && (
            <details className="trace-details">
              <summary>Optimizer tool-call trace</summary>
              <ol className="trace-list">
                {trace.slice(0, 6).map((call, index) => (
                  <li key={`${call.tool}:${index}`}>
                    <code>
                      {call.outcome === 'ok' ? '✓' : '✗'} {call.tool}
                    </code>
                  </li>
                ))}
              </ol>
            </details>
          )}
        </div>
      )}
      <p className="caption review-footer">Savings depend on this catalog. No plans are changed.</p>
    </div>
  );
}

export default function SavingsOptimizer({ csrf, isDemo, realPlans = [], onSaved }) {
  const [data, setData] = useState(null);
  const [realData, setRealData] = useState(null);
  const [drafts, setDrafts] = useState(() => toDraftRows(realPlans));
  const [action, setAction] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    setDrafts(toDraftRows(realPlans));
  }, [realPlans]);

  async function runDemo(withGemini) {
    setError('');
    setAction(withGemini ? 'gemini' : 'calculate');
    try {
      setData(
        await request('/api/optimizer', {
          method: 'POST',
          csrf,
          body: { run_with_gemini: withGemini },
        })
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setAction(null);
    }
  }

  async function runReal() {
    setError('');
    setAction('real');
    try {
      if (drafts.length > 0) {
        await request('/api/plan-metadata', {
          method: 'POST',
          csrf,
          body: {
            plans: drafts.map((d) => ({
              subscription_key: d.plan_id,
              currency: d.currency,
              monthly_cost: d.monthly_cost,
              features: d.features,
            })),
          },
        });
      }
      const res = await request('/api/optimize-real', { method: 'POST', csrf });
      setRealData(res);
      onSaved?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setAction(null);
    }
  }

  function updateDraft(index, field, value) {
    setDrafts((prev) => prev.map((row, i) => (i === index ? { ...row, [field]: value } : row)));
  }

  return (
    <section className="ledger-card savings-panel" aria-labelledby="savings-title" aria-busy={Boolean(action)}>
      <h2 className="panel-title" id="savings-title">Subscription savings</h2>

      {drafts.length > 0 && (
        <div style={{ marginTop: '12px' }}>
          <p className="caption">
            Auto-detected features and monthly prices for your active subscriptions. Edit any missing price or feature tag below, then run the optimizer.
          </p>
          <div className="stack" style={{ marginTop: '10px', display: 'grid', gap: '8px' }}>
            {drafts.map((row, idx) => (
              <div className="choice-form" key={row.plan_id} style={{ borderTop: '1px solid var(--color-hairline)', paddingTop: '8px' }}>
                <strong style={{ minWidth: '170px', alignSelf: 'center' }}>{row.plan_id}</strong>
                <label>
                  Currency
                  <input
                    type="text"
                    value={row.currency}
                    maxLength={3}
                    style={{ width: '68px' }}
                    onChange={(e) => updateDraft(idx, 'currency', e.target.value.toUpperCase())}
                  />
                </label>
                <label>
                  Monthly cost
                  <input
                    type="text"
                    value={row.monthly_cost}
                    placeholder="e.g. 379"
                    style={{ width: '105px' }}
                    onChange={(e) => updateDraft(idx, 'monthly_cost', e.target.value)}
                  />
                </label>
                <label style={{ flex: '1 1 200px' }}>
                  Features
                  <input
                    type="text"
                    value={row.features}
                    placeholder="e.g. ai, music, storage"
                    onChange={(e) => updateDraft(idx, 'features', e.target.value)}
                  />
                </label>
              </div>
            ))}
          </div>
          <div className="action-row savings-actions">
            <button type="button" className="button button-primary" disabled={Boolean(action)} onClick={runReal}>
              {action === 'real' ? 'Optimizing…' : 'Optimize my subscriptions'}
            </button>
          </div>
          {realData && (
            <OptimizerOutput
              plans={realData.plans}
              result={realData.optimization}
              review={realData.review}
              isFictional={false}
            />
          )}
        </div>
      )}

      {isDemo && (
        <div style={{ marginTop: drafts.length > 0 ? '24px' : '8px', borderTop: drafts.length > 0 ? '1px solid var(--color-hairline)' : 'none', paddingTop: drafts.length > 0 ? '16px' : '0' }}>
          <p className="caption">Compare fictional catalog plans at the lowest monthly cost while keeping every listed feature.</p>
          <div className="action-row savings-actions">
            <button type="button" className="button button-secondary" disabled={Boolean(action)} onClick={() => runDemo(false)}>
              {action === 'calculate' ? 'Calculating…' : 'Find savings (fictional catalog)'}
            </button>
            {data && (
              <button type="button" className="quiet-button" disabled={Boolean(action)} onClick={() => runDemo(true)}>
                {action === 'gemini' ? 'Running with Gemini…' : 'Run with Gemini'}
              </button>
            )}
          </div>
          {data && <OptimizerOutput plans={data.plans} result={data.result} agent={data.agent} isFictional />}
        </div>
      )}

      {error && <p className="rail-notice" role="alert">{error}</p>}
    </section>
  );
}
