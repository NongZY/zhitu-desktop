import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElMessageBox } from 'element-plus'
import ExamTakeView from './ExamTakeView.vue'
import { requestClose } from '../runtime/close'

const api = vi.hoisted(() => ({ get: vi.fn(), submit: vi.fn(), push: vi.fn() }))
vi.mock('../api', () => ({ examApi: { get: api.get, submit: api.submit } }))
vi.mock('vue-router', () => ({ onBeforeRouteLeave: vi.fn(), useRoute: () => ({ params: { id: '7' } }), useRouter: () => ({ push: api.push }) }))
let wrapper: VueWrapper
const questions = [
  { id: 1, stem: '选择正确答案', type: 'single_choice', options: [{ key: 'A', text: '一' }, { key: 'B', text: '二' }] },
  { id: 2, stem: '选择所有正确答案', type: 'multiple_choice', options: [{ key: 'A', text: '一' }, { key: 'B', text: '二' }] },
  { id: 3, stem: '判断这个说法', type: 'true_false' },
  { id: 4, stem: '计算填空', type: 'fill_blank' },
  { id: 5, stem: '说明过程', type: 'short_answer' },
].map(q => ({ ...q, difficulty: 2, score: 5 }))
const next = async () => { await wrapper.findAll('button').find(b => b.text() === '下一题')!.trigger('click') }
const finish = async () => { await wrapper.findAll('button').find(b => b.text() === '完成练习')!.trigger('click'); await flushPromises() }
beforeEach(() => {
  vi.resetAllMocks()
  // Element Plus declares the shortcut result as both an action and input data.
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue(Object.assign('confirm', { action: 'confirm' as const, value: '' }))
  api.get.mockResolvedValue({ id: 7, title: '混合练习', questions, duration_minutes: 20, total_score: 25 })
  api.submit.mockResolvedValue({ id: 8, paper_id: 7, score: 20, total_score: 25, graded_total_score: 20,
    pending_count: 1, correct_count: 4, wrong_count: 0, duration_seconds: 60, status: 'pending_self_check',
    details: questions.map(q => ({ question_id: q.id, user_answer: q.id === 3 ? false : '答案',
      correct_answer: q.id === 3 ? false : '答案', is_correct: q.id === 5 ? null : true, score: q.id === 5 ? 0 : 5, max_score: 5 })),
  })
})
afterEach(() => { wrapper?.unmount(); delete window.pywebview; vi.restoreAllMocks(); vi.useRealTimers() })
describe('混合题型练习', () => {
  it('关闭未提交练习说明不保存，可继续或放弃，不能自动交卷', async () => {
    const decisions: string[] = []
    window.pywebview = { api: { get_context: async () => ({}), respond_close: async (_id, value) => { if (value !== 'pending') decisions.push(value) } } }
    wrapper = mount(ExamTakeView, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await requestClose('exam-stay')
    expect(decisions).toEqual(['stay'])
    expect(ElMessageBox.confirm).toHaveBeenLastCalledWith(expect.stringContaining('当前作答不会保存'), expect.any(String), expect.any(Object))
    await requestClose('exam-discard')
    expect(decisions).toEqual(['stay', 'discard'])
    expect(api.submit).not.toHaveBeenCalled()
  })
  it('保留单选、多选、false 判断、填空、简答的答案格式', async () => {
    wrapper = mount(ExamTakeView, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    await wrapper.findAll('input[type="radio"]')[1].setValue()
    await next()
    for (const checkbox of wrapper.findAll('input[type="checkbox"]')) await checkbox.setValue(true)
    await next()
    await wrapper.findAll('input[type="radio"]')[1].setValue()
    await next()
    await wrapper.get('textarea').setValue('-3')
    await next()
    await wrapper.get('textarea').setValue('先计算绝对值，再比较大小。')
    await finish()
    expect(api.submit).toHaveBeenCalledWith(7, expect.objectContaining({ answers: [
      { question_id: 1, answer: 'B' }, { question_id: 2, answer: ['A', 'B'] },
      { question_id: 3, answer: false }, { question_id: 4, answer: '-3' },
      { question_id: 5, answer: '先计算绝对值，再比较大小。' },
    ] }))
  })
  it('简答题单独提示自行核对，不降低客观题得分率', async () => {
    wrapper = mount(ExamTakeView, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    await finish()
    expect(wrapper.get('.result-hero').text()).toContain('客观题得分 20 / 20')
    expect(wrapper.get('.score-ring').text()).toContain('100%')
    expect(wrapper.get('.result-hero').text()).toContain('自行核对')
    expect(wrapper.findAll('.result-item.manual')).toHaveLength(1)
    expect(wrapper.findAll('.result-item')[2].text()).toContain('你的答案：错误')
  })
  it('填空题允许按空的顺序逐行作答并保留顺序', async () => {
    api.get.mockResolvedValue({ id: 7, title: '两空练习', questions: [questions[3]], duration_minutes: 20, total_score: 5 })
    wrapper = mount(ExamTakeView, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(wrapper.text()).toContain('每空一行')
    await wrapper.get('textarea').setValue('2\n-2')
    await finish()
    expect(api.submit).toHaveBeenCalledWith(7, expect.objectContaining({ answers: [{ question_id: 4, answer: '2\n-2' }] }))
  })
  it('只有简答题时不显示误导性的零分', async () => {
    api.get.mockResolvedValue({ id: 7, title: '简答练习', questions: [questions[4]], duration_minutes: 20, total_score: 5 })
    api.submit.mockResolvedValue({ id: 8, paper_id: 7, score: 0, total_score: 5, graded_total_score: 0,
      pending_count: 1, correct_count: 0, wrong_count: 0, duration_seconds: 60,
      details: [{ question_id: 5, user_answer: '我的过程', correct_answer: '参考过程', is_correct: null, score: 0, max_score: 5 }],
    })
    wrapper = mount(ExamTakeView, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    await finish()
    expect(wrapper.get('.result-hero').text()).toContain('练习已提交')
    expect(wrapper.find('.score-ring').exists()).toBe(false)
    expect(wrapper.get('.result-hero').text()).not.toContain('得分 0')
  })
})
