import { beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { reactive } from 'vue'
import ElementPlus from 'element-plus'
import TextbookEntryView from './TextbookEntryView.vue'
import { http } from '../api/http'

const route = reactive({ params: { id: '1' }, query: {} as Record<string, string>, fullPath: '/textbooks/1' })
vi.mock('vue-router', () => ({ useRoute: () => route }))
beforeEach(() => { route.params.id = '1'; route.fullPath = '/textbooks/1'; route.query = {} })

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
