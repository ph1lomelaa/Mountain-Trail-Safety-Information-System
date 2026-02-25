const state = {
  apiBase: 'http://127.0.0.1:8000',
  role: localStorage.getItem('mtsis_lite_role') || 'admin',
  user: null,
  trails: [],
  selectedTrailId: null,
  pois: [],
  h3Boundaries: [],
  trailH3Cache: {},
  checkins: [],
  myCheckins: [],
  toggles: {
    h3: false,
    pois: false,
    checkins: false,
  },
};

const el = {
  roleSelect: document.getElementById('roleSelect'),
  applyRoleBtn: document.getElementById('applyRoleBtn'),
  userName: document.getElementById('userName'),
  trailSearchInput: document.getElementById('trailSearchInput'),
  difficultyFilter: document.getElementById('difficultyFilter'),
  trailList: document.getElementById('trailList'),
  selectedTrailEmpty: document.getElementById('selectedTrailEmpty'),
  selectedTrailContent: document.getElementById('selectedTrailContent'),
  selectedTrailName: document.getElementById('selectedTrailName'),
  selectedTrailMeta: document.getElementById('selectedTrailMeta'),
  expectedReturnInput: document.getElementById('expectedReturnInput'),
  phoneInput: document.getElementById('phoneInput'),
  startRouteBtn: document.getElementById('startRouteBtn'),
  myCheckinsList: document.getElementById('myCheckinsList'),
  monitorPanel: document.getElementById('monitorPanel'),
  monitorTableBody: document.getElementById('monitorTableBody'),
  triggerOverdueBtn: document.getElementById('triggerOverdueBtn'),
  toggleH3: document.getElementById('toggleH3'),
  togglePois: document.getElementById('togglePois'),
  toggleCheckins: document.getElementById('toggleCheckins'),
  refreshBtn: document.getElementById('refreshBtn'),
  statusText: document.getElementById('statusText'),
};

let map;
let selectedTrailLayer;
let routeH3Layer;
let h3Layer;
let poiLayer;
let checkinLayer;

function setStatus(message, isError = false) {
  el.statusText.textContent = message;
  el.statusText.style.color = isError ? '#cf2e2e' : '#33415f';
}

function getHeaders(withJson = false) {
  const headers = {
    'X-Demo-Role': state.role,
  };
  if (withJson) {
    headers['Content-Type'] = 'application/json';
  }
  return headers;
}

async function api(path, options = {}) {
  const url = `${state.apiBase.replace(/\/+$/, '')}${path}`;
  const response = await fetch(url, options);
  const contentType = response.headers.get('content-type') || '';
  const data = contentType.includes('application/json') ? await response.json() : await response.text();

  if (!response.ok) {
    const detail = typeof data === 'object' && data && data.detail ? data.detail : `${response.status} ${response.statusText}`;
    throw new Error(detail);
  }

  return data;
}

function normalizeTrail(trail) {
  let geometry = null;
  if (trail.geometry_json) {
    if (typeof trail.geometry_json === 'string') {
      try {
        geometry = JSON.parse(trail.geometry_json);
      } catch {
        geometry = null;
      }
    } else {
      geometry = trail.geometry_json;
    }
  }

  if (!geometry && trail.start_lat && trail.start_lng && trail.end_lat && trail.end_lng) {
    geometry = {
      type: 'LineString',
      coordinates: [
        [trail.start_lng, trail.start_lat],
        [trail.end_lng, trail.end_lat],
      ],
    };
  }

  const coordinates = geometry?.type === 'LineString' ? geometry.coordinates : [];
  const latlngs = coordinates.map(([lng, lat]) => [lat, lng]);

  return {
    ...trail,
    latlngs,
  };
}

function isMountainTrail(trail) {
  const description = String(trail.description || '').toLowerCase();
  const name = String(trail.name || '').toLowerCase();
  const startLat = Number(trail.start_lat);

  const hasMountainSacScale =
    description.includes('sac_scale=mountain_hiking') ||
    description.includes('sac_scale=demanding_mountain_hiking') ||
    description.includes('sac_scale=alpine_hiking') ||
    description.includes('sac_scale=demanding_alpine_hiking') ||
    description.includes('sac_scale=difficult_alpine_hiking');

  if (hasMountainSacScale) return true;

  if (!Number.isNaN(startLat) && startLat < 43.2) return true;

  return (
    name.includes('пик') ||
    name.includes('перевал') ||
    name.includes('ущель') ||
    name.includes('mountain') ||
    name.includes('peak') ||
    name.includes('pass')
  );
}

function getTrailById(trailId) {
  return state.trails.find((x) => String(x.id) === String(trailId));
}

function getFilteredTrails() {
  const search = el.trailSearchInput.value.trim().toLowerCase();
  const difficulty = el.difficultyFilter.value;

  return state.trails.filter((trail) => {
    const byDifficulty = difficulty === 'all' || trail.difficulty === difficulty;
    const bySearch =
      !search || trail.name.toLowerCase().includes(search) || String(trail.h3_index || '').includes(search);
    return byDifficulty && bySearch;
  });
}

function initMap() {
  map = L.map('map', {
    zoomControl: true,
  }).setView([43.238949, 76.889709], 11);

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 18,
    attribution: '&copy; OpenStreetMap contributors',
  }).addTo(map);

  selectedTrailLayer = L.layerGroup().addTo(map);
  routeH3Layer = L.layerGroup().addTo(map);
  h3Layer = L.layerGroup().addTo(map);
  poiLayer = L.layerGroup().addTo(map);
  checkinLayer = L.layerGroup().addTo(map);
}

function renderTrailList() {
  const filtered = getFilteredTrails();
  el.trailList.innerHTML = '';

  if (filtered.length === 0) {
    el.trailList.innerHTML = '<div class="text-muted">Маршруты не найдены.</div>';
    return;
  }

  for (const trail of filtered) {
    const item = document.createElement('button');
    item.className = `trail-item ${String(trail.id) === String(state.selectedTrailId) ? 'active' : ''}`;
    item.type = 'button';
    item.innerHTML = `
      <div class="name">${trail.name}</div>
      <div class="meta">${trail.difficulty} • ${Number(trail.length_km || 0).toFixed(1)} km</div>
    `;
    item.addEventListener('click', () => selectTrail(trail.id));
    el.trailList.appendChild(item);
  }
}

function drawSelectedTrail() {
  selectedTrailLayer.clearLayers();
  const trail = getTrailById(state.selectedTrailId);

  if (!trail || !trail.latlngs || trail.latlngs.length < 2) {
    el.selectedTrailEmpty.classList.remove('hidden');
    el.selectedTrailContent.classList.add('hidden');
    return;
  }

  el.selectedTrailEmpty.classList.add('hidden');
  el.selectedTrailContent.classList.remove('hidden');
  el.selectedTrailName.textContent = trail.name;
  el.selectedTrailMeta.textContent = `${trail.difficulty} • ${Number(trail.length_km || 0).toFixed(1)} km • H3 ${trail.h3_index}`;

  L.polyline(trail.latlngs, {
    color: '#0a66c2',
    weight: 5,
    opacity: 0.95,
  }).addTo(selectedTrailLayer);

  const start = trail.latlngs[0];
  const end = trail.latlngs[trail.latlngs.length - 1];
  L.circleMarker(start, { radius: 6, color: '#148a41', fillOpacity: 1 }).addTo(selectedTrailLayer).bindTooltip('Start');
  L.circleMarker(end, { radius: 6, color: '#cf2e2e', fillOpacity: 1 }).addTo(selectedTrailLayer).bindTooltip('End');

  map.fitBounds(trail.latlngs, { padding: [40, 40] });
}

async function ensureH3BoundariesLoaded() {
  if (state.h3Boundaries.length > 0) return;
  try {
    const rows = await api('/h3/region/9/boundaries', {
      headers: getHeaders(),
    });
    state.h3Boundaries = rows || [];
  } catch (error) {
    setStatus(`Не удалось загрузить H3: ${error.message}`, true);
  }
}

async function ensureTrailH3Loaded(trailId) {
  if (!trailId) return;
  const key = String(trailId);
  if (state.trailH3Cache[key]) return;

  try {
    const data = await api(`/trails/${trailId}/h3-cells?resolution=9`, {
      headers: getHeaders(),
    });
    state.trailH3Cache[key] = data.cells || [];
  } catch {
    state.trailH3Cache[key] = [];
  }
}

function drawH3() {
  h3Layer.clearLayers();
  routeH3Layer.clearLayers();
  if (!state.toggles.h3) return;

  for (const cell of state.h3Boundaries) {
    if (!Array.isArray(cell.boundary) || cell.boundary.length === 0) continue;
    const latlngs = cell.boundary.map(([lng, lat]) => [lat, lng]);
    const risk = cell.active_checkins > 0 ? '#cf2e2e' : '#6b7486';

    L.polygon(latlngs, {
      color: risk,
      weight: 1,
      fillColor: risk,
      fillOpacity: 0.12,
    })
      .bindTooltip(`H3 ${cell.h3_index}\nTrails: ${cell.trails}\nActive: ${cell.active_checkins}`)
      .addTo(h3Layer);
  }

  const selectedCells = state.selectedTrailId ? state.trailH3Cache[String(state.selectedTrailId)] || [] : [];
  for (const cell of selectedCells) {
    if (!Array.isArray(cell.boundary) || cell.boundary.length === 0) continue;
    const latlngs = cell.boundary.map(([lng, lat]) => [lat, lng]);
    L.polygon(latlngs, {
      color: '#0a66c2',
      weight: 2,
      fillColor: '#0a66c2',
      fillOpacity: 0.28,
    })
      .bindTooltip(`Route H3 ${cell.h3_index}`)
      .addTo(routeH3Layer);
  }
}

async function ensurePoisLoaded() {
  if (state.pois.length > 0) return;
  try {
    const rows = await api('/pois/', {
      headers: getHeaders(),
    });
    state.pois = rows || [];
  } catch (error) {
    setStatus(`Не удалось загрузить POI: ${error.message}`, true);
  }
}

function drawPois() {
  poiLayer.clearLayers();
  if (!state.toggles.pois) return;

  for (const poi of state.pois) {
    if (typeof poi.latitude !== 'number' || typeof poi.longitude !== 'number') continue;

    L.circleMarker([poi.latitude, poi.longitude], {
      radius: 4,
      color: '#8a5a00',
      fillColor: '#d08f1f',
      fillOpacity: 0.9,
      weight: 1,
    })
      .bindTooltip(`${poi.name}\n${poi.category}`)
      .addTo(poiLayer);
  }
}

function drawCheckins() {
  checkinLayer.clearLayers();
  if (!state.toggles.checkins) return;

  const points = (state.role === 'hiker' ? state.myCheckins : state.checkins).filter(
    (c) => c.status === 'active' || c.status === 'overdue',
  );

  for (const c of points) {
    if (typeof c.latitude !== 'number' || typeof c.longitude !== 'number') continue;
    const color = c.status === 'overdue' ? '#cf2e2e' : '#148a41';
    L.circleMarker([c.latitude, c.longitude], {
      radius: 6,
      color,
      fillColor: color,
      fillOpacity: 0.85,
      weight: 2,
    })
      .bindTooltip(`Check-in #${c.id}\nTrail: ${c.trail_id}\nStatus: ${c.status}`)
      .addTo(checkinLayer);
  }
}

function renderSession() {
  el.userName.textContent = state.user?.full_name || state.user?.username || `Demo ${state.role}`;
  el.monitorPanel.classList.toggle('hidden', !(state.role === 'ranger' || state.role === 'admin'));
}

function renderMyCheckins() {
  el.myCheckinsList.innerHTML = '';

  if (state.myCheckins.length === 0) {
    el.myCheckinsList.innerHTML = '<div class="text-muted">Нет активных check-ins.</div>';
    return;
  }

  for (const c of state.myCheckins) {
    const trail = getTrailById(c.trail_id);
    const card = document.createElement('div');
    card.className = 'checkin-card';
    card.innerHTML = `
      <div><span class="badge ${c.status}">${c.status}</span></div>
      <div>Маршрут: <strong>${trail ? trail.name : `#${c.trail_id}`}</strong></div>
      <div class="text-muted">Телефон: ${c.phone_number || c.emergency_contact || '-'}</div>
      <div class="text-muted">Expected: ${new Date(c.expected_return).toLocaleString('ru-RU')}</div>
    `;

    if (c.status !== 'returned') {
      const btn = document.createElement('button');
      btn.className = 'btn btn-secondary';
      btn.textContent = 'Завершить маршрут (checkout)';
      btn.addEventListener('click', async () => {
        try {
          await api(`/safety/checkout/${c.id}`, {
            method: 'POST',
            headers: getHeaders(),
          });

          state.myCheckins = state.myCheckins.filter((row) => row.id !== c.id);
          state.h3Boundaries = [];
          state.selectedTrailId = null;

          if (state.toggles.h3) {
            await ensureH3BoundariesLoaded();
          }

          drawCheckins();
          renderTrailList();
          drawSelectedTrail();
          drawH3();

          setStatus(`Маршрут завершен: check-in #${c.id}`);
          await loadSafetyData();
          drawCheckins();
        } catch (error) {
          setStatus(`Ошибка checkout: ${error.message}`, true);
        }
      });
      card.appendChild(btn);
    }

    el.myCheckinsList.appendChild(card);
  }
}

function renderMonitorTable() {
  el.monitorTableBody.innerHTML = '';

  for (const c of state.checkins) {
    const trail = getTrailById(c.trail_id);
    const row = document.createElement('tr');
    row.innerHTML = `
      <td>#${c.id}</td>
      <td>User #${c.user_id}</td>
      <td>${trail ? `${trail.name} (${trail.difficulty}, ${Number(trail.length_km).toFixed(1)} km)` : `#${c.trail_id}`}</td>
      <td>${c.phone_number || c.emergency_contact || '-'}</td>
      <td>${new Date(c.expected_return).toLocaleString('ru-RU')}</td>
      <td>${c.status}</td>
    `;

    row.addEventListener('click', async () => {
      await selectTrail(c.trail_id);
      if (typeof c.latitude === 'number' && typeof c.longitude === 'number') {
        map.setView([c.latitude, c.longitude], Math.max(map.getZoom(), 12));
      }
      setStatus(`Показан маршрут check-in #${c.id}`);
    });

    el.monitorTableBody.appendChild(row);
  }
}

async function selectTrail(trailId) {
  state.selectedTrailId = trailId;
  renderTrailList();
  drawSelectedTrail();

  if (state.toggles.h3) {
    await ensureTrailH3Loaded(trailId);
    drawH3();
  }
}

function clearLayers() {
  selectedTrailLayer.clearLayers();
  routeH3Layer.clearLayers();
  h3Layer.clearLayers();
  poiLayer.clearLayers();
  checkinLayer.clearLayers();
}

async function loadCurrentUser() {
  try {
    state.user = await api('/auth/me', {
      headers: getHeaders(),
    });
  } catch {
    state.user = {
      username: `demo_${state.role}`,
      full_name: `Demo ${state.role}`,
      role: state.role,
    };
  }
}

async function loadTrails() {
  const rows = await api('/trails/', {
    headers: getHeaders(),
  });
  state.trails = (rows || [])
    .map(normalizeTrail)
    .filter(isMountainTrail);

  if (state.selectedTrailId && !getTrailById(state.selectedTrailId)) {
    state.selectedTrailId = null;
  }

  renderTrailList();
  drawSelectedTrail();
}

async function loadSafetyData() {
  try {
    state.myCheckins = await api('/safety/mine', {
      headers: getHeaders(),
    });
  } catch {
    state.myCheckins = [];
  }

  if (state.role === 'ranger' || state.role === 'admin') {
    try {
      state.checkins = await api('/safety/active', {
        headers: getHeaders(),
      });
    } catch {
      state.checkins = [];
    }
  } else {
    state.checkins = [];
  }

  renderMyCheckins();
  renderMonitorTable();
}

async function refreshAll() {
  setStatus('Загрузка данных...');
  try {
    await loadCurrentUser();
    await loadTrails();
    await loadSafetyData();

    if (state.toggles.h3) {
      await ensureH3BoundariesLoaded();
      await ensureTrailH3Loaded(state.selectedTrailId);
    }
    drawH3();

    if (state.toggles.pois) {
      await ensurePoisLoaded();
    }
    drawPois();

    drawCheckins();
    renderSession();

    setStatus(`Данные обновлены. Роль: ${state.role}. Маршрутов: ${state.trails.length}`);
  } catch (error) {
    setStatus(`Ошибка загрузки: ${error.message}`, true);
  }
}

async function startRoute() {
  const trail = getTrailById(state.selectedTrailId);
  if (!trail) {
    setStatus('Выберите маршрут.', true);
    return;
  }

  const expected = el.expectedReturnInput.value;
  if (!expected) {
    setStatus('Укажите ожидаемое время возвращения.', true);
    return;
  }

  const phone = el.phoneInput.value.trim();
  if (!phone) {
    setStatus('Укажите номер телефона туриста.', true);
    return;
  }

  const start = trail.latlngs && trail.latlngs.length > 0 ? trail.latlngs[0] : [43.238949, 76.889709];

  const payload = {
    trail_id: Number(trail.id),
    expected_return: new Date(expected).toISOString(),
    emergency_contact: phone,
    phone_number: phone,
    latitude: start[0],
    longitude: start[1],
    notes: `Start from MTSIS Lite for trail ${trail.id}`,
  };

  try {
    const created = await api('/safety/checkin', {
      method: 'POST',
      headers: getHeaders(true),
      body: JSON.stringify(payload),
    });

    setStatus(`Маршрут начат. Check-in #${created.id}`);
    await loadSafetyData();
    drawCheckins();
  } catch (error) {
    setStatus(`Ошибка start route: ${error.message}`, true);
  }
}

async function applyRole() {
  state.role = el.roleSelect.value;
  localStorage.setItem('mtsis_lite_role', state.role);
  state.selectedTrailId = null;
  state.pois = [];
  state.h3Boundaries = [];
  state.trailH3Cache = {};
  clearLayers();
  await refreshAll();
}

function setupEvents() {
  el.roleSelect.value = state.role;

  const defaultExpected = new Date(Date.now() + 4 * 60 * 60 * 1000);
  el.expectedReturnInput.value = defaultExpected.toISOString().slice(0, 16);

  el.applyRoleBtn.addEventListener('click', applyRole);
  el.trailSearchInput.addEventListener('input', renderTrailList);
  el.difficultyFilter.addEventListener('change', renderTrailList);
  el.startRouteBtn.addEventListener('click', startRoute);

  el.toggleH3.addEventListener('change', async (event) => {
    state.toggles.h3 = event.target.checked;
    if (state.toggles.h3) {
      await ensureH3BoundariesLoaded();
      await ensureTrailH3Loaded(state.selectedTrailId);
    }
    drawH3();
  });

  el.togglePois.addEventListener('change', async (event) => {
    state.toggles.pois = event.target.checked;
    if (state.toggles.pois) {
      await ensurePoisLoaded();
    }
    drawPois();
  });

  el.toggleCheckins.addEventListener('change', async (event) => {
    state.toggles.checkins = event.target.checked;
    if (state.toggles.checkins) {
      await loadSafetyData();
    }
    drawCheckins();
  });

  el.refreshBtn.addEventListener('click', refreshAll);

  el.triggerOverdueBtn.addEventListener('click', async () => {
    try {
      const result = await api('/safety/trigger-overdue', {
        method: 'POST',
        headers: getHeaders(),
      });
      setStatus(result.detail || 'Overdue обновлены');
      await loadSafetyData();
      drawCheckins();
    } catch (error) {
      setStatus(`Ошибка trigger overdue: ${error.message}`, true);
    }
  });
}

async function boot() {
  initMap();
  setupEvents();
  renderSession();
  renderTrailList();
  renderMyCheckins();
  drawSelectedTrail();
  await refreshAll();
}

boot();
