<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import PageHeader from '../components/PageHeader.vue'
import { examApi, textbookApi, type Chapter, type ExamGeneratePayload, type QuestionType, type Textbook } from '../api'
import { getApiErrorMessage } from '../api/http'
const route = useRoute()
const router = useRouter()
const books = ref<Textbook[]>([])
const chapters = ref<Chapter[]>([])
const chapterId = ref<string | number>()
const knowledgePointId = ref<string | number>()
const scopeError = ref('')
const loading = ref(false)
const loadingBooks = ref(true)
const booksError = ref('')
const chaptersError = ref('')
const loadingChapters = ref(false)
const error = ref('')
const advanced = ref(false)
let requestId = 0
const questionTypes: Array<{ value: QuestionType; label: string }> = [
  { value: 'single_choice', label: '单选题' },
  { value: 'multiple_choice', label: '多选题' },
  { value: 'true_false', label: '判断题' },
  { value: 'fill_blank', label: '填空题' },
  { value: 'short_answer', label: '简答题' },
]
const form = reactive<ExamGeneratePayload>({ question_count: 5, duration_minutes: 20, mode: 'adaptive', auto_fill: true, question_types: questionTypes.map(type => type.value) })
function flattenChapters(nodes: Chapter[]): Chapter[] {
  return nodes.flatMap(node => [node, ...flattenChapters(node.children || [])])
}
const chapterOptions = computed(() => {
  const walk = (nodes: Chapter[], depth = 0): Array<{ id: string | number; label: string }> =>
    nodes.flatMap(n => [{ id: n.id, label: `${'　'.repeat(depth)}${n.title}` }, ...walk(n.children || [], depth + 1)])
  return walk(chapters.value)
})
const knowledgePointOptions = computed(() => {
  const selected = flattenChapters(chapters.value).find(chapter => chapter.id === chapterId.value)
  return flattenChapters(selected ? [selected] : chapters.value).flatMap(chapter => chapter.knowledge_points || [])
})
const canGenerate = computed(() => !loading.value && !loadingBooks.value && !loadingChapters.value
  && !booksError.value && !chaptersError.value && !scopeError.value && !!form.textbook_id && !!form.question_types?.length)
function changeChapter() {
  knowledgePointId.value = undefined
  scopeError.value = ''
}
async function loadChapters(id = form.textbook_id) {
  const request = ++requestId
  chapterId.value = undefined
  knowledgePointId.value = undefined
  chapters.value = []
  error.value = ''
  chaptersError.value = ''
  scopeError.value = ''
  if (!id) { loadingChapters.value = false; return }
  loadingChapters.value = true
  try {
    const result = await textbookApi.getStructure(id)
    if (request !== requestId) return
    chapters.value = result.chapters
    if (String(id) === route.query.textbook) {
      if (route.query.chapter) {
        chapterId.value = chapterOptions.value.find(c => String(c.id) === route.query.chapter)?.id
        if (chapterId.value === undefined) {
          scopeError.value = '指定章节已失效，请重新选择练习范围。'
          return
        }
      }
      if (route.query.knowledgePoint) {
        knowledgePointId.value = knowledgePointOptions.value.find(point => String(point.id) === route.query.knowledgePoint)?.id
        if (knowledgePointId.value === undefined) scopeError.value = '指定知识点已失效或不属于所选章节，请重新选择练习范围。'
      }
    }
  } catch (err) { if (request === requestId) chaptersError.value = getApiErrorMessage(err) }
  finally { if (request === requestId) loadingChapters.value = false }
}
watch(() => form.textbook_id, id => void loadChapters(id))
async function generate() {
  if (!canGenerate.value) return
  if (!form.textbook_id) return ElMessage.warning('请先选一本课本')
  loading.value = true
  error.value = ''
  try {
    const paper = await examApi.generate({ ...form, chapter_ids: chapterId.value ? [chapterId.value] : [], knowledge_point_ids: knowledgePointId.value ? [knowledgePointId.value] : [] })
    await router.push(`/exam/${paper.id}/take`)
  } catch (err) { error.value = getApiErrorMessage(err, '这次练习没有准备好，请稍后再试') }
  finally { loading.value = false }
}
async function loadBooks() {
  loadingBooks.value = true
  booksError.value = ''
  scopeError.value = ''
  try {
    books.value = (await textbookApi.list()).items.filter(b => ['ready', 'review'].includes(b.status))
    const previousBook = form.textbook_id
    if (route.query.textbook) {
      form.textbook_id = books.value.find(b => String(b.id) === route.query.textbook)?.id
      if (form.textbook_id === undefined) scopeError.value = '指定课本已失效或尚未准备好，请重新选择课本。'
    } else if (route.query.chapter || route.query.knowledgePoint) {
      form.textbook_id = undefined
      scopeError.value = '练习入口缺少课本信息，请重新选择练习范围。'
    } else {
      form.textbook_id = books.value[0]?.id
    }
    if (form.textbook_id && form.textbook_id === previousBook) await loadChapters(form.textbook_id)
  } catch (err) { booksError.value = getApiErrorMessage(err) }
  finally { loadingBooks.value = false }
}
onMounted(loadBooks)
watch(() => route.query, loadBooks)
</script>

<template>
  <div>
    <PageHeader title="做练习" description="选一本课本，做几道题，看看自己学会了多少。" />
    <section class="surface-card practice-card">
      <el-alert v-if="error" type="warning" :closable="false" show-icon :title="error" />
      <p v-if="loadingBooks" role="status">正在加载课本…</p>
      <div v-else-if="booksError"><el-alert type="warning" :closable="false" title="课本暂时没有加载出来" :description="booksError" /><el-button @click="loadBooks">重新加载课本</el-button></div>
      <el-empty v-else-if="!books.length" description="先上传一本课本，再来做练习"><el-button type="primary" @click="router.push('/textbooks')">去上传课本</el-button></el-empty>
      <el-form v-else label-position="top" size="large" @submit.prevent="generate">
        <el-form-item label="哪本课本？"><el-select v-model="form.textbook_id" style="width:100%"><el-option v-for="book in books" :key="book.id" :label="book.title" :value="book.id" /></el-select></el-form-item>
        <el-form-item label="练哪一章？"><el-select v-model="chapterId" clearable filterable :disabled="loadingChapters || !form.textbook_id" :loading="loadingChapters" placeholder="整本课本，也可以选择章节" style="width:100%" @change="changeChapter"><el-option v-for="chapter in chapterOptions" :key="chapter.id" :label="chapter.label" :value="chapter.id" /></el-select></el-form-item>
        <el-form-item v-if="knowledgePointOptions.length" label="练哪个知识点？"><el-select v-model="knowledgePointId" clearable filterable placeholder="所选范围内的全部知识点" style="width:100%" @change="scopeError = ''"><el-option v-for="point in knowledgePointOptions" :key="point.id" :label="point.name" :value="point.id" /></el-select></el-form-item>
        <el-alert v-if="scopeError" type="warning" :closable="false" :title="scopeError" />
        <div v-if="chaptersError"><el-alert type="warning" :closable="false" title="章节暂时没有加载出来，请重试后再开始" :description="chaptersError" /><el-button @click="loadChapters()">重新加载章节</el-button></div>
        <el-form-item label="做几道题？"><el-radio-group v-model="form.question_count"><el-radio-button :value="5">5 道</el-radio-button><el-radio-button :value="10">10 道</el-radio-button><el-radio-button :value="15">15 道</el-radio-button></el-radio-group></el-form-item>
        <el-form-item label="练哪些题型？"><el-checkbox-group v-model="form.question_types"><el-checkbox v-for="type in questionTypes" :key="type.value" :value="type.value">{{ type.label }}</el-checkbox></el-checkbox-group></el-form-item>
        <p v-if="!form.question_types?.length" role="alert" class="practice-note">请至少选择一种题型。</p>
        <p class="practice-note">默认混合五种题型，也可以选择想练的题型。优先使用已有题目，不足时会为支持的数学内容编写练习题，并提供参考答案和讲解。编写题不是课本原题；简答题提交后需要自行核对，不计入客观题得分率。范围或题型暂不支持时会提示你。</p>
        <el-button text @click="advanced = !advanced">{{ advanced ? '收起设置' : '更多设置（可不改）' }}</el-button>
        <div v-if="advanced">
          <el-form-item label="练习方式"><el-radio-group v-model="form.mode"><el-radio value="adaptive">多练不熟的内容</el-radio><el-radio value="random">随机练习</el-radio></el-radio-group></el-form-item>
          <el-form-item label="练习时间（分钟）"><el-input-number v-model="form.duration_minutes" :min="1" :max="180" /></el-form-item>
        </div>
        <el-button class="start-button" type="primary" size="large" :disabled="!canGenerate" :loading="loading" native-type="submit">{{ loading ? '正在准备题目…' : '开始练习' }}</el-button>
        <el-button text @click="router.push(`/textbooks/${form.textbook_id}`)">先读课本</el-button>
      </el-form>
    </section>
  </div>
</template>
<style scoped>
.practice-card{max-width:720px;padding:28px}.practice-card .el-alert{margin-bottom:20px}.practice-note{font-size:13px;color:#747d93;line-height:1.8}.start-button{display:block;width:100%;margin:20px 0 12px}.el-form{margin-top:12px}
</style>
