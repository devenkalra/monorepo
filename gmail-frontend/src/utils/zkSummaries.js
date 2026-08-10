/** Browser-only persistence for zero-knowledge email summaries. */

const PREFIX = 'gmail-zk-summaries:'

export function zkStorageKey(userId, accountId) {
  return `${PREFIX}${userId || 'anon'}:${accountId || 'none'}`
}

export function loadZkSummaries(userId, accountId) {
  try {
    const raw = localStorage.getItem(zkStorageKey(userId, accountId))
    if (!raw) return {}
    const data = JSON.parse(raw)
    if (!data || typeof data !== 'object' || Array.isArray(data)) return {}
    return data
  } catch {
    return {}
  }
}

export function saveZkSummaries(userId, accountId, summaries) {
  try {
    localStorage.setItem(
      zkStorageKey(userId, accountId),
      JSON.stringify(summaries || {}),
    )
    return true
  } catch (err) {
    console.warn('Could not persist ZK summaries in localStorage', err)
    return false
  }
}

export function clearZkSummaries(userId, accountId) {
  try {
    localStorage.removeItem(zkStorageKey(userId, accountId))
  } catch {
    /* ignore */
  }
}

/** Clear all ZK summary caches for a user across Gmail accounts. */
export function clearAllZkSummariesForUser(userId) {
  const prefix = `${PREFIX}${userId || 'anon'}:`
  try {
    const keys = []
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i)
      if (k && k.startsWith(prefix)) keys.push(k)
    }
    keys.forEach((k) => localStorage.removeItem(k))
  } catch {
    /* ignore */
  }
}
