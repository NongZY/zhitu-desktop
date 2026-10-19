<script setup lang="ts">
import MathContent from '../components/MathContent.vue'
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { CirclePlus, Delete, Edit, Search, Tickets } from '@element-plus/icons-vue'
import PageHeader from '../components/PageHeader.vue'
import QuestionTypeTag from '../components/QuestionTypeTag.vue'
import StatePanel from '../components/StatePanel.vue'
import { questionApi, textbookApi, type Question, type QuestionPayload, type QuestionType, type Textbook } from '../api'
import { getApiErrorMessage } from '../api/http'

const loading = ref(false)
const saving = ref(false)
const error = ref('')
const items = ref<Question[]>([])
const total = ref(0)
const books = ref<Textbook[]>([])
const dialogVisible = ref(false)
const editingId = ref<string | number>()
const formRef = ref<FormInstance>()
const filters = reactive({ keyword: '', textbook_id: undefined as string | number | undefined, type: '' as QuestionType | '', difficulty: '' as number | '' })
const form = reactive({
  stem: '',
  type: 'single_choice' as QuestionType,
  textbook_id: undefined as string | number | undefined,
  chapter_id: undefined as string | number | undefined,
  knowledge_point_id: undefined as string | number | undefined,
  difficulty: 3,
  status: 'approved' as 'draft' | 'pending' | 'approved' | 'rejected',
  optionsText: 'A. \nB. \nC. \nD. ',
  answerText: '',
  analysis: '',
})
const rules: FormRules = {
  stem: [{ required: true, message: '请输入题干', trigger: 'blur' }],
  textbook_id: [{ required: true, message: '请选择教材', trigger: 'change' }],
  answerText: [{ required: true, message: '请输入标准答案', trigger: 'blur' }],
}

const typeOptions: Array<{ value: QuestionType; label: string }> = [
  { value: 'single_choice', label: '单选题' },
  { value: 'multiple_choice', label: '多选题' },
  { value: 'fill_blank', label: '填空题' },
  { value: 'true_false', label: '判断题' },
  { value: 'short_answer', label: '简答题' },
]
const statusLabel: Record<string, string> = { draft: '草稿', pending: '待确认', approved: '可练习', rejected: '已停用' }

async function load() {
  loading.value = true
  error.value = ''
  try {
    const result = await questionApi.list({ ...filters, page_size: 100 })
    items.value = result.items
    total.value = result.total
  } catch (err) {
    error.value = getApiErrorMessage(err)
  } finally {
    loading.value = false
  }
}

function resetForm() {
  editingId.value = undefined
  Object.assign(form, { stem: '', type: 'single_choice', textbook_id: books.value[0]?.id, chapter_id: undefined, knowledge_point_id: undefined, difficulty: 3, status: 'approved', optionsText: 'A. \nB. \nC. \nD. ', answerText: '', analysis: '' })
}

function openCreate() {
  resetForm()
  dialogVisible.value = true
}

function openEdit(question: Question) {
  editingId.value = question.id
  const options = Array.isArray(question.options)
    ? question.options.map((item) => typeof item === 'string' ? item : `${item.key}. ${item.text}`).join('\n')
    : question.options && typeof question.options === 'object'
      ? Object.entries(question.options).map(([key, value]) => `${key}. ${value}`).join('\n')
      : ''
  Object.assign(form, {
    stem: question.stem,
    type: question.type,
    textbook_id: question.textbook_id,
    chapter_id: question.chapter_id,
    knowledge_point_id: question.knowledge_point_id,
    difficulty: question.difficulty,
    status: question.status || 'draft',
    optionsText: options,
    answerText: Array.isArray(question.answer) ? question.answer.join(',') : String(question.answer ?? ''),
    analysis: question.analysis || '',
  })
  dialogVisible.value = true
}

function payload(): QuestionPayload {
  const optionLines = form.optionsText.split('\n').map((value) => value.trim()).filter(Boolean)
  let answer: QuestionPayload['answer'] = form.answerText.trim()
  if (form.type === 'multiple_choice') answer = form.answerText.split(',').map((value) => value.trim()).filter(Boolean)
  if (form.type === 'true_false') answer = ['正确', 'true', '对', '1'].includes(form.answerText.trim().toLowerCase())
  return {
    stem: form.stem,
    type: form.type,
    textbook_id: form.textbook_id,
    chapter_id: form.chapter_id,
    knowledge_point_id: form.knowledge_point_id,
    difficulty: form.difficulty,
    status: form.status,
    options: ['single_choice', 'multiple_choice'].includes(form.type) ? optionLines.map((text, index) => ({ key: String.fromCharCode(65 + index), text })) : undefined,
    answer,
    analysis: form.analysis,
  }
}

async function save() {
  if (!formRef.value || !(await formRef.value.validate().catch(() => false))) return
  saving.value = true
  try {
    if (editingId.value) await questionApi.update(editingId.value, payload())
    else await questionApi.create(payload())
    ElMessage.success(editingId.value ? '题目已更新' : '题目已加入我的题库')
    dialogVisible.value = false
    await load()
  } catch (err) {
    ElMessage.error(getApiErrorMessage(err, '保存题目失败'))
  } finally {
    saving.value = false
  }
}

async function remove(question: Question) {
  try {
    await ElMessageBox.confirm('删除后无法恢复，确定继续吗？', '删除题目', { type: 'warning' })
  } catch { return }
  try {
    await questionApi.remove(question.id)
    ElMessage.success('题目已删除')
    await load()
  } catch (err) {
    ElMessage.error(getApiErrorMessage(err, '删除失败'))
  }
}

onMounted(async () => {
  const [bookResult] = await Promise.allSettled([textbookApi.list()])
  if (bookResult.status === 'fulfilled') books.value = bookResult.value.items
  await load()
})
</script>

<template>
  <div>
    <PageHeader eyebrow="My Question Bank" title="我的题库" description="整理教材习题与自己添加的题目，随时编辑并决定哪些题用于练习。">
      <template #actions><el-button type="primary" :icon="CirclePlus" @click="openCreate">添加题目</el-button></template>
    </PageHeader>
    <section class="surface-card filter-bar">
      <el-input v-model="filters.keyword" class="search-input" clearable placeholder="搜索题干" :prefix-icon="Search" @keyup.enter="load" @clear="load" />
      <el-select v-model="filters.textbook_id" clearable placeholder="全部教材" @change="load"><el-option v-for="book in books" :key="book.id" :label="book.title" :value="book.id" /></el-select>
      <el-select v-model="filters.type" clearable placeholder="全部题型" @change="load"><el-option v-for="item in typeOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select>
      <el-select v-model="filters.difficulty" clearable placeholder="全部难度" @change="load"><el-option v-for="level in 5" :key="level" :label="`${level} 星`" :value="level" /></el-select>
      <el-button @click="load">查询</el-button><span class="filter-spacer"></span><span class="soft-label">共 {{ total }} 道题</span>
    </section>
    <el-alert v-if="error" class="error-banner" type="warning" :closable="false" show-icon title="题库暂不可用" :description="error" />
    <section v-loading="loading" class="surface-card list-card question-list">
      <el-table v-if="items.length" :data="items" row-key="id">
        <el-table-column label="题目" min-width="360"><template #default="{ row }"><div class="stem"><QuestionTypeTag :type="row.type" /><span><MathContent :text="row.stem" /></span></div></template></el-table-column>
        <el-table-column label="难度" width="130"><template #default="{ row }"><el-rate :model-value="row.difficulty" disabled /></template></el-table-column>
        <el-table-column label="来源" prop="source" width="100" />
        <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.status === 'approved' ? 'success' : row.status === 'rejected' ? 'danger' : 'warning'" effect="light">{{ statusLabel[row.status] || row.status || '草稿' }}</el-tag></template></el-table-column>
        <el-table-column label="操作" width="110" align="right"><template #default="{ row }"><el-button link :icon="Edit" @click="openEdit(row)" /><el-button link type="danger" :icon="Delete" @click="remove(row)" /></template></el-table-column>
      </el-table>
      <StatePanel v-else :icon="Tickets" title="没有匹配的题目" description="调整筛选条件，或添加第一道属于你的练习题。" />
    </section>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑题目' : '录入题目'" width="min(680px, 94vw)" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item label="教材" prop="textbook_id"><el-select v-model="form.textbook_id" style="width:100%"><el-option v-for="book in books" :key="book.id" :label="book.title" :value="book.id" /></el-select></el-form-item>
        <div class="form-grid"><el-form-item label="题型"><el-select v-model="form.type"><el-option v-for="item in typeOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item><el-form-item label="使用状态"><el-select v-model="form.status"><el-option label="暂存草稿" value="draft" /><el-option label="等待确认" value="pending" /><el-option label="可用于练习" value="approved" /><el-option label="暂不使用" value="rejected" /></el-select></el-form-item></div>
        <el-form-item label="难度"><el-rate v-model="form.difficulty" /></el-form-item>
        <el-form-item label="题干" prop="stem"><el-input v-model="form.stem" type="textarea" :rows="3" placeholder="请输入题目内容" /></el-form-item>
        <el-form-item v-if="['single_choice','multiple_choice'].includes(form.type)" label="选项（每行一个）"><el-input v-model="form.optionsText" type="textarea" :rows="4" /></el-form-item>
        <el-form-item :label="form.type === 'true_false' ? '标准答案（正确/错误）' : '标准答案'" prop="answerText"><el-input v-model="form.answerText" placeholder="多选题用英文逗号分隔" /></el-form-item>
        <el-form-item label="解析"><el-input v-model="form.analysis" type="textarea" :rows="3" placeholder="说明解题思路与易错点" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存题目</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.question-list{min-height:300px}.stem{display:flex;align-items:flex-start;gap:10px;line-height:1.7}.stem span{font-size:12px;color:#38425e}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.el-rate{--el-rate-icon-size:15px}@media(max-width:620px){.form-grid{grid-template-columns:1fr;gap:0}}
</style>
