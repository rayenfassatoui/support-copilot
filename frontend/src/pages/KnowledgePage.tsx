import { useState } from 'react';
import type { FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, api } from '../api';
import { safeHttpUrl } from '../format';
import { queryKeys } from '../query';
import type { FieldErrors } from '../types';
import { DocumentContent } from '../components/DocumentContent';
import { EmptyState, ErrorNotice, FieldError, Loading } from '../components/Feedback';

interface KnowledgeForm {
  title: string;
  source_url: string;
  content: string;
}

export function KnowledgePage() {
  const client = useQueryClient();
  const [values, setValues] = useState<KnowledgeForm>({ title: '', source_url: '', content: '' });
  const [errors, setErrors] = useState<FieldErrors>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [success, setSuccess] = useState('');
  const knowledge = useQuery({ queryKey: queryKeys.knowledge, queryFn: ({ signal }) => api.knowledge(signal) });
  const document = useQuery({
    queryKey: queryKeys.document(selectedId ?? ''),
    queryFn: ({ signal }) => api.document(selectedId!, signal),
    enabled: selectedId !== null,
    staleTime: Infinity,
  });
  const index = useMutation({
    mutationFn: api.createDocument,
    onSuccess: async (created) => {
      client.setQueryData(queryKeys.document(created.id), created);
      setSelectedId(created.id);
      setValues({ title: '', source_url: '', content: '' });
      setErrors({});
      setSuccess(`“${created.title}” was indexed with ${created.chunk_count} ${created.chunk_count === 1 ? 'chunk' : 'chunks'}.`);
      await Promise.all([
        client.invalidateQueries({ queryKey: queryKeys.knowledge }),
        client.invalidateQueries({ queryKey: queryKeys.document(created.id) }),
      ]);
    },
    onError: (error) => { if (error instanceof ApiError) setErrors(error.fields); },
  });

  function changeField(field: keyof KnowledgeForm, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
    setSuccess('');
    setErrors((current) => {
      const next = { ...current };
      delete next[field];
      return next;
    });
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (index.isPending) return;
    const title = values.title.trim();
    const content = values.content.replace(/\r\n/g, '\n').trim();
    const sourceUrl = values.source_url.trim();
    const nextErrors: FieldErrors = {};
    if (title.length < 3 || title.length > 200) nextErrors.title = 'Enter a title with 3–200 characters.';
    if (content.length < 50 || content.length > 20_000) nextErrors.content = 'Enter a body with 50–20,000 characters.';
    if (sourceUrl && !safeHttpUrl(sourceUrl)) nextErrors.source_url = 'Enter a complete HTTP or HTTPS URL, or leave this blank.';
    setErrors(nextErrors);
    setSuccess('');
    index.reset();
    if (Object.keys(nextErrors).length) return;
    index.mutate({ title, content, source_url: sourceUrl || null });
  }

  return (
    <>
      <div className="page-heading"><div><p className="eyebrow">Grounding and evidence</p><h1>Knowledge Base</h1><p>Inspect the original policies used by the copilot, or index a new plain-text document.</p></div></div>
      <div className="knowledge-layout">
        <section className="panel" aria-labelledby="knowledge-create-heading">
          <h2 id="knowledge-create-heading">Index a document</h2>
          <p className="field-help">Documents are immutable after indexing. Use fictional or authorized content only. Source URLs are display metadata and are never fetched.</p>
          <ErrorNotice error={index.error} />
          {Object.keys(errors).length > 0 && !index.error && <div className="notice notice-error" role="alert">Please check the highlighted fields.</div>}
          {success && <p className="notice notice-success" role="status">{success}</p>}
          <form onSubmit={submit} noValidate aria-busy={index.isPending}>
            <fieldset className="form-fields" disabled={index.isPending}>
              <legend className="sr-only">Knowledge document</legend>
              <div className="field"><label htmlFor="knowledge-title">Title <span className="required-text">(required)</span></label><input id="knowledge-title" name="title" value={values.title} onChange={(event) => changeField('title', event.target.value)} required minLength={3} maxLength={200} aria-invalid={Boolean(errors.title)} aria-describedby={errors.title ? 'knowledge-title-error' : undefined} /><FieldError id="knowledge-title-error" message={errors.title} /></div>
              <div className="field"><label htmlFor="knowledge-url">Source URL <span className="required-text">(optional)</span></label><input id="knowledge-url" name="source_url" type="url" placeholder="https://example.com/policy" value={values.source_url} onChange={(event) => changeField('source_url', event.target.value)} aria-invalid={Boolean(errors.source_url)} aria-describedby={`knowledge-url-help${errors.source_url ? ' knowledge-url-error' : ''}`} /><p className="field-help" id="knowledge-url-help">HTTP(S) only. Leave blank for a local indexed source.</p><FieldError id="knowledge-url-error" message={errors.source_url} /></div>
              <div className="field"><label htmlFor="knowledge-content">Document body <span className="required-text">(required)</span></label><textarea id="knowledge-content" name="content" rows={14} required minLength={50} maxLength={20_000} value={values.content} onChange={(event) => changeField('content', event.target.value)} aria-invalid={Boolean(errors.content)} aria-describedby={`knowledge-content-help${errors.content ? ' knowledge-content-error' : ''}`} /><p className="field-help" id="knowledge-content-help">50–20,000 characters. Plain text and Markdown are displayed as text, not executed.</p><FieldError id="knowledge-content-error" message={errors.content} /></div>
            </fieldset>
            <div className="form-actions"><button type="submit" className="button" disabled={index.isPending}>{index.isPending ? 'Indexing knowledge…' : 'Index knowledge'}</button></div>
            {index.isPending && <p className="field-help" role="status">Indexing knowledge. Validating embeddings before saving the document and its chunks.</p>}
          </form>
        </section>
        <div className="panel-stack">
          <section className="panel" aria-labelledby="knowledge-list-heading">
            <div className="panel-heading"><h2 id="knowledge-list-heading">Indexed documents</h2><button type="button" className="button button-secondary button-small" onClick={() => { void knowledge.refetch(); }} disabled={knowledge.isFetching}>{knowledge.isFetching && !knowledge.isPending ? 'Refreshing…' : 'Refresh list'}</button></div>
            <ErrorNotice error={knowledge.error} onRetry={() => { void knowledge.refetch(); }} retrying={knowledge.isFetching} />
            {knowledge.isPending && <Loading>Loading knowledge…</Loading>}
            {knowledge.data?.length === 0 && <EmptyState title="No knowledge indexed"><p>Add a document here, or ask the demo operator to seed the fictional AcmeCloud policies. Without supporting knowledge, the copilot will not draft a customer answer.</p></EmptyState>}
            {knowledge.data && knowledge.data.length > 0 && <ul className="document-list">{knowledge.data.map((item) => <li key={item.id}><button type="button" className={`document-select ${selectedId === item.id ? 'selected' : ''}`} aria-pressed={selectedId === item.id} onClick={() => setSelectedId(item.id)} aria-controls="document-inspector"><strong>{item.title}</strong><span className="metadata">{item.chunk_count} {item.chunk_count === 1 ? 'chunk' : 'chunks'} · {item.source_url ? 'Source URL available' : 'Local indexed source'}</span></button></li>)}</ul>}
          </section>
          <section className="panel" id="document-inspector" aria-labelledby="knowledge-inspector-heading">
            <h2 id="knowledge-inspector-heading">Original document</h2>
            {!selectedId && <p className="muted">Select an indexed document to inspect its full original text.</p>}
            {selectedId && document.isPending && <Loading>Loading original document…</Loading>}
            {selectedId && <ErrorNotice error={document.error} onRetry={() => { void document.refetch(); }} retrying={document.isFetching} />}
            {selectedId && document.data && <DocumentContent document={document.data} />}
          </section>
        </div>
      </div>
    </>
  );
}
