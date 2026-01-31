import requests
import json

# Test with Bob's account
print("Testing import for Bob...")
print("="*70)

# Login as Bob
login_response = requests.post(
    'http://localhost:8001/api/auth/login/',
    json={
        'email': 'bob@example.com',
        'password': 'bobpassword'
    }
)

if login_response.status_code != 200:
    print(f"Bob login failed: {login_response.status_code}")
    print("Response:", login_response.text[:200])
    print("\nTrying to create Bob's account...")
    
    # Try to register Bob
    reg_response = requests.post(
        'http://localhost:8001/api/auth/registration/',
        json={
            'email': 'bob@example.com',
            'password1': 'bobpassword',
            'password2': 'bobpassword'
        }
    )
    print(f"Registration status: {reg_response.status_code}")
    if reg_response.status_code in [200, 201]:
        token = reg_response.json().get('access_token') or reg_response.json().get('access')
    else:
        print("Could not create/login Bob")
        exit(1)
else:
    token = login_response.json().get('access_token') or login_response.json().get('access')

print(f"✓ Logged in as Bob")
print(f"Token: {token[:20]}...")

headers = {'Authorization': f'Bearer {token}'}

# Check Bob's current entities
print("\n📊 Bob's current data BEFORE import:")
people_response = requests.get('http://localhost:8001/api/people/', headers=headers)
if people_response.status_code == 200:
    people_data = people_response.json()
    if isinstance(people_data, dict):
        count = people_data.get('count', len(people_data.get('results', [])))
    else:
        count = len(people_data)
    print(f"   People: {count}")
else:
    print(f"   Error getting people: {people_response.status_code}")

# Now import
print("\n📥 Importing data...")
with open('/home/ubuntu/data/bldrdojo/import_data.json', 'rb') as f:
    files = {'file': ('import_data.json', f, 'application/json')}
    
    response = requests.post(
        'http://localhost:8001/api/notes/import_data/',
        files=files,
        headers=headers
    )

print(f"Status: {response.status_code}")
result = response.json()

if 'stats' in result:
    stats = result['stats']
    print(f"\n📈 Import Statistics:")
    print(f"   People created: {stats.get('people_created', 0)}")
    print(f"   People updated: {stats.get('people_updated', 0)}")
    print(f"   Relations created: {stats.get('relations_created', 0)}")
    print(f"   Relations updated: {stats.get('relations_updated', 0)}")
    print(f"   Errors: {len(stats.get('errors', []))}")
    
    if stats.get('errors'):
        print(f"\n⚠️  First 5 errors:")
        for i, error in enumerate(stats['errors'][:5], 1):
            print(f"   {i}. {error}")

# Check Bob's data AFTER import
print("\n📊 Bob's data AFTER import:")
people_response = requests.get('http://localhost:8001/api/people/', headers=headers)
if people_response.status_code == 200:
    people_data = people_response.json()
    if isinstance(people_data, dict):
        count = people_data.get('count', len(people_data.get('results', [])))
        people = people_data.get('results', [])
    else:
        count = len(people_data)
        people = people_data
    print(f"   People: {count}")
    
    if people and count > 0:
        print(f"\n   Sample people:")
        for i, person in enumerate(people[:3], 1):
            print(f"      {i}. {person.get('first_name', '')} {person.get('last_name', '')} (ID: {person.get('id')[:8]}...)")
