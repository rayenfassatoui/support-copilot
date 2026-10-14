import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Clock3, Mail, PencilLine, RotateCcw, Save, Undo2, UserRound } from 'lucide-react';
import { ApiError, api } from '../api';
import { formatDate } from '../format';
import { invalidateTicket, queryKeys } from '../query';
import type { FieldErrors, Ticket, TicketPatch } from '../types';
import { Avatar } from '../components/Avatar';
import { StatusBadge } from '../components/Badges';
import { CopilotPanel } from '../components/CopilotPanel';
import { ConversationPanel } from '../components/ConversationPanel';
import { SlaSummary } from '../components/SlaSummary';
import { ErrorNotice, Loading } from '../components/Feedback';
import { PageHeader } from '../components/PageHeader';
import { TicketFormFields, ticketFormValues, validateTicketForm } from '../components/TicketFormFields';
import type { TicketFormValues } from '../components/TicketFormFields';
import { TicketTimeline } from '../components/TicketTimeline';
import './detail.css';

interface TicketEditor {
  values: TicketFormValues;
  baseline: TicketFormValues;
  formVersion: number;
}

const editableFields: (keyof TicketFormValues)[] = ['title', 'customer_email', 'description', 'assignee_id', 'status', 'priority'];

export function TicketDetailPage() {
  const { id } = useParams();
  if (!id) return (
    <div className="ticket-workbench">
      <Link className="back-link" to="/tickets"><ArrowLeft size={16} aria-hidden="true" />Back to tickets</Link>
      <PageHeader title="Ticket not found" description="Choose a ticket from your queue to open its workspace." />
    </div>
  );
  return <TicketWorkspace key={id} id={id} />;
}

function TicketWorkspace({ id }: { id: string }) {
  const client = useQueryClient();
  const [editor, setEditor] = useState<TicketEditor | null>(null);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [notice, setNotice] = useState('');
  const [reloading, setReloading] = useState(false);
  const ticket = useQuery({
    queryKey: queryKeys.ticket(id),
    queryFn: ({ signal }) => api.ticket(id, signal),
    refetchOnWindowFocus: false,
  });
  const agents = useQuery({ queryKey: queryKeys.agents, queryFn: ({ signal }) => api.agents(signal) });

  useEffect(() => {
    const loaded = ticket.data;
    if (!loaded) return;
    setEditor((current) => {
      if (current) return current;
      const values = ticketFormValues(loaded);
      return { values, baseline: values, formVersion: loaded.version };
    });
  }, [ticket.data]);

  function resetEditor(saved: Ticket) {
    const values = ticketFormValues(saved);
    setEditor({ values, baseline: values, formVersion: saved.version });
    setErrors({});
  }

  const save = useMutation({
    mutationFn: (payload: TicketPatch) => api.patchTicket(id, payload),
    onSuccess: async (saved) => {
      client.setQueryData(queryKeys.ticket(id), saved);
      resetEditor(saved);
      setNotice('Ticket saved. Any older AI analysis is marked stale.');
      await invalidateTicket(client, id);
    },
    onError: (error) => { if (error instanceof ApiError) setErrors(error.fields); },
  });
  const analyze = useMutation({
    mutationFn: (version: number) => api.analyze(id, version),
    onSuccess: async (run) => {
      await client.cancelQueries({ queryKey: queryKeys.ticket(id), exact: true });
      client.setQueryData<Ticket>(queryKeys.ticket(id), (current) => current ? {
        ...current, latest_analysis: run, analysis_stale: current.version !== run.ticket_version,
      } : current);
      setNotice('Analysis saved. Review the result and sources before using the draft.');
      await invalidateTicket(client, id);
    },
  });
  const escalate = useMutation({
    mutationFn: (version: number) => api.patchTicket(id, { version, status: 'escalated' }),
    onSuccess: async (saved) => {
      client.setQueryData(queryKeys.ticket(id), saved);
      resetEditor(saved);
      setNotice('Ticket escalated. The status change is recorded in ticket history.');
      await invalidateTicket(client, id);
    },
  });

  const [conversationBusy, setConversationBusy] = useState(false);
  const draft = useMutation({
    mutationFn: () => {
      const run = ticket.data?.latest_analysis;
      if (!ticket.data || !run?.grounded || !run.response_draft || ticket.data.analysis_stale) throw new Error('No current grounded draft is available.');
      return api.createMessage(id, { kind: 'reply', body: run.response_draft, source_run_id: run.id, ticket_version: ticket.data.version });
    },
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: queryKeys.messages(id) });
      setNotice('AI draft added to the conversation. Edit and approve it before sending.');
      document.getElementById('conversation-heading')?.focus();
    },
  });
  async function conversationChanged() {
    await invalidateTicket(client, id);
    const saved = client.getQueryData<Ticket>(queryKeys.ticket(id));
    if (saved) resetEditor(saved);
  }
  const busy = save.isPending || analyze.isPending || escalate.isPending || draft.isPending || conversationBusy || reloading;
  const dirty = Boolean(editor && editableFields.some((field) => editor.values[field] !== editor.baseline[field]));
  const serverChanged = Boolean(editor && ticket.data && ticket.data.version !== editor.formVersion);
  const analysisBlocked = dirty || serverChanged;
  const blockedReason = dirty
    ? 'Save or discard unsaved ticket edits before analyzing or escalating.'
    : serverChanged ? 'A newer ticket version is available. Reload latest before analyzing or escalating.' : null;

  function changeField<K extends keyof TicketFormValues>(field: K, value: TicketFormValues[K]) {
    setEditor((current) => current ? { ...current, values: { ...current.values, [field]: value } } : current);
    setNotice('');
    setErrors((current) => {
      const next = { ...current };
      delete next[field];
      return next;
    });
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editor || !dirty || busy) return;
    const nextErrors = validateTicketForm(editor.values);
    const emailInput = event.currentTarget.elements.namedItem('customer_email');
    if (emailInput instanceof HTMLInputElement && emailInput.validity.typeMismatch) nextErrors.customer_email = 'Enter a valid customer email address.';
    setErrors(nextErrors);
    setNotice('');
    save.reset();
    if (Object.keys(nextErrors).length) return;
    save.mutate({
      version: editor.formVersion,
      title: editor.values.title.trim(),
      customer_email: editor.values.customer_email.trim(),
      description: editor.values.description.trim(),
      assignee_id: editor.values.assignee_id || null,
      status: editor.values.status,
      priority: editor.values.priority,
    });
  }

  async function reloadLatest() {
    if (busy) return;
    setReloading(true);
    setNotice('');
    try {
      const latest = await ticket.refetch({ throwOnError: false });
      if (latest.isSuccess && latest.data) {
        resetEditor(latest.data);
        save.reset();
        analyze.reset();
        escalate.reset();
        setNotice('Latest saved ticket loaded. Local edits were discarded.');
      }
    } finally {
      setReloading(false);
    }
  }

  function discardEdits() {
    if (busy || !ticket.data) return;
    resetEditor(ticket.data);
    save.reset();
    analyze.reset();
    escalate.reset();
    setNotice('Unsaved edits discarded.');
  }

  function analyzeSavedTicket() {
    if (!editor || analysisBlocked || busy) return;
    setNotice('');
    analyze.mutate(editor.formVersion);
  }

  function escalateSavedTicket() {
    if (!editor || analysisBlocked || busy || ticket.data?.status === 'escalated') return;
    setNotice('');
    escalate.mutate(editor.formVersion);
  }

  if (ticket.isPending) return <Loading>Loading ticket…</Loading>;
  if (!ticket.data) return (
    <div className="ticket-workbench">
      <Link className="back-link" to="/tickets"><ArrowLeft size={16} aria-hidden="true" />Back to tickets</Link>
      <PageHeader title={ticket.error instanceof ApiError && ticket.error.status === 404 ? 'Ticket not found' : 'Ticket unavailable'} description="Your ticket queue is still available. Try loading this ticket again." />
      <ErrorNotice error={ticket.error} onRetry={() => { void ticket.refetch(); }} retrying={ticket.isFetching} />
    </div>
  );
  if (!editor) return <Loading>Preparing ticket form…</Loading>;
  const savedTicket = ticket.data;

  return (
    <div className="ticket-workbench">
      <div className="ticket-workbench-nav">
        <Link className="back-link" to="/tickets"><ArrowLeft size={16} aria-hidden="true" />Back to tickets</Link>
        <span className="ticket-reference"><span>Ticket reference</span><code>{savedTicket.id}</code></span>
      </div>

      <header className="ticket-context-header">
        <PageHeader
          eyebrow="Ticket workspace"
          title={savedTicket.title}
          description={<>Updated <time dateTime={savedTicket.updated_at}>{formatDate(savedTicket.updated_at)}</time><span className="ticket-heading-separator" aria-hidden="true">·</span>Saved version {savedTicket.version}</>}
          actions={<StatusBadge status={savedTicket.status} />}
        />
        <dl className="ticket-context-grid">
          <div>
            <dt>Customer</dt>
            <dd><Mail size={16} aria-hidden="true" /><span>{savedTicket.customer_email}</span></dd>
          </div>
          <div>
            <dt>Assigned agent</dt>
            <dd>
              {savedTicket.assignee ? <Avatar name={savedTicket.assignee.name} /> : <UserRound size={16} aria-hidden="true" />}
              <span>{savedTicket.assignee?.name ?? (savedTicket.assignee_id ? 'Unknown agent' : 'Unassigned')}</span>
            </dd>
          </div>
          <div>
            <dt>Created</dt>
            <dd><Clock3 size={16} aria-hidden="true" /><time dateTime={savedTicket.created_at}>{formatDate(savedTicket.created_at)}</time></dd>
          </div>
        </dl>
      </header>

      <SlaSummary ticket={savedTicket} />
      <ErrorNotice error={ticket.error} onRetry={() => { void ticket.refetch(); }} retrying={ticket.isFetching} />
      <ErrorNotice error={draft.error} />
      {notice && <p className="notice notice-success" role="status">{notice}</p>}
      {serverChanged && (
        <div className="notice notice-warning ticket-conflict-notice" role="status">
          <strong>A newer saved ticket version is available.</strong>
          <p>Your form is still on version {editor.formVersion}; the latest saved version is {savedTicket.version}. Your local inputs have not been replaced. Reload latest before continuing.</p>
          <button type="button" className="button button-secondary button-small" onClick={() => { void reloadLatest(); }} disabled={busy}>
            <RotateCcw size={15} aria-hidden="true" />{reloading ? 'Reloading…' : `Reload latest${dirty ? ' (discard edits)' : ''}`}
          </button>
        </div>
      )}

      <div className="ticket-detail-layout">
        <div className="panel-stack ticket-primary-column">
          <ConversationPanel ticket={savedTicket} blocked={analysisBlocked || busy} onChanged={conversationChanged} onBusyChange={setConversationBusy} />
          <section className="panel ticket-editor" aria-labelledby="ticket-edit-heading">
            <div className="ticket-section-header">
              <div>
                <h2 id="ticket-edit-heading"><PencilLine size={18} aria-hidden="true" />Edit ticket</h2>
                <p className="field-help">Customer request, ownership, and status.</p>
              </div>
              <span className="ticket-form-version">Form version {editor.formVersion}</span>
            </div>
            {dirty && (
              <div className="ticket-unsaved-state" role="status">
                <span className="ticket-unsaved-dot" aria-hidden="true" />
                <p><strong>Unsaved changes</strong><span>Save or discard your edits before analyzing.</span></p>
              </div>
            )}
            <ErrorNotice error={agents.error} onRetry={() => { void agents.refetch(); }} retrying={agents.isFetching} />
            <ErrorNotice error={save.error}>
              {save.error instanceof ApiError && save.error.code === 'ticket_conflict' && <>
                <p>Your unsaved edits are preserved. Reload latest replaces them with the saved ticket; it does not save your local changes.</p>
                <button type="button" className="button button-secondary button-small" onClick={() => { void reloadLatest(); }} disabled={busy}><RotateCcw size={15} aria-hidden="true" />{reloading ? 'Reloading…' : 'Reload latest (discard edits)'}</button>
              </>}
            </ErrorNotice>
            {Object.keys(errors).length > 0 && !save.error && <div className="notice notice-error" role="alert">Please check the highlighted fields.</div>}
            <form onSubmit={submit} noValidate aria-busy={save.isPending || reloading || escalate.isPending}>
              <TicketFormFields values={editor.values} onChange={changeField} agents={agents.data ?? []} errors={errors} disabled={busy} editing assigneesUnavailable={agents.isPending || agents.isError} />
              <div className="form-actions ticket-editor-actions">
                <button type="submit" className="button" disabled={!dirty || busy}><Save size={16} aria-hidden="true" />{save.isPending ? 'Saving…' : 'Save changes'}</button>
                <button type="button" className="button button-secondary" onClick={discardEdits} disabled={!dirty || busy}><Undo2 size={16} aria-hidden="true" />Discard edits</button>
                <button type="button" className="button button-quiet ticket-reload-button" onClick={() => { void reloadLatest(); }} disabled={busy}><RotateCcw size={15} aria-hidden="true" />{reloading ? 'Reloading…' : dirty ? 'Reload latest (discard edits)' : 'Reload latest'}</button>
              </div>
            </form>
          </section>
          <TicketTimeline ticketId={id} agents={agents.data ?? (savedTicket.assignee ? [savedTicket.assignee] : [])} />
        </div>
        <CopilotPanel run={savedTicket.latest_analysis} stale={savedTicket.analysis_stale} blocked={analysisBlocked} blockedReason={blockedReason} busy={busy} analyzing={analyze.isPending} escalating={escalate.isPending} onAnalyze={analyzeSavedTicket} onEscalate={escalateSavedTicket} onUseDraft={() => draft.mutate()} analyzeError={analyze.error} escalateError={escalate.error} status={savedTicket.status} onReload={() => { void reloadLatest(); }} />
      </div>
    </div>
  );
}
