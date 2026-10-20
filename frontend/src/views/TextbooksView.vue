<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules, type UploadFile } from 'element-plus'
import { CirclePlus, DocumentAdd, Reading, UploadFilled } from '@element-plus/icons-vue'
import PageHeader from '../components/PageHeader.vue'
import StatePanel from '../components/StatePanel.vue'
import { textbookApi, type Textbook } from '../api'
import { getApiErrorMessage } from '../api/http'

const router = useRouter()
const loading = ref(false)
const error = ref('')
const books = ref<Textbook[]>([])
const dialogVisible = ref(false)
const creating = ref(false)
const uploadProgress = ref(0)
const selectedFile = ref<File>()
const formRef = ref<FormInstance>()
const form = reactive({ title: '', subject: '', grade: '', edition: '' })
let refreshTimer: number | undefined
const rules: FormRules = {
  title: [{ required: true, message: '请输入课本名称', trigger: 'blur' }],
  subject: [{ required: true, message: '请输入学科', trigger: 'blur' }],
}

const readyCount = computed(() => books.value.filter((book) => ['ready', 'review'].includes(book.status)).length)
const statusMeta: Record<string, { label: string; type: 'success' | 'info' | 'warning' | 'danger'; className: string }> = {
  draft: { label: '待上传', type: 'info', className: 'draft' },
  processing: { label: '准备中', type: 'warning', className: 'processing' },
  review: { label: '可以学习', type: 'success', className: 'ready' },
  ready: { label: '可学习', type: 'success', className: 'ready' },
  failed: { label: '需要重试', type: 'danger', className: 'failed' },
}

async function load() {
  if (refreshTimer) window.clearTimeout(refreshTimer)
  loading.value = true
  error.value = ''
  try {
    books.value = (await textbookApi.list()).items
  } catch (err) {
    error.value = getApiErrorMessage(err)
  } finally {
    loading.value = false
    if (books.value.some((book) => book.status === 'processing')) {
      refreshTimer = window.setTimeout(() => void load(), 3000)
    }
  }
}

function onFileChange(file: UploadFile) {
  selectedFile.value = file.raw
  if (!form.title) form.title = file.name.replace(/\.pdf$/i, '')
}

function openCreate() {
  dialogVisible.value = true
}

async function createBook() {
  if (!formRef.value || !(await formRef.value.validate().catch(() => false))) return
  creating.value = true
  try {
    const book = await textbookApi.create(form)
    if (selectedFile.value) await textbookApi.upload(book.id, selectedFile.value, (value) => (uploadProgress.value = value))
    ElMessage.success(selectedFile.value ? '课本已上传，准备好后就能阅读' : '课本已添加')
    dialogVisible.value = false
    Object.assign(form, { title: '', subject: '', grade: '', edition: '' })
    selectedFile.value = undefined
    uploadProgress.value = 0
    await load()
  } catch (err) {
    ElMessage.error(getApiErrorMessage(err, '创建教材失败'))
  } finally {
    creating.value = false
  }
}

onMounted(load)
onUnmounted(() => refreshTimer && window.clearTimeout(refreshTimer))
</script>

<template>
  <div>
    <PageHeader title="我的课本" description="上传课本后，点击目录就能阅读。遇到不会的内容，可以问一问、练一练。">
      <template #actions><el-button type="primary" :icon="CirclePlus" @click="openCreate">上传课本</el-button></template>
    </PageHeader>

    <div class="library-summary surface-card">
      <div><span class="summary-icon"><el-icon><Reading /></el-icon></span><div><strong>{{ books.length }}</strong><small>全部教材</small></div></div>
      <div><span class="summary-dot ready"></span><div><strong>{{ readyCount }}</strong><small>可以学习</small></div></div>
      <div><span class="summary-dot processing"></span><div><strong>{{ books.length - readyCount }}</strong><small>还未准备好</small></div></div>
      <p>教材内容仅在你的账户空间中使用，请确保拥有相关资料的合法使用权。</p>
    </div>

    <el-alert v-if="error" class="error-banner" type="warning" :closable="false" show-icon title="教材列表暂不可用" :description="error" />
    <div v-loading="loading" class="book-grid">
      <article v-for="book in books" :key="book.id" class="book-card surface-card" @click="router.push(`/textbooks/${book.id}`)">
        <div class="book-cover" :class="statusMeta[book.status]?.className">
          <div class="cover-lines"></div><el-icon><Reading /></el-icon><span>{{ book.subject || '学习资料' }}</span><small>{{ book.grade || book.edition || '知识学习' }}</small>
          <el-tag class="book-status" :type="statusMeta[book.status]?.type" effect="light" round size="small">{{ statusMeta[book.status]?.label || book.status }}</el-tag>
        </div>
        <div class="book-info">
          <div class="book-heading"><div><h2>{{ book.title || book.name }}</h2><p>{{ [book.grade, book.subject, book.edition].filter(Boolean).join(' · ') || '未设置课本信息' }}</p></div></div>
          <div v-if="book.status === 'processing'" class="parse-progress"><div><span>准备进度</span><strong>{{ book.processing_progress || 0 }}%</strong></div><div class="progress-track"><div class="progress-bar" :style="{ width: `${book.processing_progress || 0}%` }"></div></div></div>
          <div v-else class="book-meta"><span><strong>{{ book.chapter_count || 0 }}</strong> 章节</span><i></i><span><strong>{{ book.knowledge_point_count || 0 }}</strong> 知识点</span><i></i><span><strong>{{ book.question_count || 0 }}</strong> 习题</span></div>
          <p v-if="['ready', 'review'].includes(book.status)" class="task-message">点击课本开始阅读，无需确认。公式和图形请对照原书。</p>
          <p v-else-if="book.processing_message" class="task-message" :class="{ 'task-error': book.status === 'failed' }">{{ book.processing_message }}</p>
        </div>
      </article>
      <button class="add-book-card" type="button" @click="openCreate"><span><el-icon><DocumentAdd /></el-icon></span><strong>添加课本</strong><small>上传 PDF，准备好后直接阅读</small></button>
    </div>
    <StatePanel v-if="!loading && !books.length" title="还没有上传课本" description="从一本你真正想学的教材开始，按自己的节奏开始学习。">
      <el-button type="primary" @click="openCreate">立即导入</el-button>
    </StatePanel>

    <el-dialog v-model="dialogVisible" title="上传课本" width="min(560px, 92vw)" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item label="课本名称" prop="title"><el-input v-model="form.title" placeholder="例如：高中数学 必修第一册" /></el-form-item>
        <div class="form-row"><el-form-item label="学科" prop="subject"><el-input v-model="form.subject" placeholder="数学" /></el-form-item><el-form-item label="年级"><el-input v-model="form.grade" placeholder="高一" /></el-form-item></div>
        <el-form-item label="版本 / 出版社"><el-input v-model="form.edition" placeholder="例如：人教 A 版" /></el-form-item>
        <el-form-item label="教材 PDF（可稍后上传）">
          <el-upload drag :auto-upload="false" :limit="1" accept="application/pdf" :on-change="onFileChange" :on-remove="() => selectedFile = undefined">
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon><div class="el-upload__text">拖入 PDF，或<em>点击选择</em></div><template #tip><div class="el-upload__tip">建议上传能选中文字的 PDF。照片或扫描版课本暂不能直接阅读。</div></template>
          </el-upload>
        </el-form-item>
        <el-progress v-if="uploadProgress" :percentage="uploadProgress" />
      </el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" :loading="creating" @click="createBook">添加课本</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.task-message{margin:10px 0 0;font-size:11px;line-height:1.6;color:#737d92;overflow-wrap:anywhere}.task-error{color:#c64857}
.library-summary{margin-bottom:22px;padding:18px 22px;display:flex;align-items:center;gap:34px}.library-summary>div{display:flex;align-items:center;gap:11px}.summary-icon{width:40px;height:40px;display:grid;place-items:center;border-radius:12px;color:#5561d5;background:#eef0ff}.library-summary strong{display:block;font:700 18px 'Plus Jakarta Sans'}.library-summary small{color:#8b93a7;font-size:10px}.summary-dot{width:9px;height:9px;border-radius:50%}.summary-dot.ready{background:#28b49e}.summary-dot.processing{background:#f1a04f}.library-summary p{margin:0 0 0 auto;max-width:380px;color:#959bad;font-size:10px;line-height:1.7}.book-grid{display:grid;grid-template-columns:repeat(3,minmax(250px,1fr));gap:20px;min-height:180px}.book-card{padding:13px;display:grid;grid-template-columns:118px minmax(0,1fr);gap:17px;cursor:pointer;transition:.2s ease}.book-card:hover{transform:translateY(-3px);box-shadow:var(--shadow-md);border-color:#d8dcf0}.book-cover{position:relative;height:158px;border-radius:12px;overflow:hidden;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#fff;background:linear-gradient(145deg,#5764d9,#2d376f)}.book-cover.ready{background:linear-gradient(145deg,#1fae9c,#286c82)}.book-cover.review{background:linear-gradient(145deg,#ed9a4c,#9a5766)}.book-cover.failed{background:linear-gradient(145deg,#d76073,#72364f)}.book-cover img{width:100%;height:100%;object-fit:cover}.book-cover>.el-icon{position:relative;font-size:27px}.book-cover>span:not(.el-tag){position:relative;margin-top:9px;font-weight:600;font-size:12px}.book-cover>small{position:relative;margin-top:2px;color:rgba(255,255,255,.7);font-size:9px}.cover-lines{position:absolute;inset:0;background:linear-gradient(120deg,transparent 45%,rgba(255,255,255,.08) 45%,rgba(255,255,255,.08) 47%,transparent 47%)}.book-status{position:absolute;top:8px;right:7px}.book-info{min-width:0;padding:6px 3px 4px;display:flex;flex-direction:column}.book-heading{display:flex;justify-content:space-between;gap:5px}.book-heading h2{margin-bottom:6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:14px}.book-heading p{margin:0;color:#8c94aa;font-size:10px;line-height:1.6}.book-heading button{height:24px;border:0;background:transparent;color:#a2a8b8;cursor:pointer}.book-meta{margin-top:auto;display:flex;align-items:center;gap:7px;color:#81899f;font-size:9px;flex-wrap:wrap}.book-meta strong{color:#48516c;font-size:11px}.book-meta i{width:2px;height:2px;border-radius:50%;background:#c6cad6}.parse-progress{margin-top:auto}.parse-progress>div:first-child{margin-bottom:7px;display:flex;justify-content:space-between;color:#8d94a8;font-size:9px}.parse-progress strong{color:#5d67d5}.add-book-card{min-height:184px;border:1px dashed #cfd4e6;border-radius:18px;display:flex;flex-direction:column;align-items:center;justify-content:center;background:rgba(255,255,255,.45);color:#717a93;cursor:pointer}.add-book-card:hover{border-color:#7f89e6;background:#f7f8ff}.add-book-card span{width:45px;height:45px;margin-bottom:11px;display:grid;place-items:center;border-radius:14px;color:#6671da;background:#eef0ff;font-size:20px}.add-book-card strong{font-size:13px}.add-book-card small{margin-top:5px;color:#a0a6b6;font-size:9px}.form-row{display:grid;grid-template-columns:1fr 1fr;gap:16px}.el-upload{width:100%}:deep(.el-upload-dragger){padding:24px}.state-panel+.state-panel{display:none}@media(max-width:1280px){.book-grid{grid-template-columns:repeat(2,minmax(250px,1fr))}}@media(max-width:780px){.library-summary{align-items:flex-start;gap:18px;flex-wrap:wrap}.library-summary p{width:100%;margin:0}.book-grid{grid-template-columns:1fr}}@media(max-width:430px){.book-card{grid-template-columns:96px minmax(0,1fr)}.book-cover{height:140px}.form-row{grid-template-columns:1fr;gap:0}}
</style>
