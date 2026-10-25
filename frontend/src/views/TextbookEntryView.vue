<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import TextbookDetailView from './TextbookDetailView.vue'
import DocumentStudyView from './DocumentStudyView.vue'
import { documentLink, documentsApi, type DocumentData, type DocumentPosition } from '../api/documents'
import { getApiErrorMessage } from '../api/http'

const route = useRoute()
const router = useRouter()
const data = ref<DocumentData | null>(null), loading = ref(true), error = ref(''), pdf = ref(false)
const state = ref<Awaited<ReturnType<typeof documentsApi.state>> | null>(null)
const encoding = ref('auto')
const retrying = ref(false), newlyReady = ref(false), importError = ref('')
const previousPosition = ref<DocumentPosition | null>(null)
let request = 0, timer: ReturnType<typeof setTimeout> | undefined
function schedulePoll() { clearTimeout(timer); timer = setTimeout(poll, 2000) }
async function poll() {
  const own = request, book = String(route.params.id)
  try {
    const status = await documentsApi.state(book)
    if (own !== request) return
    state.value = status
    if (['queued', 'processing'].includes(status.status)) schedulePoll()
    else if (!data.value && !pdf.value) await load()
    else if (status.status === 'completed') newlyReady.value = true
  } catch (err) { if (own === request) importError.value = getApiErrorMessage(err) }
}
function openUpdated() {
  void router.push({ path: `/textbooks/${route.params.id}`, query: { refreshed: String(Date.now()) } })
}
async function load() {
  const own = ++request
  clearTimeout(timer); loading.value = true; error.value = ''; data.value = null; pdf.value = false; newlyReady.value = false; importError.value = ''; previousPosition.value = null; retrying.value = false
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
    if (['queued', 'processing'].includes(status.status)) schedulePoll()
    void documentsApi.position(book).then(position => {
      if (own === request && position?.source_changed && position.rendition_revision !== version) previousPosition.value = position
    }).catch(() => { /* The reader separately displays position-read failures. */ })
  } catch (err) { if (own === request) error.value = getApiErrorMessage(err) }
  finally { if (own === request) loading.value = false }
}
async function retry() {
  if (retrying.value) return
  const own = request
  retrying.value = true; importError.value = ''
  try {
    const task = await documentsApi.retry(String(route.params.id), encoding.value)
    if (own !== request) return
    state.value = { ...state.value!, status: task.status, message: task.message || '正在重新整理', progress: task.progress || 0 }
    schedulePoll()
  } catch (err) { if (own === request) importError.value = getApiErrorMessage(err) }
  finally { if (own === request) retrying.value = false }
}
watch(() => route.fullPath, load, { immediate: true })
onUnmounted(() => { request++; clearTimeout(timer) })
</script>

<template>
  <div v-if="loading" role="status">正在打开资料…</div>
  <section v-else-if="error" class="surface-card card-pad"><p role="alert">{{ error }}</p><el-button @click="load">重新打开</el-button></section>
  <template v-else>
    <p v-if="previousPosition" role="status">资料已经更新，上次阅读的原版本仍保留。<el-button @click="router.push(documentLink(String(route.params.id), previousPosition))">查看上次阅读原文</el-button></p>
    <section v-if="!data && !pdf || state?.status !== 'completed' || newlyReady" class="surface-card card-pad">
      <h2>资料整理</h2><p>{{ state?.message || '正在准备阅读内容' }}</p>
      <el-progress v-if="['queued','processing'].includes(state?.status || '')" :percentage="state?.progress || 0" />
      <p v-if="data || pdf">原有内容仍可阅读，重新整理不会清空学习记录。</p>
      <p v-if="importError" role="alert">{{ importError }} <el-button @click="poll">重新查看进度</el-button></p>
      <template v-if="state?.status === 'failed'"><p>原文件已保留，不需要重新上传。文字编码提示错误时可换一种编码重试。</p><el-select v-model="encoding"><el-option label="自动识别 UTF-8 / Unicode" value="auto" /><el-option label="中文 GB18030" value="gb18030" /></el-select><el-button :loading="retrying" @click="retry">重新整理</el-button></template>
      <el-button v-if="newlyReady" @click="openUpdated">打开新内容</el-button>
    </section>
    <DocumentStudyView v-if="data" :key="route.fullPath" :initial-document="data" />
    <TextbookDetailView v-else-if="pdf" />
  </template>
</template>
