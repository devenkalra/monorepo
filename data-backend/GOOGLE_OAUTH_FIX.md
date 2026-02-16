# Google OAuth Configuration Fix

## Changes Made

### 1. Removed Hardcoded localhost URLs

**File: `people/social_auth_views.py`**
- Changed hardcoded `http://localhost:5174/auth/google/callback` to use `settings.GOOGLE_OAUTH_CALLBACK_URL`
- Both the `GoogleLogin` class and `google_login_redirect` function now use the configured callback URL

### 2. Added Configuration Setting

**File: `config/settings.py`**
- Added `GOOGLE_OAUTH_CALLBACK_URL` setting that reads from environment variable
- Default value: `http://localhost:5174/auth/google/callback` (for local development)
- Production value should be: `https://bldrdojo.com/auth/google/callback`

### 3. Updated Docker Compose

**File: `docker-compose.yml`**
- Added `GOOGLE_OAUTH_CALLBACK_URL` environment variable to backend service
- Default value set to: `https://bldrdojo.com/auth/google/callback`

## Frontend OAuth Flow

The frontend is properly configured:
- **Login Button**: `GoogleLoginButton.jsx` fetches OAuth URL from backend API
- **Callback Route**: `/auth/google/callback` handled by `GoogleCallback.jsx`
- **Token Storage**: Stores JWT tokens in localStorage after successful auth

## Required Actions

### 1. Update Google OAuth Console

You need to update your Google OAuth application's authorized redirect URIs:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to: APIs & Services > Credentials
3. Click on your OAuth 2.0 Client ID
4. Under "Authorized redirect URIs", add **all** of these that apply:

   **Production:**
   - `https://bldrdojo.com/auth/google/callback`
   - `https://bldrdojo.com/accounts/google/login/callback/`

   **Local development (login page uses allauth):**
   - `http://localhost/accounts/google/login/callback/` ← **required for local Google login**
   - `http://127.0.0.1/accounts/google/login/callback/`

   **Local development (people-frontend custom flow, if used):**
   - `http://localhost/people-app/auth/google/callback`
   - `http://localhost:5174/auth/google/callback`

5. Save the changes

### 2. Set Environment Variable (Optional)

The docker-compose.yml already sets the default to `https://bldrdojo.com/auth/google/callback`.

If you need to override it, add to your `.env` file:

```bash
GOOGLE_OAUTH_CALLBACK_URL=https://bldrdojo.com/auth/google/callback
```

### 3. Restart Backend Service

```bash
docker compose restart backend
```

## Testing

After making these changes, test the Google OAuth flow:

1. Navigate to `https://bldrdojo.com` (or click login if not authenticated)
2. Click "Continue with Google"
3. You should be redirected to Google's OAuth consent screen
4. After approving, you should be redirected back to `https://bldrdojo.com/auth/google/callback`
5. The frontend will exchange the code for tokens and log you in

## Troubleshooting

### Username/password works, Google doesn't (localhost)

The login page uses **django-allauth** directly: clicking "Google" goes to `/accounts/google/login/`. Google redirects back to:

- `http://localhost/accounts/google/login/callback/` (when using nginx on port 80)

**Fix:** Add this exact URL to Google Cloud Console → Credentials → your OAuth client → Authorized redirect URIs. The URL must match exactly (including trailing slash).

### redirect_uri_mismatch error

- Check that the redirect URI in Google Console exactly matches what your app uses
- For localhost login page: `http://localhost/accounts/google/login/callback/`
- For production: `https://bldrdojo.com/accounts/google/login/callback/` or `https://bldrdojo.com/auth/google/callback`
- Make sure there are no typos; trailing slashes matter

### Authentication fails after callback

- Check backend logs: `docker compose logs backend --tail 50`
- Verify the Google OAuth credentials are properly configured in Django admin
- Test the backend endpoint: `curl https://bldrdojo.com/api/auth/google/url/`

## Production Deployment

For production (bldrdojo.com), ensure:

1. **`data-backend/.env`** has:
   ```
   GOOGLE_CLIENT_ID=your-actual-client-id.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=your-actual-client-secret
   GOOGLE_OAUTH_CALLBACK_URL=https://bldrdojo.com/auth/google/callback
   DJANGO_ALLOWED_HOSTS=bldrdojo.com,www.bldrdojo.com
   DJANGO_CSRF_TRUSTED_ORIGINS=https://bldrdojo.com,https://www.bldrdojo.com
   ```

2. **Google Cloud Console** → Authorized redirect URIs:
   - `https://bldrdojo.com/accounts/google/login/callback/` (allauth login page)
   - `https://bldrdojo.com/auth/google/callback` (people-app custom flow)

3. **Deploy** – the deploy script runs `setup_google_oauth --domain="bldrdojo.com"` automatically. If credentials are missing, run manually after deploy:
   ```bash
   docker compose -f docker-compose.production.yml exec backend python manage.py setup_google_oauth --domain="bldrdojo.com"
   ```

4. **CSRF** – already configured when `bldrdojo.com` is in `ALLOWED_HOSTS`; the login page sends the CSRF token from the cookie.

## Note on Registration Issue

The username requirement issue is still pending. The current workaround is to make username optional in the `CustomRegisterSerializer`, but there may be a deeper issue with how `dj-rest-auth` validates the fields. This needs further investigation.

Possible solutions:
1. Create a custom User model that doesn't require username
2. Use a different authentication library
3. Debug why the `CustomRegisterSerializer` field removal isn't working
