<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { Aim, ArrowRight, Check, Connection, Lock, Message, Reading, User } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import { getApiErrorMessage } from '../api/http'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const mode = ref<'login' | 'register'>('login')
const formRef = ref<FormInstance>()
const form = reactive({ name: '', email: '', password: '', confirmPassword: '' })

const rules: FormRules = {
  name: [{ required: true, message: '请输入你的姓名', trigger: 'blur' }],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入有效邮箱', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 8, message: '密码至少 8 位', trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    { validator: (_rule, value, callback) => value === form.password ? callback() : callback(new Error('两次密码不一致')), trigger: 'blur' },
  ],
}

async function submit() {
  if (!formRef.value || !(await formRef.value.validate().catch(() => false))) return
  try {
    if (mode.value === 'login') await auth.login({ email: form.email, password: form.password })
    else await auth.register({ name: form.name, email: form.email, password: form.password, role: 'student' })
    ElMessage.success(mode.value === 'login' ? '欢迎回来' : '账户创建成功')
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/dashboard'
    await router.replace(redirect)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '登录失败'))
  }
}

async function enterDemo() {
  auth.enterDemo()
  ElMessage.info('已进入只读演示模式，连接后端后可使用完整功能')
  await router.replace('/dashboard')
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-story">
      <div class="story-grid"></div>
      <div class="story-orb orb-one"></div><div class="story-orb orb-two"></div>
      <div class="auth-brand"><span class="brand-mark"><el-icon><Aim /></el-icon></span><strong>知途</strong></div>
      <div class="story-content">
        <p class="story-kicker">YOUR PERSONAL LEARNING COMPASS</p>
        <h1>让每一次学习<br /><span>都更接近掌握</span></h1>
        <p>从教材出发，理解你的知识状态，为你规划真正个性化的学习路径。</p>
        <div class="story-points">
          <div><span><el-icon><Reading /></el-icon></span><p><strong>教材驱动</strong><small>结构化知识，精确引用来源</small></p></div>
          <div><span><el-icon><Check /></el-icon></span><p><strong>自适应练习</strong><small>持续识别薄弱点，动态调整策略</small></p></div>
          <div><span><el-icon><Connection /></el-icon></span><p><strong>成长路径</strong><small>跨教材延续你的学习轨迹</small></p></div>
        </div>
      </div>
      <p class="story-footer">© 2026 知途智能学习</p>
    </section>

    <section class="auth-form-side">
      <div class="auth-panel">
        <div class="auth-mobile-brand"><span class="brand-mark"><el-icon><Aim /></el-icon></span><strong>知途</strong></div>
        <div class="auth-tabs">
          <button :class="{ active: mode === 'login' }" type="button" @click="mode = 'login'; formRef?.clearValidate()">登录</button>
          <button :class="{ active: mode === 'register' }" type="button" @click="mode = 'register'; formRef?.clearValidate()">注册</button>
        </div>
        <h2>{{ mode === 'login' ? '欢迎回来' : '开启你的学习旅程' }}</h2>
        <p class="auth-subtitle">{{ mode === 'login' ? '继续探索属于你的知识地图' : '创建账户，让系统从第一道题开始了解你' }}</p>
        <el-form ref="formRef" :model="form" :rules="rules" label-position="top" size="large" @submit.prevent="submit">
          <el-form-item v-if="mode === 'register'" label="姓名" prop="name">
            <el-input v-model="form.name" placeholder="你的姓名" :prefix-icon="User" autocomplete="name" />
          </el-form-item>
          <el-form-item label="邮箱" prop="email">
            <el-input v-model="form.email" placeholder="name@example.com" :prefix-icon="Message" autocomplete="email" />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input v-model="form.password" type="password" placeholder="至少 8 位" :prefix-icon="Lock" show-password autocomplete="current-password" @keyup.enter="submit" />
          </el-form-item>
          <el-form-item v-if="mode === 'register'" label="确认密码" prop="confirmPassword">
            <el-input v-model="form.confirmPassword" type="password" placeholder="再次输入密码" :prefix-icon="Lock" show-password @keyup.enter="submit" />
          </el-form-item>
          <el-button class="auth-submit" type="primary" size="large" :loading="auth.loading" native-type="submit">
            {{ mode === 'login' ? '登录' : '创建账户' }} <el-icon><ArrowRight /></el-icon>
          </el-button>
        </el-form>
        <div class="demo-divider"><span>或</span></div>
        <el-button class="demo-button" size="large" @click="enterDemo">只读演示浏览</el-button>
        <p class="demo-tip">后端未启动也可查看界面；演示模式不会伪造或保存任何数据。</p>
      </div>
    </section>
  </main>
</template>

<style scoped>
.auth-page { min-height: 100vh; display: grid; grid-template-columns: minmax(420px, 1.05fr) minmax(480px, .95fr); background: #fff; }
.auth-story { position: relative; min-height: 100vh; padding: 42px clamp(38px, 6vw, 92px); display: flex; flex-direction: column; overflow: hidden; color: #fff; background: linear-gradient(145deg,#171d3c 0%,#252d5d 72%,#2a356d 100%); }
.story-grid { position: absolute; inset: 0; opacity: .09; background-image: linear-gradient(rgba(255,255,255,.4) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.4) 1px,transparent 1px); background-size: 52px 52px; mask-image: linear-gradient(to bottom right,#000,transparent 80%); }
.story-orb { position: absolute; border-radius: 50%; filter: blur(2px); }
.orb-one { width: 320px; height: 320px; right: -120px; top: 13%; background: radial-gradient(circle,rgba(101,115,241,.26),transparent 68%); }
.orb-two { width: 410px; height: 410px; left: -190px; bottom: -180px; background: radial-gradient(circle,rgba(37,199,178,.18),transparent 68%); }
.auth-brand { position: relative; z-index: 1; display: flex; align-items: center; gap: 13px; font-size: 22px; }
.story-content { position: relative; z-index: 1; width: min(550px,100%); margin: auto 0; padding: 65px 0; }
.story-kicker { margin-bottom: 19px; color: #7edacf; font: 700 11px 'Plus Jakarta Sans'; letter-spacing: .18em; }
.story-content h1 { margin-bottom: 23px; font-size: clamp(38px,5vw,64px); line-height: 1.2; letter-spacing: -.05em; }
.story-content h1 span { background: linear-gradient(90deg,#8d99ff,#65d9c8); -webkit-background-clip: text; color: transparent; }
.story-content > p:not(.story-kicker) { width: min(440px,100%); color: #a9b1ce; font-size: 15px; line-height: 1.9; }
.story-points { margin-top: 45px; display: grid; gap: 19px; }
.story-points > div { display: flex; align-items: center; gap: 14px; }
.story-points > div > span { width: 39px; height: 39px; display: grid; place-items: center; border: 1px solid rgba(255,255,255,.1); border-radius: 12px; color: #8f99fb; background: rgba(255,255,255,.05); }
.story-points p { margin: 0; display: flex; flex-direction: column; gap: 2px; }
.story-points strong { font-size: 13px; }
.story-points small { color: #8e97b6; font-size: 11px; }
.story-footer { position: relative; z-index: 1; margin: 0; color: #646d90; font-size: 10px; }
.auth-form-side { padding: 50px clamp(35px,7vw,110px); display: grid; place-items: center; }
.auth-panel { width: min(420px,100%); }
.auth-mobile-brand { display: none; }
.auth-tabs { display: inline-flex; gap: 5px; padding: 4px; margin-bottom: 36px; border-radius: 11px; background: #f1f3f8; }
.auth-tabs button { min-width: 80px; height: 34px; border: 0; border-radius: 8px; background: transparent; color: #8a92a8; cursor: pointer; }
.auth-tabs button.active { color: #343dbe; background: #fff; box-shadow: 0 3px 10px rgba(30,42,84,.08); font-weight: 600; }
.auth-panel h2 { margin-bottom: 8px; font-size: 28px; letter-spacing: -.03em; }
.auth-subtitle { margin-bottom: 28px; color: #81899e; font-size: 13px; }
.auth-panel :deep(.el-form-item) { margin-bottom: 20px; }
.auth-panel :deep(.el-form-item__label) { padding-bottom: 7px; font-size: 12px; }
.auth-panel :deep(.el-input__wrapper) { min-height: 45px; }
.auth-submit, .demo-button { width: 100%; min-height: 46px; }
.auth-submit .el-icon { margin-left: 7px; }
.demo-divider { height: 36px; display: flex; align-items: center; justify-content: center; color: #adb2c0; font-size: 11px; }
.demo-divider::before,.demo-divider::after { content:''; flex:1; height:1px; background:#edf0f5; }
.demo-divider span { padding:0 12px; }
.demo-tip { margin: 10px auto 0; max-width: 320px; color: #a1a7b6; font-size: 10px; line-height: 1.6; text-align: center; }
@media(max-width:900px){.auth-page{grid-template-columns:1fr}.auth-story{display:none}.auth-form-side{min-height:100vh;padding:36px 22px}.auth-mobile-brand{margin-bottom:38px;display:flex;align-items:center;gap:12px;font-size:20px}}
</style>
