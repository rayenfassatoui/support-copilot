import type {
  Agent, CopilotRun, FieldErrors, KnowledgeCreate, KnowledgeDocument, KnowledgeSummary,
  Ticket, TicketCreate, TicketEvent, TicketFilters, TicketPage, TicketPatch,
} from './types';

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

async function request<T>(path: string, options: { method?: string; body?: unknown; signal?: AbortSignal } = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method: options.method ?? 'GET',
      credentials: 'same-origin',
      signal: options.signal,
      headers: options.body === undefined
        ? { Accept: 'application/json' }
        : { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw error;
    throw new ApiError(0, 'network_unavailable', 'Cannot reach the server. Check that the API is running, then reload to confirm the latest saved state.');
  }

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
  agents: (signal?: AbortSignal) => request<Agent[]>('/agents', { signal }),
  tickets: (filters: TicketFilters, signal?: AbortSignal) => {
    const params = new URLSearchParams({ limit: String(filters.limit), offset: String(filters.offset) });
    if (filters.status) params.set('status', filters.status);
    if (filters.assignee_id) params.set('assignee_id', filters.assignee_id);
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
};
