import { formatDate } from '../format';
import type { Ticket } from '../types';

export function SlaSummary({ ticket }: { ticket: Ticket }) {
  return <section className="sla-summary" aria-label="Service level deadlines">
    {([{ key: 'first_response', label: 'First response' }, { key: 'resolution', label: 'Resolution' }] as const).map(({ key, label }) => {
      const target = ticket.sla[key];
      return <div className={`sla-target sla-${target.status}`} key={key}><h3>{label}</h3><span className="sla-status">{target.status === 'met' ? 'Met' : target.status === 'breached' ? 'Breached' : 'On track'}</span><p>Due <time dateTime={target.due_at}>{formatDate(target.due_at)}</time></p>{target.completed_at && <p>Completed <time dateTime={target.completed_at}>{formatDate(target.completed_at)}</time></p>}</div>;
    })}
  </section>;
}
