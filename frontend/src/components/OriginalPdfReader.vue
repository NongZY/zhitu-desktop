<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { textbookApi, type Chapter, type PageSearchItem } from '../api'
import { getApiErrorMessage } from '../api/http'
import { documentsApi } from '../api/documents'

const props = defineProps<{ bookId: string | number; chapter?: Chapter; page: number | null; pageCount: number; navigationId: number; version?: string }>()
const emit = defineEmits<{ navigate: [page: number]; 'page-displayed': [position: { page: number; navigationId: number }] }>()
const count = computed(() => props.pageCount)
const current = computed(() => props.page || 1)
const searchPageSize = computed(() => props.version ? 30 : 10)
const pageInput = ref(1)
const zoom = ref(100)
const warm = ref(false)
const loading = ref(false)
const error = ref('')
const imageUrl = ref('')
const viewport = ref<HTMLElement>()
const query = ref('')
const scope = ref('book')
const hits = ref<PageSearchItem[]>([])
const total = ref(0)
const resultPage = ref(1)
const searched = ref(false)
const searching = ref(false)
const searchError = ref('')
let imageRequest = 0
let displayedRequest = -1
const imageIdentity = ref({ request: 0, page: 0, navigationId: 0 })
let searchRequest = 0
let imageAbort: AbortController | undefined
let searchAbort: AbortController | undefined

function clearImage() {
  imageRequest++
  imageAbort?.abort()
  if (imageUrl.value) URL.revokeObjectURL(imageUrl.value)
  imageUrl.value = ''
  loading.value = false
}
function clearSearch() {
  searchRequest++
  searchAbort?.abort()
  searching.value = false
  hits.value = []; total.value = 0; searched.value = false; searchError.value = ''
}
function jump(page: number) {
  if (!count.value || !Number.isFinite(page)) return
  const target = Math.min(count.value, Math.max(1, Math.trunc(page)))
  emit('navigate', target)
}
async function loadImage() {
  clearImage()
  if (!props.page || props.page > count.value) return
  const target = props.page
  const navigationId = props.navigationId
  const request = imageRequest
  imageAbort = new AbortController()
  pageInput.value = target; error.value = ''; loading.value = true
  if (viewport.value) { viewport.value.scrollTop = 0; viewport.value.scrollLeft = 0 }
  try {
    const blob = props.version
      ? await textbookApi.pageImage(props.bookId, target, imageAbort.signal, props.version)
      : await textbookApi.pageImage(props.bookId, target, imageAbort.signal)
    if (request !== imageRequest) return
    imageIdentity.value = { request, page: target, navigationId }
    imageUrl.value = URL.createObjectURL(blob)
  } catch (err) {
    if (request === imageRequest) error.value = getApiErrorMessage(err, '原页加载失败，请重试')
  } finally {
    if (request === imageRequest) loading.value = false
  }
}
function isCurrentImage(event: Event) {
  const img = event.target as HTMLImageElement
  return Number(img.dataset.request) === imageRequest && imageIdentity.value.navigationId === props.navigationId
    && imageIdentity.value.page === props.page && img.getAttribute('src') === imageUrl.value
}
function displayed(event: Event) {
  if (!isCurrentImage(event) || error.value || displayedRequest === imageRequest) return
  displayedRequest = imageRequest
  emit('page-displayed', { page: imageIdentity.value.page, navigationId: imageIdentity.value.navigationId })
}
function imageFailed(event: Event) {
  if (isCurrentImage(event)) error.value = '图片未能显示，请重试'
}
async function search(page = 1) {
  if (!query.value.trim() || !count.value) return
  const request = ++searchRequest
  searchAbort?.abort(); searchAbort = new AbortController()
  searching.value = true; searchError.value = ''; hits.value = []; searched.value = false
  try {
    if (props.version) {
      const data = await documentsApi.search(props.bookId, query.value.trim(), page, props.version)
      if (request !== searchRequest) return
      hits.value = data.items.map(hit => ({ page_number: Number(hit.locator.unit_id), excerpt: hit.excerpt,
        chapter_id: hit.chapter_id ?? null, chapter_title: null }))
      total.value = data.total; resultPage.value = page; searched.value = true
      return
    }
    const data = await textbookApi.searchPages(props.bookId, {
      q: query.value.trim(), chapter_id: scope.value === 'chapter' ? props.chapter?.id : undefined,
      page, page_size: 10,
    }, searchAbort.signal)
    if (request !== searchRequest) return
    hits.value = data.items; total.value = data.total; resultPage.value = page; searched.value = true
  } catch (err) {
    if (request === searchRequest) searchError.value = getApiErrorMessage(err, '查找失败，请重试')
  } finally {
    if (request === searchRequest) searching.value = false
  }
}
watch([() => props.bookId, () => props.page, () => props.navigationId, () => props.version], loadImage, { immediate: true })
watch([() => props.bookId, () => props.version], clearSearch)
watch(() => props.chapter?.id, () => {
  clearSearch()
  if (!props.chapter) scope.value = 'book'
})
watch([query, scope], clearSearch)
onUnmounted(() => { clearImage(); clearSearch() })
</script>

<template>
  <section class="pdf-reader" aria-label="课本原页阅读器">
    <p v-if="!count" class="reader-note">这本课本还没有 PDF 原文件。可上传 PDF，或展开下方提取文字阅读笔记。</p>
    <template v-if="count">
      <form class="reader-search" @submit.prevent="search(1)">
        <input v-model="query" aria-label="搜索课本内容" maxlength="100" placeholder="查找课本内容，如：绝对值" />
        <select v-model="scope" aria-label="搜索范围"><option value="book">整本课本</option><option v-if="chapter" value="chapter">当前章节</option></select>
        <button :disabled="!query.trim() || searching">{{ searching ? '查找中…' : '查找' }}</button>
      </form>
      <p v-if="searchError" role="alert">{{ searchError }}</p>
      <div v-if="searched" class="search-results">
        <p>{{ total ? `找到 ${total} 页，点击定位到原页` : '没有找到，可换个关键词。扫描图片中的文字暂不能查找。' }}</p>
        <button v-for="hit in hits" :key="hit.page_number" type="button" @click="jump(hit.page_number)"><strong>PDF 第 {{ hit.page_number }} 页 · {{ hit.chapter_title || '课本正文' }}</strong><span>{{ hit.excerpt }}</span></button>
        <div v-if="total > searchPageSize" class="reader-controls"><button :disabled="resultPage <= 1 || searching" @click="search(resultPage - 1)">上一组结果</button><span>{{ resultPage }} / {{ Math.ceil(total / searchPageSize) }}</span><button :disabled="resultPage * searchPageSize >= total || searching" @click="search(resultPage + 1)">下一组结果</button></div>
        <small>摘要来自提取文字，仅用于找页；本次定位到页，不对未确认的位置高亮。</small>
      </div>
      <div class="reader-controls">
        <button :disabled="current <= 1" @click="jump(current - 1)">上一页</button>
        <form @submit.prevent="jump(pageInput)"><label>PDF 第 <input v-model.number="pageInput" aria-label="PDF 页码" type="number" min="1" :max="count" /> 页 / {{ count }} 页</label><button>跳转</button></form>
        <button :disabled="current >= count" @click="jump(current + 1)">下一页</button>
        <label>缩放 <select v-model.number="zoom" aria-label="页面缩放"><option :value="100">适合宽度</option><option :value="125">125%</option><option :value="150">150%</option><option :value="200">200%</option></select></label>
        <label><input v-model="warm" type="checkbox" />护眼背景</label>
      </div>
      <p class="reader-note">原书公式、插图和底色保持不变。PDF 页码含封面，可能与书上印刷页码不同。</p>
      <div ref="viewport" class="page-viewport" :class="{ warm }" :aria-busy="loading">
        <p v-if="loading" role="status">正在加载 PDF 第 {{ current }} 页…</p>
        <p v-else-if="error" role="alert">{{ error }} <button @click="loadImage">重试本页</button></p>
        <img v-else-if="imageUrl" :key="imageIdentity.request" :data-request="imageIdentity.request" :src="imageUrl" :style="{ width: `${zoom}%` }" :alt="`课本原页：PDF 第 ${current} 页`" @load="displayed" @error="imageFailed" />
      </div>
    </template>
  </section>
</template>

<style scoped>
.pdf-reader{padding:18px;min-width:0;color:#334155}.reader-search,.reader-controls,.reader-controls form{display:flex;flex-wrap:wrap;align-items:center;gap:8px}.reader-search{margin-bottom:12px}.reader-search>input{flex:1;min-width:150px}.pdf-reader button,.pdf-reader select,.pdf-reader input:not([type=checkbox]){padding:7px 10px;border:1px solid #ccd3df;border-radius:7px;background:white;color:#334155;font:inherit;font-size:13px}.pdf-reader button{cursor:pointer}.pdf-reader button:hover:not(:disabled){border-color:#6271d9;color:#4254cb}.pdf-reader button:disabled{opacity:.4;cursor:default}.reader-controls{font-size:12px}.reader-controls input[type=number]{width:68px}.reader-note{font-size:12px;line-height:1.6;color:#68768b}.page-viewport{padding:16px;background:#e7ebf0;max-height:78vh;overflow:auto;min-height:200px;border-radius:8px}.page-viewport.warm{background:#eee5d1}.page-viewport img{display:block;height:auto;max-width:none;margin:0 auto;background:white;box-shadow:0 2px 12px #1c29441f}.page-viewport>p{padding:45px 10px;text-align:center}.search-results{margin-bottom:14px;max-height:280px;overflow:auto;background:#f4f6fb;border-radius:8px;padding:12px}.search-results>button{display:block;width:100%;text-align:left;margin:6px 0}.search-results span{display:block;font-size:12px;line-height:1.6;margin-top:4px}.search-results small{color:#68768b}.search-results p{margin:0 0 8px;font-size:13px}@media(max-width:600px){.pdf-reader{padding:10px}.page-viewport{padding:6px}}
</style>
