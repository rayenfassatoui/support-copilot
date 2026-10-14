import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../api';
import { formatDate, statusLabels, statuses } from '../format';
import { queryKeys } from '../query';
import type { TicketFilters, TicketStatus } from '../types';
import { IntentBadge, PriorityBadge, StatusBadge } from '../components/Badges';
import { EmptyState, ErrorNotice, Loading } from '../components/Feedback';

export function TicketsPage() {
  const [search, setSearch] = useSearchParams();
  const rawStatus = search.get('status');
  const status = rawStatus && statuses.includes(rawStatus as TicketStatus) ? rawStatus as TicketStatus : undefined;
  const assignee = search.get('assignee_id') || undefined;
  const rawOffset = Number(search.get('offset') ?? 0);
  const offset = Number.isSafeInteger(rawOffset) && rawOffset >= 0 ? rawOffset : 0;
  const rawLimit = Number(search.get('limit') ?? 20);
  const limit = [20, 50, 100].includes(rawLimit) ? rawLimit : 20;
  const filters: TicketFilters = { status, assignee_id: assignee, limit, offset };
  const tickets = useQuery({ queryKey: queryKeys.tickets(filters), queryFn: ({ signal }) => api.tickets(filters, signal) });
  const agents = useQuery({ queryKey: queryKeys.agents, queryFn: ({ signal }) => api.agents(signal) });

  function changeFilter(key: string, value: string) {
    setSearch((current) => {
      const next = new URLSearchParams(current);
      if (value) next.set(key, value); else next.delete(key);
      next.delete('offset');
      return next;
    });
  }

  function changePage(nextOffset: number) {
    setSearch((current) => {
      const next = new URLSearchParams(current);
      if (nextOffset) next.set('offset', String(nextOffset)); else next.delete('offset');
      return next;
    });
  }

  return (
    <>
      <div className="page-heading"><div><p className="eyebrow">Agent workspace</p><h1>Tickets</h1><p>Manage customer requests and review source-grounded AI advice.</p></div><Link className="button" to="/tickets/new">New ticket</Link></div>
      <section className="panel" aria-label="Ticket list">
        <div className="filters">
          <div className="field"><label htmlFor="filter-status">Status</label><select id="filter-status" value={status ?? ''} onChange={(event) => changeFilter('status', event.target.value)}><option value="">All statuses</option>{statuses.map((value) => <option key={value} value={value}>{statusLabels[value]}</option>)}</select></div>
          <div className="field"><label htmlFor="filter-agent">Assigned agent</label><select id="filter-agent" value={assignee ?? ''} onChange={(event) => changeFilter('assignee_id', event.target.value)} disabled={agents.isPending || agents.isError}><option value="">All agents</option>{assignee && !agents.data?.some((agent) => agent.id === assignee) && <option value={assignee}>Selected agent</option>}{agents.data?.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}</select></div>
          <div className="field"><label htmlFor="filter-limit">Tickets per page</label><select id="filter-limit" value={limit} onChange={(event) => changeFilter('limit', event.target.value)}>{[20, 50, 100].map((value) => <option key={value} value={value}>{value}</option>)}</select></div>
          {(status || assignee) && <button type="button" className="button button-secondary" onClick={() => setSearch({ limit: String(limit) })}>Clear filters</button>}
        </div>
        <ErrorNotice error={agents.error} onRetry={() => { void agents.refetch(); }} retrying={agents.isFetching} />
        <ErrorNotice error={tickets.error} onRetry={() => { void tickets.refetch(); }} retrying={tickets.isFetching} />
        {tickets.isPending && <Loading>Loading tickets…</Loading>}
        {tickets.data && <>
          <div className="list-summary"><p className="metadata" role="status">{tickets.data.total === 0 ? '0 tickets' : tickets.data.items.length ? `${offset + 1}–${offset + tickets.data.items.length} of ${tickets.data.total} tickets` : `${tickets.data.total} tickets; no results on this page`}</p>{tickets.isFetching && <span className="metadata" role="status">Refreshing…</span>}</div>
          {tickets.data.items.length === 0
            ? <EmptyState title={offset > 0 ? 'No tickets on this page' : status || assignee ? 'No matching tickets' : 'No tickets yet'}><p>{offset > 0 ? 'Go back to the previous page to see tickets.' : status || assignee ? 'Try a different status or agent filter.' : 'Create a ticket to start the support workflow.'}</p>{!status && !assignee && offset === 0 && <Link className="button button-secondary" to="/tickets/new">Create the first ticket</Link>}</EmptyState>
            : <div className="table-scroll" tabIndex={0} aria-label="Scrollable ticket table"><table className="tickets-table"><caption className="sr-only">Tickets ordered by most recently updated</caption><thead><tr><th scope="col">Title</th><th scope="col">Status</th><th scope="col">Assigned agent</th><th scope="col">Intent</th><th scope="col">Priority</th><th scope="col">Updated</th></tr></thead><tbody>{tickets.data.items.map((ticket) => <tr key={ticket.id}>
              <td className="ticket-title-cell"><Link className="ticket-title-link" to={`/tickets/${ticket.id}`}>{ticket.title}</Link><span className="metadata">Version {ticket.version}</span></td>
              <td><StatusBadge status={ticket.status} /></td>
              <td>{ticket.assignee?.name ?? <span className="muted">Unassigned</span>}</td>
              <td>{ticket.latest_analysis ? <><IntentBadge intent={ticket.latest_analysis.intent} />{ticket.analysis_stale && <span className="stale-label">Stale analysis</span>}</> : <span className="badge badge-neutral">Unclassified</span>}</td>
              <td>{ticket.latest_analysis ? <><PriorityBadge priority={ticket.latest_analysis.priority} />{ticket.latest_analysis.escalation_recommended && <span className="escalation-label">Escalation advised</span>}</> : <span className="muted">Not assessed</span>}</td>
              <td className="date-cell"><time dateTime={ticket.updated_at} title={ticket.updated_at}>{formatDate(ticket.updated_at)}</time></td>
            </tr>)}</tbody></table></div>}
          <nav className="pagination" aria-label="Ticket pagination"><button type="button" className="button button-secondary" onClick={() => changePage(Math.max(0, offset - limit))} disabled={offset === 0 || tickets.isFetching}>Previous</button><span className="metadata">Page {Math.floor(offset / limit) + 1}{tickets.data.total > 0 ? ` of ${Math.max(Math.ceil(tickets.data.total / limit), Math.floor(offset / limit) + 1)}` : ''}</span><button type="button" className="button button-secondary" onClick={() => changePage(offset + limit)} disabled={offset + limit >= tickets.data.total || tickets.isFetching}>Next</button></nav>
        </>}
      </section>
    </>
  );
}
