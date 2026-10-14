import type { TicketMessage } from './types';

export interface DraftState {
  body: string;
  saved: TicketMessage | null;
  saving: boolean;
  error: Error | null;
  dirty: boolean;
}
export type PersistDraft = (body: string, saved: TicketMessage | null) => Promise<TicketMessage>;

export class DraftQueue {
  private state: DraftState;
  private listeners = new Set<() => void>();
  private flight: Promise<TicketMessage | null> | null = null;
  persist: PersistDraft;
  private changed: () => void;
  constructor(saved: TicketMessage | null, persist: PersistDraft, changed: () => void) {
    this.changed = changed;
    this.persist = persist;
    this.state = { body: saved?.body ?? '', saved, saving: false, error: null, dirty: false };
  }
  snapshot = (): DraftState => this.state;
  subscribe = (listener: () => void): (() => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private publish(values: Partial<DraftState>) {
    const next = { ...this.state, ...values };
    next.dirty = next.body.trim() !== (next.saved?.body ?? '');
    this.state = next;
    for (const listener of this.listeners) listener();
    this.changed();
  }
  edit(body: string) { this.publish({ body }); }
  observe(saved: TicketMessage | null) {
    if (this.state.saving || (saved?.id === this.state.saved?.id && saved?.version === this.state.saved?.version)) return;
    if (this.state.dirty) this.publish({ error: new Error('This draft changed elsewhere. Your text is preserved. Reload the saved draft before continuing.') });
    else this.publish({ saved, body: saved?.body ?? '', error: null });
  }
  discard(saved: TicketMessage | null = this.state.saved) {
    if (!this.state.saving) this.publish({ saved, body: saved?.body ?? '', error: null });
  }
  startNew() { if (!this.state.saving) this.publish({ saved: null, error: null }); }
  flush = ({ retry = false, force = false }: { retry?: boolean; force?: boolean } = {}): Promise<TicketMessage | null> => {
    if (this.flight) return this.flight;
    if (this.state.error && !retry) return Promise.reject(this.state.error);
    if (!this.state.dirty && !force) return Promise.resolve(this.state.saved);
    const operation = async () => {
      try {
        while (this.state.dirty || force) {
          force = false;
          const body = this.state.body.trim();
          if (!body) throw new Error('A reply cannot be empty. Restore its text or discard your edits.');
          const saved = await this.persist(body, this.state.saved);
          // Preserve typing (including a trailing space) that occurred while the write was in flight.
          this.publish({ saved });
        }
        return this.state.saved;
      } catch (error) {
        const failure = error instanceof Error ? error : new Error('Draft could not be saved. Your text is preserved.');
        this.publish({ error: failure });
        throw failure;
      } finally {
        this.flight = null;
        this.publish({ saving: false });
      }
    };
    this.flight = Promise.resolve().then(operation);
    this.publish({ saving: true, error: null });
    return this.flight;
  };
}
