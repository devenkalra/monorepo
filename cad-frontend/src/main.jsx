import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import './index.css'
import CadApp from './components/CadApp'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AuthProvider>
      <BrowserRouter basename="/cad-app">
        <CadApp />
      </BrowserRouter>
    </AuthProvider>
  </StrictMode>,
)
