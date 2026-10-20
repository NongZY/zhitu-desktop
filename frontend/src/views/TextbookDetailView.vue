<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, ChatDotRound, CircleCheck, CirclePlus, Document, EditPen, Reading } from '@element-plus/icons-vue'
import PageHeader from '../components/PageHeader.vue'
import StatePanel from '../components/StatePanel.vue'
import OriginalPdfReader from '../components/OriginalPdfReader.vue'
import { textbookApi, type Chapter, type ChapterContent, type TextbookStructure } from '../api'
import { getApiErrorMessage } from '../api/http'
import { useWorkspaceStore } from '../stores/workspace'
import { registerCloseGuard, type CloseDecision, type CloseControl } from '../runtime/close'
import { useReadingProgress } from '../composables/useReadingProgress'
import { resolveReadingTarget } from '../utils/readingNavigation'

const route = useRoute()
const router = useRouter()
const workspace = useWorkspaceStore()
const bookId = computed(() => Number(route.params.id))
const userId = computed(() => workspace.ownerId)
const documentRevision = ref<string | null>(null)
const readerCount = ref(0)
const readerPage = ref<number | null>(null)
const navigationId = ref(0)
const readerLoading = ref(true)
const readerError = ref('')
const readingNotice = ref('')
const needsPositionChoice = ref(false)
const displayedPage = ref<number | null>(null)
const progressState = useReadingProgress({ bookId, userId, documentRevision })
const { status: readingStatus, error: progressError } = progressState
async function prepareLeave(control?: CloseControl): Promise<CloseDecision> {
  if (await progressState.flush()) return 'ready'
  const ask = async (): Promise<CloseDecision> => {
    try {
      await ElMessageBox.confirm('阅读位置尚未保存。可以留在这里重试，或放弃这次位置后离开；已保存的资料不会删除。', '位置未保存', { confirmButtonText: '放弃位置并离开', cancelButtonText: '留在这里', type: 'warning' })
      return 'discard'
    } catch { return 'stay' }
  }
  return control ? control.confirm(ask, () => ElMessageBox.close()) : ask()
}
const unregisterClose = registerCloseGuard(prepareLeave)
onBeforeRouteLeave(async () => (await prepareLeave()) !== 'stay')
onBeforeRouteUpdate(async (to, from) => to.params.id === from.params.id || (await prepareLeave()) !== 'stay')
onUnmounted(unregisterClose)
let readerRequest = 0
let readerAbort: AbortController | undefined
const loading = ref(true)
const saving = ref(false)
const recognizing = ref(false)
const error = ref('')
const structure = ref<TextbookStructure>()
const readingChapters = computed(() => structure.value?.chapters || [])
const selectedChapter = ref<Chapter>()
const chapterSearch = ref('')
const contentItems = ref<ChapterContent[]>([])
const showExtracted = ref(false)
const contentLoading = ref(false)
const contentError = ref('')
const contentPage = ref(1)
const contentTotal = ref(0)
let contentRequest = 0
let structureRequest = 0
const pageImageDialog = ref(false)
const pageImagePage = ref(0)
const pageImageUrl = ref('')
const pageImageLoading = ref(false)
const pageImageError = ref('')
let pageImageRequest = 0
let pageImageController: AbortController | undefined

function clearPageImage() {
  pageImageRequest++
  pageImageController?.abort()
  pageImageController = undefined
  if (pageImageUrl.value) URL.revokeObjectURL(pageImageUrl.value)
  pageImageUrl.value = ''
  pageImageLoading.value = false
}

async function viewOriginalPage(pageNumber: number) {
  clearPageImage()
  const request = pageImageRequest
  const controller = new AbortController()
  pageImageController = controller
  pageImagePage.value = pageNumber
  pageImageDialog.value = true
  pageImageError.value = ''
  pageImageLoading.value = true
  try {
    const blob = await textbookApi.pageImage(String(route.params.id), pageNumber, controller.signal)
    if (request !== pageImageRequest) return
    pageImageUrl.value = URL.createObjectURL(blob)
  } catch (err) {
    if (request === pageImageRequest) pageImageError.value = getApiErrorMessage(err, '原页暂时无法加载，请重试')
  } finally {
    if (request === pageImageRequest) pageImageLoading.value = false
  }
}

watch(pageImageDialog, (visible) => { if (!visible) clearPageImage() }, { flush: 'sync' })
watch([() => selectedChapter.value?.id, contentPage, () => route.params.id], () => {
  pageImageDialog.value = false
  clearPageImage()
})
onUnmounted(() => { contentRequest++; structureRequest++; readerRequest++; readerAbort?.abort(); progressState.dispose(); clearPageImage() })
const filteredChapters = computed(() => {
  const query = chapterSearch.value.trim().toLowerCase()
  const filter = (chapters: Chapter[]): Chapter[] => chapters.flatMap((chapter) => {
    const children = filter(chapter.children || [])
    const matches = chapter.title.toLowerCase().includes(query)
      || chapter.knowledge_points?.some(point => point.name.toLowerCase().includes(query))
    return matches ? [chapter] : children.length ? [{ ...chapter, children }] : []
  })
  return filter(structure.value?.chapters || [])
})

async function loadContent() {
  const request = ++contentRequest
  contentItems.value = []
  contentTotal.value = 0
  contentError.value = ''
  if (!selectedChapter.value) { contentLoading.value = false; return }
  contentLoading.value = true
  try {
    const result = await textbookApi.chapterContent(selectedChapter.value.id, contentPage.value)
    if (request !== contentRequest) return
    contentItems.value = result.items
    contentTotal.value = result.total
  } catch (err) {
    if (request === contentRequest) contentError.value = getApiErrorMessage(err)
  } finally {
    if (request === contentRequest) contentLoading.value = false
  }
}
watch(() => selectedChapter.value?.id, () => {
  contentPage.value = 1; contentItems.value = []; showExtracted.value = false
})
watch(showExtracted, (visible) => { if (visible) void loadContent() })
const chapterDialog = ref(false)
const pointDialog = ref(false)
const chapterForm = reactive<{
  title: string
  parent_id?: string | number
  order_index: number
  page_start?: number
  page_end?: number
  summary: string
}>({ title: '', parent_id: undefined, order_index: 0, page_start: undefined, page_end: undefined, summary: '' })
const pointForm = reactive({ name: '', description: '', order_index: 0 })

const treeProps = { children: 'children', label: 'title' }
const flatChapters = computed(() => {
  const result: Chapter[] = []
  const walk = (nodes: Chapter[]) => nodes.forEach((node) => { result.push(node); if (node.children) walk(node.children) })
  walk(structure.value?.chapters || [])
  return result
})
const allPoints = computed(() => flatChapters.value.flatMap((chapter) => chapter.knowledge_points || []))
const parseState = computed(() => {
  const states = {
    ready: { title: '可以学习了', description: '点击左侧目录开始阅读' },
    processing: { title: '正在准备课本', description: '准备好后就能直接阅读' },
    review: { title: '可以学习了', description: '无需确认，点击左侧目录开始阅读' },
    failed: { title: '课本没准备好', description: '文件可能无法读取，请换一份可选中文字的 PDF' },
    draft: { title: '还没有课本内容', description: '上传 PDF 后，就能按章节阅读' },
  }
  return states[structure.value?.textbook.status || 'draft']
})

async function load(preferredChapterId: string | number | undefined = selectedChapter.value?.id ?? String(route.query.chapter || '')) {
  const request = ++structureRequest
  loading.value = true
  error.value = ''
  try {
    const result = await textbookApi.getStructure(String(route.params.id))
    if (request !== structureRequest) return
    structure.value = result
    selectedChapter.value = flatChapters.value.find((item) => String(item.id) === String(preferredChapterId)) || flatChapters.value[0]
    if (!readerLoading.value) applyReadingTarget()
  } catch (err) {
    if (request === structureRequest) error.value = getApiErrorMessage(err)
  } finally {
    if (request === structureRequest) loading.value = false
  }
}

function applyReadingTarget() {
  if (readerLoading.value) return
  const target = resolveReadingTarget({ pageQuery: route.query.page, chapterQuery: route.query.chapter,
    chapters: structure.value?.chapters || [], pageCount: readerCount.value,
    progress: progressState.progress.value, documentRevision: documentRevision.value })
  readerPage.value = target.page; navigationId.value++; displayedPage.value = null
  selectedChapter.value = flatChapters.value.find(c => Number(c.id) === target.chapterId)
  readingNotice.value = target.notice || ''
}
async function openReader(restoreSaved = false) {
  const request = ++readerRequest
  readerAbort?.abort(); readerAbort = new AbortController()
  readerLoading.value = true; readerError.value = ''; readingNotice.value = ''
  readerPage.value = null; readerCount.value = 0; documentRevision.value = null
  displayedPage.value = null; needsPositionChoice.value = false
  navigationId.value++
  selectedChapter.value = undefined
  structure.value = undefined
  const metadata = textbookApi.reader(String(route.params.id), readerAbort.signal).then(info => {
    if (request !== readerRequest) return
    readerCount.value = info.page_count; documentRevision.value = info.document_revision
  }).catch(err => {
    if (request === readerRequest) readerError.value = getApiErrorMessage(err, '课本暂时无法读取')
  })
  await Promise.all([load(String(route.query.chapter || '')), metadata, progressState.reload()])
  if (request !== readerRequest) return
  if (restoreSaved && !readerError.value && readingStatus.value !== 'error') {
    const target = resolveReadingTarget({ chapters: readingChapters.value, pageCount: readerCount.value,
      progress: progressState.progress.value, documentRevision: documentRevision.value })
    const { page: _page, chapter: _chapter, ...query } = route.query
    await router.replace({ path: `/textbooks/${bookId.value}`, query: { ...query, ...(target.page ? { page: String(target.page) } : {}) } })
    if (request !== readerRequest) return
  }
  readerLoading.value = false
  needsPositionChoice.value = !!progressState.progress.value && progressState.progress.value.document_revision !== documentRevision.value
  applyReadingTarget()
}
watch([() => route.params.id, userId], () => { void openReader() })
watch([() => route.query.page, () => route.query.chapter], applyReadingTarget)

function onChapterClick(data: Chapter) {
  needsPositionChoice.value = false
  const { page: _page, ...query } = route.query
  void router.push({ path: `/textbooks/${bookId.value}`, query: { ...query, chapter: String(data.id) } })
}
function navigateReading(page: number) {
  needsPositionChoice.value = false
  const { chapter: _chapter, ...query } = route.query
  if (String(route.query.page) === String(page)) { applyReadingTarget(); return }
  void router.replace({ path: `/textbooks/${bookId.value}`, query: { ...query, page: String(page) } })
}
function pageDisplayed(position: { page: number; navigationId: number }) {
  if (position.navigationId !== navigationId.value || position.page !== readerPage.value) return
  displayedPage.value = position.page
  if (!needsPositionChoice.value) progressState.recordDisplayed(position.page, selectedChapter.value ? Number(selectedChapter.value.id) : null)
}
function chooseCurrentPosition() {
  needsPositionChoice.value = false
  if (displayedPage.value !== null) progressState.recordDisplayed(displayedPage.value, selectedChapter.value ? Number(selectedChapter.value.id) : null)
}
function openChapterDialog() {
  Object.assign(chapterForm, { title: '', parent_id: undefined, order_index: flatChapters.value.length, page_start: undefined, page_end: undefined, summary: '' })
  chapterDialog.value = true
}

function openPointDialog() {
  Object.assign(pointForm, { name: '', description: '', order_index: selectedChapter.value?.knowledge_points?.length || 0 })
  pointDialog.value = true
}

async function createChapter() {
  if (!chapterForm.title.trim()) return ElMessage.warning('请输入章节名称')
  if (chapterForm.page_start && chapterForm.page_end && chapterForm.page_end < chapterForm.page_start) {
    return ElMessage.warning('结束页不能小于起始页')
  }
  saving.value = true
  try {
    const chapter = await textbookApi.createChapter(String(route.params.id), {
      ...chapterForm,
      title: chapterForm.title.trim(),
      summary: chapterForm.summary.trim() || undefined,
    })
    chapterDialog.value = false
    await load(chapter.id)
    ElMessage.success('章节已创建')
  } catch (err) {
    ElMessage.error(getApiErrorMessage(err))
  } finally {
    saving.value = false
  }
}

async function createKnowledgePoint() {
  if (!selectedChapter.value) return ElMessage.warning('请先选择章节')
  if (!pointForm.name.trim()) return ElMessage.warning('请输入知识点名称')
  saving.value = true
  try {
    await textbookApi.createKnowledgePoint(selectedChapter.value.id, {
      ...pointForm,
      name: pointForm.name.trim(),
      description: pointForm.description.trim() || undefined,
    })
    const chapterId = selectedChapter.value.id
    pointDialog.value = false
    await load(chapterId)
    ElMessage.success('学习要点已保存')
  } catch (err) {
    ElMessage.error(getApiErrorMessage(err))
  } finally {
    saving.value = false
  }
}

async function recognizeOutline() {
  recognizing.value = true
  try {
    const result = await textbookApi.recognizeOutline(String(route.params.id))
    await load()
    if (result.added) ElMessage.success(result.message)
    else ElMessage.info(result.message)
  } catch (err) {
    ElMessage.error(getApiErrorMessage(err))
  } finally {
    recognizing.value = false
  }
}
onMounted(() => { void openReader() })
</script>

<template>
  <div v-loading="loading">
    <button class="back-link" type="button" @click="router.push('/textbooks')"><el-icon><ArrowLeft /></el-icon>返回我的课本</button>
    <PageHeader :eyebrow="structure?.textbook.subject || '我的课本'" :title="structure?.textbook.title || '课本内容'" :description="[structure?.textbook.grade, structure?.textbook.edition].filter(Boolean).join(' · ') || '点击目录，开始学习'">
      <template #actions><el-button :icon="ChatDotRound" @click="router.push({ path: '/rag', query: { textbook: route.params.id } })">问一问</el-button><el-button type="primary" :icon="EditPen" @click="router.push({ path: '/exam/generate', query: { textbook: route.params.id, chapter: selectedChapter?.id } })">练一练</el-button></template>
    </PageHeader>
    <el-alert v-if="error" class="error-banner" type="warning" :closable="false" show-icon title="课本暂时没有加载出来" :description="error" />

    <template v-if="structure">
      <div class="detail-summary">
        <div><span><el-icon><Document /></el-icon></span><p><strong>{{ flatChapters.length }}</strong><small>章节与小节</small></p></div>
        <div><span class="teal"><el-icon><Reading /></el-icon></span><p><strong>{{ allPoints.length }}</strong><small>学习要点</small></p></div>
        <div class="parse-state"><el-icon><CircleCheck /></el-icon><p><strong>{{ parseState.title }}</strong><small>{{ parseState.description }}</small></p></div>
      </div>
      <div class="structure-grid">
        <section class="surface-card chapter-panel">
          <div class="panel-heading"><div><h2>章节目录</h2><p>点击章节开始阅读</p></div><div class="panel-actions"><el-button v-if="!structure.chapters.length" size="small" :loading="recognizing" @click="recognizeOutline">识别章节</el-button><el-button size="small" :icon="CirclePlus" @click="openChapterDialog">添加章节</el-button></div></div>
          <div class="chapter-search"><el-input v-model="chapterSearch" clearable placeholder="搜索章节或知识点，如：绝对值" aria-label="搜索章节或知识点" /></div>
          <el-tree v-if="structure.chapters.length" class="chapter-tree" :data="filteredChapters" :props="treeProps" node-key="id" :current-node-key="selectedChapter?.id" default-expand-all highlight-current :expand-on-click-node="false" @node-click="onChapterClick">
            <template #default="{ data }"><span class="tree-node" :title="data.title"><el-icon><Document /></el-icon><span>{{ data.title }}</span><small>{{ data.knowledge_points?.length || 0 }}</small></span></template>
          </el-tree>
          <StatePanel v-else compact title="尚未识别章节" description="课本准备好后可以重试识别，也可以自己添加章节。" />
        </section>
        <section class="surface-card knowledge-panel">
          <div class="panel-heading"><div><p class="eyebrow">当前章节</p><h2>{{ selectedChapter?.title || '请选择章节' }}</h2><p v-if="selectedChapter?.page_start">PDF 第 {{ selectedChapter.page_start }}–{{ selectedChapter.page_end || selectedChapter.page_start }} 页（含封面，与书上印刷页码可能不同）</p></div><div class="panel-actions"><el-button v-if="selectedChapter" size="small" :icon="ChatDotRound" @click="router.push({ path: '/rag', query: { textbook: route.params.id, chapter: selectedChapter.id } })">就本章提问</el-button><el-button v-if="selectedChapter" size="small" type="primary" plain :icon="CirclePlus" @click="openPointDialog">添加知识点</el-button></div></div>
          <div v-if="selectedChapter?.children?.length" class="section-links"><el-button v-for="child in selectedChapter.children" :key="child.id" text @click="onChapterClick(child)">{{ child.title }}</el-button></div>
          <div v-if="selectedChapter?.knowledge_points?.length" class="knowledge-list">
            <article v-for="(point, index) in selectedChapter.knowledge_points" :key="point.id" class="knowledge-item">
              <span class="point-index">{{ String(index + 1).padStart(2, '0') }}</span>
              <div class="point-copy"><h3>{{ point.name }}</h3><p>{{ point.description || '可以记下自己的理解或容易出错的地方' }}</p><el-tag size="small" type="info" effect="light">学习要点</el-tag></div>
              <div v-if="point.mastery != null" class="point-mastery"><strong>{{ Math.round(point.mastery * (point.mastery <= 1 ? 100 : 1)) }}%</strong><small>掌握度</small></div>
            </article>
          </div>
          <p v-if="readerLoading" role="status">正在打开课本…</p>
          <p v-else-if="readerError" role="alert">{{ readerError }} <el-button text @click="openReader()">重新读取课本</el-button></p>
          <template v-else>
            <p v-if="readingNotice" role="status">{{ readingNotice }}</p>
            <p v-if="needsPositionChoice"><el-button @click="chooseCurrentPosition">从这一页开始阅读</el-button></p>
            <div class="reading-save-state" aria-live="polite">
              <span v-if="readingStatus === 'saving'">阅读位置保存中…</span>
              <span v-else-if="readingStatus === 'saved'">阅读位置已保存</span>
              <span v-else-if="readingStatus === 'error' || readingStatus === 'conflict'">{{ progressError }}</span>
              <el-button v-if="readingStatus === 'error'" text @click="progressState.retry">重试保存位置</el-button>
              <el-button v-if="readingStatus === 'conflict'" text @click="openReader(true)">重新载入位置</el-button>
            </div>
            <OriginalPdfReader :key="`${route.params.id}:${userId}`" :book-id="String(route.params.id)" :chapter="selectedChapter" :page="readerPage" :page-count="readerCount" :navigation-id="navigationId" @navigate="navigateReading" @page-displayed="pageDisplayed" />
          </template>
          <div v-if="selectedChapter" class="chapter-content">
            <el-button @click="showExtracted = !showExtracted">{{ showExtracted ? '收起提取文字' : '查看提取文字（辅助）' }}</el-button>
            <div v-if="showExtracted" v-loading="contentLoading">
            <p class="content-note">文字提取可能不完整，公式和颜色请以原页为准。</p>
            <el-alert v-if="contentError" type="error" :closable="false" :title="contentError" />
            <article v-for="item in contentItems" :key="item.id" class="content-excerpt">
              <div class="excerpt-heading">
                <small>{{ item.page_number ? `PDF 第 ${item.page_number} 页` : '正文片段' }}</small>
                <el-button v-if="item.page_number && item.page_number > 0" size="small" text type="primary" @click="viewOriginalPage(item.page_number)">查看原页</el-button>
              </div>
              <el-alert v-if="item.quality_note" type="warning" :closable="false" show-icon :title="item.quality_note" />
              <p>{{ item.content }}</p>
            </article>
            <StatePanel v-if="!contentLoading && !contentError && !contentItems.length" compact title="这一节还没有读到文字" description="可以换个章节试试，或对照原课本阅读。" />
            <el-pagination v-if="contentTotal > 10" v-model:current-page="contentPage" :page-size="10" :total="contentTotal" layout="prev, pager, next" @current-change="loadContent" />
            </div>
          </div>
        </section>
      </div>
    </template>

    <el-dialog v-model="pageImageDialog" :title="`PDF 第 ${pageImagePage} 页`" width="min(1000px, 96vw)" destroy-on-close>
      <div class="original-page" :aria-busy="pageImageLoading">
        <p v-if="pageImageLoading" role="status">正在加载原页…</p>
        <el-alert v-else-if="pageImageError" type="error" :closable="false" show-icon :title="pageImageError" />
        <img v-else-if="pageImageUrl" :src="pageImageUrl" :alt="`课本原页：PDF 第 ${pageImagePage} 页`" />
      </div>
      <template #footer><el-button v-if="pageImageError" @click="viewOriginalPage(pageImagePage)">重新加载原页</el-button><el-button @click="pageImageDialog = false">关闭</el-button></template>
    </el-dialog>

    <el-dialog v-model="chapterDialog" title="添加教材章节" width="min(520px, 92vw)" destroy-on-close>
      <el-form label-position="top">
        <el-form-item label="章节名称" required><el-input v-model="chapterForm.title" maxlength="120" show-word-limit placeholder="例如：第一章 有理数" /></el-form-item>
        <el-form-item label="属于哪一章"><el-select v-model="chapterForm.parent_id" clearable placeholder="不选就是独立的一章" style="width:100%"><el-option v-for="chapter in flatChapters" :key="chapter.id" :label="chapter.title" :value="chapter.id" /></el-select></el-form-item>
        <div class="form-row"><el-form-item label="排序"><el-input-number v-model="chapterForm.order_index" :min="0" /></el-form-item><el-form-item label="起始页"><el-input-number v-model="chapterForm.page_start" :min="1" /></el-form-item><el-form-item label="结束页"><el-input-number v-model="chapterForm.page_end" :min="1" /></el-form-item></div>
        <el-form-item label="章节摘要"><el-input v-model="chapterForm.summary" type="textarea" :rows="3" maxlength="1000" placeholder="可选，写下这一章主要讲什么" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="chapterDialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="createChapter">创建章节</el-button></template>
    </el-dialog>

    <el-dialog v-model="pointDialog" :title="`为“${selectedChapter?.title || ''}”添加知识点`" width="min(520px, 92vw)" destroy-on-close>
      <el-form label-position="top">
        <el-form-item label="知识点名称" required><el-input v-model="pointForm.name" maxlength="160" show-word-limit placeholder="例如：相反数的定义" /></el-form-item>
        <el-form-item label="知识点描述"><el-input v-model="pointForm.description" type="textarea" :rows="4" maxlength="2000" placeholder="描述学习目标、核心概念或常见易错点" /></el-form-item>
        <el-form-item label="排序"><el-input-number v-model="pointForm.order_index" :min="0" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="pointDialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="createKnowledgePoint">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.excerpt-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}.original-page{min-height:160px;max-height:75vh;overflow:auto;text-align:center}.original-page img{display:block;width:100%;height:auto}.original-page>p{padding:50px 0;color:#80889d}
.chapter-panel .chapter-tree{max-height:70vh;overflow:auto}
.chapter-search{padding:12px 16px 0}.section-links{display:flex;flex-wrap:wrap;padding:12px 18px;gap:4px}.section-links .el-button{margin:0;white-space:normal;height:auto;text-align:left}.chapter-content{padding:18px 22px}.chapter-content h3{margin-top:0}.content-note{color:#80889d;font-size:12px;line-height:1.7}.content-excerpt{padding:16px 0;border-bottom:1px solid var(--line)}.content-excerpt small{color:#6570d9}.content-excerpt p{white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px;line-height:1.9}.chapter-content .el-pagination{margin-top:18px}.tree-node>span{overflow:hidden;text-overflow:ellipsis}
.back-link{margin-bottom:17px;padding:0;display:flex;align-items:center;gap:6px;border:0;background:transparent;color:#7e879e;font-size:11px;cursor:pointer}.back-link:hover{color:var(--primary)}.detail-summary{margin-bottom:20px;display:grid;grid-template-columns:1fr 1fr 1.4fr;gap:12px}.detail-summary>div{padding:16px 18px;display:flex;align-items:center;gap:12px;border:1px solid var(--line);border-radius:15px;background:#fff}.detail-summary>div>span{width:37px;height:37px;display:grid;place-items:center;border-radius:11px;color:#5965d9;background:#eef0ff}.detail-summary>div>span.teal{color:#1cad99;background:#eaf9f6}.detail-summary>div>span.orange{color:#e88c3c;background:#fff2e7}.detail-summary p{margin:0;display:flex;flex-direction:column}.detail-summary strong{font:700 16px 'Plus Jakarta Sans','Noto Sans SC'}.detail-summary small{margin-top:2px;color:#9299ac;font-size:9px}.detail-summary .parse-state{color:#fff;border:0;background:linear-gradient(120deg,#5260d5,#6e58cc)}.parse-state>.el-icon{font-size:28px}.parse-state small{color:rgba(255,255,255,.65)}.structure-grid{display:grid;grid-template-columns:minmax(280px,.72fr) minmax(0,1.5fr);gap:20px}.chapter-panel,.knowledge-panel{min-height:520px;overflow:hidden}.panel-heading{min-height:82px;padding:20px 22px;display:flex;align-items:center;justify-content:space-between;gap:14px;border-bottom:1px solid var(--line)}.panel-heading h2{margin:0;font-size:16px}.panel-heading p:not(.eyebrow){margin:5px 0 0;color:#9299ac;font-size:10px}.panel-heading .eyebrow{margin-bottom:5px}.panel-actions,.form-row{display:flex;align-items:center;gap:10px}.form-row{align-items:flex-start}.form-row>*{flex:1}.chapter-tree{padding:15px 12px;--el-tree-node-hover-bg-color:#f4f5fc;--el-tree-text-color:#4f5871}:deep(.el-tree-node__content){height:43px;border-radius:9px}:deep(.el-tree--highlight-current .el-tree-node.is-current>.el-tree-node__content){color:#4e59ce;background:#eff1ff}.tree-node{width:100%;padding-right:9px;display:flex;align-items:center;gap:8px;font-size:12px}.tree-node small{margin-left:auto;color:#a2a7b6;font-size:9px}.knowledge-list{padding:8px 22px 16px}.knowledge-item{padding:18px 4px;display:flex;align-items:flex-start;gap:14px;border-bottom:1px solid #eff1f5}.knowledge-item:last-child{border:0}.point-index{width:32px;height:32px;flex:0 0 auto;display:grid;place-items:center;border-radius:10px;color:#6570d9;background:#f0f1ff;font:700 10px 'Plus Jakarta Sans'}.point-copy{flex:1}.point-copy h3{margin:1px 0 6px;font-size:13px}.point-copy p{margin:0 0 8px;color:#80889d;font-size:10px;line-height:1.65}.point-copy>div{display:flex;align-items:center;gap:9px;color:#8d94a7;font-size:9px}.point-mastery{display:flex;flex-direction:column;text-align:right}.point-mastery strong{color:#1ca995;font:700 15px 'Plus Jakarta Sans'}.point-mastery small{color:#a0a5b4;font-size:8px}@media(max-width:1050px){.detail-summary{grid-template-columns:repeat(2,1fr)}.structure-grid{grid-template-columns:1fr}.chapter-panel,.knowledge-panel{min-height:0}}@media(max-width:560px){.detail-summary{grid-template-columns:1fr 1fr}.detail-summary .parse-state{grid-column:1/-1}.panel-heading{align-items:flex-start}.panel-actions,.form-row{align-items:stretch;flex-direction:column}.knowledge-item{gap:9px}.point-mastery{display:none}}
</style>
