import { useState, type FormEvent } from 'react';
import { Dialog } from '@base-ui/react/dialog';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BookmarkPlus, Save, Trash2 } from 'lucide-react';
import { api } from '../api';
import type { SavedView, TicketFilters } from '../types';
import { ErrorNotice, Loading } from './Feedback';

type ViewCommand = { action: 'create' | 'update'; name: string } | { action: 'delete' };

export function SavedViews({ filters, selectedId, onApply, onClearSelection }: {
  filters: TicketFilters;
  selectedId: string | null;
  onApply: (view: SavedView) => void;
  onClearSelection: () => void;
}) {
  const client = useQueryClient();
  const views = useQuery({ queryKey: ['saved-views'], queryFn: api.views, refetchOnWindowFocus: false });
  const selected = views.data?.find(view => view.id === selectedId);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [notice, setNotice] = useState('');
  const mutation = useMutation({
    mutationFn: async (command: ViewCommand) => {
      if (command.action === 'delete') {
        if (!selected) throw new Error('Choose a view to delete.');
        await api.deleteView(selected.id, selected.version);
        return null;
      }
      const stored: SavedView['filters'] = { status: filters.status, assignee_id: filters.assignee_id, assignment: filters.assignment, priority: filters.priority, intent: filters.intent, q: filters.q, sla: filters.sla, sort: filters.sort, limit: filters.limit };
      if (command.action === 'create') return api.createView({ name: command.name, filters: stored });
      if (!selected) throw new Error('Choose a view to update.');
      return api.patchView(selected.id, { name: command.name, filters: stored, version: selected.version });
    },
    onMutate: () => setNotice(''),
    onSuccess: async (view) => {
      if (view) onApply(view); else { onClearSelection(); setDeleteOpen(false); }
      await client.invalidateQueries({ queryKey: ['saved-views'] });
      setNotice(view ? 'Private view saved with the current filters.' : 'View deleted. Current filters are unchanged.');
    },
  });
  return <section className="saved-views" aria-label="Private saved views">
    <div className="saved-view-bar"><div className="field"><label htmlFor="saved-view">Your saved views</label><select id="saved-view" value={selected?.id ?? ''} disabled={views.isPending || mutation.isPending} onChange={event => { const view = views.data?.find(item => item.id === event.target.value); if (view) onApply(view); else onClearSelection(); }}><option value="">Custom filters</option>{views.data?.map(view => <option key={view.id} value={view.id}>{view.name}</option>)}</select></div><span className="field-help">Private to your account · pagination is not saved</span></div>
    {views.isPending && <Loading>Loading saved views…</Loading>}<ErrorNotice error={views.error} onRetry={() => { void views.refetch(); }} /><ErrorNotice error={mutation.error} onRetry={() => { mutation.reset(); void views.refetch(); }} />{notice && <p className="field-help" role="status">{notice}</p>}
    {views.data && <details className="saved-view-management"><summary>Save or manage this view</summary><ViewForm key={`${selected?.id ?? 'new'}:${selected?.version ?? 0}`} selected={selected} busy={mutation.isPending} onSave={command => mutation.mutate(command)} onDelete={() => setDeleteOpen(true)} /></details>}
    <Dialog.Root open={deleteOpen} onOpenChange={open => { if (!mutation.isPending) setDeleteOpen(open); }}><Dialog.Portal><Dialog.Backdrop className="dialog-backdrop" /><Dialog.Popup className="dialog-popup" finalFocus={() => document.getElementById('saved-view')}><div className="dialog-header"><div><Dialog.Title>Delete “{selected?.name}”?</Dialog.Title><Dialog.Description>This removes only your saved view. Tickets and current filters are not deleted.</Dialog.Description></div></div><ErrorNotice error={mutation.error} /><div className="form-actions"><Dialog.Close className="button button-secondary" disabled={mutation.isPending}>Cancel</Dialog.Close><button className="button" disabled={mutation.isPending || !selected} onClick={() => mutation.mutate({ action: 'delete' })}><Trash2 size={15} aria-hidden="true" />{mutation.isPending ? 'Deleting…' : 'Delete view'}</button></div></Dialog.Popup></Dialog.Portal></Dialog.Root>
  </section>;
}

function ViewForm({ selected, busy, onSave, onDelete }: {
  selected?: SavedView;
  busy: boolean;
  onSave: (command: Exclude<ViewCommand, { action: 'delete' }>) => void;
  onDelete: () => void;
}) {
  const [name, setName] = useState(selected?.name ?? '');
  function submit(event: FormEvent) { event.preventDefault(); if (name.trim() && !busy) onSave({ action: 'create', name: name.trim() }); }
  return <form className="view-save-form" onSubmit={submit}><div className="saved-view-bar"><div className="field"><label htmlFor="view-name">View name</label><input id="view-name" value={name} onChange={event => setName(event.target.value)} required maxLength={60} disabled={busy} /></div><div className="saved-view-actions"><button className="button button-secondary button-small" disabled={busy || !name.trim()}><BookmarkPlus size={15} aria-hidden="true" />Save as new</button>{selected && <><button type="button" className="button button-secondary button-small" disabled={busy || !name.trim()} onClick={() => onSave({ action: 'update', name: name.trim() })}><Save size={15} aria-hidden="true" />Update selected</button><button type="button" className="button button-quiet button-small" disabled={busy} onClick={onDelete}><Trash2 size={15} aria-hidden="true" />Delete</button></>}</div></div></form>;
}
