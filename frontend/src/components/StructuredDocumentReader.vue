<script setup lang="ts">
import { nextTick, watch } from 'vue'
import type { DocumentBlock } from '../api/documents'
const props = defineProps<{ blocks: DocumentBlock[] }>()
const emit = defineEmits<{ displayed: [id: string] }>()
const safeImage = (image?: string) => !!image && /^data:image\/(png|jpeg|gif|webp);base64,[a-zA-Z0-9+/=]+$/.test(image)
watch(() => props.blocks, async (blocks) => {
  await nextTick()
  if (blocks === props.blocks && blocks[0]) emit('displayed', blocks[0].id)
}, { immediate: true })
</script>

<template>
  <section class="document-paper" aria-label="资料正文">
    <article v-for="block in blocks" :key="block.id" :id="`document-${block.id}`" class="document-block">
      <h2 v-if="block.kind === 'heading'">{{ block.text }}</h2>
      <table v-else-if="block.kind === 'table'"><tbody><tr v-for="(row, index) in block.cells" :key="index"><td v-for="(cell, column) in row" :key="column">{{ cell }}</td></tr></tbody></table>
      <img v-else-if="block.kind === 'image' && safeImage(block.image)" :src="block.image" alt="资料内嵌图片" />
      <pre v-else-if="block.kind === 'code'">{{ block.text }}</pre>
      <p v-else-if="block.kind === 'unsupported'" class="notice">{{ block.text }}</p>
      <p v-else>{{ block.text }}</p>
    </article>
  </section>
</template>

<style scoped>
.document-paper{padding:26px 34px;background:#fff;color:#25304b;min-height:360px;border:1px solid #e5e8ef;border-radius:14px}.document-block{scroll-margin-top:30px;overflow-wrap:anywhere}.document-block p{white-space:pre-wrap;line-height:1.9;font-size:16px}.document-block h2{font-size:23px;line-height:1.5;margin:20px 0}.document-block table{border-collapse:collapse;max-width:100%;display:block;overflow:auto;margin:18px 0}.document-block td{border:1px solid #ccd4e3;padding:10px 14px;white-space:pre-wrap}.document-block img{max-width:100%;max-height:650px;object-fit:contain}.document-block pre{white-space:pre-wrap;background:#f3f5f9;padding:16px}.document-block .notice{font-size:13px;background:#fff8e7;color:#856318;padding:12px;border-radius:8px}@media(max-width:620px){.document-paper{padding:16px}}
</style>
