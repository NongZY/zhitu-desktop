<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, ChatDotRound, CircleCheck, CirclePlus, Document, EditPen, Link, Reading, Upload } from '@element-plus/icons-vue'
import PageHeader from '../components/PageHeader.vue'
import StatePanel from '../components/StatePanel.vue'
import { textbookApi, type Chapter, type KnowledgePoint, type TextbookStructure } from '../api'
import { getApiErrorMessage } from '../api/http'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const loading = ref(true)
const saving = ref(false)
const publishing = ref(false)
const error = ref('')
const structure = ref<TextbookStructure>()
const selectedChapter = ref<Chapter>()
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
const canEdit = computed(() => auth.user?.role === 'teacher' || auth.user?.role === 'admin')
const flatChapters = computed(() => {
  const result: Chapter[] = []
  const walk = (nodes: Chapter[]) => nodes.forEach((node) => { result.push(node); if (node.children) walk(node.children) })
  walk(structure.value?.chapters || [])
  return result
})
const allPoints = computed(() => flatChapters.value.flatMap((chapter) => chapter.knowledge_points || []))
const parseState = computed(() => {
  const states = {
    ready: { title: '教材已发布', description: '结构与知识库已开放使用' },
    processing: { title: '教材解析中', description: '完成后可进入人工审核' },
    review: { title: '等待结构审核', description: '教师确认后即可发布教材' },
    failed: { title: '解析需要处理', description: '请检查文件或人工补充结构' },
    draft: { title: '教材待完善', description: '请添加章节与知识点' },
  }
  return states[structure.value?.textbook.status || 'draft']
})

async function load(preferredChapterId: string | number | undefined = selectedChapter.value?.id) {
  loading.value = true
  error.value = ''
  try {
    structure.value = await textbookApi.getStructure(String(route.params.id))
    selectedChapter.value = flatChapters.value.find((item) => item.id === preferredChapterId) || flatChapters.value[0]
  } catch (err) {
    error.value = getApiErrorMessage(err)
  } finally {
    loading.value = false
  }
}

function onChapterClick(data: Chapter) { selectedChapter.value = data }
function pointStatus(point: KnowledgePoint) { return point.global_knowledge_point_id ? '已映射' : '待映射' }
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
    ElMessage.success('知识点已创建并映射到全局知识点')
  } catch (err) {
    ElMessage.error(getApiErrorMessage(err))
  } finally {
    saving.value = false
  }
}

async function publishTextbook() {
  publishing.value = true
  try {
    await textbookApi.publish(String(route.params.id))
    await load()
    ElMessage.success('教材已发布')
  } catch (err) {
    ElMessage.error(getApiErrorMessage(err))
  } finally {
    publishing.value = false
  }
}
onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <button class="back-link" type="button" @click="router.push('/textbooks')"><el-icon><ArrowLeft /></el-icon>返回教材中心</button>
    <PageHeader :eyebrow="structure?.textbook.subject || 'Textbook Structure'" :title="structure?.textbook.title || '教材结构'" :description="[structure?.textbook.grade, structure?.textbook.edition].filter(Boolean).join(' · ') || '查看章节与知识点解析结果'">
      <template #actions><el-button v-if="canEdit && structure?.textbook.status !== 'ready'" :icon="Upload" :loading="publishing" @click="publishTextbook">发布教材</el-button><el-button :icon="ChatDotRound" @click="router.push({ path: '/rag', query: { textbook: route.params.id } })">向教材提问</el-button><el-button type="primary" :icon="EditPen" @click="router.push({ path: '/exam/generate', query: { textbook: route.params.id } })">按本书组卷</el-button></template>
    </PageHeader>
    <el-alert v-if="error" class="error-banner" type="warning" :closable="false" show-icon title="教材结构暂不可用" :description="error" />

    <template v-if="structure">
      <div class="detail-summary">
        <div><span><el-icon><Document /></el-icon></span><p><strong>{{ flatChapters.length }}</strong><small>章节节点</small></p></div>
        <div><span class="teal"><el-icon><Reading /></el-icon></span><p><strong>{{ allPoints.length }}</strong><small>本地知识点</small></p></div>
        <div><span class="orange"><el-icon><Link /></el-icon></span><p><strong>{{ allPoints.filter(p => p.global_knowledge_point_id).length }}</strong><small>已映射全局知识点</small></p></div>
        <div class="parse-state"><el-icon><CircleCheck /></el-icon><p><strong>{{ parseState.title }}</strong><small>{{ parseState.description }}</small></p></div>
      </div>
      <div class="structure-grid">
        <section class="surface-card chapter-panel">
          <div class="panel-heading"><div><h2>章节目录</h2><p>点击章节查看关联知识点</p></div><el-button v-if="canEdit" size="small" :icon="CirclePlus" @click="openChapterDialog">添加章节</el-button></div>
          <el-tree v-if="structure.chapters.length" class="chapter-tree" :data="structure.chapters" :props="treeProps" node-key="id" default-expand-all highlight-current :expand-on-click-node="false" @node-click="onChapterClick">
            <template #default="{ data }"><span class="tree-node"><el-icon><Document /></el-icon><span>{{ data.title }}</span><small>{{ data.knowledge_points?.length || 0 }}</small></span></template>
          </el-tree>
          <StatePanel v-else compact title="尚未识别章节" description="解析完成或人工创建章节后显示。" />
        </section>
        <section class="surface-card knowledge-panel">
          <div class="panel-heading"><div><p class="eyebrow">CURRENT CHAPTER</p><h2>{{ selectedChapter?.title || '请选择章节' }}</h2><p v-if="selectedChapter?.page_start">教材第 {{ selectedChapter.page_start }}–{{ selectedChapter.page_end || selectedChapter.page_start }} 页</p></div><div class="panel-actions"><el-tag v-if="selectedChapter" effect="plain">{{ selectedChapter.knowledge_points?.length || 0 }} 个知识点</el-tag><el-button v-if="canEdit && selectedChapter" size="small" type="primary" plain :icon="CirclePlus" @click="openPointDialog">添加知识点</el-button></div></div>
          <div v-if="selectedChapter?.knowledge_points?.length" class="knowledge-list">
            <article v-for="(point, index) in selectedChapter.knowledge_points" :key="point.id" class="knowledge-item">
              <span class="point-index">{{ String(index + 1).padStart(2, '0') }}</span>
              <div class="point-copy"><h3>{{ point.name }}</h3><p>{{ point.description || '等待补充知识点描述' }}</p><div><el-tag size="small" :type="point.global_knowledge_point_id ? 'success' : 'info'" effect="light">{{ pointStatus(point) }}</el-tag><span v-if="point.global_name">全局：{{ point.global_name }}</span></div></div>
              <div v-if="point.mastery != null" class="point-mastery"><strong>{{ Math.round(point.mastery * (point.mastery <= 1 ? 100 : 1)) }}%</strong><small>掌握度</small></div>
            </article>
          </div>
          <StatePanel v-else compact title="本章节暂无知识点" description="可等待自动解析完成，或由教师在审核阶段补充。" />
        </section>
      </div>
    </template>

    <el-dialog v-model="chapterDialog" title="添加教材章节" width="min(520px, 92vw)" destroy-on-close>
      <el-form label-position="top">
        <el-form-item label="章节名称" required><el-input v-model="chapterForm.title" maxlength="120" show-word-limit placeholder="例如：第一章 有理数" /></el-form-item>
        <el-form-item label="父章节"><el-select v-model="chapterForm.parent_id" clearable placeholder="留空表示一级章节" style="width:100%"><el-option v-for="chapter in flatChapters" :key="chapter.id" :label="chapter.title" :value="chapter.id" /></el-select></el-form-item>
        <div class="form-row"><el-form-item label="排序"><el-input-number v-model="chapterForm.order_index" :min="0" /></el-form-item><el-form-item label="起始页"><el-input-number v-model="chapterForm.page_start" :min="1" /></el-form-item><el-form-item label="结束页"><el-input-number v-model="chapterForm.page_end" :min="1" /></el-form-item></div>
        <el-form-item label="章节摘要"><el-input v-model="chapterForm.summary" type="textarea" :rows="3" maxlength="1000" placeholder="可选，用于检索和人工审核" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="chapterDialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="createChapter">创建章节</el-button></template>
    </el-dialog>

    <el-dialog v-model="pointDialog" :title="`为“${selectedChapter?.title || ''}”添加知识点`" width="min(520px, 92vw)" destroy-on-close>
      <el-form label-position="top">
        <el-form-item label="知识点名称" required><el-input v-model="pointForm.name" maxlength="160" show-word-limit placeholder="例如：相反数的定义" /></el-form-item>
        <el-form-item label="知识点描述"><el-input v-model="pointForm.description" type="textarea" :rows="4" maxlength="2000" placeholder="描述学习目标、核心概念或常见易错点" /></el-form-item>
        <el-form-item label="排序"><el-input-number v-model="pointForm.order_index" :min="0" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="pointDialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="createKnowledgePoint">添加并映射</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.back-link{margin-bottom:17px;padding:0;display:flex;align-items:center;gap:6px;border:0;background:transparent;color:#7e879e;font-size:11px;cursor:pointer}.back-link:hover{color:var(--primary)}.detail-summary{margin-bottom:20px;display:grid;grid-template-columns:repeat(3,1fr) 1.4fr;gap:12px}.detail-summary>div{padding:16px 18px;display:flex;align-items:center;gap:12px;border:1px solid var(--line);border-radius:15px;background:#fff}.detail-summary>div>span{width:37px;height:37px;display:grid;place-items:center;border-radius:11px;color:#5965d9;background:#eef0ff}.detail-summary>div>span.teal{color:#1cad99;background:#eaf9f6}.detail-summary>div>span.orange{color:#e88c3c;background:#fff2e7}.detail-summary p{margin:0;display:flex;flex-direction:column}.detail-summary strong{font:700 16px 'Plus Jakarta Sans','Noto Sans SC'}.detail-summary small{margin-top:2px;color:#9299ac;font-size:9px}.detail-summary .parse-state{color:#fff;border:0;background:linear-gradient(120deg,#5260d5,#6e58cc)}.parse-state>.el-icon{font-size:28px}.parse-state small{color:rgba(255,255,255,.65)}.structure-grid{display:grid;grid-template-columns:minmax(280px,.72fr) minmax(0,1.5fr);gap:20px}.chapter-panel,.knowledge-panel{min-height:520px;overflow:hidden}.panel-heading{min-height:82px;padding:20px 22px;display:flex;align-items:center;justify-content:space-between;gap:14px;border-bottom:1px solid var(--line)}.panel-heading h2{margin:0;font-size:16px}.panel-heading p:not(.eyebrow){margin:5px 0 0;color:#9299ac;font-size:10px}.panel-heading .eyebrow{margin-bottom:5px}.panel-actions,.form-row{display:flex;align-items:center;gap:10px}.form-row{align-items:flex-start}.form-row>*{flex:1}.chapter-tree{padding:15px 12px;--el-tree-node-hover-bg-color:#f4f5fc;--el-tree-text-color:#4f5871}:deep(.el-tree-node__content){height:43px;border-radius:9px}:deep(.el-tree--highlight-current .el-tree-node.is-current>.el-tree-node__content){color:#4e59ce;background:#eff1ff}.tree-node{width:100%;padding-right:9px;display:flex;align-items:center;gap:8px;font-size:12px}.tree-node small{margin-left:auto;color:#a2a7b6;font-size:9px}.knowledge-list{padding:8px 22px 16px}.knowledge-item{padding:18px 4px;display:flex;align-items:flex-start;gap:14px;border-bottom:1px solid #eff1f5}.knowledge-item:last-child{border:0}.point-index{width:32px;height:32px;flex:0 0 auto;display:grid;place-items:center;border-radius:10px;color:#6570d9;background:#f0f1ff;font:700 10px 'Plus Jakarta Sans'}.point-copy{flex:1}.point-copy h3{margin:1px 0 6px;font-size:13px}.point-copy p{margin:0 0 8px;color:#80889d;font-size:10px;line-height:1.65}.point-copy>div{display:flex;align-items:center;gap:9px;color:#8d94a7;font-size:9px}.point-mastery{display:flex;flex-direction:column;text-align:right}.point-mastery strong{color:#1ca995;font:700 15px 'Plus Jakarta Sans'}.point-mastery small{color:#a0a5b4;font-size:8px}@media(max-width:1050px){.detail-summary{grid-template-columns:repeat(2,1fr)}.structure-grid{grid-template-columns:1fr}.chapter-panel,.knowledge-panel{min-height:0}}@media(max-width:560px){.detail-summary{grid-template-columns:1fr 1fr}.detail-summary .parse-state{grid-column:1/-1}.panel-heading{align-items:flex-start}.panel-actions,.form-row{align-items:stretch;flex-direction:column}.knowledge-item{gap:9px}.point-mastery{display:none}}
</style>
