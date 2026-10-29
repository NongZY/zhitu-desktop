<script setup lang="ts">
import MathContent from '../components/MathContent.vue'
import QuestionTypeTag from '../components/QuestionTypeTag.vue'
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Check, Clock, FullScreen, Loading, Warning } from '@element-plus/icons-vue'
import { examApi, type ExamPaper, type ExamResult, type QuestionOption } from '../api'
import { getApiErrorMessage } from '../api/http'
import { formatDuration } from '../utils/learning'
import { registerCloseGuard, type CloseDecision, type CloseControl } from '../runtime/close'

const route = useRoute()
const router = useRouter()
const paper = ref<ExamPaper>()
const result = ref<ExamResult>()
const loading = ref(true)
const submitting = ref(false)
const error = ref('')
const currentIndex = ref(0)
const remaining = ref(0)
const startedAt = ref(Date.now())
const answers = reactive<Record<string, string | string[] | boolean | null>>({})
let timer: number | undefined
async function prepareLeave(control?: CloseControl): Promise<CloseDecision> {
  if (!paper.value || result.value) return 'ready'
  if (submitting.value) { ElMessage.warning('正在提交，请稍等后再离开'); return 'stay' }
  const ask = async (): Promise<CloseDecision> => {
    try {
      await ElMessageBox.confirm('这次练习尚未提交，当前作答不会保存。要放弃并离开吗？', '练习尚未完成', { confirmButtonText: '放弃作答并离开', cancelButtonText: '继续练习', type: 'warning' })
      return 'discard'
    } catch { return 'stay' }
  }
  return control ? control.confirm(ask, () => ElMessageBox.close()) : ask()
}
const unregisterClose = registerCloseGuard(prepareLeave)
onBeforeRouteLeave(async () => (await prepareLeave()) !== 'stay')
onBeforeUnmount(unregisterClose)

const currentQuestion = computed(() => paper.value?.questions[currentIndex.value])
const answeredCount = computed(() => Object.values(answers).filter((value) => Array.isArray(value) ? value.length : value !== null && value !== '').length)
const progress = computed(() => paper.value?.questions.length ? Math.round(answeredCount.value / paper.value.questions.length * 100) : 0)
const gradedTotal = computed(() => result.value?.graded_total_score ?? result.value?.total_score ?? 0)
const pendingCount = computed(() => result.value?.pending_count ?? result.value?.details?.filter(item => item.is_correct === null).length ?? 0)
const resultRate = computed(() => gradedTotal.value > 0 ? Math.round((result.value?.score || 0) / gradedTotal.value * 100) : 0)

function answerText(value: unknown): string {
  if (value == null || value === '' || (Array.isArray(value) && !value.length)) return '未作答'
  if (typeof value === 'boolean') return value ? '正确' : '错误'
  return Array.isArray(value) ? value.map(String).join('、') : String(value)
}

function optionsOf(options: ExamPaper['questions'][number]['options']): QuestionOption[] {
  if (!options) return []
  if (Array.isArray(options)) return options.map((item, index) => typeof item === 'string' ? { key: String.fromCharCode(65 + index), text: item } : item)
  return Object.entries(options).map(([key, text]) => ({ key, text: String(text) }))
}

function answerKey(id: string | number) { return String(id) }
function selectQuestion(index: number) { currentIndex.value = index }

async function load() {
  loading.value = true
  try {
    paper.value = await examApi.get(String(route.params.id))
    remaining.value = paper.value.duration_minutes * 60
    startedAt.value = Date.now()
    paper.value.questions.forEach((question) => {
      answers[answerKey(question.id)] = question.type === 'multiple_choice' ? [] : null
    })
    timer = window.setInterval(() => {
      remaining.value = Math.max(0, remaining.value - 1)
      if (remaining.value === 0) {
        window.clearInterval(timer)
        void submit(true)
      }
    }, 1000)
  } catch (err) {
    error.value = getApiErrorMessage(err, '练习加载失败')
  } finally {
    loading.value = false
  }
}

async function submit(auto = false) {
  if (!paper.value || result.value || submitting.value) return
  if (!auto) {
    try {
      await ElMessageBox.confirm(`已完成 ${answeredCount.value}/${paper.value.questions.length} 题，确定交卷吗？`, '确认交卷', { type: answeredCount.value < paper.value.questions.length ? 'warning' : 'info', confirmButtonText: '确认交卷' })
    } catch { return }
  }
  submitting.value = true
  try {
    const elapsed = Math.max(0, Math.round((Date.now() - startedAt.value) / 1000))
    result.value = await examApi.submit(paper.value.id, {
      duration_seconds: elapsed,
      answers: paper.value.questions.map((question) => ({ question_id: question.id, answer: answers[answerKey(question.id)] })),
    })
    if (timer) window.clearInterval(timer)
    if (document.fullscreenElement) await document.exitFullscreen().catch(() => undefined)
    ElMessage.success(auto ? '练习时间到，系统已自动提交' : '练习已完成')
  } catch (err) {
    ElMessage.error(getApiErrorMessage(err, '交卷失败，请稍后重试'))
  } finally {
    submitting.value = false
  }
}

async function toggleFullscreen() {
  if (!document.fullscreenElement) await document.documentElement.requestFullscreen().catch(() => ElMessage.info('浏览器未允许全屏'))
  else await document.exitFullscreen()
}

function resultFor(questionId: string | number) {
  return result.value?.details?.find((item) => String(item.question_id) === String(questionId))
}

onMounted(load)
onBeforeUnmount(() => { if (timer) window.clearInterval(timer) })
</script>

<template>
  <main class="exam-screen">
    <header class="exam-header">
      <button class="exam-brand" type="button" @click="router.push('/dashboard')"><span>知途</span><small>专注练习</small></button>
      <div v-if="paper" class="exam-title"><strong>{{ paper.title }}</strong><small>{{ paper.questions.length }} 题 · 共 {{ paper.total_score }} 分</small></div>
      <div class="exam-tools"><button type="button" @click="toggleFullscreen"><el-icon><FullScreen /></el-icon><span>全屏</span></button><div class="countdown" :class="{ urgent: remaining < 300 }"><el-icon><Clock /></el-icon><span>{{ formatDuration(remaining) }}</span></div><el-button v-if="paper && !result" type="primary" :loading="submitting" @click="submit(false)">完成练习</el-button></div>
    </header>

    <section v-if="loading" class="exam-loading"><el-icon class="is-loading"><Loading /></el-icon><p>正在准备练习…</p></section>
    <section v-else-if="error" class="exam-loading"><el-icon><Warning /></el-icon><h2>无法打开练习</h2><p>{{ error }}</p><el-button @click="router.push('/exam/generate')">返回练习设置</el-button></section>

    <template v-else-if="paper && !result">
      <div class="exam-progress"><div :style="{ width: `${progress}%` }"></div></div>
      <div class="exam-layout">
        <aside class="answer-sheet">
          <div class="sheet-heading"><strong>答题卡</strong><span>{{ answeredCount }}/{{ paper.questions.length }}</span></div>
          <div class="sheet-grid"><button v-for="(question, index) in paper.questions" :key="question.id" type="button" :class="{ active: currentIndex === index, answered: answers[answerKey(question.id)] !== null && answers[answerKey(question.id)] !== '' && (!Array.isArray(answers[answerKey(question.id)]) || (answers[answerKey(question.id)] as string[]).length) }" @click="selectQuestion(index)">{{ index + 1 }}</button></div>
          <div class="sheet-legend"><span><i class="answered"></i>已答</span><span><i></i>未答</span></div>
        </aside>

        <section v-if="currentQuestion" class="question-stage">
          <div class="question-card">
            <div class="question-meta"><span>第 {{ currentIndex + 1 }} 题</span><QuestionTypeTag :type="currentQuestion.type" /><el-tag effect="plain">{{ currentQuestion.type === 'short_answer' ? '提交后自行核对' : `${currentQuestion.score} 分` }}</el-tag><el-rate :model-value="currentQuestion.difficulty" disabled /></div>
            <h1><MathContent :text="currentQuestion.stem" /></h1>
            <el-radio-group v-if="currentQuestion.type === 'single_choice'" v-model="answers[answerKey(currentQuestion.id)]" class="choice-list">
              <el-radio v-for="option in optionsOf(currentQuestion.options)" :key="option.key" :value="option.key" border><strong>{{ option.key }}</strong><span><MathContent :text="option.text" /></span></el-radio>
            </el-radio-group>
            <el-checkbox-group v-else-if="currentQuestion.type === 'multiple_choice'" v-model="answers[answerKey(currentQuestion.id)] as string[]" class="choice-list">
              <el-checkbox v-for="option in optionsOf(currentQuestion.options)" :key="option.key" :value="option.key" border><strong>{{ option.key }}</strong><span><MathContent :text="option.text" /></span></el-checkbox>
            </el-checkbox-group>
            <el-radio-group v-else-if="currentQuestion.type === 'true_false'" v-model="answers[answerKey(currentQuestion.id)]" class="judge-list"><el-radio :value="true" border>正确</el-radio><el-radio :value="false" border>错误</el-radio></el-radio-group>
            <div v-else-if="currentQuestion.type === 'fill_blank'"><p>按题目中的顺序作答，每空一行。</p><el-input v-model="answers[answerKey(currentQuestion.id)] as string" type="textarea" :rows="3" placeholder="请输入答案，每空一行" /></div>
            <el-input v-else v-model="answers[answerKey(currentQuestion.id)] as string" type="textarea" :rows="8" placeholder="请写出解题过程与答案，提交后可结合参考答案自行核对" />
          </div>
          <div class="question-nav"><el-button :disabled="currentIndex === 0" @click="currentIndex--"><el-icon><ArrowLeft /></el-icon>上一题</el-button><el-button v-if="currentIndex < paper.questions.length - 1" type="primary" @click="currentIndex++">下一题</el-button><el-button v-else type="success" @click="submit(false)">完成练习</el-button></div>
        </section>
      </div>
    </template>

    <section v-else-if="paper && result" class="result-page">
      <div class="result-hero"><span class="result-check"><el-icon><Check /></el-icon></span><p class="eyebrow">EXAM COMPLETED</p><h1 v-if="gradedTotal > 0">客观题得分 {{ result.score }} / {{ gradedTotal }}</h1><h1 v-else>练习已提交</h1><p v-if="gradedTotal > 0">客观题已评分，掌握度和错题本已同步更新。</p><p v-if="pendingCount">{{ pendingCount }} 道简答题请结合参考答案自行核对，不计入客观题得分率，也不会直接判错。</p><div v-if="gradedTotal > 0" class="score-ring" :style="{ '--score': `${resultRate * 3.6}deg` }"><strong>{{ resultRate }}%</strong><small>客观题得分率</small></div><div class="result-stats"><div><strong>{{ result.correct_count }}</strong><small>答对</small></div><div><strong>{{ result.wrong_count }}</strong><small>答错</small></div><div><strong>{{ formatDuration(result.duration_seconds) }}</strong><small>用时</small></div></div></div>
      <div class="result-details surface-card"><div class="section-title"><div><h2>答题解析</h2><p>逐题核对答案与参考解析</p></div></div><article v-for="(question, index) in paper.questions" :key="question.id" class="result-item" :class="{ correct: resultFor(question.id)?.is_correct, manual: resultFor(question.id)?.is_correct == null }"><span>{{ index + 1 }}</span><div><h3><MathContent :text="question.stem" /></h3><p v-for="option in optionsOf(question.options)" :key="option.key">{{ option.key }}. <MathContent :text="option.text" /></p><p>你的答案：<MathContent :text="answerText(resultFor(question.id)?.user_answer)" /></p><p>参考答案：<MathContent :text="resultFor(question.id)?.correct_answer == null ? '暂无参考答案' : answerText(resultFor(question.id)?.correct_answer)" /></p><small><MathContent :text="resultFor(question.id)?.explanation || '暂无解析'" /></small></div><el-tag :type="resultFor(question.id)?.is_correct ? 'success' : resultFor(question.id)?.is_correct == null ? 'info' : 'danger'">{{ resultFor(question.id)?.is_correct ? '正确' : resultFor(question.id)?.is_correct == null ? '自行核对' : '错误' }}</el-tag></article></div>
      <div class="result-actions"><el-button @click="router.push(result.id ? `/results/${result.id}` : '/results')">查看学习记录</el-button><el-button type="primary" @click="router.push('/exam/generate')">再练一组</el-button></div>
    </section>
  </main>
</template>

<style scoped>
.exam-screen{min-height:100vh;background:#f4f6fb}.exam-header{height:72px;padding:0 28px;display:grid;grid-template-columns:1fr auto 1fr;align-items:center;border-bottom:1px solid #e6e9f1;background:#fff}.exam-brand{border:0;background:none;text-align:left;cursor:pointer}.exam-brand span{font-size:18px;font-weight:700;color:#3f4bc6}.exam-brand small{margin-left:10px;color:#8d95a9}.exam-title{text-align:center;display:flex;flex-direction:column;gap:3px}.exam-title strong{font-size:14px}.exam-title small{color:#9299aa;font-size:9px}.exam-tools{justify-self:end;display:flex;align-items:center;gap:12px}.exam-tools>button:not(.el-button){height:36px;padding:0 10px;display:flex;align-items:center;gap:6px;border:0;background:none;color:#6d758b;cursor:pointer}.countdown{height:38px;padding:0 13px;display:flex;align-items:center;gap:7px;border-radius:10px;color:#44506f;background:#f2f4f9;font:700 13px 'Plus Jakarta Sans'}.countdown.urgent{color:#d94d5d;background:#fff0f2}.exam-progress{height:3px;background:#e9ecf4}.exam-progress div{height:100%;background:linear-gradient(90deg,#5d68dd,#27baa8);transition:width .25s}.exam-loading{min-height:calc(100vh - 72px);display:flex;flex-direction:column;align-items:center;justify-content:center;color:#828aa0}.exam-loading>.el-icon{font-size:36px;color:#626edc}.exam-layout{width:min(1380px,100%);margin:0 auto;padding:28px;display:grid;grid-template-columns:250px minmax(0,1fr);gap:24px}.answer-sheet{align-self:start;padding:20px;border:1px solid #e4e7ef;border-radius:16px;background:#fff}.sheet-heading{display:flex;justify-content:space-between;margin-bottom:16px}.sheet-heading strong{font-size:14px}.sheet-heading span{color:#6872da;font-size:11px}.sheet-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}.sheet-grid button{aspect-ratio:1;border:1px solid #dfe3ed;border-radius:8px;background:#fff;color:#7a8296;font-size:11px;cursor:pointer}.sheet-grid button.answered{color:#fff;border-color:#24af9d;background:#24af9d}.sheet-grid button.active{box-shadow:0 0 0 3px rgba(86,99,216,.18);border-color:#5966d8}.sheet-legend{margin-top:18px;display:flex;gap:16px;color:#9299aa;font-size:9px}.sheet-legend span{display:flex;align-items:center;gap:5px}.sheet-legend i{width:8px;height:8px;border:1px solid #dfe3ed;border-radius:2px}.sheet-legend i.answered{border-color:#24af9d;background:#24af9d}.question-stage{min-width:0}.question-card{min-height:500px;padding:34px 40px;border:1px solid #e3e6ef;border-radius:18px;background:#fff;box-shadow:var(--shadow-sm)}.question-meta{display:flex;align-items:center;gap:12px;color:#6470da;font-size:11px;font-weight:600}.question-meta .el-rate{margin-left:auto;--el-rate-icon-size:14px}.question-card h1{margin:29px 0 32px;font-size:19px;line-height:1.8}.choice-list{width:100%;display:grid;gap:13px}.choice-list .el-radio,.choice-list .el-checkbox{width:100%;height:auto;min-height:54px;margin:0;padding:13px 16px;border-radius:11px}.choice-list strong{width:25px;height:25px;margin-right:10px;display:inline-grid;place-items:center;border-radius:7px;background:#f0f2f8}.choice-list span{white-space:normal}.judge-list{display:flex;gap:15px}.judge-list .el-radio{min-width:150px;height:52px;margin:0;border-radius:11px}.question-nav{margin-top:16px;display:flex;justify-content:space-between}.question-nav .el-button:last-child{margin-left:auto}.result-page{width:min(980px,100%);margin:0 auto;padding:42px 24px 60px}.result-hero{text-align:center}.result-check{width:54px;height:54px;margin:0 auto 13px;display:grid;place-items:center;border-radius:17px;color:#fff;background:#25b19f;font-size:25px}.result-hero h1{margin-bottom:8px;font-size:28px}.result-hero>p:not(.eyebrow){color:#81899d;font-size:12px}.score-ring{width:142px;height:142px;margin:25px auto;display:flex;flex-direction:column;align-items:center;justify-content:center;border-radius:50%;background:radial-gradient(circle closest-side,#f4f6fb 81%,transparent 82%),conic-gradient(#5663d8 var(--score),#e5e8f1 0)}.score-ring strong{font:700 27px 'Plus Jakarta Sans'}.score-ring small{color:#9299aa;font-size:9px}.result-stats{width:min(440px,100%);margin:0 auto 26px;padding:15px;display:grid;grid-template-columns:repeat(3,1fr);border-radius:14px;background:#fff}.result-stats div{display:flex;flex-direction:column;border-right:1px solid #edf0f5}.result-stats div:last-child{border:0}.result-stats small{margin-top:3px;color:#979eaf;font-size:9px}.result-details{padding:24px}.result-item{padding:17px 0;display:grid;grid-template-columns:32px 1fr auto;gap:13px;border-top:1px solid #edf0f5}.result-item>span{width:30px;height:30px;display:grid;place-items:center;border-radius:9px;color:#dc5968;background:#fff0f2;font-size:10px}.result-item.correct>span{color:#159d8c;background:#e9faf6}.result-item.manual>span{color:#7e869a;background:#f1f3f7}.result-item h3{margin:0 0 7px;font-size:12px}.result-item p{margin:3px 0;color:#737c92;font-size:10px}.result-item small{display:block;margin-top:7px;color:#9299aa;line-height:1.6}.result-actions{margin-top:18px;display:flex;justify-content:center;gap:10px}@media(max-width:800px){.exam-header{padding:0 14px;grid-template-columns:1fr auto}.exam-title{display:none}.exam-tools>button span{display:none}.exam-layout{padding:16px;grid-template-columns:1fr}.answer-sheet{order:2}.question-card{min-height:420px;padding:24px}.sheet-grid{grid-template-columns:repeat(8,1fr)}}@media(max-width:520px){.exam-brand small,.exam-tools>button:not(.el-button){display:none}.exam-header{height:64px}.exam-layout{padding:10px}.question-card{padding:20px 17px}.question-card h1{font-size:16px}.sheet-grid{grid-template-columns:repeat(6,1fr)}}
</style>
