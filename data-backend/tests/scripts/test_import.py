import requests
import json
import sys
import os

# Get email from command line argument
user_email = sys.argv[2] if len(sys.argv) > 2 else 'test@example.com'
username = user_email.split('@')[0]
password = 'testpass123'

# First, create a test user and get a token
print(f"Creating test user {user_email}...")
register_response = requests.post(
    'http://localhost:8000/api/auth/registration/',
    json={
        'username': username,
        'email': user_email,
        'password1': password,
        'password2': password
    }
)

if register_response.status_code in [200, 201]:
    print("✓ User created")
    token_data = register_response.json()
    access_token = token_data.get('access_token') or token_data.get('access')
elif register_response.status_code == 400:
    # User might already exist, try to login
    print("User exists, logging in...")
    login_response = requests.post(
        'http://localhost:8000/api/auth/login/',
        json={
            'email': user_email,
            'password': password
        }
    )
    if login_response.status_code == 200:
        print("✓ Logged in")
        token_data = login_response.json()
        access_token = token_data.get('access_token') or token_data.get('access')
    else:
        print(f"✗ Login failed: {login_response.status_code}")
        print(login_response.text)
        exit(1)
else:
    print(f"✗ Registration failed: {register_response.status_code}")
    print(register_response.text)
    exit(1)

print(f"\nAccess token: {access_token[:20]}...")

# Now try to import
print("\nAttempting import...")
import_file = sys.argv[1] if len(sys.argv) > 1 else '/home/ubuntu/data/bldrdojo/import_data.json'
print(f"Import file: {import_file}")

with open(import_file, 'rb') as f:
    files = {'file': (os.path.basename(import_file), f, 'application/json')}
    headers = {'Authorization': f'Bearer {access_token}'}
    
    response = requests.post(
        'http://localhost:8000/api/orgs/import_data/',
        files=files,
        headers=headers
    )

print(f"\nStatus: {response.status_code}")
print(f"Response:")
result = response.json()
print(json.dumps(result, indent=2))

if 'errors' in result and result['errors']:
    print(f"\n⚠️  {len(result['errors'])} errors found:")
    for i, error in enumerate(result['errors'][:10], 1):
        print(f"   {i}. {error}")
    if len(result['errors']) > 10:
        print(f"   ... and {len(result['errors']) - 10} more errors")
