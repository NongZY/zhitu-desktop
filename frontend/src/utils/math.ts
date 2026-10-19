import katex from 'katex'

export interface MathPart { text: string; html?: string }

/** Parse the small keyboard notation used by our exercises, never evaluate it.
 * Unknown words, unbalanced expressions and ambiguous slash products fall back.
 */
export function keyboardMath(source: string): string | undefined {
  const input = source.trim().replaceAll('−', '-').replaceAll('×', '*').replaceAll('÷', '/')
  if (!input || input.length > 500 || !/(?:[\^_*/=+\-√]|sqrt\()/.test(input)) return
  if (/[a-zA-Z]{3,}/.test(input.replaceAll('sqrt', ''))) return
  const tokens = input.match(/sqrt|\d+(?:\.\d+)?|[a-zA-Z]|[()+\-*/^_=√]/g) || []
  if (tokens.join('') !== input.replace(/\s/g, '')) return
  // Whitespace-separated numbers may be a mixed fraction or damaged OCR.
  // Never join "1 1/2" into "11/2" through implicit multiplication.
  if (tokens.some((token, i) => i > 0 && /^\d/.test(token) && /^\d/.test(tokens[i - 1]!))) return
  let index = 0
  const peek = () => tokens[index]
  const consume = () => tokens[index++]!
  const atomStart = (token?: string) => !!token && /^(?:\d|[a-zA-Z]|\(|√)/.test(token)
  function atom(): string {
    const token = consume()
    if (token === '(') {
      const inside = sum()
      if (consume() !== ')') throw new Error('parenthesis')
      return `(${inside})`
    }
    if (token === 'sqrt' || token === '√') {
      const grouped = peek() === '('
      const value = atom()
      // Without parentheses, the original root bar's extent is unknown.
      if (!grouped && (peek() === '^' || peek() === '_')) throw new Error('ambiguous root extent')
      return `\\sqrt{${value.startsWith('(') ? value.slice(1, -1) : value}}`
    }
    if (!token || !/^(?:\d+(?:\.\d+)?|[a-zA-Z])$/.test(token)) throw new Error('atom')
    return token
  }
  function power(): string {
    let value = atom()
    if (peek() === '_') { consume(); value += `_{${atom()}}` }
    if (peek() === '^') {
      consume()
      let exponent = unary()
      if (exponent.startsWith('(') && exponent.endsWith(')')) exponent = exponent.slice(1, -1)
      value += `^{${exponent}}`
    }
    return value
  }
  function unary(): string {
    if (peek() === '+' || peek() === '-') return consume() + unary()
    return power()
  }
  function product(): string {
    let value = unary()
    let slash = false
    while (peek() === '*' || peek() === '/' || atomStart(peek())) {
      const explicit = peek() === '*' || peek() === '/'
      const operator = explicit ? consume() : ''
      if (!explicit && slash) throw new Error('ambiguous slash product')
      const next = unary()
      value = operator === '/' ? `\\frac{${value}}{${next}}`
        : value + (operator === '*' ? '\\times ' : '') + next
      slash = operator === '/'
    }
    return value
  }
  function sum(): string {
    let value = product()
    while (peek() === '+' || peek() === '-') value += consume() + product()
    return value
  }
  try {
    let latex = sum()
    if (peek() === '=') { consume(); latex += '=' + sum() }
    return index === tokens.length ? latex : undefined
  } catch { return undefined }
}

function render(text: string, latex: string, displayMode = false): MathPart {
  // Explicitly disable links, images and HTML extensions; no shared macro state.
  if (latex.length > 2000 || /\\(?:href|url|includegraphics|html\w*|def|gdef|newcommand)\b/.test(latex)) return { text }
  try {
    return { text, html: katex.renderToString(latex, {
      displayMode, output: 'htmlAndMathml', throwOnError: true,
      trust: false, strict: 'error', maxSize: 10, maxExpand: 200, macros: {},
    }) }
  } catch { return { text } }
}

function legacyParts(text: string): MathPart[] {
  const result: MathPart[] = []
  // The whole candidate must parse. Never convert just a substring of a malformed formula.
  const pattern = /[A-Za-z0-9()+\-−×÷*/^_=√. \t]+/g
  let end = 0
  for (const match of text.matchAll(pattern)) {
    const start = match.index!
    if (start > end) result.push({ text: text.slice(end, start) })
    const raw = match[0]
    const leading = raw.match(/^\s*/)?.[0] || ''
    const trailing = raw.match(/\s*$/)?.[0] || ''
    const latex = keyboardMath(raw)
    if (latex) {
      if (leading) result.push({ text: leading })
      result.push(render(raw.trim(), latex))
      if (trailing) result.push({ text: trailing })
    } else result.push({ text: raw })
    end = start + raw.length
  }
  if (end < text.length) result.push({ text: text.slice(end) })
  return result
}

export function mathParts(text: string): MathPart[] {
  // A linear scan protects URL/code runs and recognises explicit math delimiters.
  const pattern = /```[\s\S]*?```|`[^`\n]*`|https?:\/\/[^\s]+|\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\]|\$\$[\s\S]*?\$\$|\$[^$\n]+\$/g
  const result: MathPart[] = []
  let end = 0
  for (const match of text.matchAll(pattern)) {
    result.push(...legacyParts(text.slice(end, match.index)))
    const raw = match[0]
    if (raw.startsWith('`') || /^https?:/.test(raw)) result.push({ text: raw })
    else {
      const block = raw.startsWith('$$') || raw.startsWith('\\[')
      const margin = raw.startsWith('\\') || raw.startsWith('$$') ? 2 : 1
      result.push(render(raw, raw.slice(margin, -margin), block))
    }
    end = match.index! + raw.length
  }
  result.push(...legacyParts(text.slice(end)))
  return result
}
