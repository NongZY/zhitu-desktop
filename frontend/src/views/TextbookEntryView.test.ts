import { beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount, shallowMount } from '@vue/test-utils'
import { reactive } from 'vue'
import ElementPlus from 'element-plus'
import TextbookEntryView from './TextbookEntryView.vue'
import { http } from '../api/http'

const route = reactive({ params: { id: '1' }, query: {} as Record<string, string>, fullPath: '/textbooks/1' })
const navigation = vi.hoisted(() => ({ push: vi.fn() }))
vi.mock('vue-router', () => ({ useRoute: () => route, useRouter: () => navigation }))
beforeEach(() => { route.params.id = '1'; route.fullPath = '/textbooks/1'; route.query = {} })

it('替换旧 PDF 后可从上次阅读提示打开固定版本原页', async () => {
  http.defaults.adapter = async config => ({ config, status: 200, statusText: 'OK', headers: {}, data:
    config.url?.endsWith('/position') ? { source_changed: true, source_id: 'old-source', source_revision: 'a'.repeat(64), rendition_revision: 'b'.repeat(64), kind: 'page', unit_id: '5', revision: 0 }
      : config.url?.endsWith('/state') ? { available: true, format: 'txt', status: 'completed' }
      : { textbook_id: 1, format: 'txt', original_name: '新资料', blocks: [], chapters: [], warnings: [] } })
  const wrapper = mount(TextbookEntryView, { global: { plugins: [ElementPlus], stubs: { DocumentStudyView: true } } })
  await flushPromises()
  const link = wrapper.findAll('button').find(b => b.text() === '查看上次阅读原文')
  expect(link).toBeDefined()
  await link!.trigger('click')
  expect(navigation.push).toHaveBeenCalledWith(expect.stringContaining('source=old-source&version=' + 'b'.repeat(64)))
  wrapper.unmount()
})

it('保留旧正文时仍显示替换失败与重试，后台完成不直接卸载阅读器', async () => {
  vi.useFakeTimers()
  let retried = false, loads = 0
  const old = { textbook_id: 1, format: 'txt', original_name: '旧正文', blocks: [], chapters: [], warnings: [] }
  http.defaults.adapter = async config => {
    if (config.method === 'post') retried = true
    if (config.url?.endsWith('/document')) loads++
    return { config, status: 200, statusText: 'OK', headers: {}, data:
      config.url?.endsWith('/state') ? { available: true, format: 'txt', status: retried ? 'completed' : 'failed', message: retried ? '整理完成' : '请重新选择文字编码', progress: 100 }
        : config.method === 'post' ? { status: 'queued', progress: 0 } : old }
  }
  const wrapper = mount(TextbookEntryView, { global: { plugins: [ElementPlus], stubs: { DocumentStudyView: true, TextbookDetailView: true } } })
  try {
    await flushPromises()
    expect(wrapper.text()).toContain('请重新选择文字编码')
    await wrapper.findAll('button').find(b => b.text() === '重新整理')!.trigger('click')
    await flushPromises()
    await vi.advanceTimersByTimeAsync(2100)
    await flushPromises()
    expect(wrapper.text()).toContain('打开新内容')
    expect(loads).toBe(1)
    expect(wrapper.findComponent({ name: 'DocumentStudyView' }).props('initialDocument').original_name).toBe('旧正文')
  } finally { wrapper.unmount(); vi.useRealTimers() }
})

it('首次 PDF 导入失败显示重新整理，不误入空白阅读页', async () => {
  http.defaults.adapter = async config => ({ config, status: 200, statusText: 'OK', headers: {},
    data: config.url?.endsWith('/state') ? { format: 'pdf', status: 'failed', message: '没有提取到正文', progress: 10, available: false } : null })
  const wrapper = shallowMount(TextbookEntryView, { global: { plugins: [ElementPlus] } })
  await flushPromises()
  expect(wrapper.text()).toContain('没有提取到正文')
  expect(wrapper.findComponent({ name: 'TextbookDetailView' }).exists()).toBe(false)
  wrapper.unmount()
})

it('切换教材时忽略上一份资料晚到的响应', async () => {
  let finish!: (value: unknown) => void
  http.defaults.adapter = async config => ({ config, status: 200, statusText: 'OK', headers: {},
    data: config.url === '/textbooks/1/document' ? await new Promise(resolve => { finish = resolve })
      : config.url?.endsWith('/state') ? { format: 'txt', status: 'completed', available: true }
      : { textbook_id: 2, format: 'txt', original_name: '第二本', blocks: [], chapters: [], warnings: [] } })
  const wrapper = shallowMount(TextbookEntryView, { global: { plugins: [ElementPlus] } })
  await flushPromises()
  route.params.id = '2'; route.fullPath = '/textbooks/2'
  await flushPromises()
  finish({ textbook_id: 1, format: 'txt', original_name: '第一本' })
  await flushPromises()
  expect(wrapper.findComponent({ name: 'DocumentStudyView' }).props('initialDocument').textbook_id).toBe(2)
  wrapper.unmount()
})
