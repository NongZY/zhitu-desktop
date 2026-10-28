<script setup lang="ts">
import { computed } from 'vue'
import type { CandidateQuestion } from '../api/practice'
const draft = defineModel<CandidateQuestion>({ required: true })
defineProps<{ disabled?: boolean }>()
const textAnswer = computed({
  get: () => Array.isArray(draft.value.correct_answer) ? draft.value.correct_answer.join('\n') : String(draft.value.correct_answer),
  set: (value: string) => { draft.value.correct_answer = draft.value.question_type === 'fill_blank' ? value.split('\n').map(s => s.trim()).filter(Boolean) : value },
})
</script>
<template>
  <fieldset :disabled="disabled" class="candidate-editor">
    <label>题目<textarea v-model="draft.stem" rows="3" maxlength="3000" /></label>
    <label v-for="option in draft.options || []" :key="option.key">选项 {{ option.key }}<input v-model="option.text" maxlength="2000"></label>
    <label v-if="draft.question_type === 'single_choice'">正确选项<select v-model="draft.correct_answer"><option v-for="option in draft.options || []" :key="option.key" :value="option.key">{{ option.key }} · {{ option.text }}</option></select></label>
    <div v-else-if="draft.question_type === 'multiple_choice'"><p>正确选项（可多选）</p><label v-for="option in draft.options || []" :key="option.key" class="inline"><input v-model="draft.correct_answer" type="checkbox" :value="option.key">{{ option.key }}</label></div>
    <label v-else-if="draft.question_type === 'true_false'">正确答案<select v-model="draft.correct_answer"><option :value="true">正确</option><option :value="false">错误</option></select></label>
    <label v-else>{{ draft.question_type === 'fill_blank' ? '答案（按顺序，每空一行）' : '参考答案' }}<textarea v-model="textAnswer" rows="3" maxlength="10000" /></label>
    <label>讲解<textarea v-model="draft.explanation" rows="2" maxlength="8000" /></label>
    <label>难度（1 最容易，5 最难）<input v-model.number="draft.difficulty" type="number" min="1" max="5"></label>
  </fieldset>
</template>
<style scoped>
.candidate-editor{padding:0;border:0}label{display:grid;gap:6px;margin:12px 0;font-size:14px}input:not([type=checkbox]),select,textarea{width:100%;padding:9px 11px;border:1px solid #cfd5e1;border-radius:7px;font:inherit;background:#fff;color:#27344b}textarea{resize:vertical}.inline{display:inline-flex;gap:6px;margin-right:18px}fieldset:disabled{opacity:.7}
</style>
