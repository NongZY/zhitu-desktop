import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { loadDesktopContext } from './desktop'

const context = () => ({ schemaVersion: 1, mode: 'desktop', apiBaseUrl: location.origin + '/api/v1', version: '0.2.0-dev', workspace: { id: '74ab5210-4583-4a42-b838-982545752491', ownerId: 17, label: '本地学习空间' } })
beforeEach(() => { vi.useFakeTimers(); delete window.pywebview; localStorage.setItem('adaptive_learning_token', 'old-jwt') })
afterEach(() => { vi.useRealTimers(); delete window.pywebview; localStorage.clear() })
it('等待原生桥再加载空间，不把旧 JWT 当作本地身份', async () => {
  const loading = loadDesktopContext(100)
  window.pywebview = { api: { get_context: async () => context(), respond_close: async () => undefined } }
  window.dispatchEvent(new Event('pywebviewready'))
  expect((await loading).workspace.ownerId).toBe(17)
})
it('无原生桥明确报错，不回到登录页', async () => {
  const result = loadDesktopContext(100).catch(e => e.message)
  await vi.advanceTimersByTimeAsync(101)
  expect(await result).toContain('软件尚未连接本地服务')
})
it.each([{ apiBaseUrl: 'https://evil.invalid/api/v1' }, { mode: 'web' }, { workspace: { ownerId: 0 } }])('拒绝伪造的启动信息 %j', async change => {
  window.pywebview = { api: { get_context: async () => ({ ...context(), ...change }), respond_close: async () => undefined } }
  await expect(loadDesktopContext()).rejects.toThrow('本地')
})
