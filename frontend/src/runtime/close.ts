export type CloseDecision = 'ready' | 'stay' | 'discard'
export interface CloseControl {
  signal: AbortSignal
  confirm: (ask: () => Promise<CloseDecision>, dismiss: () => void) => Promise<CloseDecision>
}
const guards = new Set<(control: CloseControl) => Promise<CloseDecision>>()
const answered = new Set<string>()
function retire(requestId: string) {
  answered.add(requestId)
  if (answered.size > 64) answered.delete(answered.values().next().value!)
}
let active: { id: string, promise: Promise<void>, cancel: () => void } | null = null
export function registerCloseGuard(guard: (control: CloseControl) => Promise<CloseDecision>): () => void {
  guards.add(guard)
  return () => { guards.delete(guard) }
}
export function requestClose(requestId: string): Promise<void> {
  if (!requestId || answered.has(requestId)) return Promise.resolve()
  if (active) return active.promise
  const controller = new AbortController()
  let finished = false
  let timer: ReturnType<typeof setTimeout> | undefined
  let heartbeat: ReturnType<typeof setInterval> | undefined
  let settle!: () => void
  const promise = new Promise<void>(resolve => { settle = resolve })
  const send = async (decision: CloseDecision | 'pending') => {
    try { await window.pywebview?.api.respond_close(requestId, decision) }
    catch { window.dispatchEvent(new Event('desktop:disconnected')) }
  }
  const finish = (decision: CloseDecision, notify = true) => {
    if (finished) return
    finished = true
    clearTimeout(timer)
    clearInterval(heartbeat)
    controller.abort()
    retire(requestId)
    active = null
    if (notify) void send(decision).finally(settle)
    else settle()
  }
  const boundWork = () => { timer = setTimeout(() => finish('stay'), 7500) }
  const control: CloseControl = {
    signal: controller.signal,
    async confirm(ask, dismiss) {
      if (finished) return 'stay'
      // Only human decision time is unbounded. A live heartbeat lets the native
      // watchdog distinguish a reader considering the choice from a frozen UI.
      clearTimeout(timer)
      const dismissOwnDialog = () => { try { dismiss() } catch { /* already closed */ } }
      controller.signal.addEventListener('abort', dismissOwnDialog, { once: true })
      void send('pending')
      heartbeat = setInterval(() => { void send('pending') }, 1000)
      try { return await ask() }
      finally {
        clearInterval(heartbeat)
        controller.signal.removeEventListener('abort', dismissOwnDialog)
        if (!finished) boundWork()
      }
    },
  }
  active = { id: requestId, promise, cancel: () => finish('stay', false) }
  boundWork()
  const work = async (): Promise<CloseDecision> => {
    let decision: CloseDecision = 'ready'
    for (const guard of [...guards]) {
      const result = await guard(control)
      if (finished) return 'stay'
      if (result === 'stay') return 'stay'
      if (result === 'discard') decision = 'discard'
    }
    return decision
  }
  void work().then(decision => finish(decision), () => finish('stay'))
  return promise
}
export function cancelClose(requestId: string) {
  if (!requestId) return
  // Native dispatch is asynchronous: cancellation may arrive before its request.
  retire(requestId)
  if (active?.id === requestId) active.cancel()
}
export function installCloseListener() {
  window.addEventListener('zhitu:close-request', event => {
    const id = (event as CustomEvent).detail
    if (typeof id === 'string') void requestClose(id)
  })
  window.addEventListener('zhitu:close-cancel', event => {
    const id = (event as CustomEvent).detail
    if (typeof id === 'string') cancelClose(id)
  })
}
