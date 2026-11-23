import { zoneCity } from './zoneMath';

const SHORT_COUNTRY = { US: 'USA', GB: 'UK', AE: 'UAE' };
const REGION_COUNTRIES = new Set(['US', 'CA', 'AU', 'BR', 'IN', 'MX']);

const fold = (s) => (s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

let indexPromise = null;

function buildIndex(cities) {
  const entries = cities.map((c) => {
    const country = SHORT_COUNTRY[c.iso2] || c.country;
    const detail = REGION_COUNTRIES.has(c.iso2) && c.province ? `${c.province}, ${country}` : country;
    return {
      label: c.city,
      detail,
      timezone: c.timezone,
      pop: c.pop || 0,
      name: fold(c.city_ascii || c.city),
      haystack: fold([c.city, c.city_ascii, c.province, c.state_ansi, c.country, country, c.iso2].join(' ')),
    };
  });
  const known = new Set(entries.map((e) => `${e.name}|${e.timezone}`));
  const zones = typeof Intl.supportedValuesOf === 'function' ? Intl.supportedValuesOf('timeZone') : [];
  for (const zone of [...zones, 'UTC']) {
    const label = zone === 'UTC' ? 'UTC' : zoneCity(zone);
    const name = fold(label);
    if (known.has(`${name}|${zone}`)) continue;
    known.add(`${name}|${zone}`);
    entries.push({ label, detail: zone, timezone: zone, pop: 0, name, haystack: fold(`${label} ${zone}`) });
  }
  return entries.filter((e) => e.timezone);
}

export function loadCityIndex() {
  if (!indexPromise) {
    indexPromise = import('city-timezones/data/cityMap.json')
      .then((m) => buildIndex(m.default))
      .catch((err) => {
        indexPromise = null;
        throw err;
      });
  }
  return indexPromise;
}

/** Best matches for `query`: exact city name, then prefix, then word prefix, then anywhere; bigger cities first. */
export function searchCities(index, query, limit = 12) {
  const q = fold(query).trim();
  if (!q) return [];
  const tokens = q.split(/[\s,]+/).filter(Boolean);
  const scored = [];
  for (const e of index) {
    if (!tokens.every((t) => e.haystack.includes(t))) continue;
    let rank;
    if (e.name === q || e.name === tokens[0]) rank = 0;
    else if (e.name.startsWith(q) || e.name.startsWith(tokens[0])) rank = 1;
    else if (e.name.split(/[\s-]+/).some((w) => w.startsWith(tokens[0]))) rank = 2;
    else rank = 3;
    scored.push([rank, e]);
  }
  scored.sort((a, b) => a[0] - b[0] || b[1].pop - a[1].pop || a[1].label.localeCompare(b[1].label));
  return scored.slice(0, limit).map(([, e]) => e);
}
