<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import TextbookDetailView from './TextbookDetailView.vue'
import DocumentStudyView from './DocumentStudyView.vue'
import { documentsApi, type DocumentData } from '../api/documents'
import { getApiErrorMessage } from '../api/http'

const route = useRoute()
const data = ref<DocumentData | null>(null), loading = ref(true), error = ref(''), pdf = ref(false)
const state = ref<Awaited<ReturnType<typeof documentsApi.state>> | null>(null)
const encoding = ref('auto')
let request = 0, timer: ReturnType<typeof setTimeout> | undefined
async function load() {
  const own = ++request
  clearTimeout(timer); loading.value = true; error.value = ''; data.value = null; pdf.value = false
  try {
    const book = String(route.params.id)
    const version = typeof route.query.version === 'string' ? route.query.version : undefined
    const [document, status] = await Promise.all([documentsApi.read(book, version), documentsApi.state(book)])
    if (own !== request) return
    if (document && route.query.source && route.query.source !== document.source_id) throw new Error('引用来源不匹配，请从资料目录重新打开')
    const currentPdf = document?.format === 'pdf' && !version
    data.value = currentPdf ? null : document; state.value = status
    const preparingFirst = !status.available && ['queued', 'processing', 'failed'].includes(status.status)
    pdf.value = currentPdf || (!document && !preparingFirst && (!status.format || status.format === 'pdf'))
    if (!document && !pdf.value && ['queued', 'processing'].includes(status.status)) timer = setTimeout(load, 2000)
  } catch (err) { if (own === request) error.value = getApiErrorMessage(err) }
  finally { if (own === request) loading.value = false }
}
async function retry() {
  try { await documentsApi.retry(String(route.params.id), encoding.value); await load() }
  catch (err) { error.value = getApiErrorMessage(err) }
}
watch(() => route.fullPath, load, { immediate: true })
onUnmounted(() => { request++; clearTimeout(timer) })
</script>

<template>
  <div v-if="loading" role="status">正在打开资料…</div>
  <section v-else-if="error" class="surface-card card-pad"><p role="alert">{{ error }}</p><el-button @click="load">重新打开</el-button></section>
  <DocumentStudyView v-else-if="data" :key="route.fullPath" :initial-document="data" />
  <TextbookDetailView v-else-if="pdf" />
  <section v-else class="surface-card card-pad"><h2>资料整理</h2><p>{{ state?.message || '正在准备阅读内容' }}</p><el-progress :percentage="state?.progress || 0" />
    <template v-if="state?.status === 'failed'"><p>原文件已保留，不需要重新上传。文字编码提示错误时可换一种编码重试。</p><el-select v-model="encoding"><el-option label="自动识别 UTF-8 / Unicode" value="auto" /><el-option label="中文 GB18030" value="gb18030" /></el-select><el-button @click="retry">重新整理</el-button></template>
  </section>
</template>
