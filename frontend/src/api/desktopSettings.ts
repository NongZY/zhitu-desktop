import { http } from './http'

export interface AISettings {
  base_url: string; model: string; qa_enabled: boolean; practice_enabled: boolean
  key_configured: boolean; key_masked: string
}
export interface MaintenanceStatus { pending: boolean; can_rollback: boolean; restore_error: string }
export interface BackupInfo { id: string; counts: Record<string, number>; size?: number; notice?: string }
export const desktopSettings = {
  async readAI() { return (await http.get<AISettings>('/settings/ai')).data },
  async saveAI(payload: object) { return (await http.put<AISettings>('/settings/ai', payload)).data },
  async testAI(consent: boolean) { return (await http.post<{ status: string; notice: string }>('/settings/ai/test', { consent }, { timeout: 45000 })).data },
  async status() { return (await http.get<MaintenanceStatus>('/maintenance/status')).data },
  async backup() { return (await http.post<BackupInfo>('/maintenance/backups', {}, { timeout: 300000 })).data },
  async prepareRestore(file: File) {
    const form = new FormData(); form.append('file', file)
    return (await http.post<BackupInfo>('/maintenance/restores', form, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 300000 })).data
  },
  async confirmRestore(id: string) { return (await http.post(`/maintenance/restores/${id}/confirm`)).data },
  async cancelRestore() { await http.delete('/maintenance/pending') },
  async rollback() { return (await http.post('/maintenance/rollback')).data },
}
