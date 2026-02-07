# API Coverage Analysis

## Frontend API Calls vs Integration Test Coverage

### ✅ **COVERED** - API endpoints used in frontend that ARE tested:

1. **Search & Entities**
   - `GET /api/search/?q=...` ✅ (tested in test_09, test_17, test_20)
   - `GET /api/search/?tags=...` ✅ (tested in test_01, test_04, test_09, etc.)
   - `GET /api/search/?type=...` ✅ (tested in test_09)
   - `GET /api/search/?display=...` ✅ (tested in test_20)
   - `GET /api/search/count/?tags=...` ✅ (tested in test_05, test_21)
   - `POST /api/search/delete_all/?tags=...` ✅ (tested in test_05, test_19)
   - `GET /api/entities/{id}/` ✅ (tested indirectly through model creation)
   - `DELETE /api/entities/{id}/` ✅ (tested in test_01)

2. **People**
   - `POST /api/people/` ✅ (tested in test_01, test_08, etc.)
   - `PATCH /api/people/{id}/` ✅ (tested in test_01)
   - `DELETE /api/people/{id}/` ✅ (tested in test_01)

3. **Relations**
   - `GET /api/entities/{id}/relations/` ✅ (tested in test_04)
   - `POST /api/relations/` ✅ (tested in test_04, test_14)
   - `DELETE /api/relations/{id}/` ✅ (tested in test_04)

4. **Tags**
   - `GET /api/tags/?limit=...` ✅ (tested in test_18)

5. **Import/Export**
   - `GET /api/entities/export/` ✅ (tested in test_07, CrossUserImportExportTest)
   - `POST /api/entities/import_data/` ✅ (tested in test_07, CrossUserImportExportTest)

---

### ❌ **NOT COVERED** - API endpoints used in frontend that are NOT tested:

1. **Authentication** (AuthContext.jsx, GoogleCallback.jsx, GoogleLoginButton.jsx)
   - `POST /api/auth/login/` ❌
   - `POST /api/auth/registration/` ❌
   - `POST /api/auth/logout/` ❌
   - `POST /api/auth/token/refresh/` ❌
   - `GET /api/auth/google/url/` ❌
   - `POST /api/auth/google/` ❌
   - `GET /api/auth/user/` ❌

2. **File Upload** (EntityDetail.jsx, RichTextEditor.jsx)
   - `POST /api/upload/` ❌

3. **Notes/Conversation Import** (UserMenu.jsx, ConversationImport.jsx)
   - `POST /api/notes/import_file/` ❌

4. **Entity Update** (EntityDetail.jsx)
   - `PATCH /api/entities/{id}/` ❌ (only tested for specific types like Person)
   - `PUT /api/entities/{id}/` ❌

5. **Relation Update** (EntityDetail.jsx)
   - `PATCH /api/relations/{id}/` ❌

---

## Summary

### Coverage Statistics:
- **Total unique API endpoints used in frontend**: ~20
- **Covered by integration tests**: ~13 (65%)
- **Not covered**: ~7 (35%)

### Priority for Additional Tests:

#### **HIGH PRIORITY** (Core functionality):
1. ✅ Authentication flows (login, registration, logout, token refresh)
2. ✅ File upload functionality
3. ✅ Entity PATCH/PUT operations (generic Entity, not just Person)

#### **MEDIUM PRIORITY** (Important features):
4. ✅ Notes/conversation import
5. ✅ Relation update (PATCH)

#### **LOW PRIORITY** (Already partially covered or less critical):
6. Google OAuth flow (complex, may require mocking)

---

## Recommendations:

### 1. Add Authentication Tests
```python
class AuthenticationTest(TransactionTestCase):
    def test_user_registration(self):
        # POST /api/auth/registration/
        
    def test_user_login(self):
        # POST /api/auth/login/
        
    def test_token_refresh(self):
        # POST /api/auth/token/refresh/
        
    def test_logout(self):
        # POST /api/auth/logout/
```

### 2. Add File Upload Tests
```python
class FileUploadTest(TransactionTestCase):
    def test_upload_image(self):
        # POST /api/upload/ with image file
        
    def test_upload_attachment(self):
        # POST /api/upload/ with document
```

### 3. Add Generic Entity Update Tests
```python
class EntityUpdateTest(TransactionTestCase):
    def test_patch_entity(self):
        # PATCH /api/entities/{id}/
        
    def test_put_entity(self):
        # PUT /api/entities/{id}/
```

### 4. Add Notes Import Test
```python
class NotesImportTest(TransactionTestCase):
    def test_import_chatgpt_conversations(self):
        # POST /api/notes/import_file/ with ChatGPT export
        
    def test_import_claude_conversations(self):
        # POST /api/notes/import_file/ with Claude export
```

### 5. Add Relation Update Test
```python
class RelationUpdateTest(TransactionTestCase):
    def test_patch_relation(self):
        # PATCH /api/relations/{id}/
```

---

## Notes:
- The integration tests focus heavily on **search, tags, and hierarchical features**
- **CRUD operations** are well-covered for Person entities but not for generic Entity or other types
- **Authentication** is completely untested at the integration level (may have unit tests)
- **File upload** is a critical feature that should be tested
- The **cross-user import/export** test was just added and provides excellent coverage for that feature
