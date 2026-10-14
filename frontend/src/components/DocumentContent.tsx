import { useId, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronDown, ExternalLink, FileText } from 'lucide-react';
import { api } from '../api';
import { formatDate, safeHttpUrl } from '../format';
import { queryKeys } from '../query';
import type { KnowledgeDocument } from '../types';
import { ErrorNotice, Loading } from './Feedback';
import '../pages/knowledge.css';

export function SourceLink({ url }: { url: string | null }) {
  const href = safeHttpUrl(url);
  return href ? <a href={href} target="_blank" rel="noopener noreferrer" className="source-link">Visit source URL <span className="sr-only">(opens in a new tab)</span><ExternalLink size={14} aria-hidden="true" /></a> : null;
}

export function DocumentContent({ document }: { document: KnowledgeDocument }) {
  return (
    <article className="document-content">
      <header className="document-original-heading">
        <h3>{document.title}</h3>
        <div className="document-original-metadata metadata">
          <span>{document.chunk_count} {document.chunk_count === 1 ? 'chunk' : 'chunks'}</span>
          <span>Revision {document.version}{document.is_current ? ' · current' : ' · archived'}</span>
          <span>Indexed <time dateTime={document.created_at}>{formatDate(document.created_at)}</time></span>
        </div>
        <div className="document-original-reference">
          {safeHttpUrl(document.source_url) ? <SourceLink url={document.source_url} /> : <span className="metadata"><FileText size={14} aria-hidden="true" />Local indexed source</span>}
        </div>
      </header>
      {!document.is_current && <p className="notice notice-warning">Archived revision. This citation preserves the original evidence; new AI analyses use the current knowledge documents.</p>}
      <pre className="plain-document" tabIndex={0} aria-label={`Original text of ${document.title}`}>{document.content}</pre>
    </article>
  );
}

export function SourceDisclosure({ documentId, number }: { documentId: string; number: number }) {
  const contentId = useId();
  const [open, setOpen] = useState(false);
  const document = useQuery({
    queryKey: queryKeys.document(documentId),
    queryFn: ({ signal }) => api.document(documentId, signal),
    enabled: open,
  });
  return (
    <details className="source-disclosure" onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary aria-controls={contentId}><span>Open source <span className="sr-only">{number} — full indexed document</span></span><ChevronDown size={15} aria-hidden="true" /></summary>
      <div className="disclosure-body" id={contentId}>
        {open && document.isPending && <Loading>Loading original source…</Loading>}
        {open && <ErrorNotice error={document.error} onRetry={() => { void document.refetch(); }} retrying={document.isFetching} />}
        {open && document.data && <DocumentContent document={document.data} />}
      </div>
    </details>
  );
}
