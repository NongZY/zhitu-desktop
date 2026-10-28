<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '../components/PageHeader.vue'
import StatePanel from '../components/StatePanel.vue'
import MathContent from '../components/MathContent.vue'
import QuestionTypeTag from '../components/QuestionTypeTag.vue'
import { learningApi, type AnswerEvidence, type ExamRecordDetail } from '../api'
import { getApiErrorMessage } from '../api/http'
import { formatDuration } from '../utils/learning'

const route = useRoute()
const router = useRouter()
const record = ref<ExamRecordDetail | null>(null)
const loading = ref(true)
const error = ref('')
let request = 0
const gradedTotal = computed(() => record.value?.graded_total_score ?? record.value?.total_score ?? 0)
const scoreRate = computed(() => gradedTotal.value > 0 ? Math.round((record.value?.score || 0) / gradedTotal.value * 100) : null)

async function load() {
  const current = ++request
  loading.value = true
  error.value = ''
  record.value = null
  try {
    const result = await learningApi.examDetail(String(route.params.id))
    if (current === request) record.value = result
  } catch (cause) {
    if (current === request) error.value = getApiErrorMessage(cause)
  } finally {
    if (current === request) loading.value = false
  }
}

function answerText(value: unknown, type: AnswerEvidence['question_type']): string {
  if (value == null || value === '' || (Array.isArray(value) && !value.length)) return '未作答'
  if (typeof value === 'boolean') return value ? '正确' : '错误'
  if (Array.isArray(value)) return value.map((answer, index) => type === 'fill_blank' ? `第 ${index + 1} 空：${String(answer ?? '')}` : String(answer)).join(type === 'fill_blank' ? '\n' : '、')
  return String(value)
}

function optionsOf(options: AnswerEvidence['options']) {
  if (!options) return []
  if (Array.isArray(options)) return options.map((option, index) => typeof option === 'string' ? { key: String.fromCharCode(65 + index), text: option } : option)
  return Object.entries(options).map(([key, text]) => ({ key, text }))
}

watch(() => route.params.id, load, { immediate: true })
onUnmounted(() => { request++ })
</script>

<template>
  <div>
    <PageHeader :title="record?.title || '练习详情'" description="回顾每道题的作答、参考答案与解析。">
      <template #actions><el-button @click="router.push('/results')">返回学习记录</el-button></template>
    </PageHeader>
    <section v-if="loading" class="surface-card detail-state" aria-busy="true"><el-skeleton :rows="7" animated /><p>正在读取练习详情…</p></section>
    <StatePanel v-else-if="error" title="无法打开这次练习" :description="error"><el-button type="primary" @click="load">重试</el-button></StatePanel>
    <template v-else-if="record">
      <section class="surface-card summary-card">
        <div><span>客观题得分</span><strong v-if="scoreRate !== null">{{ record.score }} / {{ gradedTotal }} <small>（{{ scoreRate }}%）</small></strong><strong v-else>本次无客观题</strong></div>
        <div><span>作答情况</span><strong>{{ record.correct_count }} 题正确 · {{ record.wrong_count }} 题错误</strong><p v-if="record.pending_count">自行检查 {{ record.pending_count }} 题，参照答案和解析核对。</p></div>
        <div><span>{{ record.textbook_title || '练习记录' }}</span><p>{{ new Date(record.submitted_at).toLocaleString('zh-CN') }}</p><p>用时 {{ formatDuration(record.duration_seconds) }}</p></div>
      </section>
      <div v-if="record.details?.length" class="answer-list">
        <article v-for="(item, index) in record.details" :key="item.question_id" class="surface-card answer-card">
          <div class="answer-heading"><span>第 {{ index + 1 }} 题</span><QuestionTypeTag :type="item.question_type" /><el-tag :type="item.is_correct === null ? 'warning' : item.is_correct ? 'success' : 'danger'">{{ item.is_correct === null ? '自行检查' : item.is_correct ? '正确' : '错误' }}</el-tag><span class="question-score">{{ item.is_correct === null ? '未自动评分' : `${item.score} / ${item.max_score} 分` }}</span></div>
          <h2><MathContent :text="item.stem" /></h2>
          <p v-if="item.snapshot_verified === false" role="note">这是一条旧版记录，未保存当时的题目副本。下方题目与答案来自当前题库，原有得分仍保留。</p>
          <ul v-if="optionsOf(item.options).length" class="options"><li v-for="option in optionsOf(item.options)" :key="option.key"><b>{{ option.key }}.</b> <MathContent :text="option.text" /></li></ul>
          <div class="answer-comparison"><section><h3>我的答案</h3><MathContent :text="answerText(item.user_answer, item.question_type)" /></section><section><h3>参考答案</h3><MathContent :text="item.correct_answer == null ? '暂无参考答案' : answerText(item.correct_answer, item.question_type)" /></section></div>
          <section class="explanation"><h3>解析</h3><MathContent :text="item.explanation || '暂无解析'" /></section>
          <div class="question-actions"><el-button v-if="item.global_knowledge_point_id != null" link type="primary" @click="router.push(`/learning/knowledge-points/${item.global_knowledge_point_id}`)">查看知识点：{{ item.knowledge_point_name || '知识点详情' }}</el-button><el-button v-if="item.textbook_id != null && item.chapter_id != null" link type="primary" @click="router.push({ path: `/textbooks/${item.textbook_id}`, query: { chapter: item.chapter_id } })">回到课本</el-button></div>
        </article>
      </div>
      <StatePanel v-else title="这次练习暂无逐题记录" description="已有成绩保留在上方，你可以返回查看其他练习。" />
    </template>
    <StatePanel v-else title="没有找到练习记录" description="这次练习可能已不可用。"><el-button @click="router.push('/results')">返回学习记录</el-button></StatePanel>
  </div>
</template>

<style scoped>
.detail-state{padding:24px}.detail-state p,.summary-card span,.summary-card p{color:#7d879b;font-size:12px}.summary-card{display:grid;grid-template-columns:1fr 1.3fr 1fr;gap:24px;padding:24px;margin-bottom:20px}.summary-card strong{display:block;margin-top:10px;font-size:18px}.summary-card small{font-size:14px}.summary-card p{margin:8px 0 0}.answer-list{display:grid;gap:18px}.answer-card{padding:24px}.answer-heading{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:12px;color:#737d91}.question-score{margin-left:auto}.answer-card h2{font-size:16px;line-height:1.8;margin:18px 0}.answer-card h3{font-size:12px;color:#737d91;margin:0 0 10px}.options{list-style:none;display:grid;gap:10px;margin:0 0 20px;padding:0;font-size:14px}.answer-comparison{display:grid;grid-template-columns:1fr 1fr;gap:14px}.answer-comparison>section{padding:16px;background:#f7f8fc;border-radius:10px;min-width:0;line-height:1.8}.explanation{margin-top:20px;line-height:1.8;font-size:14px}.question-actions{display:flex;flex-wrap:wrap;gap:12px;margin-top:16px}.question-actions .el-button{margin:0}@media(max-width:700px){.summary-card,.answer-comparison{grid-template-columns:1fr}.answer-card{padding:18px}.question-score{margin-left:0}}
</style>
