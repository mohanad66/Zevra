import axios from 'axios'
import { getStoredLang } from '../i18n'

const API_BASE = (import.meta.env.VITE_API_BASE || '/api').replace(/\/+$/, '')

export const client = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
})

const TOKEN_KEY = 'miyartrading_access'
const REFRESH_KEY = 'miyartrading_refresh'

export const tokenStore = {
  get access() {
    return localStorage.getItem(TOKEN_KEY)
  },
  get refresh() {
    return localStorage.getItem(REFRESH_KEY)
  },
  set tokens({ access, refresh }) {
    if (access) localStorage.setItem(TOKEN_KEY, access)
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh)
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}

client.interceptors.request.use((config) => {
  const token = tokenStore.access
  if (token) config.headers.Authorization = `Bearer ${token}`
  config.headers['X-Lang'] = getStoredLang()
  if (config.data instanceof FormData) {
    delete config.headers['Content-Type']
  }
  return config
})

let refreshing = null

client.interceptors.response.use(
  (res) => res,
  async (error) => {
    const { config, response } = error
    if (response?.status === 401 && !config._retry && tokenStore.refresh) {
      config._retry = true
      refreshing =
        refreshing ||
        axios
          .post(`${API_BASE}/auth/refresh/`, { refresh: tokenStore.refresh })
          .then((res) => {
            tokenStore.tokens = { access: res.data.access }
            return res.data.access
          })
          .finally(() => {
            refreshing = null
          })
      const newToken = await refreshing
      config.headers.Authorization = `Bearer ${newToken}`
      return client(config)
    }
    if (response?.status === 401) {
      tokenStore.clear()
      window.dispatchEvent(new Event('miyartrading:logout'))
    }
    return Promise.reject(error)
  },
)

const GENERIC_ERRORS = {
  en: {
    network: 'Network error. Please check your connection and try again.',
    timeout: 'The request took too long. Please try again.',
    server: 'Server error. Please try again in a moment.',
    permission: "You don't have permission to do that.",
    throttle: 'Too many attempts. Please wait a minute and try again.',
    generic: 'Something went wrong. Please try again.',
  },
  ar: {
    network: 'تعذّر الاتصال. تحقّق من الإنترنت وحاول مرة أخرى.',
    timeout: 'استغرق الطلب وقتاً طويلاً. حاول مرة أخرى.',
    server: 'خطأ في الخادم. حاول مرة أخرى بعد قليل.',
    permission: 'ليست لديك صلاحية للقيام بذلك.',
    throttle: 'محاولات كثيرة. انتظر دقيقة ثم حاول مرة أخرى.',
    generic: 'حدث خطأ ما. حاول مرة أخرى.',
  },
}

export function apiError(error, fallback) {
  const lang = getStoredLang() === 'ar' ? 'ar' : 'en'
  const msgs = GENERIC_ERRORS[lang]
  const response = error?.response

  if (!response) {
    const timedOut = error?.code === 'ECONNABORTED' || /timeout/i.test(error?.message || '')
    return fallback || (timedOut ? msgs.timeout : msgs.network)
  }

  const data = response.data
  if (typeof data === 'string' && data.trim()) return data
  if (data && typeof data === 'object') {
    if (typeof data.detail === 'string' && data.detail.trim()) return data.detail
    const flat = []
    const walk = (obj, prefix = '') => {
      for (const key of Object.keys(obj)) {
        const val = obj[key]
        if (Array.isArray(val)) {
          val.forEach((v) => {
            if (typeof v === 'string') flat.push(v)
            else if (v && typeof v === 'object') walk(v, prefix)
          })
        } else if (typeof val === 'object' && val !== null) {
          walk(val, prefix)
        } else if (val != null) {
          flat.push(String(val))
        }
      }
    }
    walk(data)
    if (flat.length) return flat.join(' ')
  }

  const status = response.status
  if (status === 401) return msgs.permission
  if (status === 403) return msgs.permission
  if (status === 429) return msgs.throttle
  if (status >= 500) return msgs.server
  return fallback || msgs.generic
}