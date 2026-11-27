import React from 'react';
import { timestamp } from '../portfolio.js';

export default function Evidence({ ids, sources, timezone, label }) {
  const records = [...new Set(ids || [])].map((id) => sources.get(id)).filter(Boolean);
  if (!records.length) return <span className="caption">Evidence unavailable</span>;
  return (
    <span className="evidence-list">
      {records.map((source) => (
        <a className="evidence-chip" key={source.source_id} title={source.subject}
          href={`/api/evidence/${encodeURIComponent(source.source_id)}`} target="_blank" rel="noopener noreferrer">
          <span aria-hidden="true">✉</span>{' '}{label ? `${label} · ` : ''}{source.sender_domain}
          {source.received_at && ` · ${timestamp(source.received_at, timezone, true)}`}
        </a>
      ))}
    </span>
  );
}
