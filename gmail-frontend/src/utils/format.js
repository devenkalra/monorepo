export function escapeHtml(s) {
  return String(s ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

const URL_RE = /\b((?:https?:\/\/|www\.)[^\s<]+[^\s<.,;:!?'")\]])/gi;

export function linkifyHtml(s) {
  const escaped = escapeHtml(s);
  return escaped.replace(URL_RE, (raw) => {
    let href = raw;
    if (/^www\./i.test(href)) href = `https://${href}`;
    return `<a class="gm-autolink" href="${href}" target="_blank" rel="noopener noreferrer">${raw}</a>`;
  });
}

export function formatMailDate(iso, internalMs) {
  let d = null;
  if (iso) {
    const parsed = new Date(iso);
    if (!Number.isNaN(parsed.getTime())) d = parsed;
  }
  if (!d && internalMs) d = new Date(Number(internalMs));
  if (!d || Number.isNaN(d.getTime())) return '';
  const now = new Date();
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();
  if (sameDay) {
    return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  }
  if (d.getFullYear() === now.getFullYear()) {
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  }
  const yy = String(d.getFullYear()).slice(-2);
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${yy}/${mm}/${dd}`;
}

export function shortFrom(from) {
  const s = String(from || '').trim();
  const m = s.match(/^"?([^"<]+)"?\s*</) || s.match(/^([^@<\s]+)/);
  return (m ? m[1] : s).trim() || '(unknown)';
}

export function snippetWords(snippet, maxWords = 12) {
  const words = String(snippet || '')
    .replace(/\s+/g, ' ')
    .trim()
    .split(' ')
    .filter(Boolean);
  if (words.length <= maxWords) return words.join(' ');
  return `${words.slice(0, maxWords).join(' ')}…`;
}

export function gmailOpenUrl(e) {
  const id = (e && (e.thread_id || e.gmail_id)) || '';
  if (!id) return '';
  return `https://mail.google.com/mail/u/0/#all/${encodeURIComponent(id)}`;
}
