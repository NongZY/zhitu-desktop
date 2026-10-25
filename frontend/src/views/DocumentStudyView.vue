<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import StructuredDocumentReader from '../components/StructuredDocumentReader.vue'
import OriginalPdfReader from '../components/OriginalPdfReader.vue'
import PageHeader from '../components/PageHeader.vue'
import { documentsApi, type DocumentData, type DocumentLocator, type DocumentPosition } from '../api/documents'
import { getApiErrorMessage } from '../api/http'
import { registerCloseGuard, type CloseControl, type CloseDecision } from '../runtime/close'

const props = defineProps<{ initialDocument: DocumentData }>()
const route = useRoute(), router = useRouter()
const data = computed(() => props.initialDocument)
const start = ref(0), revision = ref(0), notice = ref(''), saveError = ref(''), saving = ref(false)
const pending = ref<DocumentLocator | null>(null), ready = ref(false)
const query = ref(''), searchError = ref(''), searching = ref(false), searchTotal = ref(0), searchPage = ref(1)
const matches = ref<{ excerpt: string; locator: DocumentLocator; chapter_id: number }[]>([])
let disposed = false, generation = 0, searchGeneration = 0
let savePromise: Promise<void> | null = null
const blocks = computed(() => data.value.blocks.slice(start.value, start.value + 20))
const chapterId = computed(() => blocks.value[0]?.chapter_id)
const historical = computed(() => data.value.is_current === false)
const pdfSnapshot = computed(() => data.value.format === 'pdf')
const positionLabel = computed(() => data.value.format === 'pptx' ? `第 ${blocks.value[0]?.slide || 1} 张幻灯片` : `第 ${start.value + 1} 个内容块`)

function locate(locator: Pick<DocumentLocator, 'kind' | 'unit_id'>) {
  return data.value.blocks.findIndex(block => locator.kind === 'page' ? String(block.page) === locator.unit_id : locator.kind === 'slide' ? String(block.slide) === locator.unit_id : block.id === locator.unit_id)
}
function blockLocator(index: number): DocumentLocator {
  const block = data.value.blocks[index]!
  return { source_id: data.value.source_id, source_revision: data.value.source_revision,
    rendition_revision: data.value.rendition_revision, kind: data.value.format === 'pptx' ? 'slide' : 'block',
    unit_id: data.value.format === 'pptx' ? String(block.slide) : block.id }
}
async function initialize() {
  const own = ++generation
  ready.value = false; pending.value = null; saveError.value = ''; notice.value = ''; start.value = 0
  try {
    const saved = await documentsApi.position(data.value.textbook_id)
    if (disposed || own !== generation) return
    revision.value = saved?.revision || 0
    if (!historical.value && saved?.source_changed) notice.value = '资料已更新，上次阅读位置已保留。请选择目录中的位置继续。'
    const wanted = typeof route.query.unit === 'string' ? { kind: String(route.query.kind || 'block'), unit_id: route.query.unit } : saved?.rendition_revision === data.value.rendition_revision ? saved : null
    if (wanted) {
      const index = locate(wanted)
      if (index >= 0) start.value = index
      else notice.value = '原来的位置无法定位，请重新选择目录。'
    } else if (route.query.chapter) {
      const chapter = data.value.chapters.find(item => String(item.id) === route.query.chapter)
      if (chapter) start.value = Math.max(0, locate(chapter.locator))
    }
    ready.value = true
  } catch (error) { if (disposed || own !== generation) return; notice.value = getApiErrorMessage(error, '阅读位置未加载，请重试后继续'); ready.value = false }
}
function choose(index: number) {
  if (!ready.value || saving.value || index < 0 || index >= data.value.blocks.length) return
  const alreadyDisplayed = start.value === index
  start.value = index
  if (historical.value || pdfSnapshot.value) return
  pending.value = blockLocator(index)
  saveError.value = ''
  if (alreadyDisplayed) void nextTick().then(() => { if (!disposed) void save() })
}
function jump(locator: Pick<DocumentLocator, 'kind' | 'unit_id'>) { choose(locate(locator)) }
function displayed(id: string) { if (id === blocks.value[0]?.id && pending.value) void save() }
async function save() {
  if (savePromise) return savePromise
  if (!pending.value) return
  const locator = pending.value, own = generation
  saving.value = true; saveError.value = ''
  savePromise = (async () => {
    try {
      const saved: DocumentPosition = await documentsApi.savePosition(data.value.textbook_id, locator, revision.value)
      if (disposed || own !== generation) return
      revision.value = saved.revision; pending.value = null; notice.value = ''
    } catch (error) {
      if (!disposed && own === generation) saveError.value = `阅读位置未保存：${getApiErrorMessage(error)}`
    } finally { saving.value = false; savePromise = null }
  })()
  return savePromise
}
async function search(page = 1) {
  const own = ++searchGeneration
  if (!query.value.trim()) { matches.value = []; searchTotal.value = 0; return }
  searching.value = true; searchError.value = ''
  try {
    const result = await documentsApi.search(data.value.textbook_id, query.value, page, data.value.rendition_revision)
    if (disposed || own !== searchGeneration) return
    matches.value = result.items; searchTotal.value = result.total; searchPage.value = page
  } catch (error) { if (!disposed && own === searchGeneration) searchError.value = getApiErrorMessage(error) }
  finally { if (own === searchGeneration) searching.value = false }
}
async function leave(control?: CloseControl): Promise<CloseDecision> {
  if (savePromise) await savePromise
  if (!pending.value) return 'ready'
  const ask = async (): Promise<CloseDecision> => {
    try { await ElMessageBox.confirm('阅读位置尚未保存。仍要离开吗？', '保存提醒', { confirmButtonText: '仍然离开', cancelButtonText: '留下重试' }); return 'discard' }
    catch { return 'stay' }
  }
  return control ? control.confirm(ask, () => ElMessageBox.close()) : ask()
}
const unregister = registerCloseGuard(leave)
onBeforeRouteLeave(async () => (await leave()) !== 'stay')
onBeforeRouteUpdate(async () => (await leave()) !== 'stay')
watch(() => props.initialDocument.rendition_revision, initialize)
onMounted(initialize)
onUnmounted(() => { disposed = true; generation++; searchGeneration++; unregister() })
</script>

<template>
  <div>
    <PageHeader :title="data.original_name" description="资料已保存在本机。按目录阅读，或查找你需要的内容。">
      <template #actions><el-button @click="router.push({ path: '/rag', query: { textbook: String(data.textbook_id), chapter: chapterId ? String(chapterId) : undefined } })">问一问</el-button><el-button @click="router.push({ path: '/exam/generate', query: { textbook: String(data.textbook_id) } })">做练习</el-button></template>
    </PageHeader>
    <el-alert v-if="notice" :title="notice" type="info" :closable="false" />
    <p v-if="historical" role="status">你正在查看引用的旧版本，不会更改当前教材的阅读位置。<el-button @click="router.push(`/textbooks/${data.textbook_id}`)">返回当前教材</el-button></p>
    <p v-else-if="pdfSnapshot" role="status">正在核对引用原页，不会更改阅读进度。<el-button @click="router.push(`/textbooks/${data.textbook_id}`)">进入教材阅读</el-button></p>
    <el-button v-if="!ready" @click="initialize">重试读取位置</el-button>
    <el-alert v-for="warning in data.warnings" :key="warning" :title="warning" type="warning" :closable="false" />
    <p v-if="['docx','pptx'].includes(data.format)" class="format-note">这是结构化阅读，保留文字、表格和支持的图片，不代表原文件的完整排版。复杂公式请对照原文件。</p>
    <div class="study-grid">
      <aside class="surface-card document-nav"><h2>目录</h2>
        <button v-for="chapter in data.chapters" :key="`${chapter.id}-${chapter.locator.unit_id}`" :disabled="!ready || saving" :class="{ active: chapter.id === chapterId }" :style="{ paddingLeft: `${12 + (chapter.level - 1) * 12}px` }" @click="jump(chapter.locator)">{{ chapter.title }}</button>
        <h2>查找内容</h2><el-input v-model="query" placeholder="输入教材中的词语" @keyup.enter="search()" /><el-button :loading="searching" @click="search()">查找</el-button>
        <p v-if="searchError" role="alert">{{ searchError }}</p><p v-if="searchTotal">找到 {{ searchTotal }} 处</p>
        <button v-for="(match, i) in matches" :key="i" :disabled="!ready || saving" @click="jump(match.locator)">{{ match.excerpt }}</button>
        <el-pagination v-if="searchTotal > 30" small layout="prev, pager, next" :page-size="30" :total="searchTotal" :current-page="searchPage" @current-change="search" />
      </aside>
      <main>
        <div v-if="!pdfSnapshot" class="reading-toolbar"><el-button :disabled="!ready || saving || start === 0" @click="choose(Math.max(0,start-20))">上一段</el-button><span>{{ positionLabel }} / {{ data.blocks.length }} 个内容块</span><el-button :disabled="!ready || saving || start+20 >= data.blocks.length" @click="choose(start+20)">下一段</el-button></div>
        <p v-if="saveError" role="alert">{{ saveError }} <el-button @click="save">重试保存</el-button><el-button @click="initialize">重新读取位置</el-button></p>
        <p v-else-if="!historical && !pdfSnapshot" role="status">{{ saving ? '正在保存阅读位置…' : pending ? '等待显示后保存…' : '阅读位置自动保存' }}</p>
        <OriginalPdfReader v-if="pdfSnapshot" :book-id="data.textbook_id" :page="start+1" :page-count="data.page_count || data.blocks.length" :navigation-id="start" :version="data.rendition_revision" @navigate="choose($event-1)" />
        <StructuredDocumentReader v-else :blocks="blocks" @displayed="displayed" />
      </main>
    </div>
  </div>
</template>

<style scoped>
.study-grid{display:grid;grid-template-columns:260px minmax(0,1fr);gap:20px}.document-nav{padding:16px;height:fit-content;max-height:80vh;overflow:auto}.document-nav h2{font-size:16px;margin:12px 0}.document-nav>button{display:block;width:100%;border:0;background:transparent;text-align:left;padding:12px;color:inherit;cursor:pointer;border-radius:8px;line-height:1.5}.document-nav>button:hover,.document-nav>button.active{background:#edf0ff;color:#4653bd}.reading-toolbar{display:flex;justify-content:space-between;align-items:center;gap:12px}.format-note,main>p{font-size:13px;color:#737d92;line-height:1.6}main>p[role=alert]{color:#bd4b49}@media(max-width:800px){.study-grid{grid-template-columns:1fr}.document-nav{max-height:270px}}
</style>
