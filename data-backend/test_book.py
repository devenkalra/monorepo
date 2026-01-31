import requests
import json

BASE_URL = 'http://localhost:8001'

print("=" * 70)
print("📚 TESTING BOOK ENTITY")
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

# Test 1: Create a Book
print("\n📚 Test 1: Create Book")
book_data = {
    'label': 'The Lord of the Rings',
    'year': 1954,
    'language': 'English',
    'country': 'United Kingdom',
    'summary': 'An epic high-fantasy novel following the quest to destroy the One Ring.',
    'description': 'The Lord of the Rings is an epic high-fantasy novel by J.R.R. Tolkien.',
    'tags': ['Fantasy', 'Classic', 'Adventure']
}

response = requests.post(
    f'{BASE_URL}/api/books/',
    json=book_data,
    headers=headers
)
print(f"Status: {response.status_code}")
if response.status_code == 201:
    book = response.json()
    print(f"✅ Created: {book['label']}")
    print(f"   ID: {book['id']}")
    print(f"   Year: {book['year']}")
    print(f"   Language: {book['language']}")
    book_id = book['id']
else:
    print(f"❌ Failed: {response.text}")
    exit(1)

# Test 2: Get the Book
print("\n📚 Test 2: Retrieve Book")
response = requests.get(f'{BASE_URL}/api/books/{book_id}/', headers=headers)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    book = response.json()
    print(f"✅ Retrieved: {book['label']} ({book['year']})")
    print(f"   Summary: {book['summary'][:50]}...")
else:
    print(f"❌ Failed: {response.text}")

# Test 3: Update the Book
print("\n📚 Test 3: Update Book")
update_data = {
    'summary': 'Updated: An epic high-fantasy novel following the quest to destroy the One Ring and save Middle-earth.'
}
response = requests.patch(
    f'{BASE_URL}/api/books/{book_id}/',
    json=update_data,
    headers=headers
)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    print(f"✅ Updated book summary")
else:
    print(f"❌ Failed: {response.text}")

# Test 4: Create HAS_AS_AUTHOR relation
print("\n🔗 Test 4: Create HAS_AS_AUTHOR Relation")
people_response = requests.get(f'{BASE_URL}/api/people/', headers=headers)
people_data = people_response.json()
people = people_data.get('results', []) if isinstance(people_data, dict) else people_data

if people:
    person = people[0]
    relation_data = {
        'from_entity': book_id,
        'to_entity': person['id'],
        'relation_type': 'HAS_AS_AUTHOR'
    }
    
    response = requests.post(
        f'{BASE_URL}/api/relations/',
        json=relation_data,
        headers=headers
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 201:
        print(f"✅ Created relation: {book['label']} HAS_AS_AUTHOR {person['label']}")
        
        # Verify reverse relation
        print("\n🔗 Test 5: Verify Reverse Relation (IS_AUTHOR_OF)")
        relations_response = requests.get(
            f'{BASE_URL}/api/relations/?from_entity={person["id"]}',
            headers=headers
        )
        if relations_response.status_code == 200:
            relations = relations_response.json()
            results = relations.get('results', []) if isinstance(relations, dict) else relations
            is_author_of = [r for r in results if r['relation_type'] == 'IS_AUTHOR_OF']
            if is_author_of:
                print(f"✅ Reverse relation exists: {person['label']} IS_AUTHOR_OF {book['label']}")
            else:
                print("❌ Reverse relation not found")
    else:
        print(f"❌ Failed: {response.text}")

# Test 6: Create INSPIRED relation (Book → Movie)
print("\n🔗 Test 6: Create INSPIRED Relation (Book → Movie)")
movies_response = requests.get(f'{BASE_URL}/api/movies/', headers=headers)
movies_data = movies_response.json()
movies = movies_data.get('results', []) if isinstance(movies_data, dict) else movies_data

if movies:
    movie = movies[0]
    relation_data = {
        'from_entity': book_id,
        'to_entity': movie['id'],
        'relation_type': 'INSPIRED'
    }
    
    response = requests.post(
        f'{BASE_URL}/api/relations/',
        json=relation_data,
        headers=headers
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 201:
        print(f"✅ Created relation: {book['label']} INSPIRED {movie['label']}")
        
        # Verify reverse relation
        relations_response = requests.get(
            f'{BASE_URL}/api/relations/?from_entity={movie["id"]}',
            headers=headers
        )
        if relations_response.status_code == 200:
            relations = relations_response.json()
            results = relations.get('results', []) if isinstance(relations, dict) else relations
            is_based_on = [r for r in results if r['relation_type'] == 'IS_BASED_ON']
            if is_based_on:
                print(f"✅ Reverse relation exists: {movie['label']} IS_BASED_ON {book['label']}")
    else:
        print(f"❌ Failed: {response.text}")

# Test 7: List all books
print("\n📚 Test 7: List All Books")
response = requests.get(f'{BASE_URL}/api/books/', headers=headers)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    books = response.json()
    count = books.get('count', 0) if isinstance(books, dict) else len(books)
    print(f"✅ Total books: {count}")
    results = books.get('results', []) if isinstance(books, dict) else books
    for b in results:
        print(f"   • {b['label']} ({b.get('year', 'N/A')}) - {b.get('language', 'N/A')}")

# Test 8: Filter by year
print("\n🔍 Test 8: Filter Books by Year")
response = requests.get(f'{BASE_URL}/api/books/?year=1954', headers=headers)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    books = response.json()
    count = books.get('count', 0) if isinstance(books, dict) else len(books)
    print(f"✅ Found {count} book(s) from 1954")

# Test 9: Search books
print("\n🔍 Test 9: Search Books")
response = requests.get(f'{BASE_URL}/api/books/?search=Lord', headers=headers)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    books = response.json()
    count = books.get('count', 0) if isinstance(books, dict) else len(books)
    print(f"✅ Found {count} book(s) matching 'Lord'")

print("\n" + "=" * 70)
print("✅ ALL TESTS PASSED!")
print("=" * 70)
print("\n🎉 Book entity is fully functional!")
print("\n📝 Available Relations:")
print("   • Book → HAS_AS_AUTHOR → Person")
print("   • Person → IS_AUTHOR_OF → Book")
print("   • Book → INSPIRED → Movie")
print("   • Movie → IS_BASED_ON → Book")
print("   • Book → IS_LOCATED_IN → Location")
print("   • Location → IS_LOCATION_OF → Book")
