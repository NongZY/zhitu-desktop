import { describe, expect, it } from 'vitest'
import { resolveReadingTarget } from './readingNavigation'

const chapters = [
  { id: 1, title: '第一章', page_start: 4, page_end: 19, children: [{ id: 2, title: '小节', page_start: 8, page_end: 10 }] },
  { id: 3, title: '第二章', page_start: 20, page_end: 30 },
]
const progress = { textbook_id: 1, page_number: 15, chapter_id: 1, document_revision: 'v1', revision: 2, updated_at: '2026-10-15T00:00:00Z' }
const base = { chapters, pageCount: 30, progress, documentRevision: 'v1' }
describe('阅读导航优先级', () => {
  it('显式页优先于章节和已存页，并选择最深覆盖章节', () => {
    expect(resolveReadingTarget({ ...base, pageQuery: '9', chapterQuery: '3' })).toEqual({ page: 9, chapterId: 2, notice: null })
    expect(resolveReadingTarget({ ...base, chapterQuery: '3' }).page).toBe(20)
    expect(resolveReadingTarget(base).page).toBe(15)
  })
  it.each(['0', '-1', '31', '1.2', 'abc', ['9'], true])('非法 URL %s 提示并回退而不是裁剪', (pageQuery) => {
    expect(resolveReadingTarget({ ...base, pageQuery })).toMatchObject({ page: 15, notice: '这个页码不可用' })
  })
  it('无目录、空文件、旧版本有确定的回退', () => {
    expect(resolveReadingTarget({ ...base, progress: null, chapters: [] }).page).toBe(1)
    expect(resolveReadingTarget({ ...base, pageCount: 0 }).page).toBeNull()
    expect(resolveReadingTarget({ ...base, documentRevision: 'v2' })).toMatchObject({ page: 4, notice: '教材已更新，请重新选择阅读位置' })
  })
})
