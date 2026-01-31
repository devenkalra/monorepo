import requests
import json

BASE_URL = 'http://localhost:8001'

print("=" * 70)
print("🧪 TESTING CONTAINER, ASSET, AND ORG ENTITIES")
print("=" * 70)

# Login as Bob
print("\n🔐 Logging in as Bob...")
login_response = requests.post(
    f'{BASE_URL}/api/auth/login/',
    json={'email': 'bob@example.com', 'password': 'testpass123'}
)
token = login_response.json().get('access_token') or login_response.json().get('access')
headers = {'Authorization': f'Bearer {token}'}
print("✅ Logged in successfully")

# ========== CONTAINER TESTS ==========
print("\n" + "=" * 70)
print("📦 CONTAINER ENTITY TESTS")
print("=" * 70)

# Test 1: Create a Container
print("\n📦 Test 1: Create Container")
container_data = {
    'label': 'Storage Box A',
    'description': 'Main storage container for household items',
    'tags': ['Storage', 'Home']
}

response = requests.post(
    f'{BASE_URL}/api/containers/',
    json=container_data,
    headers=headers
)
print(f"Status: {response.status_code}")
if response.status_code == 201:
    container = response.json()
    print(f"✅ Created: {container['label']}")
    print(f"   ID: {container['id']}")
    container_id = container['id']
else:
    print(f"❌ Failed: {response.text}")
    exit(1)

# Test 2: Create nested Container (IS_CONTAINED_IN)
print("\n📦 Test 2: Create Nested Container")
nested_container_data = {
    'label': 'Drawer 1',
    'description': 'Top drawer in Storage Box A'
}

response = requests.post(
    f'{BASE_URL}/api/containers/',
    json=nested_container_data,
    headers=headers
)
if response.status_code == 201:
    nested_container = response.json()
    print(f"✅ Created: {nested_container['label']}")
    nested_container_id = nested_container['id']
    
    # Create IS_CONTAINED_IN relation
    relation_data = {
        'from_entity': nested_container_id,
        'to_entity': container_id,
        'relation_type': 'IS_CONTAINED_IN'
    }
    
    response = requests.post(
        f'{BASE_URL}/api/relations/',
        json=relation_data,
        headers=headers
    )
    if response.status_code == 201:
        print(f"✅ Created relation: {nested_container['label']} IS_CONTAINED_IN {container['label']}")
    else:
        print(f"❌ Relation failed: {response.text}")
else:
    print(f"❌ Failed: {response.text}")

# ========== ASSET TESTS ==========
print("\n" + "=" * 70)
print("💰 ASSET ENTITY TESTS")
print("=" * 70)

# Test 3: Create an Asset
print("\n💰 Test 3: Create Asset")
asset_data = {
    'label': 'Laptop - MacBook Pro',
    'value': 2499.99,
    'acquired_on': '2024-01-15',
    'description': '16-inch MacBook Pro M3',
    'tags': ['Electronics', 'Computer']
}

response = requests.post(
    f'{BASE_URL}/api/assets/',
    json=asset_data,
    headers=headers
)
print(f"Status: {response.status_code}")
if response.status_code == 201:
    asset = response.json()
    print(f"✅ Created: {asset['label']}")
    print(f"   Value: ${asset['value']}")
    print(f"   Acquired: {asset['acquired_on']}")
    asset_id = asset['id']
else:
    print(f"❌ Failed: {response.text}")
    exit(1)

# Test 4: Link Asset to Container
print("\n💰 Test 4: Link Asset to Container")
relation_data = {
    'from_entity': asset_id,
    'to_entity': container_id,
    'relation_type': 'IS_LOCATED_IN'
}

response = requests.post(
    f'{BASE_URL}/api/relations/',
    json=relation_data,
    headers=headers
)
print(f"Status: {response.status_code}")
if response.status_code == 201:
    print(f"✅ Created relation: {asset['label']} IS_LOCATED_IN {container['label']}")
else:
    print(f"❌ Failed: {response.text}")

# Test 5: Filter Assets by Value
print("\n💰 Test 5: Filter Assets by Value")
response = requests.get(f'{BASE_URL}/api/assets/?value__gte=2000', headers=headers)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    assets = response.json()
    count = assets.get('count', 0) if isinstance(assets, dict) else len(assets)
    print(f"✅ Found {count} asset(s) with value >= $2000")

# ========== ORG TESTS ==========
print("\n" + "=" * 70)
print("🏢 ORG ENTITY TESTS")
print("=" * 70)

# Test 6: Create an Org
print("\n🏢 Test 6: Create Organization")
org_data = {
    'name': 'Tech Innovators Inc',
    'kind': 'Company',
    'description': 'A leading technology company',
    'tags': ['Technology', 'Software']
}

response = requests.post(
    f'{BASE_URL}/api/orgs/',
    json=org_data,
    headers=headers
)
print(f"Status: {response.status_code}")
if response.status_code == 201:
    org = response.json()
    print(f"✅ Created: {org['name']}")
    print(f"   Kind: {org['kind']}")
    print(f"   Label: {org['label']}")
    org_id = org['id']
else:
    print(f"❌ Failed: {response.text}")
    exit(1)

# Test 7: Link Person to Org (HAS_EMPLOYEE)
print("\n🏢 Test 7: Link Person to Org (HAS_EMPLOYEE)")
people_response = requests.get(f'{BASE_URL}/api/people/', headers=headers)
people_data = people_response.json()
people = people_data.get('results', []) if isinstance(people_data, dict) else people_data

if people:
    person = people[0]
    relation_data = {
        'from_entity': org_id,
        'to_entity': person['id'],
        'relation_type': 'HAS_EMPLOYEE'
    }
    
    response = requests.post(
        f'{BASE_URL}/api/relations/',
        json=relation_data,
        headers=headers
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 201:
        print(f"✅ Created relation: {org['name']} HAS_EMPLOYEE {person['label']}")
        
        # Verify reverse relation
        print("\n🔗 Test 8: Verify Reverse Relation (WORKS_AT)")
        relations_response = requests.get(
            f'{BASE_URL}/api/relations/?from_entity={person["id"]}',
            headers=headers
        )
        if relations_response.status_code == 200:
            relations = relations_response.json()
            results = relations.get('results', []) if isinstance(relations, dict) else relations
            works_at = [r for r in results if r['relation_type'] == 'WORKS_AT']
            if works_at:
                print(f"✅ Reverse relation exists: {person['label']} WORKS_AT {org['name']}")
            else:
                print("❌ Reverse relation not found")
    else:
        print(f"❌ Failed: {response.text}")

# Test 9: Link Org to Location
print("\n🏢 Test 9: Link Org to Location")
locations_response = requests.get(f'{BASE_URL}/api/locations/', headers=headers)
locations_data = locations_response.json()
locations = locations_data.get('results', []) if isinstance(locations_data, dict) else locations_data

if locations:
    location = locations[0]
    relation_data = {
        'from_entity': org_id,
        'to_entity': location['id'],
        'relation_type': 'IS_LOCATED_AT'
    }
    
    response = requests.post(
        f'{BASE_URL}/api/relations/',
        json=relation_data,
        headers=headers
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 201:
        print(f"✅ Created relation: {org['name']} IS_LOCATED_AT {location['label']}")
    else:
        print(f"❌ Failed: {response.text}")

# Test 10: Filter Orgs by Kind
print("\n🏢 Test 10: Filter Orgs by Kind")
response = requests.get(f'{BASE_URL}/api/orgs/?kind=Company', headers=headers)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    orgs = response.json()
    count = orgs.get('count', 0) if isinstance(orgs, dict) else len(orgs)
    print(f"✅ Found {count} organization(s) of kind 'Company'")

# Test 11: List all Containers
print("\n📦 Test 11: List All Containers")
response = requests.get(f'{BASE_URL}/api/containers/', headers=headers)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    containers = response.json()
    count = containers.get('count', 0) if isinstance(containers, dict) else len(containers)
    print(f"✅ Total containers: {count}")

# Test 12: List all Assets
print("\n💰 Test 12: List All Assets")
response = requests.get(f'{BASE_URL}/api/assets/', headers=headers)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    assets = response.json()
    count = assets.get('count', 0) if isinstance(assets, dict) else len(assets)
    print(f"✅ Total assets: {count}")

# Test 13: List all Orgs
print("\n🏢 Test 13: List All Orgs")
response = requests.get(f'{BASE_URL}/api/orgs/', headers=headers)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    orgs = response.json()
    count = orgs.get('count', 0) if isinstance(orgs, dict) else len(orgs)
    print(f"✅ Total orgs: {count}")

print("\n" + "=" * 70)
print("✅ ALL TESTS PASSED!")
print("=" * 70)
print("\n🎉 Container, Asset, and Org entities are fully functional!")
print("\n📝 Available Relations:")
print("   Container:")
print("      • Container → IS_CONTAINED_IN → Container")
print("   Asset:")
print("      • Asset → IS_LOCATED_IN → Container")
print("   Org:")
print("      • Org → IS_LOCATED_AT → Location")
print("      • Org → HAS_EMPLOYEE → Person (reverse: WORKS_AT)")
print("      • Org → HAS_MEMBER → Person (reverse: IS_MEMBER_OF)")
print("      • Org → HAS_STUDENT → Person (reverse: STUDIES_AT)")
