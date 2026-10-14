import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Mail, RefreshCw } from 'lucide-react';
import { mailApi } from '../mail-api';
import { useAuth } from '../auth';
import { formatDate } from '../format';
import { PageHeader } from '../components/PageHeader';
import { ErrorNotice, Loading } from '../components/Feedback';
import './operations.css';

export function MailboxPage() {
  const { member } = useAuth();
  if (member?.role !== 'admin') return <section className="panel"><h1>Administrator access required</h1></section>;
  return <Mailbox />;
}
function Mailbox() {
  const client = useQueryClient();
  const mailbox = useQuery({ queryKey: ['mailbox'], queryFn: mailApi.status, refetchInterval: 30000 });
  const sync = useMutation({ mutationFn: mailApi.sync, onSuccess: async data => { client.setQueryData(['mailbox'], data); await client.invalidateQueries({ queryKey: ['tickets'] }); }, onError: () => { void mailbox.refetch(); } });
  const data = mailbox.data;
  return <div className="operations-page">
    <PageHeader title="Support mailbox" description="One conversation, from the first email to the reviewed reply." actions={<button className="button" disabled={!data?.configured || sync.isPending} onClick={() => sync.mutate()}><RefreshCw size={16} />{sync.isPending ? 'Synchronizing…' : 'Sync now'}</button>} />
    <ErrorNotice error={mailbox.error} onRetry={() => { void mailbox.refetch(); }} /><ErrorNotice error={sync.error} />
    {mailbox.isPending && <Loading>Loading mailbox…</Loading>}
    {data && <>
      <section className="panel operations-summary"><Mail size={24} aria-hidden="true" /><div><h2>{data.configured ? 'Inbound IMAP configured' : 'Inbound mailbox not configured'}</h2><p>{data.configured ? `${data.folder} · checked every ${data.poll_seconds} seconds` : 'Set IMAP_HOST, IMAP_PORT, IMAP_SECURITY, IMAP_USERNAME and IMAP_PASSWORD on the server.'}</p><p className="metadata">Last successful sync: {data.last_synced_at ? formatDate(data.last_synced_at) : 'Not yet synchronized'}</p></div></section>
      {data.last_error && <p className="notice notice-error" role="alert">Connection failed ({data.last_error}). Verify server-side IMAP settings; no credentials are exposed here.</p>}
      <p className="notice">{data.delivery_mode === 'mailpit' ? 'Development mode: replies are captured in Mailpit. No external customer receives them.' : 'External SMTP configured. Every reply still requires approval and an explicit send.'} References keep replies in their thread; a subject alone never merges conversations.</p>
      <section className="panel"><h2>Latest inbound outcomes</h2><p className="field-help">Failed and ignored emails remain in the original mailbox. Attachments stay there; the conversation contains the text body.</p>
        {!data.receipts.length ? <p className="muted">No messages processed yet. Send a message to the configured support inbox, then synchronize.</p> : <div className="data-table-scroll"><table className="data-table"><thead><tr><th scope="col">Received</th><th scope="col">Outcome</th><th scope="col">Details</th><th scope="col">Conversation</th></tr></thead><tbody>{data.receipts.map(row => <tr key={row.id}><td>{formatDate(row.created_at)}</td><td><span className={`badge ${row.status === 'failed' ? 'badge-danger' : 'badge-neutral'}`}>{row.status}</span></td><td>{row.error?.replaceAll('_', ' ') ?? 'Message imported'}</td><td>{row.ticket_id ? <Link to={`/tickets/${row.ticket_id}`}>Open ticket</Link> : '—'}</td></tr>)}</tbody></table></div>}
      </section>
    </>}
  </div>;
}
