import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { MessageSquareHeart } from 'lucide-react';
import { analyticsApi } from '../analytics-api';
import { queryKeys } from '../query';
import type { Ticket } from '../types';
import { ErrorNotice } from './Feedback';

export function FeedbackRequest({ ticket, disabled = false }: { ticket: Ticket; disabled?: boolean }) {
  const client = useQueryClient();
  const feedback = useQuery({ queryKey: ['feedback', ticket.id, ticket.version], queryFn: () => analyticsApi.feedback(ticket.id), refetchOnWindowFocus: false });
  const create = useMutation({ mutationFn: () => analyticsApi.requestFeedback(ticket.id, ticket.version), onSuccess: async () => { await Promise.all([feedback.refetch(), client.invalidateQueries({ queryKey: queryKeys.messages(ticket.id) })]); document.getElementById('conversation-heading')?.focus(); } });
  return <section className="panel feedback-request"><h2><MessageSquareHeart size={18} aria-hidden="true" /> Customer feedback</h2>
    <ErrorNotice error={feedback.error} /><ErrorNotice error={create.error} />
    {feedback.data?.submitted ? <><p>Customer rating: <strong>{feedback.data.rating} / 5</strong></p>{feedback.data.comment && <p className="message-body">{feedback.data.comment}</p>}</> : <><p>{feedback.data?.active ? 'A private survey link has been prepared. It is sent only through the approved reply workflow.' : 'Create a private rating link in a reply draft, then review, approve and send it.'}</p><button type="button" className="button button-secondary" disabled={disabled || create.isPending || feedback.isPending || feedback.data?.active} onClick={() => create.mutate()}>{create.isPending ? 'Preparing…' : 'Prepare feedback draft'}</button></>}
    {create.isSuccess && <p role="status" className="notice notice-success">Survey draft prepared. Nothing has been sent.</p>}
  </section>;
}
