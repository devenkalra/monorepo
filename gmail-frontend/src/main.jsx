import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import GmailApp from './components/GmailApp'
import './index.css'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AuthProvider>
      <BrowserRouter basename="/app/gmail">
        <GmailApp />
      </BrowserRouter>
    </AuthProvider>
  </StrictMode>,
)
