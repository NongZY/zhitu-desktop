<script setup lang="ts">
import MathContent from '../components/MathContent.vue'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { EChartsOption } from 'echarts'
import { CircleCheck, EditPen, RefreshRight, TrendCharts, Warning } from '@element-plus/icons-vue'
import BaseChart from '../components/BaseChart.vue'
import PageHeader from '../components/PageHeader.vue'
import QuestionTypeTag from '../components/QuestionTypeTag.vue'
import StatePanel from '../components/StatePanel.vue'
import { learningApi, type ExamHistoryItem, type MasteryItem, type WrongQuestion } from '../api'
import { getApiErrorMessage } from '../api/http'
import { formatDuration, toPercent } from '../utils/learning'

const router = useRouter()
const loading = ref(true)
const error = ref('')
const history = ref<ExamHistoryItem[]>([])
const page = ref(1)
const pageSize = 10
const total = ref(0)
const wrong = ref<WrongQuestion[]>([])
const wrongTotal = ref(0)
const mastery = ref<MasteryItem[]>([])
const tab = ref<'records' | 'wrong'>('records')

const gradedTotal = (item: ExamHistoryItem) => item.graded_total_score ?? item.total_score
const scoreRate = (item: ExamHistoryItem) => Math.round(item.score / gradedTotal(item) * 100)
const average = computed(() => {
  const graded = history.value.filter((item) => gradedTotal(item) > 0)
  return graded.length ? Math.round(graded.reduce((sum, item) => sum + item.score / gradedTotal(item) * 100, 0) / graded.length) : null
})
const masteryOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  grid: { top: 12, right: 18, bottom: 24, left: 88 },
  xAxis: { type: 'value', max: 100, splitLine: { lineStyle: { color: '#eef0f5' } }, axisLabel: { color: '#969daf', fontSize: 9 } },
  yAxis: { type: 'category', inverse: true, data: mastery.value.slice(0, 6).map((item) => item.name), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: '#626c84', width: 75, overflow: 'truncate', fontSize: 10 } },
  series: [{ type: 'bar', data: mastery.value.slice(0, 6).map((item) => toPercent(item.mastery)), barWidth: 10, itemStyle: { borderRadius: 6, color: { type: 'linear', x: 0, y: 0, x2: 1, y2: 0, colorStops: [{ offset: 0, color: '#5c68dc' }, { offset: 1, color: '#27baa8' }] } } }],
}))

async function load() {
  loading.value = true
  const [examResult, wrongResult, masteryResult] = await Promise.allSettled([learningApi.historyPage({ page: page.value, page_size: pageSize }), learningApi.wrongQuestions(), learningApi.mastery()])
  const errors: string[] = []
  if (examResult.status === 'fulfilled') {
    history.value = examResult.value.items
    total.value = examResult.value.total
  }
  else errors.push(getApiErrorMessage(examResult.reason))
  if (wrongResult.status === 'fulfilled') {
    wrong.value = wrongResult.value.items
    wrongTotal.value = wrongResult.value.total
  }
  else errors.push(getApiErrorMessage(wrongResult.reason))
  if (masteryResult.status === 'fulfilled') mastery.value = masteryResult.value
  else errors.push(getApiErrorMessage(masteryResult.reason))
  error.value = errors[0] || ''
  loading.value = false
}

function changePage(value: number) { page.value = value; void load() }
function practiceWrong(item: WrongQuestion) {
  const textbook = item.question.textbook_id ?? item.textbook_id
  const knowledgePoint = item.question.knowledge_point_id ?? item.knowledge_point_id
  const query: Record<string, string> = {}
  if (textbook != null) query.textbook = String(textbook)
  if (knowledgePoint != null) query.knowledgePoint = String(knowledgePoint)
  void router.push({ path: '/exam/generate', query })
}

onMounted(load)
</script>

<template>
  <div>
    <PageHeader eyebrow="Learning Records" title="学习记录" description="回顾每次练习的表现，把错误转化为下一阶段的学习线索。">
      <template #actions><el-button :icon="RefreshRight" @click="load">刷新</el-button><el-button type="primary" :icon="EditPen" @click="router.push('/exam/generate')">开始练习</el-button></template>
    </PageHeader>
    <el-alert v-if="error" class="error-banner" type="warning" :closable="false" show-icon title="部分学习记录暂不可用" :description="error" />
    <div class="stat-grid" v-loading="loading">
      <article class="surface-card stat-card" style="--stat-color:#5864dc;--stat-soft:#eef0ff"><div class="stat-top"><span class="stat-icon"><el-icon><CircleCheck /></el-icon></span></div><p class="stat-value">{{ total }}</p><span class="stat-label">已完成练习</span></article>
      <article class="surface-card stat-card" style="--stat-color:#19a994;--stat-soft:#e8faf6"><div class="stat-top"><span class="stat-icon"><el-icon><TrendCharts /></el-icon></span></div><p class="stat-value">{{ average ?? '—' }}<small v-if="average !== null">%</small></p><span class="stat-label">本页客观题平均得分率</span></article>
      <article class="surface-card stat-card" style="--stat-color:#e95f6f;--stat-soft:#fff0f2"><div class="stat-top"><span class="stat-icon"><el-icon><Warning /></el-icon></span></div><p class="stat-value">{{ wrongTotal }}</p><span class="stat-label">待巩固错题</span></article>
      <article class="surface-card stat-card" style="--stat-color:#ef9342;--stat-soft:#fff3e8"><div class="stat-top"><span class="stat-icon"><el-icon><CircleCheck /></el-icon></span></div><p class="stat-value">{{ mastery.filter(item => item.mastery >= .8).length }}</p><span class="stat-label">已掌握知识点</span></article>
    </div>

    <div class="result-grid">
      <section class="surface-card records-card">
        <div class="records-tabs"><button :class="{ active: tab === 'records' }" @click="tab = 'records'">练习记录</button><button :class="{ active: tab === 'wrong' }" @click="tab = 'wrong'">错题本 <span>{{ wrongTotal }}</span></button></div>
        <div v-if="tab === 'records'">
          <el-table v-if="history.length" :data="history">
            <el-table-column label="练习" min-width="220"><template #default="{ row }"><div class="record-title"><strong>{{ row.title }}</strong><small>{{ new Date(row.submitted_at).toLocaleString('zh-CN') }}</small></div></template></el-table-column>
            <el-table-column label="客观题得分" width="140"><template #default="{ row }"><template v-if="gradedTotal(row) > 0"><strong class="score">{{ row.score }}</strong><span class="score-total"> / {{ gradedTotal(row) }}（{{ scoreRate(row) }}%）</span></template><span v-else>自行检查</span></template></el-table-column>
            <el-table-column label="正确 / 错误" width="140"><template #default="{ row }"><span class="success-text">{{ row.correct_count }}</span> / <span class="danger-text">{{ row.wrong_count }}</span><small v-if="row.pending_count" class="pending-note">自行检查 {{ row.pending_count }} 题</small></template></el-table-column>
            <el-table-column label="用时" width="100"><template #default="{ row }">{{ formatDuration(row.duration_seconds) }}</template></el-table-column>
            <el-table-column label="详情" width="110"><template #default="{ row }"><el-button link type="primary" @click="router.push(`/results/${row.id}`)">查看详情</el-button></template></el-table-column>
          </el-table>
          <StatePanel v-else title="还没有练习记录" description="生成一组练习并完成作答后，结果会出现在这里。"><el-button type="primary" @click="router.push('/exam/generate')">开始第一次练习</el-button></StatePanel>
          <el-pagination v-if="total > pageSize" class="record-pagination" :current-page="page" :page-size="pageSize" :total="total" :disabled="loading" layout="prev, pager, next, total" @current-change="changePage" />
        </div>
        <div v-else class="wrong-list">
          <article v-for="item in wrong" :key="item.id"><span class="wrong-index">{{ item.wrong_count }}×</span><div><div class="wrong-meta"><QuestionTypeTag :type="item.question.type" /><el-rate :model-value="item.question.difficulty" disabled /></div><h3><MathContent :text="item.question.stem" /></h3><p>最近答错：{{ new Date(item.last_wrong_at).toLocaleDateString('zh-CN') }}</p></div><el-button size="small" @click="practiceWrong(item)">再练</el-button></article>
          <StatePanel v-if="!wrong.length" :icon="CircleCheck" title="错题本是空的" description="继续保持，新的错误会自动归集到这里。" />
        </div>
      </section>
      <section class="surface-card card-pad mastery-side"><div class="section-title"><div><h2>掌握度分布</h2><p>优先展示薄弱知识点</p></div></div><BaseChart v-if="mastery.length" :option="masteryOption" height="290px" /><StatePanel v-else compact title="暂无掌握度数据" description="完成练习后自动生成。" /><el-button class="path-button" @click="router.push('/learning')">查看完整成长路径</el-button></section>
    </div>
  </div>
</template>

<style scoped>
.pending-note{display:block;margin-top:5px;color:#8b6c30;font-size:11px}.record-pagination{padding:18px;justify-content:center;flex-wrap:wrap}
.stat-value small{font-size:12px;color:#8991a4}.result-grid{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(300px,.65fr);gap:20px}.records-card{overflow:hidden}.records-tabs{height:66px;padding:0 23px;display:flex;gap:24px;border-bottom:1px solid var(--line)}.records-tabs button{position:relative;border:0;background:none;color:#8a92a6;font-size:12px;cursor:pointer}.records-tabs button.active{color:#4853c6;font-weight:600}.records-tabs button.active:after{content:'';position:absolute;right:0;bottom:0;left:0;height:3px;border-radius:3px 3px 0 0;background:#5662d7}.records-tabs span{padding:2px 6px;border-radius:8px;background:#fff0f2;color:#dc5d6c;font-size:8px}.record-title{display:flex;flex-direction:column;gap:4px}.record-title strong{font-size:12px}.record-title small{color:#959cad;font-size:9px}.score{color:#4e59ce;font:700 16px 'Plus Jakarta Sans'}.score-total{color:#9ba1b1;font-size:9px}.success-text{color:#18a792}.danger-text{color:#df5d6d}.wrong-list{padding:6px 23px 18px}.wrong-list>article{padding:18px 0;display:grid;grid-template-columns:38px 1fr auto;gap:13px;align-items:center;border-bottom:1px solid #edf0f5}.wrong-index{width:36px;height:36px;display:grid;place-items:center;border-radius:10px;color:#dc5c6b;background:#fff0f2;font-size:10px;font-weight:600}.wrong-meta{display:flex;align-items:center;gap:10px}.wrong-meta .el-rate{--el-rate-icon-size:12px}.wrong-list h3{margin:7px 0 4px;font-size:12px}.wrong-list p{margin:0;color:#999faf;font-size:9px}.mastery-side{align-self:start}.path-button{width:100%;margin-top:12px}@media(max-width:1050px){.result-grid{grid-template-columns:1fr}}@media(max-width:560px){.wrong-list>article{grid-template-columns:34px 1fr}.wrong-list>article>.el-button{grid-column:2}}
</style>
