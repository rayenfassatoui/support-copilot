import { useState, type FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { BarChart3 } from 'lucide-react';
import { analyticsApi, type TimeMetric } from '../analytics-api';
import { PageHeader } from '../components/PageHeader';
import { ErrorNotice, Loading } from '../components/Feedback';
import './operations.css';

function minutes(value: number | null): string { return value === null ? 'No completed targets' : value < 60 ? `${value.toFixed(1)} min` : `${(value / 60).toFixed(1)} h`; }
function TargetMetric({ title, value }: { title: string; value: TimeMetric }) {
  return <section className="panel metric-card"><h2>{title}</h2><strong className="metric-value">{minutes(value.average_minutes)}</strong><p>{value.completed} completed · {value.outstanding} outstanding</p><dl className="metric-breakdown"><div><dt>SLA compliance</dt><dd>{value.sla_percent === null ? 'Not yet measurable' : `${value.sla_percent.toFixed(1)}%`}</dd></div><div><dt>Met / breached / pending</dt><dd>{value.sla_met} / {value.sla_breached} / {value.sla_pending}</dd></div></dl></section>;
}
export function AnalyticsPage() {
  const [range, setRange] = useState(() => { const end = new Date(); end.setUTCDate(end.getUTCDate() + 1); const start = new Date(end); start.setUTCDate(start.getUTCDate() - 30); return { start: start.toISOString().slice(0, 10), end: end.toISOString().slice(0, 10) }; });
  const [draft, setDraft] = useState(range);
  const report = useQuery({ queryKey: ['analytics', range], queryFn: ({ signal }) => analyticsApi.report(range.start, range.end, signal), refetchOnWindowFocus: false });
  function submit(event: FormEvent) { event.preventDefault(); setRange({ ...draft }); }
  const data = report.data;
  return <div className="operations-page"><PageHeader title="Service insights" description="Response speed, promises kept, and the customer's own verdict." />
    <form className="panel report-range" onSubmit={submit}><div className="field"><label htmlFor="report-start">Created from · UTC</label><input id="report-start" type="date" value={draft.start} onChange={e => setDraft({ ...draft, start: e.target.value })} required /></div><div className="field"><label htmlFor="report-end">Before · UTC, exclusive</label><input id="report-end" type="date" value={draft.end} onChange={e => setDraft({ ...draft, end: e.target.value })} required /></div><button className="button" disabled={report.isFetching}><BarChart3 size={16} />Apply range</button></form>
    <ErrorNotice error={report.error} onRetry={() => { void report.refetch(); }} />{report.isPending && <Loading>Calculating service metrics…</Loading>}
    {data && <><p className="metadata">{data.tickets} tickets created in this range. Outcomes are current; averages use elapsed time and exclude unfinished targets. Pending SLA targets are excluded from compliance until completed or overdue.</p>
      <div className="metrics-grid"><TargetMetric title="First response" value={data.first_response} /><TargetMetric title="Resolution" value={data.resolution} /><section className="panel metric-card"><h2>Customer satisfaction</h2><strong className="metric-value">{data.feedback.average_rating === null ? 'No ratings yet' : `${data.feedback.average_rating.toFixed(1)} / 5`}</strong><p>{data.feedback.submitted} responses / {data.feedback.requested} surveys requested in this range</p><dl className="metric-breakdown"><div><dt>Satisfied · ratings 4–5</dt><dd>{data.feedback.satisfied_percent === null ? '—' : `${data.feedback.satisfied_percent.toFixed(1)}%`}</dd></div><div><dt>Survey response rate</dt><dd>{data.feedback.response_percent === null ? '—' : `${data.feedback.response_percent.toFixed(1)}%`}</dd></div></dl></section></div>
      <p className="field-help">Satisfaction counts one survey per ticket, grouped by its latest request date. A replacement link moves an unanswered survey into the new request cohort.</p>
      <section className="panel"><h2>Daily ticket cohorts</h2><p className="field-help">Each row groups tickets by their UTC creation date, not the day they were answered. Resolution uses the current resolved state; reopened tickets are outstanding.</p><div className="data-table-scroll"><table className="data-table"><thead><tr><th scope="col">Day · UTC</th><th scope="col">Tickets</th><th scope="col">Avg first response</th><th scope="col">Avg resolution</th></tr></thead><tbody>{data.daily.map(day => <tr key={day.day}><td>{day.day}</td><td>{day.tickets}</td><td>{minutes(day.first_response_minutes)}</td><td>{minutes(day.resolution_minutes)}</td></tr>)}</tbody></table></div></section>
    </>}
  </div>;
}
