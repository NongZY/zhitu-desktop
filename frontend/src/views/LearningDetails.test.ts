import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import DashboardView from './DashboardView.vue'
import LearningView from './LearningView.vue'
import ResultsView from './ResultsView.vue'

const api = vi.hoisted(() => ({ home: vi.fn(), dashboard: vi.fn(), mastery: vi.fn(), path: vi.fn(), exams: vi.fn(), historyPage: vi.fn(), wrongQuestions: vi.fn(), push: vi.fn(), query: {} as Record<string, string> }))
vi.mock('../api', () => ({ learningApi: api, readingApi: api }))
vi.mock('../stores/auth', () => ({ useAuthStore: () => ({ user: { name: '学习者' } }) }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: api.push }), useRoute: () => ({ query: api.query }) }))
let wrapper: VueWrapper | undefined
const render = async (view: typeof DashboardView | typeof LearningView | typeof ResultsView) => {
  wrapper = mount(view, { global: { plugins: [ElementPlus], stubs: { BaseChart: true } } })
  await flushPromises()
  return wrapper
}
const button = (label: string) => wrapper!.findAll('button').find(item => item.text().includes(label))!
beforeEach(() => {
  vi.resetAllMocks()
  api.query = {}
  api.home.mockResolvedValue({ textbook_count: 2, continue_reading: null, reading_notice: null })
  api.mastery.mockResolvedValue([{ knowledge_point_id: 81, name: '待巩固的有理数', mastery: .4, attempts: 2 }, { knowledge_point_id: 82, name: '已经掌握的整式', mastery: .95, attempts: 3 }])
  api.path.mockResolvedValue({ nodes: [{ id: 81, name: '待巩固的有理数', mastery: .4 }, { id: 82, name: '已经掌握的整式', mastery: .95 }], edges: [] })
  api.dashboard.mockResolvedValue({ textbook_count: 2, completed_exam_count: 21, average_score: 100, study_minutes: 20, weak_point_count: 1, recent_exams: [{ id: 17, title: '混合练习', score: 5, total_score: 10, graded_total_score: 5, pending_count: 1, submitted_at: '2026-10-04T12:00:00Z' }], recommendations: [{ id: 81, knowledge_point_id: 81, title: '巩固：有理数', description: '多练一练' }] })
  const page = { items: [{ id: 17, paper_id: 8, title: '混合练习', score: 5, total_score: 10, graded_total_score: 5, correct_count: 1, wrong_count: 0, pending_count: 1, submitted_at: '2026-10-04T12:00:00Z' }], total: 21, page: 1, page_size: 10 }
  api.exams.mockResolvedValue(page)
  api.historyPage.mockResolvedValue(page)
  api.wrongQuestions.mockResolvedValue({ items: [], total: 0 })
})
afterEach(() => { wrapper?.unmount(); wrapper = undefined })

describe('学习详情入口', () => {
  it('尚未练习的知识点不冒充零分薄弱点', async () => {
    api.path.mockResolvedValue({ nodes: [{ id: 83, name: '还没练习的知识点', mastery: 0 }], edges: [] })
    await render(LearningView)
    expect(wrapper!.get('.point-list').text()).toContain('尚未练习')
    wrapper!.unmount()
    api.query = { filter: 'weak' }
    await render(LearningView)
    expect(wrapper!.get('.points-card').text()).not.toContain('还没练习的知识点')
  })
  it('总览可以打开最近练习和建议知识点的详情', async () => {
    await render(DashboardView)
    await button('混合练习').trigger('click')
    expect(api.push).toHaveBeenCalledWith('/results/17')
    await button('巩固：有理数').trigger('click')
    expect(api.push).toHaveBeenCalledWith('/learning/knowledge-points/81')
  })
  it('优先巩固不包含已掌握知识点，且能打开具体知识点', async () => {
    await render(LearningView)
    const weak = wrapper!.get('.weak-card')
    expect(weak.text()).not.toContain('已经掌握的整式')
    await weak.findAll('button').find(item => item.text().includes('待巩固的有理数'))!.trigger('click')
    expect(api.push).toHaveBeenCalledWith('/learning/knowledge-points/81')
  })
  it('记录分页并打开逐题详情，简答题不降低客观题得分率', async () => {
    await render(ResultsView)
    expect(api.historyPage).toHaveBeenCalledWith({ page: 1, page_size: 10 })
    expect(wrapper!.text()).toContain('100%')
    expect(wrapper!.text()).toContain('自行检查 1 题')
    await button('查看详情').trigger('click')
    expect(api.push).toHaveBeenCalledWith('/results/17')
    await wrapper!.get('button.btn-next').trigger('click')
    await flushPromises()
    expect(api.historyPage).toHaveBeenLastCalledWith({ page: 2, page_size: 10 })
  })
})
