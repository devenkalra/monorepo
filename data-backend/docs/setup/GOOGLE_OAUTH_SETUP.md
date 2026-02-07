# Google OAuth Setup Guide

## Step 1: Create Google OAuth Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the **Google+ API** (or Google People API)
4. Go to **Credentials** → **Create Credentials** → **OAuth 2.0 Client ID**
5. Configure the OAuth consent screen:
   - User Type: External (for testing) or Internal (for organization)
   - App name: Your app name
   - User support email: Your email
   - Developer contact: Your email
6. Create OAuth 2.0 Client ID:
   - Application type: **Web application**
   - Name: Your app name
   - Authorized JavaScript origins:
     - `http://localhost:3000`
     - `http://localhost:8001`
   - Authorized redirect URIs:
     - `http://localhost:3000/auth/google/callback`
     - `http://localhost:8001/accounts/google/login/callback/`
7. Copy the **Client ID** and **Client Secret**

## Step 2: Configure Django Backend

### Option A: Using Django Admin (Recommended for development)

1. Start your Django server:
   ```bash
   cd /home/ubuntu/monorepo/data-backend
   source .venv/bin/activate
   python manage.py runserver 8001
   ```

2. Go to Django Admin: http://localhost:8001/admin/

3. Log in with your superuser account (create one if needed):
   ```bash
   python manage.py createsuperuser
   ```

4. Navigate to **Sites** → Click on "example.com" → Change to:
   - Domain name: `localhost:8001`
   - Display name: `localhost:8001`
   - Save

5. Navigate to **Social applications** → **Add social application**
   - Provider: **Google**
   - Name: `Google OAuth`
   - Client id: *Paste your Google Client ID*
   - Secret key: *Paste your Google Client Secret*
   - Sites: Select `localhost:8001` and move it to "Chosen sites"
   - Save

### Option B: Using Environment Variables

1. Create a `.env` file in `/home/ubuntu/monorepo/data-backend/`:
   ```bash
   GOOGLE_OAUTH_CLIENT_ID=your-client-id.apps.googleusercontent.com
   GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret
   ```

2. Install python-decouple:
   ```bash
   pip install python-decouple
   ```

3. Update `settings.py` to read from environment variables (already configured)

## Step 3: Frontend Configuration

The frontend React app will use the Google OAuth flow. No additional configuration needed in the frontend code - just ensure the backend is running.

## Step 4: Test the OAuth Flow

1. Start the Django backend:
   ```bash
   cd /home/ubuntu/monorepo/data-backend
   source .venv/bin/activate
   python manage.py runserver 8001
   ```

2. Start the React frontend:
   ```bash
   cd /home/ubuntu/monorepo/data-backend/frontend
   npm run dev
   ```

3. Open http://localhost:3000/login

4. Click "Sign in with Google"

5. Complete the Google OAuth flow

6. You should be redirected back to the app and logged in

## Troubleshooting

### "redirect_uri_mismatch" error
- Ensure the redirect URI in Google Console matches exactly: `http://localhost:3000/auth/google/callback`
- Check that there are no trailing slashes

### "Google OAuth not configured" error
- Ensure you've added the Social Application in Django Admin
- Check that the Site is set to `localhost:8001`

### CORS errors
- Ensure `CORS_ALLOWED_ORIGINS` in `settings.py` includes `http://localhost:3000`

## Production Deployment

For production, update:
1. Authorized JavaScript origins to your production domain
2. Authorized redirect URIs to your production callback URL
3. Update `FRONTEND_URL` in settings
4. Set `DEBUG=False` in Django settings
5. Use HTTPS for all URLs
