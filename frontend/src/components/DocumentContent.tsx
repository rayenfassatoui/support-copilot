import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api';
import { formatDate, safeHttpUrl } from '../format';
import { queryKeys } from '../query';
import type { KnowledgeDocument } from '../types';
import { ErrorNotice, Loading } from './Feedback';

export function SourceLink({ url }: { url: string | null }) {
  const href = safeHttpUrl(url);
  return href ? <a href={href} target="_blank" rel="noopener noreferrer" className="source-link">Visit source URL <span className="sr-only">(opens in a new tab)</span><span aria-hidden="true">↗</span></a> : null;
}

export function DocumentContent({ document }: { document: KnowledgeDocument }) {
  return (
    <article className="document-content">
      <h3>{document.title}</h3>
      <p className="metadata">{document.chunk_count} {document.chunk_count === 1 ? 'chunk' : 'chunks'} · Indexed <time dateTime={document.created_at}>{formatDate(document.created_at)}</time></p>
      <SourceLink url={document.source_url} />
      <pre className="plain-document" tabIndex={0} aria-label={`Original text of ${document.title}`}>{document.content}</pre>
    </article>
  );
}

export function SourceDisclosure({ documentId, number }: { documentId: string; number: number }) {
  const [open, setOpen] = useState(false);
  const document = useQuery({
    queryKey: queryKeys.document(documentId),
    queryFn: ({ signal }) => api.document(documentId, signal),
    enabled: open,
    staleTime: Infinity,
  });
  return (
    <details className="source-disclosure" onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>Open source <span className="sr-only">{number} — full indexed document</span></summary>
      <div className="disclosure-body">
        {open && document.isPending && <Loading>Loading original source…</Loading>}
        <ErrorNotice error={document.error} onRetry={() => { void document.refetch(); }} retrying={document.isFetching} />
        {document.data && <DocumentContent document={document.data} />}
      </div>
    </details>
  );
}
