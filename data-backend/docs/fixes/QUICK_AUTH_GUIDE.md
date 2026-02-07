# Quick Authentication Guide

## Test the System Right Now

```bash
# 1. Login as Alice
curl -X POST http://localhost:8001/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"testpass123"}'

# Save the "access" token from response

# 2. Get Alice's entities
curl http://localhost:8001/api/entities/ \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"

# 3. Create a new person
curl -X POST http://localhost:8001/api/people/ \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{"first_name":"Test","last_name":"User","description":"Testing"}'
```

## Test Users

| Username | Email | Password |
|----------|-------|----------|
| alice | alice@example.com | testpass123 |
| bob | bob@example.com | testpass123 |
| default_user | default@example.com | (owns legacy data) |

## Key Endpoints

- **Login:** `POST /api/auth/login/`
- **Register:** `POST /api/auth/registration/`
- **Logout:** `POST /api/auth/logout/`
- **Refresh:** `POST /api/auth/token/refresh/`
- **Entities:** `GET /api/entities/` (auto-filtered by user)
- **People:** `GET /api/people/` (auto-filtered by user)
- **Conversations:** `GET /api/conversations/` (auto-filtered by user)
- **Search:** `GET /api/search/?q=query` (auto-filtered by user)

## Token Lifetime

- **Access Token:** 1 hour
- **Refresh Token:** 7 days

## What Changed?

✅ Every API endpoint now requires authentication  
✅ Each user sees only their own data  
✅ Creating entities automatically assigns to current user  
✅ JWT tokens used for stateless authentication  
✅ Social login ready (Google, GitHub)

## Run Tests

```bash
/tmp/test_multiuser.sh
```

