import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { reactive } from 'vue'
import DocumentStudyView from './DocumentStudyView.vue'
import { http } from '../api/http'

const navigation = vi.hoisted(() => ({ push: vi.fn(), leave: vi.fn() }))
const route = reactive({ params: { id: '5' }, query: {} as Record<string, string> })
vi.mock('vue-router', () => ({ useRouter: () => navigation, useRoute: () => route, onBeforeRouteLeave: () => {}, onBeforeRouteUpdate: () => {} }))
const document = { textbook_id: 5, format: 'txt', original_name: '笔记.txt', source_id: 's1', source_revision: 'a'.repeat(64), rendition_revision: 'b'.repeat(64), warnings: [], chapters: [
  { id: 1, title: '第一章', level: 1, locator: { source_id: 's1', source_revision: 'a'.repeat(64), rendition_revision: 'b'.repeat(64), kind: 'block', unit_id: 'b1' } },
  { id: 2, title: '第二章', level: 1, locator: { source_id: 's1', source_revision: 'a'.repeat(64), rendition_revision: 'b'.repeat(64), kind: 'block', unit_id: 'b3' } },
], blocks: [{ id: 'b1', kind: 'heading', text: '第一章', chapter_id: 1 }, { id: 'b2', kind: 'paragraph', text: '旧内容', chapter_id: 1 }, { id: 'b3', kind: 'heading', text: '第二章', chapter_id: 2 }, { id: 'b4', kind: 'paragraph', text: '阅读目标', chapter_id: 2 }] }

beforeEach(() => { vi.clearAllMocks(); route.query = {} })
describe('多格式续读', () => {
  it('阅读旧版本只查找该版本，不覆盖当前阅读进度', async () => {
    const requests: { method?: string; params: unknown }[] = []
    http.defaults.adapter = async config => {
      requests.push({ method: config.method, params: config.params })
      return { data: config.url?.endsWith('/search') ? { items: [], total: 0 } : null, status: 200, statusText: 'OK', headers: {}, config }
    }
    const wrapper = mount(DocumentStudyView, { props: { initialDocument: { ...document, is_current: false } }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(wrapper.text()).toContain('旧版本')
    await wrapper.findAll('button').find(b => b.text() === '第二章')!.trigger('click')
    await wrapper.find('input').setValue('目标')
    await wrapper.findAll('button').find(b => b.text() === '查找')!.trigger('click')
    await flushPromises()
    expect(requests.some(r => r.method === 'put')).toBe(false)
    expect(requests.some(r => (r.params as { revision?: string })?.revision === document.rendition_revision)).toBe(true)
    wrapper.unmount()
  })
  it('点击已经显示的第一章也保存位置', async () => {
    let writes = 0
    http.defaults.adapter = async config => {
      if (config.method === 'put') writes++
      return { data: config.method === 'put' ? { revision: 1 } : null, status: 200, statusText: 'OK', headers: {}, config }
    }
    const wrapper = mount(DocumentStudyView, { props: { initialDocument: document }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    await wrapper.findAll('button').find(b => b.text() === '第一章')!.trigger('click')
    await flushPromises()
    expect(writes).toBe(1)
    wrapper.unmount()
  })
  it('读取已保存位置并在跳转保存失败时提示重试', async () => {
    http.defaults.adapter = async config => {
      if (config.url?.endsWith('/position') && config.method === 'put') throw new Error('disk full')
      const data = config.url?.endsWith('/position') ? { ...document.chapters[0]!.locator, source_id: 's1', source_revision: 'a'.repeat(64), rendition_revision: 'b'.repeat(64), revision: 1, source_changed: false } : document
      return { data, status: 200, statusText: 'OK', headers: {}, config }
    }
    const wrapper = mount(DocumentStudyView, { props: { initialDocument: document }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    await wrapper.findAll('button').find(b => b.text() === '第二章')!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('阅读目标')
    expect(wrapper.text()).toContain('未保存')
    expect(wrapper.text()).toContain('重试保存')
    wrapper.unmount()
  })
  it('教材版本改变时解释并等待选择，不静默覆盖旧位置', async () => {
    let writes = 0
    http.defaults.adapter = async config => {
      if (config.method === 'put') writes++
      return { data: { source_changed: true, rendition_revision: 'old', revision: 4, unit_id: 'b3', kind: 'block' }, status: 200, statusText: 'OK', headers: {}, config }
    }
    const wrapper = mount(DocumentStudyView, { props: { initialDocument: document }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(wrapper.text()).toContain('资料已更新')
    expect(writes).toBe(0)
    wrapper.unmount()
  })
})
