const currencyOptions = new Map();
const DAY_MS = 86_400_000;
const ZERO_DECIMAL_CURRENCIES = new Set([
  'BIF', 'CLP', 'DJF', 'GNF', 'ISK', 'JPY', 'KMF', 'KRW',
  'MGA', 'PYG', 'RWF', 'UGX', 'VND', 'VUV', 'XAF', 'XOF', 'XPF',
]);
const THREE_DECIMAL_CURRENCIES = new Set(['BHD', 'IQD', 'JOD', 'KWD', 'LYD', 'OMR', 'TND']);

export function money(currency, minor) {
  if (!currency || !Number.isSafeInteger(minor)) return 'Amount unknown';
  if (!currencyOptions.has(currency)) {
    const digits = ZERO_DECIMAL_CURRENCIES.has(currency) ? 0 : THREE_DECIMAL_CURRENCIES.has(currency) ? 3 : 2;
    currencyOptions.set(currency, {
      divisor: 10 ** digits,
      format: new Intl.NumberFormat('en-PK', { maximumFractionDigits: digits }),
    });
  }
  const { divisor, format } = currencyOptions.get(currency);
  return `${currency} ${format.format(minor / divisor)}`;
}

export function nameOf(key) {
  return (key || 'Subscription').split('-').map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(' ');
}

export function calendarDate(date) {
  if (!date) return null;
  const parsed = new Date(`${date}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return null;
  return new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', day: 'numeric', month: 'short', year: 'numeric' })
    .format(parsed);
}

export function timestamp(value, timezone = 'Asia/Karachi', dateOnly = false) {
  if (!value) return null;
  const parsed = new Date(typeof value === 'string' && !/[zZ]|[+-]\d\d:\d\d$/.test(value) ? `${value}Z` : value);
  if (Number.isNaN(parsed.getTime())) return null;
  return new Intl.DateTimeFormat('en-GB', dateOnly ? { timeZone: timezone, day: 'numeric', month: 'short' } : {
    timeZone: timezone, dateStyle: 'medium', timeStyle: 'short',
  }).format(parsed);
}

export function confirmedWindow(portfolio) {
  const start = Date.parse(portfolio?.as_of || '');
  const days = Array.from({ length: 8 }, () => []);
  if (!Number.isFinite(start)) return days;
  for (const due of portfolio.due || []) {
    if (due.date_basis !== 'confirmed' || !due.date) continue;
    const offset = (Date.parse(due.date) - start) / DAY_MS;
    if (Number.isInteger(offset) && offset >= 0 && offset < days.length) days[offset].push(due);
  }
  return days;
}

export function subscriptionRows(portfolio, estimates) {
  const dueByKey = new Map();
  for (const due of portfolio.due || []) {
    if (!due.date) continue;
    if (!dueByKey.has(due.subscription_key)) dueByKey.set(due.subscription_key, []);
    dueByKey.get(due.subscription_key).push(due);
  }
  return (portfolio.subscriptions || []).map((subscription) => {
    const key = subscription.subscription_key;
    const timeline = portfolio.timelines?.[key] || [];
    const upcoming = (dueByKey.get(key) || []).toSorted((a, b) => a.date.localeCompare(b.date));
    const choice = estimates[key];
    const stopped = subscription.auto_renew === false || ['canceled', 'cancelled', 'suspended'].includes(subscription.status);
    const due = stopped ? null : upcoming[0] || choice?.estimate || null;
    const lastPayment = timeline.findLast((event) => event.kind === 'payment');
    const cycle = timeline.findLast((event) => event.cycle)?.cycle || choice?.cycle;
    const evidence = [...new Set([...(due?.evidence_ids || []), ...(subscription.evidence_ids || [])])];
    return { ...subscription, key, timeline, due, upcoming, cycle, lastPayment, choice, stopped, evidence,
      prompt: stopped ? null : portfolio.billing_prompts?.[key] };
  }).sort((a, b) => {
    if (a.stopped !== b.stopped) return a.stopped ? 1 : -1;
    const needsAction = (row) => row.status === 'payment_failed' || row.status === 'cancellation_requested';
    if (needsAction(a) !== needsAction(b)) return needsAction(a) ? -1 : 1;
    return (a.due?.date || '9999').localeCompare(b.due?.date || '9999') || a.key.localeCompare(b.key);
  });
}
