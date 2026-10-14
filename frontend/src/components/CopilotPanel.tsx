import { useEffect, useState } from 'react';
import { BookOpen, Check, CheckCircle2, ChevronDown, ClipboardCopy, Clock3, CornerUpRight, MessageSquareText, RotateCcw, ShieldAlert, ShieldCheck, Sparkles } from 'lucide-react';
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
      <header className="copilot-workspace-header">
        <div className="copilot-workspace-heading">
          <div className="copilot-title">
            <span className="copilot-mark"><Sparkles size={20} aria-hidden="true" /></span>
            <div><p className="eyebrow">AI workspace</p><h2 id="copilot-heading">Support copilot</h2></div>
          </div>
          <button type="button" className="button copilot-analyze-button" onClick={onAnalyze} disabled={blocked || busy} aria-describedby="analysis-help">
            {analyzing ? <span className="spinner" aria-hidden="true" /> : <Sparkles size={16} aria-hidden="true" />}
            {analyzing ? 'Analyzing…' : 'Analyze ticket'}
          </button>
        </div>
        <p className="field-help" id="analysis-help">{analyzing ? 'Classifying this saved ticket and checking indexed knowledge. Nothing is sent to the customer.' : blockedReason ?? 'A source-grounded draft and a recommended next step, for your review. Nothing is sent automatically.'}</p>
      </header>

      {(Boolean(analyzeError) || analyzing) && (
        <div className="copilot-feedback">
          <ErrorNotice error={analyzeError}>
            {run && <p>Your preceding analysis remains below.</p>}
            {analyzeError instanceof ApiError && analyzeError.code === 'ticket_conflict' && <>
              <p>Your ticket edits are preserved. Reloading replaces them with the latest saved ticket.</p>
              <button type="button" className="button button-secondary button-small" onClick={onReload} disabled={busy}><RotateCcw size={15} aria-hidden="true" />Reload latest</button>
            </>}
          </ErrorNotice>
          {analyzing && (
            <div className="copilot-pending-state" role="status">
              <span className="spinner" aria-hidden="true" />
              <div><strong>Analyzing saved ticket…</strong><p>{run ? 'Your previous result stays visible while a new analysis is prepared.' : 'Checking the request against the indexed knowledge base.'}</p></div>
            </div>
          )}
        </div>
      )}

      {!run && !analyzing && (
        <div className="copilot-empty-state">
          <span className="copilot-empty-mark"><MessageSquareText size={28} aria-hidden="true" /></span>
          <h3>No analysis yet</h3>
          <p>Analyze the saved ticket to understand the request, review a supported reply, and see whether human escalation is needed.</p>
          <div className="copilot-empty-capabilities" aria-label="Copilot analysis includes">
            <span><Check size={14} aria-hidden="true" />Intent and priority</span>
            <span><BookOpen size={14} aria-hidden="true" />Verified sources</span>
            <span><ShieldCheck size={14} aria-hidden="true" />Human review</span>
          </div>
          <p className="copilot-empty-note">AI failures do not prevent ticket editing.</p>
        </div>
      )}

      {run && (
        <div className="copilot-result">
          {stale && (
            <div className="copilot-stale-state">
              <div className="notice notice-warning" role="status">
                <strong>Ticket changed — analyze again</strong>
                <p>This result describes ticket version {run.ticket_version}. Copy is disabled until a new analysis is saved.</p>
              </div>
            </div>
          )}

          <section className="copilot-section copilot-classification" aria-labelledby="copilot-classification-heading">
            <div className="copilot-section-heading">
              <h3 id="copilot-classification-heading">Classification</h3>
              <span className={`badge ${run.grounded ? 'badge-success' : 'badge-warning'}`}>
                {run.grounded ? <CheckCircle2 size={13} aria-hidden="true" /> : <ShieldAlert size={13} aria-hidden="true" />}
                {run.grounded ? 'Supported by sources' : 'No supported answer'}
              </span>
            </div>
            <dl className="copilot-classification-grid">
              <div><dt>Intent</dt><dd><IntentBadge intent={run.intent} /></dd></div>
              <div><dt>Priority</dt><dd><PriorityBadge priority={run.priority} /></dd></div>
            </dl>
            <p className="classification-reason">{run.classification_reason}</p>
            <details className="copilot-run-details">
              <summary><span><Clock3 size={14} aria-hidden="true" />Analysis details</span><ChevronDown size={15} aria-hidden="true" /></summary>
              <dl>
                <div><dt>Analyzed</dt><dd><time dateTime={run.created_at}>{formatDate(run.created_at)}</time></dd></div>
                <div><dt>Ticket version</dt><dd>{run.ticket_version}</dd></div>
                <div><dt>Model</dt><dd><code>{run.model}</code></dd></div>
              </dl>
            </details>
          </section>

          {!run.grounded && (
            <section className="copilot-section copilot-abstention" aria-labelledby="copilot-abstention-heading" role="status">
              <div className="copilot-abstention-heading"><ShieldAlert size={21} aria-hidden="true" /><h3 id="copilot-abstention-heading">No supported answer found — human review required</h3></div>
              <p>The available sources do not support a customer reply. No reply draft has been generated.</p>
            </section>
          )}

          {run.grounded && run.response_draft && (
            <>
              <section className="copilot-section copilot-draft-section" aria-labelledby="copilot-draft-heading">
                <div className="copilot-section-heading">
                  <h3 id="copilot-draft-heading"><MessageSquareText size={17} aria-hidden="true" />Response draft</h3>
                  <button type="button" className="button button-secondary button-small" onClick={() => { void copyDraft(); }} disabled={!canCopy || copyState === 'copying'} aria-describedby="copilot-copy-help">
                    {copyState === 'copying' ? <span className="spinner" aria-hidden="true" /> : copyState === 'copied' ? <Check size={15} aria-hidden="true" /> : <ClipboardCopy size={15} aria-hidden="true" />}
                    {copyState === 'copying' ? 'Copying…' : copyState === 'copied' ? 'Copied with sources' : 'Copy draft'}
                  </button>
                </div>
                <p className="field-help" id="copilot-copy-help">Review before using. Copy includes a numbered Sources footer with the verified quotes.{blocked && ' Save or discard your edits before copying.'}{stale && ' This draft is outdated; analyze the ticket again first.'}</p>
                <div className="reply-draft">{run.response_draft}</div>
                {copyState === 'copied' && <p className="success-text copilot-copy-success" role="status"><CheckCircle2 size={15} aria-hidden="true" />Draft and sources copied. No message was sent.</p>}
                {copyError && canCopy && (
                  <div className="notice notice-warning copilot-manual-copy" role="alert">
                    <p>Clipboard access is unavailable. Select and copy the complete draft below instead.</p>
                    <label htmlFor="manual-copy">Draft and numbered sources</label>
                    <textarea id="manual-copy" className="manual-copy" readOnly rows={10} value={copyText} onFocus={(event) => event.currentTarget.select()} />
                  </div>
                )}
              </section>

              <section className="copilot-section copilot-sources-section" aria-labelledby="copilot-sources-heading">
                <div className="copilot-section-heading">
                  <h3 id="copilot-sources-heading"><BookOpen size={17} aria-hidden="true" />Sources</h3>
                  <span className="metadata">{run.citations.length} cited {run.citations.length === 1 ? 'source' : 'sources'}</span>
                </div>
                <p className="field-help">Verified excerpts from your knowledge base. Open an original document to review its full context.</p>
                <ol className="source-list">
                  {run.citations.map((citation, index) => (
                    <li className="source-card" key={citation.chunk_id}>
                      <div className="copilot-source-heading"><span className="source-number">[{index + 1}]</span><h4>{citation.title}</h4></div>
                      <blockquote>{citation.quote}</blockquote>
                      <SourceLink url={citation.source_url} />
                      <SourceDisclosure documentId={citation.document_id} number={index + 1} />
                    </li>
                  ))}
                </ol>
              </section>
            </>
          )}

          <section className={`copilot-section copilot-escalation-section${run.escalation.recommended ? ' copilot-escalation-recommended' : ''}`} aria-labelledby="copilot-escalation-heading" aria-busy={escalating}>
            <div className="copilot-section-heading">
              <h3 id="copilot-escalation-heading">
                {run.escalation.recommended ? <ShieldAlert size={18} aria-hidden="true" /> : <ShieldCheck size={18} aria-hidden="true" />}
                {run.escalation.recommended ? 'Human escalation recommended' : 'No escalation recommended'}
              </h3>
            </div>
            {run.escalation.recommended ? (
              <>
                <ul className="copilot-escalation-reasons">{run.escalation.reasons.map((reason) => <li key={reason}>{escalationLabels[reason]}</li>)}</ul>
                <p className="field-help" id="copilot-escalation-help">This is advice only. Escalating changes the ticket status and records it in history.</p>
                {status === 'escalated' ? (
                  <p className="copilot-already-escalated" role="status"><CheckCircle2 size={17} aria-hidden="true" />Ticket is already escalated.</p>
                ) : (
                  <button type="button" className="button button-warning" onClick={onEscalate} disabled={blocked || busy} aria-describedby="copilot-escalation-help"><CornerUpRight size={16} aria-hidden="true" />{escalating ? 'Escalating…' : 'Escalate ticket'}</button>
                )}
              </>
            ) : (
              <p className="field-help">No escalation was suggested for this analysis. You can still change the ticket status in the editor.</p>
            )}
            <ErrorNotice error={escalateError}>
              {escalateError instanceof ApiError && escalateError.code === 'ticket_conflict' && <>
                <p>Your unsaved edits have not been replaced.</p>
                <button type="button" className="button button-secondary button-small" onClick={onReload} disabled={busy}><RotateCcw size={15} aria-hidden="true" />Reload latest</button>
              </>}
            </ErrorNotice>
          </section>
        </div>
      )}
    </section>
  );
}
