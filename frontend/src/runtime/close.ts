export type CloseDecision = 'ready' | 'stay' | 'discard'
const guards = new Set<() => Promise<CloseDecision>>()
const answered = new Set<string>()
let active: Promise<void> | null = null
export function registerCloseGuard(guard: () => Promise<CloseDecision>): () => void {
  guards.add(guard)
  return () => { guards.delete(guard) }
}
export function requestClose(requestId: string): Promise<void> {
  if (!requestId || answered.has(requestId)) return Promise.resolve()
  if (active) return active
  const work = async (): Promise<CloseDecision> => {
    let decision: CloseDecision = 'ready'
    for (const guard of [...guards]) {
      const result = await guard()
      if (result === 'stay') return 'stay'
      if (result === 'discard') decision = 'discard'
    }
    return decision
  }
  let timer: ReturnType<typeof setTimeout>
  const timeout = new Promise<CloseDecision>(resolve => { timer = setTimeout(() => resolve('stay'), 7500) })
  active = Promise.race([work().catch(() => 'stay' as const), timeout]).then(async decision => {
    clearTimeout(timer)
    answered.add(requestId)
    if (answered.size > 64) answered.delete(answered.values().next().value!)
    await window.pywebview?.api.respond_close(requestId, decision)
  }).finally(() => { active = null })
  return active
}
export function installCloseListener() {
  window.addEventListener('zhitu:close-request', event => {
    const id = (event as CustomEvent).detail
    if (typeof id === 'string') void requestClose(id)
  })
}
