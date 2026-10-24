import { StrictMode, useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

function Root() {
  useEffect(() => {
    // Ensure the app doesn't block on background assets and we repaint once ready
    const id = requestAnimationFrame(() => {
      document.documentElement.dataset.appReady = '1'
    })
    return () => cancelAnimationFrame(id)
  }, [])
  return (
    <StrictMode>
      <div className="bg-layer" aria-hidden="true" />
      <App />
    </StrictMode>
  )
}

createRoot(document.getElementById('root')).render(<Root />)
