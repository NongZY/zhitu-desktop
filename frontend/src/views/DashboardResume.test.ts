import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import DashboardView from './DashboardView.vue'

const api = vi.hoisted(() => ({ home: vi.fn(), dashboard: vi.fn(), mastery: vi.fn(), push: vi.fn() }))
const documents = vi.hoisted(() => ({ recent: vi.fn() }))
vi.mock('../api/documents', () => ({ documentsApi: documents, documentLink: () => '/textbooks/9?unit=b5' }))
vi.mock('../api', () => ({ readingApi: api, learningApi: api }))
vi.mock('../stores/workspace', () => ({ useWorkspaceStore: () => ({ ownerId: 17, label: '本地学习空间' }) }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: api.push }) }))
let wrapper: VueWrapper | undefined
beforeEach(() => {
  vi.resetAllMocks()
  api.home.mockResolvedValue({ textbook_count: 0, continue_reading: null, reading_notice: null })
  api.dashboard.mockResolvedValue({ textbook_count: 0, completed_exam_count: 0, average_score: 0, study_minutes: 0 })
  api.mastery.mockResolvedValue([])
  documents.recent.mockResolvedValue(null)
})
afterEach(() => wrapper?.unmount())
async function render() {
  wrapper = mount(DashboardView, { global: { plugins: [ElementPlus], stubs: { BaseChart: true } } })
  await flushPromises()
}
async function click(label: string) { await wrapper!.findAll('button').find(b => b.text() === label)!.trigger('click') }
describe('首页继续阅读', () => {
  it('最近阅读 Word 或文本时能进入对应段落', async () => {
    documents.recent.mockResolvedValue({ textbook_id: 9, title: '语言学习', kind: 'block', unit_id: 'b5', updated_at: '2026-10-24T00:00:00Z' })
    await render()
    expect(wrapper!.text()).toContain('语言学习')
    await click('继续阅读')
    expect(api.push).toHaveBeenCalledWith('/textbooks/9?unit=b5')
  })
  it('图表失败也显示最近原页的继续入口', async () => {
    api.home.mockResolvedValue({ textbook_count: 1, reading_notice: null, continue_reading: {
      textbook_id: 2, title: '数学', page_number: 15, page_count: 200, chapter_title: '有理数',
      chapter_id: 8, revision: 1, document_revision: 'v1', updated_at: '2026-10-15T00:00:00Z',
    } })
    api.dashboard.mockRejectedValue(new Error('offline')); api.mastery.mockRejectedValue(new Error('offline'))
    await render()
    expect(wrapper!.text()).toContain('PDF 第 15 页')
    await click('继续阅读')
    expect(api.push).toHaveBeenCalledWith('/textbooks/2?page=15')
  })
  it.each([[0, '上传第一本教材'], [2, '打开教材']])('教材数量 %s 有清晰入口', async (count, label) => {
    api.home.mockResolvedValue({ textbook_count: count, continue_reading: null, reading_notice: null })
    await render(); await click(String(label))
    expect(api.push).toHaveBeenCalledWith('/textbooks')
  })
  it('继续阅读接口失败仍可打开教材和练习，并可重试', async () => {
    api.home.mockRejectedValueOnce(new Error('offline'))
    await render()
    expect(wrapper!.text()).toContain('阅读位置暂时没有加载出来')
    await click('打开教材'); expect(api.push).toHaveBeenCalledWith('/textbooks')
    await click('做练习'); expect(api.push).toHaveBeenCalledWith('/exam/generate')
    await click('重试读取位置'); await flushPromises()
    expect(wrapper!.text()).toContain('上传第一本教材')
  })
})
