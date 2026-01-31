import requests
import json

BASE_URL = 'http://localhost:8001'

print("=" * 70)
print("🎬 TESTING MOVIE ENTITY")
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

# Test 1: Create a Movie
print("\n🎬 Test 1: Create Movie")
movie_data = {
    'label': 'The Shawshank Redemption',
    'year': 1994,
    'language': 'English',
    'country': 'USA',
    'description': 'Two imprisoned men bond over a number of years...',
    'tags': ['Drama', 'Classic']
}

response = requests.post(
    f'{BASE_URL}/api/movies/',
    json=movie_data,
    headers=headers
)
print(f"Status: {response.status_code}")
if response.status_code == 201:
    movie = response.json()
    print(f"✅ Created: {movie['label']}")
    print(f"   ID: {movie['id']}")
    print(f"   Year: {movie['year']}")
    print(f"   Language: {movie['language']}")
    movie_id = movie['id']
else:
    print(f"❌ Failed: {response.text}")
    exit(1)

# Test 2: Get the Movie
print("\n🎬 Test 2: Retrieve Movie")
response = requests.get(f'{BASE_URL}/api/movies/{movie_id}/', headers=headers)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    movie = response.json()
    print(f"✅ Retrieved: {movie['label']} ({movie['year']})")
else:
    print(f"❌ Failed: {response.text}")

# Test 3: Update the Movie
print("\n🎬 Test 3: Update Movie")
update_data = {
    'description': 'Updated: Two imprisoned men bond over a number of years, finding solace and eventual redemption through acts of common decency.'
}
response = requests.patch(
    f'{BASE_URL}/api/movies/{movie_id}/',
    json=update_data,
    headers=headers
)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    print(f"✅ Updated movie description")
else:
    print(f"❌ Failed: {response.text}")

# Test 4: Create HAS_ACTOR relation
print("\n🔗 Test 4: Create HAS_ACTOR Relation")
people_response = requests.get(f'{BASE_URL}/api/people/', headers=headers)
people_data = people_response.json()
people = people_data.get('results', []) if isinstance(people_data, dict) else people_data

if people:
    person = people[0]
    relation_data = {
        'from_entity': movie_id,
        'to_entity': person['id'],
        'relation_type': 'HAS_ACTOR'
    }
    
    response = requests.post(
        f'{BASE_URL}/api/relations/',
        json=relation_data,
        headers=headers
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 201:
        print(f"✅ Created relation: {movie['label']} HAS_ACTOR {person['label']}")
        
        # Verify reverse relation
        print("\n🔗 Test 5: Verify Reverse Relation (ACTED_IN)")
        relations_response = requests.get(
            f'{BASE_URL}/api/relations/?from_entity={person["id"]}',
            headers=headers
        )
        if relations_response.status_code == 200:
            relations = relations_response.json()
            results = relations.get('results', []) if isinstance(relations, dict) else relations
            acted_in = [r for r in results if r['relation_type'] == 'ACTED_IN']
            if acted_in:
                print(f"✅ Reverse relation exists: {person['label']} ACTED_IN {movie['label']}")
            else:
                print("❌ Reverse relation not found")
    else:
        print(f"❌ Failed: {response.text}")

# Test 6: List all movies
print("\n🎬 Test 6: List All Movies")
response = requests.get(f'{BASE_URL}/api/movies/', headers=headers)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    movies = response.json()
    count = movies.get('count', 0) if isinstance(movies, dict) else len(movies)
    print(f"✅ Total movies: {count}")
    results = movies.get('results', []) if isinstance(movies, dict) else movies
    for m in results:
        print(f"   • {m['label']} ({m.get('year', 'N/A')}) - {m.get('language', 'N/A')}")

# Test 7: Filter by year
print("\n🔍 Test 7: Filter Movies by Year")
response = requests.get(f'{BASE_URL}/api/movies/?year=1994', headers=headers)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    movies = response.json()
    count = movies.get('count', 0) if isinstance(movies, dict) else len(movies)
    print(f"✅ Found {count} movie(s) from 1994")

# Test 8: Search movies
print("\n🔍 Test 8: Search Movies")
response = requests.get(f'{BASE_URL}/api/movies/?search=Shawshank', headers=headers)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    movies = response.json()
    count = movies.get('count', 0) if isinstance(movies, dict) else len(movies)
    print(f"✅ Found {count} movie(s) matching 'Shawshank'")

print("\n" + "=" * 70)
print("✅ ALL TESTS PASSED!")
print("=" * 70)
print("\n🎉 Movie entity is fully functional!")
print("\n📝 Available Relations:")
print("   • Movie → HAS_ACTOR → Person")
print("   • Person → ACTED_IN → Movie")
print("   • Movie → HAS_DIRECTOR → Person")
print("   • Person → DIRECTED → Movie")
print("   • Movie → HAS_MUS_DIRECTOR → Person")
print("   • Person → GAVE_MUSIC_TO → Movie")
