<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Aim,
  ArrowDown,
  ChatDotRound,
  Collection,
  DataAnalysis,
  DocumentChecked,
  Fold,
  HomeFilled,
  Menu as MenuIcon,
  Notebook,
  Reading,
  SwitchButton,
  Tickets,
  TrendCharts,
} from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const collapsed = ref(false)
const mobileMenu = ref(false)

const items = [
  { path: '/dashboard', label: '学习总览', icon: HomeFilled },
  { path: '/textbooks', label: '我的课本', icon: Reading },
  { path: '/questions', label: '我的题库', icon: Tickets },
  { path: '/exam/generate', label: '做练习', icon: DocumentChecked },
  { path: '/results', label: '学习记录', icon: DataAnalysis },
  { path: '/rag', label: '问一问', icon: ChatDotRound },
  { path: '/learning', label: '学习进度', icon: TrendCharts },
]

const activePath = computed(() => {
  if (route.path.startsWith('/textbooks')) return '/textbooks'
  return items.find((item) => route.path.startsWith(item.path))?.path || '/dashboard'
})

const initials = computed(() => (auth.user?.name || auth.user?.email || '学').slice(0, 1).toUpperCase())

function navigate(path: string) {
  mobileMenu.value = false
  void router.push(path)
}

function logout() {
  auth.logout()
  void router.replace('/auth')
}
</script>

<template>
  <div class="app-shell" :class="{ 'sidebar-collapsed': collapsed }">
    <aside class="sidebar desktop-sidebar">
      <button class="brand" type="button" @click="navigate('/dashboard')">
        <span class="brand-mark"><el-icon><Aim /></el-icon></span>
        <span v-if="!collapsed" class="brand-copy"><strong>知途</strong><small>ADAPTIVE LEARNING</small></span>
      </button>
      <nav class="side-nav" aria-label="主要导航">
        <button
          v-for="item in items"
          :key="item.path"
          type="button"
          class="nav-item"
          :class="{ active: activePath === item.path }"
          :title="collapsed ? item.label : undefined"
          @click="navigate(item.path)"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <span v-if="!collapsed">{{ item.label }}</span>
        </button>
      </nav>
      <div class="sidebar-insight" v-if="!collapsed">
        <span class="insight-icon"><el-icon><Notebook /></el-icon></span>
        <div><strong>今日目标</strong><small>保持专注，完成一次练习</small></div>
      </div>
      <button class="collapse-button" type="button" @click="collapsed = !collapsed">
        <el-icon><Fold :class="{ reversed: collapsed }" /></el-icon>
        <span v-if="!collapsed">收起导航</span>
      </button>
    </aside>

    <div class="app-main">
      <header class="topbar">
        <div class="topbar-left">
          <button class="mobile-menu-button" type="button" aria-label="打开菜单" @click="mobileMenu = true">
            <el-icon><MenuIcon /></el-icon>
          </button>
          <div class="context-title">
            <span class="context-dot"></span>
            <span>{{ String(route.meta.title || '学习平台') }}</span>
          </div>
        </div>
        <div class="topbar-actions">
          <button class="quick-study" type="button" @click="navigate('/exam/generate')">
            <el-icon><Collection /></el-icon><span>开始练习</span>
          </button>
          <el-dropdown trigger="click">
            <button class="user-trigger" type="button">
              <span class="avatar">{{ initials }}</span>
              <span class="user-copy"><strong>{{ auth.user?.name || '学习者' }}</strong><small>个人学习空间</small></span>
              <el-icon><ArrowDown /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item :icon="SwitchButton" @click="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>
      <main class="page-container"><router-view /></main>
    </div>

    <el-drawer v-model="mobileMenu" direction="ltr" size="280px" :with-header="false" class="mobile-drawer">
      <div class="mobile-brand"><span class="brand-mark"><el-icon><Aim /></el-icon></span><strong>知途学习</strong></div>
      <nav class="side-nav mobile-nav">
        <button v-for="item in items" :key="item.path" type="button" class="nav-item" :class="{ active: activePath === item.path }" @click="navigate(item.path)">
          <el-icon><component :is="item.icon" /></el-icon><span>{{ item.label }}</span>
        </button>
      </nav>
    </el-drawer>
  </div>
</template>
