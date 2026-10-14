import { request } from './api';
import type { TicketMessage } from './types';
export interface TimeMetric {
  completed: number; outstanding: number; average_minutes: number | null;
  sla_met: number; sla_breached: number; sla_pending: number; sla_percent: number | null;
}
export interface AnalyticsReport {
  start: string; end: string; as_of: string; tickets: number;
  first_response: TimeMetric; resolution: TimeMetric;
  feedback: { requested: number; submitted: number; average_rating: number | null; satisfied_percent: number | null; response_percent: number | null };
  daily: { day: string; tickets: number; first_response_minutes: number | null; resolution_minutes: number | null }[];
}
export interface FeedbackStatus { requested: boolean; active: boolean; submitted: boolean; rating: number | null; comment: string | null; expires_at: string | null }
export const analyticsApi = {
  report: (start: string, end: string, signal?: AbortSignal) => request<AnalyticsReport>(`/analytics?start=${start}&end=${end}`, { signal }),
  feedback: (id: string) => request<FeedbackStatus>(`/tickets/${id}/feedback`),
  requestFeedback: (id: string, ticket_version: number) => request<TicketMessage>(`/tickets/${id}/feedback/request`, { method: 'POST', body: { ticket_version } }),
  validate: (token: string) => request<{ expires_at: string }>('/feedback/validate', { method: 'POST', body: { token }, anonymous: true }),
  submit: (token: string, rating: number, comment: string) => request<{ submitted: boolean }>('/feedback/submit', { method: 'POST', body: { token, rating, comment }, anonymous: true }),
};
