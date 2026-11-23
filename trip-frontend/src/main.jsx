import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import TripApp from './components/TripApp'
import { PublicTripView } from './components/TripCollaboration'
import NavLab from './navlab/NavLab'
import './index.css'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AuthProvider>
      <BrowserRouter basename="/app/trips">
        <Routes>
          <Route path="/share/:token" element={<PublicTripView />} />
          <Route path="/nav-lab" element={<NavLab />} />
          <Route path="*" element={<TripApp />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  </StrictMode>,
)
