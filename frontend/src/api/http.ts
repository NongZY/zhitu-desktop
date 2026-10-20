import axios, { AxiosError } from 'axios'
import type { ApiErrorData } from './types'

export const TOKEN_KEY = 'adaptive_learning_token'

export const http = axios.create({
  baseURL: '/api/v1',
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
})

export function initializeDesktopHttp(context: { apiBaseUrl: string }) {
  http.defaults.baseURL = context.apiBaseUrl
}

http.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiErrorData>) => {
    if (error.response?.status === 401 || error.response?.status === 403) {
      window.dispatchEvent(new CustomEvent('desktop:disconnected'))
    }
    return Promise.reject(error)
  },
)

export function getApiErrorMessage(error: unknown, fallback = '请求失败，请稍后重试'): string {
  if (!axios.isAxiosError<ApiErrorData>(error)) return error instanceof Error ? error.message : fallback
  if (!error.response) return '本地服务暂时没有响应，请重试或重新启动软件'
  const detail = error.response.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((item) => item.msg).filter(Boolean).join('；') || fallback
  return error.response.data?.message || fallback
}

export function normalizePage<T>(payload: PageResultLike<T>): { items: T[]; total: number } {
  if (Array.isArray(payload)) return { items: payload, total: payload.length }
  const items = payload.items ?? payload.results ?? payload.data ?? []
  return { items, total: payload.total ?? items.length }
}

type PageResultLike<T> =
  | T[]
  | { items?: T[]; results?: T[]; data?: T[]; total?: number }
