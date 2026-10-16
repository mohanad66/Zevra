import { createContext, useContext, useEffect, useState } from 'react'
import { getCookie, setCookie } from './utils/storage'

const STORAGE_KEY = 'miyartrading_theme'
export const DEFAULT_THEME = 'dark'

export function getStoredTheme() {
  try {
    const value = getCookie(STORAGE_KEY)
    return value === 'light' || value === 'dark' ? value : null
  } catch {
    return null
  }
}

function storeTheme(theme) {
  try {
    setCookie(STORAGE_KEY, theme)
  } catch {
    /* ignore storage errors */
  }
}

const ThemeContext = createContext(null)

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(() => getStoredTheme() || DEFAULT_THEME)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  const setTheme = (next) => {
    const value = next === 'light' ? 'light' : 'dark'
    setThemeState(value)
    storeTheme(value)
  }

  const toggleTheme = () => setTheme(theme === 'dark' ? 'light' : 'dark')

  return (
    <ThemeContext.Provider value={{ theme, setTheme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  return useContext(ThemeContext)
}
