import React from 'react';
import { timestamp } from '../portfolio.js';

export default function Notifications({ records, timezone }) {
  const unique = [...new Map(records.map((record) => [record.notification_id, record])).values()];
  return (
    <section className="ledger-card standalone-panel" aria-labelledby="notifications-heading">
      <h1 className="panel-title" id="notifications-heading">Notifications</h1>
      <p className="caption notifications-intro">Delivered reminders appear here, even when this tab was closed.</p>
      {unique.length ? <ul className="notifications-list">{unique.map((record) => (
        <li key={record.notification_id}>
          <p>{record.message}</p>
          <time dateTime={record.created_at} className="caption">{timestamp(record.created_at, timezone)}{record.created_at && ` (${timezone})`}</time>
        </li>
      ))}</ul> : <p className="caption empty-list">No reminders have been delivered yet.</p>}
    </section>
  );
}
