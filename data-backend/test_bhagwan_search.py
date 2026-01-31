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

# Search for "Bhagwan" in people endpoint
print("=" * 70)
print("🔍 SEARCHING PEOPLE ENDPOINT FOR 'Bhagwan'")
print("=" * 70)

response = requests.get(f'{BASE_URL}/api/people/?search=Bhagwan', headers=headers)
print(f"URL: {BASE_URL}/api/people/?search=Bhagwan")
print(f"Status: {response.status_code}")

if response.status_code == 200:
    data = response.json()
    results = data.get('results', []) if isinstance(data, dict) else data
    if results:
        print(f"\n✅ Found {len(results)} result(s) in people endpoint:")
        for result in results:
            print(f"  • {result.get('label', 'N/A')} (first_name: {result.get('first_name', 'N/A')})")
            print(f"    ID: {result.get('id')}")
    else:
        print("\n❌ No results found in people endpoint")
else:
    print(f"❌ Error: {response.text}")

# Search for "Bhag" in search endpoint
print("\n" + "=" * 70)
print("🔍 SEARCHING SEARCH ENDPOINT FOR 'Bhag'")
print("=" * 70)

response = requests.get(f'{BASE_URL}/api/search/?q=Bhag', headers=headers)
print(f"URL: {BASE_URL}/api/search/?q=Bhag")
print(f"Status: {response.status_code}")

if response.status_code == 200:
    results = response.json()
    print(f"Response type: {type(results)}")
    if results:
        print(f"\n✅ Found {len(results)} result(s) in search endpoint:")
        for result in results:
            print(f"  • {result.get('label', 'N/A')} ({result.get('type', 'N/A')})")
            print(f"    ID: {result.get('id')}")
    else:
        print("\n❌ No results found in search endpoint")
        print("\n🔍 Let's check what's in the search endpoint response:")
        print(f"Raw response: {results}")
else:
    print(f"❌ Error: {response.text}")

# List all people to find Bhagwan Dass Kalra
print("\n" + "=" * 70)
print("📋 LISTING ALL PEOPLE TO FIND 'Bhagwan Dass Kalra'")
print("=" * 70)

response = requests.get(f'{BASE_URL}/api/people/', headers=headers)
if response.status_code == 200:
    data = response.json()
    results = data.get('results', []) if isinstance(data, dict) else data
    
    found = False
    for person in results:
        label = person.get('label', '')
        first_name = person.get('first_name', '')
        last_name = person.get('last_name', '')
        
        if 'bhagwan' in label.lower() or 'bhagwan' in first_name.lower():
            print(f"\n✅ FOUND: {label}")
            print(f"   First Name: {first_name}")
            print(f"   Last Name: {last_name}")
            print(f"   ID: {person.get('id')}")
            found = True
    
    if not found:
        print("\n❌ 'Bhagwan Dass Kalra' not found in people list")
        print(f"\nTotal people: {len(results)}")
        print("\nShowing first 10 people:")
        for i, person in enumerate(results[:10]):
            print(f"  {i+1}. {person.get('label', 'N/A')}")

