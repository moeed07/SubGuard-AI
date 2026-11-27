import assert from 'node:assert/strict';
import test from 'node:test';
import { confirmedWindow, money, subscriptionLogoId, subscriptionRows } from '../src/portfolio.js';

test('money uses the currency exponent and visibly separates unknown and zero', () => {
  assert.equal(money('PKR', 1_270_000), 'PKR 12,700');
  assert.equal(money('PKR', 0), 'PKR 0');
  assert.equal(money('PKR', null), 'Amount unknown');
  assert.equal(money('JPY', 251), 'JPY 251');
  assert.equal(money('KWD', 1005), 'KWD 1.005');
});

test('the rail includes today and day seven without mixing estimates or distant charges', () => {
  const due = [
    { date: '2026-11-26', date_basis: 'confirmed', currency: 'PKR' },
    { date: '2026-11-29', date_basis: 'estimated', currency: 'PKR' },
    { date: '2026-12-03', date_basis: 'confirmed', currency: 'USD' },
    { date: '2026-12-04', date_basis: 'confirmed', currency: 'PKR' },
  ];
  const days = confirmedWindow({ as_of: '2026-11-26', due });
  assert.equal(days.length, 8);
  assert.deepEqual(days[0], [due[0]]);
  assert.deepEqual(days[7], [due[2]]);
  assert.equal(days.flat().length, 2);
});

test('a saved estimate cannot revive a canceled renewal or replace a confirmed charge', () => {
  const estimate = { date: '2026-11-29', date_basis: 'estimated' };
  const confirmed = { date: '2026-12-01', date_basis: 'confirmed', subscription_key: 'active', currency: 'PKR', amount_minor: 1_200_000 };
  const result = subscriptionRows({
    subscriptions: [{ subscription_key: 'stopped', status: 'canceled' }, { subscription_key: 'active', status: 'active' }],
    due: [confirmed],
    timelines: { stopped: [{ kind: 'payment', amount_minor: 200_000 }] },
  }, { stopped: { estimate }, active: { estimate } });
  assert.equal(result[0].due, confirmed);
  assert.equal(result[1].due, null);
  assert.equal(result[1].lastPayment.amount_minor, 200_000);
});

test('subscriptionRows and confirmedWindow prefer priced entries over same-date null-amount notices', () => {
  const unpriced = { date: '2026-12-01', date_basis: 'confirmed', subscription_key: 'netflix-standard', currency: null, amount_minor: null, evidence_ids: ['src_null'] };
  const priced = { date: '2026-12-01', date_basis: 'confirmed', subscription_key: 'netflix-standard', currency: 'PKR', amount_minor: 80_000, evidence_ids: ['src_pkr'] };
  const rows = subscriptionRows({
    subscriptions: [{ subscription_key: 'netflix-standard', status: 'active', evidence_ids: ['src_pkr'] }],
    due: [unpriced, priced],
    timelines: { 'netflix-standard': [] },
  }, {});
  assert.equal(rows[0].due.amount_minor, 80_000);
  assert.equal(rows[0].due.currency, 'PKR');
  const days = confirmedWindow({ as_of: '2026-11-27', due: [unpriced, priced] });
  assert.equal(days[4].length, 1);
  assert.equal(days[4][0].amount_minor, 80_000);
});

test('subscriptionLogoId resolves uploaded brand logos and returns null for unknown plans', () => {
  assert.equal(subscriptionLogoId('netflix-standard'), 'netflix');
  assert.equal(subscriptionLogoId('google-ai-pro'), 'google-ai-pro');
  assert.equal(subscriptionLogoId('microsoft-365-personal'), 'microsoft');
  assert.equal(subscriptionLogoId('tamasha'), 'tamasha');
  assert.equal(subscriptionLogoId('chatgpt-plus'), 'chatgpt');
  assert.equal(subscriptionLogoId('spotify-premium-individual'), 'spotify');
  assert.equal(subscriptionLogoId('design-pro'), null);
  assert.equal(subscriptionLogoId('individual'), null);
});
