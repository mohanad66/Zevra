import { createContext, useContext, useEffect, useState } from 'react'
import { client, tokenStore, apiError } from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const logoutEvt = () => setUser(null)
    window.addEventListener('miyartrading:logout', logoutEvt)
    return () => window.removeEventListener('miyartrading:logout', logoutEvt)
  }, [])

  useEffect(() => {
    if (!tokenStore.access) {
      setLoading(false)
      return
    }
    client
      .get('/auth/me/')
      .then((res) => setUser(res.data))
      .catch(() => {
        // Transient failure must not end the session: keep tokens, retry once
        // the backend is reachable again instead of logging the user out.
        if (tokenStore.refresh) {
          client
            .post('/auth/refresh/', { refresh: tokenStore.refresh })
            .then((r) => {
              tokenStore.tokens = { access: r.data.access }
              return client.get('/auth/me/')
            })
            .then((res) => setUser(res.data))
            .catch(() => {})
            .finally(() => setLoading(false))
        } else {
          setLoading(false)
        }
      })
      .finally(() => setLoading(false))
  }, [])

  async function login(email, password) {
    const res = await client.post('/auth/login/', { email, password })
    tokenStore.tokens = res.data
    const me = await client.get('/auth/me/')
    setUser(me.data)
    return me.data
  }

  async function register(payload) {
    const res = await client.post('/auth/register/', payload)
    return res.data
  }

  async function logout() {
    try {
      if (tokenStore.refresh) {
        await client.post('/auth/logout/', { refresh: tokenStore.refresh })
      }
    } catch {
      /* ignore */
    }
    tokenStore.clear()
    setUser(null)
  }

  async function refreshUser() {
    try {
      const res = await client.get('/auth/me/')
      setUser(res.data)
      return res.data
    } catch {
      // Ignore transient failures so a background refresh never logs the user out.
      return null
    }
  }

  return (
    <AuthContext.Provider
      value={{ user, loading, login, register, logout, refreshUser, apiError }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}