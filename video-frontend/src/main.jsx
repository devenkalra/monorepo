import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import ProductionsApp from './components/ProductionsApp'
import './index.css'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AuthProvider>
      <BrowserRouter basename="/app/productions">
        <ProductionsApp />
      </BrowserRouter>
    </AuthProvider>
  </StrictMode>,
)
