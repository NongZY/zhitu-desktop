import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { registerCloseGuard, requestClose } from './close'
const responses: Array<[string, string]> = []
let unregister: Array<() => void> = []
beforeEach(() => {
  responses.length = 0
  window.pywebview = { api: { get_context: async () => ({}), respond_close: async (id, result) => { responses.push([id, result]) } } }
})
afterEach(() => { unregister.forEach(fn => fn()); unregister = []; delete window.pywebview; vi.useRealTimers() })
it('关闭按顺序等待保存，只响应一次当前请求', async () => {
  let finish!: (value: 'ready') => void
  unregister.push(registerCloseGuard(() => new Promise(resolve => { finish = resolve })))
  const first = requestClose('close-1')
  const duplicate = requestClose('close-1')
  expect(responses).toEqual([])
  finish('ready'); await Promise.all([first, duplicate])
  expect(responses).toEqual([['close-1', 'ready']])
})
it('保存失败、守卫抛错时不假称可以退出', async () => {
  unregister.push(registerCloseGuard(async () => { throw new Error('disk full') }))
  await requestClose('close-failed')
  expect(responses).toEqual([['close-failed', 'stay']])
})
it('未完成练习可以停留，也可以明确放弃', async () => {
  const remove = registerCloseGuard(async () => 'stay'); unregister.push(remove)
  await requestClose('close-stay'); remove()
  unregister.push(registerCloseGuard(async () => 'discard'))
  await requestClose('close-discard')
  expect(responses).toEqual([['close-stay', 'stay'], ['close-discard', 'discard']])
})
it('守卫超时应停留', async () => {
  vi.useFakeTimers()
  unregister.push(registerCloseGuard(() => new Promise(() => {})))
  const closing = requestClose('close-timeout')
  await vi.advanceTimersByTimeAsync(7500); await closing
  expect(responses).toEqual([['close-timeout', 'stay']])
})
