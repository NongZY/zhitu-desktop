<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { EChartsOption } from 'echarts'
import { Clock, Collection, DataLine, EditPen, Reading, Right, Trophy } from '@element-plus/icons-vue'
import BaseChart from '../components/BaseChart.vue'
import PageHeader from '../components/PageHeader.vue'
import StatePanel from '../components/StatePanel.vue'
import { learningApi, type DashboardSummary, type MasteryItem } from '../api'
import { getApiErrorMessage } from '../api/http'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const loading = ref(true)
const error = ref('')
const summary = ref<DashboardSummary>({ textbook_count: 0, completed_exam_count: 0, average_score: 0, study_minutes: 0 })
const mastery = ref<MasteryItem[]>([])

const greeting = computed(() => {
  const hour = new Date().getHours()
  return hour < 11 ? '早上好' : hour < 14 ? '中午好' : hour < 18 ? '下午好' : '晚上好'
})

const activityOption = computed<EChartsOption>(() => {
  const data = summary.value.weekly_activity || []
  return {
    color: ['#5864dc'],
    tooltip: { trigger: 'axis', formatter: '{b}<br/>学习 {c} 分钟' },
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

onMounted(load)
</script>

<template>
  <div>
    <PageHeader eyebrow="Learning Overview" :title="`${greeting}，${auth.user?.name || '学习者'}`" description="今天也向前一步吧。系统会根据你的学习表现，持续优化下一次练习。">
      <template #actions><el-button type="primary" :icon="EditPen" @click="router.push('/exam/generate')">开始智能练习</el-button></template>
    </PageHeader>

    <el-alert v-if="error" class="error-banner" type="warning" :closable="false" show-icon title="学习数据暂不可用" :description="error" />
    <div class="stat-grid" v-loading="loading">
      <article class="surface-card stat-card" style="--stat-color:#5864dc;--stat-soft:#eef0ff"><div class="stat-top"><span class="stat-icon"><el-icon><Reading /></el-icon></span><span class="stat-trend">持续积累</span></div><p class="stat-value">{{ summary.textbook_count }}</p><span class="stat-label">正在学习的教材</span></article>
      <article class="surface-card stat-card" style="--stat-color:#1aa995;--stat-soft:#e8faf6"><div class="stat-top"><span class="stat-icon"><el-icon><Trophy /></el-icon></span><span class="stat-trend">{{ summary.completed_exam_count ? '稳步提升' : '等待首测' }}</span></div><p class="stat-value">{{ Math.round(summary.average_score || 0) }}<small> 分</small></p><span class="stat-label">测验平均成绩</span></article>
      <article class="surface-card stat-card" style="--stat-color:#ef9140;--stat-soft:#fff3e8"><div class="stat-top"><span class="stat-icon"><el-icon><Clock /></el-icon></span><span class="stat-trend">本阶段</span></div><p class="stat-value">{{ summary.study_minutes || 0 }}<small> 分钟</small></p><span class="stat-label">累计学习时长</span></article>
      <article class="surface-card stat-card" style="--stat-color:#d95f76;--stat-soft:#fff0f3"><div class="stat-top"><span class="stat-icon"><el-icon><DataLine /></el-icon></span><span class="stat-trend">需要关注</span></div><p class="stat-value">{{ summary.weak_point_count || 0 }}</p><span class="stat-label">待巩固知识点</span></article>
    </div>

    <div class="dashboard-main-grid">
      <section class="surface-card card-pad activity-card">
        <div class="section-title"><div><h2>本周学习趋势</h2><p>每天的有效学习时长</p></div><span class="week-chip">近 7 天</span></div>
        <BaseChart v-if="summary.weekly_activity?.length" :option="activityOption" height="260px" />
        <StatePanel v-else compact title="还没有学习趋势" description="完成练习后，这里会形成你的学习曲线。" />
      </section>
      <section class="surface-card card-pad mastery-card">
        <div class="section-title"><div><h2>知识掌握概况</h2><p>重点知识维度分布</p></div><button class="icon-link" @click="router.push('/learning')"><el-icon><Right /></el-icon></button></div>
        <BaseChart v-if="mastery.length >= 3" :option="masteryOption" height="260px" />
        <StatePanel v-else compact title="尚未形成掌握画像" description="至少完成一次覆盖多个知识点的测试。" />
      </section>
    </div>

    <div class="dashboard-lower-grid">
      <section class="surface-card card-pad">
        <div class="section-title"><div><h2>最近测试</h2><p>你的阶段性学习成果</p></div><span class="section-link" @click="router.push('/results')">查看全部</span></div>
        <div v-if="summary.recent_exams?.length" class="recent-list">
          <article v-for="item in summary.recent_exams" :key="item.id" class="recent-item">
            <span class="recent-icon"><el-icon><Collection /></el-icon></span>
            <div class="recent-copy"><strong>{{ item.title }}</strong><small>{{ new Date(item.submitted_at).toLocaleDateString('zh-CN') }}</small></div>
            <div class="recent-score"><strong>{{ item.score }}</strong><small>/ {{ item.total_score }}</small></div>
          </article>
        </div>
        <StatePanel v-else compact title="还没有测试记录" description="完成第一份试卷，开始追踪你的进步。"><el-button size="small" @click="router.push('/exam/generate')">去组卷</el-button></StatePanel>
      </section>
      <section class="surface-card card-pad recommendation-card">
        <div class="section-title"><div><h2>今日建议</h2><p>根据掌握状态动态生成</p></div></div>
        <div v-if="summary.recommendations?.length" class="recommendation-list">
          <article v-for="(item, index) in summary.recommendations.slice(0, 3)" :key="item.id || index"><span>{{ String(index + 1).padStart(2, '0') }}</span><div><strong>{{ item.title }}</strong><p>{{ item.description }}</p></div></article>
        </div>
        <StatePanel v-else compact title="暂无个性化建议" description="系统需要更多练习数据来理解你的学习状态。" />
      </section>
    </div>
  </div>
</template>

<style scoped>
.stat-value small{font-size:12px;color:#848ca1}.dashboard-main-grid{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(300px,.85fr);gap:20px;margin-bottom:20px}.dashboard-lower-grid{display:grid;grid-template-columns:1.15fr .85fr;gap:20px}.week-chip{padding:6px 10px;border-radius:8px;color:#69728b;background:#f5f6fa;font-size:10px}.icon-link{width:30px;height:30px;border:0;border-radius:9px;background:#f4f5fa;color:#5f68cf;cursor:pointer}.recent-list{display:grid}.recent-item{display:flex;align-items:center;gap:13px;padding:13px 0;border-bottom:1px solid #eff1f6}.recent-item:last-child{border:0}.recent-icon{width:38px;height:38px;display:grid;place-items:center;border-radius:11px;color:#5965d8;background:#eef0ff}.recent-copy{flex:1;display:flex;flex-direction:column;gap:3px}.recent-copy strong{font-size:13px}.recent-copy small{color:#989fb1;font-size:10px}.recent-score strong{font:700 17px 'Plus Jakarta Sans';color:#2c3656}.recent-score small{color:#9ca2b2;font-size:10px}.recommendation-list{display:grid;gap:10px}.recommendation-list article{padding:14px;display:flex;gap:13px;border-radius:13px;background:#f8f9fd}.recommendation-list article>span{font:700 12px 'Plus Jakarta Sans';color:#7781e1}.recommendation-list strong{font-size:12px}.recommendation-list p{margin:4px 0 0;color:#858da3;font-size:10px;line-height:1.6}@media(max-width:1100px){.dashboard-main-grid,.dashboard-lower-grid{grid-template-columns:1fr}}@media(max-width:520px){.activity-card,.mastery-card{padding:18px}}
</style>
