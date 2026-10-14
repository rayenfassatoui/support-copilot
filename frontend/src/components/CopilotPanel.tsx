import { useEffect, useState } from 'react';
import { ApiError } from '../api';
import { escalationLabels, formatDate, safeHttpUrl } from '../format';
import type { CopilotRun, TicketStatus } from '../types';
import { IntentBadge, PriorityBadge } from './Badges';
import { SourceDisclosure, SourceLink } from './DocumentContent';
import { ErrorNotice } from './Feedback';

export function CopilotPanel({ run, stale, blocked, blockedReason, busy, analyzing, escalating, onAnalyze, onEscalate, analyzeError, escalateError, status, onReload }: {
  run: CopilotRun | null;
  stale: boolean;
  blocked: boolean;
  blockedReason: string | null;
  busy: boolean;
  analyzing: boolean;
  escalating: boolean;
  onAnalyze: () => void;
  onEscalate: () => void;
  analyzeError: unknown;
  escalateError: unknown;
  status: TicketStatus;
  onReload: () => void;
}) {
  const [copyState, setCopyState] = useState<'idle' | 'copying' | 'copied'>('idle');
  const [copyError, setCopyError] = useState(false);
  useEffect(() => {
    setCopyState('idle');
    setCopyError(false);
  }, [run?.id, stale, blocked]);

  const canCopy = Boolean(run?.grounded && run.response_draft && !stale && !blocked && !busy);
  const copyText = run?.grounded && run.response_draft
    ? `${run.response_draft}\n\nSources\n${run.citations.map((citation, index) => {
      const url = safeHttpUrl(citation.source_url);
      return `[${index + 1}] ${citation.title}\n“${citation.quote}”${url ? `\n${url}` : ''}`;
    }).join('\n\n')}`
    : '';

  async function copyDraft() {
    if (!canCopy || copyState === 'copying') return;
    setCopyState('copying');
    setCopyError(false);
    try {
      if (!navigator.clipboard) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText(copyText);
      setCopyState('copied');
    } catch {
      setCopyState('idle');
      setCopyError(true);
    }
  }

  return (
    <section className="panel copilot-panel" aria-labelledby="copilot-heading" aria-busy={analyzing}>
      <div className="panel-heading">
        <div><p className="eyebrow">AI assistance</p><h2 id="copilot-heading">Support copilot</h2></div>
        <button type="button" className="button" onClick={onAnalyze} disabled={blocked || busy} aria-describedby="analysis-help">{analyzing ? 'Analyzing…' : 'Analyze ticket'}</button>
      </div>
      <p className="field-help" id="analysis-help">{analyzing ? 'Classifying this saved ticket and checking indexed knowledge. Nothing is sent to the customer.' : blockedReason ?? 'Generates a source-grounded draft and escalation recommendation for human review. Nothing is sent automatically.'}</p>
      <ErrorNotice error={analyzeError}>
        {analyzeError instanceof ApiError && analyzeError.code === 'ticket_conflict' && <><p>Your ticket edits are preserved. Reloading replaces them with the latest saved ticket.</p><button type="button" className="button button-secondary button-small" onClick={onReload} disabled={busy}>Reload latest</button></>}
      </ErrorNotice>
      {analyzing && <p className="analysis-pending" role="status"><span className="spinner" aria-hidden="true" />Analyzing saved ticket…</p>}
      {!run && <div className="empty-state compact"><h3>No analysis yet</h3><p>Save the ticket, then analyze it to see intent, priority, supporting sources, and a reply draft.</p><p>AI failures do not prevent ticket editing.</p></div>}
      {run && <div className="analysis-result">
        {stale && <div className="notice notice-warning" role="status"><strong>Ticket changed — analyze again</strong><p>This result describes ticket version {run.ticket_version}. Copy is disabled until a new analysis is saved.</p></div>}
        <div className="badge-row"><IntentBadge intent={run.intent} /><PriorityBadge priority={run.priority} /><span className={`badge ${run.grounded ? 'badge-success' : 'badge-warning'}`}>{run.grounded ? 'Supported by sources' : 'No supported answer'}</span></div>
        <p className="classification-reason">{run.classification_reason}</p>
        <p className="metadata">Analyzed <time dateTime={run.created_at}>{formatDate(run.created_at)}</time> · Version {run.ticket_version} · {run.model}</p>
        <div className={`escalation-box ${run.escalation.recommended ? 'escalation-recommended' : ''}`}>
          <h3>{run.escalation.recommended ? 'Human escalation recommended' : 'No escalation recommended'}</h3>
          {run.escalation.recommended && <>
            <ul>{run.escalation.reasons.map((reason) => <li key={reason}>{escalationLabels[reason]}</li>)}</ul>
            <p className="field-help">This is advice only. Escalating changes the ticket status and records it in history.</p>
            {status === 'escalated'
              ? <p className="already-escalated">Ticket is already escalated.</p>
              : <button type="button" className="button button-warning" onClick={onEscalate} disabled={blocked || busy}>{escalating ? 'Escalating…' : 'Escalate ticket'}</button>}
          </>}
          <ErrorNotice error={escalateError}>
            {escalateError instanceof ApiError && escalateError.code === 'ticket_conflict' && <><p>Your unsaved edits have not been replaced.</p><button type="button" className="button button-secondary button-small" onClick={onReload} disabled={busy}>Reload latest</button></>}
          </ErrorNotice>
        </div>
        {!run.grounded && <div className="notice notice-warning"><strong>No supported answer found — human review required</strong><p>The available sources do not support a customer reply. No reply draft has been generated.</p></div>}
        {run.grounded && run.response_draft && <>
          <div className="section-heading"><h3>Response draft</h3><button type="button" className="button button-secondary button-small" onClick={() => { void copyDraft(); }} disabled={!canCopy || copyState === 'copying'}>{copyState === 'copying' ? 'Copying…' : copyState === 'copied' ? 'Copied with sources' : 'Copy draft'}</button></div>
          <p className="field-help">Review this draft before using it. Copy includes the numbered Sources footer with the verified quotes.</p>
          <div className="reply-draft">{run.response_draft}</div>
          {copyState === 'copied' && <p className="success-text" role="status">Draft and sources copied. No message was sent.</p>}
          {copyError && canCopy && <div className="notice notice-warning" role="alert"><p>Clipboard access is unavailable. Select and copy the complete draft below instead.</p><label htmlFor="manual-copy">Draft and numbered sources</label><textarea id="manual-copy" className="manual-copy" readOnly rows={10} value={copyText} onFocus={(event) => event.currentTarget.select()} /></div>}
          <h3 className="sources-heading">Sources</h3>
          <ol className="source-list">
            {run.citations.map((citation, index) => <li className="source-card" key={citation.chunk_id}>
              <h4><span className="source-number">[{index + 1}]</span> {citation.title}</h4>
              <blockquote>{citation.quote}</blockquote>
              <SourceLink url={citation.source_url} />
              <SourceDisclosure documentId={citation.document_id} number={index + 1} />
            </li>)}
          </ol>
        </>}
      </div>}
    </section>
  );
}
