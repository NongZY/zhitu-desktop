<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Aim, Clock, DataAnalysis, MagicStick, Select } from '@element-plus/icons-vue'
import PageHeader from '../components/PageHeader.vue'
import { examApi, textbookApi, type ExamGeneratePayload, type QuestionType, type Textbook } from '../api'
import { getApiErrorMessage } from '../api/http'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const books = ref<Textbook[]>([])
const loading = ref(false)
const error = ref('')
const form = reactive<ExamGeneratePayload>({
  title: '',
  textbook_id: undefined,
  question_types: ['single_choice', 'fill_blank', 'true_false'],
  difficulty_min: 1,
  difficulty_max: 5,
  question_count: 5,
  duration_minutes: 20,
  mode: 'adaptive',
})
const types: Array<{ value: QuestionType; label: string }> = [
  { value: 'single_choice', label: '单选题' }, { value: 'multiple_choice', label: '多选题' },
  { value: 'fill_blank', label: '填空题' }, { value: 'true_false', label: '判断题' },
  { value: 'short_answer', label: '简答题' },
]

async function generate() {
  if (auth.isDemo) return ElMessage.info('演示模式不会创建试卷，请连接后端体验完整流程')
  if (!form.textbook_id) return ElMessage.warning('请先选择教材')
  if ((form.difficulty_min || 1) > (form.difficulty_max || 5)) return ElMessage.warning('难度范围设置有误')
  loading.value = true
  error.value = ''
  try {
    const paper = await examApi.generate(form)
    ElMessage.success(`已生成 ${paper.questions.length} 道题`)
    await router.push(`/exam/${paper.id}/take`)
  } catch (err) {
    error.value = getApiErrorMessage(err, '组卷失败，请确认题库中有足够的已审核题目')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    books.value = (await textbookApi.list()).items
    const requested = typeof route.query.textbook === 'string' ? route.query.textbook : undefined
    form.textbook_id = requested || books.value[0]?.id
  } catch (err) {
    error.value = getApiErrorMessage(err)
  }
})
</script>

<template>
  <div>
    <PageHeader eyebrow="Adaptive Paper" title="智能组卷" description="系统结合筛选条件与知识掌握度，优先覆盖薄弱知识点。" />
    <el-alert v-if="error" class="error-banner" type="warning" show-icon :closable="false" title="暂时无法生成试卷" :description="error" />
    <div class="generate-grid">
      <section class="surface-card configuration-card">
        <div class="section-title"><div><h2>组卷配置</h2><p>本次设置只影响新试卷</p></div><span class="step-chip">01</span></div>
        <el-form label-position="top" size="large">
          <el-form-item label="试卷名称"><el-input v-model="form.title" placeholder="留空将使用系统名称" /></el-form-item>
          <el-form-item label="教材范围"><el-select v-model="form.textbook_id" style="width:100%" placeholder="选择教材"><el-option v-for="book in books" :key="book.id" :label="`${book.title} · ${book.grade || book.subject || ''}`" :value="book.id" /></el-select></el-form-item>
          <el-form-item label="出题策略">
            <div class="mode-grid">
              <button type="button" :class="{ active: form.mode === 'adaptive' }" @click="form.mode = 'adaptive'"><span><el-icon><MagicStick /></el-icon></span><strong>自适应组卷</strong><small>薄弱点获得更高抽题权重</small></button>
              <button type="button" :class="{ active: form.mode === 'random' }" @click="form.mode = 'random'"><span><el-icon><Select /></el-icon></span><strong>随机组卷</strong><small>在筛选范围内均匀抽取</small></button>
            </div>
          </el-form-item>
          <el-form-item label="题型"><el-checkbox-group v-model="form.question_types"><el-checkbox v-for="item in types" :key="item.value" :value="item.value">{{ item.label }}</el-checkbox></el-checkbox-group></el-form-item>
          <div class="form-row">
            <el-form-item label="题目数量"><el-input-number v-model="form.question_count" :min="1" :max="50" /></el-form-item>
            <el-form-item label="考试时长"><el-input-number v-model="form.duration_minutes" :min="1" :max="180" /><span class="unit">分钟</span></el-form-item>
          </div>
          <el-form-item label="难度范围"><div class="difficulty-row"><el-select v-model="form.difficulty_min"><el-option v-for="n in 5" :key="n" :label="`${n} 星`" :value="n" /></el-select><span>至</span><el-select v-model="form.difficulty_max"><el-option v-for="n in 5" :key="n" :label="`${n} 星`" :value="n" /></el-select></div></el-form-item>
          <el-button class="generate-button" type="primary" size="large" :loading="loading" :icon="Aim" @click="generate">生成并开始考试</el-button>
        </el-form>
      </section>

      <aside class="preview-column">
        <section class="strategy-card">
          <p class="eyebrow">HOW IT WORKS</p><h2>你的下一份试卷<br />由学习数据驱动</h2>
          <div class="strategy-flow">
            <article><span><el-icon><DataAnalysis /></el-icon></span><div><strong>读取掌握画像</strong><p>基于历史正确率、难度与练习记录识别薄弱点。</p></div></article>
            <i></i>
            <article><span><el-icon><MagicStick /></el-icon></span><div><strong>动态分配权重</strong><p>薄弱知识点被优先选中，同时保留整体覆盖。</p></div></article>
            <i></i>
            <article><span><el-icon><Clock /></el-icon></span><div><strong>考试后立即更新</strong><p>客观题自动评分，结果回写错题本与掌握度。</p></div></article>
          </div>
        </section>
        <section class="surface-card tip-card"><strong>组卷前提示</strong><p>只有“已审核”题目会进入正式试卷。简答题可作答，但当前版本需要教师后续人工评分。</p></section>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.generate-grid{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(330px,.72fr);gap:22px}.configuration-card{padding:27px 30px}.step-chip{width:35px;height:30px;display:grid;place-items:center;border-radius:9px;color:#5c67d7;background:#f0f1ff;font:700 11px 'Plus Jakarta Sans'}.mode-grid{width:100%;display:grid;grid-template-columns:1fr 1fr;gap:12px}.mode-grid button{padding:17px;display:grid;grid-template-columns:38px 1fr;column-gap:11px;text-align:left;border:1px solid #e3e6ef;border-radius:13px;background:#fff;cursor:pointer}.mode-grid button.active{border-color:#717ce5;background:#f7f8ff;box-shadow:0 0 0 2px rgba(85,98,218,.08)}.mode-grid button>span{grid-row:1/3;width:38px;height:38px;display:grid;place-items:center;border-radius:11px;color:#5f69d7;background:#eef0ff}.mode-grid strong{font-size:12px}.mode-grid small{margin-top:3px;color:#9097aa;font-size:9px}.form-row{display:grid;grid-template-columns:1fr 1fr;gap:18px}.unit{margin-left:8px;color:#8c93a5;font-size:11px}.difficulty-row{display:flex;align-items:center;gap:12px}.difficulty-row .el-select{width:130px}.difficulty-row>span{color:#939aac;font-size:11px}.generate-button{width:100%;margin-top:8px}.preview-column{display:grid;align-content:start;gap:17px}.strategy-card{padding:31px;border-radius:20px;color:#fff;background:linear-gradient(150deg,#1a2044,#303872);box-shadow:0 18px 45px rgba(27,35,82,.2)}.strategy-card .eyebrow{color:#7ed8ce}.strategy-card h2{font-size:23px;line-height:1.45}.strategy-flow{margin-top:28px}.strategy-flow article{display:flex;gap:13px}.strategy-flow article>span{width:38px;height:38px;flex:0 0 auto;display:grid;place-items:center;border:1px solid rgba(255,255,255,.1);border-radius:11px;color:#98a1ff;background:rgba(255,255,255,.06)}.strategy-flow strong{font-size:12px}.strategy-flow p{margin:5px 0 0;color:#a0a9c9;font-size:10px;line-height:1.65}.strategy-flow>i{display:block;width:1px;height:23px;margin:4px 0 4px 19px;background:rgba(255,255,255,.12)}.tip-card{padding:20px}.tip-card strong{font-size:12px}.tip-card p{margin:7px 0 0;color:#858da2;font-size:10px;line-height:1.75}@media(max-width:1050px){.generate-grid{grid-template-columns:1fr}}@media(max-width:600px){.configuration-card{padding:20px}.mode-grid,.form-row{grid-template-columns:1fr}}
</style>
