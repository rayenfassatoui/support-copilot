import { useState } from 'react';
import { Dialog } from '@base-ui/react/dialog';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Bell, X } from 'lucide-react';
import { automationApi } from '../automation-api';
import { formatDate } from '../format';
import { ErrorNotice, Loading } from './Feedback';
import '../pages/operations.css';

export function SlaAlerts() {
  const [open, setOpen] = useState(false);
  const alerts = useQuery({ queryKey: ['sla-alerts'], queryFn: automationApi.alerts, refetchInterval: 30000 });
  return <Dialog.Root open={open} onOpenChange={setOpen}><Dialog.Trigger className="icon-button alert-trigger" aria-label={`Service alerts${alerts.data ? `: ${alerts.data.items.length} shown` : ''}`}><Bell size={18} />{Boolean(alerts.data?.items.length) && <span className="alert-count">{alerts.data!.items.length}</span>}{alerts.isError && <span className="alert-count">!</span>}</Dialog.Trigger><Dialog.Portal><Dialog.Backdrop className="dialog-backdrop" /><Dialog.Popup className="dialog-popup alert-dialog"><div className="dialog-header"><div><Dialog.Title>Service alerts</Dialog.Title><Dialog.Description>Outstanding targets due in the next {alerts.data?.window_minutes ?? '…'} minutes, including overdue targets. Up to 50 are shown, earliest first.</Dialog.Description></div><Dialog.Close className="icon-button" aria-label="Close alerts"><X size={18} /></Dialog.Close></div><ErrorNotice error={alerts.error} onRetry={() => { void alerts.refetch(); }} />{alerts.isPending && <Loading>Checking deadlines…</Loading>}<ul className="alert-list">{alerts.data?.items.map(item => <li key={`${item.ticket_id}:${item.target}`}><Link to={`/tickets/${item.ticket_id}`} onClick={() => setOpen(false)}><strong>{item.title}</strong><span>{item.target === 'first_response' ? 'First response' : 'Resolution'} · {formatDate(item.due_at)}</span><span className={item.breached ? 'sla-overdue' : 'muted'}>{item.breached ? 'Overdue' : 'Due soon'}</span></Link></li>)}</ul>{alerts.data?.items.length === 0 && <p className="muted">No outstanding deadlines within the alert window.</p>}</Dialog.Popup></Dialog.Portal></Dialog.Root>;
}
