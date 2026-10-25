import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { defineComponent, reactive } from 'vue'
import ElementPlus from 'element-plus'
import TextbookDetailView from './TextbookDetailView.vue'

const api = vi.hoisted(() => ({ structure: vi.fn(), content: vi.fn(), pageImage: vi.fn(), readerInfo: vi.fn(), search: vi.fn(), push: vi.fn(), replace: vi.fn(), query: {} as Record<string, string>, params: { id: '2' }, getProgress: vi.fn(), saveProgress: vi.fn() }))
let leaveGuard: () => Promise<boolean>
vi.mock('../api', () => ({
  textbookApi: { getStructure: api.structure, chapterContent: api.content, pageImage: api.pageImage, reader: api.readerInfo, searchPages: api.search },
  readingApi: { getProgress: api.getProgress, saveProgress: api.saveProgress },
}))
vi.mock('../stores/workspace', () => ({ useWorkspaceStore: () => ({ ownerId: 17, label: '本地学习空间' }) }))
vi.mock('vue-router', () => ({
  onBeforeRouteLeave: (guard: () => Promise<boolean>) => { leaveGuard = guard }, onBeforeRouteUpdate: vi.fn(),
  useRoute: () => ({ params: api.params, get query() { return api.query } }),
  useRouter: () => ({ push: api.push, replace: api.replace }),
}))

const Dialog = defineComponent({
  props: ['modelValue', 'title'],
  emits: ['update:modelValue'],
  template: '<section v-if="modelValue" role="dialog"><h2>{{ title }}</h2><button @click="$emit(\'update:modelValue\', false)">关闭原页</button><slot /><slot name="footer" /></section>',
})
let wrapper: VueWrapper | undefined
const button = (label: string) => wrapper!.findAll('button').find(item => item.text() === label)!

beforeEach(() => {
  vi.resetAllMocks()
  api.query = reactive({}); api.params = reactive({ id: '2' })
  const update = async (location: { query?: Record<string, string> }) => {
    Object.keys(api.query).forEach(key => delete api.query[key])
    Object.assign(api.query, location.query || {})
  }
  api.push.mockImplementation(update); api.replace.mockImplementation(update)
  api.getProgress.mockResolvedValue({ progress: null })
  api.saveProgress.mockImplementation(async (_id, payload) => ({ ...payload, textbook_id: 2, revision: 1, updated_at: '2026-10-15T00:00:00Z' }))
  vi.stubGlobal('URL', class extends URL {
    static createObjectURL = vi.fn(() => 'blob:original-page')
    static revokeObjectURL = vi.fn()
  })
  api.structure.mockResolvedValue({
    textbook: { id: 2, title: '数学', status: 'ready' },
    chapters: [{ id: 8, title: '分数与根式', page_start: 9, children: [] }],
  })
  api.content.mockResolvedValue({
    items: [
      { id: 1, page_number: 1, content: 'a / b', quality_note: '本页有公式或符号需要对照原页，请勿仅凭提取文字计算。' },
      { id: 2, page_number: 2, content: '第二页正文' },
    ], total: 2,
  })
  api.readerInfo.mockResolvedValue({ page_count: 20, document_revision: 'v1' })
  api.pageImage.mockResolvedValue(new Blob(['image'], { type: 'image/png' }))
})
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.unstubAllGlobals() })

const render = async () => {
  wrapper = mount(TextbookDetailView, { global: { plugins: [ElementPlus], stubs: { ElDialog: Dialog } } })
  await flushPromises()
}

describe('查看教材原页', () => {
  it('使用当前文件目录，不把旧学习章节的页码用于新 PDF', async () => {
    api.structure.mockResolvedValue({
      textbook: { id: 2, title: '新资料', status: 'ready' },
      chapters: [{ id: 8, title: '旧目录', page_start: 9, children: [] }],
      reader_chapters: [{ id: 20, title: '新目录', page_start: 2, children: [] }],
    })
    await render()
    expect(wrapper!.find('img[alt="课本原页：PDF 第 2 页"]').exists()).toBe(true)
    expect(wrapper!.find('.chapter-tree').text()).toContain('新目录')
    expect(wrapper!.find('.chapter-tree').text()).not.toContain('旧目录')
  })
  it('离开阅读页等原页的保存响应，不能在防抖前卸载丢位置', async () => {
    await render()
    await wrapper!.get('img').trigger('load')
    let finish!: (value: unknown) => void
    api.saveProgress.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    let left = false
    const leaving = leaveGuard().then(value => { left = value })
    await flushPromises()
    expect(left).toBe(false)
    expect(api.saveProgress).toHaveBeenCalledWith(2, expect.objectContaining({ page_number: 9 }), expect.any(AbortSignal))
    finish({ textbook_id: 2, page_number: 9, chapter_id: null, document_revision: 'v1', revision: 1, updated_at: '2026-10-20T00:00:00Z' })
    await leaving
    expect(left).toBe(true)
  })
  it('从知识点详情返回教材时定位到指定章节的原页', async () => {
    api.query.chapter = '9'
    api.structure.mockResolvedValue({
      textbook: { id: 2, title: '数学', status: 'ready' },
      chapters: [{ id: 8, title: '第一章', page_start: 9 }, { id: 9, title: '第二章', page_start: 15 }],
    })
    await render()
    expect(api.pageImage).toHaveBeenCalledWith('2', 15, expect.any(AbortSignal))
  })
  it('默认打开当前章节的 PDF 原页，提取文字仅在主动展开后显示', async () => {
    await render()
    expect(wrapper!.find('img[alt="课本原页：PDF 第 9 页"]').exists()).toBe(true)
    expect(api.pageImage).toHaveBeenCalledWith('2', 9, expect.any(AbortSignal))
    expect(wrapper!.text()).not.toContain('a / b')
    await button('查看提取文字（辅助）').trigger('click')
    await flushPromises()
    expect(wrapper!.text()).toContain('a / b')
    expect(wrapper!.text()).toContain('本页有公式或符号需要对照原页，请勿仅凭提取文字计算。')
  })
  it.each(['structure', 'readerInfo', 'getProgress'] as const)('晚到的 %s 不覆盖显式页，目录点击覆盖旧 page', async (delayed) => {
    api.query.page = '9'; api.query.chapter = '9'
    const responses = {
      structure: { textbook: { id: 2, title: '数学', status: 'ready' }, chapters: [{ id: 8, title: '第一章', page_start: 4, page_end: 19 }, { id: 9, title: '第二章', page_start: 20, page_end: 20 }] },
      readerInfo: { page_count: 20, document_revision: 'v1' },
      getProgress: { progress: { textbook_id: 2, page_number: 15, chapter_id: 8, revision: 1, document_revision: 'v1', updated_at: '2026-10-15T00:00:00Z' } },
    }
    for (const key of ['structure', 'readerInfo', 'getProgress'] as const) api[key].mockResolvedValue(responses[key])
    let finish!: (value: unknown) => void
    api[delayed].mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    await render(); finish(responses[delayed]); await flushPromises()
    expect(wrapper!.get('img').attributes('alt')).toContain('第 9 页')
    const chapter = wrapper!.findAll('.el-tree-node__content').find(node => node.text().includes('第二章'))!
    await chapter.trigger('click'); await flushPromises()
    expect(api.query.page).toBeUndefined()
    expect(wrapper!.get('img').attributes('alt')).toContain('第 20 页')
  })
  it('读取进度失败不阻断阅读，提示重试；图片未显示不保存', async () => {
    api.getProgress.mockRejectedValue(new Error('offline'))
    await render()
    expect(wrapper!.get('img').attributes('alt')).toContain('第 9 页')
    expect(wrapper!.text()).toContain('暂时无法恢复')
    expect(wrapper!.text()).toContain('重试保存位置')
    expect(api.saveProgress).not.toHaveBeenCalled()
  })
  it('切换教材后忽略旧响应', async () => {
    let finish!: (value: unknown) => void
    api.structure.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    await render()
    api.structure.mockResolvedValue({ textbook: { id: 3, title: '新书', status: 'ready' }, chapters: [] })
    api.params.id = '3'; await flushPromises()
    finish({ textbook: { id: 2, title: '旧书', status: 'ready' }, chapters: [] }); await flushPromises()
    expect(wrapper!.text()).toContain('新书')
    expect(wrapper!.text()).not.toContain('旧书')
    expect(wrapper!.get('img').attributes('alt')).toContain('第 1 页')
  })
  it('发生冲突后重新载入服务器页码，不把旧 URL 页再次覆盖回去', async () => {
    api.query.page = '9'
    api.saveProgress.mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'reading_conflict', message: '其他页面已更新阅读位置，请重新载入' } } } })
    await render()
    vi.useFakeTimers()
    try {
      await wrapper!.get('img').trigger('load')
      await vi.advanceTimersByTimeAsync(1000); await flushPromises()
      expect(wrapper!.text()).toContain('其他页面已更新')
      api.getProgress.mockResolvedValue({ progress: { textbook_id: 2, page_number: 15, chapter_id: null, document_revision: 'v1', revision: 2, updated_at: '2026-10-15T00:00:00Z' } })
      await button('重新载入位置').trigger('click'); await flushPromises()
      expect(wrapper!.get('img').attributes('alt')).toContain('第 15 页')
      expect(api.query.page).toBe('15')
    } finally { vi.useRealTimers() }
  })
})
