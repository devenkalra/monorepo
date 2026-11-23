import mockTrip from './mockTrip.json';

export const freshTrip = () => structuredClone(mockTrip);

export const KIND_LABEL = { stop: 'Stop', event: 'Event', travel: 'Travel' };
export const MODE_LABEL = { flight: 'Flight', train: 'Train', drive: 'Drive', ferry: 'Ferry' };
export const MODE_GLYPH = { flight: '✈', train: 'T', drive: 'D', ferry: 'F' };

function parseDate(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d);
}

export function fmtDate(iso, opts = { weekday: 'short', month: 'short', day: 'numeric' }) {
  return iso ? parseDate(iso).toLocaleDateString('en-US', opts) : '';
}

export function fmtTime(hhmm) {
  if (!hhmm) return '';
  const [h, m] = hhmm.split(':').map(Number);
  return `${h % 12 || 12}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`;
}

export function fmtDuration(min) {
  if (!min) return '';
  const h = Math.floor(min / 60);
  const m = min % 60;
  return [h && `${h}h`, m && `${m}m`].filter(Boolean).join(' ');
}

export function fmtRange(trip) {
  const start = fmtDate(trip.startDate, { month: 'short', day: 'numeric' });
  const end = fmtDate(trip.endDate, { month: 'short', day: 'numeric', year: 'numeric' });
  return `${start} – ${end}`;
}

export const itemTime = (item) => item.start || item.time || item.depart || '';

export function itemTitle(item) {
  if (item.kind === 'travel') return `${item.from || '?'} → ${item.to || '?'}`;
  return item.title || 'Untitled';
}

/** Second (and last) line of a list row: time plus the one fact that tells items apart. */
export function itemSubtitle(item) {
  if (item.kind === 'travel') {
    const times = [fmtTime(item.depart), fmtTime(item.arrive)].filter(Boolean).join(' → ');
    return [MODE_LABEL[item.mode] || 'Travel', times].filter(Boolean).join(' · ');
  }
  if (item.kind === 'event') return [fmtTime(item.time), 'Event'].filter(Boolean).join(' · ');
  return [fmtTime(item.start), fmtDuration(item.durationMin)].filter(Boolean).join(' · ') || 'Stop';
}

export const sortedItems = (day) =>
  [...day.items].sort((a, b) => (itemTime(a) || '99').localeCompare(itemTime(b) || '99'));

export const sortedDays = (trip) => [...trip.days].sort((a, b) => a.date.localeCompare(b.date));

export const dayNumber = (trip, day) => sortedDays(trip).findIndex((d) => d.id === day.id) + 1;

export const dayTitle = (trip, day) => `Day ${dayNumber(trip, day)} · ${day.city || 'Unplanned'}`;

export function daySubtitle(day) {
  const n = day.items.length;
  return `${fmtDate(day.date)} · ${n} item${n === 1 ? '' : 's'}`;
}

export const tripSubtitle = (trip) => {
  const n = trip.travelers.length;
  return `${fmtRange(trip)} · ${n} traveler${n === 1 ? '' : 's'}`;
};

export function findNode(trip, sel) {
  if (!sel || sel.type === 'trip') return { type: 'trip' };
  const day = trip.days.find((d) => d.id === sel.dayId);
  if (!day) return { type: 'trip' };
  if (sel.type === 'day') return { type: 'day', day };
  const item = day.items.find((i) => i.id === sel.itemId);
  return item ? { type: 'item', day, item } : { type: 'day', day };
}

const CURRENCIES = ['EUR', 'USD', 'GBP', 'CHF'];

export const TRIP_FIELDS = [
  { key: 'title', label: 'Title' },
  { key: 'startDate', label: 'Start date', type: 'date', half: true },
  { key: 'endDate', label: 'End date', type: 'date', half: true },
  { key: 'travelers', label: 'Travelers (comma-separated)', type: 'list' },
  { key: 'budget.amount', label: 'Base budget', type: 'number', half: true },
  { key: 'budget.currency', label: 'Currency', type: 'select', options: CURRENCIES, half: true },
  { key: 'notes', label: 'General notes', type: 'textarea' },
];

export const DAY_FIELDS = [
  { key: 'date', label: 'Date', type: 'date', half: true },
  { key: 'city', label: 'Overnight city', half: true },
  { key: 'hotel', label: 'Hotel' },
  { key: 'summary', label: 'Daily summary', type: 'textarea' },
  { key: 'weather', label: 'Weather' },
  { key: 'transit', label: 'Transit notes', type: 'textarea' },
];

export const ITEM_FIELDS = {
  stop: [
    { key: 'title', label: 'Place' },
    { key: 'start', label: 'Arrive', type: 'time', half: true },
    { key: 'durationMin', label: 'Duration (min)', type: 'number', half: true },
    { key: 'address', label: 'Address' },
    { key: 'notes', label: 'Notes', type: 'textarea' },
  ],
  event: [
    { key: 'title', label: 'Event' },
    { key: 'time', label: 'Time', type: 'time', half: true },
    { key: 'venue', label: 'Venue', half: true },
    { key: 'address', label: 'Address' },
    { key: 'confirmation', label: 'Confirmation code', half: true },
    { key: 'tickets', label: 'Tickets', half: true },
    { key: 'notes', label: 'Notes', type: 'textarea' },
  ],
  travel: [
    { key: 'mode', label: 'Mode', type: 'select', options: Object.keys(MODE_LABEL), labels: MODE_LABEL, half: true },
    { key: 'carrier', label: 'Carrier / service', half: true },
    { key: 'from', label: 'From', half: true },
    { key: 'to', label: 'To', half: true },
    { key: 'depart', label: 'Departs', type: 'time', half: true },
    { key: 'arrive', label: 'Arrives', type: 'time', half: true },
    { key: 'distanceKm', label: 'Distance (km)', type: 'number', half: true },
    { key: 'confirmation', label: 'Confirmation code', half: true },
    { key: 'notes', label: 'Notes', type: 'textarea' },
  ],
};

export const getPath = (obj, path) => path.split('.').reduce((o, k) => o?.[k], obj);

function setPath(obj, path, value) {
  const [head, ...rest] = path.split('.');
  return { ...obj, [head]: rest.length ? setPath(obj[head] || {}, rest.join('.'), value) : value };
}

export function tripReducer(trip, action) {
  switch (action.type) {
    case 'trip':
      return setPath(trip, action.key, action.value);
    case 'day':
      return {
        ...trip,
        days: trip.days.map((d) => (d.id === action.dayId ? setPath(d, action.key, action.value) : d)),
      };
    case 'item':
      return {
        ...trip,
        days: trip.days.map((d) => (d.id !== action.dayId ? d : {
          ...d,
          items: d.items.map((i) => (i.id === action.itemId ? setPath(i, action.key, action.value) : i)),
        })),
      };
    case 'reset':
      return freshTrip();
    default:
      return trip;
  }
}
