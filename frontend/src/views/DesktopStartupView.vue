<script setup lang="ts">
defineProps<{ error?: string }>()
</script>
<template>
  <main class="desktop-startup" role="status"><h1>知途</h1><p>{{ error || '正在打开本地学习空间…' }}</p><small v-if="error">请关闭窗口后重新打开软件，已有学习资料不会删除。</small></main>
</template>
<style scoped>
.desktop-startup { padding: 20vh 2rem; text-align: center; }
h1 { color: #5361d8; }
</style>
