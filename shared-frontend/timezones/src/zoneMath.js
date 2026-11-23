export function localZone() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
}

export function isValidZone(zone) {
  if (!zone) return false;
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: zone });
    return true;
  } catch {
    return false;
  }
}

/** Last path segment of an IANA zone, readable: "America/Argentina/Buenos_Aires" -> "Buenos Aires". */
export function zoneCity(zone) {
  return String(zone || '').split('/').pop().replace(/_/g, ' ');
}

function parts(zone, epochMs) {
  return Object.fromEntries(
    new Intl.DateTimeFormat('en-US', {
      timeZone: zone, hourCycle: 'h23',
      year: 'numeric', month: 'numeric', day: 'numeric', hour: 'numeric', minute: 'numeric', second: 'numeric',
    }).formatToParts(new Date(epochMs)).map((p) => [p.type, Number(p.value)]),
  );
}

/** Minutes east of UTC for `zone` at instant `epochMs`. */
export function offsetMinutes(zone, epochMs) {
  const p = parts(zone, epochMs);
  const asUtc = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second);
  return Math.round((asUtc - Math.floor(epochMs / 1000) * 1000) / 60000);
}

/** Instant for wall time "HH:MM" on "YYYY-MM-DD" in `zone`. */
export function zonedToEpoch(date, time, zone) {
  const [y, mo, d] = String(date).split('-').map(Number);
  const [h, mi] = String(time).split(':').map(Number);
  const wall = Date.UTC(y, mo - 1, d, h, mi);
  let guess = wall - offsetMinutes(zone, wall) * 60000;
  guess = wall - offsetMinutes(zone, guess) * 60000;
  return guess;
}

/** { date: 'YYYY-MM-DD', time: 'HH:MM' } for instant `epochMs` in `zone`. */
export function epochToZoned(epochMs, zone) {
  const p = parts(zone, epochMs);
  const pad = (n) => String(n).padStart(2, '0');
  return { date: `${p.year}-${pad(p.month)}-${pad(p.day)}`, time: `${pad(p.hour)}:${pad(p.minute)}` };
}

/** Whole days from date `a` to date `b` (both 'YYYY-MM-DD'). */
export function dayDiff(a, b) {
  const t = (s) => Date.UTC(...String(s).split('-').map((n, i) => Number(n) - (i === 1 ? 1 : 0)));
  return Math.round((t(b) - t(a)) / 86400000);
}

const LETTER_ABBR = {
  'Europe/London': ['GMT', 'BST'], 'Europe/Dublin': ['GMT', 'IST'], 'Asia/Kolkata': ['IST', 'IST'],
  'Asia/Tokyo': ['JST', 'JST'], 'Asia/Seoul': ['KST', 'KST'], 'Asia/Shanghai': ['CST', 'CST'],
  'Asia/Hong_Kong': ['HKT', 'HKT'], 'Europe/Paris': ['CET', 'CEST'], 'Europe/Berlin': ['CET', 'CEST'],
  'Europe/Rome': ['CET', 'CEST'], 'Europe/Madrid': ['CET', 'CEST'], 'Europe/Amsterdam': ['CET', 'CEST'],
  'Australia/Sydney': ['AEDT', 'AEST'], 'Australia/Melbourne': ['AEDT', 'AEST'], 'Pacific/Auckland': ['NZDT', 'NZST'],
};

/** 'PST', 'GMT', 'GMT+7', 'GMT+5:30' at instant `epochMs` (defaults to now). */
export function zoneAbbr(zone, epochMs = Date.now()) {
  if (!zone) return '';
  const name = new Intl.DateTimeFormat('en-US', { timeZone: zone, timeZoneName: 'short' })
    .formatToParts(new Date(epochMs)).find((p) => p.type === 'timeZoneName')?.value || '';
  if (/^[A-Z]{2,5}$/.test(name) && name !== 'GMT') return name;
  const known = LETTER_ABBR[zone];
  if (known) {
    const jan = offsetMinutes(zone, Date.UTC(new Date(epochMs).getUTCFullYear(), 0, 15));
    return offsetMinutes(zone, epochMs) === jan ? known[0] : known[1];
  }
  const minutes = offsetMinutes(zone, epochMs);
  if (minutes === 0) return 'GMT';
  const sign = minutes < 0 ? '-' : '+';
  const h = Math.floor(Math.abs(minutes) / 60);
  const m = Math.abs(minutes) % 60;
  return `GMT${sign}${h}${m ? `:${String(m).padStart(2, '0')}` : ''}`;
}
