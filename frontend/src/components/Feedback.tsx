import type { ReactNode } from 'react';
import { ApiError } from '../api';

export function ErrorNotice({ error, onRetry, retrying = false, children }: {
  error: unknown;
  onRetry?: () => void;
  retrying?: boolean;
  children?: ReactNode;
}) {
  if (!error) return null;
  const apiError = error instanceof ApiError ? error : null;
  return (
    <div className="notice notice-error" role="alert">
      <strong>{apiError?.code === 'ticket_conflict' ? 'Ticket changed' : 'Request could not be completed'}</strong>
      <p>{apiError?.message ?? 'An unexpected error occurred. Please try again.'}</p>
      {apiError?.code === 'ai_not_configured' && <p>Ticket management remains available. The OpenRouter key must be configured on the server, not in this browser.</p>}
      {children}
      {onRetry && <button type="button" className="button button-small button-secondary" onClick={onRetry} disabled={retrying}>{retrying ? 'Loading…' : 'Try again'}</button>}
    </div>
  );
}

export function Loading({ children = 'Loading…' }: { children?: ReactNode }) {
  return <p className="loading" role="status"><span className="spinner" aria-hidden="true" />{children}</p>;
}

export function FieldError({ id, message }: { id: string; message?: string }) {
  return message ? <p className="field-error" id={id}>{message}</p> : null;
}

export function EmptyState({ title, children }: { title: string; children: ReactNode }) {
  return <div className="empty-state"><h2>{title}</h2><div>{children}</div></div>;
}
