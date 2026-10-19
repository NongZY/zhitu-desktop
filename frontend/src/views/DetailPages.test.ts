import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const api = vi.hoisted(() => ({ examDetail: vi.fn(), knowledgePointDetail: vi.fn(), push: vi.fn(), params: { id: '17' } }))
vi.mock('../api', () => ({ learningApi: api }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: api.push }), useRoute: () => ({ params: api.params }) }))
let wrapper: VueWrapper | undefined
beforeEach(() => vi.resetAllMocks())
afterEach(() => wrapper?.unmount())

describe('学习详情内容', () => {
  it('逐题显示答案和解析，未自动评分的简答题标记为自行检查', async () => {
    api.examDetail.mockResolvedValue({ id: 17, title: '复习', score: 5, total_score: 10, graded_total_score: 5, pending_count: 1, correct_count: 1, wrong_count: 0, textbook_title: '数学', submitted_at: '2026-10-04T12:00:00Z', details: [{ question_id: 1, stem: '负数一定小于零吗？', question_type: 'true_false', options: null, user_answer: false, correct_answer: true, is_correct: false, score: 0, max_score: 5, explanation: '负数小于零' }, { question_id: 2, stem: '说明理由', question_type: 'short_answer', options: null, user_answer: '我的理由', correct_answer: '参考理由', is_correct: null, score: 0, max_score: 5, explanation: '结合数轴说明' }] })
    const view = (await import('./ExamRecordDetailView.vue')).default
    wrapper = mount(view, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(api.examDetail).toHaveBeenCalledWith('17')
    expect(wrapper.text()).toContain('客观题得分')
    expect(wrapper.text()).toContain('自行检查')
    expect(wrapper.text()).toContain('我的理由')
    expect(wrapper.text()).toContain('参考理由')
    expect(wrapper.text()).toContain('错误')
    expect(wrapper.text()).toContain('负数小于零')
  })
  it('知识点详情用教材内编号练习，并可以回到原书章节', async () => {
    api.knowledgePointDetail.mockResolvedValue({ id: 81, name: '有理数', description: '有理数概念', mastery: .4, attempts: 2, correct_count: 1, mappings: [{ textbook_id: 2, textbook_title: '数学', chapter_id: 7, chapter_title: '第一章', local_knowledge_point_id: 9, page_start: 8 }], recent_answers: [] })
    const view = (await import('./KnowledgePointDetailView.vue')).default
    wrapper = mount(view, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    await wrapper.findAll('button').find(item => item.text().includes('练习这个知识点'))!.trigger('click')
    expect(api.push).toHaveBeenCalledWith({ path: '/exam/generate', query: { textbook: 2, knowledgePoint: 9 } })
    await wrapper.findAll('button').find(item => item.text().includes('回到课本'))!.trigger('click')
    expect(api.push).toHaveBeenCalledWith({ path: '/textbooks/2', query: { chapter: 7 } })
    expect(wrapper.text()).toContain('40%')
  })
  it.each([
    { options: [{ key: 'A', text: '正数' }, { key: 'B', text: '负数' }] },
    { options: ['正数', '负数'] },
    { options: { A: '正数', B: '负数' } },
  ])('知识点最近作答展示选择题选项 %#', async ({ options }) => {
    api.knowledgePointDetail.mockResolvedValue({ id: 81, name: '有理数', description: null, mastery: .4, attempts: 1, correct_count: 1, mappings: [], recent_answers: [{ question_id: 1, record_id: 17, submitted_at: '2026-10-04T12:00:00Z', stem: '小于零的数是什么？', question_type: 'single_choice', options, user_answer: 'B', correct_answer: 'B', is_correct: true, score: 5, max_score: 5, explanation: '结合数轴理解' }] })
    const view = (await import('./KnowledgePointDetailView.vue')).default
    wrapper = mount(view, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(wrapper.text()).toContain('A. 正数')
    expect(wrapper.text()).toContain('B. 负数')
  })
  it('读取失败可重试，不显示空白成功页面', async () => {
    api.examDetail.mockRejectedValue(new Error('暂时不可用'))
    const view = (await import('./ExamRecordDetailView.vue')).default
    wrapper = mount(view, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(wrapper.text()).toContain('无法打开这次练习')
    await wrapper.findAll('button').find(item => item.text().includes('重试'))!.trigger('click')
    await flushPromises()
    expect(api.examDetail).toHaveBeenCalledTimes(2)
  })
})
