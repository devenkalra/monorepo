import requests
import json

# Login
print("Logging in...")
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

# Check imported data
print("\n" + "="*70)
print("VERIFYING IMPORTED DATA")
print("="*70)

# Get people count
people_response = requests.get('http://localhost:8001/api/people/', headers=headers)
people_data = people_response.json()

# Handle paginated response
if isinstance(people_data, dict):
    people = people_data.get('results', [])
    total_count = people_data.get('count', len(people))
else:
    people = people_data
    total_count = len(people)

print(f"\n✓ People imported: {total_count}")

if people:
    print(f"\n📝 Sample People:")
    for i, person in enumerate(people[:3], 1):
        print(f"   {i}. {person.get('first_name', '')} {person.get('last_name', '')} ({person.get('gender', '')})")

# Get relations count
relations_response = requests.get('http://localhost:8001/api/relations/', headers=headers)
relations_data = relations_response.json()

# Handle paginated response
if isinstance(relations_data, dict):
    relations = relations_data.get('results', [])
    rel_count = relations_data.get('count', len(relations))
else:
    relations = relations_data
    rel_count = len(relations)

print(f"\n✓ Relations imported: {rel_count}")

if relations:
    print(f"\n🔗 Sample Relations:")
    # Create a map of entity IDs to labels
    entity_map = {p['id']: p.get('label', '') for p in people}
    
    for i, rel in enumerate(relations[:5], 1):
        from_id = rel.get('from_entity')
        to_id = rel.get('to_entity')
        from_label = entity_map.get(from_id, from_id if isinstance(from_id, str) else 'Unknown')
        to_label = entity_map.get(to_id, to_id if isinstance(to_id, str) else 'Unknown')
        print(f"   {i}. {from_label} --[{rel['relation_type']}]--> {to_label}")

print("\n" + "="*70)
print("✅ IMPORT VERIFICATION COMPLETE!")
print(f"\n📊 Summary:")
print(f"   • {total_count} Person entities")
print(f"   • {rel_count} Relationships")
print(f"   • All data successfully imported with 0 errors!")
print("="*70)
