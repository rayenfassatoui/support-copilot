import { useEffect, useState } from 'react';
import { Dialog } from '@base-ui/react/dialog';
import { useQuery } from '@tanstack/react-query';
import { useLocation, useNavigate } from 'react-router-dom';
import { ArrowUpRight, Search, X } from 'lucide-react';
import { api } from '../api';
import { useAuth } from '../auth';
import { ErrorNotice } from './Feedback';

export function ignoresShortcut(event: KeyboardEvent): boolean {
  return event.isComposing || event.defaultPrevented || Boolean(event.target instanceof Element && event.target.closest('input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="textbox"], [role="combobox"], [role="dialog"], [role="alertdialog"]'));
}

export function CommandPalette() {
  const { member } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [active, setActive] = useState(0);
  function changeOpen(value: boolean) { setOpen(value); setQuery(''); setDebounced(''); setActive(0); }
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query.trim()), 180);
    return () => window.clearTimeout(timer);
  }, [query]);
  useEffect(() => {
    const handle = (event: KeyboardEvent) => {
      if (event.isComposing || event.defaultPrevented) return;
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k' && !event.altKey) {
        if (!open && document.querySelector('[role="dialog"], [role="alertdialog"]')) return;
        event.preventDefault(); changeOpen(!open); return;
      }
      if (open || ignoresShortcut(event) || event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return;
      if (event.key === '/') { event.preventDefault(); changeOpen(true); }
      if (event.key === 'n') { event.preventDefault(); navigate('/tickets/new'); }
      if (event.key === 'r' && /^\/tickets\/[^/]+$/.test(location.pathname) && location.pathname !== '/tickets/new') {
        event.preventDefault(); window.dispatchEvent(new Event('copilot-compose-reply'));
      }
    };
    window.addEventListener('keydown', handle);
    return () => window.removeEventListener('keydown', handle);
  }, [open, navigate, location.pathname]);
  const tickets = useQuery({ queryKey: ['command-tickets', debounced], queryFn: ({ signal }) => api.tickets({ q: debounced, limit: 8, offset: 0 }, signal), enabled: open && debounced.length >= 2 });
  const actions = [
    { label: 'Open ticket inbox', detail: 'Workspace', to: '/tickets' },
    { label: 'Create a new ticket', detail: 'N', to: '/tickets/new' },
    { label: 'Open knowledge base', detail: 'Documents and imports', to: '/knowledge' },
    { label: 'Open analytics', detail: 'Response, resolution and satisfaction', to: '/analytics' },
    ...(member?.role === 'admin' ? [
      { label: 'Open support mailbox', detail: 'Inbound email', to: '/mailbox' },
      { label: 'Open automation', detail: 'Assignments and business hours', to: '/automation' },
      { label: 'Open settings', detail: 'Team and service targets', to: '/settings' },
    ] : []),
  ];
  const options = [
    ...actions.filter(item => `${item.label} ${item.detail}`.toLowerCase().includes(query.trim().toLowerCase())),
    ...(debounced === query.trim() && debounced.length >= 2 ? tickets.data?.items.map(ticket => ({ label: ticket.title, detail: ticket.customer_email, to: `/tickets/${ticket.id}` })) ?? [] : []),
  ];
  function select(index: number) {
    const item = options[index];
    if (!item) return;
    changeOpen(false); navigate(item.to);
  }
  return <Dialog.Root open={open} onOpenChange={changeOpen}>
    <Dialog.Trigger className="command-trigger" aria-label="Search tickets and actions"><Search size={16} aria-hidden="true" /><span>Search</span><kbd>⌘ / Ctrl K</kbd></Dialog.Trigger>
    <Dialog.Portal><Dialog.Backdrop className="dialog-backdrop" /><Dialog.Popup className="dialog-popup command-palette">
      <Dialog.Title className="sr-only">Search tickets and actions</Dialog.Title><Dialog.Description className="sr-only">Type to search, use arrow keys to choose a result, and Enter to open it.</Dialog.Description>
      <div className="command-input"><Search size={19} aria-hidden="true" /><input aria-label="Search tickets and actions" role="combobox" aria-autocomplete="list" aria-expanded="true" aria-controls="command-results" aria-activedescendant={options[active] ? `command-option-${active}` : undefined} value={query} maxLength={200} placeholder="Search tickets or choose an action…" onChange={event => { setQuery(event.target.value); setActive(0); }} onKeyDown={event => {
        if (event.key === 'Enter') { event.preventDefault(); select(active); }
        if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && options.length) { event.preventDefault(); setActive(value => (value + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length); }
      }} /><Dialog.Close className="icon-button" aria-label="Close search"><X size={18} aria-hidden="true" /></Dialog.Close></div>
      <ErrorNotice error={debounced.length >= 2 ? tickets.error : null} />
      <div id="command-results" role="listbox" aria-label="Tickets and actions" className="command-results">{options.map((item, index) => <button type="button" role="option" aria-selected={active === index} id={`command-option-${index}`} key={item.to} tabIndex={-1} onMouseMove={() => setActive(index)} onClick={() => select(index)}><span><strong>{item.label}</strong><small>{item.detail}</small></span><ArrowUpRight size={16} aria-hidden="true" /></button>)}</div>
      <p className="command-status" role="status">{tickets.isFetching && debounced.length >= 2 ? 'Searching tickets…' : !options.length ? 'No matching tickets or actions.' : query.trim().length < 2 ? 'Type at least 2 characters to search tickets.' : `${options.length} results`}</p>
      <div className="command-shortcuts"><span><kbd>↑ ↓</kbd> Choose</span><span><kbd>Enter</kbd> Open</span><span><kbd>J / K</kbd> Next / previous ticket</span><span><kbd>R</kbd> Reply</span><span><kbd>Esc</kbd> Close</span></div>
    </Dialog.Popup></Dialog.Portal>
  </Dialog.Root>;
}
