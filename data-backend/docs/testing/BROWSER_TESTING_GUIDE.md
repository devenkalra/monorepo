# Browser Testing Guide

## 🌐 Access the Login Page

**Open in your browser:**
```
http://localhost:8001/
```

You'll see a modern login interface with:
- **Login tab** - For existing users
- **Register tab** - For new users
- **Test user shortcuts** - Click to auto-fill credentials
- **Social login buttons** - Google and GitHub (after setup)

---

## 🧪 Test Scenarios

### Scenario 1: Login with Test User

1. **Open:** http://localhost:8001/
2. **Click on test user:** `alice@example.com / testpass123`
3. **Click "Login"**
4. **See dashboard** with:
   - User info (Welcome, alice!)
   - Statistics (Entities, People, Notes, Conversations)
   - Recent entities list

### Scenario 2: Register New User

1. **Click "Register" tab**
2. **Fill in:**
   - Email: `charlie@example.com`
   - Password: `testpass123`
   - Confirm: `testpass123`
3. **Click "Register"**
4. **Automatically logged in** and shown dashboard
5. **Notice:** 0 entities (isolated from alice and bob)

### Scenario 3: Test Data Isolation

1. **Login as alice** (alice@example.com)
2. **Note her entity count** (e.g., 1 entity)
3. **Logout** (click Logout button)
4. **Login as bob** (bob@example.com)
5. **Notice different entity count** (e.g., 1 entity, but different)
6. **Verify:** Bob cannot see Alice's entities

### Scenario 4: Create Entity via API Console

1. **Login as alice**
2. **Open browser console** (F12)
3. **Run:**
```javascript
// Get token
const token = localStorage.getItem('access_token');

// Create a person
fetch('http://localhost:8001/api/people/', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    first_name: 'Jane',
    last_name: 'Doe',
    description: 'Created via browser console'
  })
}).then(r => r.json()).then(console.log);
```
4. **Refresh page** - See new entity in dashboard

---

## 🔍 Using Browser Developer Tools

### View Your Token
```javascript
// In browser console (F12)
console.log('Access Token:', localStorage.getItem('access_token'));
console.log('Refresh Token:', localStorage.getItem('refresh_token'));
console.log('User:', JSON.parse(localStorage.getItem('current_user')));
```

### Make API Calls
```javascript
const token = localStorage.getItem('access_token');

// Get all entities
fetch('http://localhost:8001/api/entities/', {
  headers: {'Authorization': `Bearer ${token}`}
})
.then(r => r.json())
.then(data => console.log('Entities:', data));

// Get all conversations
fetch('http://localhost:8001/api/conversations/', {
  headers: {'Authorization': `Bearer ${token}`}
})
.then(r => r.json())
.then(data => console.log('Conversations:', data));

// Search
fetch('http://localhost:8001/api/search/?q=test', {
  headers: {'Authorization': `Bearer ${token}`}
})
.then(r => r.json())
.then(data => console.log('Search results:', data));
```

### Test Token Refresh
```javascript
const refresh = localStorage.getItem('refresh_token');

fetch('http://localhost:8001/api/auth/token/refresh/', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({refresh})
})
.then(r => r.json())
.then(data => {
  console.log('New access token:', data.access);
  localStorage.setItem('access_token', data.access);
});
```

---

## 🛠️ Django Admin Interface

Django Admin provides a powerful interface to manage users, entities, and social apps.

### Access Django Admin

1. **Create superuser** (if not exists):
```bash
cd /home/ubuntu/monorepo/data-backend
source .venv/bin/activate
python manage.py createsuperuser
# Follow prompts: email, password
```

2. **Access:** http://localhost:8001/admin/
3. **Login** with superuser credentials

### What You Can Do in Admin

**Users & Authentication:**
- View all registered users
- Create/edit users
- Assign permissions
- View login sessions

**Social Applications:**
- Add Google OAuth credentials
- Add GitHub OAuth credentials
- Configure callback URLs

**Entities:**
- View all entities
- See which user owns each entity
- Manually assign entities to users
- Delete entities

**Conversations:**
- View all conversations
- See conversation turns
- Edit metadata

**Sites:**
- Configure site domain (required for social auth)
- Update site name

---

## 🔧 Configure Social Login (Optional)

### Setup Google OAuth

1. **Get Credentials:**
   - Go to https://console.cloud.google.com/
   - Create project → APIs & Services → Credentials
   - Create OAuth 2.0 Client ID
   - Application type: Web application
   - Authorized redirect URI: `http://localhost:8001/accounts/google/login/callback/`

2. **Add to Django Admin:**
   - Go to http://localhost:8001/admin/
   - Social applications → Add
   - Provider: Google
   - Name: Google OAuth
   - Client ID: (from console)
   - Secret key: (from console)
   - Sites: localhost (select)
   - Save

3. **Test:**
   - On login page, click "Continue with Google"
   - Should redirect to Google login
   - After auth, redirects back with token

### Setup GitHub OAuth

1. **Get Credentials:**
   - Go to https://github.com/settings/developers
   - New OAuth App
   - Homepage URL: `http://localhost:8001`
   - Callback URL: `http://localhost:8001/accounts/github/login/callback/`

2. **Add to Django Admin:**
   - Social applications → Add
   - Provider: GitHub
   - Client ID & Secret from GitHub
   - Save

3. **Test:**
   - Click "Continue with GitHub" on login page

---

## 🎯 Test Multi-User Isolation in Browser

### Method 1: Multiple Browser Windows

1. **Window 1:** Login as alice@example.com
2. **Window 2:** Login as bob@example.com (use Incognito/Private)
3. **Compare:** Each shows different entities

### Method 2: Browser Console

```javascript
// Login as Alice
fetch('http://localhost:8001/api/auth/login/', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    email: 'alice@example.com',
    password: 'testpass123'
  })
}).then(r => r.json()).then(data => {
  const aliceToken = data.access;
  
  // Get Alice's entities
  return fetch('http://localhost:8001/api/entities/', {
    headers: {'Authorization': `Bearer ${aliceToken}`}
  });
}).then(r => r.json()).then(data => {
  console.log('Alice entities:', data);
});

// Login as Bob (in same console)
fetch('http://localhost:8001/api/auth/login/', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    email: 'bob@example.com',
    password: 'testpass123'
  })
}).then(r => r.json()).then(data => {
  const bobToken = data.access;
  
  // Get Bob's entities
  return fetch('http://localhost:8001/api/entities/', {
    headers: {'Authorization': `Bearer ${bobToken}`}
  });
}).then(r => r.json()).then(data => {
  console.log('Bob entities:', data);
});
```

---

## 🔐 Test Security in Browser

### Test 1: Access Without Token (Should Fail)
```javascript
fetch('http://localhost:8001/api/entities/')
  .then(r => r.json())
  .then(data => console.log(data));
// Expected: {detail: "Authentication credentials were not provided."}
```

### Test 2: Access With Invalid Token (Should Fail)
```javascript
fetch('http://localhost:8001/api/entities/', {
  headers: {'Authorization': 'Bearer invalid_token'}
})
  .then(r => r.json())
  .then(data => console.log(data));
// Expected: {detail: "Given token not valid for any token type"}
```

### Test 3: Access Other User's Entity (Should Fail)
```javascript
// Login as Alice, get her entity ID
// Then login as Bob
// Try to access Alice's entity ID with Bob's token
fetch(`http://localhost:8001/api/people/ALICE_ENTITY_ID/`, {
  headers: {'Authorization': `Bearer ${bobToken}`}
})
  .then(r => r.json())
  .then(data => console.log(data));
// Expected: {detail: "Not found."}
```

---

## 📱 Network Tab Inspection

### View API Calls

1. **Open DevTools** (F12)
2. **Go to Network tab**
3. **Login or make API call**
4. **Click on request** to see:
   - Request headers (Authorization: Bearer ...)
   - Response data
   - Status codes
   - Timing

### Check CORS Headers

Look for these response headers:
- `Access-Control-Allow-Origin: http://localhost:3000`
- `Access-Control-Allow-Credentials: true`

---

## 🎨 Customize Login Page

The login page is at `/home/ubuntu/monorepo/data-backend/static/login.html`

**Edit to:**
- Change colors/branding
- Add your logo
- Modify layout
- Add custom fields
- Change redirect after login

**Example customizations:**
```html
<!-- Add logo -->
<div class="header">
    <img src="/static/logo.png" alt="Logo" style="width: 80px;">
    <h1>Your App Name</h1>
</div>

<!-- Change gradient colors -->
<style>
    body {
        background: linear-gradient(135deg, #YOUR_COLOR1 0%, #YOUR_COLOR2 100%);
    }
</style>
```

---

## 🚀 Next Steps for Frontend Integration

### Option 1: Use the Provided Login Page
- Customize `static/login.html`
- Add links to your main app
- Use as landing page

### Option 2: Build Your Own React/Vue/Angular Frontend
- Use the API endpoints
- Implement login/register forms
- Store tokens in localStorage
- Add Authorization header to all requests

### Option 3: Integrate with Existing Frontend
- Add authentication layer
- Protect routes with login check
- Auto-refresh tokens on expiry

---

## 🐛 Troubleshooting

### Login Page Not Loading
```bash
# Check server is running
ps aux | grep "manage.py runserver"

# Check logs
tail -f /tmp/django_browser.log

# Restart server
lsof -ti:8001 | xargs kill -9
cd ~/monorepo/data-backend
source .venv/bin/activate
python manage.py runserver 8001
```

### CORS Errors in Browser Console
Check `config/settings.py`:
```python
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    # Add your frontend URL
]
```

### 401 Errors After Login
- Token might be expired (1 hour default)
- Check localStorage has valid token
- Try refreshing token or re-login

---

## 📊 Verify Everything is Working

Run this in browser console after login:
```javascript
const token = localStorage.getItem('access_token');

// Test all endpoints
const tests = [
    {name: 'Entities', url: '/api/entities/'},
    {name: 'People', url: '/api/people/'},
    {name: 'Notes', url: '/api/notes/'},
    {name: 'Conversations', url: '/api/conversations/'},
    {name: 'Recent', url: '/api/entities/recent/'},
];

for (const test of tests) {
    fetch(`http://localhost:8001${test.url}`, {
        headers: {'Authorization': `Bearer ${token}`}
    })
    .then(r => r.json())
    .then(data => {
        const count = data.count || data.results?.length || data.length || 0;
        console.log(`✓ ${test.name}: ${count} items`);
    })
    .catch(err => console.error(`✗ ${test.name}:`, err));
}
```

Expected output:
```
✓ Entities: 1 items
✓ People: 1 items
✓ Notes: 0 items
✓ Conversations: 0 items
✓ Recent: 1 items
```

---

## 🎉 Success!

You now have:
- ✅ Browser-based login interface
- ✅ Django Admin for management
- ✅ Full API access via JavaScript
- ✅ Multiple testing methods
- ✅ Ready for frontend integration

**Open http://localhost:8001/ to start testing!**
