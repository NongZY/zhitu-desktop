<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { EChartsOption } from 'echarts'
import { Aim, CircleCheck, Connection, EditPen, TrendCharts } from '@element-plus/icons-vue'
import BaseChart from '../components/BaseChart.vue'
import PageHeader from '../components/PageHeader.vue'
import StatePanel from '../components/StatePanel.vue'
import { learningApi, type LearningPath, type MasteryItem } from '../api'
import { getApiErrorMessage } from '../api/http'
import { masteryLevel, toPercent } from '../utils/learning'

const router = useRouter()
const loading = ref(true)
const error = ref('')
const mastery = ref<MasteryItem[]>([])
const path = ref<LearningPath>({ nodes: [], edges: [] })

const mastered = computed(() => mastery.value.filter((item) => masteryLevel(item.mastery) === 'mastered').length)
const average = computed(() => mastery.value.length ? Math.round(mastery.value.reduce((sum, item) => sum + toPercent(item.mastery), 0) / mastery.value.length) : 0)
const weak = computed(() => [...mastery.value].sort((a, b) => a.mastery - b.mastery).slice(0, 6))
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
  const [masteryResult, pathResult] = await Promise.allSettled([learningApi.mastery(), learningApi.path()])
  if (masteryResult.status === 'fulfilled') mastery.value = masteryResult.value
  else error.value = getApiErrorMessage(masteryResult.reason)
  if (pathResult.status === 'fulfilled') path.value = pathResult.value
  else if (!error.value) error.value = getApiErrorMessage(pathResult.reason)
  loading.value = false
}

function color(item: MasteryItem) { const level = masteryLevel(item.mastery); return level === 'mastered' ? '#23ad9b' : level === 'learning' ? '#5a66d8' : '#e26b77' }
onMounted(load)
</script>

<template>
  <div>
    <PageHeader eyebrow="Growth Path" title="学习路径" description="跨教材保留知识掌握状态，并用前置关系连接持续成长路线。">
      <template #actions><el-button type="primary" :icon="EditPen" @click="router.push('/exam/generate')">巩固薄弱点</el-button></template>
    </PageHeader>
    <el-alert v-if="error" class="error-banner" type="warning" :closable="false" show-icon title="学习路径暂不可用" :description="error" />
    <div class="path-summary" v-loading="loading">
      <article class="surface-card"><span><el-icon><Connection /></el-icon></span><div><strong>{{ path.nodes.length }}</strong><small>全局知识节点</small></div></article>
      <article class="surface-card"><span class="green"><el-icon><CircleCheck /></el-icon></span><div><strong>{{ mastered }}</strong><small>已掌握知识点</small></div></article>
      <article class="surface-card"><span class="orange"><el-icon><TrendCharts /></el-icon></span><div><strong>{{ average }}%</strong><small>平均掌握度</small></div></article>
      <article class="surface-card growth-note"><el-icon><Aim /></el-icon><div><strong>跨教材连续学习</strong><small>更换教材后，历史掌握度与错题仍会保留</small></div></article>
    </div>
    <div class="learning-grid">
      <section class="surface-card graph-card"><div class="section-title"><div><h2>全局知识图谱</h2><p>拖动节点探索前置关系，滚轮可缩放</p></div><div class="legend"><span><i class="mastered"></i>已掌握</span><span><i class="learning"></i>学习中</span><span><i></i>未开始</span></div></div><BaseChart v-if="path.nodes.length" :option="graphOption" height="520px" /><StatePanel v-else title="知识图谱尚未建立" description="教师完成教材知识点映射和前置关系审核后，这里会生成学习路径。" /></section>
      <aside class="surface-card weak-card"><div class="section-title"><div><h2>优先巩固</h2><p>按当前掌握度从低到高</p></div></div><div v-if="weak.length" class="weak-list"><article v-for="(item, index) in weak" :key="item.knowledge_point_id"><span class="rank">{{ String(index + 1).padStart(2, '0') }}</span><div><strong>{{ item.name }}</strong><div class="progress-track"><div class="progress-bar" :style="{ width: `${toPercent(item.mastery)}%`, background: color(item) }"></div></div><small>{{ item.attempts || 0 }} 次练习</small></div><b :style="{ color: color(item) }">{{ toPercent(item.mastery) }}%</b></article></div><StatePanel v-else compact title="暂无薄弱点" description="完成练习后会动态排序。" /><el-button class="practice-button" type="primary" plain @click="router.push('/exam/generate')">生成针对性练习</el-button></aside>
    </div>
  </div>
</template>

<style scoped>
.path-summary{margin-bottom:20px;display:grid;grid-template-columns:repeat(3,1fr) 1.5fr;gap:13px}.path-summary article{min-height:82px;padding:17px;display:flex;align-items:center;gap:12px}.path-summary article>span{width:40px;height:40px;display:grid;place-items:center;border-radius:12px;color:#5b66d6;background:#eef0ff}.path-summary article>span.green{color:#1aa893;background:#e9faf6}.path-summary article>span.orange{color:#e99141;background:#fff2e7}.path-summary strong,.path-summary small{display:block}.path-summary strong{font:700 17px 'Plus Jakarta Sans','Noto Sans SC'}.path-summary small{margin-top:3px;color:#9299aa;font-size:9px}.path-summary .growth-note{color:#fff;border:0;background:linear-gradient(115deg,#5260d5,#7658c6)}.growth-note>.el-icon{font-size:27px}.growth-note small{color:rgba(255,255,255,.68)}.learning-grid{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(300px,.55fr);gap:20px}.graph-card{padding:23px}.legend{display:flex;gap:12px;color:#8b93a6;font-size:9px}.legend span{display:flex;align-items:center;gap:5px}.legend i{width:7px;height:7px;border-radius:50%;background:#d4d8e4}.legend i.mastered{background:#26b39f}.legend i.learning{background:#5b67d9}.weak-card{padding:23px;align-self:start}.weak-list article{padding:14px 0;display:grid;grid-template-columns:31px 1fr auto;gap:11px;align-items:center;border-top:1px solid #edf0f5}.rank{width:29px;height:29px;display:grid;place-items:center;border-radius:9px;color:#6b75d9;background:#f0f1ff;font:700 9px 'Plus Jakarta Sans'}.weak-list article>div{min-width:0}.weak-list strong{display:block;margin-bottom:7px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px}.weak-list .progress-track{width:100%;height:5px}.weak-list small{display:block;margin-top:5px;color:#9aa0af;font-size:8px}.weak-list b{font:700 12px 'Plus Jakarta Sans'}.practice-button{width:100%;margin-top:15px}@media(max-width:1100px){.path-summary{grid-template-columns:repeat(2,1fr)}.learning-grid{grid-template-columns:1fr}}@media(max-width:560px){.path-summary{grid-template-columns:1fr 1fr}.path-summary .growth-note{grid-column:1/-1}.graph-card{padding:17px}.legend{display:none}}
</style>
