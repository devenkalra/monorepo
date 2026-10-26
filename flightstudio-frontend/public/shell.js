const APPS = [
  { id: 'people', label: 'People', href: '/app/people/' },
  { id: 'cad', label: 'CAD', href: '/app/cad/' },
  { id: 'food', label: 'Food', href: '/app/food/' },
  { id: 'email', label: 'Email', href: '/app/email/' },
  { id: 'gmail', label: 'Gmail', href: '/app/gmail/' },
  { id: 'gallery', label: 'Gallery', href: '/app/gallery/' },
  { id: 'vacation', label: 'Vacation', href: '/app/vacation/' },
  { id: 'trips', label: 'Trips', href: '/app/trips/' },
  { id: 'productions', label: 'Productions', href: '/app/productions/' },
  { id: 'timeline', label: 'Timeline', href: '/app/timeline/' },
  { id: 'flightstudio', label: 'FlightStudio', href: '/app/flightstudio/' },
];

function renderAppsMenu(user) {
  const host = document.getElementById('apps-root');
  if (!host) return;
  const name = user?.username || user?.email || '';
  host.innerHTML = `
    <div class="apps-menu">
      <button type="button" id="apps-toggle" aria-haspopup="menu" aria-expanded="false">Apps</button>
      <div class="apps-dropdown" id="apps-dropdown" hidden role="menu"></div>
    </div>
    <span class="apps-user" title="${name}">${name}</span>
  `;
  const dropdown = host.querySelector('#apps-dropdown');
  dropdown.innerHTML = APPS.map((app) => {
    const active = app.id === 'flightstudio' ? ' class="active"' : '';
    return `<a href="${app.href}" role="menuitem"${active}>${app.label}</a>`;
  }).join('');
  const toggle = host.querySelector('#apps-toggle');
  toggle.onclick = (event) => {
    event.stopPropagation();
    const open = dropdown.hidden;
    dropdown.hidden = !open;
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
  };
  document.addEventListener('click', () => {
    dropdown.hidden = true;
    toggle.setAttribute('aria-expanded', 'false');
  });
}

document.addEventListener('DOMContentLoaded', () => {
  const logout = document.getElementById('btn-logout');
  if (!logout) return;
  logout.onclick = async () => {
    const token = localStorage.getItem('access_token');
    try {
      await fetch('/api/auth/logout/', {
        method: 'POST',
        credentials: 'include',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
    } catch (_) { /* ignore */ }
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('current_user');
    location.href = `/login/?next=${encodeURIComponent('/app/flightstudio/')}`;
  };
});
