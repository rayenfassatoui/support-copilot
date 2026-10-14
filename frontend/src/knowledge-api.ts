import { request } from './api';
import type { KnowledgeCreate, KnowledgeDocument, KnowledgeSummary } from './types';
export const knowledgeApi = {
  importUrl: (title: string, url: string) => request<KnowledgeDocument>('/knowledge/import/url', { method: 'POST', body: { title, url } }),
  importFile: (title: string, file: File) => {
    const body = new FormData(); body.set('title', title); body.set('file', file);
    return request<KnowledgeDocument>('/knowledge/import/file', { method: 'POST', body });
  },
  update: (id: string, body: KnowledgeCreate & { version: number }) => request<KnowledgeDocument>(`/knowledge/${id}`, { method: 'PUT', body }),
  history: (id: string, offset = 0) => request<KnowledgeSummary[]>(`/knowledge/${id}/history?limit=50&offset=${offset}`),
};
