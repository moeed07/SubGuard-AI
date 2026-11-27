import React from 'react';

function AccessList({ title, items }) {
  return (
    <section>
      <h3 className="access-list-title">{title}</h3>
      <ul className="grid gap-2.5">
        {items.map((item) => <li key={item}>{item}</li>)}
      </ul>
    </section>
  );
}

export default function AccessPanel({ dashboard, checking }) {
  let connection = 'No Gmail account connected';
  if (checking) connection = 'Checking connection…';
  else if (!dashboard) connection = 'Connection status unavailable';
  else if (dashboard.is_demo) connection = 'Fictional example data';
  else if (dashboard.connected) connection = 'Gmail connected';

  return (
    <aside className="access-panel rounded-card border border-hairline bg-surface" aria-labelledby="gmail-access-title">
      <div className="flex items-start justify-between gap-4">
        <h2 id="gmail-access-title" className="panel-title">Gmail access</h2>
        <code className="scope rounded-chrome">gmail.readonly</code>
      </div>
      <div className="access-lists grid grid-cols-2">
        <AccessList title="Will read" items={['Receipts', 'Renewals', 'Trials', 'Cancellations']} />
        <AccessList title="Will never" items={['Send email', 'Delete or change email', 'Read personal mail for any other purpose', 'Sell your data']} />
      </div>
      <p className="connection-status flex items-center gap-2.5" role="status">
        <span className="connection-marker" aria-hidden="true" />
        {connection}
      </p>
    </aside>
  );
}
