<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import type { EChartsOption } from 'echarts'
import { Clock, Collection, DataLine, EditPen, Reading, Right, Trophy } from '@element-plus/icons-vue'
import BaseChart from '../components/BaseChart.vue'
import PageHeader from '../components/PageHeader.vue'
import StatePanel from '../components/StatePanel.vue'
import { learningApi, readingApi, type ReadingHome, type DashboardSummary, type MasteryItem } from '../api'
import { getApiErrorMessage } from '../api/http'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const loading = ref(true)
const error = ref('')
const summary = ref<DashboardSummary>({ textbook_count: 0, completed_exam_count: 0, average_score: 0, study_minutes: 0 })
const mastery = ref<MasteryItem[]>([])
const readingHome = ref<ReadingHome | null>(null)
const readingLoading = ref(true)
const readingError = ref('')
let homeRequest = 0
let homeAbort: AbortController | undefined

async function loadReadingHome() {
  const request = ++homeRequest
  homeAbort?.abort(); homeAbort = new AbortController()
  readingHome.value = null; readingLoading.value = true; readingError.value = ''
  try {
    const data = await readingApi.home(homeAbort.signal)
    if (request === homeRequest) readingHome.value = data
  } catch {
    if (request === homeRequest) readingError.value = '阅读位置暂时没有加载出来，可以先打开教材'
  } finally {
    if (request === homeRequest) readingLoading.value = false
  }
}
watch(() => auth.user?.id, loadReadingHome)
onUnmounted(() => { homeRequest++; homeAbort?.abort() })

const greeting = computed(() => {
  const hour = new Date().getHours()
  return hour < 11 ? '早上好' : hour < 14 ? '中午好' : hour < 18 ? '下午好' : '晚上好'
})

const activityOption = computed<EChartsOption>(() => {
  const data = summary.value.weekly_activity || []
  return {
    color: ['#5864dc'],
    tooltip: { trigger: 'axis', formatter: '{b}<br/>练习 {c} 分钟' },
    grid: { top: 18, right: 12, bottom: 24, left: 36 },
    xAxis: { type: 'category', data: data.map((item) => item.date.slice(5)), boundaryGap: false, axisLine: { lineStyle: { color: '#e8ebf3' } }, axisTick: { show: false }, axisLabel: { color: '#9299ad', fontSize: 10 } },
    yAxis: { type: 'value', minInterval: 10, splitLine: { lineStyle: { color: '#f0f2f7' } }, axisLabel: { color: '#9299ad', fontSize: 10 } },
    series: [{ type: 'line', data: data.map((item) => item.minutes), smooth: true, symbol: 'circle', symbolSize: 7, lineStyle: { width: 3 }, areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(88,100,220,.24)' }, { offset: 1, color: 'rgba(88,100,220,.01)' }] } } }],
  }
})

const masteryOption = computed<EChartsOption>(() => {
  const points = mastery.value.slice(0, 6)
  return {
    tooltip: {},
    radar: { radius: '68%', splitNumber: 4, indicator: points.map((item) => ({ name: item.name, max: 100 })), axisName: { color: '#69728b', fontSize: 10 }, splitLine: { lineStyle: { color: '#e7eaf2' } }, splitArea: { areaStyle: { color: ['#fff', '#fafbfe'] } }, axisLine: { lineStyle: { color: '#e7eaf2' } } },
    series: [{ type: 'radar', data: [{ value: points.map((item) => Math.round(item.mastery * (item.mastery <= 1 ? 100 : 1))), areaStyle: { color: 'rgba(42,187,169,.2)' }, lineStyle: { color: '#21b5a3', width: 2 }, itemStyle: { color: '#21b5a3' } }] }],
  }
})

async function load() {
  loading.value = true
  error.value = ''
  const [dashboardResult, masteryResult] = await Promise.allSettled([learningApi.dashboard(), learningApi.mastery()])
  if (dashboardResult.status === 'fulfilled') summary.value = dashboardResult.value
  else error.value = getApiErrorMessage(dashboardResult.reason)
  if (masteryResult.status === 'fulfilled') mastery.value = masteryResult.value
  loading.value = false
}

onMounted(() => { void load(); void loadReadingHome() })
</script>

<template>
  <div>
    <PageHeader eyebrow="Learning Overview" :title="`${greeting}，${auth.user?.name || '学习者'}`" description="今天也向前一步吧。系统会根据你的学习表现，持续优化下一次练习。">
      <template #actions><el-button type="primary" :icon="EditPen" @click="router.push('/exam/generate')">开始智能练习</el-button></template>
    </PageHeader>

    <section class="surface-card card-pad resume-card" aria-label="继续学习">
      <h2>接着学</h2>
      <p v-if="readingLoading" role="status">正在查找上次读到的位置…</p>
      <p v-if="readingError" role="alert">{{ readingError }} <el-button text @click="loadReadingHome">重试读取位置</el-button></p>
      <template v-if="readingHome?.continue_reading">
        <h3>{{ readingHome.continue_reading.title }}</h3>
        <p>{{ readingHome.continue_reading.chapter_title ? `${readingHome.continue_reading.chapter_title} · ` : '' }}PDF 第 {{ readingHome.continue_reading.page_number }} 页 / {{ readingHome.continue_reading.page_count }} 页</p>
        <el-button type="primary" :icon="Reading" @click="router.push(`/textbooks/${readingHome.continue_reading.textbook_id}?page=${readingHome.continue_reading.page_number}`)">继续阅读</el-button>
      </template>
      <p v-else-if="readingHome && !readingHome.textbook_count">把想学的教材放进来，从第一本开始。</p>
      <p v-else-if="readingHome">选一本教材开始阅读，读到的位置会自动保存。</p>
      <p v-if="readingHome?.reading_notice" role="status">{{ readingHome.reading_notice }}</p>
      <div class="resume-actions">
        <el-button @click="router.push('/textbooks')">{{ readingHome && !readingHome.textbook_count ? '上传第一本教材' : '打开教材' }}</el-button>
        <el-button @click="router.push('/exam/generate')">做练习</el-button>
        <el-button @click="router.push('/results')">学习记录</el-button>
      </div>
    </section>

    <el-alert v-if="error" class="error-banner" type="warning" :closable="false" show-icon title="学习数据暂不可用" :description="error" />
    <el-button v-if="error" @click="load">重新加载</el-button>
    <div class="stat-grid" v-loading="loading">
      <button class="surface-card stat-card" style="--stat-color:#5864dc;--stat-soft:#eef0ff" @click="router.push('/textbooks')"><div class="stat-top"><span class="stat-icon"><el-icon><Reading /></el-icon></span><span class="stat-trend">查看教材 →</span></div><p class="stat-value">{{ summary.textbook_count }}</p><span class="stat-label">正在学习的教材</span></button>
      <button class="surface-card stat-card" style="--stat-color:#1aa995;--stat-soft:#e8faf6" @click="router.push('/results')"><div class="stat-top"><span class="stat-icon"><el-icon><Trophy /></el-icon></span><span class="stat-trend">查看练习 →</span></div><p class="stat-value">{{ Math.round(summary.average_score || 0) }}<small>%</small></p><span class="stat-label">客观题平均得分率</span></button>
      <button class="surface-card stat-card" style="--stat-color:#ef9140;--stat-soft:#fff3e8" @click="router.push('/results')"><div class="stat-top"><span class="stat-icon"><el-icon><Clock /></el-icon></span><span class="stat-trend">查看用时 →</span></div><p class="stat-value">{{ summary.study_minutes || 0 }}<small> 分钟</small></p><span class="stat-label">累计练习时长</span></button>
      <button class="surface-card stat-card" style="--stat-color:#d95f76;--stat-soft:#fff0f3" @click="router.push('/learning?filter=weak')"><div class="stat-top"><span class="stat-icon"><el-icon><DataLine /></el-icon></span><span class="stat-trend">查看薄弱点 →</span></div><p class="stat-value">{{ summary.weak_point_count || 0 }}</p><span class="stat-label">待巩固知识点</span></button>
    </div>

    <div class="dashboard-main-grid">
      <section class="surface-card card-pad activity-card">
        <div class="section-title"><div><h2>本周学习趋势</h2><p>每天的练习时长</p></div><span class="week-chip">近 7 天</span></div>
        <BaseChart v-if="summary.weekly_activity?.length" :option="activityOption" height="260px" />
        <StatePanel v-else compact title="还没有学习趋势" description="完成练习后，这里会形成你的学习曲线。" />
      </section>
      <section class="surface-card card-pad mastery-card">
        <div class="section-title"><div><h2>知识掌握概况</h2><p>重点知识维度分布</p></div><button class="icon-link" aria-label="查看知识点详情" @click="router.push('/learning')"><el-icon><Right /></el-icon></button></div>
        <BaseChart v-if="mastery.length >= 3" :option="masteryOption" height="260px" />
        <StatePanel v-else compact title="尚未形成掌握画像" description="至少完成一次覆盖多个知识点的练习。" />
        <div class="point-links"><el-button v-for="item in mastery.slice(0, 6)" :key="item.knowledge_point_id" link type="primary" @click="router.push(`/learning/knowledge-points/${item.knowledge_point_id}`)">{{ item.name }}</el-button></div>
      </section>
    </div>

    <div class="dashboard-lower-grid">
      <section class="surface-card card-pad">
        <div class="section-title"><div><h2>最近练习</h2><p>点开查看每道题的答案和解析</p></div><el-button link type="primary" @click="router.push('/results')">查看全部</el-button></div>
        <div v-if="summary.recent_exams?.length" class="recent-list">
          <button v-for="item in summary.recent_exams" :key="item.id" class="recent-item" @click="router.push(`/results/${item.id}`)">
            <span class="recent-icon"><el-icon><Collection /></el-icon></span>
            <div class="recent-copy"><strong>{{ item.title }}</strong><small>{{ new Date(item.submitted_at).toLocaleDateString('zh-CN') }}</small></div>
            <div class="recent-score"><strong v-if="(item.graded_total_score ?? item.total_score) > 0">{{ item.score }}<small>/ {{ item.graded_total_score ?? item.total_score }}</small></strong><small v-else>自行检查</small><small v-if="item.pending_count"> · {{ item.pending_count }} 题待自查</small></div>
          </button>
        </div>
        <StatePanel v-else compact title="还没有练习记录" description="完成第一次练习，开始追踪你的进步。"><el-button size="small" @click="router.push('/exam/generate')">开始练习</el-button></StatePanel>
      </section>
      <section class="surface-card card-pad recommendation-card">
        <div class="section-title"><div><h2>今日建议</h2><p>根据掌握状态动态生成</p></div></div>
        <div v-if="summary.recommendations?.length" class="recommendation-list">
          <button v-for="(item, index) in summary.recommendations.slice(0, 3)" :key="item.id || index" @click="router.push(item.knowledge_point_id != null ? `/learning/knowledge-points/${item.knowledge_point_id}` : '/learning?filter=weak')"><span>{{ String(index + 1).padStart(2, '0') }}</span><div><strong>{{ item.title }}</strong><p>{{ item.description }}</p><small>查看详情 →</small></div></button>
        </div>
        <StatePanel v-else compact title="暂无个性化建议" description="系统需要更多练习数据来理解你的学习状态。" />
      </section>
    </div>
  </div>
</template>

<style scoped>
.resume-card{margin-bottom:20px}.resume-card h2{margin-top:0}.resume-card h3{margin-bottom:6px}.resume-card p{color:#69728b;font-size:14px;line-height:1.6}.resume-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}.resume-actions .el-button{margin:0}
.stat-card,.recent-item,.recommendation-list>button{text-align:left;font:inherit;cursor:pointer;color:inherit}.stat-card:focus-visible,.recent-item:focus-visible,.recommendation-list>button:focus-visible{outline:2px solid #5864dc;outline-offset:3px}.recent-item{width:100%;background:transparent;border:0}.recommendation-list>button{border:0;padding:14px;display:flex;gap:13px;border-radius:13px;background:#f8f9fd}.recommendation-list>button>span{font-weight:700;color:#7781e1}.recommendation-list>button small{display:block;margin-top:8px;color:#5864dc}.point-links{display:flex;flex-wrap:wrap;gap:8px}.point-links .el-button{margin:0}
.stat-value small{font-size:12px;color:#848ca1}.dashboard-main-grid{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(300px,.85fr);gap:20px;margin-bottom:20px}.dashboard-lower-grid{display:grid;grid-template-columns:1.15fr .85fr;gap:20px}.week-chip{padding:6px 10px;border-radius:8px;color:#69728b;background:#f5f6fa;font-size:10px}.icon-link{width:30px;height:30px;border:0;border-radius:9px;background:#f4f5fa;color:#5f68cf;cursor:pointer}.recent-list{display:grid}.recent-item{display:flex;align-items:center;gap:13px;padding:13px 0;border-bottom:1px solid #eff1f6}.recent-item:last-child{border:0}.recent-icon{width:38px;height:38px;display:grid;place-items:center;border-radius:11px;color:#5965d8;background:#eef0ff}.recent-copy{flex:1;display:flex;flex-direction:column;gap:3px}.recent-copy strong{font-size:13px}.recent-copy small{color:#989fb1;font-size:10px}.recent-score strong{font:700 17px 'Plus Jakarta Sans';color:#2c3656}.recent-score small{color:#9ca2b2;font-size:10px}.recommendation-list{display:grid;gap:10px}.recommendation-list article{padding:14px;display:flex;gap:13px;border-radius:13px;background:#f8f9fd}.recommendation-list article>span{font:700 12px 'Plus Jakarta Sans';color:#7781e1}.recommendation-list strong{font-size:12px}.recommendation-list p{margin:4px 0 0;color:#858da3;font-size:10px;line-height:1.6}@media(max-width:1100px){.dashboard-main-grid,.dashboard-lower-grid{grid-template-columns:1fr}}@media(max-width:520px){.activity-card,.mastery-card{padding:18px}}
</style>
