import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, RefreshCw, Save, ShieldCheck } from 'lucide-react';
import { api } from '../api';
import { useAuth } from '../auth';
import type { Member, SlaPolicy } from '../types';
import { PageHeader } from '../components/PageHeader';
import { ErrorNotice, Loading } from '../components/Feedback';
import './workspace.css';

export function SettingsPage() {
  const { member } = useAuth();
  if (member?.role !== 'admin') return <section className="panel"><h1>Administrator access required</h1><p>Your account can manage tickets, conversations and replies. Team access and SLA policies are administrator-only.</p></section>;
  return <AdminSettings />;
}

function AdminSettings() {
  const client = useQueryClient();
  const members = useQuery({ queryKey: ['members'], queryFn: api.members, refetchOnWindowFocus: false });
  const policies = useQuery({ queryKey: ['sla-policies'], queryFn: api.policies, refetchOnWindowFocus: false });
  const [memberReload, setMemberReload] = useState(0);
  const [policyReload, setPolicyReload] = useState(0);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<Member['role']>('agent');
  const add = useMutation({ mutationFn: api.createMember, onSuccess: async () => { setName(''); setEmail(''); setRole('agent'); await Promise.all([client.invalidateQueries({ queryKey: ['members'] }), client.invalidateQueries({ queryKey: ['agents'] })]); } });
  function submit(event: FormEvent) { event.preventDefault(); if (!add.isPending) add.mutate({ name: name.trim(), email: email.trim(), role }); }
  return <>
    <PageHeader title="Workspace settings" description="Manage who can work here, and the service targets your team owns." />
    <div className="settings-layout">
      <section className="panel" aria-labelledby="team-heading"><div className="section-heading"><h2 id="team-heading"><ShieldCheck size={18} aria-hidden="true" /> Team access</h2><button className="button button-secondary button-small" onClick={() => { void members.refetch().then(result => { if (result.isSuccess) setMemberReload(value => value + 1); }); }} disabled={members.isFetching}><RefreshCw size={14} aria-hidden="true" />Reload (discard edits)</button></div>
        <p className="settings-intro">Authorize an email, then ask its owner to create an account and verify it. Agents handle tickets and replies; admins also manage knowledge, members and SLA policies. Disabling a member blocks their next API request.</p>
        <ErrorNotice error={members.error} />{members.isPending && <Loading>Loading members…</Loading>}
        <div className="settings-member-list">{members.data?.map(member => <MemberEditor key={`${member.id}:${member.version}:${memberReload}`} member={member} />)}</div>
        <h3 style={{ marginTop: 28 }}>Authorize a team member</h3><ErrorNotice error={add.error} />{add.isSuccess && <p className="notice notice-success" role="status">Email authorized. No invitation email was sent; share the app address with the member.</p>}
        <form className="member-add" onSubmit={submit}>
          <div className="field"><label htmlFor="member-name">Name</label><input id="member-name" value={name} onChange={event => setName(event.target.value)} maxLength={200} required disabled={add.isPending} /></div>
          <div className="field"><label htmlFor="member-email">Email</label><input id="member-email" type="email" value={email} onChange={event => setEmail(event.target.value)} required disabled={add.isPending} /></div>
          <div className="field"><label htmlFor="member-role">Role</label><select id="member-role" value={role} onChange={event => setRole(event.target.value as Member['role'])} disabled={add.isPending}><option value="agent">Agent</option><option value="admin">Admin</option></select></div>
          <button className="button" disabled={add.isPending}><Plus size={16} aria-hidden="true" />{add.isPending ? 'Adding…' : 'Authorize email'}</button>
        </form>
      </section>
      <section className="panel" aria-labelledby="sla-heading"><div className="section-heading"><h2 id="sla-heading">Service targets</h2><button className="button button-secondary button-small" onClick={() => { void policies.refetch().then(result => { if (result.isSuccess) setPolicyReload(value => value + 1); }); }} disabled={policies.isFetching}><RefreshCw size={14} aria-hidden="true" />Reload (discard edits)</button></div>
        <p className="settings-intro">Elapsed time, 24/7. First response is recorded only after SMTP accepts an approved reply; notes and drafts do not stop the clock. Changes apply to new tickets and explicit priority changes, not existing deadlines. Reopening retains the original deadlines.</p>
        <ErrorNotice error={policies.error} />{policies.isPending && <Loading>Loading service targets…</Loading>}
        <div className="settings-policy-list">{policies.data?.map(policy => <PolicyEditor key={`${policy.priority}:${policy.version}:${policyReload}`} policy={policy} />)}</div>
      </section>
    </div>
  </>;
}

function MemberEditor({ member }: { member: Member }) {
  const client = useQueryClient();
  const auth = useAuth();
  const [role, setRole] = useState(member.role);
  const [active, setActive] = useState(member.active);
  const save = useMutation({ mutationFn: () => api.patchMember(member.id, { version: member.version, role, active }), onSuccess: async () => { await client.invalidateQueries({ queryKey: ['members'] }); if (auth.member?.id === member.id) await auth.refresh(); } });
  const dirty = role !== member.role || active !== member.active;
  return <form className="member-row" onSubmit={event => { event.preventDefault(); if (dirty && !save.isPending) save.mutate(); }}>
    <div className="member-fields"><div className="member-identity"><strong>{member.name}</strong><span>{member.email}</span><span>{member.registered ? 'Account linked' : 'Awaiting verified sign-in'}</span></div>
      <div className="field"><label htmlFor={`role-${member.id}`}>Role</label><select id={`role-${member.id}`} value={role} onChange={event => setRole(event.target.value as Member['role'])} disabled={save.isPending}><option value="agent">Agent</option><option value="admin">Admin</option></select></div>
      <label className="checkbox-label"><input type="checkbox" checked={active} onChange={event => setActive(event.target.checked)} disabled={save.isPending} />Active</label>
      <button className="button button-secondary" disabled={!dirty || save.isPending}><Save size={15} aria-hidden="true" />{save.isPending ? 'Saving…' : 'Save access'}</button></div>
    <ErrorNotice error={save.error} />
  </form>;
}

function PolicyEditor({ policy }: { policy: SlaPolicy }) {
  const client = useQueryClient();
  const [response, setResponse] = useState(String(policy.first_response_minutes));
  const [resolution, setResolution] = useState(String(policy.resolution_minutes));
  const save = useMutation({ mutationFn: () => api.patchPolicy(policy.priority, { version: policy.version, first_response_minutes: Number(response), resolution_minutes: Number(resolution) }), onSuccess: () => client.invalidateQueries({ queryKey: ['sla-policies'] }) });
  const dirty = Number(response) !== policy.first_response_minutes || Number(resolution) !== policy.resolution_minutes;
  return <form className="policy-row" onSubmit={event => { event.preventDefault(); if (dirty && !save.isPending) save.mutate(); }}>
    <div className="policy-fields"><h3>{policy.priority}</h3>
      <div className="field"><label htmlFor={`response-${policy.priority}`}>First response · minutes</label><input id={`response-${policy.priority}`} type="number" min={1} max={525600} step={1} value={response} onChange={event => setResponse(event.target.value)} required disabled={save.isPending} /></div>
      <div className="field"><label htmlFor={`resolution-${policy.priority}`}>Resolution · minutes</label><input id={`resolution-${policy.priority}`} type="number" min={Number(response) || 1} max={525600} step={1} value={resolution} onChange={event => setResolution(event.target.value)} required disabled={save.isPending} /></div>
      <button className="button button-secondary" disabled={!dirty || save.isPending}><Save size={15} aria-hidden="true" />{save.isPending ? 'Saving…' : 'Save target'}</button></div>
    <ErrorNotice error={save.error} />
  </form>;
}
