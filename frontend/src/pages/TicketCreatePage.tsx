import { useState } from 'react';
import type { FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { ApiError, api } from '../api';
import { invalidateTicket, queryKeys } from '../query';
import type { FieldErrors } from '../types';
import { ErrorNotice } from '../components/Feedback';
import { TicketFormFields, validateTicketForm } from '../components/TicketFormFields';
import type { TicketFormValues } from '../components/TicketFormFields';

export function TicketCreatePage() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [values, setValues] = useState<TicketFormValues>({ title: '', customer_email: '', description: '', assignee_id: '', status: 'open' });
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
    if (Object.keys(nextErrors).length) return;
    create.mutate({
      title: values.title.trim(),
      customer_email: values.customer_email.trim(),
      description: values.description.trim(),
      assignee_id: values.assignee_id || null,
    });
  }

  return (
    <>
      <Link className="back-link" to="/tickets">← Back to tickets</Link>
      <div className="page-heading"><div><p className="eyebrow">New request</p><h1>New ticket</h1><p>Tickets start open. An agent reviews and sends any customer response manually.</p></div></div>
      <section className="panel creation-panel" aria-label="Create ticket">
        <ErrorNotice error={agents.error} onRetry={() => { void agents.refetch(); }} retrying={agents.isFetching} />
        <ErrorNotice error={create.error} />
        {Object.keys(errors).length > 0 && !create.error && <div className="notice notice-error" role="alert">Please check the highlighted fields.</div>}
        <form onSubmit={submit} noValidate aria-busy={create.isPending}>
          <TicketFormFields values={values} onChange={changeField} agents={agents.data ?? []} errors={errors} disabled={create.isPending} assigneesUnavailable={agents.isPending || agents.isError} />
          <div className="form-actions"><button className="button" type="submit" disabled={create.isPending}>{create.isPending ? 'Creating ticket…' : 'Create ticket'}</button><Link className="button button-secondary" to="/tickets">Cancel</Link></div>
        </form>
      </section>
    </>
  );
}
