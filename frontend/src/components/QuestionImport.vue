<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { questionApi, type Textbook } from '../api'
import { getApiErrorMessage } from '../api/http'
import { exampleQuestions, parseQuestions } from '../utils/questionText'
import QuestionTypeTag from './QuestionTypeTag.vue'
defineProps<{ books: Textbook[] }>()
const emit = defineEmits<{ imported: [id: number] }>()
const visible = ref(false)
const text = ref('')
const target = ref<string | number>()
const busy = ref(false)
const reading = ref(false)
const error = ref('')
const preview = computed(() => {
  try { return { rows: parseQuestions(text.value), error: '' } }
  catch (e) { return { rows: [], error: (e as Error).message } }
})
async function choose(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  error.value = ''
  reading.value = true
  try {
    if (!file.name.toLowerCase().endsWith('.txt')) throw new Error('请选择 .txt 文件，或直接粘贴题目。')
    if (file.size > 2 * 1024 * 1024) throw new Error('文件超过 2 MB，请分批导入。')
    const content = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer())
    text.value = content
    if (!content.trim()) throw new Error('这个文件里没有题目。')
  } catch (e) { text.value = ''; error.value = e instanceof TypeError ? '请将文件另存为 UTF-8 编码，或复制粘贴题目。' : (e as Error).message }
  finally { reading.value = false }
}
async function save() {
  if (busy.value || reading.value || !preview.value.rows.length) return
  busy.value = true
  error.value = ''
  try {
    const result = await questionApi.importFile(preview.value.rows, target.value)
    ElMessage.success('已导入 ' + result.imported + ' 道题' + (result.skipped ? '，跳过 ' + result.skipped + ' 道重复题' : ''))
    text.value = ''
    visible.value = false
    emit('imported', result.textbook_id)
  } catch (e) { error.value = getApiErrorMessage(e) }
  finally { busy.value = false }
}
</script>
<template>
  <el-button type="primary" @click="visible = true; error = ''">导入题目</el-button>
  <el-dialog v-model="visible" title="导入题目" width="min(650px, 94vw)" :close-on-click-modal="false" :show-close="!busy && !reading" :close-on-press-escape="!busy && !reading">
    <el-form label-position="top">
      <el-form-item label="保存到"><el-select v-model="target" clearable placeholder="独立题库（无需教材）"><el-option v-for="book in books.filter(b => b.parse_status !== 'standalone_question_bank')" :key="book.id" :value="book.id" :label="book.title" /></el-select></el-form-item>
      <el-form-item label="选择 TXT 文件，或在下方粘贴题目"><input type="file" accept=".txt,text/plain" :disabled="busy || reading" @change="choose" /></el-form-item>
      <p>每道题以【单选题】【多选题】【判断题】【填空题】或【简答题】开头，答案另起一行。<el-button link type="primary" :disabled="!!text || busy || reading" @click="text = exampleQuestions">填入示例</el-button></p>
      <el-input v-model="text" type="textarea" :rows="7" :placeholder="exampleQuestions" :disabled="busy || reading" @input="error = ''" />
      <p v-if="preview.error || error" role="alert">{{ error || preview.error }}</p>
      <section v-if="preview.rows.length" aria-label="题目预览"><p>共 {{ preview.rows.length }} 道题，预览前 {{ Math.min(3, preview.rows.length) }} 道</p><div v-for="(row, i) in preview.rows.slice(0, 3)" :key="i"><QuestionTypeTag :type="row.type" /> {{ row.stem }} · 答案 {{ typeof row.answer === 'boolean' ? (row.answer ? '对' : '错') : Array.isArray(row.answer) ? row.answer.join('、') : row.answer }}</div></section>
    </el-form>
    <template #footer><el-button :disabled="busy || reading" @click="visible = false">取消</el-button><el-button type="primary" :loading="busy" :disabled="reading || !preview.rows.length" @click="save">确认导入</el-button></template>
  </el-dialog>
</template>
<style scoped>
p { line-height: 1.7; } [role=alert] { color: #a53225; } section { margin-top: 12px; } section div { margin: 6px 0; overflow-wrap: anywhere; }
</style>
