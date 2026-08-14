import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import './index.css'
import CadApp from './components/CadApp'
import ProfileEdit from './components/ProfileEdit'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AuthProvider>
      <BrowserRouter basename="/app/cad">
        <Routes>
          <Route path="/profile" element={<ProfileEdit />} />
          <Route path="/*" element={<CadApp />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  </StrictMode>,
)
