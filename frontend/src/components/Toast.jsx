import { createContext, useCallback, useContext, useState } from 'react'
import { CheckCircle2, XCircle, Info, ArrowRight } from 'lucide-react'

const ToastContext = createContext(null)

let idSeq = 0

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const push = useCallback((message, type = 'info', ttl = 4500, onClick = null) => {
    const id = ++idSeq
    setToasts((prev) => [...prev, { id, message, type, onClick }])
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), ttl)
  }, [])

  const dismiss = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const handleClick = useCallback((t) => {
    if (t.onClick) t.onClick()
    dismiss(t.id)
  }, [dismiss])

  return (
    <ToastContext.Provider value={{ toast: push }}>
      {children}
      <div className="toast-wrap">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.type}${t.onClick ? ' toast-action' : ''}`} onClick={() => handleClick(t)}>
            {t.type === 'success' && <CheckCircle2 size={18} />}
            {t.type === 'error' && <XCircle size={18} />}
            {t.type === 'info' && <Info size={18} />}
            <span>{t.message}</span>
            {t.onClick && <ArrowRight size={16} className="toast-arrow" />}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  return useContext(ToastContext)
}