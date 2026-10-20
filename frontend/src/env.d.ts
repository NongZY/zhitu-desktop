/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_API_PROXY?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

interface Window {
  pywebview?: { api: {
    get_context: () => Promise<unknown>
    respond_close: (requestId: string, decision: 'ready' | 'stay' | 'discard') => Promise<void>
  } }
}
