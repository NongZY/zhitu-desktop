import { describe, expect, it } from 'vitest'
import { formatDuration, masteryLevel, toPercent } from './learning'

describe('learning display helpers', () => {
  it('normalizes ratio and percentage mastery values', () => {
    expect(toPercent(0.82)).toBe(82)
    expect(toPercent(82)).toBe(82)
    expect(toPercent(2)).toBe(2)
  })

  it('classifies mastery boundaries', () => {
    expect(masteryLevel(0.49)).toBe('weak')
    expect(masteryLevel(0.5)).toBe('learning')
    expect(masteryLevel(0.8)).toBe('mastered')
  })

  it('formats seconds without leaking invalid values', () => {
    expect(formatDuration(125)).toBe('2:05')
    expect(formatDuration(undefined)).toBe('0:00')
  })
})
