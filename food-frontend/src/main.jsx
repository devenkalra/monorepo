import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import { initIframeAuth } from './utils/iframeAuth'
import './index.css'
import FoodApp from './components/FoodApp'

initIframeAuth()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AuthProvider>
      <BrowserRouter basename="/app/food">
        <FoodApp />
      </BrowserRouter>
    </AuthProvider>
  </StrictMode>,
)
