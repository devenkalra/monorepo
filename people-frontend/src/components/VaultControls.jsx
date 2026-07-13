import React, { useState } from 'react';
import { useEncryption } from '../contexts/EncryptionContext';

function VaultControls() {
    const { hasKeys, encryptionKeys, deriveKey, clearKeys } = useEncryption();
    const [passphrase, setPassphrase] = useState('');
    const [isUnlocking, setIsUnlocking] = useState(false);
    const [error, setError] = useState('');
    const [successMessage, setSuccessMessage] = useState('');

    const handleUnlock = async (e) => {
        e.preventDefault();
        if (!passphrase.trim()) return;
        setIsUnlocking(true);
        setError('');
        setSuccessMessage('');
        
        // Use setTimeout to allow browser to render the loading state
        setTimeout(async () => {
            try {
                await deriveKey(passphrase);
                setPassphrase('');
                setSuccessMessage('Passphrase added to Key Ring!');
                setTimeout(() => setSuccessMessage(''), 3000);
            } catch (err) {
                console.error(err);
                setError('Failed to derive key. Make sure you are logged in.');
            } finally {
                setIsUnlocking(false);
            }
        }, 50);
    };

    return (
        <div className="p-3 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl mb-4 shadow-sm transition-all">
            <div className="flex flex-col md:flex-row gap-3 items-center justify-between">
                <div className="flex items-center gap-2 mr-auto text-gray-700 dark:text-gray-300">
                    <span className="text-xl">{hasKeys ? '🔓' : '🔒'}</span>
                    <div>
                        <span className="text-sm font-semibold block">
                            {hasKeys ? `Secure Vault Active (${encryptionKeys.length} key${encryptionKeys.length === 1 ? '' : 's'} loaded)` : 'Secure Vault Locked'}
                        </span>
                        <span className="text-xs text-gray-500 dark:text-gray-400">
                            {hasKeys ? 'Ready to decrypt matching entities' : 'Passphrases are derived purely in memory'}
                        </span>
                    </div>
                </div>
                
                <form onSubmit={handleUnlock} className="w-full md:w-auto flex flex-wrap gap-2 items-center justify-end">
                    <input
                        type="password"
                        placeholder={hasKeys ? "Add another passphrase..." : "Enter Vault Passphrase"}
                        value={passphrase}
                        onChange={(e) => setPassphrase(e.target.value)}
                        disabled={isUnlocking}
                        className="flex-1 md:w-64 px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-750 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    <button
                        type="submit"
                        disabled={isUnlocking || !passphrase.trim()}
                        className="px-4 py-1.5 text-sm font-semibold rounded-lg bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white shadow-sm transition flex items-center gap-2"
                    >
                        {isUnlocking ? (
                            <>
                                <svg className="animate-spin h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                                </svg>
                                Deriving...
                            </>
                        ) : hasKeys ? 'Add Key' : 'Unlock'}
                    </button>
                    
                    {hasKeys && (
                        <button
                            type="button"
                            onClick={clearKeys}
                            className="px-3 py-1.5 text-sm font-semibold rounded-lg bg-red-600 hover:bg-red-700 text-white shadow-sm transition"
                        >
                            Lock Vault
                        </button>
                    )}
                </form>
            </div>
            {error && <p className="text-xs text-red-500 mt-1">{error}</p>}
            {successMessage && <p className="text-xs text-green-500 mt-1">{successMessage}</p>}
        </div>
    );
}

export default VaultControls;
