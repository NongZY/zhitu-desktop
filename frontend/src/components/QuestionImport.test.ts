import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ElementPlus from 'element-plus'
import QuestionImport from './QuestionImport.vue'
import { exampleQuestions } from '../utils/questionText'

const { upload } = vi.hoisted(() => ({ upload: vi.fn() }))
vi.mock('../api', () => ({ questionApi: { importFile: upload } }))
afterEach(() => { document.body.innerHTML = ''; vi.resetAllMocks() })

describe('空题库导入', () => {
  it('读取本地文件、预览后才保存，成功后跳到该题库', async () => {
    const view = mount(QuestionImport, { props: { books: [] }, attachTo: document.body, global: { plugins: [ElementPlus] } })
    try {
      await view.get('button').trigger('click')
      await flushPromises()
      const input = document.querySelector<HTMLInputElement>('input[type=file]')!
      Object.defineProperty(input, 'files', { value: [{ name: '练习.txt', size: 100, arrayBuffer: async () => new TextEncoder().encode(exampleQuestions).buffer }] })
      input.dispatchEvent(new Event('change', { bubbles: true }))
      await flushPromises()
      expect(document.body.textContent).toContain('共 2 道题')
      expect(upload).not.toHaveBeenCalled()
      upload.mockResolvedValue({ textbook_id: 4, imported: 2, skipped: 0 })
      Array.from(document.querySelectorAll('button')).find(b => b.textContent?.trim() === '确认导入')!.click()
      await flushPromises()
      expect(upload).toHaveBeenCalledWith(expect.arrayContaining([expect.objectContaining({ type: 'true_false', answer: false })]), undefined)
      expect(view.emitted('imported')).toEqual([[4]])
    } finally { view.unmount() }
  })
})
