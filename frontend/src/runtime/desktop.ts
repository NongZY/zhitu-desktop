export interface DesktopContext {
  schemaVersion: 1
  mode: 'desktop'
  apiBaseUrl: string
  version: '0.2.0-dev'
  workspace: { id: string; ownerId: number; label: '本地学习空间' }
}

export function validateDesktopContext(value: unknown): DesktopContext {
  const c = value as DesktopContext | undefined
  try {
    const url = new URL(c?.apiBaseUrl || '')
    if (!c || c.schemaVersion !== 1 || c.mode !== 'desktop' || c.version !== '0.2.0-dev'
      || url.origin !== location.origin || url.username || url.password || url.search || url.hash
      || url.pathname !== '/api/v1' || !Number.isSafeInteger(c.workspace?.ownerId) || c.workspace.ownerId < 1
      || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(c.workspace.id)
      || c.workspace.label !== '本地学习空间') throw new Error()
    return { schemaVersion: 1, mode: 'desktop', apiBaseUrl: url.href, version: '0.2.0-dev',
      workspace: { id: c.workspace.id, ownerId: c.workspace.ownerId, label: '本地学习空间' } }
  } catch { throw new Error('软件尚未连接本地服务，请关闭后重新启动') }
}

export function loadDesktopContext(timeoutMs = 15000): Promise<DesktopContext> {
  return new Promise((resolve, reject) => {
    let started = false
    const cleanup = () => { clearTimeout(timer); window.removeEventListener('pywebviewready', connect) }
    const connect = async () => {
      if (started || !window.pywebview?.api) return
      started = true
      try {
        const context = validateDesktopContext(await window.pywebview.api.get_context())
        cleanup(); resolve(context)
      } catch {
        cleanup(); reject(new Error('软件尚未连接本地服务，请关闭后重新启动'))
      }
    }
    const timer = setTimeout(() => { cleanup(); reject(new Error('软件尚未连接本地服务，请关闭后重新启动')) }, timeoutMs)
    window.addEventListener('pywebviewready', connect)
    void connect()
  })
}
