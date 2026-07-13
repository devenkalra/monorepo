import React, { createContext, useState, useContext } from 'react';
import { useAuth } from './AuthContext';

const EncryptionContext = createContext(null);

export const EncryptionProvider = ({ children }) => {
  // Store multiple keys in volatile memory (key ring)
  const [encryptionKeys, setEncryptionKeys] = useState([]);
  const { user } = useAuth();

  const deriveKey = async (passphrase) => {
    if (!user) throw new Error('User not authenticated');
    const saltString = `bldrdojo-salt-${user.id || user.email || 'default'}`;
    const encoder = new TextEncoder();
    const passphraseBytes = encoder.encode(passphrase);
    const saltBytes = encoder.encode(saltString);

    const baseKey = await window.crypto.subtle.importKey(
      'raw',
      passphraseBytes,
      'PBKDF2',
      false,
      ['deriveKey', 'deriveBits']
    );

    const derived = await window.crypto.subtle.deriveKey(
      {
        name: 'PBKDF2',
        salt: saltBytes,
        iterations: 600000,
        hash: 'SHA-256',
      },
      baseKey,
      {
        name: 'AES-GCM',
        length: 256,
      },
      false,
      ['encrypt', 'decrypt']
    );

    // Add to key ring if not already there
    setEncryptionKeys(prev => {
      // Basic check: we can keep all unique derived keys
      return [...prev, derived];
    });

    return derived;
  };

  const clearKeys = () => {
    setEncryptionKeys([]);
  };

  const encryptText = async (text, key) => {
    // If no key specified, use the most recently added key
    const targetKey = key || encryptionKeys[encryptionKeys.length - 1];
    if (!targetKey) throw new Error('No encryption key available. Unlock the vault first.');
    if (!text) return '';

    const encoder = new TextEncoder();
    const plaintextBytes = encoder.encode(text);
    const iv = window.crypto.getRandomValues(new Uint8Array(12));

    const ciphertextBuffer = await window.crypto.subtle.encrypt(
      {
        name: 'AES-GCM',
        iv: iv,
      },
      targetKey,
      plaintextBytes
    );

    const ciphertextBytes = new Uint8Array(ciphertextBuffer);
    const combinedBytes = new Uint8Array(iv.length + ciphertextBytes.length);
    combinedBytes.set(iv);
    combinedBytes.set(ciphertextBytes, iv.length);

    // Convert to binary string, then base64
    let binary = '';
    const len = combinedBytes.byteLength;
    for (let i = 0; i < len; i++) {
      binary += String.fromCharCode(combinedBytes[i]);
    }
    return window.btoa(binary);
  };

  const decryptText = async (base64Ciphertext) => {
    if (encryptionKeys.length === 0) throw new Error('Vault is locked. No keys available.');
    if (!base64Ciphertext) return { plaintext: '', key: null };

    const binaryString = window.atob(base64Ciphertext);
    const len = binaryString.length;
    const combinedBytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
      combinedBytes[i] = binaryString.charCodeAt(i);
    }

    const iv = combinedBytes.slice(0, 12);
    const ciphertextBytes = combinedBytes.slice(12);

    // Try each key in the key ring
    for (const key of encryptionKeys) {
      try {
        const decryptedBuffer = await window.crypto.subtle.decrypt(
          {
            name: 'AES-GCM',
            iv: iv,
          },
          key,
          ciphertextBytes
        );

        const decoder = new TextDecoder();
        const plaintext = decoder.decode(decryptedBuffer);
        return { plaintext, key }; // Return the decrypted text and the key that succeeded
      } catch (err) {
        // Decryption with this key failed, try next
        continue;
      }
    }

    throw new Error('Decryption failed with all available keys.');
  };

  const encryptBlob = async (blob, key) => {
    const targetKey = key || encryptionKeys[encryptionKeys.length - 1];
    if (!targetKey) throw new Error('No encryption key available. Unlock the vault first.');
    
    const fileBuffer = await blob.arrayBuffer();
    const iv = window.crypto.getRandomValues(new Uint8Array(12));

    const ciphertextBuffer = await window.crypto.subtle.encrypt(
      {
        name: 'AES-GCM',
        iv: iv,
      },
      targetKey,
      fileBuffer
    );

    const ciphertextBytes = new Uint8Array(ciphertextBuffer);
    const combinedBytes = new Uint8Array(iv.length + ciphertextBytes.length);
    combinedBytes.set(iv);
    combinedBytes.set(ciphertextBytes, iv.length);

    return new Blob([combinedBytes], { type: 'application/octet-stream' });
  };

  const decryptBlob = async (encryptedBlob, mimeType, key) => {
    // If we have a specific key associated with the entity, use it.
    // Otherwise try all keys in the key ring.
    const keysToTry = key ? [key] : encryptionKeys;
    if (keysToTry.length === 0) throw new Error('Vault is locked. No keys available.');

    const arrayBuffer = await encryptedBlob.arrayBuffer();
    const combinedBytes = new Uint8Array(arrayBuffer);

    const iv = combinedBytes.slice(0, 12);
    const ciphertextBytes = combinedBytes.slice(12);

    for (const k of keysToTry) {
      try {
        const decryptedBuffer = await window.crypto.subtle.decrypt(
          {
            name: 'AES-GCM',
            iv: iv,
          },
          k,
          ciphertextBytes
        );

        return new Blob([decryptedBuffer], { type: mimeType });
      } catch (err) {
        continue;
      }
    }

    throw new Error('Blob decryption failed.');
  };

  const value = {
    encryptionKeys,
    hasKeys: encryptionKeys.length > 0,
    deriveKey,
    clearKeys,
    encryptText,
    decryptText,
    encryptBlob,
    decryptBlob,
  };

  return (
    <EncryptionContext.Provider value={value}>
      {children}
    </EncryptionContext.Provider>
  );
};

export const useEncryption = () => {
  const context = useContext(EncryptionContext);
  if (!context) {
    throw new Error('useEncryption must be used within EncryptionProvider');
  }
  return context;
};
