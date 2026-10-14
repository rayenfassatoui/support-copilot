import { useState, type FormEvent } from 'react';
import { Dialog } from '@base-ui/react/dialog';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCheck, LockKeyhole, MessageSquareText, RefreshCw, Save, Send, X } from 'lucide-react';
import { api } from '../api';
import { formatDate } from '../format';
import { queryKeys } from '../query';
import type { MessageKind, Ticket, TicketMessage } from '../types';
import { ErrorNotice, Loading } from './Feedback';
import '../pages/workspace.css';

type MessageCommand =
  | { action: 'create'; kind: MessageKind; body: string }
  | { action: 'edit'; message: TicketMessage; body: string }
  | { action: 'approve' | 'send'; message: TicketMessage };

export function ConversationPanel({ ticket, blocked, onChanged, onBusyChange }: {
  ticket: Ticket;
  blocked: boolean;
  onChanged: () => Promise<void>;
  onBusyChange: (busy: boolean) => void;
}) {
  const client = useQueryClient();
  const messages = useQuery({ queryKey: queryKeys.messages(ticket.id), queryFn: ({ signal }) => api.messages(ticket.id, signal), refetchOnWindowFocus: false });
  const delivery = useQuery({ queryKey: ['delivery-config'], queryFn: api.delivery });
  const [kind, setKind] = useState<MessageKind>('note');
  const [body, setBody] = useState('');
  const [notice, setNotice] = useState('');
  const [confirmation, setConfirmation] = useState<TicketMessage | null>(null);
  const mutation = useMutation({
    mutationFn: (command: MessageCommand) => {
      if (command.action === 'create') return api.createMessage(ticket.id, { kind: command.kind, body: command.body, ticket_version: ticket.version });
      const payload = { version: command.message.version, ticket_version: ticket.version };
      if (command.action === 'edit') return api.patchMessage(ticket.id, command.message.id, { ...payload, body: command.body });
      return command.action === 'approve' ? api.approveMessage(ticket.id, command.message.id, payload) : api.sendMessage(ticket.id, command.message.id, payload);
    },
    onMutate: () => { onBusyChange(true); setNotice(''); },
    onSuccess: async (message, command) => {
      if (command.action === 'create') setBody('');
      if (command.action === 'send') setConfirmation(null);
      setNotice(message.delivery_status === 'sent' ? 'SMTP accepted the approved reply.' : message.delivery_status === 'failed' ? 'Delivery failed. The approved reply is preserved; review the error before retrying.' : message.delivery_status === 'unknown' ? 'Delivery is uncertain. Check the mailbox; do not send another copy.' : command.action === 'approve' ? 'Reply approved. Review the recipient and content before choosing Send.' : 'Conversation saved.');
      await onChanged();
    },
    onError: () => { void client.invalidateQueries({ queryKey: queryKeys.ticket(ticket.id) }); void messages.refetch(); },
    onSettled: () => onBusyChange(false),
  });
  const hasDraft = messages.data?.some(message => message.delivery_status === 'draft');
  const locked = blocked || mutation.isPending;
  async function execute(command: MessageCommand) {
    if (locked) return null;
    try { return await mutation.mutateAsync(command); } catch { return null; }
  }
  function submit(event: FormEvent) { event.preventDefault(); if (body.trim()) void execute({ action: 'create', kind, body: body.trim() }); }

  return <section className="panel conversation-panel" id="conversation" aria-labelledby="conversation-heading">
    <div className="conversation-heading"><div><h2 id="conversation-heading" tabIndex={-1}><MessageSquareText size={18} aria-hidden="true" /> Conversation</h2><p>Log customer messages, keep internal notes, and review replies before sending.</p></div><button type="button" className="icon-button" aria-label="Refresh conversation" onClick={() => { void messages.refetch(); }} disabled={messages.isFetching || mutation.isPending}><RefreshCw size={17} aria-hidden="true" /></button></div>
    {delivery.data?.mode === 'mailpit' && <p className="field-help">Local delivery only. <a href={delivery.data.mailpit_url ?? undefined} target="_blank" rel="noopener noreferrer">Open Mailpit inbox</a> — no emails reach external customers.</p>}
    <ErrorNotice error={messages.error} /><ErrorNotice error={delivery.error} /><ErrorNotice error={mutation.error} />
    {messages.isPending && <Loading>Loading conversation…</Loading>}
    {notice && <p className="notice" role="status">{notice}</p>}
    {blocked && !mutation.isPending && <p className="notice notice-warning">Save or discard ticket edits, and reload any newer ticket version, before changing the conversation.</p>}
    <ol className="conversation-list">{messages.data?.map(message => <li className={`message-card message-${message.kind}`} key={message.id}>
      <header className="message-heading"><strong>{message.kind === 'note' ? <><LockKeyhole size={13} aria-hidden="true" /> Internal note</> : message.kind === 'customer' ? 'Customer message' : 'Agent reply'}</strong>{message.kind === 'reply' && <span className={`message-delivery delivery-${message.delivery_status}`}>{message.delivery_status}</span>}<time dateTime={message.created_at}>{formatDate(message.created_at)}</time></header>
      {message.delivery_status === 'draft' ? <DraftEditor message={message} ticketVersion={ticket.version} disabled={locked} onSave={(versioned, text) => execute({ action: 'edit', message: versioned, body: text })} onApprove={versioned => execute({ action: 'approve', message: versioned })} /> : <p className="message-body">{message.body}</p>}
      <div className="message-meta"><p>{message.kind === 'customer' ? 'Recorded by' : 'By'} {message.author.name}{message.kind === 'note' ? ' · never sent to the client or the AI provider' : ''}</p>{message.approved_by && <p>Approved by {message.approved_by.name} · To: {message.recipient_email}</p>}{message.sent_at && <p>SMTP accepted {formatDate(message.sent_at)}</p>}{message.smtp_message_id && <p>Message-ID: <code>{message.smtp_message_id}</code></p>}</div>
      {message.delivery_status === 'failed' && <p className="notice notice-error" role="status">The SMTP server did not accept this reply ({message.delivery_error}). It remains approved and can be explicitly retried if the ticket is unchanged.</p>}
      {(message.delivery_status === 'unknown' || message.delivery_status === 'sending') && <p className="notice notice-warning">{message.delivery_status === 'unknown' ? 'The server could not confirm delivery.' : 'A delivery attempt is in progress or awaiting reconciliation.'} Check the mailbox using Message-ID. Sending again is blocked to prevent duplicates.</p>}
      {(message.delivery_status === 'approved' || message.delivery_status === 'failed') && <div className="message-actions">{message.ticket_version !== ticket.version ? <p className="field-help">Ticket changed after approval. Prepare and review a new draft before sending.</p> : <button type="button" className="button" disabled={locked || !delivery.data?.configured} onClick={() => setConfirmation(message)}><Send size={15} aria-hidden="true" />{message.delivery_status === 'failed' ? 'Retry delivery…' : 'Review and send…'}</button>}{delivery.data && !delivery.data.configured && <p className="field-help">Email delivery is not configured.</p>}</div>}
    </li>)}</ol>
    {!messages.isPending && messages.data?.length === 0 && <p className="muted">No follow-up messages yet. The original request remains in the ticket details.</p>}
    <form className="conversation-composer" onSubmit={submit}>
      <fieldset className="form-fields" disabled={locked || messages.isPending || messages.isError}>
        <legend className="sr-only">Add to conversation</legend>
        <div className="field"><label htmlFor="message-kind">Add to conversation</label><select id="message-kind" value={kind} onChange={event => setKind(event.target.value as MessageKind)}><option value="note">Internal note</option><option value="customer">Log a customer message</option><option value="reply" disabled={hasDraft}>Reply draft</option></select></div>
        <div className="field"><label htmlFor="message-body">{kind === 'note' ? 'Internal note' : kind === 'customer' ? 'Received customer message' : 'Reply draft'}</label><textarea id="message-body" value={body} onChange={event => setBody(event.target.value)} rows={5} required maxLength={10000} /><p className="field-help">{kind === 'note' ? 'Visible only to the support team. Never included in AI context or outbound email.' : kind === 'customer' ? 'Record received text manually; this is not an inbound email integration.' : 'Saving creates a draft only. Approval and sending are separate explicit actions.'}</p></div>
        <button className="button button-secondary" disabled={!body.trim() || (kind === 'reply' && hasDraft)}><Save size={15} aria-hidden="true" />{mutation.isPending ? 'Saving…' : kind === 'reply' ? 'Save reply draft' : 'Add message'}</button>
      </fieldset>
    </form>
    <Dialog.Root open={confirmation !== null} onOpenChange={open => { if (!open && !mutation.isPending) setConfirmation(null); }}>
      <Dialog.Portal><Dialog.Backdrop className="dialog-backdrop" /><Dialog.Popup className="dialog-popup" finalFocus={() => document.getElementById('conversation-heading')}>
        <div className="dialog-header"><div><Dialog.Title>Send this approved reply?</Dialog.Title><Dialog.Description>{delivery.data?.mode === 'mailpit' ? 'This message will be captured by local Mailpit, not delivered externally.' : 'This action sends the exact approved content to the recipient below.'}</Dialog.Description></div><Dialog.Close className="icon-button" aria-label="Close send confirmation" disabled={mutation.isPending}><X size={18} aria-hidden="true" /></Dialog.Close></div>
        <dl className="send-recipient"><dt>To</dt><dd>{confirmation?.recipient_email}</dd><dt>Subject</dt><dd>{confirmation?.subject}</dd></dl><div className="send-preview"><p className="message-body">{confirmation?.body}</p></div>
        <ErrorNotice error={mutation.error} /><div className="form-actions"><Dialog.Close className="button button-secondary" disabled={mutation.isPending}>Cancel</Dialog.Close><button className="button" disabled={locked || !confirmation || confirmation.ticket_version !== ticket.version} onClick={() => { if (confirmation) void execute({ action: 'send', message: confirmation }); }}><Send size={15} aria-hidden="true" />{mutation.isPending ? 'Sending…' : delivery.data?.mode === 'mailpit' ? 'Send to Mailpit' : 'Send reply'}</button></div>
      </Dialog.Popup></Dialog.Portal>
    </Dialog.Root>
  </section>;
}

function DraftEditor({ message, ticketVersion, disabled, onSave, onApprove }: {
  message: TicketMessage;
  ticketVersion: number;
  disabled: boolean;
  onSave: (message: TicketMessage, body: string) => Promise<TicketMessage | null>;
  onApprove: (message: TicketMessage) => Promise<TicketMessage | null>;
}) {
  const [editor, setEditor] = useState({ body: message.body, baseline: message.body, version: message.version });
  const dirty = editor.body !== editor.baseline;
  const changed = editor.version !== message.version;
  const stale = message.ticket_version !== ticketVersion;
  async function save(event: FormEvent) { event.preventDefault(); const saved = await onSave({ ...message, version: editor.version }, editor.body.trim()); if (saved) setEditor({ body: saved.body, baseline: saved.body, version: saved.version }); }
  return <form className="draft-editor" onSubmit={save}>
    <div className="field"><label htmlFor={`draft-${message.id}`}>Review and edit reply</label><textarea id={`draft-${message.id}`} value={editor.body} onChange={event => setEditor(current => ({ ...current, body: event.target.value }))} rows={6} required maxLength={10000} disabled={disabled} /></div>
    {stale && <p className="notice notice-warning">The ticket changed. Review the latest conversation, then save this draft to acknowledge the new version before approving.</p>}
    {changed && <p className="notice notice-warning">This draft changed elsewhere. Your input is preserved; reload to see the saved draft.</p>}
    <div className="message-actions"><button className="button button-secondary" disabled={disabled || !editor.body.trim() || (!dirty && !stale) || changed}><Save size={15} aria-hidden="true" />Save draft</button><button type="button" className="button" disabled={disabled || dirty || changed || stale} onClick={() => { void onApprove({ ...message, version: editor.version }); }}><CheckCheck size={15} aria-hidden="true" />Approve reply</button>{(dirty || changed) && <button type="button" className="button button-quiet" disabled={disabled} onClick={() => setEditor({ body: message.body, baseline: message.body, version: message.version })}>Reload draft (discard edits)</button>}</div>
  </form>;
}
