import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { ArrowRight, ChevronLeft, ChevronRight, CircleAlert, Inbox, Plus, RotateCcw, Search, SlidersHorizontal, UserRound } from 'lucide-react';
import { api } from '../api';
import { formatDate, statusLabels, statuses } from '../format';
import { queryKeys } from '../query';
import type { Intent, Priority, SavedView, TicketFilters, TicketStatus } from '../types';
import { IntentBadge, PriorityBadge, StatusBadge } from '../components/Badges';
import { EmptyState, ErrorNotice, Loading } from '../components/Feedback';
import { Avatar } from '../components/Avatar';
import { PageHeader } from '../components/PageHeader';
import { SavedViews } from '../components/SavedViews';
import { TicketDetailPage } from './TicketDetailPage';
import { ignoresShortcut } from '../components/CommandPalette';
import './tickets.css';
import './workspace.css';

const priorities: Priority[] = ['low', 'medium', 'high', 'urgent'];
const intents: Intent[] = ['billing', 'technical', 'account', 'cancellation', 'security', 'other'];

export function TicketsPage() {
  const [search, setSearch] = useSearchParams();
  const { id } = useParams();
  const navigate = useNavigate();
  const pane = useRef<HTMLElement>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const suffix = search.size ? `?${search}` : '';
  const rawStatus = search.get('status');
  const status = rawStatus && statuses.includes(rawStatus as TicketStatus) ? rawStatus as TicketStatus : undefined;
  const assignee = search.get('assignee_id') || undefined;
  const rawOffset = Number(search.get('offset') ?? 0);
  const offset = Number.isSafeInteger(rawOffset) && rawOffset >= 0 ? rawOffset : 0;
  const rawLimit = Number(search.get('limit') ?? 20);
  const limit = [20, 50, 100].includes(rawLimit) ? rawLimit : 20;
  const rawPriority = search.get('priority') as Priority | null;
  const rawIntent = search.get('intent') as Intent | null;
  const rawAssignment = search.get('assignment');
  const rawSort = search.get('sort');
  const filters: TicketFilters = {
    status, assignee_id: assignee, limit, offset,
    assignment: !assignee && (rawAssignment === 'mine' || rawAssignment === 'unassigned') ? rawAssignment : 'all',
    priority: rawPriority && priorities.includes(rawPriority) ? rawPriority : undefined,
    intent: rawIntent && intents.includes(rawIntent) ? rawIntent : undefined,
    q: search.get('q') ?? '',
    sla: search.get('sla') === 'breached' ? 'breached' : 'all',
    sort: rawSort === 'priority' || rawSort === 'due' ? rawSort : 'updated',
  };
  const filtered = Boolean(status || assignee || filters.assignment !== 'all' || filters.priority || filters.intent || filters.q || filters.sla !== 'all');
  const sortLabel = filters.sort === 'due' ? 'Earliest outstanding deadline first' : filters.sort === 'priority' ? 'Urgent priority first' : 'Recently updated first';
  const tickets = useQuery({ queryKey: queryKeys.tickets(filters), queryFn: ({ signal }) => api.tickets(filters, signal) });
  const agents = useQuery({ queryKey: queryKeys.agents, queryFn: ({ signal }) => api.agents(signal) });
  useEffect(() => { pane.current?.scrollTo({ top: 0 }); }, [id]);
  useEffect(() => {
    const handle = (event: KeyboardEvent) => {
      if (ignoresShortcut(event) || event.metaKey || event.ctrlKey || event.altKey || event.shiftKey || (event.key !== 'j' && event.key !== 'k')) return;
      const items = tickets.data?.items;
      if (!items?.length) return;
      const current = items.findIndex(ticket => ticket.id === id);
      const next = current < 0 ? event.key === 'j' ? 0 : items.length - 1 : Math.max(0, Math.min(items.length - 1, current + (event.key === 'j' ? 1 : -1)));
      event.preventDefault();
      navigate(`/tickets/${items[next].id}${suffix}`);
    };
    window.addEventListener('keydown', handle);
    return () => window.removeEventListener('keydown', handle);
  }, [tickets.data, id, navigate, suffix]);

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

  function changeAssignment(value: string) {
    setSearch(current => {
      const next = new URLSearchParams(current);
      next.delete('offset'); next.delete('assignee_id'); next.delete('assignment');
      if (value === 'mine' || value === 'unassigned') next.set('assignment', value);
      else if (value) next.set('assignee_id', value);
      return next;
    });
  }

  function applyView(view: SavedView) {
    const next = new URLSearchParams({ view: view.id });
    for (const [key, value] of Object.entries(view.filters)) if (value !== undefined && value !== null && value !== '') next.set(key, String(value));
    setSearch(next);
  }

  return (
    <div className={`inbox-workspace${id ? ' is-split' : ''}`}>
    <div className="ticket-queue-page">
      <PageHeader
        title="Tickets"
        description="A clear view of customer requests, and the advice behind your next response."
        actions={<Link className="button" to="/tickets/new"><Plus size={17} aria-hidden="true" />New ticket</Link>}
      />
      <section className="panel ticket-queue" aria-label="Ticket list">
        <details className="queue-filter-disclosure" open={!id || filtersOpen} onToggle={event => { if (id) setFiltersOpen(event.currentTarget.open); }}>
          <summary>Filters and saved views{filtered ? ' · active' : ''}</summary>
        <div className="queue-status-switcher" role="group" aria-label="Filter tickets by status">
          <button type="button" className="queue-status-option" aria-pressed={!status} onClick={() => changeFilter('status', '')}>All tickets</button>
          {statuses.map((value) => (
            <button key={value} type="button" className="queue-status-option" aria-pressed={status === value} onClick={() => changeFilter('status', value)}>
              <span className={`queue-status-dot status-${value}`} aria-hidden="true" />{statusLabels[value]}
            </button>
          ))}
        </div>
        <div className="queue-advanced">
          <SavedViews filters={filters} selectedId={search.get('view')} onApply={applyView} onClearSelection={() => setSearch(current => { const next = new URLSearchParams(current); next.delete('view'); return next; })} />
          <TicketSearch key={filters.q} query={filters.q ?? ''} onSearch={value => changeFilter('q', value)} />
          <div className="queue-extra-filters">
            <div className="field"><label htmlFor="filter-priority">Priority</label><select id="filter-priority" value={filters.priority ?? ''} onChange={event => changeFilter('priority', event.target.value)}><option value="">All priorities</option>{priorities.map(value => <option key={value} value={value}>{value[0].toUpperCase() + value.slice(1)}</option>)}</select></div>
            <div className="field"><label htmlFor="filter-intent">Latest AI intent</label><select id="filter-intent" value={filters.intent ?? ''} onChange={event => changeFilter('intent', event.target.value)}><option value="">All intents</option>{intents.map(value => <option key={value} value={value}>{value[0].toUpperCase() + value.slice(1)}</option>)}</select></div>
            <div className="field"><label htmlFor="filter-sla">Service level</label><select id="filter-sla" value={filters.sla} onChange={event => changeFilter('sla', event.target.value)}><option value="all">All targets</option><option value="breached">Outstanding overdue</option></select></div>
            <div className="field"><label htmlFor="filter-sort">Order by</label><select id="filter-sort" value={filters.sort} onChange={event => changeFilter('sort', event.target.value)}><option value="updated">Recently updated</option><option value="priority">Highest priority</option><option value="due">Next deadline</option></select></div>
          </div>
        </div>
        <div className="queue-toolbar">
          <span className="queue-filter-heading"><SlidersHorizontal size={15} aria-hidden="true" />Filter by</span>
          <div className="field queue-agent-filter">
            <label htmlFor="filter-agent">Assigned agent</label>
            <select id="filter-agent" value={assignee ?? (filters.assignment === 'all' ? '' : filters.assignment)} onChange={(event) => changeAssignment(event.target.value)} disabled={agents.isPending || agents.isError}>
              <option value="">All agents</option><option value="mine">Assigned to me</option><option value="unassigned">Unassigned</option>
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
          {filtered && <button type="button" className="button button-quiet queue-clear" onClick={() => setSearch({ limit: String(limit) })}><RotateCcw size={14} aria-hidden="true" />Clear filters</button>}
        </div>
        </details>
        <div className="queue-feedback">
          <ErrorNotice error={agents.error} onRetry={() => { void agents.refetch(); }} retrying={agents.isFetching} />
          <ErrorNotice error={tickets.error} onRetry={() => { void tickets.refetch(); }} retrying={tickets.isFetching} />
          {tickets.isPending && <Loading>Loading tickets…</Loading>}
        </div>
        {tickets.data && <>
          <div className="queue-summary">
            <p className="metadata" role="status">{tickets.data.total === 0 ? '0 tickets' : tickets.data.items.length ? `${offset + 1}–${offset + tickets.data.items.length} of ${tickets.data.total} tickets` : `${tickets.data.total} tickets; no results on this page`}</p>
            {tickets.isFetching ? <span className="metadata" role="status">Refreshing…</span> : <span className="queue-sort-note">{sortLabel}</span>}
          </div>
          {tickets.data.items.length === 0
            ? <div className="queue-empty">
              <Inbox size={29} strokeWidth={1.4} aria-hidden="true" />
              <EmptyState title={offset > 0 ? 'No tickets on this page' : filtered ? 'No matching tickets' : 'Your queue starts here'}>
                <p>{offset > 0 ? 'Go back to the previous page to see tickets.' : filtered ? 'Adjust the search or filters to find the request you need.' : 'Create your first customer request, then review it with Copilot.'}</p>
                {!filtered && offset === 0 && <Link className="button button-secondary" to="/tickets/new"><Plus size={16} aria-hidden="true" />Create the first ticket</Link>}
              </EmptyState>
            </div>
            : <table className="queue-table" role="table">
              <caption className="sr-only">Tickets · {sortLabel}</caption>
              <thead role="rowgroup"><tr role="row"><th scope="col" role="columnheader">Ticket</th><th scope="col" role="columnheader">Status</th><th scope="col" role="columnheader">Assigned agent</th><th scope="col" role="columnheader">Intent</th><th scope="col" role="columnheader">Priority</th><th scope="col" role="columnheader">Updated</th></tr></thead>
              <tbody role="rowgroup">{tickets.data.items.map((ticket) => <tr key={ticket.id} role="row" className={ticket.id === id ? 'queue-selected' : undefined}>
                <td className="queue-ticket-cell" role="cell">
                  <Link className="queue-ticket-link" to={`/tickets/${ticket.id}${suffix}`} aria-current={ticket.id === id ? 'page' : undefined}><span>{ticket.title}</span><ArrowRight size={15} aria-hidden="true" /></Link>
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
                  <div className="queue-analysis"><PriorityBadge priority={ticket.priority} />{ticket.latest_analysis?.escalation_recommended && <span className="queue-advice-note queue-escalation"><CircleAlert size={12} aria-hidden="true" />Escalation advised</span>}</div>
                  <span className={`queue-sla-caption${Object.values(ticket.sla).some(target => !target.completed_at && target.status === 'breached') ? ' sla-overdue' : ''}`}>{Object.values(ticket.sla).some(target => !target.completed_at && target.status === 'breached') ? 'Overdue target' : ticket.sla.first_response.completed_at && ticket.sla.resolution.completed_at ? 'Targets completed' : 'Targets on track'}</span>
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
      {id && <section ref={pane} className="conversation-pane" aria-label="Selected ticket"><TicketDetailPage /></section>}
    </div>
  );
}

function TicketSearch({ query, onSearch }: { query: string; onSearch: (query: string) => void }) {
  const [value, setValue] = useState(query);
  function submit(event: FormEvent) { event.preventDefault(); onSearch(value.trim()); }
  return <form className="queue-search" role="search" onSubmit={submit}><div className="field"><label htmlFor="ticket-search">Search title, request or customer email</label><input id="ticket-search" type="search" value={value} onChange={event => setValue(event.target.value)} maxLength={200} /></div><button className="button button-secondary"><Search size={16} aria-hidden="true" />Search</button></form>;
}
