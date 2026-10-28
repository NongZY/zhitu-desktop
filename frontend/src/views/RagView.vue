<script setup lang="ts">
import MathContent from '../components/MathContent.vue'
import { nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { documentLink } from '../api/documents'
import { ChatDotRound, Document, Promotion, Reading, RefreshLeft } from '@element-plus/icons-vue'
import PageHeader from '../components/PageHeader.vue'
import { ragApi, textbookApi, type Citation, type Textbook } from '../api'
import { getApiErrorMessage } from '../api/http'
import { desktopSettings, type AISettings } from '../api/desktopSettings'

interface ChatMessage { role: 'user' | 'assistant'; content: string; citations?: Citation[]; error?: boolean; mode?: string; notice?: string }

const route = useRoute()
const router = useRouter()
function openCitation(citation: Citation) {
  if (!citation.textbook_id) return
  void router.push(citation.locator ? documentLink(citation.textbook_id, citation.locator) : `/textbooks/${citation.textbook_id}${citation.page ? `?page=${citation.page}` : ''}`)
}
const books = ref<Textbook[]>([])
const textbookId = ref<string | number>()
const useAI = ref(false), ai = ref<AISettings | null>(null)
watch(textbookId, () => { useAI.value = false })
const chapterId = ref<string | number>()
const chapterTitle = ref('')
const question = ref('')
const sending = ref(false)
const messages = ref<ChatMessage[]>([])
const conversation = ref<HTMLElement>()
const suggestions = ['请总结本章的核心知识点', '这个概念在教材中是如何定义的？', '给我解释一个教材中的典型例题']

async function send(preset?: string) {
  const content = (preset || question.value).trim()
  if (!content || sending.value) return
  messages.value.push({ role: 'user', content })
  question.value = ''
  sending.value = true
  await scrollBottom()
  try {
    const answer = await ragApi.ask({ question: content, textbook_id: textbookId.value, chapter_id: chapterId.value, top_k: 5, use_ai: useAI.value })
    messages.value.push({ role: 'assistant', content: answer.answer, citations: answer.citations, mode: answer.mode, notice: answer.notice })
  } catch (err) {
    messages.value.push({ role: 'assistant', content: getApiErrorMessage(err, '问答服务暂不可用，请稍后重试。'), error: true })
  } finally {
    sending.value = false
    await scrollBottom()
  }
}

async function scrollBottom() {
  await nextTick()
  conversation.value?.scrollTo({ top: conversation.value.scrollHeight, behavior: 'smooth' })
}

function reset() { messages.value = []; question.value = '' }

onMounted(async () => {
  try {
    books.value = (await textbookApi.list()).items.filter((book) => ['ready', 'review'].includes(book.status))
    const requested = typeof route.query.textbook === 'string' ? route.query.textbook : undefined
    textbookId.value = requested || books.value[0]?.id
    if (requested && typeof route.query.chapter === 'string') {
      const structure = await textbookApi.getStructure(requested)
      const find = (chapters: typeof structure.chapters): typeof structure.chapters[number] | undefined => {
        for (const chapter of chapters) {
          if (String(chapter.id) === route.query.chapter) return chapter
          const child = find(chapter.children || [])
          if (child) return child
        }
      }
      const chapter = find(structure.chapters)
      if (chapter) { chapterId.value = chapter.id; chapterTitle.value = chapter.title }
    }
  } catch { books.value = [] }
  try { ai.value = await desktopSettings.readAI() } catch { ai.value = null }
})
</script>

<template>
  <div>
    <PageHeader title="教材问答" description="默认查找本地原文；需要 AI 解释时，可选择发送相关片段。">
      <template #actions><el-button :icon="RefreshLeft" @click="reset">新对话</el-button></template>
    </PageHeader>
    <el-alert v-if="chapterId" type="info" show-icon :title="`当前仅检索：${chapterTitle}（含子章节）`" @close="chapterId = undefined" />
    <div class="rag-grid">
      <section class="surface-card chat-card">
        <header class="chat-header"><div><span><el-icon><ChatDotRound /></el-icon></span><div><strong>教材智能助教</strong><small><i></i> 引用式回答 · 不确定时拒答</small></div></div><el-select v-model="textbookId" placeholder="全部教材" clearable @change="chapterId = undefined"><el-option v-for="book in books" :key="book.id" :label="book.title" :value="book.id" /></el-select></header>
        <div ref="conversation" class="conversation">
          <div v-if="!messages.length" class="chat-empty"><span><el-icon><Reading /></el-icon></span><h2>从教材中寻找答案</h2><p>选择一本教材并提出问题。系统先检索相关原文，再生成带引用的回答。</p><div><button v-for="item in suggestions" :key="item" type="button" @click="send(item)">{{ item }}</button></div></div>
          <article v-for="(message, index) in messages" :key="index" class="message" :class="message.role">
            <span class="message-avatar">{{ message.role === 'user' ? '我' : '知' }}</span>
            <div class="message-body"><small v-if="message.role === 'assistant'">{{ message.mode === 'ai' ? 'AI 解释' : '本地资料' }}<template v-if="message.notice"> · {{ message.notice }}</template></small><p :class="{ error: message.error }"><MathContent :text="message.content" /></p><div v-if="message.citations?.length" class="citations"><strong>引用来源（点击查看原文）</strong><button v-for="(citation, citationIndex) in message.citations" :key="citation.chunk_id || citationIndex" type="button" @click="openCitation(citation)"><el-icon><Document /></el-icon><span><b>[{{ citationIndex + 1 }}] {{ citation.textbook_title }}</b><small>{{ citation.chapter_title || '教材正文' }}<template v-if="citation.page"> · 第 {{ citation.page }} 页</template><template v-else-if="citation.locator?.kind === 'slide'"> · 幻灯片 {{ citation.locator.unit_id }}</template></small><em>{{ citation.content }}</em></span></button></div></div>
          </article>
          <article v-if="sending" class="message assistant"><span class="message-avatar">知</span><div class="message-body typing"><i></i><i></i><i></i><span>正在检索教材并组织回答</span></div></article>
        </div>
        <footer class="composer"><el-input v-model="question" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" maxlength="2000" show-word-limit placeholder="请输入与教材内容相关的问题…" @keydown.enter.exact.prevent="send()" /><button type="button" :disabled="!question.trim() || sending" @click="send()"><el-icon><Promotion /></el-icon></button><p>AI 可能出错，请以引用的教材原文为准。</p></footer>
      </section>
      <aside class="rag-aside">
        <section class="surface-card guide-card"><h2>本次问答方式</h2><label style="display:flex;gap:8px;line-height:1.8;font-size:14px"><input data-test="use-ai" v-model="useAI" type="checkbox" :disabled="sending || !textbookId || !ai?.qa_enabled || !ai?.key_configured">使用 AI 解释，同意发送问题和相关片段</label><p style="font-size:13px;line-height:1.8">{{ useAI ? '会发送至：' + ai?.base_url + '，模型：' + ai?.model + '。最多 5 段，每段 500 字，可能产生费用。' : '当前只查本地资料，不发送教材。' }}</p><el-button @click="router.push('/settings')">设置 AI 接口</el-button></section>
        <section class="surface-card guide-card"><p class="eyebrow">提问指南</p><h2>如何得到更好的回答</h2><ul><li><span>01</span><p><strong>限定教材范围</strong><small>选择具体教材，减少跨资料干扰。</small></p></li><li><span>02</span><p><strong>描述具体问题</strong><small>带上概念、章节或题目条件。</small></p></li><li><span>03</span><p><strong>核对原文引用</strong><small>点击式卡片会显示相关教材片段。</small></p></li></ul></section>
        <section class="privacy-card"><el-icon><Document /></el-icon><div><strong>资料安全</strong><p>只查找你自己的课本。若配置了在线 AI，会把相关课本片段发送给该服务。</p></div></section>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.rag-grid{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(280px,.55fr);gap:20px}.chat-card{height:calc(100vh - 185px);min-height:610px;display:grid;grid-template-rows:70px minmax(0,1fr) auto;overflow:hidden}.chat-header{padding:0 22px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--line)}.chat-header>div{display:flex;align-items:center;gap:11px}.chat-header>div>span{width:36px;height:36px;display:grid;place-items:center;border-radius:11px;color:#fff;background:linear-gradient(135deg,#5e6ade,#28baa8)}.chat-header strong,.chat-header small{display:block}.chat-header strong{font-size:12px}.chat-header small{margin-top:3px;color:#8d95a8;font-size:9px}.chat-header small i{display:inline-block;width:6px;height:6px;border-radius:50%;background:#25b19e}.chat-header .el-select{width:220px}.conversation{padding:24px;overflow:auto;background:#fafbfe}.chat-empty{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center}.chat-empty>span{width:62px;height:62px;display:grid;place-items:center;border-radius:20px;color:#5e69d9;background:#eef0ff;font-size:27px}.chat-empty h2{margin:17px 0 7px;font-size:18px}.chat-empty p{max-width:430px;color:#8991a5;font-size:11px;line-height:1.8}.chat-empty>div{margin-top:14px;display:flex;flex-wrap:wrap;justify-content:center;gap:8px}.chat-empty button{padding:8px 12px;border:1px solid #e1e5ef;border-radius:9px;background:#fff;color:#69728a;font-size:10px;cursor:pointer}.chat-empty button:hover{color:#4f5bd0;border-color:#aeb5eb}.message{margin-bottom:22px;display:flex;gap:11px}.message.user{flex-direction:row-reverse}.message-avatar{width:32px;height:32px;flex:0 0 auto;display:grid;place-items:center;border-radius:10px;color:#fff;background:#5662d5;font-size:10px;font-weight:700}.message.assistant .message-avatar{background:#20ad9b}.message-body{max-width:78%}.message-body>p{margin:0;padding:13px 16px;border-radius:4px 14px 14px 14px;background:#fff;box-shadow:0 3px 14px rgba(30,42,80,.06);font-size:12px;line-height:1.9;white-space:pre-wrap}.user .message-body>p{border-radius:14px 4px 14px 14px;color:#fff;background:#5662d5}.message-body>p.error{color:#c64b5a;background:#fff0f2}.citations{margin-top:9px;padding:12px;border:1px solid #e5e8f1;border-radius:12px;background:#fff}.citations>strong{display:block;margin-bottom:8px;color:#697289;font-size:9px}.citations button{width:100%;padding:9px;display:flex;gap:8px;text-align:left;border:0;border-radius:9px;background:#f7f8fc;cursor:pointer}.citations button+button{margin-top:6px}.citations button>.el-icon{margin-top:2px;color:#5b66d7}.citations b,.citations small,.citations em{display:block}.citations b{font-size:9px}.citations small{margin-top:2px;color:#9299aa;font-size:8px}.citations em{margin-top:5px;color:#747d93;font-size:8px;font-style:normal;line-height:1.6}.typing{padding:13px 16px;display:flex;align-items:center;gap:5px;border-radius:4px 14px 14px 14px;background:#fff}.typing i{width:5px;height:5px;border-radius:50%;background:#7a84df;animation:pulse 1s infinite}.typing i:nth-child(2){animation-delay:.15s}.typing i:nth-child(3){animation-delay:.3s}.typing span{margin-left:5px;color:#9299aa;font-size:9px}@keyframes pulse{50%{opacity:.25;transform:translateY(-2px)}}.composer{position:relative;padding:15px 20px 12px;border-top:1px solid var(--line);background:#fff}.composer .el-textarea{padding-right:48px}.composer>button{position:absolute;right:29px;top:24px;width:36px;height:36px;display:grid;place-items:center;border:0;border-radius:10px;color:#fff;background:#5662d7;cursor:pointer}.composer>button:disabled{opacity:.4;cursor:not-allowed}.composer>p{margin:7px 0 0;color:#a0a6b5;font-size:8px;text-align:center}.rag-aside{display:grid;align-content:start;gap:14px}.guide-card{padding:24px}.guide-card h2{font-size:17px}.guide-card ul{padding:0;margin:23px 0 0;list-style:none}.guide-card li{padding:13px 0;display:flex;gap:11px;border-top:1px solid #edf0f5}.guide-card li>span{color:#6a74dc;font:700 10px 'Plus Jakarta Sans'}.guide-card li p{margin:0}.guide-card li strong,.guide-card li small{display:block}.guide-card li strong{font-size:11px}.guide-card li small{margin-top:4px;color:#9097aa;font-size:9px;line-height:1.6}.privacy-card{padding:18px;display:flex;gap:11px;border-radius:15px;color:#fff;background:#1c2347}.privacy-card>.el-icon{flex:0 0 auto;color:#73d3c6}.privacy-card strong{font-size:11px}.privacy-card p{margin:5px 0 0;color:#9ca5c4;font-size:9px;line-height:1.6}@media(max-width:1000px){.rag-grid{grid-template-columns:1fr}.rag-aside{grid-template-columns:1fr 1fr}.chat-card{height:700px}}@media(max-width:620px){.chat-card{height:calc(100vh - 155px);min-height:560px}.rag-aside{grid-template-columns:1fr}.chat-header .el-select{width:145px}.message-body{max-width:88%}.conversation{padding:16px}}
</style>
