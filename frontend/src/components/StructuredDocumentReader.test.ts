import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import StructuredDocumentReader from './StructuredDocumentReader.vue'

describe('结构化教材阅读', () => {
  it('显示表格和文字但不执行文档 HTML，不加载远程图片', async () => {
    const wrapper = mount(StructuredDocumentReader, { props: { blocks: [
      { id: 'b1', kind: 'heading', text: '章节' },
      { id: 'b2', kind: 'paragraph', text: '<img src="https://evil.example" onerror="alert(1)"> (-1)^4' },
      { id: 'b3', kind: 'table', text: '', cells: [['温度', '-3℃']] },
      { id: 'b4', kind: 'image', text: '', image: 'https://evil.example/pixel' },
    ] } })
    await flushPromises()
    expect(wrapper.find('h2').text()).toBe('章节')
    expect(wrapper.find('table').text()).toContain('-3℃')
    expect(wrapper.text()).toContain('(-1)^4')
    expect(wrapper.findAll('img')).toHaveLength(0)
    expect(wrapper.findAll('script')).toHaveLength(0)
    wrapper.unmount()
  })
  it('只在内容显示后报告位置', async () => {
    const wrapper = mount(StructuredDocumentReader, { props: { blocks: [{ id: 'b77', kind: 'paragraph', text: '正文' }] } })
    await flushPromises()
    expect(wrapper.emitted('displayed')?.[0]).toEqual(['b77'])
    wrapper.unmount()
  })
})
