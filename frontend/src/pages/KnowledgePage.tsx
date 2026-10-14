import { useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Dialog } from '@base-ui/react/dialog';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BookOpen, ChevronRight, FileText, Library, Plus, RefreshCw, Search, X } from 'lucide-react';
import { ApiError, api } from '../api';
import { safeHttpUrl } from '../format';
import { queryKeys } from '../query';
import type { FieldErrors } from '../types';
import { DocumentContent } from '../components/DocumentContent';
import { EmptyState, ErrorNotice, FieldError, Loading } from '../components/Feedback';
import { PageHeader } from '../components/PageHeader';
import './knowledge.css';

interface KnowledgeForm {
  title: string;
  source_url: string;
  content: string;
}

export function KnowledgePage() {
  const client = useQueryClient();
  const addDocumentRef = useRef<HTMLButtonElement | null>(null);
  const [values, setValues] = useState<KnowledgeForm>({ title: '', source_url: '', content: '' });
  const [errors, setErrors] = useState<FieldErrors>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [search, setSearch] = useState('');
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
      setSearch('');
      setValues({ title: '', source_url: '', content: '' });
      setErrors({});
      setDialogOpen(false);
      setSuccess(`“${created.title}” was indexed with ${created.chunk_count} ${created.chunk_count === 1 ? 'chunk' : 'chunks'}.`);
      await Promise.all([
        client.invalidateQueries({ queryKey: queryKeys.knowledge }),
        client.invalidateQueries({ queryKey: queryKeys.document(created.id) }),
      ]);
    },
    onError: (error) => { if (error instanceof ApiError) setErrors(error.fields); },
  });
  const documents = knowledge.data;
  const searchTerm = search.trim().toLocaleLowerCase();
  const filteredDocuments = documents?.filter((item) => item.title.toLocaleLowerCase().includes(searchTerm));
  const chunkCount = documents?.reduce((total, item) => total + item.chunk_count, 0);

  function changeField(field: keyof KnowledgeForm, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
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
    const firstInvalidField = Object.keys(nextErrors)[0];
    if (firstInvalidField) {
      const control = event.currentTarget.elements.namedItem(firstInvalidField);
      if (control instanceof HTMLElement) control.focus();
      return;
    }
    index.mutate({ title, content, source_url: sourceUrl || null });
  }

  return (
    <Dialog.Root open={dialogOpen} onOpenChange={setDialogOpen}>
      <div className="knowledge-page">
        <PageHeader
          title="Knowledge base"
          description="The original sources behind every supported answer."
          actions={<Dialog.Trigger ref={addDocumentRef} type="button" className="button"><Plus size={17} aria-hidden="true" />Add document</Dialog.Trigger>}
        />
        {success && <p className="notice notice-success" role="status">{success}</p>}
        {!dialogOpen && index.isPending && <Loading>Indexing knowledge… You can continue browsing.</Loading>}
        {!dialogOpen && index.error && <ErrorNotice error={index.error}><button type="button" className="button button-secondary button-small" onClick={() => setDialogOpen(true)}>Return to document</button></ErrorNotice>}

        <div className="knowledge-workspace">
          <section className="knowledge-library" aria-labelledby="knowledge-list-heading">
            <div className="knowledge-library-heading">
              <div><h2 id="knowledge-list-heading">Document library</h2><p className="metadata">{documents ? `${documents.length} ${documents.length === 1 ? 'document' : 'documents'} · ${chunkCount} indexed ${chunkCount === 1 ? 'chunk' : 'chunks'}` : 'Your indexed sources'}</p></div>
              <button type="button" className="icon-button knowledge-refresh" aria-label="Refresh document list" onClick={() => { void knowledge.refetch(); }} disabled={knowledge.isFetching}><RefreshCw size={17} aria-hidden="true" /></button>
            </div>
            <div className="knowledge-search">
              <label className="sr-only" htmlFor="knowledge-search">Filter document titles</label>
              <Search size={17} aria-hidden="true" />
              <input id="knowledge-search" type="search" placeholder="Find a document…" value={search} onChange={(event) => setSearch(event.target.value)} aria-describedby="knowledge-search-help" />
              <span className="sr-only" id="knowledge-search-help">Filters this library by document title only.</span>
            </div>
            <div className="knowledge-library-feedback">
              <ErrorNotice error={knowledge.error} onRetry={() => { void knowledge.refetch(); }} retrying={knowledge.isFetching} />
              {knowledge.isPending && <Loading>Loading knowledge…</Loading>}
              {knowledge.isFetching && !knowledge.isPending && <p className="metadata" role="status">Refreshing document list…</p>}
              {documents?.length === 0 && <EmptyState title="Your library starts here"><p>Add your first document, or ask the demo operator to seed the fictional AcmeCloud policies. Without supporting sources, the copilot will not draft an answer.</p><button type="button" className="button button-secondary" onClick={() => setDialogOpen(true)}><Plus size={16} aria-hidden="true" />Add a document</button></EmptyState>}
              {documents && documents.length > 0 && filteredDocuments?.length === 0 && <EmptyState title="No matching documents"><p>Try another title. This filter searches document titles, not their contents.</p><button type="button" className="button button-quiet" onClick={() => setSearch('')}>Clear filter</button></EmptyState>}
            </div>
            {filteredDocuments && filteredDocuments.length > 0 && (
              <>
                {searchTerm && <p className="knowledge-filter-count metadata" role="status">{filteredDocuments.length} of {documents?.length} documents</p>}
                <ul className="knowledge-document-list">
                  {filteredDocuments.map((item) => (
                    <li key={item.id}>
                      <button type="button" className={`knowledge-document-select${selectedId === item.id ? ' is-selected' : ''}`} aria-pressed={selectedId === item.id} onClick={() => setSelectedId(item.id)} aria-controls="document-inspector">
                        <span className="knowledge-document-icon"><FileText size={18} aria-hidden="true" /></span>
                        <span className="knowledge-document-summary"><strong>{item.title}</strong><span className="metadata">{item.chunk_count} {item.chunk_count === 1 ? 'chunk' : 'chunks'} · {safeHttpUrl(item.source_url) ? 'Linked source' : 'Local source'}</span></span>
                        <ChevronRight size={15} className="knowledge-document-chevron" aria-hidden="true" />
                      </button>
                    </li>
                  ))}
                </ul>
              </>
            )}
            <p className="knowledge-library-note"><Library size={15} aria-hidden="true" /><span>Original documents stay unchanged after indexing.</span></p>
          </section>

          <section className="knowledge-reader" id="document-inspector" aria-labelledby="knowledge-inspector-heading">
            <div className="knowledge-reader-heading"><BookOpen size={16} aria-hidden="true" /><h2 id="knowledge-inspector-heading">Original document</h2><span className="metadata">Read only</span></div>
            {!selectedId && <div className="knowledge-reader-empty"><span className="knowledge-reader-empty-icon"><BookOpen size={27} aria-hidden="true" /></span><h3>Read the source, not just the answer</h3><p>Select a document to inspect its complete original text and the source used by the copilot.</p></div>}
            {selectedId && <div className="knowledge-reader-body">
              {document.isPending && <Loading>Loading original document…</Loading>}
              <ErrorNotice error={document.error} onRetry={() => { void document.refetch(); }} retrying={document.isFetching} />
              {document.data && <DocumentContent document={document.data} />}
            </div>}
          </section>
        </div>
      </div>

      <Dialog.Portal>
        <Dialog.Backdrop className="dialog-backdrop" />
        <Dialog.Popup className="dialog-popup knowledge-index-dialog" finalFocus={addDocumentRef}>
          <div className="dialog-header">
            <div><Dialog.Title>Add a document</Dialog.Title><Dialog.Description>Index an original source so the copilot can cite it in supported answers.</Dialog.Description></div>
            <Dialog.Close type="button" className="icon-button dialog-close" aria-label="Close document form"><X size={19} aria-hidden="true" /></Dialog.Close>
          </div>
          <div className="knowledge-index-guidance"><FileText size={18} aria-hidden="true" /><p>Use fictional or authorized content only. Indexed documents cannot be edited. Source URLs are metadata and are never fetched.</p></div>
          <ErrorNotice error={index.error} />
          {Object.keys(errors).length > 0 && !index.error && <div className="notice notice-error" role="alert">Please check the highlighted fields.</div>}
          <form onSubmit={submit} noValidate aria-busy={index.isPending}>
            <fieldset className="form-fields" disabled={index.isPending}>
              <legend className="sr-only">Knowledge document</legend>
              <div className="field">
                <label htmlFor="knowledge-title">Document title <span className="required-text">(required)</span></label>
                <input id="knowledge-title" name="title" placeholder="e.g. Password reset policy" value={values.title} onChange={(event) => changeField('title', event.target.value)} required minLength={3} maxLength={200} aria-invalid={Boolean(errors.title)} aria-describedby={errors.title ? 'knowledge-title-error' : undefined} />
                <FieldError id="knowledge-title-error" message={errors.title} />
              </div>
              <div className="field">
                <label htmlFor="knowledge-url">Source URL <span className="required-text">(optional)</span></label>
                <input id="knowledge-url" name="source_url" type="url" placeholder="https://example.com/policy" value={values.source_url} onChange={(event) => changeField('source_url', event.target.value)} aria-invalid={Boolean(errors.source_url)} aria-describedby={`knowledge-url-help${errors.source_url ? ' knowledge-url-error' : ''}`} />
                <p className="field-help" id="knowledge-url-help">HTTP(S) only. Leave blank for a local indexed source.</p>
                <FieldError id="knowledge-url-error" message={errors.source_url} />
              </div>
              <div className="field">
                <label htmlFor="knowledge-content">Document body <span className="required-text">(required)</span></label>
                <textarea id="knowledge-content" name="content" placeholder="Paste the complete policy or source text…" rows={9} required minLength={50} maxLength={20_000} value={values.content} onChange={(event) => changeField('content', event.target.value)} aria-invalid={Boolean(errors.content)} aria-describedby={`knowledge-content-help${errors.content ? ' knowledge-content-error' : ''}`} />
                <div className="knowledge-body-help"><p className="field-help" id="knowledge-content-help">50–20,000 characters. Plain text and Markdown stay plain text.</p><span className="metadata">{values.content.length.toLocaleString()} / 20,000</span></div>
                <FieldError id="knowledge-content-error" message={errors.content} />
              </div>
            </fieldset>
            <div className="form-actions knowledge-index-actions"><Dialog.Close type="button" className="button button-secondary">{index.isPending ? 'Keep browsing' : 'Close'}</Dialog.Close><button type="submit" className="button" disabled={index.isPending}>{index.isPending ? <><span className="spinner" aria-hidden="true" />Indexing knowledge…</> : <><Plus size={16} aria-hidden="true" />Index document</>}</button></div>
            {index.isPending ? <p className="field-help" role="status">Indexing knowledge. Embeddings are validated before the document and its chunks are saved.</p> : <p className="field-help knowledge-draft-note">Closing this form keeps your entered text until a document is successfully indexed.</p>}
          </form>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
