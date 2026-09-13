import axios from 'axios'

const API_BASE = (import.meta.env.VITE_API_BASE || '/api').replace(/\/+$/, '')

export const client = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
})

const TOKEN_KEY = 'zevra_access'
const REFRESH_KEY = 'zevra_refresh'

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
      window.dispatchEvent(new Event('zevra:logout'))
    }
    return Promise.reject(error)
  },
)

export function apiError(error) {
  const data = error?.response?.data
  if (!data) return 'Network error. Please try again.'
  if (typeof data === 'string') return data
  const flat = []
  const walk = (obj) => {
    for (const key of Object.keys(obj)) {
      const val = obj[key]
      if (Array.isArray(val)) flat.push(...val.map((v) => (typeof v === 'string' ? v : JSON.stringify(v))))
      else if (typeof val === 'object' && val !== null) walk(val)
      else if (val != null) flat.push(String(val))
    }
  }
  walk(data)
  return flat.length ? flat.join(' ') : 'Something went wrong.'
}