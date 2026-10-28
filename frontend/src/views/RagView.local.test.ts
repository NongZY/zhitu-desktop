import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import RagView from './RagView.vue'
const api = vi.hoisted(() => ({ list: vi.fn(), ask: vi.fn(), readAI: vi.fn(), push: vi.fn() }))
vi.mock('../api', () => ({ textbookApi: api, ragApi: api }))
vi.mock('../api/desktopSettings', () => ({ desktopSettings: api }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: {} }), useRouter: () => ({ push: api.push }) }))
let wrapper: VueWrapper
beforeEach(() => {
  vi.resetAllMocks()
  HTMLElement.prototype.scrollTo = vi.fn()
  api.list.mockResolvedValue({ items: [{ id: 2, title: '数学', status: 'ready' }] })
  api.readAI.mockResolvedValue({ qa_enabled: true, key_configured: true, base_url: 'https://api.example.com/v1', model: 'test' })
  api.ask.mockResolvedValue({ answer: '本地原文', citations: [], mode: 'local', notice: '接口无法连接，已显示本地资料。' })
})
afterEach(() => wrapper?.unmount())
it('默认只查本地，即使接口已经开启；失败时显示本地降级状态', async () => {
  wrapper = mount(RagView, { global: { plugins: [ElementPlus] } }); await flushPromises()
  await wrapper.get('textarea').setValue('什么是绝对值？')
  await wrapper.get('.composer>button').trigger('click'); await flushPromises()
  expect(api.ask).toHaveBeenCalledWith(expect.objectContaining({ use_ai: false }))
  expect(wrapper.text()).toContain('本地资料')
  expect(wrapper.text()).toContain('接口无法连接')
  await wrapper.get('[data-test="use-ai"]').setValue(true)
  await wrapper.get('textarea').setValue('请解释这个定义')
  await wrapper.get('.composer>button').trigger('click'); await flushPromises()
  expect(api.ask).toHaveBeenLastCalledWith(expect.objectContaining({ use_ai: true, textbook_id: 2 }))
})
