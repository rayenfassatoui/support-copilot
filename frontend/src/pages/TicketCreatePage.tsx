import { useState } from 'react';
import type { FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, ArrowRight, FileText, ShieldCheck } from 'lucide-react';
import { ApiError, api } from '../api';
import { invalidateTicket, queryKeys } from '../query';
import type { FieldErrors } from '../types';
import { ErrorNotice } from '../components/Feedback';
import { TicketFormFields, validateTicketForm } from '../components/TicketFormFields';
import type { TicketFormValues } from '../components/TicketFormFields';
import { PageHeader } from '../components/PageHeader';
import './tickets.css';

export function TicketCreatePage() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [values, setValues] = useState<TicketFormValues>({ title: '', customer_email: '', description: '', assignee_id: '', status: 'open', priority: 'medium' });
  const [errors, setErrors] = useState<FieldErrors>({});
  const agents = useQuery({ queryKey: queryKeys.agents, queryFn: ({ signal }) => api.agents(signal) });
  const create = useMutation({
    mutationFn: api.createTicket,
    onSuccess: async (ticket) => {
      client.setQueryData(queryKeys.ticket(ticket.id), ticket);
      await invalidateTicket(client, ticket.id);
      navigate(`/tickets/${ticket.id}`);
    },
    onError: (error) => { if (error instanceof ApiError) setErrors(error.fields); },
  });

  function changeField<K extends keyof TicketFormValues>(field: K, value: TicketFormValues[K]) {
    setValues((current) => ({ ...current, [field]: value }));
    setErrors((current) => {
      const next = { ...current };
      delete next[field];
      return next;
    });
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (create.isPending) return;
    const nextErrors = validateTicketForm(values);
    const emailInput = event.currentTarget.elements.namedItem('customer_email');
    if (emailInput instanceof HTMLInputElement && emailInput.validity.typeMismatch) nextErrors.customer_email = 'Enter a valid customer email address.';
    setErrors(nextErrors);
    create.reset();
    if (Object.keys(nextErrors).length) {
      const firstInvalid = event.currentTarget.elements.namedItem(Object.keys(nextErrors)[0]);
      if (firstInvalid instanceof HTMLElement) firstInvalid.focus();
      return;
    }
    create.mutate({
      title: values.title.trim(),
      customer_email: values.customer_email.trim(),
      description: values.description.trim(),
      assignee_id: values.assignee_id || null,
      priority: values.priority,
    });
  }

  return (
    <div className="ticket-create-page">
      <Link className="back-link" to="/tickets"><ArrowLeft size={15} aria-hidden="true" />Back to tickets</Link>
      <PageHeader title="New ticket" description="Start with the customer’s request. Your team and Copilot can take it from here." />
      <div className="ticket-create-layout">
        <section className="panel ticket-create-panel" aria-labelledby="ticket-create-heading">
          <div className="ticket-create-intro">
            <span className="ticket-create-icon"><FileText size={19} strokeWidth={1.6} aria-hidden="true" /></span>
            <div><h2 id="ticket-create-heading">Request details</h2><p>A clear description helps your team find the right next step.</p></div>
          </div>
          <form className="ticket-create-form" onSubmit={submit} noValidate aria-busy={create.isPending}>
            <ErrorNotice error={agents.error} onRetry={() => { void agents.refetch(); }} retrying={agents.isFetching} />
            <ErrorNotice error={create.error} />
            {Object.keys(errors).length > 0 && !create.error && <div className="notice notice-error" role="alert">Please check the highlighted fields.</div>}
            <TicketFormFields values={values} onChange={changeField} agents={agents.data ?? []} errors={errors} disabled={create.isPending} assigneesUnavailable={agents.isPending || agents.isError} />
            <div className="form-actions">
              <button className="button" type="submit" disabled={create.isPending}>{create.isPending ? <><span className="spinner" aria-hidden="true" />Creating ticket…</> : <>Create ticket<ArrowRight size={16} aria-hidden="true" /></>}</button>
              <Link className="button button-secondary" to="/tickets">Cancel</Link>
            </div>
            <p className="ticket-create-status" role="status">{create.isPending ? 'Saving the request. You’ll open the ticket when it’s ready.' : ''}</p>
          </form>
        </section>
        <aside className="ticket-create-context" aria-labelledby="ticket-create-next">
          <h2 id="ticket-create-next">What happens next</h2>
          <ol className="ticket-create-steps">
            <li><strong>It starts open</strong><p>Choose an agent, or let matching assignment rules route the request.</p></li>
            <li><strong>Review with Copilot</strong><p>Run an analysis from the ticket to see classification, advice, and supporting sources.</p></li>
            <li><strong>You stay in control</strong><p>Review any draft and send your response manually. Copilot never sends it for you.</p></li>
          </ol>
          <div className="ticket-create-safety"><ShieldCheck size={19} strokeWidth={1.6} aria-hidden="true" /><p>Only include details you are authorized to process. AI providers may retain inputs; keep secrets and sensitive personal data out of tickets.</p></div>
        </aside>
      </div>
    </div>
  );
}
