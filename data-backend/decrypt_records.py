import base64
import hashlib
import json
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from people.models import Entity

passphrases = [
    'password', 'passwordA', 'passwordB', 'deven', 'test', '123456',
    'Deven', 'Deven Kalra', 'deven kalra', 'deven@kalra.com',
    'Encrypted P2', 'Encrypted P2Ex', 'Encrypted P2EX', 'p2', 'p2ex'
]
salts = [
    b"bldrdojo-salt-1",
    b"bldrdojo-salt-deven@kalra.com",
    b"bldrdojo-salt-deven",
    b"bldrdojo-salt-default",
    b"bldrdojo-salt-undefined"
]

for entity in Entity.objects.filter(is_encrypted=True):
    print(f"\n--- Entity ID: {entity.id} (updated_at: {entity.updated_at}) ---")
    if not entity.encrypted_data:
        print("No encrypted data")
        continue
    
    try:
        combined_bytes = base64.b64decode(entity.encrypted_data)
        iv = combined_bytes[:12]
        ciphertext = combined_bytes[12:]
    except Exception as e:
        print(f"Failed to decode base64: {e}")
        continue
        
    decrypted = False
    for salt in salts:
        for pw in passphrases:
            try:
                key = hashlib.pbkdf2_hmac('sha256', pw.encode('utf-8'), salt, 600000, 32)
                aesgcm = AESGCM(key)
                plaintext_bytes = aesgcm.decrypt(iv, ciphertext, None)
                plaintext = plaintext_bytes.decode('utf-8')
                print(f"Decrypted successfully! key='{pw}', salt='{salt.decode()}':")
                data = json.loads(plaintext)
                for k, v in data.items():
                    print(f"  {k}: {v}")
                decrypted = True
                break
            except Exception as e:
                continue
        if decrypted:
            break
    if not decrypted:
        print("Failed to decrypt with all combinations")
