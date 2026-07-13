import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import { EncryptionProvider } from './contexts/EncryptionContext'
import './index.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AuthProvider>
      <EncryptionProvider>
        <BrowserRouter basename="/people-app">
          <App />
        </BrowserRouter>
      </EncryptionProvider>
    </AuthProvider>
  </StrictMode>,
)
