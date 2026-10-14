import { intentLabels, priorityLabels, statusLabels } from '../format';
import type { Intent, Priority, TicketStatus } from '../types';

export function StatusBadge({ status }: { status: TicketStatus }) {
  return <span className={`badge status-${status}`}><span className="badge-dot" aria-hidden="true" />{statusLabels[status]}</span>;
}

export function PriorityBadge({ priority }: { priority: Priority }) {
  return <span className={`badge priority-${priority}`}>{priorityLabels[priority]} priority</span>;
}

export function IntentBadge({ intent }: { intent: Intent }) {
  return <span className="badge badge-neutral">{intentLabels[intent]}</span>;
}
