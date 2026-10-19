import { beforeEach, describe, expect, it, vi } from 'vitest'
import { examApi, learningApi } from './index'

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('./http', () => ({
  http: mocks,
  normalizePage: (data: { items: unknown[]; total: number }) => data,
}))

beforeEach(() => vi.resetAllMocks())

describe('学习详情数据', () => {
  it('巩固知识点数量不再误用错题数量', async () => {
    mocks.get.mockResolvedValue({ data: { weak_point_count: 1, wrong_question_count: 9 } })
    expect((await learningApi.dashboard()).weak_point_count).toBe(1)
  })
  it('错题再练保留教材和教材内知识点', async () => {
    mocks.get.mockResolvedValue({ data: { items: [{ id: 1, question_id: 2, textbook_id: 3,
      chapter_id: 4, knowledge_point_id: 5, stem: '1+1', question_type: 'fill_blank' }], total: 1 } })
    expect((await learningApi.wrongQuestions()).items[0].question).toMatchObject({
      textbook_id: 3, chapter_id: 4, knowledge_point_id: 5,
    })
  })
  it('历史分页传递页码，详情使用记录编号而非试卷编号', async () => {
    mocks.get.mockResolvedValue({ data: { items: [], total: 0 } })
    await learningApi.historyPage({ page: 3, page_size: 10 })
    expect(mocks.get).toHaveBeenCalledWith('/learning/exams', { params: { page: 3, page_size: 10 } })
    await learningApi.examDetail(42)
    expect(mocks.get).toHaveBeenCalledWith('/learning/exams/42')
    await learningApi.knowledgePointDetail(9)
    expect(mocks.get).toHaveBeenCalledWith('/learning/knowledge-points/9')
  })
  it('每题满分不会被替换成零分，简答保留未评分状态', async () => {
    mocks.post.mockResolvedValue({ data: {
      paper_id: 1, pending_count: 1, graded_total_score: 0,
      details: [{ question_id: 2, score: 0, max_score: 5, is_correct: null }],
    } })
    const result = await examApi.submit(1, { answers: [] })
    expect(result.question_results?.[0]).toMatchObject({ score: 0, max_score: 5, correct: null })
    expect(result.pending_count).toBe(1)
    expect(result.graded_total_score).toBe(0)
  })
})
