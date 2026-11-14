import type { QuestionPayload, QuestionType } from '../api/types'

const names: Record<string, QuestionType> = {
  单选: 'single_choice', 多选: 'multiple_choice', 判断: 'true_false', 填空: 'fill_blank', 简答: 'short_answer',
}

export const exampleQuestions = `【单选题】下列哪个数是偶数？
A. 3
B. 4
答案：B
解析：4 可以被 2 整除。

【判断题】0 是正数。
答案：错`

export function parseQuestions(text: string): QuestionPayload[] {
  const lines = text.replace(/^\uFEFF/, '').split(/\r?\n/)
  const rows: QuestionPayload[] = []
  let current: QuestionPayload | undefined
  let field: 'stem' | 'answer' | 'analysis' | 'option' = 'stem'
  let start = 0
  let answer = ''
  function finish() {
    if (!current) return
    const fail = (message: string): never => { throw new Error('第 ' + start + ' 行的题目：' + message) }
    if (!current.stem.trim()) fail('请填写题干。')
    if (!answer.trim()) fail('请用“答案：”写出答案。')
    const t = current.type
    if (t === 'true_false') {
      if (/^(正确|是|对|真|true|√|✓|1)$/i.test(answer)) current.answer = true
      else if (/^(错误|否|错|假|false|×|✗|0)$/i.test(answer)) current.answer = false
      else fail('判断题答案请写“对”或“错”。')
    } else if (t === 'single_choice' || t === 'multiple_choice') {
      const keys = (current.options || []).map(o => o.key)
      if (keys.length < 2 || keys.length > 8 || new Set(keys).size !== keys.length) fail('请填写 2 到 8 个编号不同的选项。')
      const selected = answer.toUpperCase().replace(/[\s,，、]+/g, '').split('')
      if (selected.some(k => !keys.includes(k)) || new Set(selected).size !== selected.length || (t === 'single_choice' && selected.length !== 1)) fail('答案编号与选项不匹配。')
      current.answer = t === 'single_choice' ? selected[0] : selected
    } else current.answer = answer
    rows.push(current)
    if (rows.length > 500) fail('每次最多导入 500 道题。')
  }
  for (const [index, raw] of lines.entries()) {
    const line = raw.trim()
    if (!line) continue
    const head = /^(?:\d+\s*[.、．)]\s*)?(?:【(单选|多选|判断|填空|简答)题?】|\[(单选|多选|判断|填空|简答)题?\]|(单选|多选|判断|填空|简答)题?\s*[:：])\s*(.*)$/.exec(line)
    if (head) {
      finish()
      current = { type: names[head[1] || head[2] || head[3]], stem: head[4], difficulty: 2, status: 'approved' }
      start = index + 1
      field = 'stem'
      answer = ''
      continue
    }
    if (!current) throw new Error('第 ' + (index + 1) + ' 行：请在每道题前写明题型，例如【单选题】。')
    const label = /^(?:参考|标准)?(答案|解析)\s*[:：]\s*(.*)$/.exec(line)
    const option = /^([A-Ha-h])\s*[.．、:：)）]\s*(.+)$/.exec(line)
    if (label) {
      field = label[1] === '答案' ? 'answer' : 'analysis'
      if (field === 'answer') answer = label[2]
      else current.analysis = label[2]
    } else if (option && (field === 'stem' || field === 'option') && ['single_choice','multiple_choice'].includes(current.type)) {
      ;(current.options ??= []).push({key: option[1].toUpperCase(), text: option[2]})
      field = 'option'
    } else if (field === 'stem') current.stem = [current.stem, line].filter(Boolean).join('\n')
    else if (field === 'answer') answer = [answer, line].filter(Boolean).join('\n')
    else if (field === 'analysis') current.analysis = [current.analysis, line].filter(Boolean).join('\n')
    else if (current.options?.length) current.options[current.options.length - 1].text += '\n' + line
  }
  finish()
  return rows
}
