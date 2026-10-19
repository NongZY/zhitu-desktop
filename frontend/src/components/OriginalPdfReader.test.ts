import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import OriginalPdfReader from './OriginalPdfReader.vue'

const api = vi.hoisted(() => ({ reader: vi.fn(), pageImage: vi.fn(), searchPages: vi.fn() }))
vi.mock('../api', () => ({ textbookApi: api }))
let wrapper: VueWrapper
const button = (text: string) => wrapper.findAll('button').find(b => b.text() === text)!
const chapter = { id: 8, title: '正数和负数', page_start: 9 }
beforeEach(() => {
  vi.resetAllMocks()
  vi.stubGlobal('URL', class extends URL {
    static createObjectURL = vi.fn(() => 'blob:page')
    static revokeObjectURL = vi.fn()
  })
  api.reader.mockResolvedValue({ page_count: 20 })
  api.pageImage.mockResolvedValue(new Blob(['image']))
  api.searchPages.mockResolvedValue({ items: [{ page_number: 17, excerpt: '相反数', chapter_title: '有理数' }], total: 1 })
})
afterEach(() => { wrapper?.unmount(); vi.unstubAllGlobals() })
async function render(control = true, pageCount = 20) {
  let navigation = 1
  wrapper = mount(OriginalPdfReader, { props: { bookId: '2', chapter, page: pageCount ? 9 : null, pageCount, navigationId: 1,
    onNavigate: (page: number) => { if (control) void wrapper.setProps({ page, navigationId: ++navigation }) },
  } })
  await flushPromises()
}
describe('原页阅读', () => {
  it('按章节开页、翻页、跳页并保留颜色', async () => {
    await render()
    expect(wrapper.get('img').attributes('alt')).toContain('第 9 页')
    await button('下一页').trigger('click'); await flushPromises()
    expect(wrapper.get('img').attributes('alt')).toContain('第 10 页')
    await wrapper.get('[aria-label="PDF 页码"]').setValue(999)
    await button('跳转').trigger('submit'); await flushPromises()
    expect(wrapper.get('img').attributes('alt')).toContain('第 20 页')
    await wrapper.get('[type=checkbox]').setValue(true)
    expect(wrapper.get('.page-viewport').classes()).toContain('warm')
    expect(wrapper.get('img').attributes('style')).not.toContain('filter')
  })
  it('搜索点击请求跳页，章节高亮本身不会覆盖父级页码', async () => {
    await render()
    await wrapper.get('[aria-label="搜索课本内容"]').setValue('相反数')
    await wrapper.get('.reader-search').trigger('submit'); await flushPromises()
    expect(wrapper.text()).toContain('找到 1 页')
    await wrapper.get('.search-results>button').trigger('click'); await flushPromises()
    expect(wrapper.get('img').attributes('alt')).toContain('第 17 页')
    await wrapper.setProps({ chapter: { id: 9, title: '绝对值', page_start: 18 } }); await flushPromises()
    expect(wrapper.get('img').attributes('alt')).toContain('第 17 页')
    await wrapper.setProps({ page: 18, navigationId: 3 }); await flushPromises()
    expect(wrapper.get('img').attributes('alt')).toContain('第 18 页')
    expect(wrapper.find('.search-results').exists()).toBe(false)
  })
  it('忽略旧页响应并释放图片地址', async () => {
    await render()
    let finish!: (blob: Blob) => void
    api.pageImage.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    await button('下一页').trigger('click')
    await button('下一页').trigger('click'); await flushPromises()
    finish(new Blob(['old'])); await flushPromises()
    expect(wrapper.get('img').attributes('alt')).toContain('第 11 页')
    expect(URL.createObjectURL).toHaveBeenCalledTimes(2)
    wrapper.unmount()
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(2)
  })
  it('无PDF可以阅读辅助笔记，文件错误可重试', async () => {
    api.reader.mockResolvedValue({ page_count: 0 })
    await render(true, 0)
    expect(wrapper.text()).toContain('还没有 PDF 原文件')
    expect(api.pageImage).not.toHaveBeenCalled()
  })
  it('只有当前图片真正显示才报告保存，旧事件和失败图片不能保存', async () => {
    await render(false)
    const old = wrapper.get('img')
    expect(wrapper.emitted('page-displayed')).toBeUndefined()
    await old.trigger('load')
    await old.trigger('load')
    expect(wrapper.emitted('page-displayed')).toEqual([[{ page: 9, navigationId: 1 }]])
    await button('下一页').trigger('click'); await flushPromises()
    expect(wrapper.emitted('navigate')).toEqual([[10]])
    expect(wrapper.get('img').attributes('alt')).toContain('第 9 页')
    await wrapper.setProps({ page: 10, navigationId: 2 }); await flushPromises()
    await old.trigger('load')
    expect(wrapper.emitted('page-displayed')).toHaveLength(1)
    await wrapper.get('img').trigger('error')
    expect(wrapper.text()).toContain('图片未能显示')
    expect(wrapper.emitted('page-displayed')).toHaveLength(1)
  })
})
