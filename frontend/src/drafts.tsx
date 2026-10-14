import { createContext, useContext, useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from 'react';
import { Dialog } from '@base-ui/react/dialog';
import { useBlocker } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from './api';
import { useAuth } from './auth';
import { DraftQueue, type DraftState, type PersistDraft } from './draft-queue';
import { queryKeys } from './query';
import type { Ticket, TicketMessage } from './types';

class DraftRegistry {
  queues = new Map<string, DraftQueue>();
  private listeners = new Set<() => void>();
  private revision = 0;
  private wasDirty = false;
  changed = () => { const dirty = this.dirty; if (dirty === this.wasDirty) return; this.wasDirty = dirty; this.revision++; for (const listener of this.listeners) listener(); };
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  snapshot = () => this.revision;
  get dirty() { return [...this.queues.values()].some(queue => queue.snapshot().dirty || queue.snapshot().saving); }
  async flushAll() { for (const queue of this.queues.values()) await queue.flush({ retry: true }); }
  discardAll() { for (const queue of this.queues.values()) queue.discard(); }
}
const DraftContext = createContext<DraftRegistry | null>(null);

export function DraftProvider({ children }: { children: ReactNode }) {
  const { member } = useAuth();
  const owner = useRef<string | null>(null);
  if (member) owner.current = member.id;
  const registry = useMemo(() => new DraftRegistry(), [owner.current]);
  useSyncExternalStore(registry.subscribe, registry.snapshot);
  const blocker = useBlocker(({ currentLocation, nextLocation }) => registry.dirty && currentLocation.pathname !== nextLocation.pathname);
  const [error, setError] = useState('');
  const [leaving, setLeaving] = useState(false);
  const attempt = useRef(false);
  useEffect(() => {
    if (blocker.state !== 'blocked') { attempt.current = false; setError(''); return; }
    if (attempt.current) return;
    attempt.current = true; setLeaving(true);
    void registry.flushAll().then(() => blocker.proceed(), failure => setError(failure.message)).finally(() => setLeaving(false));
  }, [blocker, registry]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (registry.dirty) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [registry]);
  return <DraftContext.Provider value={registry}>{children}<Dialog.Root open={blocker.state === 'blocked'} onOpenChange={open => { if (!open && !leaving && blocker.state === 'blocked') blocker.reset(); }}><Dialog.Portal><Dialog.Backdrop className="dialog-backdrop" /><Dialog.Popup className="dialog-popup"><Dialog.Title>{leaving ? 'Saving your reply…' : 'Your reply is not saved'}</Dialog.Title><Dialog.Description>{error || 'We are saving your draft before leaving this conversation.'}</Dialog.Description>{!leaving && <div className="form-actions"><button className="button" onClick={() => { if (blocker.state === 'blocked') blocker.reset(); }}>Keep editing</button><button className="button button-secondary" onClick={() => { registry.discardAll(); if (blocker.state === 'blocked') blocker.proceed(); }}>Discard edits and leave</button></div>}</Dialog.Popup></Dialog.Portal></Dialog.Root></DraftContext.Provider>;
}

export function useDraftRegistry(): DraftRegistry {
  const registry = useContext(DraftContext);
  if (!registry) throw new Error('Draft provider is missing.');
  useSyncExternalStore(registry.subscribe, registry.snapshot);
  return registry;
}

export function useReplyDraft(ticket: Ticket, message: TicketMessage | null, blocked: boolean): { queue: DraftQueue; state: DraftState } {
  const registry = useDraftRegistry();
  const client = useQueryClient();
  const context = useRef({ ticket, blocked });
  context.current = { ticket, blocked };
  const persist: PersistDraft = async (body, saved) => {
    if (context.current.blocked) throw new Error('Review and save the latest ticket state before saving this reply.');
    try {
      const value = saved ? await api.patchMessage(ticket.id, saved.id, { body, version: saved.version, ticket_version: context.current.ticket.version }) : await api.createMessage(ticket.id, { kind: 'reply', body, ticket_version: context.current.ticket.version });
      client.setQueryData<TicketMessage[]>(queryKeys.messages(ticket.id), current => current ? [...current.filter(item => item.id !== value.id), value].sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id)) : [value]);
      return value;
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) { void client.invalidateQueries({ queryKey: queryKeys.messages(ticket.id) }); void client.invalidateQueries({ queryKey: queryKeys.ticket(ticket.id) }); }
      throw error;
    }
  };
  const queue = useMemo(() => {
    const existing = registry.queues.get(ticket.id);
    if (existing) return existing;
    const created = new DraftQueue(message, persist, registry.changed);
    registry.queues.set(ticket.id, created);
    return created;
  }, [registry, ticket.id]);
  queue.persist = persist;
  const state = useSyncExternalStore(queue.subscribe, queue.snapshot);
  useEffect(() => { queue.observe(message); }, [message, queue]);
  useEffect(() => () => { if (queue.snapshot().dirty && !queue.snapshot().error) void queue.flush().catch(() => {}); }, [queue]);
  useEffect(() => {
    if (!state.dirty || state.error || state.saving || blocked || !state.body.trim()) return;
    const timer = window.setTimeout(() => { void queue.flush().catch(() => {}); }, 800);
    return () => window.clearTimeout(timer);
  }, [state.body, state.dirty, state.error, state.saving, blocked, queue]);
  return { queue, state };
}
