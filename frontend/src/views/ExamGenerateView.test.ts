import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import ExamGenerateView from './ExamGenerateView.vue'

const api = vi.hoisted(() => ({ list: vi.fn(), structure: vi.fn(), generate: vi.fn(), push: vi.fn(), query: { textbook: '2', chapter: '8', knowledgePoint: undefined as string | undefined } }))
vi.mock('../api', () => ({
  textbookApi: { list: api.list, getStructure: api.structure },
  examApi: { generate: api.generate },
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: api.query }),
  useRouter: () => ({ push: api.push }),
}))
let wrapper: VueWrapper
const render = () => (wrapper = mount(ExamGenerateView, { global: { plugins: [ElementPlus] } }))
const button = (label: string) => wrapper.findAll('button').find(b => b.text() === label)!
beforeEach(() => {
  vi.resetAllMocks()
  api.query.knowledgePoint = undefined
  api.list.mockResolvedValue({ items: [{ id: 2, title: '数学', status: 'review' }] })
  api.structure.mockResolvedValue({ chapters: [{ id: 8, title: '绝对值', children: [] }] })
  api.generate.mockResolvedValue({ id: 42 })
})
afterEach(() => wrapper?.unmount())

describe('学生开始练习', () => {
  it('课本还在加载时，不显示没有课本', () => {
    api.list.mockReturnValue(new Promise(() => {}))
    render()
    expect(wrapper.text()).not.toContain('先上传一本课本')
    expect(wrapper.text()).toContain('正在加载课本')
  })
  it('章节加载失败时不能默默改为整本练习，并允许重试', async () => {
    api.structure.mockRejectedValueOnce(new Error('连接中断'))
    render()
    await flushPromises()
    expect(button('开始练习').attributes('disabled')).toBeDefined()
    await button('重新加载章节').trigger('click')
    await flushPromises()
    expect(button('开始练习').attributes('disabled')).toBeUndefined()
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(api.generate).toHaveBeenCalledWith(expect.objectContaining({
      textbook_id: 2, chapter_ids: [8], question_count: 5, auto_fill: false,
    }))
    expect(api.push).toHaveBeenCalledWith('/exam/42/take')
  })
  it('课本加载失败不提示重新上传，允许重新加载', async () => {
    api.list.mockRejectedValueOnce(new Error('连接中断'))
    render()
    await flushPromises()
    expect(wrapper.text()).not.toContain('先上传一本课本')
    await button('重新加载课本').trigger('click')
    await flushPromises()
    expect(button('开始练习')).toBeDefined()
  })
  it('默认提供五种题型，选择题型后把选择传给组题接口', async () => {
    render()
    await flushPromises()
    const choices = wrapper.findAll('input[type="checkbox"]')
    expect(choices).toHaveLength(5)
    expect(choices.every(c => (c.element as HTMLInputElement).checked)).toBe(true)
    await choices[1].setValue(false)
    await wrapper.get('form').trigger('submit')
    expect(api.generate).toHaveBeenCalledWith(expect.objectContaining({
      question_types: ['single_choice', 'true_false', 'fill_blank', 'short_answer'],
    }))
  })
  it('从知识点进入练习时保留本地知识点，不扩大成整章', async () => {
    api.query.knowledgePoint = '19'
    api.structure.mockResolvedValue({ chapters: [{ id: 8, title: '绝对值', knowledge_points: [{ id: 19, name: '绝对值的计算' }] }] })
    render()
    await flushPromises()
    expect(wrapper.text()).toContain('绝对值的计算')
    await wrapper.get('form').trigger('submit')
    expect(api.generate).toHaveBeenCalledWith(expect.objectContaining({ knowledge_point_ids: [19], chapter_ids: [8] }))
  })
  it('知识点失效时不静默生成其他内容', async () => {
    api.query.knowledgePoint = '999'
    render()
    await flushPromises()
    expect(button('开始练习').attributes('disabled')).toBeDefined()
    await wrapper.get('form').trigger('submit')
    expect(api.generate).not.toHaveBeenCalled()
  })
})
