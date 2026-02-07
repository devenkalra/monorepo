# Multi-User System Implementation Plan

## Status: IN PROGRESS

### ✅ Completed
1. Added `user` ForeignKey to Entity model
2. Created migrations (0010, 0011)
3. Assigned existing entities to default_user
4. 13 entities successfully migrated

### 🔄 In Progress
Making user field non-nullable and implementing authentication

### 📋 Remaining Tasks

#### Phase 2: Authentication Setup
- [ ] Install django-cors-headers and djangorestframework-simplejwt
- [ ] Configure CORS settings
- [ ] Set up JWT authentication
- [ ] Create authentication endpoints (login, register, logout, whoami)

#### Phase 3: Permissions & Isolation
- [ ] Create IsOwner permission class
- [ ] Update all viewsets to filter by user
- [ ] Update serializers to handle user field
- [ ] Auto-assign user on entity creation (signals)

#### Phase 4: View Updates
- [ ] EntityViewSet - filter by request.user
- [ ] PersonViewSet - filter by request.user
- [ ] NoteViewSet - filter by request.user
- [ ] ConversationViewSet - filter by request.user
- [ ] EntityRelationViewSet - ensure both entities belong to user
- [ ] SearchViewSet - filter results by user

#### Phase 5: Management Commands
- [ ] Update import_chats to accept --user parameter
- [ ] Update update_conversation_descriptions for user filtering
- [ ] Create assign_entities_to_user command

#### Phase 6: Testing
- [ ] Create test users
- [ ] Test entity isolation
- [ ] Test conversation isolation
- [ ] Test search filtering
- [ ] Test relationships across users (should fail)

### Architecture

```
Client (Frontend)
    ↓
  [Login with JWT]
    ↓
Django REST API
    ↓
  [Authentication Middleware]
    ↓
  [Permission Check: IsOwner]
    ↓
  [Filter QuerySet by request.user]
    ↓
Database (user-isolated data)
```

### Key Changes Required

1. **Settings.py**
   - Add rest_framework_simplejwt
   - Configure JWT settings
   - Add CORS headers

2. **Views.py**
   - Add permission_classes = [IsAuthenticated, IsOwner]
   - Filter queryset: `.filter(user=request.user)`
   - Set user on create: `serializer.save(user=request.user)`

3. **Serializers.py**
   - Add `user` to read_only_fields
   - Remove from writable fields

4. **URLs.py**
   - Add /api/auth/login/
   - Add /api/auth/register/
   - Add /api/auth/logout/
   - Add /api/auth/whoami/

5. **Signals.py**
   - Auto-set user from request context

### Security Considerations

1. **Never expose other users' data**
   - All queries filtered by user
   - Relationships checked for ownership
   
2. **JWT Token Security**
   - Short access token lifetime (5 minutes)
   - Longer refresh token (24 hours)
   - HTTP-only cookies for tokens

3. **Permission Checks**
   - IsAuthenticated for all endpoints
   - IsOwner for detail views
   - Custom permissions for relations

### API Changes

#### Before (No Auth)
```bash
GET /api/conversations/
# Returns ALL conversations
```

#### After (With Auth)
```bash
GET /api/conversations/
Authorization: Bearer <jwt_token>
# Returns only current user's conversations
```

### Next Steps

1. Continue with Phase 2 - Install packages and configure authentication
2. Implement IsOwner permission class
3. Update all viewsets with user filtering
4. Test with multiple users

