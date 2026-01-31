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

# Create a test image file
print("📸 Creating test image...")
from PIL import Image
import io

# Create a simple test image
img = Image.new('RGB', (100, 100), color='red')
img_bytes = io.BytesIO()
img.save(img_bytes, format='PNG')
img_bytes.seek(0)

# Test upload endpoint
print("\n🔼 Testing upload endpoint...")
files = {'file': ('test.png', img_bytes, 'image/png')}
response = requests.post(
    f'{BASE_URL}/api/upload/',
    headers=headers,
    files=files
)

print(f"Status: {response.status_code}")
if response.status_code == 201:
    data = response.json()
    print(f"✅ Upload successful!")
    print(f"   URL: {data.get('url')}")
    print(f"   Thumbnail: {data.get('thumbnail_url')}")
    print(f"   SHA256: {data.get('sha256')}")
else:
    print(f"❌ Upload failed: {response.text}")

