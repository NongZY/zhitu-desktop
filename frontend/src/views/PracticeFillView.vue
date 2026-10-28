<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '../components/PageHeader.vue'
import CandidateEditor from '../components/CandidateEditor.vue'
import QuestionTypeTag from '../components/QuestionTypeTag.vue'
import MathContent from '../components/MathContent.vue'
import { textbookApi, type Textbook, type Chapter, type QuestionType } from '../api'
import { practiceApi, type CandidateQuestion, type Coverage, type PracticeJob, type JobSummary } from '../api/practice'
import { desktopSettings, type AISettings } from '../api/desktopSettings'
import { documentLink } from '../api/documents'
import { getApiErrorMessage } from '../api/http'

const route = useRoute(), router = useRouter()
const books = ref<Textbook[]>([]), bookId = ref<string | number>(), chapterId = ref<number>()
const chapters = ref<Chapter[]>([]), coverage = ref<Coverage | null>(null), history = ref<JobSummary[]>([])
const ai = ref<AISettings | null>(null), mode = ref('rules'), count = ref(5), consent = ref(false)
const loading = ref(true), busy = ref(false), error = ref(''), notice = ref('')
const job = ref<PracticeJob | null>(null), selected = ref<string[]>([]), drafts = reactive<Record<string, CandidateQuestion>>({})
const types: { value: QuestionType; label: string }[] = [{ value: 'single_choice', label: '单选' }, { value: 'multiple_choice', label: '多选' }, { value: 'true_false', label: '判断' }, { value: 'fill_blank', label: '填空' }, { value: 'short_answer', label: '简答' }]
const kinds = ref<QuestionType[]>(types.map(t => t.value))
const running = computed(() => job.value && ['queued', 'running'].includes(job.value.status))
const canStart = computed(() => !busy.value && !loading.value && !running.value && !!coverage.value?.rendition_revision && !!kinds.value.length
  && (mode.value !== 'ai' || (consent.value && ai.value?.practice_enabled && ai.value?.key_configured)))
const canRetry = computed(() => !!job.value && !job.value.source_changed && !running.value && !busy.value && !['completed', 'obsolete'].includes(job.value.status)
  && (job.value.parameters.mode !== 'ai' || (consent.value && ai.value?.practice_enabled && ai.value?.key_configured)))
const methodLabel: Record<string, string> = { textbook_rules: '本地配套题（非课本原题）', textbook_original: '教材原题', textbook_ai: 'AI 配套题（请核对）' }
const statusLabel: Record<string, string> = { queued: '等待中', running: '正在补充', completed: '已完成', partial: '部分完成', failed: '未完成', cancelled: '已停止', interrupted: '上次已中断', obsolete: '来源已更新' }
let timer: ReturnType<typeof setTimeout> | undefined, generation = 0, disposed = false
let attempt: { signature: string; id: string } | null = null
const flatChapters = computed(() => {
  const walk = (nodes: Chapter[], depth = 0): { id: number; title: string }[] => nodes.flatMap(n => [{ id: Number(n.id), title: '　'.repeat(depth) + n.title }, ...walk(n.children || [], depth + 1)])
  return walk(chapters.value)
})
function acceptJob(value: PracticeJob) {
  job.value = value
  for (const row of value.candidates) if (!drafts[row.id]) drafts[row.id] = JSON.parse(JSON.stringify(row.question))
  selected.value = selected.value.filter(id => value.candidates.some(c => c.id === id && !c.saved_question_id))
  clearTimeout(timer)
  if (['queued', 'running'].includes(value.status)) timer = setTimeout(() => void refresh(), 1500)
}
async function refresh(id = job.value?.id) {
  if (!id) return
  const current = generation
  try { const result = await practiceApi.read(id); if (!disposed && current === generation) acceptJob(result) }
  catch (err) { if (!disposed && current === generation) error.value = getApiErrorMessage(err) }
}
async function loadScope(includeChapters = false) {
  const current = ++generation
  clearTimeout(timer); consent.value = false; coverage.value = null; job.value = null; selected.value = []; error.value = ''; notice.value = ''
  if (!bookId.value) { loading.value = false; return }
  loading.value = true
  try {
    const id = bookId.value
    if (includeChapters) {
      const structure = await textbookApi.getStructure(id)
      if (current !== generation || disposed) return
      chapters.value = structure.chapters
    }
    const [result, jobs] = await Promise.all([practiceApi.coverage(id, chapterId.value), practiceApi.jobs(id)])
    if (current !== generation || disposed) return
    coverage.value = result; history.value = jobs
    if (jobs[0]) await refresh(jobs[0].id)
  } catch (err) { if (current === generation) error.value = getApiErrorMessage(err) }
  finally { if (current === generation) loading.value = false }
}
async function perform(action: () => Promise<void>) {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try { await action() } catch (err) { error.value = getApiErrorMessage(err) }
  finally { busy.value = false }
}
async function start() {
  if (!canStart.value || !bookId.value) return
  await perform(async () => {
    const payload = { chapter_id: chapterId.value ?? null, mode: mode.value, count: count.value, question_types: kinds.value, external_consent: mode.value === 'ai' && consent.value }
    const signature = JSON.stringify([bookId.value, payload])
    if (!attempt || attempt.signature !== signature) attempt = { signature, id: crypto.randomUUID() }
    const result = await practiceApi.start(bookId.value!, { ...payload, request_id: attempt.id })
    attempt = null
    acceptJob(result); history.value = await practiceApi.jobs(bookId.value!)
  })
}
async function stop() { if (job.value) await perform(async () => acceptJob(await practiceApi.cancel(job.value!.id))) }
async function retry() { if (canRetry.value) await perform(async () => acceptJob(await practiceApi.retry(job.value!.id, consent.value))) }
async function confirm() {
  if (!job.value || job.value.source_changed || !selected.value.length || running.value) return
  await perform(async () => {
    const ids = [...selected.value], active = job.value!
    for (const id of ids) await practiceApi.edit(id, drafts[id])
    await practiceApi.confirm(active.id, ids)
    selected.value = []; notice.value = '已加入我的题库，可以开始练习了。'
    await refresh(active.id)
    coverage.value = await practiceApi.coverage(bookId.value!, chapterId.value)
  })
}
function bookChanged() { chapterId.value = undefined; void loadScope(true) }
watch(mode, () => { consent.value = false; if (mode.value === 'extract') kinds.value = ['short_answer']; else kinds.value = types.map(t => t.value) })
watch([chapterId, count, () => kinds.value.join(',')], () => { consent.value = false })
onMounted(async () => {
  try {
    books.value = (await textbookApi.list()).items.filter(b => ['ready', 'review'].includes(b.status))
    bookId.value = books.value.find(b => String(b.id) === route.query.textbook)?.id || books.value[0]?.id
    if (route.query.chapter) chapterId.value = Number(route.query.chapter)
    try { ai.value = await desktopSettings.readAI() } catch { ai.value = null }
    if (!disposed) await loadScope(true)
  } catch (err) { error.value = getApiErrorMessage(err); loading.value = false }
})
onUnmounted(() => { disposed = true; generation++; clearTimeout(timer) })
</script>

<template>
  <div class="fill-page">
    <PageHeader title="给教材补充练习" description="先看教材内容，再补充题目。核对答案后，才加入你的题库。" />
    <p v-if="error" role="alert" class="notice warning">{{ error }} <button :disabled="busy" @click="loadScope(true)">重新加载</button></p>
    <p v-if="notice" role="status" class="notice">{{ notice }}</p>
    <section class="surface-card fill-card">
      <div class="scope"><label>课本<select v-model="bookId" :disabled="busy || loading" @change="bookChanged"><option v-for="book in books" :key="book.id" :value="book.id">{{ book.title }}</option></select></label><label>章节<select v-model="chapterId" :disabled="busy || loading" @change="loadScope()"><option :value="undefined">整本课本</option><option v-for="chapter in flatChapters" :key="chapter.id" :value="chapter.id">{{ chapter.title }}</option></select></label></div>
      <p v-if="loading" role="status">正在读取教材内容…</p>
      <p v-else-if="!books.length">先导入一本课本，整理完成后就能补充练习。<button @click="router.push('/textbooks')">去导入课本</button></p>
      <template v-if="coverage">
        <p>所选内容已有 {{ coverage.ready_questions }} 道可练习的题。</p>
        <label>补题方式<select data-test="fill-mode" v-model="mode" :disabled="busy || !!running"><option value="rules">本地配套练习（无需联网，支持部分数学内容）</option><option value="ai">AI 配套练习（需要已配置的接口）</option><option value="extract">教材原题（需要原文中明确给出题目和答案）</option></select></label>
        <p v-if="mode === 'rules'">本地方法目前覆盖绝对值、相反数等有限数学内容。没有匹配的正文会说明原因，不会凭章节名称编题。</p>
        <p v-if="mode === 'extract'">目前只整理明确标注“题目：”“答案：”的简答题。未找到答案的内容不会猜测，也不会冒充原题。</p>
        <label>每章最多补几道？<input v-model.number="count" type="number" min="1" max="20" :disabled="busy || !!running"></label>
        <div class="checks"><label v-for="type in types" :key="type.value"><input v-model="kinds" type="checkbox" :value="type.value" :disabled="busy || !!running || mode === 'extract'">{{ type.label }}</label></div>
        <details class="source-preview" open><summary>查看本次使用的教材片段（{{ coverage.chapters.length }} 个章节范围）</summary><article v-for="chapter in coverage.chapters" :key="String(chapter.chapter_id)"><h3>{{ chapter.title }}</h3><p>已选 {{ chapter.selected_blocks }} 段 / 共 {{ chapter.body_blocks }} 段正文<span v-if="mode === 'rules'"> · 本地支持：{{ chapter.supported_topics.join('、') || '暂无匹配内容' }}</span></p><blockquote v-for="excerpt in chapter.excerpts" :key="excerpt.id"><MathContent :text="excerpt.text" /><button @click="router.push(documentLink(bookId!, excerpt.locator))">查看原文</button></blockquote></article></details>
        <div v-if="mode === 'ai' || job?.parameters.mode === 'ai'" class="ai-consent"><p>服务：{{ ai?.base_url || '尚未设置' }} · 模型：{{ ai?.model || '尚未设置' }}</p><p>开始新任务会发送上面预览的正文片段，预计最多 {{ coverage.estimated_requests }} 次请求，每章最多 12 段、6000 字。不是整章全文，也不包含学习记录。AI 可能出错，费用由服务商计算。</p><p v-if="!ai?.practice_enabled || !ai?.key_configured">请先在设置中开启 AI 补题并填写接口。<button @click="router.push('/settings')">打开设置</button></p><label class="check"><input data-test="fill-consent" v-model="consent" type="checkbox">同意按所选范围发送内容并承担可能的费用；重试使用原任务范围，不会自动重试。</label></div>
        <button data-test="start-fill" class="primary" :disabled="!canStart" @click="start">生成候选题</button>
      </template>
    </section>
    <section v-if="history.length" class="surface-card fill-card"><label>查看补题记录<select :value="job?.id" :disabled="busy || !!running" @change="refresh(($event.target as HTMLSelectElement).value)"><option v-for="item in history" :key="item.id" :value="item.id">{{ statusLabel[item.status] || item.status }} {{ item.created_at ? new Date(item.created_at).toLocaleString('zh-CN') : '' }}</option></select></label></section>
    <section v-if="job" class="surface-card fill-card">
      <h2>{{ statusLabel[job.status] || job.status }} · {{ job.candidates.length }} 道候选题</h2><p>{{ job.message }}</p>
      <p v-if="job.source_changed" role="alert" class="notice warning">教材或章节已更新，下面的旧候选仅供查看，请重新补题。</p>
      <ul><li v-for="(unit, index) in job.units" :key="index">{{ unit.title }}：{{ statusLabel[unit.status] || unit.status }} {{ unit.message }}</li></ul>
      <details v-if="job.parameters.mode === 'ai' && !running"><summary>重试时将使用这次任务保存的原文范围</summary><section v-for="(unit, index) in job.units.filter(u => u.status !== 'completed')" :key="index"><h3>{{ unit.title }}</h3><blockquote v-for="entry in unit.evidence" :key="entry.id"><MathContent :text="entry.text" /></blockquote></section></details>
      <div class="actions"><button v-if="running" :disabled="busy" @click="stop">停止补题</button><button :disabled="busy" @click="refresh()">刷新进度</button><button v-if="!running && !['completed','obsolete'].includes(job.status)" :disabled="!canRetry" @click="retry">重试未完成部分</button></div>
      <article v-for="(row, index) in job.candidates" :key="row.id" class="candidate">
        <div class="candidate-title"><label class="check"><input data-test="select-candidate" v-model="selected" type="checkbox" :value="row.id" :disabled="busy || !!running || job.source_changed || !!row.saved_question_id">第 {{ index + 1 }} 题 {{ row.saved_question_id ? '（已保存）' : '' }}</label><QuestionTypeTag :type="row.question.question_type" /></div>
        <p>{{ methodLabel[row.method] || '教材配套题' }}<span v-if="row.provenance.model"> · {{ row.provenance.model }}</span></p>
        <MathContent :text="drafts[row.id]?.stem || row.question.stem" />
        <CandidateEditor v-if="drafts[row.id]" v-model="drafts[row.id]" :disabled="busy || !!running || job.source_changed || !!row.saved_question_id" />
        <details><summary>核对教材来源</summary><blockquote v-for="entry in row.evidence" :key="entry.id"><MathContent :text="entry.text" /><button @click="router.push(documentLink(job!.textbook_id, entry.locator))">查看原文</button></blockquote></details>
      </article>
      <div class="actions"><button data-test="confirm-candidates" class="primary" :disabled="busy || !!running || job.source_changed || !selected.length" @click="confirm">确认选中题目，加入题库</button><button @click="router.push({ path: '/exam/generate', query: { textbook: String(bookId), chapter: chapterId ? String(chapterId) : undefined } })">去做练习</button></div>
      <p>保存时会同时保存你对选中题目的修改。简答题需要自己核对答案，不自动判定对错。</p>
    </section>
  </div>
</template>

<style scoped>
.fill-page{max-width:1080px}.fill-card{padding:24px;margin-bottom:20px}.fill-card h2{font-size:19px;margin-top:0}.fill-card h3{font-size:16px}.fill-card p,.fill-card li{font-size:14px;line-height:1.8;color:#68748a}label{display:grid;gap:7px;margin:14px 0;font-size:14px}select,input[type=number]{padding:10px;border:1px solid #cfd5e1;border-radius:8px;background:#fff;color:#27344b;font:inherit;max-width:100%}.scope{display:grid;grid-template-columns:1fr 1fr;gap:16px}.checks,.actions,.candidate-title{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.checks label,.check{display:flex;gap:8px;align-items:flex-start;line-height:1.8}.check input,.checks input{margin-top:6px}button{padding:9px 14px;border:1px solid #ccd4e2;border-radius:8px;background:#fff;cursor:pointer;font:inherit;font-size:14px;color:#33405a}button.primary{background:#515fca;color:white;border-color:#515fca}button:disabled{opacity:.5;cursor:not-allowed}.source-preview{margin:20px 0;max-height:420px;overflow:auto;padding:16px;background:#f7f8fc;border-radius:10px}summary{cursor:pointer;line-height:1.8;font-size:14px}blockquote{margin:12px 0;padding:12px 14px;border-left:3px solid #c8cfee;background:#f4f6fb;white-space:pre-wrap;line-height:1.8;font-size:14px}blockquote button{display:block;margin-top:10px}.ai-consent,.notice{padding:16px;margin:15px 0;background:#eef3ff;border-radius:10px}.warning{background:#fff3df;color:#80571f}.candidate{padding:20px 0;border-top:1px solid #e0e5ef;margin-top:20px}.actions{margin-top:20px}button:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid #515fca;outline-offset:3px}@media(max-width:700px){.scope{grid-template-columns:1fr}.fill-card{padding:16px}}
</style>
