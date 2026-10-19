import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import MathContent from '../components/MathContent.vue'
import { keyboardMath, mathParts } from './math'

describe('mathematical display preserves meaning', () => {
  it.each([
    ['(-1)^4', '(-1)^{4}'], ['-1^4', '-1^{4}'], ['2x^2', '2x^{2}'],
    ['sqrt(9)', '\\sqrt{9}'], ['(a+b)/c', '\\frac{(a+b)}{c}'],
    ['2*x', '2\\times x'], ['x_1', 'x_{1}'], ['x^(n+1)', 'x^{n+1}'],
    ['2(x+1)', '2(x+1)'], ['√9', '\\sqrt{9}'],
    ['√(x^2)', '\\sqrt{x^{2}}'], ['√(x)^2', '\\sqrt{x}^{2}'],
  ])('%s retains its operands', (input, expected) => expect(keyboardMath(input)).toBe(expected))
  it.each(['a/bc', '2^', '(-1)^4)', 'ordinary text', 'x++', '1.2.3',
    '1 1/2', '1 2 + 3', '2\t3*4', '√x^2', '√x_1'])('does not guess %s', input => {
    expect(keyboardMath(input)).toBeUndefined()
  })
  it.each(['1 1/2', '1 2 + 3', '√x^2'])('preserves ambiguous source %s in the view', input => {
    const text = `计算：${input}`
    const view = mount(MathContent, { props: { text } })
    expect(view.find('math').exists()).toBe(false)
    expect(view.text()).toBe(text)
  })
  it('renders mixed Chinese text, fractions and roots safely', () => {
    const view = mount(MathContent, { props: { text: '计算：(-1)^4，(a+b)/c，sqrt(9)。' } })
    expect(view.find('math msup').exists()).toBe(true)
    expect(view.find('math mfrac').exists()).toBe(true)
    expect(view.find('math msqrt').exists()).toBe(true)
    expect(view.text()).toContain('计算：')
  })
  it('leaves URLs, code and untrusted HTML inert', () => {
    const text = '<img src=x onerror=alert(1)> `2^3` https://example.org/a^2'
    const view = mount(MathContent, { props: { text } })
    expect(view.find('img').exists()).toBe(false)
    expect(view.text()).toContain('`2^3` https://example.org/a^2')
    expect(mathParts('\\(\\href{javascript:alert(1)}{x}\\)')[0]?.html).toBeUndefined()
  })
})
