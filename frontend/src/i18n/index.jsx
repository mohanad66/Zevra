import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { en } from './en'
import { ar } from './ar'
import { client } from '../api/client'
import { getCookie, setCookie } from '../utils/storage'

const STORAGE_KEY = 'miyartrading_lang'
export const DEFAULT_LANG = 'en'

export function getStoredLang() {
  try {
    return getCookie(STORAGE_KEY) || DEFAULT_LANG
  } catch {
    return DEFAULT_LANG
  }
}

export function hasStoredLang() {
  try {
    return Boolean(getCookie(STORAGE_KEY))
  } catch {
    return false
  }
}

export function storeLang(lang) {
  try {
    setCookie(STORAGE_KEY, lang)
  } catch {
    /* ignore storage errors */
  }
}

const I18nContext = createContext(null)

export function I18nProvider({ children }) {
  const [lang, setLang] = useState(null)

  useEffect(() => {
    let mounted = true
    async function resolve() {
      if (hasStoredLang()) {
        setLang(getStoredLang())
        return
      }
      let platform = DEFAULT_LANG
      try {
        const res = await client.get('/settings/')
        platform = res.data?.default_lang === 'ar' ? 'ar' : DEFAULT_LANG
      } catch {
        /* keep DEFAULT_LANG when the settings can't be fetched */
      }
      if (mounted) setLang(platform)
    }
    resolve()
    return () => {
      mounted = false
    }
  }, [])

  useEffect(() => {
    if (lang) {
      document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr'
      document.documentElement.lang = lang
    }
  }, [lang])

  const dict = lang === 'ar' ? ar : en

  const t = useMemo(
    () =>
      (key, vars) => {
        let tmpl = dict[key]
        if (tmpl === undefined) tmpl = en[key]
        if (tmpl === undefined) tmpl = key
        if (vars) {
          return String(tmpl).replace(/\{(\w+)\}/g, (_, k) => (vars[k] !== undefined ? vars[k] : `{${k}}`))
        }
        return String(tmpl)
      },
    [dict]
  )

  const changeLang = (next) => {
    setLang(next)
    storeLang(next)
    window.location.reload()
  }

  if (!lang) return null

  return <I18nContext.Provider value={{ lang, t, changeLang }}>{children}</I18nContext.Provider>
}

export function useI18n() {
  return useContext(I18nContext)
}