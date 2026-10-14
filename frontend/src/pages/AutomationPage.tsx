import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowDown, ArrowUp, CalendarClock, Plus, Save, Trash2 } from 'lucide-react';
import { api } from '../api';
import { useAuth } from '../auth';
import { automationApi, type AssignmentRule, type BusinessCalendar } from '../automation-api';
import type { Member, Priority } from '../types';
import { PageHeader } from '../components/PageHeader';
import { ErrorNotice, Loading } from '../components/Feedback';
import './operations.css';

const weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
function clock(minutes: number) { return `${String(Math.floor(minutes / 60) % 24).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`; }
function fromClock(value: string) { const [hour, minute] = value.split(':').map(Number); return hour * 60 + minute; }

export function AutomationPage() {
  if (useAuth().member?.role !== 'admin') return <section className="panel"><h1>Administrator access required</h1></section>;
  return <Operations />;
}
function Operations() {
  const client = useQueryClient();
  const calendar = useQuery({ queryKey: ['business-calendar'], queryFn: automationApi.calendar, refetchOnWindowFocus: false });
  const rules = useQuery({ queryKey: ['assignment-rules'], queryFn: automationApi.rules, refetchOnWindowFocus: false });
  const members = useQuery({ queryKey: ['members'], queryFn: api.members, refetchOnWindowFocus: false });
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState(() => new Set<string>());
  const markEditing = useCallback((id: string, value: boolean) => {
    setEditing(current => { if (current.has(id) === value) return current; const next = new Set(current); if (value) next.add(id); else next.delete(id); return next; });
  }, []);
  const reorder = useMutation({ mutationFn: automationApi.orderRules, onSuccess: data => client.setQueryData(['assignment-rules'], data) });
  function move(index: number, direction: number) { if (!rules.data || reorder.isPending || editing.size) return; const next = [...rules.data]; [next[index], next[index + direction]] = [next[index + direction], next[index]]; reorder.mutate(next); }
  return <div className="operations-page"><PageHeader title="Working smarter" description="Predictable routing and service promises that match your team's working day." />
    <ErrorNotice error={calendar.error} onRetry={() => { void calendar.refetch(); }} />{calendar.isPending && <Loading>Loading business calendar…</Loading>}
    {calendar.data && <CalendarEditor key={calendar.data.version} calendar={calendar.data} />}
    <section className="panel"><div className="section-heading"><div><h2>Assignment rules</h2><p className="field-help">First matching enabled rule wins on new tickets. All conditions must match. Manual assignment is never overwritten.</p></div><button className="button button-secondary" disabled={adding || !members.data?.some(member => member.active)} onClick={() => setAdding(true)}><Plus size={16} />Add rule</button></div>
      <ErrorNotice error={rules.error} onRetry={() => { void rules.refetch(); }} /><ErrorNotice error={members.error} /><ErrorNotice error={reorder.error} />
      {rules.isPending && <Loading>Loading routing rules…</Loading>}
      {adding && <RuleEditor members={members.data ?? []} position={(rules.data?.at(-1)?.position ?? -1) + 1} onEditing={markEditing} onClose={() => setAdding(false)} />}
      {editing.size > 0 && <p className="field-help">Save or reset your rule edits before reordering.</p>}
      <div className="rule-list">{rules.data?.map((rule, index) => <div className="rule-row" key={`${rule.id}:${rule.version}`}><div className="rule-position"><span>{index + 1}</span><button className="icon-button" aria-label={`Move ${rule.name} up`} disabled={index === 0 || reorder.isPending || editing.size > 0} onClick={() => move(index, -1)}><ArrowUp size={15} /></button><button className="icon-button" aria-label={`Move ${rule.name} down`} disabled={index === rules.data!.length - 1 || reorder.isPending || editing.size > 0} onClick={() => move(index, 1)}><ArrowDown size={15} /></button></div><RuleEditor rule={rule} members={members.data ?? []} onEditing={markEditing} /></div>)}</div>
      {rules.data?.length === 0 && <p className="muted">No automatic assignment rules. New tickets remain unassigned unless an agent is selected.</p>}
    </section>
  </div>;
}
function CalendarEditor({ calendar }: { calendar: BusinessCalendar }) {
  const client = useQueryClient();
  const [values, setValues] = useState(calendar);
  const [holidays, setHolidays] = useState(calendar.holidays.join('\n'));
  const [opens, setOpens] = useState(clock(calendar.opens_minute));
  const [closes, setCloses] = useState(clock(calendar.closes_minute));
  const save = useMutation({ mutationFn: () => automationApi.saveCalendar({ ...values, opens_minute: fromClock(opens), closes_minute: closes === '00:00' ? 1440 : fromClock(closes), holidays: holidays.split(/\s+/).filter(Boolean) }), onSuccess: async data => { client.setQueryData(['business-calendar'], data); await client.invalidateQueries({ queryKey: ['sla-alerts'] }); } });
  function submit(event: FormEvent) { event.preventDefault(); if (!save.isPending) save.mutate(); }
  return <section className="panel"><div className="section-heading"><h2><CalendarClock size={18} /> Business calendar</h2><span className="badge badge-neutral">{calendar.enabled ? calendar.timezone : '24/7'}</span></div>
    <p className="field-help">Only new tickets and explicit priority changes take a new deadline snapshot. Existing deadlines and reopened tickets keep their original targets. Configured targets count actual working minutes, including daylight-saving transitions.</p>
    <form onSubmit={submit}><fieldset className="form-fields" disabled={save.isPending}><label className="checkbox-label"><input type="checkbox" checked={values.enabled} onChange={event => setValues({ ...values, enabled: event.target.checked })} />Use business hours instead of 24/7</label>
      <div className="operations-form-grid"><div className="field"><label htmlFor="calendar-zone">IANA timezone</label><input id="calendar-zone" value={values.timezone} placeholder="Africa/Tunis" onChange={event => setValues({ ...values, timezone: event.target.value })} required /></div><div className="field"><label htmlFor="calendar-open">Opens</label><input id="calendar-open" type="time" value={opens} onChange={event => setOpens(event.target.value)} required /></div><div className="field"><label htmlFor="calendar-close">Closes · 00:00 means midnight</label><input id="calendar-close" type="time" value={closes} onChange={event => setCloses(event.target.value)} required /></div><div className="field"><label htmlFor="calendar-alert">Alert before deadline · minutes</label><input id="calendar-alert" type="number" min={1} max={10080} value={values.alert_minutes} onChange={event => setValues({ ...values, alert_minutes: Number(event.target.value) })} required /></div></div>
      <div className="weekday-options" role="group" aria-label="Working weekdays">{weekdays.map((day, index) => <label className="checkbox-label" key={day}><input type="checkbox" checked={values.weekdays.includes(index)} onChange={event => setValues({ ...values, weekdays: event.target.checked ? [...values.weekdays, index].sort() : values.weekdays.filter(value => value !== index) })} />{day}</label>)}</div>
      <div className="field"><label htmlFor="calendar-holidays">Holidays · one YYYY-MM-DD date per line</label><textarea id="calendar-holidays" rows={3} value={holidays} onChange={event => setHolidays(event.target.value)} /></div><ErrorNotice error={save.error} />{save.isError && <button type="button" className="button button-secondary" onClick={() => { setValues(calendar); setOpens(clock(calendar.opens_minute)); setCloses(clock(calendar.closes_minute)); setHolidays(calendar.holidays.join('\n')); save.reset(); void client.invalidateQueries({ queryKey: ['business-calendar'] }); }}>Reload saved calendar (discard edits)</button>}<button className="button" disabled={save.isPending || values.weekdays.length === 0}><Save size={16} />{save.isPending ? 'Saving…' : 'Save calendar'}</button></fieldset></form>
  </section>;
}
function RuleEditor({ rule, members, position = 0, onEditing, onClose }: { rule?: AssignmentRule; members: Member[]; position?: number; onEditing: (id: string, value: boolean) => void; onClose?: () => void }) {
  const client = useQueryClient();
  const [values, setValues] = useState<Omit<AssignmentRule, 'id' | 'version'>>(() => rule ? { name: rule.name, enabled: rule.enabled, position: rule.position, priority: rule.priority, customer_domain: rule.customer_domain, subject_contains: rule.subject_contains, assignee_id: rule.assignee_id, catch_all: rule.catch_all } : { name: '', enabled: true, position, priority: null, customer_domain: null, subject_contains: null, assignee_id: members.find(member => member.active)?.agent_id ?? '', catch_all: false });
  const baseline = useRef(values);
  const [edited, setEdited] = useState(false);
  useEffect(() => { const id = rule?.id ?? 'new'; onEditing(id, edited); return () => onEditing(id, false); }, [edited, rule?.id, onEditing]);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const save = useMutation({ mutationFn: () => rule ? automationApi.saveRule({ ...values, id: rule.id, version: rule.version }) : automationApi.createRule(values), onSuccess: async () => { await client.invalidateQueries({ queryKey: ['assignment-rules'] }); onClose?.(); } });
  const remove = useMutation({ mutationFn: () => automationApi.deleteRule(rule!), onSuccess: () => client.invalidateQueries({ queryKey: ['assignment-rules'] }) });
  const busy = save.isPending || remove.isPending;
  return <form className="rule-editor" onChangeCapture={() => setEdited(true)} onSubmit={event => { event.preventDefault(); if (!busy) save.mutate(); }}><fieldset className="form-fields" disabled={busy}>
    <div className="operations-form-grid"><div className="field"><label htmlFor={`rule-name-${rule?.id ?? 'new'}`}>Rule name</label><input id={`rule-name-${rule?.id ?? 'new'}`} value={values.name} onChange={event => setValues({ ...values, name: event.target.value })} required maxLength={100} /></div><div className="field"><label htmlFor={`rule-assignee-${rule?.id ?? 'new'}`}>Assign to</label><select id={`rule-assignee-${rule?.id ?? 'new'}`} value={values.assignee_id} onChange={event => setValues({ ...values, assignee_id: event.target.value })} required><option value="">Select active member</option>{members.filter(member => member.active || member.agent_id === values.assignee_id).map(member => <option value={member.agent_id} key={member.id} disabled={!member.active}>{member.name}{member.active ? '' : ' · inactive'}</option>)}</select></div></div>
    <div className="operations-form-grid"><div className="field"><label htmlFor={`rule-priority-${rule?.id ?? 'new'}`}>Priority</label><select id={`rule-priority-${rule?.id ?? 'new'}`} disabled={values.catch_all} value={values.priority ?? ''} onChange={event => setValues({ ...values, priority: event.target.value as Priority || null })}><option value="">Any priority</option>{['low', 'medium', 'high', 'urgent'].map(priority => <option key={priority}>{priority}</option>)}</select></div><div className="field"><label htmlFor={`rule-domain-${rule?.id ?? 'new'}`}>Customer email domain</label><input id={`rule-domain-${rule?.id ?? 'new'}`} disabled={values.catch_all} value={values.customer_domain ?? ''} onChange={event => setValues({ ...values, customer_domain: event.target.value.trim() || null })} placeholder="example.com" maxLength={253} /></div><div className="field"><label htmlFor={`rule-subject-${rule?.id ?? 'new'}`}>Subject contains</label><input id={`rule-subject-${rule?.id ?? 'new'}`} disabled={values.catch_all} value={values.subject_contains ?? ''} onChange={event => setValues({ ...values, subject_contains: event.target.value || null })} maxLength={200} /></div></div>
    <div className="form-actions"><label className="checkbox-label"><input type="checkbox" checked={values.enabled} onChange={event => setValues({ ...values, enabled: event.target.checked })} />Enabled</label><label className="checkbox-label"><input type="checkbox" checked={values.catch_all} onChange={event => setValues({ ...values, catch_all: event.target.checked, ...(event.target.checked ? { priority: null, customer_domain: null, subject_contains: null } : {}) })} />Match all new tickets</label></div><ErrorNotice error={save.error} /><ErrorNotice error={remove.error} />
    <div className="form-actions"><button className="button button-secondary" disabled={busy}><Save size={15} />{save.isPending ? 'Saving…' : 'Save rule'}</button>{onClose && <button type="button" className="button button-quiet" onClick={onClose}>Cancel</button>}{rule && <button type="button" className="button button-quiet" onClick={() => setConfirmDelete(true)}><Trash2 size={15} />Delete…</button>}</div>
    {rule && edited && <button type="button" className="button button-quiet" onClick={() => { setValues(baseline.current); setEdited(false); }}>Reset edits</button>}
    {confirmDelete && <div className="notice notice-warning"><p>Delete this routing rule? Existing assignments will not change.</p><button type="button" className="button button-secondary" onClick={() => setConfirmDelete(false)}>Keep rule</button> <button type="button" className="button" onClick={() => remove.mutate()}>Confirm delete</button></div>}
  </fieldset></form>;
}
