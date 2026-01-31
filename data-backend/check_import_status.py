import requests
import json

# Login
login_response = requests.post(
    'http://localhost:8001/api/auth/login/',
    json={
        'email': 'test@example.com',
        'password': 'testpass123'
    }
)

if login_response.status_code != 200:
    print(f"Login failed: {login_response.status_code}")
    exit(1)

token = login_response.json().get('access_token') or login_response.json().get('access')
headers = {'Authorization': f'Bearer {token}'}

# Try a fresh import
print("Attempting fresh import...")
with open('/home/ubuntu/data/bldrdojo/import_data.json', 'rb') as f:
    files = {'file': ('import_data.json', f, 'application/json')}
    
    response = requests.post(
        'http://localhost:8001/api/notes/import_data/',
        files=files,
        headers=headers
    )

print(f"\nStatus: {response.status_code}")
result = response.json()

print(f"\n📊 Import Results:")
print(f"   Success: {result.get('success', False)}")
print(f"   Message: {result.get('message', 'N/A')}")

if 'stats' in result:
    stats = result['stats']
    print(f"\n📈 Statistics:")
    print(f"   People created: {stats.get('people_created', 0)}")
    print(f"   People updated: {stats.get('people_updated', 0)}")
    print(f"   Relations created: {stats.get('relations_created', 0)}")
    print(f"   Relations updated: {stats.get('relations_updated', 0)}")
    print(f"   Errors: {len(stats.get('errors', []))}")
    
    if stats.get('errors'):
        print(f"\n⚠️  Error Details:")
        for i, error in enumerate(stats['errors'][:10], 1):
            print(f"   {i}. {error}")
        if len(stats['errors']) > 10:
            print(f"   ... and {len(stats['errors']) - 10} more")
    else:
        print(f"\n✅ No errors!")

print(json.dumps(result, indent=2))
