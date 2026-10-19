<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '../components/PageHeader.vue'
import StatePanel from '../components/StatePanel.vue'
import MathContent from '../components/MathContent.vue'
import QuestionTypeTag from '../components/QuestionTypeTag.vue'
import { learningApi, type AnswerEvidence, type KnowledgePointDetail } from '../api'
import { getApiErrorMessage } from '../api/http'
import { toPercent } from '../utils/learning'

const route = useRoute()
const router = useRouter()
const point = ref<KnowledgePointDetail | null>(null)
const loading = ref(true)
const error = ref('')
let request = 0

async function load() {
  const current = ++request
  loading.value = true
  error.value = ''
  point.value = null
  try {
    const result = await learningApi.knowledgePointDetail(String(route.params.id))
    if (current === request) point.value = result
  } catch (cause) {
    if (current === request) error.value = getApiErrorMessage(cause)
  } finally {
    if (current === request) loading.value = false
  }
}

function answerText(value: unknown): string {
  if (value == null || value === '' || (Array.isArray(value) && !value.length)) return '未作答'
  if (typeof value === 'boolean') return value ? '正确' : '错误'
  return Array.isArray(value) ? value.map(String).join('、') : String(value)
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
    <PageHeader :title="point?.name || '知识点详情'" description="结合原书与作答记录，决定下一步如何巩固。"><template #actions><el-button @click="router.push('/learning')">返回学习进度</el-button></template></PageHeader>
    <section v-if="loading" class="surface-card detail-state" aria-busy="true"><el-skeleton :rows="6" animated /><p>正在读取知识点详情…</p></section>
    <StatePanel v-else-if="error" title="无法打开这个知识点" :description="error"><el-button type="primary" @click="load">重试</el-button></StatePanel>
    <template v-else-if="point">
      <section class="surface-card overview-card">
        <div class="mastery-score"><strong>{{ point.mastery == null ? '尚未练习' : `${toPercent(point.mastery)}%` }}</strong><span>当前掌握度</span></div>
        <div class="overview-copy"><MathContent :text="point.description || '暂时没有知识点说明，可回到原书阅读。'" /><p>已作答 {{ point.attempts }} 次 · 客观题答对 {{ point.correct_count }} 次</p><p v-if="point.updated_at">最近更新：{{ new Date(point.updated_at).toLocaleString('zh-CN') }}</p></div>
      </section>
      <section class="surface-card detail-section"><div class="section-title"><div><h2>在我的课本中</h2><p>选择一本教材，回到原文或练习对应内容。</p></div></div>
        <div v-if="point.mappings?.length" class="mapping-list"><article v-for="mapping in point.mappings" :key="`${mapping.textbook_id}-${mapping.local_knowledge_point_id}`"><div><h3>{{ mapping.textbook_title }}</h3><p>{{ mapping.chapter_title }}<span v-if="mapping.page_start != null"> · 第 {{ mapping.page_start }} 页</span></p></div><div class="mapping-actions"><el-button @click="router.push({ path: `/textbooks/${mapping.textbook_id}`, query: { chapter: mapping.chapter_id } })">回到课本</el-button><el-button type="primary" plain @click="router.push({ path: '/exam/generate', query: { textbook: mapping.textbook_id, knowledgePoint: mapping.local_knowledge_point_id } })">练习这个知识点</el-button></div></article></div>
        <StatePanel v-else compact title="暂未关联课本" description="当前没有可阅读或练习的教材来源。" />
      </section>
      <section class="surface-card detail-section"><div class="section-title"><div><h2>最近作答证据</h2><p>查看参考答案与解析，逐次巩固理解。</p></div></div>
        <div v-if="point.recent_answers?.length" class="evidence-list"><article v-for="(answer, index) in point.recent_answers" :key="`${answer.record_id}-${answer.question_id}-${index}`"><div class="evidence-heading"><QuestionTypeTag :type="answer.question_type" /><el-tag :type="answer.is_correct === null ? 'warning' : answer.is_correct ? 'success' : 'danger'">{{ answer.is_correct === null ? '自行检查' : answer.is_correct ? '正确' : '错误' }}</el-tag><small>{{ new Date(answer.submitted_at).toLocaleString('zh-CN') }}</small></div><h3><MathContent :text="answer.stem" /></h3>
          <ul v-if="optionsOf(answer.options).length" class="options"><li v-for="option in optionsOf(answer.options)" :key="option.key"><b>{{ option.key }}.</b> <MathContent :text="option.text" /></li></ul>
          <div class="answers"><section><h4>我的答案</h4><MathContent :text="answerText(answer.user_answer)" /></section><section><h4>参考答案</h4><MathContent :text="answer.correct_answer == null ? '暂无参考答案' : answerText(answer.correct_answer)" /></section></div><section class="explanation"><h4>解析</h4><MathContent :text="answer.explanation || '暂无解析'" /></section><el-button link type="primary" @click="router.push(`/results/${answer.record_id}`)">查看这次练习详情</el-button></article></div>
        <StatePanel v-else compact title="还没有作答证据" description="从上方选择教材练习，完成后这里会记录你的表现。" />
      </section>
    </template>
    <StatePanel v-else title="没有找到知识点" description="该知识点可能已不可用。"><el-button @click="router.push('/learning')">返回学习进度</el-button></StatePanel>
  </div>
</template>

<style scoped>
.options{list-style:none;display:grid;gap:10px;margin:0 0 20px;padding:0;font-size:14px}
.detail-state,.overview-card,.detail-section{padding:24px}.detail-state p{color:#7d879b;font-size:12px}.overview-card{display:flex;gap:32px;align-items:center;margin-bottom:20px}.mastery-score{display:flex;flex-direction:column;gap:8px;min-width:120px}.mastery-score strong{font-size:30px;color:#5864dc}.mastery-score span,.overview-copy p{color:#7d879b;font-size:12px}.overview-copy{line-height:1.8}.overview-copy p{margin:8px 0 0}.detail-section{margin-bottom:20px}.mapping-list article{display:flex;justify-content:space-between;align-items:center;gap:20px;padding:18px 0;border-top:1px solid #edf0f5}.mapping-list h3{font-size:15px;margin:0 0 8px}.mapping-list p{font-size:12px;margin:0;color:#7d879b}.mapping-actions{display:flex;flex-wrap:wrap;gap:10px}.mapping-actions .el-button{margin:0}.evidence-list>article{border-top:1px solid #edf0f5;padding:20px 0}.evidence-heading{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.evidence-heading small{color:#7d879b}.evidence-list h3{font-size:15px;line-height:1.8}.answers{display:grid;grid-template-columns:1fr 1fr;gap:14px}.answers>section{padding:14px;background:#f7f8fc;border-radius:10px;min-width:0}.answers h4,.explanation h4{color:#7d879b;font-size:12px;margin:0 0 10px}.explanation{margin:18px 0;line-height:1.8}@media(max-width:700px){.overview-card,.mapping-list article{align-items:flex-start;flex-direction:column;gap:16px}.answers{grid-template-columns:1fr}}
</style>
