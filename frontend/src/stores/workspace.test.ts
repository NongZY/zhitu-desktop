import { beforeEach, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useWorkspaceStore } from './workspace'
beforeEach(() => setActivePinia(createPinia()))
it('稳定空间使用内部 ownerId，不硬编码为一', () => {
  const store = useWorkspaceStore()
  expect(store.ownerId).toBeNull()
  store.initialize({ schemaVersion: 1, mode: 'desktop', apiBaseUrl: location.origin + '/api/v1', version: '0.2.0-dev', workspace: { id: '74ab5210-4583-4a42-b838-982545752491', ownerId: 17, label: '本地学习空间' } })
  expect(store.ownerId).toBe(17)
  expect(store.label).toBe('本地学习空间')
})
