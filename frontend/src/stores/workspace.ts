import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { validateDesktopContext, type DesktopContext } from '../runtime/desktop'
export const useWorkspaceStore = defineStore('workspace', () => {
  const context = ref<DesktopContext | null>(null)
  const ownerId = computed(() => context.value?.workspace.ownerId ?? null)
  const label = computed(() => context.value?.workspace.label ?? '本地学习空间')
  function initialize(value: DesktopContext) { context.value = validateDesktopContext(value) }
  return { context, ownerId, label, initialize }
})
