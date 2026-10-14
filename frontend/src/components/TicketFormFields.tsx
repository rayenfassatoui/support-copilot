import { statuses, statusLabels } from '../format';
import type { Agent, FieldErrors, Ticket, TicketStatus } from '../types';
import { FieldError } from './Feedback';

export interface TicketFormValues {
  title: string;
  customer_email: string;
  description: string;
  assignee_id: string;
  status: TicketStatus;
}

export function ticketFormValues(ticket: Ticket): TicketFormValues {
  return {
    title: ticket.title,
    customer_email: ticket.customer_email,
    description: ticket.description,
    assignee_id: ticket.assignee_id ?? '',
    status: ticket.status,
  };
}

export function validateTicketForm(values: TicketFormValues): FieldErrors {
  const errors: FieldErrors = {};
  const titleLength = values.title.trim().length;
  const descriptionLength = values.description.trim().length;
  if (titleLength < 3 || titleLength > 200) errors.title = 'Enter a title with 3–200 characters.';
  if (descriptionLength < 10 || descriptionLength > 10_000) errors.description = 'Enter a description with 10–10,000 characters.';
  if (!values.customer_email.trim()) errors.customer_email = 'Enter the customer’s email address.';
  return errors;
}

export function TicketFormFields({ values, onChange, agents, errors, disabled = false, editing = false, assigneesUnavailable = false }: {
  values: TicketFormValues;
  onChange: <K extends keyof TicketFormValues>(field: K, value: TicketFormValues[K]) => void;
  agents: Agent[];
  errors: FieldErrors;
  disabled?: boolean;
  editing?: boolean;
  assigneesUnavailable?: boolean;
}) {
  return (
    <fieldset className="form-fields" disabled={disabled}>
      <legend className="sr-only">Ticket information</legend>
      <div className="field">
        <label htmlFor="ticket-title">Title <span className="required-text">(required)</span></label>
        <input id="ticket-title" name="title" value={values.title} onChange={(event) => onChange('title', event.target.value)} required minLength={3} maxLength={200}
          aria-invalid={Boolean(errors.title)} aria-describedby={errors.title ? 'ticket-title-error' : undefined} />
        <FieldError id="ticket-title-error" message={errors.title} />
      </div>
      <div className="field">
        <label htmlFor="ticket-email">Customer email <span className="required-text">(required)</span></label>
        <input id="ticket-email" name="customer_email" type="email" autoComplete="email" value={values.customer_email} onChange={(event) => onChange('customer_email', event.target.value)} required
          aria-invalid={Boolean(errors.customer_email)} aria-describedby={errors.customer_email ? 'ticket-email-error' : undefined} />
        <FieldError id="ticket-email-error" message={errors.customer_email} />
      </div>
      <div className="field">
        <label htmlFor="ticket-description">Description <span className="required-text">(required)</span></label>
        <textarea id="ticket-description" name="description" rows={8} value={values.description} onChange={(event) => onChange('description', event.target.value)} required minLength={10} maxLength={10_000}
          aria-invalid={Boolean(errors.description)} aria-describedby={`ticket-description-help${errors.description ? ' ticket-description-error' : ''}`} />
        <p className="field-help" id="ticket-description-help">10–10,000 characters. Use synthetic customer details for this demo; do not include passwords, API keys, or sensitive data.</p>
        <FieldError id="ticket-description-error" message={errors.description} />
      </div>
      <div className={editing ? 'field-row' : undefined}>
        <div className="field">
          <label htmlFor="ticket-assignee">Assigned agent</label>
          <select id="ticket-assignee" name="assignee_id" value={values.assignee_id} onChange={(event) => onChange('assignee_id', event.target.value)} disabled={disabled || assigneesUnavailable}
            aria-invalid={Boolean(errors.assignee_id)} aria-describedby={`ticket-assignee-help${errors.assignee_id ? ' ticket-assignee-error' : ''}`}>
            <option value="">Unassigned</option>
            {values.assignee_id && !agents.some((agent) => agent.id === values.assignee_id) && <option value={values.assignee_id}>Current assigned agent</option>}
            {agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}
          </select>
          <p className="field-help" id="ticket-assignee-help">{assigneesUnavailable ? 'Agent choices are unavailable until the agent list loads.' : agents.length ? 'Choose an existing agent, or leave unassigned.' : 'No agents are available. Ask the demo operator to seed the agents.'}</p>
          <FieldError id="ticket-assignee-error" message={errors.assignee_id} />
        </div>
        {editing && <div className="field">
          <label htmlFor="ticket-status">Status</label>
          <select id="ticket-status" name="status" value={values.status} onChange={(event) => onChange('status', event.target.value as TicketStatus)}
            aria-invalid={Boolean(errors.status)} aria-describedby={errors.status ? 'ticket-status-error' : undefined}>
            {statuses.map((status) => <option key={status} value={status}>{statusLabels[status]}</option>)}
          </select>
          <FieldError id="ticket-status-error" message={errors.status} />
        </div>}
      </div>
    </fieldset>
  );
}
