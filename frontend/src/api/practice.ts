import { http } from './http'
import type { QuestionType } from './types'
import type { DocumentLocator } from './documents'

export interface CandidateQuestion { question_type: QuestionType; stem: string; options: { key: string; text: string }[] | null; correct_answer: string | string[] | boolean; explanation: string; difficulty: number }
export interface Evidence { id: string; text: string; locator: DocumentLocator }
export interface Candidate { id: string; chapter_id: number | null; question: CandidateQuestion; evidence: Evidence[]; method: string; provenance: { model?: string }; saved_question_id: number | null }
export interface PracticeJob { id: string; textbook_id: number; status: string; message: string; source_changed: boolean; parameters: { mode: string }; units: { title: string; status: string; message: string; evidence: Evidence[] }[]; candidates: Candidate[] }
export interface Coverage { title: string; rendition_revision: string | null; ready_questions: number; estimated_requests: number; chapters: { chapter_id: number | null; title: string; ready_questions: number; body_blocks: number; selected_blocks: number; excerpts: Evidence[]; supported_topics: string[] }[] }
export interface JobSummary { id: string; status: string; created_at?: string }
export const practiceApi = {
  async coverage(book: string | number, chapter?: number) { return (await http.get<Coverage>(`/textbooks/${book}/practice/coverage`, { params: { chapter_id: chapter } })).data },
  async jobs(book: string | number) { return (await http.get<JobSummary[]>(`/textbooks/${book}/practice/jobs`)).data },
  async start(book: string | number, payload: object) { return (await http.post<PracticeJob>(`/textbooks/${book}/practice/jobs`, payload)).data },
  async read(id: string) { return (await http.get<PracticeJob>(`/practice/jobs/${id}`)).data },
  async cancel(id: string) { return (await http.post<PracticeJob>(`/practice/jobs/${id}/cancel`)).data },
  async retry(id: string, consent: boolean) { return (await http.post<PracticeJob>(`/practice/jobs/${id}/retry`, { external_consent: consent })).data },
  async edit(id: string, question: CandidateQuestion) { return (await http.patch<Candidate>(`/practice/candidates/${id}`, question)).data },
  async confirm(id: string, candidateIds: string[]) { return (await http.post(`/practice/jobs/${id}/confirm`, { candidate_ids: candidateIds })).data },
}
