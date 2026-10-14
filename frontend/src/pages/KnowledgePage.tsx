import { useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Dialog } from '@base-ui/react/dialog';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BookOpen, ChevronRight, FileText, Library, Plus, RefreshCw, Search, X } from 'lucide-react';
import { ApiError, api } from '../api';
import { knowledgeApi } from '../knowledge-api';
import { useAuth } from '../auth';
import { safeHttpUrl } from '../format';
import { queryKeys } from '../query';
import type { FieldErrors, KnowledgeDocument } from '../types';
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
  const isAdmin = useAuth().member?.role === 'admin';
  const client = useQueryClient();
  const addDocumentRef = useRef<HTMLButtonElement | null>(null);
  const [values, setValues] = useState<KnowledgeForm>({ title: '', source_url: '', content: '' });
  const [errors, setErrors] = useState<FieldErrors>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [success, setSuccess] = useState('');
  const [mode, setMode] = useState<'text' | 'file' | 'url'>('text');
  const [file, setFile] = useState<File | null>(null);
  const [editing, setEditing] = useState<KnowledgeDocument | null>(null);
  const [historyOffset, setHistoryOffset] = useState(0);
  const history = useQuery({ queryKey: ['knowledge-history', selectedId, historyOffset],
    queryFn: () => knowledgeApi.history(selectedId!, historyOffset), enabled: selectedId !== null });
  const knowledge = useQuery({ queryKey: queryKeys.knowledge, queryFn: ({ signal }) => api.knowledge(signal) });
  const document = useQuery({
    queryKey: queryKeys.document(selectedId ?? ''),
    queryFn: ({ signal }) => api.document(selectedId!, signal),
    enabled: selectedId !== null,
  });
  const index = useMutation({
    mutationFn: async () => {
      const payload = { title: values.title.trim(), content: values.content.replace(/\r\n/g, '\n').trim(), source_url: values.source_url.trim() || null };
      if (editing) return knowledgeApi.update(editing.id, { ...payload, version: editing.version });
      if (mode === 'url') return knowledgeApi.importUrl(payload.title, values.source_url.trim());
      if (mode === 'file') {
        if (!file) throw new Error('Choose a PDF, text or Markdown file.');
        return knowledgeApi.importFile(payload.title, file);
      }
      return api.createDocument(payload);
    },
    onSuccess: async (created) => {
      client.setQueryData(queryKeys.document(created.id), created);
      setSelectedId(created.id);
      setSearch('');
      setValues({ title: '', source_url: '', content: '' });
      setEditing(null); setFile(null); setMode('text'); setHistoryOffset(0);
      setErrors({});
      setDialogOpen(false);
      setSuccess(`“${created.title}” was indexed with ${created.chunk_count} ${created.chunk_count === 1 ? 'chunk' : 'chunks'}.`);
      await Promise.all([
        client.invalidateQueries({ queryKey: ['knowledge'] }),
        client.invalidateQueries({ queryKey: ['knowledge-history'] }),
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
    if (index.isPending || !isAdmin) return;
    const title = values.title.trim();
    const content = values.content.replace(/\r\n/g, '\n').trim();
    const sourceUrl = values.source_url.trim();
    const nextErrors: FieldErrors = {};
    if (title.length < 3 || title.length > 200) nextErrors.title = 'Enter a title with 3–200 characters.';
    if (mode === 'text' && (content.length < 50 || content.length > 500_000)) nextErrors.content = 'Enter a body with 50–500,000 characters.';
    if ((mode === 'url' || sourceUrl) && !safeHttpUrl(sourceUrl)) nextErrors.source_url = 'Enter a complete public HTTP or HTTPS URL.';
    if (mode === 'file' && (!file || file.size > 10 * 1024 * 1024)) nextErrors.file = 'Choose a PDF, UTF-8 text or Markdown file up to 10 MB.';
    setErrors(nextErrors);
    setSuccess('');
    index.reset();
    const firstInvalidField = Object.keys(nextErrors)[0];
    if (firstInvalidField) {
      const control = event.currentTarget.elements.namedItem(firstInvalidField);
      if (control instanceof HTMLElement) control.focus();
      return;
    }
    index.mutate();
  }

  function editDocument(value: KnowledgeDocument) {
    setEditing(value); setMode('text'); setValues({ title: value.title, content: value.content, source_url: value.source_url ?? '' });
    setErrors({}); index.reset(); setDialogOpen(true);
  }

  return (
    <Dialog.Root open={dialogOpen} onOpenChange={setDialogOpen}>
      <div className="knowledge-page">
        <PageHeader
          title="Knowledge base"
          description="The original sources behind every supported answer."
          actions={isAdmin ? <Dialog.Trigger ref={addDocumentRef} type="button" className="button" onClick={() => { if (editing) setValues({ title: '', content: '', source_url: '' }); setEditing(null); }}><Plus size={17} aria-hidden="true" />Add document</Dialog.Trigger> : undefined}
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
              {documents?.length === 0 && <EmptyState title="Your library starts here"><p>Ask an administrator to add supporting policies. Without supporting sources, the copilot will not draft an answer.</p>{isAdmin && <button type="button" className="button button-secondary" onClick={() => setDialogOpen(true)}><Plus size={16} aria-hidden="true" />Add a document</button>}</EmptyState>}
              {documents && documents.length > 0 && filteredDocuments?.length === 0 && <EmptyState title="No matching documents"><p>Try another title. This filter searches document titles, not their contents.</p><button type="button" className="button button-quiet" onClick={() => setSearch('')}>Clear filter</button></EmptyState>}
            </div>
            {filteredDocuments && filteredDocuments.length > 0 && (
              <>
                {searchTerm && <p className="knowledge-filter-count metadata" role="status">{filteredDocuments.length} of {documents?.length} documents</p>}
                <ul className="knowledge-document-list">
                  {filteredDocuments.map((item) => (
                    <li key={item.id}>
                      <button type="button" className={`knowledge-document-select${selectedId === item.id ? ' is-selected' : ''}`} aria-pressed={selectedId === item.id} onClick={() => { setSelectedId(item.id); setHistoryOffset(0); }} aria-controls="document-inspector">
                        <span className="knowledge-document-icon"><FileText size={18} aria-hidden="true" /></span>
                        <span className="knowledge-document-summary"><strong>{item.title}</strong><span className="metadata">Revision {item.version} · {item.chunk_count} {item.chunk_count === 1 ? 'chunk' : 'chunks'}</span></span>
                        <ChevronRight size={15} className="knowledge-document-chevron" aria-hidden="true" />
                      </button>
                    </li>
                  ))}
                </ul>
              </>
            )}
            <p className="knowledge-library-note"><Library size={15} aria-hidden="true" /><span>Only current revisions are retrieved. Historical sources remain available for existing citations.</span></p>
          </section>

          <section className="knowledge-reader" id="document-inspector" aria-labelledby="knowledge-inspector-heading">
            <div className="knowledge-reader-heading"><BookOpen size={16} aria-hidden="true" /><h2 id="knowledge-inspector-heading">Source revision</h2>{document.data && <span className="metadata">v{document.data.version}</span>}</div>
            {!selectedId && <div className="knowledge-reader-empty"><span className="knowledge-reader-empty-icon"><BookOpen size={27} aria-hidden="true" /></span><h3>Read the source, not just the answer</h3><p>Select a document to inspect its complete original text and the source used by the copilot.</p></div>}
            {selectedId && <div className="knowledge-reader-body">
              {document.isPending && <Loading>Loading original document…</Loading>}
              <ErrorNotice error={document.error} onRetry={() => { void document.refetch(); }} retrying={document.isFetching} />
              {document.data && <><DocumentContent document={document.data} />{isAdmin && knowledge.data?.some(item => item.id === document.data!.id) && <button type="button" className="button button-secondary" onClick={() => editDocument(document.data!)}>Edit as a new revision</button>}<hr /><h3>Revision history</h3><ErrorNotice error={history.error} />{history.isPending && <Loading>Loading revisions…</Loading>}<div className="form-actions">{history.data?.map(revision => <button key={revision.id} type="button" className="button button-quiet button-small" aria-pressed={revision.id === selectedId} onClick={() => setSelectedId(revision.id)}>v{revision.version}{revision.is_current ? ' · current' : ''}</button>)}</div><div className="form-actions"><button type="button" className="button button-quiet button-small" disabled={historyOffset === 0 || history.isFetching} onClick={() => setHistoryOffset(value => Math.max(0, value - 50))}>Newer revisions</button><button type="button" className="button button-quiet button-small" disabled={!history.data || history.data.length < 50 || history.isFetching} onClick={() => setHistoryOffset(value => value + 50)}>Older revisions</button></div></>}
            </div>}
          </section>
        </div>
      </div>

      <Dialog.Portal>
        <Dialog.Backdrop className="dialog-backdrop" />
        <Dialog.Popup className="dialog-popup knowledge-index-dialog" finalFocus={addDocumentRef}>
          <div className="dialog-header">
            <div><Dialog.Title>{editing ? `Edit revision ${editing.version}` : 'Add a document'}</Dialog.Title><Dialog.Description>{editing ? 'Saving creates a new revision. Existing citations keep their original source.' : 'Import a complete source for evidence-backed answers.'}</Dialog.Description></div>
            <Dialog.Close type="button" className="icon-button dialog-close" aria-label="Close document form"><X size={19} aria-hidden="true" /></Dialog.Close>
          </div>
          <div className="knowledge-index-guidance"><FileText size={18} aria-hidden="true" /><p>Use synthetic or authorized content. Public URLs are fetched securely; PDF imports extract text, not images. Embeddings use token-aware segments within the model's 512-token limit.</p></div>
          <ErrorNotice error={index.error} />
          {Object.keys(errors).length > 0 && !index.error && <div className="notice notice-error" role="alert">Please check the highlighted fields.</div>}
          <form onSubmit={submit} noValidate aria-busy={index.isPending}>
            <fieldset className="form-fields" disabled={index.isPending}>
              <legend className="sr-only">Knowledge document</legend>
              {!editing && <div className="field"><label htmlFor="knowledge-mode">Import method</label><select id="knowledge-mode" value={mode} onChange={event => { setMode(event.target.value as typeof mode); setErrors({}); }}><option value="text">Paste text / Markdown</option><option value="file">Upload PDF / text / Markdown</option><option value="url">Fetch public URL</option></select></div>}
              <div className="field">
                <label htmlFor="knowledge-title">Document title <span className="required-text">(required)</span></label>
                <input id="knowledge-title" name="title" placeholder="e.g. Password reset policy" value={values.title} onChange={(event) => changeField('title', event.target.value)} required minLength={3} maxLength={200} aria-invalid={Boolean(errors.title)} aria-describedby={errors.title ? 'knowledge-title-error' : undefined} />
                <FieldError id="knowledge-title-error" message={errors.title} />
              </div>
              {mode === 'file' && <div className="field"><label htmlFor="knowledge-file">Source file · up to 10 MB</label><input id="knowledge-file" name="file" type="file" accept=".pdf,.txt,.md" onChange={event => setFile(event.target.files?.[0] ?? null)} required /><p className="field-help">PDFs: up to 200 pages. Scanned documents need OCR first. Extracted text is retained; the original file is not stored.</p><FieldError id="knowledge-file-error" message={errors.file} /></div>}
              {mode !== 'file' && <>
              <div className="field">
                <label htmlFor="knowledge-url">{mode === 'url' ? 'Public URL (required)' : 'Source URL (optional metadata)'}</label>
                <input id="knowledge-url" name="source_url" type="url" placeholder="https://example.com/policy" value={values.source_url} onChange={(event) => changeField('source_url', event.target.value)} aria-invalid={Boolean(errors.source_url)} aria-describedby={`knowledge-url-help${errors.source_url ? ' knowledge-url-error' : ''}`} />
                <p className="field-help" id="knowledge-url-help">{mode === 'url' ? 'Public HTTP(S) only. Private networks, credentials and unsafe redirects are blocked.' : 'Optional source reference. This field is not fetched in text mode.'}</p>
                <FieldError id="knowledge-url-error" message={errors.source_url} />
              </div>
              </>}
              {mode === 'text' && <>
              <div className="field">
                <label htmlFor="knowledge-content">Document body <span className="required-text">(required)</span></label>
                <textarea id="knowledge-content" name="content" placeholder="Paste the complete policy or source text…" rows={9} required minLength={50} maxLength={500_000} value={values.content} onChange={(event) => changeField('content', event.target.value)} aria-invalid={Boolean(errors.content)} aria-describedby={`knowledge-content-help${errors.content ? ' knowledge-content-error' : ''}`} />
                <div className="knowledge-body-help"><p className="field-help" id="knowledge-content-help">50–500,000 characters. No silent truncation.</p><span className="metadata">{values.content.length.toLocaleString()} / 500,000</span></div>
                <FieldError id="knowledge-content-error" message={errors.content} />
              </div>
              </>}
            </fieldset>
            <div className="form-actions knowledge-index-actions"><Dialog.Close type="button" className="button button-secondary">{index.isPending ? 'Keep browsing' : 'Close'}</Dialog.Close><button type="submit" className="button" disabled={index.isPending}>{index.isPending ? <><span className="spinner" aria-hidden="true" />Indexing knowledge…</> : <><Plus size={16} aria-hidden="true" />Index document</>}</button></div>
            {index.isPending ? <p className="field-help" role="status">Indexing knowledge. Embeddings are validated before the document and its chunks are saved.</p> : <p className="field-help knowledge-draft-note">Closing this form keeps your entered text until a document is successfully indexed.</p>}
          </form>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
