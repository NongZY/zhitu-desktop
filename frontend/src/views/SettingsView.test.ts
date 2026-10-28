import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import SettingsView from './SettingsView.vue'

const api = vi.hoisted(() => ({ readAI: vi.fn(), saveAI: vi.fn(), testAI: vi.fn(), status: vi.fn(), backup: vi.fn(), prepareRestore: vi.fn(), confirmRestore: vi.fn(), cancelRestore: vi.fn(), rollback: vi.fn() }))
vi.mock('../api/desktopSettings', () => ({ desktopSettings: api }))
let wrapper: VueWrapper
const setting = { base_url: 'https://api.example.com/v1', model: 'example', qa_enabled: false, practice_enabled: false, key_configured: true, key_masked: '••••••••' }
beforeEach(() => {
  vi.resetAllMocks()
  api.readAI.mockResolvedValue(setting)
  api.saveAI.mockResolvedValue(setting)
  api.status.mockResolvedValue({ pending: false, can_rollback: false, restore_error: '' })
})
afterEach(() => wrapper?.unmount())
async function render() { wrapper = mount(SettingsView, { global: { plugins: [ElementPlus] } }); await flushPromises() }
it('只显示密钥状态，保存后清空密钥输入，清除操作另行提交', async () => {
  await render()
  expect(wrapper.get('[data-test="key"]').element).toHaveProperty('value', '')
  expect(wrapper.text()).toContain('已配置')
  await wrapper.get('[data-test="key"]').setValue('synthetic-secret')
  await wrapper.get('[data-test="save-ai"]').trigger('click'); await flushPromises()
  expect(api.saveAI).toHaveBeenCalledWith(expect.objectContaining({ api_key: 'synthetic-secret' }))
  expect(wrapper.get('[data-test="key"]').element).toHaveProperty('value', '')
  await wrapper.get('[data-test="clear-key"]').trigger('click'); await flushPromises()
  expect(api.saveAI).toHaveBeenLastCalledWith(expect.objectContaining({ clear_key: true }))
})
it('启用 AI 先说明发送内容，连接测试需要单独确认', async () => {
  await render()
  await wrapper.get('[data-test="qa-enabled"]').setValue(true)
  expect(wrapper.get('[data-test="save-ai"]').attributes('disabled')).toBeDefined()
  await wrapper.get('[data-test="privacy-ack"]').setValue(true)
  expect(wrapper.get('[data-test="save-ai"]').attributes('disabled')).toBeUndefined()
  expect(wrapper.get('[data-test="test-ai"]').attributes('disabled')).toBeDefined()
  await wrapper.get('[data-test="test-consent"]').setValue(true)
  api.testAI.mockResolvedValue({ notice: '连接失败，本地学习仍可使用。' })
  await wrapper.get('[data-test="test-ai"]').trigger('click'); await flushPromises()
  expect(api.testAI).toHaveBeenCalledWith(true)
  expect(wrapper.text()).toContain('本地学习仍可使用')
})
it('已安排恢复时显示重启提示和取消入口', async () => {
  api.status.mockResolvedValue({ pending: true, can_rollback: true, restore_error: '' })
  await render()
  expect(wrapper.text()).toContain('重新打开')
  expect(wrapper.get('[data-test="backup"]').attributes('disabled')).toBeDefined()
  api.cancelRestore.mockResolvedValue(undefined)
  await wrapper.get('[data-test="cancel-restore"]').trigger('click')
  expect(api.cancelRestore).toHaveBeenCalledOnce()
})
