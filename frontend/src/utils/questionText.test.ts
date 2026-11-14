import { describe, expect, it } from 'vitest'
import { parseQuestions, exampleQuestions } from './questionText'

describe('独立题目文本导入', () => {
  it('解析五种题型，保留多行题干、中文答案和判断假值', () => {
    const text = exampleQuestions + '\n【多选题】选偶数\nA. 4\nB. 2\n答案：A、B\n简答：为什么？\n答案：第一行\n第二行\n1. 【填空题】2+2=___\n答案：4'
    const rows = parseQuestions('\uFEFF' + text.replaceAll('\n', '\r\n'))
    expect(rows.map(r => r.answer)).toEqual(['B', false, ['A', 'B'], '第一行\n第二行', '4'])
    expect(rows[0].analysis).toContain('整除')
  })
  it('提供缺少答案或选项编号错误的行号', () => {
    expect(() => parseQuestions('【判断题】太阳是恒星。')).toThrow('第 1 行')
    expect(() => parseQuestions(exampleQuestions.replace('答案：B', '答案：C'))).toThrow('不匹配')
    expect(() => parseQuestions('没有题型')).toThrow('第 1 行')
  })
})
