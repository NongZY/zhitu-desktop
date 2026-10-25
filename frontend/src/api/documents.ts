import { http } from './http'

export interface DocumentLocator {
  source_id: string
  source_revision: string
  rendition_revision: string
  kind: string
  unit_id: string
}
export interface DocumentBlock {
  id: string; kind: string; text: string; level?: number; slide?: number; page?: number
  cells?: string[][]; image?: string; chapter_id?: number
}
export interface DocumentData {
  is_current?: boolean
  page_count?: number
  textbook_id: number; format: string; original_name: string
  source_id: string; source_revision: string; rendition_revision: string
  warnings: string[]; blocks: DocumentBlock[]
  chapters: { id: number; title: string; level: number; locator: DocumentLocator }[]
}
export interface DocumentPosition extends DocumentLocator {
  revision: number; source_changed: boolean; updated_at: string
}
export const documentsApi = {
  async read(id: string | number, version?: string) {
    const path = `/textbooks/${id}/document${version ? `/versions/${encodeURIComponent(version)}` : ''}`
    return (await http.get<DocumentData | null>(path)).data
  },
  async state(id: string | number) {
    return (await http.get<{ format: string | null; status: string; message: string; progress: number; available: boolean }>(`/textbooks/${id}/document/state`)).data
  },
  async position(id: string | number) {
    return (await http.get<DocumentPosition | null>(`/textbooks/${id}/document/position`)).data
  },
  async savePosition(id: string | number, locator: DocumentLocator, expected_revision: number) {
    return (await http.put<DocumentPosition>(`/textbooks/${id}/document/position`, { ...locator, expected_revision })).data
  },
  async search(id: string | number, q: string, page = 1, revision?: string) {
    return (await http.get<{ items: { excerpt: string; locator: DocumentLocator; chapter_id: number }[]; total: number }>(`/textbooks/${id}/document/search`, { params: { q, page, revision } })).data
  },
  async retry(id: string | number, encoding = 'auto') {
    return (await http.post(`/textbooks/${id}/document/retry`, { encoding })).data
  },
  async recent() {
    return (await http.get<(DocumentPosition & { title: string; textbook_id: number }) | null>('/documents/recent')).data
  },
}
export function documentLink(book: string | number, locator: DocumentLocator): string {
  const query = new URLSearchParams({ source: locator.source_id, version: locator.rendition_revision,
    unit: locator.unit_id, kind: locator.kind })
  return `/textbooks/${book}?${query.toString()}`
}
