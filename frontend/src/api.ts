import type {
  Agent, CopilotRun, DeliveryConfiguration, FieldErrors, KnowledgeCreate, KnowledgeDocument, KnowledgeSummary,
  Member, MessageKind, SavedView, SlaPolicy, Ticket, TicketCreate, TicketEvent, TicketFilters, TicketMessage, TicketPage, TicketPatch,
} from './types';
import { clearAuthToken, getBearerToken, SessionRequiredError } from './auth-client';

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fields: FieldErrors;

  constructor(status: number, code: string, message: string, fields: FieldErrors = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.fields = fields;
  }
}

function responseError(status: number, payload: unknown): ApiError {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = payload.detail;
    if (Array.isArray(detail)) {
      const fields: FieldErrors = {};
      for (const issue of detail) {
        if (!issue || typeof issue !== 'object' || typeof issue.msg !== 'string' || !Array.isArray(issue.loc)) continue;
        const field = issue.loc[0] === 'body' ? issue.loc[1] : issue.loc[0];
        if (typeof field === 'string' && !fields[field]) fields[field] = issue.msg;
      }
      return new ApiError(status, 'validation_error', 'Please check the highlighted fields and try again.', fields);
    }
    if (detail && typeof detail === 'object' && 'code' in detail && 'message' in detail
      && typeof detail.code === 'string' && typeof detail.message === 'string') {
      const fields: FieldErrors = detail.code === 'invalid_assignee' ? { assignee_id: detail.message } : {};
      return new ApiError(status, detail.code, detail.message, fields);
    }
  }
  return new ApiError(status, 'request_failed', status === 404
    ? 'Resource not found.'
    : 'The server could not complete this request. Reload to confirm the latest saved state.');
}

export async function request<T>(path: string, options: { method?: string; body?: unknown; signal?: AbortSignal; anonymous?: boolean } = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (!options.anonymous) {
    try {
      headers.Authorization = `Bearer ${await getBearerToken()}`;
    } catch (error) {
      if (error instanceof SessionRequiredError) {
        clearAuthToken();
        window.dispatchEvent(new Event('copilot-session-expired'));
        throw new ApiError(401, 'authentication_required', error.message);
      }
      throw new ApiError(503, 'auth_unavailable', error instanceof Error ? error.message : 'Unable to authenticate this request.');
    }
  }
  const multipart = options.body instanceof FormData;
  if (options.body !== undefined && !multipart) headers['Content-Type'] = 'application/json';
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method: options.method ?? 'GET',
      credentials: 'same-origin',
      signal: options.signal,
      headers,
      body: options.body === undefined ? undefined : multipart ? options.body as FormData : JSON.stringify(options.body),
    });
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw error;
    throw new ApiError(0, 'network_unavailable', 'Cannot reach the server. Check that the API is running, then reload to confirm the latest saved state.');
  }

  if (response.status === 401 && !options.anonymous) {
    clearAuthToken();
    window.dispatchEvent(new Event('copilot-session-expired'));
  }
  if (response.status === 204) return undefined as T;
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ApiError(response.status, 'invalid_server_response', 'The server returned an unreadable response. Reload to confirm the latest saved state.');
  }
  if (!response.ok) throw responseError(response.status, payload);
  return payload as T;
}

export const api = {
  me: () => request<Member>('/auth/me'),
  delivery: () => request<DeliveryConfiguration>('/delivery/config'),
  members: () => request<Member[]>('/members'),
  createMember: (body: { name: string; email: string; role: Member['role'] }) => request<Member>('/members', { method: 'POST', body }),
  patchMember: (id: string, body: { version: number; role: Member['role']; active: boolean }) => request<Member>(`/members/${encodeURIComponent(id)}`, { method: 'PATCH', body }),
  policies: () => request<SlaPolicy[]>('/sla-policies'),
  patchPolicy: (priority: string, body: Omit<SlaPolicy, 'priority'>) => request<SlaPolicy>(`/sla-policies/${encodeURIComponent(priority)}`, { method: 'PATCH', body }),
  views: () => request<SavedView[]>('/views'),
  createView: (body: Pick<SavedView, 'name' | 'filters'>) => request<SavedView>('/views', { method: 'POST', body }),
  patchView: (id: string, body: Pick<SavedView, 'name' | 'filters' | 'version'>) => request<SavedView>(`/views/${encodeURIComponent(id)}`, { method: 'PATCH', body }),
  deleteView: (id: string, version: number) => request<void>(`/views/${encodeURIComponent(id)}?version=${version}`, { method: 'DELETE' }),
  agents: (signal?: AbortSignal) => request<Agent[]>('/agents', { signal }),
  tickets: (filters: TicketFilters, signal?: AbortSignal) => {
    const params = new URLSearchParams({ limit: String(filters.limit), offset: String(filters.offset) });
    if (filters.status) params.set('status', filters.status);
    if (filters.assignee_id) params.set('assignee_id', filters.assignee_id);
    for (const field of ['assignment', 'priority', 'intent', 'q', 'sla', 'sort'] as const) {
      if (filters[field]) params.set(field, filters[field]);
    }
    return request<TicketPage>(`/tickets?${params}`, { signal });
  },
  ticket: (id: string, signal?: AbortSignal) => request<Ticket>(`/tickets/${encodeURIComponent(id)}`, { signal }),
  createTicket: (body: TicketCreate) => request<Ticket>('/tickets', { method: 'POST', body }),
  patchTicket: (id: string, body: TicketPatch) => request<Ticket>(`/tickets/${encodeURIComponent(id)}`, { method: 'PATCH', body }),
  events: (id: string, signal?: AbortSignal) => request<TicketEvent[]>(`/tickets/${encodeURIComponent(id)}/events`, { signal }),
  analyze: (id: string, version: number) => request<CopilotRun>(`/tickets/${encodeURIComponent(id)}/analyze`, { method: 'POST', body: { version } }),
  knowledge: (signal?: AbortSignal) => request<KnowledgeSummary[]>('/knowledge', { signal }),
  document: (id: string, signal?: AbortSignal) => request<KnowledgeDocument>(`/knowledge/${encodeURIComponent(id)}`, { signal }),
  createDocument: (body: KnowledgeCreate) => request<KnowledgeDocument>('/knowledge', { method: 'POST', body }),
  messages: (id: string, signal?: AbortSignal) => request<TicketMessage[]>(`/tickets/${encodeURIComponent(id)}/messages`, { signal }),
  createMessage: (id: string, body: { kind: MessageKind; body: string; ticket_version: number; source_run_id?: string }) => request<TicketMessage>(`/tickets/${encodeURIComponent(id)}/messages`, { method: 'POST', body }),
  patchMessage: (id: string, messageId: string, body: { body: string; version: number; ticket_version: number }) => request<TicketMessage>(`/tickets/${encodeURIComponent(id)}/messages/${encodeURIComponent(messageId)}`, { method: 'PATCH', body }),
  deleteMessage: (id: string, messageId: string, body: { version: number; ticket_version: number }) => request<void>(`/tickets/${encodeURIComponent(id)}/messages/${encodeURIComponent(messageId)}`, { method: 'DELETE', body }),
  approveMessage: (id: string, messageId: string, body: { version: number; ticket_version: number }) => request<TicketMessage>(`/tickets/${encodeURIComponent(id)}/messages/${encodeURIComponent(messageId)}/approve`, { method: 'POST', body }),
  sendMessage: (id: string, messageId: string, body: { version: number; ticket_version: number }) => request<TicketMessage>(`/tickets/${encodeURIComponent(id)}/messages/${encodeURIComponent(messageId)}/send`, { method: 'POST', body }),
};
