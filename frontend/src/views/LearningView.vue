<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { EChartsOption } from 'echarts'
import { Aim, CircleCheck, Connection, EditPen, TrendCharts } from '@element-plus/icons-vue'
import BaseChart from '../components/BaseChart.vue'
import PageHeader from '../components/PageHeader.vue'
import StatePanel from '../components/StatePanel.vue'
import { learningApi, type LearningPath, type MasteryItem } from '../api'
import { getApiErrorMessage } from '../api/http'
import { masteryLevel, toPercent } from '../utils/learning'

const router = useRouter()
const route = useRoute()
const loading = ref(true)
const error = ref('')
const mastery = ref<MasteryItem[]>([])
const path = ref<LearningPath>({ nodes: [], edges: [] })

const mastered = computed(() => mastery.value.filter((item) => masteryLevel(item.mastery) === 'mastered').length)
const average = computed(() => mastery.value.length ? Math.round(mastery.value.reduce((sum, item) => sum + toPercent(item.mastery), 0) / mastery.value.length) : 0)
const weak = computed(() => mastery.value.filter((item) => item.mastery < .8).sort((a, b) => a.mastery - b.mastery).slice(0, 6))
const onlyWeak = computed(() => route.query.filter === 'weak')
const recordedPoints = computed(() => new Set(mastery.value.map(item => String(item.knowledge_point_id))))
const points = computed(() => {
  const items = new Map<string, MasteryItem>()
  for (const node of path.value.nodes) items.set(String(node.id), { knowledge_point_id: node.id, name: node.name, mastery: node.mastery, attempts: 0 })
  for (const item of mastery.value) items.set(String(item.knowledge_point_id), item)
  return [...items.values()].filter((item) => !onlyWeak.value || (recordedPoints.value.has(String(item.knowledge_point_id)) && item.mastery < .8)).sort((a, b) => a.mastery - b.mastery)
})
const graphOption = computed<EChartsOption>(() => ({
  tooltip: { formatter: (params: unknown) => {
    const item = params as { data?: { name?: string; value?: number } }
    return item.data?.name ? `${item.data.name}<br/>掌握度 ${item.data.value || 0}%` : ''
  } },
  series: [{
    type: 'graph', layout: 'force', roam: true, draggable: true, symbolSize: (value: number) => 42 + value * .18,
    force: { repulsion: 330, edgeLength: [80, 150], gravity: .08 },
    label: { show: true, position: 'bottom', distance: 7, color: '#566079', fontSize: 10 },
    edgeSymbol: ['none', 'arrow'], edgeSymbolSize: 7,
    lineStyle: { color: '#cbd0e1', width: 1.5, curveness: .08 },
    emphasis: { focus: 'adjacency', lineStyle: { width: 3 } },
    data: path.value.nodes.map((node) => {
      const value = toPercent(node.mastery)
      const level = masteryLevel(node.mastery)
      return { id: String(node.id), name: node.name, value, itemStyle: { color: level === 'mastered' ? '#26b39f' : level === 'learning' ? '#5b67d9' : '#d7dbe7', borderColor: '#fff', borderWidth: 3, shadowBlur: 12, shadowColor: 'rgba(36,47,94,.15)' } }
    }),
    links: path.value.edges.map((edge) => ({ source: String(edge.source), target: String(edge.target) })),
  }],
}))

async function load() {
  loading.value = true
  error.value = ''
  const [masteryResult, pathResult] = await Promise.allSettled([learningApi.mastery(), learningApi.path()])
  if (masteryResult.status === 'fulfilled') mastery.value = masteryResult.value
  else error.value = getApiErrorMessage(masteryResult.reason)
  if (pathResult.status === 'fulfilled') path.value = pathResult.value
  else if (!error.value) error.value = getApiErrorMessage(pathResult.reason)
  loading.value = false
}

function color(item: MasteryItem) { const level = masteryLevel(item.mastery); return level === 'mastered' ? '#23ad9b' : level === 'learning' ? '#5a66d8' : '#e26b77' }
function openPoint(id: string | number) { void router.push(`/learning/knowledge-points/${id}`) }
function openGraphPoint(params: unknown) {
  const event = params as { dataType?: string; data?: { id?: string | number } }
  if (event.dataType === 'node' && event.data?.id != null) openPoint(event.data.id)
}
onMounted(load)
</script>

<template>
  <div>
    <PageHeader title="学习进度" description="看看哪些内容已经学会，哪些还需要多练一练。">
      <template #actions><el-button type="primary" :icon="EditPen" @click="router.push('/exam/generate')">巩固薄弱点</el-button></template>
    </PageHeader>
    <el-alert v-if="error" class="error-banner" type="warning" :closable="false" show-icon title="学习路径暂不可用" :description="error" />
    <el-button v-if="error" @click="load">重新加载</el-button>
    <div class="path-summary" v-loading="loading">
      <article class="surface-card"><span><el-icon><Connection /></el-icon></span><div><strong>{{ path.nodes.length }}</strong><small>学习要点</small></div></article>
      <article class="surface-card"><span class="green"><el-icon><CircleCheck /></el-icon></span><div><strong>{{ mastered }}</strong><small>已掌握知识点</small></div></article>
      <article class="surface-card"><span class="orange"><el-icon><TrendCharts /></el-icon></span><div><strong>{{ average }}%</strong><small>平均掌握度</small></div></article>
      <article class="surface-card growth-note"><el-icon><Aim /></el-icon><div><strong>跨教材连续学习</strong><small>更换教材后，历史掌握度与错题仍会保留</small></div></article>
    </div>
    <div class="learning-grid">
      <section class="surface-card graph-card"><div class="section-title"><div><h2>我的知识地图</h2><p>点击知识点查看详情，可拖动和缩放</p></div><div class="legend"><span><i class="mastered"></i>已掌握</span><span><i class="learning"></i>学习中</span><span><i></i>未开始</span></div></div><BaseChart v-if="path.nodes.length" :option="graphOption" height="520px" @chart-click="openGraphPoint" /><StatePanel v-else title="还没有学习记录" description="先做一次练习，这里就会记录你的掌握情况。" /></section>
      <aside class="surface-card weak-card"><div class="section-title"><div><h2>优先巩固</h2><p>按当前掌握度从低到高</p></div></div><div v-if="weak.length" class="weak-list"><article v-for="(item, index) in weak" :key="item.knowledge_point_id"><span class="rank">{{ String(index + 1).padStart(2, '0') }}</span><div><button class="point-link" @click="openPoint(item.knowledge_point_id)">{{ item.name }}</button><div class="progress-track"><div class="progress-bar" :style="{ width: `${toPercent(item.mastery)}%`, background: color(item) }"></div></div><small>{{ item.attempts || 0 }} 次练习</small></div><b :style="{ color: color(item) }">{{ toPercent(item.mastery) }}%</b></article></div><StatePanel v-else compact title="暂无薄弱点" description="完成练习后会动态排序。" /><el-button class="practice-button" type="primary" plain @click="router.push('/exam/generate')">练一练薄弱内容</el-button></aside>
    </div>
    <section class="surface-card points-card">
      <div class="section-title"><div><h2>{{ onlyWeak ? '待巩固知识点' : '全部知识点' }}</h2><p>查看掌握记录、关联教材和最近作答</p></div><el-button @click="router.push({ path: '/learning', query: onlyWeak ? {} : { filter: 'weak' } })">{{ onlyWeak ? '查看全部' : '只看待巩固' }}</el-button></div>
      <div v-if="points.length" class="point-list"><button v-for="item in points" :key="item.knowledge_point_id" @click="openPoint(item.knowledge_point_id)"><span>{{ item.name }}</span><strong :style="{ color: color(item) }">{{ recordedPoints.has(String(item.knowledge_point_id)) ? `${toPercent(item.mastery)}%` : '尚未练习' }}</strong><small>查看详情 →</small></button></div>
      <StatePanel v-else compact :title="onlyWeak ? '暂无待巩固知识点' : '暂无知识点'" description="导入教材并开始学习后，这里会显示你的知识点。" />
    </section>
  </div>
</template>

<style scoped>
.point-link{display:block;max-width:100%;padding:0;margin-bottom:7px;border:0;background:none;text-align:left;color:#4551c0;font:600 11px inherit;cursor:pointer;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.point-link:focus-visible,.point-list button:focus-visible{outline:2px solid #5864dc;outline-offset:3px}.points-card{margin-top:20px;padding:23px}.point-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px}.point-list button{display:flex;align-items:center;gap:12px;padding:14px;border:1px solid #edf0f5;border-radius:10px;background:#f8f9fd;text-align:left;font:inherit;cursor:pointer}.point-list button span{flex:1;min-width:0}.point-list button small{color:#5864dc;white-space:nowrap}
.path-summary{margin-bottom:20px;display:grid;grid-template-columns:repeat(3,1fr) 1.5fr;gap:13px}.path-summary article{min-height:82px;padding:17px;display:flex;align-items:center;gap:12px}.path-summary article>span{width:40px;height:40px;display:grid;place-items:center;border-radius:12px;color:#5b66d6;background:#eef0ff}.path-summary article>span.green{color:#1aa893;background:#e9faf6}.path-summary article>span.orange{color:#e99141;background:#fff2e7}.path-summary strong,.path-summary small{display:block}.path-summary strong{font:700 17px 'Plus Jakarta Sans','Noto Sans SC'}.path-summary small{margin-top:3px;color:#9299aa;font-size:9px}.path-summary .growth-note{color:#fff;border:0;background:linear-gradient(115deg,#5260d5,#7658c6)}.growth-note>.el-icon{font-size:27px}.growth-note small{color:rgba(255,255,255,.68)}.learning-grid{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(300px,.55fr);gap:20px}.graph-card{padding:23px}.legend{display:flex;gap:12px;color:#8b93a6;font-size:9px}.legend span{display:flex;align-items:center;gap:5px}.legend i{width:7px;height:7px;border-radius:50%;background:#d4d8e4}.legend i.mastered{background:#26b39f}.legend i.learning{background:#5b67d9}.weak-card{padding:23px;align-self:start}.weak-list article{padding:14px 0;display:grid;grid-template-columns:31px 1fr auto;gap:11px;align-items:center;border-top:1px solid #edf0f5}.rank{width:29px;height:29px;display:grid;place-items:center;border-radius:9px;color:#6b75d9;background:#f0f1ff;font:700 9px 'Plus Jakarta Sans'}.weak-list article>div{min-width:0}.weak-list strong{display:block;margin-bottom:7px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px}.weak-list .progress-track{width:100%;height:5px}.weak-list small{display:block;margin-top:5px;color:#9aa0af;font-size:8px}.weak-list b{font:700 12px 'Plus Jakarta Sans'}.practice-button{width:100%;margin-top:15px}@media(max-width:1100px){.path-summary{grid-template-columns:repeat(2,1fr)}.learning-grid{grid-template-columns:1fr}}@media(max-width:560px){.path-summary{grid-template-columns:1fr 1fr}.path-summary .growth-note{grid-column:1/-1}.graph-card{padding:17px}.legend{display:none}}
</style>
