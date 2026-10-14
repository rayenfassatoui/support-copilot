import type { EscalationReason, Intent, Priority, TicketStatus } from './types';

export const statusLabels: Record<TicketStatus, string> = {
  open: 'Open', in_progress: 'In progress', resolved: 'Resolved', escalated: 'Escalated',
};
export const statuses = Object.keys(statusLabels) as TicketStatus[];
export const intentLabels: Record<Intent, string> = {
  billing: 'Billing', technical: 'Technical', account: 'Account', cancellation: 'Cancellation', security: 'Security', other: 'Other',
};
export const priorityLabels: Record<Priority, string> = {
  low: 'Low', medium: 'Medium', high: 'High', urgent: 'Urgent',
};
export const escalationLabels: Record<EscalationReason, string> = {
  insufficient_knowledge: 'Insufficient knowledge',
  security_or_privacy: 'Security or privacy concern',
  legal_or_compliance: 'Legal or compliance review',
  human_requested: 'Customer requested a human',
  urgent_impact: 'Urgent customer impact',
  policy_requires_review: 'Policy requires human review',
};

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short',
});

export function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : dateFormatter.format(date);
}

export function safeHttpUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : null;
  } catch {
    return null;
  }
}
