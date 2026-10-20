import { ref, watch, type Ref } from 'vue'
import { readingApi, type ReadingProgress } from '../api'

type Status = 'idle' | 'loading' | 'saving' | 'saved' | 'error' | 'conflict'
type Position = { page: number; chapterId: number | null }

export function useReadingProgress(input: { bookId: Ref<number>; userId: Ref<number | null>; documentRevision: Ref<string | null> }) {
  const progress = ref<ReadingProgress | null>(null)
  const status = ref<Status>('idle')
  const error = ref('')
  let generation = 0, loaded = false, busy = false, ready = false, disposed = false
  let pending: Position | null = null
  let timer: ReturnType<typeof setTimeout> | undefined
  let controller: AbortController | undefined
  let inFlight: Promise<void> | null = null

  function reset() {
    generation++; controller?.abort(); clearTimeout(timer)
    progress.value = null; status.value = 'idle'; error.value = ''
    pending = null; loaded = false; busy = false; ready = false; inFlight = null
  }
  const stop = watch([input.bookId, input.userId], reset, { flush: 'sync' })

  async function load() {
    if (disposed || input.userId.value === null) return
    const request = ++generation
    controller?.abort(); controller = new AbortController()
    busy = false; loaded = false; status.value = 'loading'; error.value = ''
    try {
      const result = await readingApi.getProgress(input.bookId.value, controller.signal)
      if (request !== generation || disposed) return
      progress.value = result.progress; loaded = true; status.value = 'idle'
    } catch {
      if (request !== generation || disposed) return
      status.value = 'error'; error.value = '阅读位置暂时无法恢复，仍可阅读；请重试后保存'
    }
  }

  async function performSave() {
    if (disposed || !loaded || busy || !ready || !pending || !input.documentRevision.value || status.value === 'conflict') return
    const position = pending; pending = null; ready = false; busy = true
    const request = generation
    controller = new AbortController(); status.value = 'saving'; error.value = ''
    try {
      const result = await readingApi.saveProgress(input.bookId.value, {
        page_number: position.page, chapter_id: position.chapterId,
        document_revision: input.documentRevision.value, expected_revision: progress.value?.revision ?? 0,
      }, controller.signal)
      if (request !== generation || disposed) return
      progress.value = result; status.value = pending ? 'saving' : 'saved'
    } catch (err) {
      if (request !== generation || disposed) return
      pending ??= position
      const response = (err as { response?: { status?: number; data?: { detail?: { message?: string } } } }).response
      status.value = response?.status === 409 ? 'conflict' : 'error'
      error.value = response?.status === 409
        ? response.data?.detail?.message || '其他页面已更新阅读位置，请重新载入'
        : '位置暂未保存，可重试'
    } finally {
      if (request === generation && !disposed) {
        busy = false
      }
    }
  }

  function save(): Promise<void> {
    if (inFlight) return inFlight
    const request = generation
    const task = performSave().finally(() => {
      if (inFlight === task) inFlight = null
      if (request === generation && !disposed && status.value === 'saving' && ready && pending) void save()
    })
    inFlight = task
    return task
  }

  async function flush(): Promise<boolean> {
    const failed = () => status.value === 'conflict' || status.value === 'error'
    clearTimeout(timer)
    if (disposed || !loaded || status.value === 'conflict') return false
    const request = generation
    const drain = async () => {
      if (inFlight) await inFlight
      if (request !== generation || disposed || status.value === 'conflict' || status.value === 'error') {
        // A failed in-flight write must be acknowledged, not silently retried on close.
        return false
      }
      while (pending || inFlight) {
        if (request !== generation || disposed) return false
        ready = true
        await save()
        if (failed()) return false
      }
      return true
    }
    let timeout: ReturnType<typeof setTimeout>
    const result = await Promise.race([drain(), new Promise<boolean>(resolve => {
      timeout = setTimeout(() => resolve(false), 6000)
    })])
    clearTimeout(timeout!)
    return result
  }

  function recordDisplayed(page: number, chapterId: number | null) {
    if (disposed || input.userId.value === null || !Number.isSafeInteger(page) || page < 1) return
    if (status.value === 'conflict') return
    pending = { page, chapterId }; ready = false; clearTimeout(timer)
    if (!loaded || status.value === 'error') return
    // Opening the saved page is also a new reading visit. Persist it so the
    // dashboard's most-recent book reflects this visit, even without a page flip.
    status.value = 'saving'
    timer = setTimeout(() => { ready = true; void save() }, 1000)
  }

  async function retry() {
    if (disposed || status.value === 'conflict') return
    if (!loaded) await load()
    if (loaded && pending) { ready = true; await save() }
  }
  async function reload() {
    reset(); await load()
    return progress.value
  }
  function dispose() { reset(); disposed = true; stop() }
  return { progress, status, error, load, recordDisplayed, retry, reload, flush, dispose }
}
