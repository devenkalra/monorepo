import requests

BASE_URL = 'http://localhost:8001'

# Login as Bob
print("🔐 Logging in as Bob...")
login_response = requests.post(
    f'{BASE_URL}/api/auth/login/',
    json={'email': 'bob@example.com', 'password': 'testpass123'}
)
token = login_response.json().get('access_token') or login_response.json().get('access')
headers = {'Authorization': f'Bearer {token}'}
print("✅ Logged in successfully\n")

# List all entities for Bob
print("=" * 70)
print("📋 ALL ENTITIES FOR BOB")
print("=" * 70)

entity_types = ['people', 'notes', 'locations', 'movies', 'books', 'containers', 'assets', 'orgs']
all_entities = []

for entity_type in entity_types:
    response = requests.get(f'{BASE_URL}/api/{entity_type}/', headers=headers)
    if response.status_code == 200:
        data = response.json()
        results = data.get('results', []) if isinstance(data, dict) else data
        if results:
            print(f"\n{entity_type.upper()}:")
            for entity in results:
                label = entity.get('label') or entity.get('name', 'N/A')
                print(f"  • {label} (ID: {entity['id'][:8]}...)")
                all_entities.append({'type': entity_type, 'label': label, 'id': entity['id']})

print(f"\n📊 Total entities: {len(all_entities)}")

# Test search for "Bhag"
print("\n" + "=" * 70)
print("🔍 TESTING SEARCH FOR 'Bhag'")
print("=" * 70)

search_term = 'Bhag'
response = requests.get(f'{BASE_URL}/api/search/?q={search_term}', headers=headers)
print(f"\nURL: {BASE_URL}/api/search/?q={search_term}")
print(f"Status: {response.status_code}")

if response.status_code == 200:
    results = response.json()
    print(f"Response: {results}")
    if results:
        print(f"\n✅ Found {len(results)} result(s):")
        for result in results:
            print(f"  • {result.get('label', 'N/A')} ({result.get('type', 'N/A')})")
    else:
        print("\n❌ No results found")
else:
    print(f"❌ Error: {response.text}")

# Check if there's an entity with "Bhag" in the name
print("\n" + "=" * 70)
print("🔍 CHECKING FOR ENTITIES CONTAINING 'Bhag'")
print("=" * 70)

matching = [e for e in all_entities if 'bhag' in e['label'].lower()]
if matching:
    print(f"\n✅ Found {len(matching)} matching entity/entities in direct API calls:")
    for e in matching:
        print(f"  • {e['label']} ({e['type']}) - ID: {e['id']}")
else:
    print("\n❌ No entities found with 'Bhag' in the label")

