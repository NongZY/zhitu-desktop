export function toPercent(value: number | null | undefined): number {
  if (!Number.isFinite(value)) return 0
  const normalized = Number(value) <= 1 ? Number(value) * 100 : Number(value)
  return Math.max(0, Math.min(100, Math.round(normalized)))
}

export function masteryLevel(value: number): 'weak' | 'learning' | 'mastered' {
  const percentage = toPercent(value)
  if (percentage >= 80) return 'mastered'
  if (percentage >= 50) return 'learning'
  return 'weak'
}

export function formatDuration(seconds: number | null | undefined): string {
  const safe = Math.max(0, Math.floor(Number(seconds) || 0))
  const minutes = Math.floor(safe / 60)
  const rest = safe % 60
  return `${minutes}:${String(rest).padStart(2, '0')}`
}
