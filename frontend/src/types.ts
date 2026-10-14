export type TicketStatus = 'open' | 'in_progress' | 'resolved' | 'escalated';
export type Intent = 'billing' | 'technical' | 'account' | 'cancellation' | 'security' | 'other';
export type Priority = 'low' | 'medium' | 'high' | 'urgent';
export type EscalationReason =
  | 'insufficient_knowledge'
  | 'security_or_privacy'
  | 'legal_or_compliance'
  | 'human_requested'
  | 'urgent_impact'
  | 'policy_requires_review';

export interface Agent {
  id: string;
  name: string;
  email: string;
}

export interface Member extends Agent {
  agent_id: string;
  role: 'admin' | 'agent';
  active: boolean;
  version: number;
  registered: boolean;
  created_at: string;
}

export interface SlaTarget {
  due_at: string;
  completed_at: string | null;
  status: 'on_track' | 'met' | 'breached';
}

export interface SlaPolicy {
  priority: Priority;
  first_response_minutes: number;
  resolution_minutes: number;
  version: number;
}

export interface Citation {
  chunk_id: string;
  document_id: string;
  title: string;
  quote: string;
  source_url: string | null;
}

export interface CopilotRun {
  id: string;
  ticket_id: string;
  ticket_version: number;
  model: string;
  intent: Intent;
  priority: Priority;
  classification_reason: string;
  grounded: boolean;
  response_draft: string | null;
  citations: Citation[];
  escalation: { recommended: boolean; reasons: EscalationReason[] };
  created_at: string;
}

export interface AnalysisSummary {
  id: string;
  intent: Intent;
  priority: Priority;
  escalation_recommended: boolean;
}

export interface TicketFields {
  id: string;
  title: string;
  description: string;
  customer_email: string;
  status: TicketStatus;
  assignee_id: string | null;
  version: number;
  created_at: string;
  updated_at: string;
  assignee: Agent | null;
  priority: Priority;
  sla: { first_response: SlaTarget; resolution: SlaTarget };
}

export interface Ticket extends TicketFields {
  latest_analysis: CopilotRun | null;
  analysis_stale: boolean;
}

export interface TicketListItem extends TicketFields {
  latest_analysis: AnalysisSummary | null;
  analysis_stale: boolean;
}

export interface TicketPage {
  items: TicketListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface TicketFilters {
  status?: TicketStatus;
  assignee_id?: string;
  assignment?: 'all' | 'mine' | 'unassigned';
  priority?: Priority;
  intent?: Intent;
  q?: string;
  sla?: 'all' | 'breached';
  sort?: 'updated' | 'priority' | 'due';
  limit: number;
  offset: number;
}

export interface TicketCreate {
  title: string;
  description: string;
  customer_email: string;
  assignee_id?: string | null;
  priority?: Priority;
}

export interface TicketPatch {
  version: number;
  title?: string;
  description?: string;
  customer_email?: string;
  status?: TicketStatus;
  assignee_id?: string | null;
  priority?: Priority;
}

export interface TicketEvent {
  id: string;
  ticket_id: string;
  ticket_version: number;
  changes: Record<string, { old: unknown; new: unknown }>;
  created_at: string;
  actor: { id: string; name: string } | null;
}

export interface KnowledgeSummary {
  id: string;
  title: string;
  source_url: string | null;
  created_at: string;
  chunk_count: number;
}

export interface KnowledgeDocument extends KnowledgeSummary {
  content: string;
}

export interface KnowledgeCreate {
  title: string;
  content: string;
  source_url?: string | null;
}

export type FieldErrors = Record<string, string>;

export interface SavedView {
  id: string;
  name: string;
  filters: Omit<TicketFilters, 'offset'>;
  version: number;
  created_at: string;
}

export type MessageKind = 'customer' | 'note' | 'reply';
export type DeliveryStatus = 'not_applicable' | 'draft' | 'approved' | 'sending' | 'sent' | 'failed' | 'unknown';

export interface TicketMessage {
  id: string;
  ticket_id: string;
  kind: MessageKind;
  body: string;
  author: { id: string; name: string };
  source_run_id: string | null;
  ticket_version: number;
  version: number;
  delivery_status: DeliveryStatus;
  approved_by: { id: string; name: string } | null;
  approved_at: string | null;
  recipient_email: string | null;
  subject: string | null;
  smtp_message_id: string | null;
  delivery_error: string | null;
  sent_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface DeliveryConfiguration {
  configured: boolean;
  mode: 'mailpit' | 'smtp';
  mailpit_url: string | null;
}
