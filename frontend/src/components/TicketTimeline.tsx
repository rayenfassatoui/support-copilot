import { useQuery } from '@tanstack/react-query';
import { ChevronDown, CirclePlus, History, PencilLine, RefreshCw } from 'lucide-react';
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
    <section className="panel ticket-activity" aria-labelledby="history-heading">
      <div className="ticket-section-header">
        <div>
          <h2 id="history-heading"><History size={18} aria-hidden="true" />Ticket history</h2>
          <p className="field-help">Saved changes, oldest first. AI analysis does not change status or assignment.</p>
        </div>
        <button type="button" className="button button-secondary button-small ticket-history-refresh" onClick={() => { void events.refetch(); }} disabled={events.isFetching}><RefreshCw size={15} aria-hidden="true" />{events.isFetching && !events.isPending ? 'Refreshing…' : 'Refresh history'}</button>
      </div>
      <ErrorNotice error={events.error} onRetry={() => { void events.refetch(); }} retrying={events.isFetching} />
      {events.isPending && <Loading>Loading ticket history…</Loading>}
      {events.isFetching && !events.isPending && <p className="ticket-history-loading metadata" role="status">Refreshing ticket history…</p>}
      {events.data?.length === 0 && (
        <div className="ticket-history-empty"><History size={23} aria-hidden="true" /><p>No ticket history is available.</p></div>
      )}
      {events.data && events.data.length > 0 && (
        <ol className="ticket-activity-list">
          {events.data.map((event) => (
            <li className="ticket-activity-event" key={event.id}>
              <span className={`ticket-event-marker${event.ticket_version === 1 ? ' ticket-event-created' : ''}`} aria-hidden="true">
                {event.ticket_version === 1 ? <CirclePlus size={14} aria-hidden="true" /> : <PencilLine size={13} aria-hidden="true" />}
              </span>
              <div className="ticket-event-body">
                <div className="ticket-event-heading">
                  <h3>{event.ticket_version === 1 ? 'Ticket created' : 'Ticket updated'}</h3>
                  <span className="ticket-event-version">Version {event.ticket_version}</span>
                </div>
                <time className="metadata" dateTime={event.created_at}>{formatDate(event.created_at)}</time>
                <details className="ticket-event-details">
                  <summary><span>{event.ticket_version === 1 ? 'View initial values' : `View changes: ${Object.keys(event.changes).map((field) => fieldLabels[field] ?? field).join(', ')}`}</span><ChevronDown size={15} aria-hidden="true" /></summary>
                  <dl className="ticket-event-changes">
                    {Object.entries(event.changes).map(([field, change]) => (
                      <div className="ticket-event-change" key={field}>
                        <dt>{fieldLabels[field] ?? field}</dt>
                        <dd><span className="ticket-change-label">Before</span><span className="ticket-change-value" tabIndex={0} aria-label={`${fieldLabels[field] ?? field} before this change`}>{eventValue(field, change.old, agents)}</span></dd>
                        <dd><span className="ticket-change-label">After</span><span className="ticket-change-value" tabIndex={0} aria-label={`${fieldLabels[field] ?? field} after this change`}>{eventValue(field, change.new, agents)}</span></dd>
                      </div>
                    ))}
                  </dl>
                </details>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
