import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import OriginalPdfReader from './OriginalPdfReader.vue'
import { http } from '../api/http'

afterEach(() => vi.unstubAllGlobals())
it('PDF 引用从固定版本加载原页，查找也不跳到当前教材', async () => {
  vi.stubGlobal('URL', class extends URL {
    static createObjectURL = () => 'blob:retained-page'
    static revokeObjectURL = () => {}
  })
  http.defaults.adapter = async config => {
    let data: unknown
    if (config.url === '/textbooks/2/document/versions/old/pages/9/image') data = new Blob(['page'])
    else if (config.url === '/textbooks/2/document/search' && config.params.revision === 'old') {
      data = { items: [{ excerpt: '原版本内容', locator: { unit_id: '9' } }], total: 1 }
    } else throw new Error('不得读取当前版本')
    return { data, config, status: 200, statusText: 'OK', headers: {} }
  }
  const wrapper = mount(OriginalPdfReader, { props: { bookId: 2, page: 9, pageCount: 10, navigationId: 1, version: 'old' } })
  await flushPromises()
  expect(wrapper.find('img').exists()).toBe(true)
  await wrapper.get('[aria-label="搜索课本内容"]').setValue('原版本')
  await wrapper.get('.reader-search').trigger('submit')
  await flushPromises()
  expect(wrapper.text()).toContain('原版本内容')
  wrapper.unmount()
})
