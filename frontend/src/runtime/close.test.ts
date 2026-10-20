import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { registerCloseGuard, requestClose, cancelClose } from './close'
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

it('用户阅读确认提示超过八秒后，放弃仍是有效的当前选择', async () => {
  vi.useFakeTimers()
  let choose!: (decision: 'discard') => void
  unregister.push(registerCloseGuard(control => control.confirm(
    () => new Promise(resolve => { choose = resolve }), () => {},
  )))
  const closing = requestClose('human-delayed')
  await vi.advanceTimersByTimeAsync(18000)
  expect(responses.filter(([, result]) => result !== 'pending')).toEqual([])
  expect(responses.some(([, result]) => result === 'pending')).toBe(true)
  choose('discard'); await closing
  expect(responses.filter(([, result]) => result !== 'pending')).toEqual([['human-delayed', 'discard']])
})

it('保存用六秒后，确认时间不会被压缩到一点五秒', async () => {
  vi.useFakeTimers()
  let choose!: (decision: 'discard') => void
  unregister.push(registerCloseGuard(async control => {
    await new Promise(resolve => setTimeout(resolve, 6000))
    return control.confirm(() => new Promise(resolve => { choose = resolve }), () => {})
  }))
  const closing = requestClose('reading-delayed')
  await vi.advanceTimersByTimeAsync(24000)
  expect(responses.filter(([, result]) => result !== 'pending')).toEqual([])
  choose('discard'); await closing
  expect(responses[responses.length - 1]).toEqual(['reading-delayed', 'discard'])
})

it('原生取消会撤掉该请求的确认框，迟到选择不影响下次关闭', async () => {
  vi.useFakeTimers()
  let choose!: (decision: 'discard') => void
  let dismissed = false
  const remove = registerCloseGuard(control => control.confirm(
    () => new Promise(resolve => { choose = resolve }), () => { dismissed = true },
  ))
  unregister.push(remove)
  const old = requestClose('retired-human')
  cancelClose('retired-human')
  await old
  expect(dismissed).toBe(true)
  remove()
  unregister.push(registerCloseGuard(async () => 'ready'))
  await requestClose('new-close-after-retirement')
  choose('discard'); await Promise.resolve()
  expect(responses.filter(([, result]) => result !== 'pending')).toEqual([['new-close-after-retirement', 'ready']])
})

it('取消事件先到时，迟到的关闭请求不能重新弹出确认框', async () => {
  const ask = vi.fn(async () => 'discard' as const)
  unregister.push(registerCloseGuard(control => control.confirm(ask, () => {})))
  cancelClose('cancel-before-dispatch')
  await requestClose('cancel-before-dispatch')
  expect(ask).not.toHaveBeenCalled()
  expect(responses).toEqual([])
})
