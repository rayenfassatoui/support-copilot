import { useState } from 'react';
import { Dialog } from '@base-ui/react/dialog';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { CheckCheck, Save, Trash2 } from 'lucide-react';
import { api, ApiError } from '../api';
import { useReplyDraft } from '../drafts';
import { queryKeys } from '../query';
import type { Ticket, TicketMessage } from '../types';
import { ErrorNotice } from './Feedback';

export function ReplyDraft({ ticket, message, blocked, onApprove }: {
  ticket: Ticket;
  message: TicketMessage | null;
  blocked: boolean;
  onApprove: (message: TicketMessage) => Promise<TicketMessage | null>;
}) {
  const client = useQueryClient();
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const { queue, state } = useReplyDraft(ticket, message, blocked || confirmDiscard);
  const stale = Boolean(state.saved && state.saved.ticket_version !== ticket.version);
  const discard = useMutation({
    mutationFn: (saved: TicketMessage) => api.deleteMessage(ticket.id, saved.id, { version: saved.version, ticket_version: ticket.version }),
    onSuccess: async (_, saved) => {
      queue.discard(null);
      setConfirmDiscard(false);
      client.setQueryData<TicketMessage[]>(queryKeys.messages(ticket.id), current => current?.filter(item => item.id !== saved.id));
      await client.invalidateQueries({ queryKey: ['feedback', ticket.id] });
    },
    onError: error => { if (error instanceof ApiError && error.status === 409) { void client.invalidateQueries({ queryKey: queryKeys.messages(ticket.id) }); void client.invalidateQueries({ queryKey: queryKeys.ticket(ticket.id) }); } },
  });
  return <>
    <form className="draft-editor" onSubmit={event => { event.preventDefault(); void queue.flush({ retry: true, force: stale }).catch(() => {}); }}>
      <div className="field"><label htmlFor={`reply-draft-${ticket.id}`}>Reply draft · autosaved</label><textarea id={`reply-draft-${ticket.id}`} value={state.body} onChange={event => queue.edit(event.target.value)} rows={6} maxLength={10000} disabled={blocked || confirmDiscard} /><p className="field-help" role="status">{state.saving ? 'Saving…' : state.error ? 'Not saved. Your text is preserved.' : state.dirty ? 'Unsaved changes' : state.saved ? 'All changes saved' : 'Start typing to create a draft.'} Saving never approves or sends.</p></div>
      <ErrorNotice error={state.error} />
      {stale && <p className="notice notice-warning">The conversation changed. Review it, then save your reviewed draft before approval.</p>}
      {!message && state.saved && state.error && <button type="button" className="button button-secondary" disabled={blocked || state.saving} onClick={() => queue.startNew()}>Keep my text as a new draft</button>}
      <div className="message-actions">
        <button className="button button-secondary" disabled={blocked || state.saving || !state.body.trim() || (!state.dirty && !state.error && !stale)}><Save size={15} />Save now</button>
        <button className="button" type="button" disabled={blocked || state.saving || state.dirty || Boolean(state.error) || stale || !state.saved} onClick={() => { if (state.saved) void onApprove(state.saved); }}><CheckCheck size={15} />Approve reply</button>
        {(state.dirty || state.error) && <button className="button button-quiet" type="button" disabled={state.saving} onClick={() => queue.discard(message)}>Reload saved draft (discard edits)</button>}
        {state.saved && <button className="button button-quiet" type="button" disabled={blocked || state.saving} onClick={() => { discard.reset(); setConfirmDiscard(true); }}><Trash2 size={14} />Discard draft…</button>}
      </div>
    </form>
    <Dialog.Root open={confirmDiscard} onOpenChange={open => { if (!discard.isPending) setConfirmDiscard(open); }}><Dialog.Portal><Dialog.Backdrop className="dialog-backdrop" /><Dialog.Popup className="dialog-popup">
      <Dialog.Title>Discard this unsent draft?</Dialog.Title><Dialog.Description>The saved draft and your current edits will be removed. If this draft contains a customer survey, its link will be revoked. Approved and sent replies are never deleted.</Dialog.Description>
      <ErrorNotice error={discard.error} /><div className="form-actions"><Dialog.Close className="button button-secondary" disabled={discard.isPending}>Keep draft</Dialog.Close><button type="button" className="button" disabled={blocked || state.saving || discard.isPending || !state.saved} onClick={() => { if (state.saved) discard.mutate(state.saved); }}>{discard.isPending ? 'Discarding…' : 'Discard draft'}</button></div>
    </Dialog.Popup></Dialog.Portal></Dialog.Root>
  </>;
}
