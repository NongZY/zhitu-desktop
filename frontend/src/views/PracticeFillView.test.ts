import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import PracticeFillView from './PracticeFillView.vue'

const api = vi.hoisted(() => ({ list: vi.fn(), getStructure: vi.fn(), coverage: vi.fn(), jobs: vi.fn(), start: vi.fn(), read: vi.fn(), cancel: vi.fn(), retry: vi.fn(), edit: vi.fn(), confirm: vi.fn(), readAI: vi.fn(), push: vi.fn() }))
vi.mock('../api', () => ({ textbookApi: api }))
vi.mock('../api/practice', () => ({ practiceApi: api }))
vi.mock('../api/desktopSettings', () => ({ desktopSettings: api }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: { textbook: '2' } }), useRouter: () => ({ push: api.push }) }))
let wrapper: VueWrapper
const locator = { source_id: 'source', source_revision: 's1', rendition_revision: 'r1', kind: 'block', unit_id: 'b1' }
const candidate = { id: 'candidate', chapter_id: 8, question: { question_type: 'true_false', stem: '绝对值会是负数吗？', correct_answer: false, options: null, explanation: '距离不小于零', difficulty: 1 }, evidence: [{ id: 'e1', text: '绝对值表示到原点的距离', locator }], method: 'textbook_rules', provenance: {}, saved_question_id: null }
const job = { id: 'job', textbook_id: 2, status: 'completed', message: '已生成 1 道候选', parameters: { mode: 'rules' }, source_changed: false, units: [], candidates: [candidate] }
beforeEach(() => {
  vi.resetAllMocks()
  api.list.mockResolvedValue({ items: [{ id: 2, title: '数学', status: 'ready' }] })
  api.getStructure.mockResolvedValue({ chapters: [{ id: 8, title: '数轴' }] })
  api.coverage.mockResolvedValue({ title: '数学', rendition_revision: 'r1', ready_questions: 0, estimated_requests: 1, chapters: [{ chapter_id: 8, title: '数轴', excerpts: candidate.evidence, supported_topics: ['绝对值'], body_blocks: 1, selected_blocks: 1, ready_questions: 0 }] })
  api.jobs.mockResolvedValue([]); api.start.mockResolvedValue(job); api.read.mockResolvedValue(job)
  api.readAI.mockResolvedValue({ base_url: 'https://api.example.com/v1', model: 'model', practice_enabled: true, key_configured: true })
  api.edit.mockImplementation(async (_id, question) => ({ ...candidate, question }))
  api.confirm.mockResolvedValue({ saved: 1 })
})
afterEach(() => wrapper?.unmount())
async function render() { wrapper = mount(PracticeFillView, { global: { plugins: [ElementPlus] } }); await flushPromises() }
it('预览实际原文，候选需选中并确认才进入题库，判断答案 false 保留', async () => {
  await render()
  expect(wrapper.text()).toContain('绝对值表示到原点的距离')
  await wrapper.get('[data-test="start-fill"]').trigger('click'); await flushPromises()
  expect(api.start).toHaveBeenCalledWith(2, expect.objectContaining({ mode: 'rules', external_consent: false, question_types: expect.arrayContaining(['single_choice', 'multiple_choice', 'true_false', 'fill_blank', 'short_answer']) }))
  expect(api.confirm).not.toHaveBeenCalled()
  expect(wrapper.text()).toContain('绝对值会是负数吗')
  expect(wrapper.get('[data-test="confirm-candidates"]').attributes('disabled')).toBeDefined()
  await wrapper.get('[data-test="select-candidate"]').setValue(true)
  await wrapper.get('[data-test="confirm-candidates"]').trigger('click'); await flushPromises()
  expect(api.edit).toHaveBeenCalledWith('candidate', expect.objectContaining({ correct_answer: false }))
  expect(api.confirm).toHaveBeenCalledWith('job', ['candidate'])
})
it('AI 模式明确服务地址和费用，未同意不能开始', async () => {
  await render()
  await wrapper.get('[data-test="fill-mode"]').setValue('ai'); await flushPromises()
  expect(wrapper.text()).toContain('https://api.example.com/v1')
  expect(wrapper.get('[data-test="start-fill"]').attributes('disabled')).toBeDefined()
  await wrapper.get('[data-test="fill-consent"]').setValue(true)
  expect(wrapper.get('[data-test="start-fill"]').attributes('disabled')).toBeUndefined()
})
it('旧来源候选只读，不能确认到当前教材', async () => {
  api.jobs.mockResolvedValue([{ id: 'job', status: 'obsolete' }])
  api.read.mockResolvedValue({ ...job, source_changed: true, status: 'obsolete' })
  await render()
  expect(wrapper.text()).toContain('教材或章节已更新')
  expect(wrapper.get('[data-test="select-candidate"]').attributes('disabled')).toBeDefined()
})
it('开始请求失联后重试沿用请求编号，不重复创建付费任务', async () => {
  api.start.mockRejectedValueOnce(new Error('连接中断')).mockResolvedValue(job)
  await render()
  await wrapper.get('[data-test="start-fill"]').trigger('click'); await flushPromises()
  await wrapper.get('[data-test="start-fill"]').trigger('click'); await flushPromises()
  expect(api.start.mock.calls[0][1].request_id).toBe(api.start.mock.calls[1][1].request_id)
})
