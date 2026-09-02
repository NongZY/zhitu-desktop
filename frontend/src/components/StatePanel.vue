<script setup lang="ts">
import { Connection, Document } from '@element-plus/icons-vue'

withDefaults(
  defineProps<{
    title?: string
    description?: string
    mode?: 'empty' | 'offline'
    compact?: boolean
  }>(),
  {
    title: '暂时没有内容',
    description: '完成相关操作后，内容会显示在这里。',
    mode: 'empty',
    compact: false,
  },
)
</script>

<template>
  <div class="state-panel" :class="{ compact }">
    <div class="state-icon">
      <el-icon :size="25"><Connection v-if="mode === 'offline'" /><Document v-else /></el-icon>
    </div>
    <h3>{{ title }}</h3>
    <p>{{ description }}</p>
    <slot />
  </div>
</template>
