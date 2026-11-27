import React, { useEffect, useState } from 'react';
import AccessPanel from './AccessPanel.jsx';

const authErrors = new Map([
  ['access_denied', 'Gmail access wasn’t granted. You can try again or explore the fictional example.'],
  ['scope_denied', 'Gmail read-only access wasn’t granted. You can try again or explore the fictional example.'],
  ['oauth_not_configured', 'Gmail connection isn’t set up on this server. You can still explore the fictional example.'],
]);

export function Brand() {
  return (
    <div className="brand flex items-center gap-2.5">
      <svg width="27" height="29" viewBox="0 0 27 29" fill="none" aria-hidden="true">
        <path d="M13.5 2.5 24 6.6v7.2c0 5.9-4.4 10.2-10.5 12.7C7.4 24 3 19.7 3 13.8V6.6l10.5-4.1Z" stroke="currentColor" strokeWidth="1.65" strokeLinejoin="round" />
        <path d="M9 12h9M9 16h6" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" />
      </svg>
      <span>SubGuard<span className="brand-ai"> AI</span></span>
    </div>
  );
}

function Arrow() {
  return (
    <svg width="17" height="17" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M4 10h11m-4.5-4.5L15 10l-4.5 4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function ConnectScreen({ dashboard, dashboardError }) {
  const [action, setAction] = useState(null);
  const [error, setError] = useState(() => {
    const code = new URLSearchParams(window.location.search).get('auth_error');
    return code ? authErrors.get(code) ?? 'Gmail couldn’t be connected. Try again or explore the fictional example.' : '';
  });

  useEffect(() => {
    const resume = (event) => { if (event.persisted) setAction(null); };
    window.addEventListener('pageshow', resume);
    return () => window.removeEventListener('pageshow', resume);
  }, []);

  async function startExample() {
    setError('');
    setAction('example');
    try {
      const response = await fetch('/demo/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({}),
      });
      if (!response.ok || (await response.json()).ok !== true) throw new Error('Example unavailable');
      window.location.assign('/');
    } catch {
      setError('The fictional example couldn’t start. Please try again.');
      setAction(null);
    }
  }

  return (
    <>
      <a className="skip-link" href="#connect">Skip to content</a>
      <header className="masthead border-b border-hairline">
        <div className="page-wrap flex items-center"><Brand /></div>
      </header>
      {dashboard?.is_demo && <div className="demo-banner" role="status">Fictional example data</div>}
      <main id="connect" className="page-wrap" tabIndex={-1}>
        <section className="connect-grid grid items-start" aria-labelledby="connect-title" data-enter>
          <div className="connect-copy">
            <h1 id="connect-title">SubGuard finds the subscriptions hiding in your Gmail and warns you before they charge you.</h1>
            <div className="connect-actions flex flex-wrap items-center gap-3" aria-busy={action !== null}>
              <a
                className="button button-primary inline-flex items-center justify-center gap-2.5"
                href="/auth/google/start"
                aria-disabled={action !== null}
                onClick={(event) => {
                  if (action) {
                    event.preventDefault();
                  } else if (!event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) {
                    setAction('google');
                  }
                }}
              >
                {action === 'google' ? 'Opening Google…' : 'Connect Gmail'} <Arrow />
              </a>
              <button className="button button-secondary inline-flex items-center justify-center" type="button" onClick={startExample} disabled={action !== null}>
                {action === 'example' ? 'Loading fictional example…' : 'Explore fictional example'}
              </button>
            </div>
            <div className="access-limits">
              <p><strong>Read-only.</strong> SubGuard searches only for billing emails: receipts, renewals, trials, and cancellations.</p>
              <p>It can never send, delete, or change any email. Disconnect anytime in <a href="https://myaccount.google.com/connections">Google settings</a>.</p>
            </div>
            {(error || dashboardError) && <p className="notice rounded-chrome" role="alert">{error || dashboardError}</p>}
            {action && <p className="sr-only" role="status">{action === 'google' ? 'Opening Google consent' : 'Loading the SubGuard fictional example'}</p>}
          </div>
          <AccessPanel dashboard={dashboard} />
        </section>
      </main>
    </>
  );
}
