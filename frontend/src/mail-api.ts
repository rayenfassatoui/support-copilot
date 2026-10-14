import { request } from './api';
export interface MailReceipt { id: string; status: 'imported' | 'ignored' | 'failed'; error: string | null; ticket_id: string | null; created_at: string }
export interface MailboxStatus {
  configured: boolean; folder: string; delivery_mode: 'mailpit' | 'smtp'; poll_seconds: number;
  last_synced_at: string | null; last_error: string | null; receipts: MailReceipt[];
}
export const mailApi = {
  status: () => request<MailboxStatus>('/mailbox'),
  sync: () => request<MailboxStatus>('/mailbox/sync', { method: 'POST' }),
};
