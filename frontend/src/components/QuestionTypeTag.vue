<script setup lang="ts">
import { computed } from 'vue'
import type { QuestionType } from '../api'

const props = defineProps<{ type: QuestionType }>()
const labels: Record<QuestionType, string> = {
  single_choice: '单选题',
  multiple_choice: '多选题',
  fill_blank: '填空题',
  true_false: '判断题',
  short_answer: '简答题',
}
const label = computed(() => labels[props.type] ?? props.type)
</script>

<template>
  <el-tag effect="plain" round>{{ label }}</el-tag>
</template>
