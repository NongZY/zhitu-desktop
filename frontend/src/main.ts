import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import './styles/index.css'
import App from './App.vue'
import router from './router'
import { loadDesktopContext } from './runtime/desktop'
import { installCloseListener } from './runtime/close'
import { useWorkspaceStore } from './stores/workspace'
import { initializeDesktopHttp } from './api/http'
import DesktopStartupView from './views/DesktopStartupView.vue'

async function start() {
  const startup = createApp(DesktopStartupView)
  startup.mount('#app')
  installCloseListener()
  try {
    const context = await loadDesktopContext()
    const pinia = createPinia()
    useWorkspaceStore(pinia).initialize(context)
    initializeDesktopHttp(context)
    startup.unmount()
    const app = createApp(App)
    app.use(pinia)
    app.use(router)
    app.use(ElementPlus, { locale: zhCn })
    app.mount('#app')
  } catch (error) {
    startup.unmount()
    createApp(DesktopStartupView, { error: (error as Error).message }).mount('#app')
  }
}
void start()
