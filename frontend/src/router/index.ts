import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/auth',
    name: 'auth',
    component: () => import('../views/AuthView.vue'),
    meta: { public: true, title: '登录' },
  },
  {
    path: '/exam/:id/take',
    name: 'exam-take',
    component: () => import('../views/ExamTakeView.vue'),
    meta: { title: '专注练习', fullscreen: true },
  },
  {
    path: '/',
    component: () => import('../layouts/AppLayout.vue'),
    children: [
      { path: '', redirect: '/dashboard' },
      { path: 'dashboard', name: 'dashboard', component: () => import('../views/DashboardView.vue'), meta: { title: '学习总览' } },
      { path: 'textbooks', name: 'textbooks', component: () => import('../views/TextbooksView.vue'), meta: { title: '我的课本' } },
      { path: 'textbooks/:id', name: 'textbook-detail', component: () => import('../views/TextbookDetailView.vue'), meta: { title: '教材详情' } },
      { path: 'questions', name: 'questions', component: () => import('../views/QuestionsView.vue'), meta: { title: '我的题库' } },
      { path: 'exam/generate', name: 'exam-generate', component: () => import('../views/ExamGenerateView.vue'), meta: { title: '做练习' } },
      { path: 'results', name: 'results', component: () => import('../views/ResultsView.vue'), meta: { title: '学习记录' } },
      { path: 'results/:id', name: 'exam-record-detail', component: () => import('../views/ExamRecordDetailView.vue'), meta: { title: '练习详情' } },
      { path: 'rag', name: 'rag', component: () => import('../views/RagView.vue'), meta: { title: '问一问' } },
      { path: 'learning', name: 'learning', component: () => import('../views/LearningView.vue'), meta: { title: '学习进度' } },
      { path: 'learning/knowledge-points/:id', name: 'knowledge-point-detail', component: () => import('../views/KnowledgePointDetailView.vue'), meta: { title: '知识点详情' } },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach(async (to) => {
  document.title = `${String(to.meta.title || '学习平台')} · 知途`
  const auth = useAuthStore()
  if (to.meta.public) return auth.isAuthenticated ? '/dashboard' : true
  if (!auth.isAuthenticated) return { path: '/auth', query: { redirect: to.fullPath } }
  if (!auth.user) {
    try {
      await auth.fetchMe()
    } catch {
      return { path: '/auth', query: { redirect: to.fullPath } }
    }
  }
  return true
})

window.addEventListener('auth:expired', () => {
  const auth = useAuthStore()
  auth.logout()
  void router.replace({ path: '/auth', query: { redirect: router.currentRoute.value.fullPath } })
})

export default router
