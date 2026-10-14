import { useQuery } from '@tanstack/react-query';
import { api } from '../api';
import { formatDate, statusLabels, statuses } from '../format';
import { queryKeys } from '../query';
import type { Agent, TicketStatus } from '../types';
import { ErrorNotice, Loading } from './Feedback';

const fieldLabels: Record<string, string> = {
  title: 'Title', description: 'Description', customer_email: 'Customer email', status: 'Status', assignee_id: 'Assigned agent',
};

function eventValue(field: string, value: unknown, agents: Agent[]): string {
  if (value === null || value === undefined) return field === 'assignee_id' ? 'Unassigned' : 'Not set';
  if (field === 'assignee_id' && typeof value === 'string') return agents.find((agent) => agent.id === value)?.name ?? value;
  if (field === 'status' && typeof value === 'string' && statuses.includes(value as TicketStatus)) return statusLabels[value as TicketStatus];
  return typeof value === 'string' ? value : JSON.stringify(value) ?? String(value);
}

export function TicketTimeline({ ticketId, agents }: { ticketId: string; agents: Agent[] }) {
  const events = useQuery({
    queryKey: queryKeys.events(ticketId),
    queryFn: ({ signal }) => api.events(ticketId, signal),
    refetchOnWindowFocus: false,
  });
  return (
    <section className="panel" aria-labelledby="history-heading">
      <div className="panel-heading"><h2 id="history-heading">Ticket history</h2><button type="button" className="button button-secondary button-small" onClick={() => { void events.refetch(); }} disabled={events.isFetching}>Refresh history</button></div>
      <p className="field-help">Saved ticket changes, oldest first. AI analysis does not change ticket status or assignment.</p>
      <ErrorNotice error={events.error} onRetry={() => { void events.refetch(); }} retrying={events.isFetching} />
      {events.isPending && <Loading>Loading ticket history…</Loading>}
      {events.data?.length === 0 && <p className="muted">No ticket history is available.</p>}
      {events.data && events.data.length > 0 && <ol className="timeline">
        {events.data.map((event) => <li key={event.id}>
          <div className="timeline-heading"><strong>{event.ticket_version === 1 ? 'Ticket created' : 'Ticket updated'}</strong><span className="badge badge-neutral">Version {event.ticket_version}</span></div>
          <time className="metadata" dateTime={event.created_at}>{formatDate(event.created_at)}</time>
          <details className="event-details"><summary>{event.ticket_version === 1 ? 'View initial values' : `View changes: ${Object.keys(event.changes).map((field) => fieldLabels[field] ?? field).join(', ')}`}</summary>
            <dl className="event-changes">{Object.entries(event.changes).map(([field, change]) => <div className="event-change" key={field}>
              <dt>{fieldLabels[field] ?? field}</dt>
              <dd><span className="change-label">Before</span><span className="change-value" tabIndex={0} aria-label={`${fieldLabels[field] ?? field} before this change`}>{eventValue(field, change.old, agents)}</span></dd>
              <dd><span className="change-label">After</span><span className="change-value" tabIndex={0} aria-label={`${fieldLabels[field] ?? field} after this change`}>{eventValue(field, change.new, agents)}</span></dd>
            </div>)}</dl>
          </details>
        </li>)}
      </ol>}
    </section>
  );
}
