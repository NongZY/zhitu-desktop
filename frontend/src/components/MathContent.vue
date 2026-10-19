<script setup lang="ts">
import { computed } from 'vue'
import 'katex/dist/katex.min.css'
import { mathParts } from '../utils/math'
const props = defineProps<{ text?: string | null }>()
const parts = computed(() => mathParts(props.text || ''))
</script>

<template>
  <span class="math-content"><template v-for="(part, index) in parts" :key="index"><span v-if="part.html" class="formula" v-html="part.html"></span><template v-else>{{ part.text }}</template></template></span>
</template>

<style scoped>
.math-content{white-space:pre-wrap;overflow-wrap:anywhere}.formula{display:inline-block;max-width:100%;overflow-x:auto;overflow-y:hidden;vertical-align:middle;padding:3px 0}.formula :deep(.katex){font-size:1.1em}.formula :deep(.katex-display){margin:.3em 0}
</style>
