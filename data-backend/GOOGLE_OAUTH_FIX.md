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
4. Under "Authorized redirect URIs", **add**:
   - `https://bldrdojo.com/auth/google/callback`
5. **Keep the existing localhost URIs** for local development:
   - `http://localhost:5174/auth/google/callback`
6. Save the changes

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

If you see "redirect_uri_mismatch" error:
- Check that the redirect URI in Google Console exactly matches: `https://bldrdojo.com/auth/google/callback`
- Make sure there are no trailing slashes or typos
- Verify the backend is using the correct `GOOGLE_OAUTH_CALLBACK_URL`

If authentication fails after callback:
- Check backend logs: `docker compose logs backend --tail 50`
- Verify the Google OAuth credentials are properly configured in Django admin
- Test the backend endpoint: `curl https://bldrdojo.com/api/auth/google/url/`

## Note on Registration Issue

The username requirement issue is still pending. The current workaround is to make username optional in the `CustomRegisterSerializer`, but there may be a deeper issue with how `dj-rest-auth` validates the fields. This needs further investigation.

Possible solutions:
1. Create a custom User model that doesn't require username
2. Use a different authentication library
3. Debug why the `CustomRegisterSerializer` field removal isn't working
