import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowRight, ChevronLeft, ChevronRight, CircleAlert, Inbox, Plus, RotateCcw, SlidersHorizontal, UserRound } from 'lucide-react';
import { api } from '../api';
import { formatDate, statusLabels, statuses } from '../format';
import { queryKeys } from '../query';
import type { TicketFilters, TicketStatus } from '../types';
import { IntentBadge, PriorityBadge, StatusBadge } from '../components/Badges';
import { EmptyState, ErrorNotice, Loading } from '../components/Feedback';
import { Avatar } from '../components/Avatar';
import { PageHeader } from '../components/PageHeader';
import './tickets.css';

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
    <div className="ticket-queue-page">
      <PageHeader
        title="Tickets"
        description="A clear view of customer requests, and the advice behind your next response."
        actions={<Link className="button" to="/tickets/new"><Plus size={17} aria-hidden="true" />New ticket</Link>}
      />
      <section className="panel ticket-queue" aria-label="Ticket list">
        <div className="queue-status-switcher" role="group" aria-label="Filter tickets by status">
          <button type="button" className="queue-status-option" aria-pressed={!status} onClick={() => changeFilter('status', '')}>All tickets</button>
          {statuses.map((value) => (
            <button key={value} type="button" className="queue-status-option" aria-pressed={status === value} onClick={() => changeFilter('status', value)}>
              <span className={`queue-status-dot status-${value}`} aria-hidden="true" />{statusLabels[value]}
            </button>
          ))}
        </div>
        <div className="queue-toolbar">
          <span className="queue-filter-heading"><SlidersHorizontal size={15} aria-hidden="true" />Filter by</span>
          <div className="field queue-agent-filter">
            <label htmlFor="filter-agent">Assigned agent</label>
            <select id="filter-agent" value={assignee ?? ''} onChange={(event) => changeFilter('assignee_id', event.target.value)} disabled={agents.isPending || agents.isError}>
              <option value="">All agents</option>
              {assignee && !agents.data?.some((agent) => agent.id === assignee) && <option value={assignee}>Selected agent</option>}
              {agents.data?.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}
            </select>
          </div>
          <div className="field queue-limit-filter">
            <label htmlFor="filter-limit">Tickets per page</label>
            <select id="filter-limit" value={limit} onChange={(event) => changeFilter('limit', event.target.value)}>
              {[20, 50, 100].map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </div>
          {(status || assignee) && <button type="button" className="button button-quiet queue-clear" onClick={() => setSearch({ limit: String(limit) })}><RotateCcw size={14} aria-hidden="true" />Clear filters</button>}
        </div>
        <div className="queue-feedback">
          <ErrorNotice error={agents.error} onRetry={() => { void agents.refetch(); }} retrying={agents.isFetching} />
          <ErrorNotice error={tickets.error} onRetry={() => { void tickets.refetch(); }} retrying={tickets.isFetching} />
          {tickets.isPending && <Loading>Loading tickets…</Loading>}
        </div>
        {tickets.data && <>
          <div className="queue-summary">
            <p className="metadata" role="status">{tickets.data.total === 0 ? '0 tickets' : tickets.data.items.length ? `${offset + 1}–${offset + tickets.data.items.length} of ${tickets.data.total} tickets` : `${tickets.data.total} tickets; no results on this page`}</p>
            {tickets.isFetching ? <span className="metadata" role="status">Refreshing…</span> : <span className="queue-sort-note">Recently updated first</span>}
          </div>
          {tickets.data.items.length === 0
            ? <div className="queue-empty">
              <Inbox size={29} strokeWidth={1.4} aria-hidden="true" />
              <EmptyState title={offset > 0 ? 'No tickets on this page' : status || assignee ? 'No matching tickets' : 'Your queue starts here'}>
                <p>{offset > 0 ? 'Go back to the previous page to see tickets.' : status || assignee ? 'Try another status or agent to find the request you need.' : 'Create your first customer request, then review it with Copilot.'}</p>
                {!status && !assignee && offset === 0 && <Link className="button button-secondary" to="/tickets/new"><Plus size={16} aria-hidden="true" />Create the first ticket</Link>}
              </EmptyState>
            </div>
            : <table className="queue-table" role="table">
              <caption className="sr-only">Tickets ordered by most recently updated</caption>
              <thead role="rowgroup"><tr role="row"><th scope="col" role="columnheader">Ticket</th><th scope="col" role="columnheader">Status</th><th scope="col" role="columnheader">Assigned agent</th><th scope="col" role="columnheader">Intent</th><th scope="col" role="columnheader">Priority</th><th scope="col" role="columnheader">Updated</th></tr></thead>
              <tbody role="rowgroup">{tickets.data.items.map((ticket) => <tr key={ticket.id} role="row">
                <td className="queue-ticket-cell" role="cell">
                  <Link className="queue-ticket-link" to={`/tickets/${ticket.id}`}><span>{ticket.title}</span><ArrowRight size={15} aria-hidden="true" /></Link>
                  <div className="queue-ticket-identity"><span>{ticket.customer_email}</span><span className="queue-version">Version {ticket.version}</span></div>
                </td>
                <td role="cell"><span className="queue-cell-label" aria-hidden="true">Status</span><StatusBadge status={ticket.status} /></td>
                <td role="cell">
                  <span className="queue-cell-label" aria-hidden="true">Assigned agent</span>
                  {ticket.assignee ? <span className="queue-assignee"><Avatar name={ticket.assignee.name} size="sm" /><span>{ticket.assignee.name}</span></span>
                    : <span className="queue-unassigned"><UserRound size={15} aria-hidden="true" />{ticket.assignee_id ? 'Assigned agent unavailable' : 'Unassigned'}</span>}
                </td>
                <td role="cell">
                  <span className="queue-cell-label" aria-hidden="true">Intent</span>
                  {ticket.latest_analysis ? <div className="queue-analysis"><IntentBadge intent={ticket.latest_analysis.intent} />{ticket.analysis_stale && <span className="queue-advice-note queue-stale"><RotateCcw size={12} aria-hidden="true" />Stale analysis</span>}</div> : <span className="badge badge-neutral">Unclassified</span>}
                </td>
                <td role="cell">
                  <span className="queue-cell-label" aria-hidden="true">Priority</span>
                  {ticket.latest_analysis ? <div className="queue-analysis"><PriorityBadge priority={ticket.latest_analysis.priority} />{ticket.latest_analysis.escalation_recommended && <span className="queue-advice-note queue-escalation"><CircleAlert size={12} aria-hidden="true" />Escalation advised</span>}</div> : <span className="muted">Not assessed</span>}
                </td>
                <td className="queue-date-cell" role="cell"><span className="queue-cell-label" aria-hidden="true">Updated</span><time dateTime={ticket.updated_at} title={ticket.updated_at}>{formatDate(ticket.updated_at)}</time></td>
              </tr>)}</tbody>
            </table>}
          <nav className="queue-pagination" aria-label="Ticket pagination">
            <button type="button" className="button button-secondary button-small" onClick={() => changePage(Math.max(0, offset - limit))} disabled={offset === 0 || tickets.isFetching}><ChevronLeft size={16} aria-hidden="true" />Previous</button>
            <span className="metadata">Page {Math.floor(offset / limit) + 1}{tickets.data.total > 0 ? ` of ${Math.max(Math.ceil(tickets.data.total / limit), Math.floor(offset / limit) + 1)}` : ''}</span>
            <button type="button" className="button button-secondary button-small" onClick={() => changePage(offset + limit)} disabled={offset + limit >= tickets.data.total || tickets.isFetching}>Next<ChevronRight size={16} aria-hidden="true" /></button>
          </nav>
        </>}
      </section>
      <p className="queue-review-note"><ArrowRight size={14} aria-hidden="true" />Open a ticket to review its advice, sources, and activity.</p>
    </div>
  );
}
