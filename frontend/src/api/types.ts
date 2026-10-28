export interface User {
  id: string | number
  email: string
  name: string
  avatar_url?: string | null
  created_at?: string
}

export interface AuthResponse {
  access_token: string
  token_type?: string
  user?: User
}

export interface LoginPayload {
  email: string
  password: string
}

export interface RegisterPayload extends LoginPayload {
  name: string
}

export type TextbookStatus = 'draft' | 'processing' | 'review' | 'ready' | 'failed'

export interface Textbook {
  id: string | number
  title: string
  name?: string
  subject?: string
  grade?: string
  edition?: string
  cover_url?: string | null
  file_name?: string | null
  status: TextbookStatus
  parse_status?: string
  processing_progress?: number
  processing_message?: string | null
  chapter_count?: number
  knowledge_point_count?: number
  question_count?: number
  created_at?: string
  updated_at?: string
}

export interface KnowledgePoint {
  id: string | number
  name: string
  description?: string
  order_index?: number
  mastery?: number | null
  global_knowledge_point_id?: string | number | null
  global_name?: string | null
}

export interface Chapter {
  id: string | number
  title: string
  order?: number
  order_index?: number
  parent_id?: string | number | null
  level?: number
  summary?: string | null
  page_start?: number | null
  page_end?: number | null
  children?: Chapter[]
  knowledge_points?: KnowledgePoint[]
}

export interface TextbookStructure {
  textbook: Textbook
  chapters: Chapter[]
  reader_chapters?: Chapter[] | null
}

export interface ChapterContent {
  id: number
  page_number: number | null
  content: string
  quality_note?: string
}

export interface PageSearchItem {
  page_number: number
  excerpt: string
  chapter_id: number | null
  chapter_title: string | null
}

export interface ReaderMetadata {
  page_count: number
  document_revision: string | null
}

export interface ReadingProgress {
  textbook_id: number
  page_number: number
  chapter_id: number | null
  document_revision: string
  revision: number
  updated_at: string
}

export interface ReadingProgressPayload {
  page_number: number
  chapter_id: number | null
  document_revision: string
  expected_revision: number
}

export interface ReadingHome {
  textbook_count: number
  continue_reading: (ReadingProgress & { title: string; chapter_title: string | null; page_count: number }) | null
  reading_notice: string | null
}

export interface ImportTask {
  id: string
  textbook_id: string | number
  celery_task_id?: string | null
  status: 'queued' | 'processing' | 'completed' | 'failed'
  progress: number
  message?: string | null
  created_at: string
  updated_at: string
}

export type QuestionType = 'single_choice' | 'multiple_choice' | 'fill_blank' | 'true_false' | 'short_answer'
export type QuestionStatus = 'draft' | 'pending' | 'approved' | 'rejected'

export interface QuestionOption {
  key: string
  text: string
}

export interface Question {
  id: string | number
  stem: string
  type: QuestionType
  difficulty: number
  options?: QuestionOption[] | Record<string, string> | null
  answer?: string | string[] | boolean | null
  analysis?: string | null
  status?: QuestionStatus
  source?: string | null
  textbook_id?: string | number | null
  textbook_title?: string | null
  chapter_id?: string | number | null
  chapter_title?: string | null
  knowledge_points?: KnowledgePoint[]
  knowledge_point_id?: string | number | null
  created_at?: string
}

export interface PageResult<T> {
  items: T[]
  total: number
  page?: number
  page_size?: number
}

export interface QuestionQuery {
  page?: number
  page_size?: number
  textbook_id?: string | number
  chapter_id?: string | number
  knowledge_point_id?: string | number
  type?: QuestionType | ''
  difficulty?: number | ''
  status?: QuestionStatus | ''
  keyword?: string
}

export interface QuestionPayload {
  stem: string
  type: QuestionType
  difficulty: number
  options?: QuestionOption[]
  answer?: string | string[] | boolean
  analysis?: string
  status?: QuestionStatus
  textbook_id?: string | number
  chapter_id?: string | number
  knowledge_point_id?: string | number
  knowledge_point_ids?: Array<string | number>
}

export interface ExamGeneratePayload {
  auto_fill?: boolean
  title?: string
  textbook_id?: string | number
  chapter_ids?: Array<string | number>
  knowledge_point_ids?: Array<string | number>
  question_types?: QuestionType[]
  difficulty_min?: number
  difficulty_max?: number
  question_count: number
  duration_minutes: number
  mode: 'random' | 'adaptive'
}

export interface ExamQuestion extends Omit<Question, 'answer' | 'analysis'> {
  score: number
  sequence?: number
}

export interface ExamPaper {
  id: string | number
  title: string
  questions: ExamQuestion[]
  duration_minutes: number
  total_score: number
  strategy?: Record<string, unknown>
  created_at?: string
}

export interface ExamAnswer {
  question_id: string | number
  answer: string | string[] | boolean | null
  time_spent_seconds?: number
}

export interface ExamSubmitPayload {
  answers: ExamAnswer[]
  duration_seconds?: number
}

export interface QuestionResult {
  question_id: string | number
  correct: boolean | null
  score: number
  max_score: number
  correct_answer?: string | string[] | boolean | null
  analysis?: string | null
}

export interface ExamResult {
  id?: string | number
  record_id?: string | number
  paper_id: string | number
  score: number
  total_score: number
  correct_count: number
  wrong_count?: number
  pending_count?: number
  graded_total_score?: number
  status?: string
  total_count: number
  duration_seconds: number
  submitted_at?: string
  question_results?: QuestionResult[]
  details?: Array<{
    question_id: string | number
    user_answer: unknown
    correct_answer?: unknown
    is_correct: boolean | null
    score: number
    max_score?: number
    explanation?: string | null
  }>
  mastery_changes?: MasteryItem[]
}

export interface DashboardSummary {
  textbook_count: number
  completed_exam_count: number
  average_score: number
  study_minutes: number
  mastery_average?: number
  weak_point_count?: number
  recent_exams?: RecentExam[]
  weekly_activity?: Array<{ date: string; minutes: number; questions: number }>
  recommendations?: Recommendation[]
}

export interface ExamHistoryItem {
  id: string | number
  paper_id: string | number
  title: string
  score: number
  total_score: number
  correct_count: number
  wrong_count: number
  pending_count?: number
  graded_total_score?: number
  status?: string
  duration_seconds?: number | null
  submitted_at: string
}

export interface RecentExam {
  id: string | number
  title: string
  score: number
  total_score: number
  pending_count?: number
  graded_total_score?: number
  submitted_at: string
}

export interface Recommendation {
  id?: string | number
  title: string
  description: string
  type?: 'review' | 'practice' | 'path'
  knowledge_point_id?: string | number
}

export interface MasteryItem {
  knowledge_point_id: string | number
  name: string
  mastery: number
  trend?: number
  question_count?: number
  last_practiced_at?: string | null
  subject?: string
  attempts?: number
  correct_count?: number
}

export interface WrongQuestion {
  id: string | number
  question: Question
  wrong_count: number
  last_wrong_at: string
  mastered?: boolean
  user_answer?: string | string[] | boolean | null
  question_id?: string | number
  stem?: string
  question_type?: QuestionType
  difficulty?: number
  resolved?: boolean
  textbook_id?: string | number | null
  chapter_id?: string | number | null
  knowledge_point_id?: string | number | null
}

export interface AnswerEvidence {
  snapshot_verified?: boolean
  question_id: string | number
  stem: string
  question_type: QuestionType
  options: QuestionOption[] | string[] | Record<string, string> | null
  user_answer: unknown
  correct_answer: unknown
  is_correct: boolean | null
  score: number
  max_score: number
  explanation: string | null
  knowledge_point_id: string | number | null
  global_knowledge_point_id: string | number | null
  knowledge_point_name: string | null
  chapter_id: string | number | null
  textbook_id: string | number
  time_spent_seconds: number | null
}

export interface ExamRecordDetail extends ExamHistoryItem {
  textbook_id: string | number | null
  textbook_title: string | null
  pending_count: number
  graded_total_score: number
  status: string
  details: AnswerEvidence[]
}

export interface KnowledgePointDetail {
  id: string | number
  name: string
  description: string | null
  subject: string
  grade: string | null
  mastery: number | null
  attempts: number
  correct_count: number
  updated_at: string | null
  mappings: Array<{
    textbook_id: string | number
    textbook_title: string
    chapter_id: string | number
    chapter_title: string
    page_start: number | null
    local_knowledge_point_id: string | number
  }>
  recent_answers: Array<AnswerEvidence & { record_id: string | number; submitted_at: string }>
}

export interface LearningPathNode {
  id: string | number
  name: string
  status: 'not_started' | 'learning' | 'mastered'
  mastery: number
  prerequisites?: Array<string | number>
  subject?: string
  grade?: string
}

export interface LearningPath {
  nodes: LearningPathNode[]
  edges: Array<{ source: string | number; target: string | number }>
}

export interface Citation {
  locator?: import('./documents').DocumentLocator | null
  chunk_id?: string | number
  textbook_id?: string | number
  textbook_title: string
  chapter_title?: string
  page?: number | null
  content?: string
  score?: number
}

export interface RagAskPayload {
  use_ai?: boolean
  question: string
  textbook_id?: string | number
  chapter_id?: string | number
  top_k?: number
}

export interface RagAnswer {
  mode?: 'local' | 'ai'
  ai_status?: string
  notice?: string
  answer: string
  citations: Citation[]
  conversation_id?: string
  insufficient_context?: boolean
}

export interface ApiErrorData {
  detail?: string | Array<{ msg?: string }>
  message?: string
}
