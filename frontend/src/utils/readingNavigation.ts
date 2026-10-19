import type { Chapter, ReadingProgress } from '../api/types'

function positiveInteger(value: unknown): number | null {
  if (typeof value !== 'number' && (typeof value !== 'string' || !/^\d+$/.test(value))) return null
  const number = Number(value)
  return Number.isSafeInteger(number) && number > 0 ? number : null
}

export function resolveReadingTarget(input: {
  pageQuery?: unknown; chapterQuery?: unknown; chapters: Chapter[]; pageCount: number
  progress: ReadingProgress | null; documentRevision: string | null
}): { page: number | null; chapterId: number | null; notice: string | null } {
  const { pageCount, progress, documentRevision } = input
  if (pageCount < 1) return { page: null, chapterId: null, notice: null }
  const rows: { chapter: Chapter; depth: number; end: number }[] = []
  function visit(nodes: Chapter[], depth: number, parentEnd: number) {
    nodes.forEach((chapter, index) => {
      const nextStart = nodes.slice(index + 1).find(c => positiveInteger(c.page_start))?.page_start
      const end = chapter.page_end ?? (nextStart ? nextStart - 1 : parentEnd)
      rows.push({ chapter, depth, end })
      visit(chapter.children || [], depth + 1, end)
    })
  }
  visit(input.chapters, 0, pageCount)
  const validPage = (value: unknown) => { const p = positiveInteger(value); return p && p <= pageCount ? p : null }
  const explicitPage = validPage(input.pageQuery)
  const explicitChapter = rows.find(r => Number(r.chapter.id) === positiveInteger(input.chapterQuery))?.chapter
  const changed = !!progress && progress.document_revision !== documentRevision
  const page = explicitPage || validPage(explicitChapter?.page_start)
    || (!changed && validPage(progress?.page_number))
    || rows.map(r => validPage(r.chapter.page_start)).find(Boolean) || 1
  const covering = rows.filter(r => r.chapter.page_start && page >= r.chapter.page_start && page <= r.end)
    .sort((a, b) => b.depth - a.depth)[0]?.chapter
  const invalidQuery = input.pageQuery !== undefined && input.pageQuery !== null && !explicitPage
  return { page, chapterId: covering ? Number(covering.id) : null,
    notice: invalidQuery ? '这个页码不可用' : changed ? '教材已更新，请重新选择阅读位置' : null }
}
