import { request } from './api';
import type { Priority } from './types';

export interface BusinessCalendar {
  version: number; enabled: boolean; timezone: string; weekdays: number[];
  opens_minute: number; closes_minute: number; holidays: string[]; alert_minutes: number;
}
export interface AssignmentRule {
  id: string; name: string; enabled: boolean; position: number; priority: Priority | null;
  customer_domain: string | null; subject_contains: string | null; assignee_id: string; version: number; catch_all: boolean;
}
export interface SlaAlert { ticket_id: string; title: string; target: 'first_response' | 'resolution'; due_at: string; breached: boolean }
export interface AlertFeed { as_of: string; window_minutes: number; items: SlaAlert[] }
export const automationApi = {
  calendar: () => request<BusinessCalendar>('/automation/calendar'),
  saveCalendar: (body: BusinessCalendar) => request<BusinessCalendar>('/automation/calendar', { method: 'PATCH', body }),
  rules: () => request<AssignmentRule[]>('/automation/rules'),
  createRule: (body: Omit<AssignmentRule, 'id' | 'version'>) => request<AssignmentRule>('/automation/rules', { method: 'POST', body }),
  saveRule: ({ id, ...body }: AssignmentRule) => request<AssignmentRule>(`/automation/rules/${id}`, { method: 'PATCH', body }),
  deleteRule: (rule: AssignmentRule) => request<void>(`/automation/rules/${rule.id}?version=${rule.version}`, { method: 'DELETE' }),
  orderRules: (rules: AssignmentRule[]) => request<AssignmentRule[]>('/automation/rules/order', { method: 'PUT', body: { rules: rules.map(({id, version}) => ({id, version})) } }),
  alerts: () => request<AlertFeed>('/automation/sla-alerts'),
};
