# Email Frontend

Standalone React application for the Email Archive system.

## Features

- Email viewer with search, filtering, and pagination
- Import manager for configuring email accounts and import rules
- Progress tracking for long-running imports
- Dark mode support
- Authentication via Django backend

## Development

### Standalone Development Server

Run the development server directly:

```bash
cd /home/ubuntu/monorepo/email-frontend
npm install
npm run dev
```

The app will be available at `http://localhost:5176`

### Docker Development

Run via Docker Compose from the monorepo root:

```bash
cd /home/ubuntu/monorepo
docker compose -f docker-compose.local.yml up email-frontend-dev --build
```

The app will be available at `http://localhost:5176`

### Production Build

The email-frontend is built and served via nginx as part of the main frontend container at `/email-app/`:

```bash
cd /home/ubuntu/monorepo
docker compose -f docker-compose.local.yml up frontend --build
```

The app will be available at `http://localhost/email-app/`

## Architecture

- **React 19** with hooks
- **React Router** for navigation
- **TailwindCSS** for styling
- **Vite** for build tooling
- **JWT** authentication via Django backend

## Components

- `App.jsx` - Main app with routing and tab navigation
- `Login.jsx` - Authentication form
- `EmailViewer.jsx` - Email list and detail view
- `EmailImporter.jsx` - Account and import config management
- `ProgressModal.jsx` - Async task progress tracking
- `Header.jsx` - App header with theme toggle and user menu
- `ThemeToggle.jsx` - Dark/light mode toggle

## API Integration

All API calls go through the `api.js` service which:
- Automatically adds authentication headers
- Handles API base URL configuration
- Proxies requests to Django backend at port 8000
