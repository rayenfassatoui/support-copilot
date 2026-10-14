import { useState, type FormEvent } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { CheckCheck, MessageSquareHeart } from 'lucide-react';
import { analyticsApi } from '../analytics-api';
import { ErrorNotice, Loading } from '../components/Feedback';
import './operations.css';

export function CustomerFeedbackPage() {
  const [token] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get('token') ?? '');
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState('');
  const link = useQuery({ queryKey: ['public-feedback', token], queryFn: () => analyticsApi.validate(token), enabled: /^[A-Za-z0-9_-]{43}$/.test(token), retry: false, refetchOnWindowFocus: false, gcTime: 0 });
  const submit = useMutation({ mutationFn: () => analyticsApi.submit(token, rating, comment) });
  function send(event: FormEvent) { event.preventDefault(); if (rating && !submit.isPending && !submit.isSuccess) submit.mutate(); }
  return <main className="customer-feedback"><section className="panel feedback-card">
    {submit.isSuccess ? <><CheckCheck size={32} aria-hidden="true" /><h1>Thank you.</h1><p>Your feedback has been recorded. You can close this page.</p></> : <>
      <MessageSquareHeart size={32} aria-hidden="true" /><h1>How did we do?</h1><p>A moment of feedback helps us improve your next support experience.</p>
      {!/^[A-Za-z0-9_-]{43}$/.test(token) ? <p className="notice notice-error">Open the private feedback link from your support email.</p> : link.isPending ? <Loading>Checking your feedback link…</Loading> : <ErrorNotice error={link.error} />}
      {link.data && <form onSubmit={send}><fieldset disabled={submit.isPending}><legend>Rate your support experience</legend><div className="rating-options">{[1, 2, 3, 4, 5].map(value => <label key={value} className={rating === value ? 'selected' : ''}><input type="radio" name="rating" value={value} checked={rating === value} onChange={() => setRating(value)} required /><span>{value}</span></label>)}</div><div className="rating-legend"><span>Very dissatisfied</span><span>Very satisfied</span></div><div className="field"><label htmlFor="feedback-comment">Anything we could improve? <span className="metadata">Optional</span></label><textarea id="feedback-comment" rows={4} maxLength={2000} value={comment} onChange={event => setComment(event.target.value)} /></div><ErrorNotice error={submit.error} /><button className="button" disabled={!rating || submit.isPending}>{submit.isPending ? 'Submitting…' : 'Submit feedback'}</button></fieldset><p className="field-help">One response per link. Please do not include passwords or sensitive information.</p></form>}
    </>}
  </section></main>;
}
