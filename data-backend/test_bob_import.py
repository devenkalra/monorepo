import requests
import json

print("Testing import for Bob...")
print("="*70)

# Login as Bob
login_response = requests.post(
    'http://localhost:8001/api/auth/login/',
    json={
        'email': 'bob@example.com',
        'password': 'testpass123'
    }
)

if login_response.status_code != 200:
    print(f"Login failed: {login_response.status_code}")
    print(login_response.json())
    exit(1)

token = login_response.json().get('access_token') or login_response.json().get('access')
print(f"✓ Logged in as Bob")

headers = {'Authorization': f'Bearer {token}'}

# Check Bob's current entities
print("\n📊 Bob's data BEFORE import:")
people_response = requests.get('http://localhost:8001/api/people/', headers=headers)
people_data = people_response.json()
before_count = people_data.get('count', 0) if isinstance(people_data, dict) else len(people_data)
print(f"   People: {before_count}")

# Import
print("\n📥 Importing...")
with open('/home/ubuntu/data/bldrdojo/import_data.json', 'rb') as f:
    files = {'file': ('import_data.json', f, 'application/json')}
    response = requests.post(
        'http://localhost:8001/api/notes/import_data/',
        files=files,
        headers=headers
    )

result = response.json()
print(f"Status: {response.status_code}")

if 'stats' in result:
    stats = result['stats']
    print(f"\n📈 Statistics:")
    print(f"   People created: {stats.get('people_created', 0)}")
    print(f"   People updated: {stats.get('people_updated', 0)}")
    print(f"   Errors: {len(stats.get('errors', []))}")
    
    if stats.get('errors'):
        print(f"\n⚠️  Errors:")
        for i, error in enumerate(stats['errors'][:3], 1):
            print(f"   {i}. {error}")

# Check after
print("\n📊 Bob's data AFTER import:")
people_response = requests.get('http://localhost:8001/api/people/', headers=headers)
people_data = people_response.json()
after_count = people_data.get('count', 0) if isinstance(people_data, dict) else len(people_data)
print(f"   People: {after_count}")
print(f"   Change: +{after_count - before_count}")
