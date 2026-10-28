<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import PageHeader from '../components/PageHeader.vue'
import { desktopSettings, type BackupInfo, type MaintenanceStatus } from '../api/desktopSettings'
import { getApiErrorMessage } from '../api/http'

const form = reactive({ base_url: '', model: '', qa_enabled: false, practice_enabled: false })
const apiKey = ref(''), keyConfigured = ref(false), privacyAck = ref(false), testConsent = ref(false)
const busy = ref(false), loaded = ref(false), error = ref(''), notice = ref('')
const state = ref<MaintenanceStatus>({ pending: false, can_rollback: false, restore_error: '' })
const staged = ref<BackupInfo | null>(null), restoreAck = ref(false), rollbackAck = ref(false)
const canSave = computed(() => loaded.value && !busy.value && !state.value.pending && (!(form.qa_enabled || form.practice_enabled) || privacyAck.value))

async function perform(action: () => Promise<void>) {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try { await action() } catch (err) { error.value = getApiErrorMessage(err) }
  finally { busy.value = false }
}
async function load() {
  await perform(async () => {
    const [config, status] = await Promise.all([desktopSettings.readAI(), desktopSettings.status()])
    Object.assign(form, { base_url: config.base_url, model: config.model, qa_enabled: config.qa_enabled, practice_enabled: config.practice_enabled })
    keyConfigured.value = config.key_configured; state.value = status; loaded.value = true
  })
}
async function save(clear = false) {
  await perform(async () => {
    try {
      const config = await desktopSettings.saveAI({ ...form, api_key: clear ? '' : apiKey.value,
        privacy_ack: privacyAck.value, ...(clear ? { clear_key: true, qa_enabled: false, practice_enabled: false } : {}) })
      keyConfigured.value = config.key_configured
      form.qa_enabled = config.qa_enabled; form.practice_enabled = config.practice_enabled
      notice.value = clear ? '密钥已清除，AI 已关闭。本地学习仍可使用。' : '设置已保存。'
      testConsent.value = false
    } finally { apiKey.value = '' }
  })
}
async function backup() {
  await perform(async () => {
    const result = await desktopSettings.backup()
    if (!window.pywebview?.api.export_backup) throw new Error('备份已保存在本地 backups 文件夹，请通过下方按钮打开资料目录。')
    const exported = await window.pywebview.api.export_backup(result.id)
    notice.value = exported.saved ? '备份已导出，请保存在其他磁盘以便找回资料。' : '已取消导出，备份仍保存在本地 backups 文件夹。'
  })
}
async function chooseRestore(event: Event) {
  const input = event.target as HTMLInputElement, file = input.files?.[0]
  if (!file) return
  staged.value = null; restoreAck.value = false
  await perform(async () => { staged.value = await desktopSettings.prepareRestore(file) })
  input.value = ''
}
async function confirmRestore() {
  if (!staged.value || !restoreAck.value) return
  await perform(async () => { await desktopSettings.confirmRestore(staged.value!.id); state.value = await desktopSettings.status(); staged.value = null })
}
async function cancelRestore() {
  await perform(async () => { await desktopSettings.cancelRestore(); state.value = await desktopSettings.status(); notice.value = '已取消，可以继续学习。' })
}
async function rollback() {
  if (!rollbackAck.value) return
  await perform(async () => { await desktopSettings.rollback(); state.value = await desktopSettings.status() })
}
async function openFolder() {
  await perform(async () => {
    if (!window.pywebview?.api.open_data_dir) throw new Error('请在桌面软件内打开资料目录')
    await window.pywebview.api.open_data_dir()
  })
}
async function testConnection() { await perform(async () => { notice.value = (await desktopSettings.testAI(testConsent.value)).notice }) }
onMounted(load)
</script>

<template>
  <div class="settings-page">
    <PageHeader title="设置" description="资料保存在本机。需要 AI 帮助时，再填写你自己的接口。" />
    <p v-if="error" role="alert" class="message warning">{{ error }} <button v-if="!loaded" @click="load">重新加载</button></p>
    <p v-if="notice" role="status" class="message">{{ notice }}</p>
    <p v-if="state.restore_error" role="alert" class="message warning">{{ state.restore_error }}</p>
    <section v-if="state.pending" class="message warning"><strong>已安排切换资料，请关闭软件后重新打开。</strong><p>重启前暂停修改。当前学习空间会保留，可从这里返回。</p><button data-test="cancel-restore" :disabled="busy" @click="cancelRestore">取消本次切换，继续学习</button></section>
    <section class="surface-card settings-card">
      <h2>AI 帮助（可选）</h2><p>不开启也能导入、阅读、查找原文和做本地题库里的练习。</p>
      <fieldset :disabled="busy || !loaded || state.pending">
        <label class="check"><input data-test="qa-enabled" v-model="form.qa_enabled" type="checkbox">允许 AI 回答教材问题</label>
        <label class="check"><input v-model="form.practice_enabled" type="checkbox">允许 AI 根据教材补充练习题</label>
        <label>接口地址<input v-model="form.base_url" type="url" placeholder="https://你的服务地址/v1" autocomplete="off"></label>
        <label>模型名称<input v-model="form.model" placeholder="填写服务商提供的模型名" autocomplete="off"></label>
        <label>API 密钥 <span>（{{ keyConfigured ? '已配置，留空保留原密钥' : '尚未配置' }}）</span><input data-test="key" v-model="apiKey" type="password" autocomplete="new-password" placeholder="填写后保存，软件不会再次显示原密钥"></label>
        <p>使用兼容 Chat Completions 的接口。密钥由当前 Windows 用户保护；与别人共用同一 Windows 账户时，对方可能访问本地资料。</p>
        <label class="check"><input data-test="privacy-ack" v-model="privacyAck" type="checkbox">我知道开启后会将问题及必要教材片段发送到所填服务，服务商可能收费。</label>
      </fieldset>
      <div class="actions"><button data-test="save-ai" class="primary" :disabled="!canSave" @click="save()">保存设置</button><button data-test="clear-key" :disabled="busy || !loaded || state.pending || !keyConfigured" @click="save(true)">清除密钥并关闭 AI</button></div>
      <div class="test-connection"><p>连接测试使用已保存的设置，只发送一条简短测试请求，不发送教材。可能产生少量费用。</p><label class="check"><input data-test="test-consent" v-model="testConsent" type="checkbox" :disabled="busy || state.pending">同意发送一次测试请求</label><button data-test="test-ai" :disabled="busy || !loaded || state.pending || !testConsent" @click="testConnection">测试连接</button></div>
    </section>
    <section class="surface-card settings-card">
      <h2>备份和恢复</h2><p>备份包含教材原文件、题库、练习和阅读记录，不包含 AI 密钥。恢复只支持知途桌面版生成的备份 ZIP。</p>
      <div class="actions"><button data-test="backup" class="primary" :disabled="busy || !loaded || state.pending" @click="backup">创建并导出备份</button><button :disabled="busy" @click="openFolder">打开本地资料目录</button></div>
      <label class="restore-file">选择备份文件（最多 2 GB）<input type="file" accept=".zip" :disabled="busy || !loaded || state.pending" @change="chooseRestore"></label>
      <div v-if="staged" class="restore-preview"><h3>备份检查通过</h3><p>{{ staged.counts.textbooks }} 本教材 · {{ staged.counts.questions }} 道题 · {{ staged.counts.exam_records }} 次练习</p><label class="check"><input v-model="restoreAck" type="checkbox">重启后使用这份备份。当前资料会保留，但不会自动合并两个空间的记录。</label><button class="primary" :disabled="busy || !restoreAck" @click="confirmRestore">确认，下次启动恢复</button></div>
      <div v-if="state.can_rollback && !state.pending" class="test-connection"><label class="check"><input v-model="rollbackAck" type="checkbox">我想返回上一次切换前的学习空间，两份资料各自保留。</label><button :disabled="busy || !rollbackAck" @click="rollback">下次启动返回上一个空间</button></div>
      <p v-if="busy" role="status">正在处理，请稍候…</p>
    </section>
  </div>
</template>

<style scoped>
.settings-page{max-width:960px}.settings-card{padding:24px;margin-bottom:20px}.settings-card h2{margin:0 0 12px;font-size:19px}.settings-card p{color:#68748a;line-height:1.8;font-size:14px}fieldset{border:0;padding:0;margin:0}label{display:grid;gap:7px;margin:15px 0;font-size:14px}.check{display:flex;align-items:flex-start;gap:9px;line-height:1.7}.check input{margin-top:6px;flex:none}input:not([type=checkbox]):not([type=file]){padding:10px 12px;border:1px solid #cfd5e1;border-radius:8px;font:inherit;background:#fff;width:100%}button{padding:10px 15px;border:1px solid #ccd4e2;border-radius:8px;background:#fff;color:#33405a;cursor:pointer;font:inherit;font-size:14px}button.primary{background:#515fca;color:#fff;border-color:#515fca}button:disabled{opacity:.5;cursor:not-allowed}.actions{display:flex;flex-wrap:wrap;gap:10px}.message{padding:16px;border-radius:10px;background:#eef5ff;margin-bottom:16px;line-height:1.7}.warning{background:#fff3df;color:#80571f}.test-connection,.restore-file,.restore-preview{margin-top:22px;padding-top:16px;border-top:1px solid #e4e8ef}.restore-preview{padding:16px;background:#f4f7ff;border-radius:10px}input:focus-visible,button:focus-visible{outline:2px solid #515fca;outline-offset:3px}
</style>
