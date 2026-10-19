import { isAxiosError } from 'axios'
import { http, normalizePage } from './http'
import type {
  AuthResponse,
  Chapter,
  ChapterContent,
  DashboardSummary,
  ExamGeneratePayload,
  ExamHistoryItem,
  ExamRecordDetail,
  ExamPaper,
  ExamResult,
  ExamSubmitPayload,
  ImportTask,
  LearningPath,
  LoginPayload,
  KnowledgePoint,
  KnowledgePointDetail,
  MasteryItem,
  PageResult,
  PageSearchItem,
  Question,
  QuestionPayload,
  QuestionQuery,
  QuestionResult,
  RagAnswer,
  RagAskPayload,
  RegisterPayload,
  ReaderMetadata,
  ReadingProgress,
  ReadingProgressPayload,
  ReadingHome,
  Textbook,
  TextbookStructure,
  User,
  WrongQuestion,
} from './types'

export const authApi = {
  async login(payload: LoginPayload) {
    return (await http.post<AuthResponse>('/auth/login', payload)).data
  },
  async register(payload: RegisterPayload) {
    return (await http.post<User>('/auth/register', payload)).data
  },
  async me() {
    return (await http.get<User>('/auth/me')).data
  },
}

export const textbookApi = {
  async reader(id: string | number, signal?: AbortSignal) {
    return (await http.get<ReaderMetadata>(`/textbooks/${id}/reader`, { signal })).data
  },
  async searchPages(id: string | number, params: {
    q: string; chapter_id?: string | number; page?: number; page_size?: number
  }, signal?: AbortSignal) {
    return (await http.get<PageResult<PageSearchItem>>(`/textbooks/${id}/search`, { params, signal })).data
  },
  async pageImage(id: string | number, pageNumber: number, signal?: AbortSignal) {
    try {
      return (await http.get<Blob>(`/textbooks/${id}/pages/${pageNumber}/image`, {
        responseType: 'blob', signal,
      })).data
    } catch (error) {
      if (isAxiosError(error) && error.response?.data instanceof Blob) {
        try {
          error.response.data = JSON.parse(await error.response.data.text())
        } catch { /* A non-JSON error uses the normal request failure message. */ }
      }
      throw error
    }
  },
  async recognizeOutline(id: string | number) {
    return (await http.post<{ added: number; message: string }>(`/textbooks/${id}/outline`)).data
  },
  async chapterContent(id: string | number, page = 1) {
    return (await http.get<PageResult<ChapterContent>>(`/chapters/${id}/content`, {
      params: { page, page_size: 10 },
    })).data
  },
  async list() {
    const { data } = await http.get<Textbook[] | PageResult<Textbook>>('/textbooks')
    const page = normalizePage(data)
    return { ...page, items: page.items.map(normalizeTextbook) }
  },
  async create(payload: Pick<Textbook, 'title'> & Partial<Textbook>) {
    return normalizeTextbook((await http.post<Textbook>('/textbooks', payload)).data)
  },
  async getStructure(id: string | number) {
    const data = (await http.get<TextbookStructure>(`/textbooks/${id}/structure`)).data
    return { ...data, textbook: normalizeTextbook(data.textbook) }
  },
  async createChapter(
    id: string | number,
    payload: {
      title: string
      parent_id?: string | number | null
      order_index?: number
      page_start?: number
      page_end?: number
      summary?: string
    },
  ) {
    return (await http.post<Chapter>(`/textbooks/${id}/chapters`, payload)).data
  },
  async createKnowledgePoint(
    chapterId: string | number,
    payload: { name: string; description?: string; order_index?: number },
  ) {
    return (
      await http.post<KnowledgePoint>(`/chapters/${chapterId}/knowledge-points`, payload)
    ).data
  },
  async publish(id: string | number) {
    return normalizeTextbook((await http.post<Textbook>(`/textbooks/${id}/publish`)).data)
  },
  async upload(id: string | number, file: File, onProgress?: (percentage: number) => void) {
    const form = new FormData()
    form.append('file', file)
    return (
      await http.post<ImportTask>(`/textbooks/${id}/upload`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (event) => {
          if (event.total) onProgress?.(Math.round((event.loaded / event.total) * 100))
        },
      })
    ).data
  },
}

export const readingApi = {
  async getProgress(bookId: number, signal?: AbortSignal) {
    return (await http.get<{ progress: ReadingProgress | null }>(`/learning/reading-progress/${bookId}`, { signal })).data
  },
  async saveProgress(bookId: number, payload: ReadingProgressPayload, signal?: AbortSignal) {
    return (await http.put<ReadingProgress>(`/learning/reading-progress/${bookId}`, payload, { signal })).data
  },
  async home(signal?: AbortSignal) {
    return (await http.get<ReadingHome>('/learning/home', { signal })).data
  },
}

export const questionApi = {
  async list(query: QuestionQuery = {}) {
    const params = { ...query, question_type: query.type || undefined }
    delete params.type
    const { data } = await http.get<RawQuestion[] | PageResult<RawQuestion>>('/questions', { params })
    const page = normalizePage(data)
    return { ...page, items: page.items.map(normalizeQuestion) }
  },
  async create(payload: QuestionPayload) {
    const { data } = await http.post<RawQuestion>('/questions', toQuestionPayload(payload))
    return normalizeQuestion(data)
  },
  async update(id: string | number, payload: Partial<QuestionPayload>) {
    const { data } = await http.put<RawQuestion>(`/questions/${id}`, toQuestionPayload(payload))
    return normalizeQuestion(data)
  },
  async remove(id: string | number) {
    await http.delete(`/questions/${id}`)
  },
}

export const examApi = {
  async generate(payload: ExamGeneratePayload) {
    const { data } = await http.post<ExamPaper>(`/exams/generate`, payload)
    return normalizeExam(data)
  },
  async get(id: string | number) {
    const { data } = await http.get<ExamPaper>(`/exams/${id}`)
    return normalizeExam(data)
  },
  async submit(id: string | number, payload: ExamSubmitPayload) {
    return normalizeExamResult((await http.post<ExamResult>(`/exams/${id}/submit`, payload)).data)
  },
}

export const learningApi = {
  async dashboard() {
    const raw = (await http.get<RawDashboard>('/learning/dashboard')).data
    return normalizeDashboard(raw)
  },
  async mastery() {
    const { data } = await http.get<MasteryItem[] | { items: MasteryItem[] }>('/learning/mastery')
    const rows = Array.isArray(data) ? data : data.items
    return rows.map(normalizeMastery)
  },
  async wrongQuestions() {
    const { data } = await http.get<WrongQuestion[] | PageResult<WrongQuestion>>('/learning/wrong-questions')
    const page = normalizePage(data)
    return { ...page, items: page.items.map(normalizeWrongQuestion) }
  },
  async path() {
    return (await http.get<LearningPath>('/learning/path')).data
  },
  async exams() {
    return (await http.get<{ items: ExamHistoryItem[]; total: number }>('/learning/exams')).data
  },
  async historyPage(params: { page?: number; page_size?: number } = {}) {
    return (await http.get<PageResult<ExamHistoryItem>>('/learning/exams', { params })).data
  },
  async examDetail(id: string | number) {
    return (await http.get<ExamRecordDetail>(`/learning/exams/${id}`)).data
  },
  async knowledgePointDetail(id: string | number) {
    return (await http.get<KnowledgePointDetail>(`/learning/knowledge-points/${id}`)).data
  },
}

export const ragApi = {
  async ask(payload: RagAskPayload) {
    const data = (await http.post<RagAnswer & { grounded?: boolean; model?: string }>('/rag/ask', payload)).data
    return {
      ...data,
      insufficient_context: data.insufficient_context ?? data.grounded === false,
      citations: (data.citations || []).map((item) => ({
        ...item,
        page: item.page ?? (item as { page_number?: number | null }).page_number,
        content: item.content ?? (item as { excerpt?: string }).excerpt,
      })),
    }
  },
}

export const systemApi = {
  async health() {
    return (await http.get<{ status: string }>('/health')).data
  },
}

export * from './types'

interface RawQuestion extends Partial<Question> {
  id: string | number
  stem: string
  question_type?: Question['type']
  correct_answer?: Question['answer']
  explanation?: string | null
}

interface RawTextbook extends Partial<Textbook> {
  id: string | number
  title: string
  parse_status?: string
}

interface RawDashboard {
  exam_count?: number
  average_score_rate?: number
  mastery_average?: number
  weak_points?: Array<Record<string, unknown>>
  wrong_question_count?: number
  weak_point_count?: number
  textbook_count?: number
  completed_exam_count?: number
  average_score?: number
  study_minutes?: number
  recent_exams?: DashboardSummary['recent_exams']
  weekly_activity?: DashboardSummary['weekly_activity']
  recommendations?: DashboardSummary['recommendations']
}

function normalizeQuestion(raw: RawQuestion): Question {
  return {
    ...raw,
    type: raw.type || raw.question_type || 'single_choice',
    difficulty: Number(raw.difficulty || 1),
    answer: raw.answer ?? raw.correct_answer,
    analysis: raw.analysis ?? raw.explanation,
  }
}

function toQuestionPayload(payload: Partial<QuestionPayload>) {
  const { type, answer, analysis, knowledge_point_ids, ...rest } = payload
  return {
    ...rest,
    question_type: type,
    correct_answer: answer,
    explanation: analysis,
    knowledge_point_id: payload.knowledge_point_id ?? knowledge_point_ids?.[0],
  }
}

function normalizeExam(paper: ExamPaper): ExamPaper {
  return {
    ...paper,
    questions: (paper.questions || []).map((question) => normalizeQuestion(question as RawQuestion)) as ExamPaper['questions'],
  }
}

function normalizeTextbook(raw: RawTextbook): Textbook {
  const source = raw.status || raw.parse_status || 'draft'
  const statusMap: Record<string, Textbook['status']> = {
    not_uploaded: 'draft',
    queued: 'processing',
    processing: 'processing',
    review: 'review',
    ready: 'ready',
    failed: 'failed',
  }
  return { ...raw, status: statusMap[source] || 'draft' }
}

function normalizeMastery(value: unknown): MasteryItem {
  const raw = value as Record<string, unknown>
  return {
    knowledge_point_id: (raw.knowledge_point_id ?? raw.global_knowledge_point_id ?? raw.id) as string | number,
    name: String(raw.name ?? raw.knowledge_point_name ?? '未命名知识点'),
    mastery: Number(raw.mastery ?? 0),
    attempts: Number(raw.attempts ?? raw.question_count ?? 0),
    correct_count: Number(raw.correct_count ?? 0),
    last_practiced_at: (raw.last_practiced_at ?? raw.updated_at ?? null) as string | null,
    subject: raw.subject ? String(raw.subject) : undefined,
  }
}

function normalizeWrongQuestion(raw: WrongQuestion): WrongQuestion {
  if (raw.question) return raw
  return {
    ...raw,
    id: raw.id,
    wrong_count: Number(raw.wrong_count || 0),
    last_wrong_at: raw.last_wrong_at,
    mastered: Boolean(raw.resolved),
    question: {
      id: raw.question_id || raw.id,
      stem: raw.stem || '题目内容不可用',
      type: raw.question_type || 'single_choice',
      difficulty: Number(raw.difficulty || 1),
      textbook_id: raw.textbook_id,
      chapter_id: raw.chapter_id,
      knowledge_point_id: raw.knowledge_point_id,
    },
  }
}

function normalizeDashboard(raw: RawDashboard): DashboardSummary {
  const weakPoints = (raw.weak_points || []).map((item) => normalizeMastery(item))
  const averageRate = Number(raw.average_score_rate ?? 0)
  return {
    textbook_count: Number(raw.textbook_count ?? 0),
    completed_exam_count: Number(raw.completed_exam_count ?? raw.exam_count ?? 0),
    average_score: Number(raw.average_score ?? averageRate * 100),
    study_minutes: Number(raw.study_minutes ?? 0),
    mastery_average: Number(raw.mastery_average ?? 0),
    weak_point_count: Number(raw.weak_point_count ?? weakPoints.filter((item) => item.mastery < 0.8).length),
    recent_exams: raw.recent_exams,
    weekly_activity: raw.weekly_activity,
    recommendations: raw.recommendations ?? weakPoints.slice(0, 3).map((item) => ({
      title: `巩固：${item.name}`,
      description: `当前掌握度 ${Math.round(item.mastery * 100)}%，建议安排一次针对性练习。`,
      type: 'review' as const,
      knowledge_point_id: item.knowledge_point_id,
    })),
  }
}

function normalizeExamResult(raw: ExamResult): ExamResult {
  const details = raw.details || []
  return {
    ...raw,
    total_count: raw.total_count ?? details.length,
    duration_seconds: raw.duration_seconds ?? 0,
    question_results: raw.question_results ?? details.map((item) => ({
      question_id: item.question_id,
      correct: item.is_correct,
      score: item.score,
      max_score: item.max_score ?? 0,
      correct_answer: item.correct_answer as QuestionResult['correct_answer'],
      analysis: item.explanation,
    })),
  }
}
