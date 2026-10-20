import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { flushPromises } from '@vue/test-utils'
import { useReadingProgress } from './useReadingProgress'

const api = vi.hoisted(() => ({ getProgress: vi.fn(), saveProgress: vi.fn() }))
vi.mock('../api', () => ({ readingApi: api }))
const saved = (page: number, revision: number) => ({ textbook_id: 2, page_number: page, chapter_id: null, document_revision: 'v1', revision, updated_at: '2026-10-15T00:00:00Z' })
let state: ReturnType<typeof useReadingProgress>
let confirmedPage: number | null = null
const lastConfirmedPage = () => confirmedPage
async function readyReadingAt(page: number) {
  await state.load()
  state.recordDisplayed(page, null)
  await vi.advanceTimersByTimeAsync(1000)
  return state
}
const bookId = ref(2), userId = ref<number | null>(1), documentRevision = ref<string | null>('v1')
beforeEach(() => {
  vi.resetAllMocks(); vi.useFakeTimers()
  bookId.value = 2; userId.value = 1; documentRevision.value = 'v1'
  api.getProgress.mockResolvedValue({ progress: null })
  confirmedPage = null
  api.saveProgress.mockImplementation(async (_id, payload) => {
    const response = saved(payload.page_number, payload.expected_revision + 1)
    confirmedPage = response.page_number
    return response
  })
  state = useReadingProgress({ bookId, userId, documentRevision })
})
afterEach(() => { state.dispose(); vi.useRealTimers() })
describe('阅读位置可靠保存', () => {
  it('关闭时保存尚未到一秒的最后显示页', async () => {
    const reading = await readyReadingAt(15)
    reading.recordDisplayed(16, null)
    expect(await reading.flush()).toBe(true)
    expect(lastConfirmedPage()).toBe(16)
  })
  it('关闭等待在途写入后保存最新显示页', async () => {
    await state.load()
    let finish!: (value: unknown) => void
    api.saveProgress.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    state.recordDisplayed(15, null); await vi.advanceTimersByTimeAsync(1000)
    state.recordDisplayed(16, null)
    const flushing = state.flush()
    finish(saved(15, 1))
    expect(await flushing).toBe(true)
    expect(lastConfirmedPage()).toBe(16)
  })
  it('保存失败不虚报成功，重试能补存', async () => {
    await state.load(); state.recordDisplayed(15, null)
    api.saveProgress.mockRejectedValueOnce(new Error('disk full'))
    expect(await state.flush()).toBe(false)
    expect(lastConfirmedPage()).toBeNull()
    await state.retry()
    expect(lastConfirmedPage()).toBe(15)
  })
  it('冲突或未加载时关闭不能当成保存成功', async () => {
    expect(await state.flush()).toBe(false)
    await state.load(); state.recordDisplayed(15, null)
    api.saveProgress.mockRejectedValueOnce({ response: { status: 409 } })
    expect(await state.flush()).toBe(false)
    expect(state.status.value).toBe('conflict')
  })
  it('写入超时返回失败，不无限卡住窗口', async () => {
    await state.load(); state.recordDisplayed(15, null)
    api.saveProgress.mockReturnValueOnce(new Promise(() => {}))
    const result = state.flush()
    await vi.advanceTimersByTimeAsync(6000)
    expect(await result).toBe(false)
  })
  it('重新打开已保存页也更新最近阅读时间，不能只在翻页时更新首页', async () => {
    api.getProgress.mockResolvedValueOnce({ progress: saved(15, 2) })
    await state.load()
    state.recordDisplayed(15, null)
    await vi.advanceTimersByTimeAsync(1000)
    expect(api.saveProgress).toHaveBeenCalledWith(2, expect.objectContaining({ page_number: 15, expected_revision: 2 }), expect.any(AbortSignal))
    expect(state.progress.value?.revision).toBe(3)
    expect(state.status.value).toBe('saved')
  })
  it('显示后延迟保存，未确认不称为已保存；串行合并最新页', async () => {
    await state.load()
    let finish!: (value: unknown) => void
    api.saveProgress.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    state.recordDisplayed(15, null)
    await vi.advanceTimersByTimeAsync(999)
    expect(api.saveProgress).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    expect(state.status.value).toBe('saving')
    state.recordDisplayed(16, null); state.recordDisplayed(17, null)
    await vi.advanceTimersByTimeAsync(1000)
    expect(api.saveProgress).toHaveBeenCalledTimes(1)
    finish(saved(15, 1)); await flushPromises()
    expect(api.saveProgress).toHaveBeenLastCalledWith(2, expect.objectContaining({ page_number: 17, expected_revision: 1 }), expect.any(AbortSignal))
    expect(state.progress.value?.page_number).toBe(17)
    expect(state.status.value).toBe('saved')
  })
  it('首次读取失败时不以版本零写入，重试后才保存', async () => {
    api.getProgress.mockRejectedValueOnce(new Error('offline'))
    await state.load(); state.recordDisplayed(15, null)
    await vi.advanceTimersByTimeAsync(1000)
    expect(state.status.value).toBe('error')
    expect(api.saveProgress).not.toHaveBeenCalled()
    api.getProgress.mockResolvedValueOnce({ progress: saved(9, 3) })
    await state.retry()
    expect(api.saveProgress).toHaveBeenCalledWith(2, expect.objectContaining({ expected_revision: 3, page_number: 15 }), expect.any(AbortSignal))
  })
  it('冲突停止写入，只有显式重新载入能解除', async () => {
    await state.load()
    api.saveProgress.mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'reading_conflict', message: '其他页面已更新阅读位置，请重新载入' } } } })
    state.recordDisplayed(15, null); await vi.advanceTimersByTimeAsync(1000)
    expect(state.status.value).toBe('conflict')
    state.recordDisplayed(16, null); await vi.advanceTimersByTimeAsync(1000)
    expect(api.saveProgress).toHaveBeenCalledTimes(1)
    api.getProgress.mockResolvedValueOnce({ progress: saved(20, 5) })
    expect((await state.reload())?.page_number).toBe(20)
    expect(state.status.value).toBe('idle')
  })
  it.each(['book', 'user', 'dispose'])('切换 %s 清理旧定时器和迟到请求', async (change) => {
    await state.load()
    let finish!: (value: unknown) => void
    api.saveProgress.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    state.recordDisplayed(15, null); await vi.advanceTimersByTimeAsync(1000)
    state.recordDisplayed(16, null)
    if (change === 'book') bookId.value = 3
    if (change === 'user') userId.value = 8
    if (change === 'dispose') state.dispose()
    await flushPromises()
    finish(saved(15, 1)); await flushPromises(); await vi.advanceTimersByTimeAsync(1000)
    expect(state.progress.value).toBeNull()
    expect(api.saveProgress).toHaveBeenCalledTimes(1)
  })
})
