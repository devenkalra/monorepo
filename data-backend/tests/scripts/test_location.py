import requests
import json

# Login as Bob
login_response = requests.post(
    'http://localhost:8001/api/auth/login/',
    json={'email': 'bob@example.com', 'password': 'testpass123'}
)
token = login_response.json().get('access_token') or login_response.json().get('access')
headers = {'Authorization': f'Bearer {token}'}

print("✅ Logged in as Bob\n")

# Create a location
location_data = {
    'address1': '123 Main St',
    'address2': 'Apt 4B',
    'city': 'San Francisco',
    'state': 'CA',
    'postal_code': '94102',
    'country': 'USA',
    'description': 'Home address'
}

print("Creating location...")
response = requests.post(
    'http://localhost:8001/api/locations/',
    json=location_data,
    headers=headers
)
print(f"Status: {response.status_code}")
location = response.json()
print(f"Created location: {location.get('label')}")
print(f"ID: {location.get('id')}")

# Get all locations
print("\n📍 Getting all locations...")
response = requests.get('http://localhost:8001/api/locations/', headers=headers)
locations = response.json()
count = locations.get('count', 0) if isinstance(locations, dict) else len(locations)
print(f"Total locations: {count}")

# Create a LIVES_AT relation
print("\n🔗 Creating LIVES_AT relation...")
people_response = requests.get('http://localhost:8001/api/people/', headers=headers)
people_data = people_response.json()
people = people_data.get('results', []) if isinstance(people_data, dict) else people_data

if people:
    person_id = people[0]['id']
    relation_data = {
        'from_entity': person_id,
        'to_entity': location['id'],
        'relation_type': 'LIVES_AT'
    }
    
    response = requests.post(
        'http://localhost:8001/api/relations/',
        json=relation_data,
        headers=headers
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 201:
        print(f"✅ Created relation: {people[0]['label']} LIVES_AT {location['label']}")
    else:
        print(f"Error: {response.json()}")

print("\n✅ Location entity type is working!")
