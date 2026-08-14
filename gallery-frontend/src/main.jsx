import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import GalleryApp from './components/GalleryApp'
import PublicGallery from './components/PublicGallery'
import './index.css'

const path = window.location.pathname
const publicMatch = path.match(/^\/([^/]+)\/gallery\/([^/]+)\/?$/)
const isPublic = publicMatch && publicMatch[1] !== 'app'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AuthProvider>
      {isPublic ? (
        <PublicGallery username={publicMatch[1]} slug={publicMatch[2]} />
      ) : (
        <BrowserRouter basename="/app/gallery">
          <GalleryApp />
        </BrowserRouter>
      )}
    </AuthProvider>
  </StrictMode>,
)
