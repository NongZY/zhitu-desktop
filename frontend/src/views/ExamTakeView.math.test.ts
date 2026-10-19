import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import ExamTakeView from './ExamTakeView.vue'

vi.mock('../api', () => ({ examApi: { get: vi.fn().mockResolvedValue({
  id: 1, title: '乘方练习', total_score: 1, duration_minutes: 10,
  questions: [{ id: 1, stem: '计算：(-1)^4。', type: 'single_choice', score: 1,
    difficulty: 1, options: [{ key: 'A', text: '2^2' }] }],
}) } }))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: { id: '1' } }), useRouter: () => ({ push: vi.fn() }) }))
let wrapper: VueWrapper
afterEach(() => wrapper?.unmount())
describe('练习页面的数学显示', () => {
  it('把题干和选项的乘方显示成上标，保留底数括号', async () => {
    wrapper = mount(ExamTakeView, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(wrapper.get('h1').find('math msup').exists()).toBe(true)
    expect(wrapper.get('h1').get('annotation').text()).toBe('(-1)^{4}')
    expect(wrapper.get('.choice-list').find('math msup').exists()).toBe(true)
  })
})
