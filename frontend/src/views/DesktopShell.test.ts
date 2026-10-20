import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'
import { expect, it } from 'vitest'
import AppLayout from '../layouts/AppLayout.vue'
import DesktopStartupView from './DesktopStartupView.vue'
import { http } from '../api/http'

it('未连接时说明本地启动失败，没有登录入口', () => {
  const wrapper = mount(DesktopStartupView, { props: { error: '软件尚未连接本地服务' } })
  expect(wrapper.text()).toContain('软件尚未连接本地服务')
  expect(wrapper.text()).not.toMatch(/登录|注册/)
})
it('空间页眉无登录、注册、退出入口', async () => {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<p>学习</p>' } }] })
  await router.push('/')
  const wrapper = mount(AppLayout, { global: { plugins: [createPinia(), router, ElementPlus] } })
  expect(wrapper.text()).toContain('本地学习空间')
  expect(wrapper.text()).not.toMatch(/登录|注册|退出登录/)
  wrapper.unmount()
})
it('旧登录数据不会作为 Authorization 外发，401 不跳登录', async () => {
  localStorage.setItem('adaptive_learning_token', 'old-secret')
  let sent = ''
  await http.get('/test', { adapter: async config => { sent = String(config.headers.Authorization || ''); return { data: {}, status: 200, statusText: 'OK', headers: {}, config } } })
  expect(sent).toBe('')
  let expired = false, disconnected = false
  window.addEventListener('auth:expired', () => { expired = true }, { once: true })
  window.addEventListener('desktop:disconnected', () => { disconnected = true }, { once: true })
  await http.get('/test', { adapter: async config => { throw { isAxiosError: true, config, response: { status: 401 } } } }).catch(() => {})
  expect(expired).toBe(false)
  expect(disconnected).toBe(true)
  localStorage.clear()
})
