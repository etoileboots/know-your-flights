// ── URL params ───────────────────────────────────────────────
const params = new URLSearchParams(location.search);
const rawFrom = params.get('from') || '';
const rawTo   = params.get('to')   || '';
let routeFrom = rawFrom.toUpperCase().replace(/[^A-Z]/g, '').slice(0, 3);
let routeTo   = rawTo.toUpperCase().replace(/[^A-Z]/g, '').slice(0, 3);
if (!rawFrom && params.get('q')) {
  const q = params.get('q').toUpperCase();
  const m = q.match(/^([A-Z]{3})[^A-Z]*([A-Z]{3})$/);
  if (m) { routeFrom = m[1]; routeTo = m[2]; }
}
// ── App state ────────────────────────────────────────────────
let routeData       = null;
let selectedCarrier = null;
let selectedYearMin = 2018, selectedYearMax = 2026;
let dataMeta = { year_min: 2018, year_max: 2026, year_min_month_name: 'January', partial_year: 2026, partial_month_name: 'April' };
fetch('./data/aggregations/map/meta.json').then(r => r.json()).then(m => { dataMeta = m; }).catch(() => {});
function fmtDateRange(yMin, yMax) {
  const partial = yMax === dataMeta.partial_year;
  if (yMin === yMax) return partial ? `${dataMeta.partial_month_name} ${yMax}` : String(yMin);
  const end = partial ? `${dataMeta.partial_month_name} ${yMax}` : String(yMax);
  const start = partial ? `January ${yMin}` : String(yMin);
  return `${start}–${end}`;
}
let currentHeatmap  = null;
let currentMonthly  = null;
let polarDelayMode  = 'dep';
let macroDelayMode  = 'dep';

// ── Constants ────────────────────────────────────────────────
const YR_MIN = 2018, YR_MAX = 2026, YR_RANGE = YR_MAX - YR_MIN;
const MONTHS     = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];
const MONTH_LONG = ['January','February','March','April','May','June','July','August','September','October','November','December'];
const DOW_NAMES  = ['MON','TUE','WED','THU','FRI','SAT','SUN'];
const DOW_LONG   = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
const TIME_NAMES = ['Morning · 6–10am','Midday · 10am–3pm','Afternoon · 3–7pm','Night · 7–11pm'];
const DOW_SHORT  = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
// BTS national avg % of flights ≥15 min late, 2018–2025
const NAT_MONTHLY = [19.0, 19.5, 19.5, 18.5, 21.0, 25.5, 26.0, 21.0, 14.5, 13.5, 15.5, 20.5];

// ── Color helpers ────────────────────────────────────────────
function lerpHex(c1, c2, t) {
  const p = h => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
  const [r1, g1, b1] = p(c1), [r2, g2, b2] = p(c2);
  return `rgb(${Math.round(r1 + (r2-r1)*t)},${Math.round(g1 + (g2-g1)*t)},${Math.round(b1 + (b2-b1)*t)})`;
}

function delayColor(pct) {
  if (pct == null) return '#94A3B8';
  const t = Math.max(0, Math.min(1, (pct - 8) / 22));
  if (t <= 0.5) return lerpHex('#22C55E', '#EAB308', t * 2);
  return lerpHex('#EAB308', '#EF4444', (t - 0.5) * 2);
}

function fmtDelay(v) {
  if (v == null) return { text: '—', cls: '' };
  const t = (v >= 0 ? `+${v.toFixed(1)}` : v.toFixed(1)) + ' min';
  const cls = v <= 2 ? 'delay-good' : v <= 10 ? 'delay-warn' : 'delay-bad';
  return { text: t, cls };
}

// ── SVG helpers ──────────────────────────────────────────────
function svgNS(tag) { return document.createElementNS('http://www.w3.org/2000/svg', tag); }
function pDeg(d) { return d * Math.PI / 180; }

function arcPath(startDeg, endDeg, innerR, outerR) {
  const a1 = pDeg(startDeg - 90), a2 = pDeg(endDeg - 90);
  const lf = (endDeg - startDeg) > 180 ? 1 : 0;
  const [ox1, oy1] = [Math.cos(a1)*outerR, Math.sin(a1)*outerR];
  const [ox2, oy2] = [Math.cos(a2)*outerR, Math.sin(a2)*outerR];
  if (innerR < 1) return `M0 0 L${ox1} ${oy1} A${outerR} ${outerR} 0 ${lf} 1 ${ox2} ${oy2}Z`;
  const [ix1, iy1] = [Math.cos(a1)*innerR, Math.sin(a1)*innerR];
  const [ix2, iy2] = [Math.cos(a2)*innerR, Math.sin(a2)*innerR];
  return `M${ix1} ${iy1} L${ox1} ${oy1} A${outerR} ${outerR} 0 ${lf} 1 ${ox2} ${oy2} L${ix2} ${iy2} A${innerR} ${innerR} 0 ${lf} 0 ${ix1} ${iy1}Z`;
}

// ── Route data fetch ──────────────────────────────────────────
async function loadRouteData(from, to) {
  const scopeEl = document.getElementById('route-scope');
  scopeEl.textContent = `Loading ${from}–${to} data…`;
  try {
    const r = await fetch(`./data/aggregations/routes/${from}-${to}.json`, {cache: 'no-store'});
    if (!r.ok) throw new Error('not found');
    routeData = await r.json();
    const rd = routeData.route;
    scopeEl.textContent = `BTS On-Time Data · ${rd.year_min}–${rd.year_max} · ${rd.total_flights.toLocaleString()} flights analyzed`;
  } catch {
    routeData = null;
    showNotFoundState(from, to);
    return;
  }
  renderAll();
}

// ── Route search controls ─────────────────────────────────────
function applyRouteHeader(from, to) {
  routeFrom = from; routeTo = to;
  document.getElementById('from-input').value = from;
  document.getElementById('to-input').value   = to;
  document.getElementById('route-title').textContent = `${from} to ${to} Historical Route Performance`;
  document.title = `Know Your Flights — ${from} to ${to} Route Performance`;
  const mode = macroDelayMode === 'dep' ? 'departure' : 'arrival';
  document.getElementById('tier5-sub').textContent = `Average ${mode} delay · ${from} to ${to}`;
}

function lookupRoute() {
  const from = document.getElementById('from-input').value.trim().toUpperCase().replace(/[^A-Z]/g, '').slice(0, 3);
  const to   = document.getElementById('to-input').value.trim().toUpperCase().replace(/[^A-Z]/g, '').slice(0, 3);
  clearInputError('from-input'); clearInputError('to-input');
  let valid = true;
  if (from.length !== 3) { showInputError('from-input', 'Enter a 3-letter airport code or city name'); valid = false; }
  else if (!isValidCode(from)) { showInputError('from-input', `"${from}" is not a known airport`); valid = false; }
  if (to.length !== 3) { showInputError('to-input', 'Enter a 3-letter airport code or city name'); valid = false; }
  else if (!isValidCode(to)) { showInputError('to-input', `"${to}" is not a known airport`); valid = false; }
  if (from === to && from.length === 3) { showInputError('to-input', 'Origin and destination must differ'); valid = false; }
  if (!valid) return;
  if (from.length === 3 && to.length === 3 && from !== to) {
    const url = new URL(location.href);
    url.searchParams.set('from', from); url.searchParams.set('to', to);
    url.searchParams.delete('q'); url.searchParams.delete('mode');
    url.searchParams.delete('carrier'); url.searchParams.delete('num');
    history.pushState({}, '', url);
    selectedCarrier = null;
    document.querySelectorAll('.carrier-link').forEach(l => l.classList.remove('active-carrier'));
    applyRouteHeader(from, to);
    showRouteState();
    loadRouteData(from, to);
  }
}

function doLookup() {
  lookupRoute();
}

function swapRoute() {
  const fromEl = document.getElementById('from-input');
  const toEl   = document.getElementById('to-input');
  const a = fromEl.value; const b = toEl.value;
  fromEl.value = b; toEl.value = a;
  clearInputError('from-input'); clearInputError('to-input');
}

// ── Airport autocomplete ──────────────────────────────────────
let airportList = [];

async function loadAirportList() {
  try {
    const r = await fetch('./data/aggregations/map/airports.geojson');
    const gj = await r.json();
    airportList = gj.features.map(f => ({
      code: f.properties.code,
      name: f.properties.name || '',
      city: f.properties.city || '',
      state: f.properties.state || '',
      flights: f.properties.flights || 0,
    }));
    ['from-input', 'to-input'].forEach(id => {
      if (document.activeElement && document.activeElement.id === id) {
        showDropdown(id, document.getElementById(id).value);
      }
    });
  } catch {}
}

let activeAcInput = null;

function matchAirports(query) {
  if (!airportList.length) return [];
  if (!query.trim()) {
    return [...airportList].sort((a, b) => a.code.localeCompare(b.code));
  }
  const q = query.trim().toUpperCase();
  const rest = query.trim().toLowerCase();
  const byCode = airportList.filter(a => a.code.startsWith(q));
  const byCity = airportList.filter(a =>
    !a.code.startsWith(q) &&
    (a.city.toLowerCase().includes(rest) || a.name.toLowerCase().includes(rest))
  );
  return [...byCode, ...byCity];
}

function isValidCode(code) {
  if (!airportList.length) return true;
  return airportList.some(a => a.code === code.toUpperCase());
}

function formatCity(city, state) {
  if (!state) return city;
  if (city.endsWith(`, ${state}`)) return city;
  return `${city}, ${state}`;
}

function dropIdFor(inputId) {
  return inputId === 'from-input' ? 'from-dropdown' : 'to-dropdown';
}

function showDropdown(inputId, query) {
  const dropId = dropIdFor(inputId);
  const drop = document.getElementById(dropId);
  const matches = matchAirports(query);
  if (!matches.length) { drop.style.display = 'none'; return; }
  drop.innerHTML = matches.map(a =>
    `<div class="ac-item" data-code="${a.code}" data-input="${inputId}" tabindex="-1">
      <span class="ac-code">${a.code}</span>
      <span class="ac-name">${formatCity(a.city, a.state)}</span>
    </div>`
  ).join('');
  drop.style.display = '';
  drop.querySelectorAll('.ac-item').forEach(item => {
    item.addEventListener('mousedown', e => {
      e.preventDefault();
      selectAirport(item.dataset.input, item.dataset.code);
    });
  });
}

function selectAirport(inputId, code) {
  const inp = document.getElementById(inputId);
  inp.value = code;
  inp.classList.remove('input-error');
  const errEl = inp.parentElement.querySelector('.input-error-msg');
  if (errEl) errEl.remove();
  document.getElementById(dropIdFor(inputId)).style.display = 'none';
}

function hideDropdown(inputId) {
  if (inputId) {
    const drop = document.getElementById(dropIdFor(inputId));
    if (drop) drop.style.display = 'none';
  } else {
    ['from-dropdown','to-dropdown'].forEach(id => {
      const d = document.getElementById(id); if (d) d.style.display = 'none';
    });
  }
}

function showInputError(inputId, msg) {
  const inp = document.getElementById(inputId);
  inp.classList.add('input-error');
  const existing = inp.parentElement.querySelector('.input-error-msg');
  if (existing) existing.remove();
  const err = document.createElement('span');
  err.className = 'input-error-msg';
  err.textContent = msg;
  inp.parentElement.appendChild(err);
}

function clearInputError(inputId) {
  const inp = document.getElementById(inputId);
  if (inp) {
    inp.classList.remove('input-error');
    const e = inp.parentElement.querySelector('.input-error-msg');
    if (e) e.remove();
  }
}

['from-input', 'to-input'].forEach(id => {
  const el = document.getElementById(id);
  const dropId = dropIdFor(id);
  el.addEventListener('focus', () => { activeAcInput = id; showDropdown(id, el.value); });
  el.addEventListener('input', e => { clearInputError(id); showDropdown(id, e.target.value); });
  el.addEventListener('keydown', e => {
    if (e.key === 'Enter') { hideDropdown(id); doLookup(); }
    if (e.key === 'Escape') hideDropdown(id);
    if (e.key === 'ArrowDown') {
      const items = document.querySelectorAll(`#${dropId} .ac-item`);
      if (items.length) { e.preventDefault(); items[0].focus(); }
    }
  });
  el.addEventListener('blur', () => setTimeout(() => hideDropdown(id), 150));
});

['from-dropdown', 'to-dropdown'].forEach(dropId => {
  const drop = document.getElementById(dropId);
  if (!drop) return;
  drop.addEventListener('keydown', e => {
    const items = [...drop.querySelectorAll('.ac-item')];
    const idx = items.indexOf(document.activeElement);
    if (e.key === 'ArrowDown' && idx < items.length - 1) { e.preventDefault(); items[idx + 1].focus(); }
    if (e.key === 'ArrowUp') { e.preventDefault(); idx > 0 ? items[idx - 1].focus() : document.getElementById(activeAcInput || 'from-input').focus(); }
    if (e.key === 'Enter' && document.activeElement.classList.contains('ac-item')) {
      document.activeElement.dispatchEvent(new MouseEvent('mousedown'));
    }
  });
});

loadAirportList();
// ── Year range slider ─────────────────────────────────────────
function updateYearSlider() {
  const startEl = document.getElementById('yr-start');
  const endEl   = document.getElementById('yr-end');
  if (!startEl || !endEl) return;
  let s = parseInt(startEl.value), e = parseInt(endEl.value);
  if (s > e) { endEl.value = s; e = s; }
  selectedYearMin = s; selectedYearMax = e;
  // When both thumbs overlap at max, raise start so it can be dragged left
  startEl.style.zIndex = (s >= YR_MAX) ? '5' : '';
  const leftPct  = (s - YR_MIN) / YR_RANGE * 100;
  const rightPct = (e - YR_MIN) / YR_RANGE * 100;
  const fill = document.getElementById('yr-fill');
  if (fill) { fill.style.left = leftPct + '%'; fill.style.width = (rightPct - leftPct) + '%'; }
  const lbl = document.getElementById('yr-selected-label');
  if (lbl) {
    lbl.textContent = fmtDateRange(s, e);
  }
  applyYearFilter();
  drawMacroChart(selectedCarrier);
}

['yr-start', 'yr-end'].forEach(id => {
  const el = document.getElementById(id);
  if (el) el.addEventListener('input', updateYearSlider);
});
updateYearSlider();

function getYearRangeData(yMin, yMax) {
  const rd = routeData;
  if (!rd) return { accuracy: null, meanArr: 0, meanDep: 0 };
  // treat slider at or beyond data bounds as "all"
  const isAll = yMin <= rd.route.year_min && yMax >= rd.route.year_max;
  if (isAll) return { accuracy: rd.accuracy, meanArr: rd.accuracy.mean_arr_delay, meanDep: rd.accuracy.mean_dep_delay };
  const years = (rd.annual?.baseline || []).filter(b => b.year >= yMin && b.year <= yMax);
  if (!years.length) return { accuracy: rd.accuracy, meanArr: rd.accuracy.mean_arr_delay, meanDep: rd.accuracy.mean_dep_delay };
  if (years.length === 1) {
    const yrKey = String(years[0].year);
    const acc = rd.accuracy_by_year?.[yrKey] || rd.accuracy;
    return { accuracy: acc, meanArr: years[0].arr_delay ?? 0, meanDep: years[0].dep_delay ?? 0 };
  }
  const totalF = years.reduce((a, b) => a + (b.flights || 1), 0);
  const wArr = years.reduce((a, b) => a + (b.arr_delay || 0) * (b.flights || 1), 0) / totalF;
  const wDep = years.reduce((a, b) => a + (b.dep_delay || 0) * (b.flights || 1), 0) / totalF;
  const byYear = rd.accuracy_by_year || {};
  const yd = years.map(y => ({ f: y.flights || 1, acc: byYear[String(y.year)] })).filter(x => x.acc);
  if (!yd.length) return { accuracy: { ...rd.accuracy, mean_arr_delay: wArr, mean_dep_delay: wDep }, meanArr: wArr, meanDep: wDep };
  const totalW = yd.reduce((a, b) => a + b.f, 0);
  const wt = (key, cat) => yd.reduce((a, b) => a + (b.acc[cat]?.[key] ?? 0) * b.f, 0) / totalW;
  return {
    accuracy: {
      dep: { perfect: wt('perfect','dep'), standard: wt('standard','dep'), disruptive: wt('disruptive','dep') },
      arr: { perfect: wt('perfect','arr'), standard: wt('standard','arr'), disruptive: wt('disruptive','arr') },
      mean_dep_delay: wDep, mean_arr_delay: wArr,
    },
    meanArr: wArr, meanDep: wDep,
  };
}

function getMonthlyForRange(yMin, yMax) {
  const rd = routeData;
  if (!rd) return null;
  if (yMin === yMax) return rd.monthly_by_year?.[String(yMin)] || rd.monthly;
  const byYear = rd.monthly_by_year || {};
  const keys = Object.keys(byYear).map(Number).filter(y => y >= yMin && y <= yMax);
  if (!keys.length) return rd.monthly;
  return Array.from({length: 12}, (_, m) => {
    const vals = keys.map(y => byYear[String(y)]?.[m]).filter(v => v != null);
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
  });
}

function applyYearFilter() {
  if (!routeData) return;
  const rd = routeData;
  const yMin = selectedYearMin, yMax = selectedYearMax;
  const isAll = yMin <= rd.route.year_min && yMax >= rd.route.year_max;
  const yearLabel = fmtDateRange(isAll ? rd.route.year_min : yMin, isAll ? rd.route.year_max : yMax);

  const scopeEl = document.getElementById('route-scope');
  if (isAll) {
    scopeEl.textContent = `BTS On-Time Data · ${rd.route.year_min}–${rd.route.year_max} · ${rd.route.total_flights.toLocaleString()} flights analyzed`;
  } else {
    const years = (rd.annual?.baseline || []).filter(b => b.year >= yMin && b.year <= yMax);
    const totalF = years.reduce((a, b) => a + (b.flights || 0), 0);
    scopeEl.textContent = totalF
      ? `${yearLabel} · ${totalF.toLocaleString()} flights`
      : `${yearLabel} · limited data for this range`;
  }

  const { accuracy, meanArr, meanDep } = getYearRangeData(yMin, yMax);
  if (accuracy) {
    renderRouteKpi(accuracy, meanArr, meanDep);
    renderDivergingBar(accuracy);
  }

  const accSub = document.getElementById('acc-tier-sub');
  if (accSub) accSub.textContent = `${yearLabel} · ${rd.route.from} to ${rd.route.to} · All carriers combined`;

  const carrierSub = document.getElementById('carrier-sub');
  if (carrierSub) carrierSub.textContent = `${yearLabel} · Ranked by total flights operated · delays averaged across all flights, including on-time and early arrivals`;

  buildCarrierTable(getCarriersForRange(yMin, yMax));

  const noteEl = document.getElementById('polar-data-note');
  if (noteEl && routeData) {
    const modeLabel = polarDelayMode === 'arr' ? 'arrival' : 'departure';
    noteEl.textContent = `${yearLabel} · ${modeLabel} delay · % of flights delayed ≥15 min`;
  }

  const monthly = getMonthlyForRange(yMin, yMax);
  if (routeData.heatmap) buildPolarChart(routeData.heatmap, routeData.arr_heatmap, monthly, routeData.arr_monthly);
}

// ── Route KPI strip ───────────────────────────────────────────
function renderRouteKpi(accuracy, meanArrDelay, meanDepDelay) {
  const fmtDelay = (val, el) => {
    if (!el) return;
    if (val == null) { el.textContent = '—'; el.className = 'route-kpi-val'; return; }
    el.textContent = (val >= 0 ? '+' : '') + val.toFixed(1) + ' min';
    el.className = 'route-kpi-val';
  };
  fmtDelay(meanDepDelay, document.getElementById('kpi-depdelay'));
  fmtDelay(meanArrDelay, document.getElementById('kpi-arrdelay'));

  const hm = routeData?.heatmap;
  if (hm) {
    const validDows = hm.map((row, i) => {
      const v = row.filter(x => x !== null);
      return v.length ? { i, avg: v.reduce((a, b) => a + b, 0) / v.length } : null;
    }).filter(Boolean);
    if (validDows.length >= 2) {
      const best  = validDows.reduce((a, b) => b.avg < a.avg ? b : a);
      const worst = validDows.reduce((a, b) => b.avg > a.avg ? b : a);
      const diff  = (worst.avg - best.avg).toFixed(1);
      const diffEl = document.getElementById('kpi-day-diff');
      const hintEl = document.getElementById('kpi-day-hint');
      if (diffEl) { diffEl.textContent = DOW_LONG[best.i]; diffEl.className = 'route-kpi-val route-kpi-val--name'; }
      if (hintEl) hintEl.textContent = `${DOW_LONG[worst.i]} has ${diff}% more delayed flights · ${dataMeta.year_min}–${dataMeta.partial_year} avg`;
    }
  }

  const cars = (routeData?.carriers || []).filter(c => c.arr_delay != null);
  const diffEl = document.getElementById('kpi-carrier-diff');
  const hintEl = document.getElementById('kpi-carrier-hint');
  if (cars.length >= 2) {
    const bestC  = cars.reduce((a, b) => b.arr_delay < a.arr_delay ? b : a);
    const worstC = cars.reduce((a, b) => b.arr_delay > a.arr_delay ? b : a);
    const diff   = (worstC.arr_delay - bestC.arr_delay).toFixed(1);
    if (diffEl) { diffEl.textContent = bestC.name.split(' ')[0]; diffEl.className = 'route-kpi-val route-kpi-val--name'; }
    if (hintEl) hintEl.textContent = `${worstC.name.split(' ')[0]} averages ${diff} minutes more · ${dataMeta.year_min}–${dataMeta.partial_year} avg`;
  } else if (cars.length === 1) {
    if (diffEl) { diffEl.textContent = cars[0].name.split(' ')[0]; diffEl.className = 'route-kpi-val route-kpi-val--name'; }
    if (hintEl) hintEl.textContent = 'Sole operator on this route';
  }
}

// ── Accuracy bars ─────────────────────────────────────────────
function renderDivergingBar(accuracy) {
  function buildBar(id, seg) {
    const p = Math.round(seg.perfect), s = Math.round(seg.standard), d = Math.round(seg.disruptive);
    document.getElementById(id).innerHTML = [
      [p, 'acc-seg acc-seg-perfect'],
      [s, 'acc-seg acc-seg-standard'],
      [d, 'acc-seg acc-seg-disruptive'],
    ].map(([flex, cls]) =>
      `<div class="${cls}" style="flex:${flex}">` +
      (flex > 0 ? `<span class="acc-seg-lbl ${flex < 10 ? 'acc-seg-lbl-below' : ''}">${flex}%</span>` : '') +
      `</div>`
    ).join('');
  }
  buildBar('dep-bar', accuracy.dep);
  buildBar('arr-bar', accuracy.arr);
  if (routeData?.route) {
    const { year_min, year_max, from, to } = routeData.route;
    const yMin = selectedYearMin, yMax = selectedYearMax;
    const isAll = yMin <= year_min && yMax >= year_max;
    const yrLabel = fmtDateRange(isAll ? year_min : yMin, isAll ? year_max : yMax);
    const titleEl = document.getElementById('acc-tier-title');
    const subEl   = document.getElementById('acc-tier-sub');
    const capEl   = document.getElementById('acc-tier-caption');
    if (titleEl) titleEl.textContent = `${yrLabel} Flight Timeliness`;
    if (subEl)   subEl.textContent   = `${from} to ${to} · All carriers combined`;
    if (capEl) {
      const dp = Math.round(accuracy.dep.perfect), ds = Math.round(accuracy.dep.standard), dd = Math.round(accuracy.dep.disruptive);
      const ap = Math.round(accuracy.arr.perfect), as_ = Math.round(accuracy.arr.standard), ad = Math.round(accuracy.arr.disruptive);
      capEl.textContent =
        `${dp}% of departures leave on time or early, ${ds}% experience a minor delay under 15 minutes, and ${dd}% face a disruptive delay of 15 minutes or more. ` +
        `On the arrival end, ${ap}% land on time or early, while ${ad}% arrive significantly late.`;
    }
  }
}

// ── Polar chart ───────────────────────────────────────────────
function setPolarMode(mode) {
  polarDelayMode = mode;
  document.getElementById('ptog-dep').classList.toggle('active', mode === 'dep');
  document.getElementById('ptog-arr').classList.toggle('active', mode === 'arr');
  if (routeData?.heatmap) buildPolarChart(routeData.heatmap, routeData.arr_heatmap, routeData.monthly, routeData.arr_monthly);
}

function buildPolarChart(depHeatmap, arrHeatmap, depMonthly, arrMonthly) {
  const hasArr = !!(arrHeatmap && arrMonthly);
  const heatmap    = (polarDelayMode === 'arr' && hasArr) ? arrHeatmap : depHeatmap;
  const rawMonthly = (polarDelayMode === 'arr' && arrMonthly) ? arrMonthly : depMonthly || routeData?.monthly;
  currentHeatmap = heatmap;
  currentMonthly = rawMonthly;

  const arrBtn = document.getElementById('ptog-arr');
  if (arrBtn) {
    arrBtn.disabled = !hasArr;
    arrBtn.style.opacity = hasArr ? '' : '0.4';
    arrBtn.title = hasArr ? '' : 'Arrival data not available for this route yet';
  }

  const svg = document.getElementById('polar-svg');
  svg.innerHTML = '';

  const M_IN = 32, M_MAX = 112, D_OUT = 158, LR_IDLE = M_MAX + 22, LR_EXP = D_OUT + 24;
  const GAP = 1.0;

  const usingRoute = rawMonthly && rawMonthly.some(v => v !== null);
  const monthData  = usingRoute
    ? rawMonthly.map((v, i) => v !== null ? v : NAT_MONTHLY[i])
    : NAT_MONTHLY;

  const delayLabel = polarDelayMode === 'arr' ? 'Arrival' : 'Departure';

  const dowAvg = heatmap.map(row => {
    const v = row.filter(x => x !== null);
    return v.length ? v.reduce((a, b) => a + b, 0) / v.length : 0;
  });

  const validDow  = dowAvg.filter(v => v > 0);
  const dowMin    = validDow.length ? Math.min(...validDow) : 0;
  const dowMax    = validDow.length ? Math.max(...validDow) : 30;
  const dowRange  = dowMax - dowMin || 1;
  function dowRelColor(v) {
    const t = Math.max(0, Math.min(1, (v - dowMin) / dowRange));
    if (t <= 0.5) return lerpHex('#22C55E', '#EAB308', t * 2);
    return lerpHex('#EAB308', '#EF4444', (t - 0.5) * 2);
  }

  const ANGLES = Array.from({length: 12}, (_, i) => {
    const s = i * 30 + GAP/2, e = (i+1)*30 - GAP/2;
    return { s, e, mid: i*30+15, outerR: M_MAX };
  });

  // ── Side info panel ────────────────────────────────────────
  const infoPanel = document.getElementById('polar-info');
  const idleEl    = document.getElementById('polar-info-idle');

  function showMonthInfo(mIdx, locked = false) {
    const pct = monthData[mIdx];
    const routeAvg = monthData.filter(v => v != null).reduce((a, b) => a + b, 0) / monthData.filter(v => v != null).length;
    const diff = pct != null ? (pct - routeAvg).toFixed(1) : null;
    const diffText = diff != null
      ? (parseFloat(diff) >= 0 ? `+${diff}% vs route avg` : `${diff}% vs route avg`)
      : '';
    if (idleEl) idleEl.style.display = 'none';
    infoPanel.innerHTML =
      `<div style="font-size:10px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#64748B;margin-bottom:6px">${MONTH_LONG[mIdx]}${locked ? ' <span style="font-weight:400;text-transform:none;letter-spacing:0;color:#CBD5E1">· locked</span>' : ''}</div>` +
      `<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;padding:3px 0;border-bottom:1px solid #E2E8F0;margin-bottom:10px">` +
        `<span style="color:#64748B;font-size:11px">${delayLabel} delay</span>` +
        `<span style="display:inline-flex;align-items:center;gap:5px">` +
        `<span style="display:inline-block;width:7px;height:7px;border-radius:2px;background:${pct != null ? delayColor(pct) : '#CBD5E1'};flex-shrink:0"></span>` +
        `<span style="font-family:'DM Mono',monospace;font-weight:700;font-size:12px;color:#1E293B">${pct != null ? pct.toFixed(1)+'%' : '—'}</span></span></div>` +
      `<div style="font-size:11px;color:#64748B;margin-bottom:4px">${diffText}</div>` +
      `<div style="margin-top:12px;font-size:10px;color:#94A3B8;line-height:1.6">${locked ? 'Hover the day bars to see<br>time-of-day breakdown<br><br><span style="color:#CBD5E1">Click month to unlock</span>' : 'Click to lock · then hover<br>the day bars for details'}</div>`;
  }

  function showDayInfo(mIdx, dow, locked = false) {
    const monthlyHm = polarDelayMode === 'arr'
      ? (routeData.arr_monthly_heatmap || routeData.arr_heatmap)
      : (routeData.monthly_heatmap || routeData.heatmap);
    const tv = monthlyHm && monthlyHm[mIdx] ? monthlyHm[mIdx][dow] : heatmap[dow];
    infoPanel.innerHTML =
      `<div style="font-size:10px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#64748B;margin-bottom:6px">${MONTH_LONG[mIdx]} · ${DOW_NAMES[dow]}${locked ? ' <span style="font-weight:400;text-transform:none;letter-spacing:0;color:#CBD5E1">· locked</span>' : ''}</div>` +
      `<div style="margin-bottom:6px;font-size:10px;color:#94A3B8">${delayLabel} delay by time</div>` +
      TIME_NAMES.map((t, i) => {
        const v = tv[i]; const clr = v != null ? delayColor(v) : '#CBD5E1';
        return `<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;padding:2px 0">` +
          `<span style="color:#64748B;font-size:11px">${t}</span>` +
          `<span style="display:inline-flex;align-items:center;gap:5px">` +
          `<span style="display:inline-block;width:7px;height:7px;border-radius:2px;background:${clr};flex-shrink:0"></span>` +
          `<span style="font-family:'DM Mono',monospace;font-weight:600;font-size:11px;color:#1E293B">${v != null ? v.toFixed(1)+'%' : '—'}</span>` +
          `</span></div>`;
      }).join('') +
      `<div style="margin-top:8px;font-size:9px;color:#94A3B8;line-height:1.5">${locked ? 'Click day to unlock' : 'Click to lock this day open'}</div>`;
  }

  function clearInfo() {
    infoPanel.innerHTML = `<span style="color:var(--color-text-faint);font-size:11px;line-height:1.5">Hover a month to explore<br>Click to lock it open</span>`;
  }

  // ── SVG hit-test ───────────────────────────────────────────
  function svgPt(ev) {
    const r = svg.getBoundingClientRect(), vb = svg.viewBox.baseVal;
    return {
      x: (ev.clientX - r.left) / r.width  * vb.width  + vb.x,
      y: (ev.clientY - r.top)  / r.height * vb.height + vb.y,
    };
  }

  // ── State ──────────────────────────────────────────────────
  let expandedMonth = -1, hoveredDay = -1, lockedMonth = -1, lockedDay = -1;

  // ── Full redraw ────────────────────────────────────────────
  function render(expIdx, hDay) {
    svg.innerHTML = '';

    MONTHS.forEach((mon, i) => {
      const { s, e, mid, outerR } = ANGLES[i];
      const pct    = monthData[i];
      const midRad = pDeg(mid - 90);
      const isExp  = i === expIdx;
      const dimmed = expIdx >= 0 && !isExp;

      const wedge = svgNS('path');
      wedge.setAttribute('d', arcPath(s, e, M_IN, outerR));
      wedge.setAttribute('fill', delayColor(pct));
      wedge.setAttribute('stroke', i === lockedMonth ? '#0F172A' : '#F8FAFC');
      wedge.setAttribute('stroke-width', i === lockedMonth ? '2' : '1.5');
      wedge.setAttribute('opacity', dimmed ? '0.38' : '1');
      svg.appendChild(wedge);

      if (!dimmed) {
        const vr = M_IN + (outerR - M_IN) * 0.52;
        const val = svgNS('text');
        val.setAttribute('x', String(Math.cos(midRad) * vr)); val.setAttribute('y', String(Math.sin(midRad) * vr));
        val.setAttribute('text-anchor', 'middle'); val.setAttribute('dominant-baseline', 'middle');
        val.setAttribute('font-size', '10');
        val.setAttribute('font-weight', '700'); val.setAttribute('font-family', 'DM Mono,monospace');
        val.setAttribute('fill', pct > 26 ? '#fff' : '#1E293B');
        val.setAttribute('pointer-events', 'none'); val.textContent = pct.toFixed(1) + '%';
        svg.appendChild(val);
      }

      if (isExp) {
        const monthlyHm = polarDelayMode === 'arr'
          ? (routeData?.arr_monthly_heatmap || routeData?.arr_heatmap)
          : (routeData?.monthly_heatmap || routeData?.heatmap);
        const daySpan = (e - s) / 7;
        DOW_NAMES.forEach((dow, d) => {
          const ds = s + d * daySpan + 0.3, de = s + (d+1)*daySpan - 0.3;
          // Use month-specific day average when available
          const monthDaySlots = monthlyHm?.[i]?.[d];
          const v = monthDaySlots
            ? (() => { const vals = monthDaySlots.filter(x => x != null); return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : dowAvg[d]; })()
            : dowAvg[d];
          const iHov    = d === hDay;
          const iLocked = d === lockedDay;
          const iActive = iHov || iLocked;
          const seg = svgNS('path');
          seg.setAttribute('d', arcPath(ds, de, outerR + 2, iActive ? D_OUT + 6 : D_OUT));
          seg.setAttribute('fill', delayColor(v));
          seg.setAttribute('stroke', iLocked ? '#0F172A' : '#F8FAFC');
          seg.setAttribute('stroke-width', iActive ? '2' : '0.8');
          seg.setAttribute('opacity', (!iActive && lockedDay >= 0) ? '0.5' : '1');
          svg.appendChild(seg);

          // Label on hover or when locked
          if (iActive) {
            const midDeg = (ds + de) / 2;
            const midRd  = pDeg(midDeg - 90);
            const lblR   = D_OUT + 16;
            const lbl = svgNS('text');
            lbl.setAttribute('x', String(Math.cos(midRd) * lblR));
            lbl.setAttribute('y', String(Math.sin(midRd) * lblR));
            lbl.setAttribute('text-anchor', 'middle'); lbl.setAttribute('dominant-baseline', 'middle');
            lbl.setAttribute('font-size', '8.5'); lbl.setAttribute('font-weight', '700');
            lbl.setAttribute('font-family', 'Public Sans,sans-serif');
            lbl.setAttribute('fill', '#0F172A');
            lbl.setAttribute('pointer-events', 'none');
            lbl.textContent = dow;
            svg.appendChild(lbl);
          }
        });
      }

      // Month labels: all at LR_IDLE when unexpanded; expanded month at LR_EXP (outside day arcs)
      if (expIdx < 0) {
        const lbl = svgNS('text');
        lbl.setAttribute('x', String(Math.cos(midRad) * LR_IDLE));
        lbl.setAttribute('y', String(Math.sin(midRad) * LR_IDLE));
        lbl.setAttribute('text-anchor', 'middle'); lbl.setAttribute('dominant-baseline', 'middle');
        lbl.setAttribute('font-size', '9'); lbl.setAttribute('font-weight', '600');
        lbl.setAttribute('font-family', 'Public Sans,sans-serif');
        lbl.setAttribute('fill', '#64748B');
        lbl.setAttribute('letter-spacing', '0.04em'); lbl.setAttribute('pointer-events', 'none');
        lbl.textContent = mon;
        svg.appendChild(lbl);
      } else if (isExp && hDay < 0 && lockedDay < 0) {
        // Only show expanded month label when no day is active (avoids collision with day label)
        const lbl = svgNS('text');
        lbl.setAttribute('x', String(Math.cos(midRad) * LR_EXP));
        lbl.setAttribute('y', String(Math.sin(midRad) * LR_EXP));
        lbl.setAttribute('text-anchor', 'middle'); lbl.setAttribute('dominant-baseline', 'middle');
        lbl.setAttribute('font-size', '9.5'); lbl.setAttribute('font-weight', '700');
        lbl.setAttribute('font-family', 'Public Sans,sans-serif');
        lbl.setAttribute('fill', '#0F172A');
        lbl.setAttribute('letter-spacing', '0.04em'); lbl.setAttribute('pointer-events', 'none');
        lbl.textContent = mon;
        svg.appendChild(lbl);
      }
    });

    const hole = svgNS('circle');
    hole.setAttribute('r', String(M_IN - 1)); hole.setAttribute('fill', '#F8FAFC');
    hole.setAttribute('stroke', '#E2E8F0'); hole.setAttribute('stroke-width', '1');
    svg.appendChild(hole);

    if (expIdx < 0 && lockedMonth < 0) {
      const ct = svgNS('text');
      ct.setAttribute('text-anchor', 'middle'); ct.setAttribute('pointer-events', 'none');
      ct.setAttribute('font-family', 'Public Sans,sans-serif'); ct.setAttribute('fill', '#94A3B8');
      const s1 = svgNS('tspan'); s1.setAttribute('x','0'); s1.setAttribute('y','-3'); s1.setAttribute('font-size','6'); s1.textContent = 'hover';
      const s2 = svgNS('tspan'); s2.setAttribute('x','0'); s2.setAttribute('y', '7'); s2.setAttribute('font-size','6'); s2.textContent = 'month';
      ct.appendChild(s1); ct.appendChild(s2); svg.appendChild(ct);
    } else if (lockedMonth >= 0 && expIdx === lockedMonth) {
      const ct = svgNS('text');
      ct.setAttribute('text-anchor', 'middle'); ct.setAttribute('pointer-events', 'none');
      ct.setAttribute('font-family', 'Public Sans,sans-serif'); ct.setAttribute('fill', '#64748B');
      if (lockedDay >= 0) {
        const s1 = svgNS('tspan'); s1.setAttribute('x','0'); s1.setAttribute('y','-7'); s1.setAttribute('font-size','7'); s1.setAttribute('font-weight','700'); s1.textContent = DOW_NAMES[lockedDay];
        const s2 = svgNS('tspan'); s2.setAttribute('x','0'); s2.setAttribute('y', '3'); s2.setAttribute('font-size','6'); s2.textContent = MONTHS[lockedMonth];
        const s3 = svgNS('tspan'); s3.setAttribute('x','0'); s3.setAttribute('y','12'); s3.setAttribute('font-size','5'); s3.setAttribute('fill','#CBD5E1'); s3.textContent = 'locked';
        ct.appendChild(s1); ct.appendChild(s2); ct.appendChild(s3);
      } else {
        const s1 = svgNS('tspan'); s1.setAttribute('x','0'); s1.setAttribute('y','-3'); s1.setAttribute('font-size','7.5'); s1.setAttribute('font-weight','700'); s1.textContent = MONTHS[lockedMonth];
        const s2 = svgNS('tspan'); s2.setAttribute('x','0'); s2.setAttribute('y', '8'); s2.setAttribute('font-size','5.5'); s2.textContent = 'locked';
        ct.appendChild(s1); ct.appendChild(s2);
      }
      svg.appendChild(ct);
    }
  }

  // ── Mouse interaction ──────────────────────────────────────
  svg.addEventListener('mousemove', ev => {
    const { x, y } = svgPt(ev);
    const r = Math.sqrt(x * x + y * y);
    if (r < M_IN || r > D_OUT + 24) return;

    let deg = Math.atan2(y, x) * 180 / Math.PI + 90;
    if (deg < 0) deg += 360;

    const mIdx = ANGLES.findIndex(a => deg >= a.s && deg < a.e);
    if (mIdx < 0) return;

    if (lockedMonth >= 0) {
      if (mIdx !== lockedMonth) return;
      const { s, e, outerR } = ANGLES[mIdx];
      let newDay = -1;
      if (r > outerR && r <= D_OUT + 16) {
        const daySpan = (e - s) / 7;
        newDay = Math.min(6, Math.floor((deg - s) / daySpan));
      }
      if (newDay !== hoveredDay) {
        hoveredDay = newDay;
        const activeDay = hoveredDay >= 0 ? hoveredDay : lockedDay;
        render(lockedMonth, activeDay);
        if (hoveredDay >= 0) showDayInfo(lockedMonth, hoveredDay, hoveredDay === lockedDay);
        else if (lockedDay >= 0) showDayInfo(lockedMonth, lockedDay, true);
        else showMonthInfo(lockedMonth, true);
      }
      return;
    }

    const { s, e, outerR } = ANGLES[mIdx];
    let newExp = -1, newDay = -1;

    if (r >= M_IN && r <= outerR) {
      newExp = mIdx; newDay = -1;
    } else if (r > outerR && r <= D_OUT + 16) {
      if (mIdx === expandedMonth) {
        const daySpan = (e - s) / 7;
        newDay = Math.min(6, Math.floor((deg - s) / daySpan));
      }
      newExp = mIdx;
    }

    if (newExp !== expandedMonth || newDay !== hoveredDay) {
      expandedMonth = newExp; hoveredDay = newDay;
      render(expandedMonth, hoveredDay);
      if (hoveredDay >= 0) showDayInfo(expandedMonth, hoveredDay);
      else if (newExp >= 0) showMonthInfo(newExp);
    }
  });

  svg.addEventListener('click', ev => {
    const { x, y } = svgPt(ev);
    const r = Math.sqrt(x * x + y * y);
    let deg = Math.atan2(y, x) * 180 / Math.PI + 90;
    if (deg < 0) deg += 360;
    const mIdx = ANGLES.findIndex(a => deg >= a.s && deg < a.e);

    if (r >= M_IN && r <= M_MAX && mIdx >= 0) {
      // Click on inner month wedge
      if (lockedMonth === mIdx) {
        lockedMonth = -1; lockedDay = -1;
        render(mIdx, -1);
        showMonthInfo(mIdx, false);
      } else {
        lockedMonth = mIdx; lockedDay = -1;
        expandedMonth = mIdx; hoveredDay = -1;
        render(mIdx, -1);
        showMonthInfo(mIdx, true);
      }
    } else if (r > M_MAX && r <= D_OUT + 16 && lockedMonth >= 0 && mIdx === lockedMonth) {
      // Click on DOW arc while month is locked
      const { s, e } = ANGLES[lockedMonth];
      const daySpan = (e - s) / 7;
      const clickedDay = Math.min(6, Math.floor((deg - s) / daySpan));
      if (lockedDay === clickedDay) {
        lockedDay = -1;
        render(lockedMonth, hoveredDay >= 0 ? hoveredDay : -1);
        showMonthInfo(lockedMonth, true);
      } else {
        lockedDay = clickedDay;
        render(lockedMonth, lockedDay);
        showDayInfo(lockedMonth, lockedDay, true);
      }
    } else if (r < M_IN) {
      lockedMonth = -1; lockedDay = -1;
      expandedMonth = -1; hoveredDay = -1;
      render(-1, -1); clearInfo();
    }
  });

  svg.style.cursor = 'pointer';

  svg.addEventListener('mouseleave', () => {
    if (lockedDay >= 0) {
      hoveredDay = -1;
      render(lockedMonth, lockedDay);
      showDayInfo(lockedMonth, lockedDay, true);
      return;
    }
    if (lockedMonth >= 0) {
      hoveredDay = -1;
      render(lockedMonth, -1);
      showMonthInfo(lockedMonth, true);
      return;
    }
    if (expandedMonth >= 0 || hoveredDay >= 0) {
      expandedMonth = -1; hoveredDay = -1;
      render(-1, -1);
      clearInfo();
    }
  });

  render(-1, -1);
  clearInfo();

  const noteEl = document.getElementById('polar-data-note');
  if (noteEl) {
    const yMin = selectedYearMin, yMax = selectedYearMax;
    const isAll = !routeData?.route || (yMin <= routeData.route.year_min && yMax >= routeData.route.year_max);
    const yrLabel = isAll ? `${routeData?.route?.year_min ?? yMin}–${routeData?.route?.year_max ?? yMax}` : yMin === yMax ? String(yMin) : `${yMin}–${yMax}`;
    noteEl.textContent = usingRoute
      ? `${yrLabel} · ${delayLabel.toLowerCase()} delay · % of flights delayed ≥15 min`
      : `${delayLabel} delay · % of flights delayed ≥15 min · national averages`;
  }
}

// ── Carrier table ─────────────────────────────────────────────
function getCarriersForRange(yMin, yMax) {
  const rd = routeData;
  if (!rd) return rd?.carriers || [];
  const byCarrier = rd.annual?.by_carrier || {};
  const nameMap = Object.fromEntries((rd.carriers || []).map(c => [c.code, c.name]));
  const isAll = yMin <= rd.route.year_min && yMax >= rd.route.year_max;
  if (isAll) return rd.carriers;
  const results = [];
  for (const [code, entries] of Object.entries(byCarrier)) {
    const rows = entries.filter(e => e.year >= yMin && e.year <= yMax);
    if (!rows.length) continue;
    const totalF = rows.reduce((a, b) => a + (b.flights || 1), 0);
    const wDep = rows.reduce((a, b) => a + (b.dep_delay || 0) * (b.flights || 1), 0) / totalF;
    const wArr = rows.reduce((a, b) => a + (b.arr_delay || 0) * (b.flights || 1), 0) / totalF;
    results.push({ code, name: nameMap[code] || code, vol: totalF, dep_delay: +wDep.toFixed(1), arr_delay: +wArr.toFixed(1) });
  }
  return results.sort((a, b) => b.vol - a.vol);
}

function buildCarrierTable(carriers) {
  const tbody = document.getElementById('carrier-tbody');
  tbody.innerHTML = '';
  carriers.forEach((c, i) => {
    const dep = fmtDelay(c.dep_delay);
    const arr = fmtDelay(c.arr_delay);

    const tr  = document.createElement('tr');

    const tdName = document.createElement('td');
    const btn = document.createElement('button');
    btn.className = 'carrier-link';
    btn.id = `cl-${i}`;
    btn.textContent = c.name;
    btn.addEventListener('click', () => selectCarrier(i));
    tdName.appendChild(btn);

    const tdVol = document.createElement('td');
    tdVol.textContent = c.vol.toLocaleString();

    const tdDep = document.createElement('td');
    tdDep.style.color = '#64748B';
    const spanDep = document.createElement('span');
    spanDep.className = dep.cls;
    spanDep.textContent = dep.text;
    tdDep.appendChild(spanDep);

    const tdArr = document.createElement('td');
    const spanArr = document.createElement('span');
    spanArr.className = arr.cls;
    spanArr.textContent = arr.text;
    tdArr.appendChild(spanArr);

    tr.appendChild(tdName);
    tr.appendChild(tdVol);
    tr.appendChild(tdDep);
    tr.appendChild(tdArr);
    tbody.appendChild(tr);
  });
}

function selectCarrier(i) {
  if (selectedCarrier === i) {
    selectedCarrier = null;
    document.querySelectorAll('.carrier-link').forEach(l => l.classList.remove('active-carrier'));
    document.getElementById('tier5-hint').textContent = 'Click a carrier in the leaderboard above to overlay their specific performance track.';
    drawMacroChart(null);
    renderRibbon(routeData.carriers, null);
    return;
  }
  selectedCarrier = i;
  document.querySelectorAll('.carrier-link').forEach(l => l.classList.remove('active-carrier'));
  document.getElementById(`cl-${i}`).classList.add('active-carrier');
  document.getElementById('tier5-hint').textContent = `Showing ${routeData.carriers[i].name} vs. route baseline.`;
  drawMacroChart(i);
  renderRibbon(routeData.carriers, i);
}

// ── Macro chart ───────────────────────────────────────────────
function setMacroMode(mode) {
  macroDelayMode = mode;
  document.getElementById('mtog-arr').classList.toggle('active', mode === 'arr');
  document.getElementById('mtog-dep').classList.toggle('active', mode === 'dep');
  if (routeData?.route) {
    const label = mode === 'dep' ? 'departure' : 'arrival';
    document.getElementById('tier5-sub').textContent = `Average ${label} delay · ${routeData.route.from} to ${routeData.route.to}`;
  }
  drawMacroChart(selectedCarrier);
}

function drawMacroChart(cIdx, annualOverride) {
  const annual = annualOverride ?? routeData?.annual;
  const svg = document.getElementById('macro-svg');
  if (!annual) return;
  const baseline = annual.baseline;
  if (!baseline || baseline.length < 2) {
    svg.innerHTML = '<text x="50%" y="50%" text-anchor="middle" dominant-baseline="middle" ' +
      'font-size="13" fill="var(--color-text-faint)" font-family="\'Public Sans\',sans-serif">' +
      'Not enough data to render this chart.</text>';
    return;
  }

  const isArr  = macroDelayMode !== 'dep';
  const valKey = isArr ? 'arr_delay' : 'dep_delay';
  const W = Math.max(320, svg.parentElement.clientWidth || 900);
  const H = Math.round(W * 0.265);
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const pL=46, pR=Math.round(W*0.13), pT=20, pB=44;
  const w=W-pL-pR, h=H-pT-pB;
  const n = baseline.length;
  const YEARS = baseline.map(d => d.year);
  const allVals = baseline.map(d => d[valKey] ?? 0);
  const carriers = annualOverride ? [] : routeData?.carriers;
  if (cIdx !== null && annual.by_carrier && carriers?.[cIdx]) {
    const code = carriers[cIdx].code;
    if (code && annual.by_carrier[code]) {
      allVals.push(...annual.by_carrier[code].map(d => d[valKey] ?? d.arr_delay ?? 0));
    }
  }

  const rawMin = Math.min(...allVals);
  const rawMax = Math.max(...allVals);
  const step   = rawMax <= 20 ? 5 : 10;
  const minV   = Math.min(0, Math.floor(rawMin / step) * step);
  const maxV   = Math.max(step * 2, Math.ceil(rawMax / step) * step);
  const yRange = maxV - minV;
  const x = i => pL + (i/(n-1))*w;
  const y = v => pT + h - ((v - minV) / yRange) * h;

  let out = `<defs>
    <linearGradient id="mg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#E2E8F0" stop-opacity="0.5"/>
      <stop offset="100%" stop-color="#E2E8F0" stop-opacity="0"/>
    </linearGradient></defs>`;

  if (selectedYearMin !== YR_MIN || selectedYearMax !== YR_MAX) {
    const yi1 = YEARS.indexOf(selectedYearMin), yi2 = YEARS.indexOf(selectedYearMax);
    const bw = w/(n-1);
    const x1 = yi1 >= 0 ? x(yi1) - bw/2 : pL;
    const x2 = yi2 >= 0 ? x(yi2) + bw/2 : pL + w;
    out += `<rect x="${x1}" y="${pT}" width="${x2-x1}" height="${h}" fill="#FEF3C7" opacity="0.7" rx="2"/>`;
  }

  if (minV < 0) {
    out += `<line x1="${pL}" y1="${y(0)}" x2="${pL+w}" y2="${y(0)}" stroke="#94A3B8" stroke-width="1" stroke-dasharray="3,2"/>`;
    out += `<text x="${pL-6}" y="${y(0)+4}" font-family="DM Mono,monospace" font-size="10" fill="#64748B" text-anchor="end" font-weight="600">0</text>`;
  }

  const nTicks = Math.ceil(yRange / step);
  for (let i = 0; i <= nTicks; i++) {
    const v = minV + i * step;
    if (v > maxV) break;
    if (v === 0 && minV < 0) continue;
    out += `<line x1="${pL}" y1="${y(v)}" x2="${pL+w}" y2="${y(v)}" stroke="#E2E8F0" stroke-width="1"/>`;
    out += `<text x="${pL-6}" y="${y(v)+4}" font-family="DM Mono,monospace" font-size="10" fill="#94A3B8" text-anchor="end">${v >= 0 ? '+' + v : v}m</text>`;
  }
  YEARS.forEach((yr, i) => {
    out += `<text x="${x(i)}" y="${H-8}" font-family="DM Mono,monospace" font-size="10" fill="#94A3B8" text-anchor="middle">${yr}</text>`;
  });

  const BVALS = baseline.map(d => d[valKey] ?? 0);
  const y0 = y(Math.max(0, minV));
  const ga = `M${x(0)},${y0} ` + BVALS.map((v, i) => `L${x(i)},${y(v)}`).join(' ') + ` L${x(n-1)},${y0} Z`;
  out += `<path d="${ga}" fill="url(#mg)"/>`;
  out += `<path d="${BVALS.map((v, i) => `${i===0?'M':'L'}${x(i)},${y(v)}`).join(' ')}" fill="none" stroke="#CBD5E1" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
  BVALS.forEach((v, i) => { out += `<circle cx="${x(i)}" cy="${y(v)}" r="3" fill="#E2E8F0" stroke="#94A3B8" stroke-width="1.5"/>`; });
  out += `<text x="${x(n-1)+6}" y="${y(BVALS[n-1])+4}" font-family="DM Mono,monospace" font-size="9" fill="#94A3B8">All carriers</text>`;

  if (cIdx !== null && carriers?.[cIdx]) {
    const code  = carriers[cIdx].code;
    const name  = carriers[cIdx].name;
    const cdata = (annual.by_carrier?.[code] || []).filter(d => YEARS.includes(d.year));
    if (cdata.length >= 1) {
      const cvals = cdata.map(d => d[valKey] ?? d.arr_delay ?? 0);
      if (cdata.length >= 2) {
        const pts = cdata.map((d, ci) => {
          const i = YEARS.indexOf(d.year);
          return i >= 0 ? `${ci===0?'M':'L'}${x(i)},${y(cvals[ci])}` : null;
        }).filter(Boolean);
        out += `<path d="${pts.join(' ')}" fill="none" stroke="#F59E0B" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>`;
      }
      cdata.forEach((d, ci) => {
        const i = YEARS.indexOf(d.year);
        if (i >= 0) out += `<circle cx="${x(i)}" cy="${y(cvals[ci])}" r="4" fill="#FFFFFF" stroke="#F59E0B" stroke-width="2"/>`;
      });
      const lastD = cdata[cdata.length - 1];
      const li = YEARS.indexOf(lastD.year);
      const labelNote = cdata.length === 1 ? ` (${lastD.year} only)` : '';
      if (li >= 0) out += `<text x="${x(li)+6}" y="${y(cvals[cdata.length-1])+4}" font-family="DM Mono,monospace" font-size="9" fill="#D97706" font-weight="500">${name.split(' ')[0]}${labelNote}</text>`;
    }
  }

  svg.innerHTML = out;
}

// ── Ribbon (delay anatomy) ────────────────────────────────────
function renderRibbon(carriers, selIdx) {
  const wrap = document.getElementById('ribbon-wrap');
  if (!wrap) return;
  if (!carriers || carriers.length === 0) { wrap.innerHTML = ''; return; }

  const CAUSE_DEFS = [
    { key: 'late_aircraft', label: 'Late aircraft',  note: 'Plane arrived late from a previous flight' },
    { key: 'carrier',       label: 'Carrier',         note: 'Airline operations: crew, maintenance, fueling' },
    { key: 'nas',           label: 'NAS / ATC',       note: 'Air traffic control, airport congestion' },
    { key: 'weather',       label: 'Weather',          note: 'Severe weather events' },
  ];

  const routeAvg = key => {
    const vals = carriers.map(c => c.causes?.[key] || 0).filter(v => v > 0);
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0;
  };
  const rTotal = CAUSE_DEFS.reduce((s, c) => s + routeAvg(c.key), 0) || 1;
  const rPct   = key => Math.round(routeAvg(key) / rTotal * 100);

  const sel = selIdx != null ? carriers[selIdx] : null;
  const selTotal = sel ? Object.values(sel.causes || {}).reduce((a, b) => a + b, 0) || 1 : 1;
  const sPct = key => sel ? Math.round((sel.causes?.[key] || 0) / selTotal * 100) : null;

  const causes = CAUSE_DEFS
    .map(c => ({ ...c, route: rPct(c.key), sel: sPct(c.key) }))
    .sort((a, b) => b.route - a.route);

  const selName = sel ? carriers[selIdx].name.split(' ')[0] : null;

  wrap.innerHTML =
    `<div style="display:flex;flex-direction:column;gap:14px">` +
    causes.map(c => {
      if (sel) {
        return `<div>
          <div style="display:flex;align-items:center;gap:6px;margin-bottom:5px">
            <span style="font-size:11px;font-weight:600;color:var(--color-text-main)">${c.label}</span>
            <span style="font-size:10px;color:var(--color-text-faint)">${c.note}</span>
          </div>
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
            <span style="font-size:10px;width:68px;flex-shrink:0;color:var(--color-text-muted);font-weight:600">${selName}</span>
            <div style="flex:1;height:7px;background:#F1F5F9;border-radius:2px;overflow:hidden">
              <div style="height:100%;width:${c.sel}%;background:var(--color-accent);border-radius:2px"></div>
            </div>
            <span style="font-size:11px;font-family:'DM Mono',monospace;font-weight:700;color:var(--color-text-main);width:32px;text-align:right">${c.sel}%</span>
          </div>
          <div style="display:flex;align-items:center;gap:8px">
            <span style="font-size:10px;width:68px;flex-shrink:0;color:var(--color-text-faint)">Route avg</span>
            <div style="flex:1;height:7px;background:#F1F5F9;border-radius:2px;overflow:hidden">
              <div style="height:100%;width:${c.route}%;background:#CBD5E1;border-radius:2px"></div>
            </div>
            <span style="font-size:11px;font-family:'DM Mono',monospace;color:var(--color-text-faint);width:32px;text-align:right">${c.route}%</span>
          </div>
        </div>`;
      } else {
        return `<div style="display:flex;align-items:center;gap:10px">
          <span style="font-size:11px;font-weight:600;color:var(--color-text-main);width:110px;flex-shrink:0">${c.label}</span>
          <div style="flex:1;height:7px;background:#F1F5F9;border-radius:2px;overflow:hidden">
            <div style="height:100%;width:${c.route}%;background:#94A3B8;border-radius:2px"></div>
          </div>
          <span style="font-size:12px;font-family:'DM Mono',monospace;font-weight:600;color:var(--color-text-main);width:32px;text-align:right">${c.route}%</span>
          <span style="font-size:10px;color:var(--color-text-faint);min-width:140px">${c.note}</span>
        </div>`;
      }
    }).join('') +
    `</div><div style="margin-top:12px;font-size:10px;color:var(--color-text-faint)">Share of total delay minutes attributed to each cause${sel ? ` · comparing ${selName} vs route average` : ' · averaged across all carriers'}</div>`;
}

// ── Master render ─────────────────────────────────────────────
function renderAll() {
  if (!routeData) return;

  const total = routeData.route?.total_flights ?? Infinity;
  const isLowVolume = total < 1000;

  const banner = document.getElementById('low-volume-banner');
  if (banner) banner.style.display = isLowVolume ? 'flex' : 'none';

  const dataSections = ['route-kpi', 'section-timeliness', 'section-polar', 'carrier-card', 'section-macro'];
  dataSections.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = isLowVolume ? 'none' : '';
  });

  if (isLowVolume) return;

  buildPolarChart(routeData.heatmap, routeData.arr_heatmap, routeData.monthly, routeData.arr_monthly);
  buildCarrierTable(routeData.carriers);
  selectedCarrier = null;
  document.getElementById('tier5-hint').textContent =
    'Click a carrier in the leaderboard above to overlay their specific performance track.';
  if (routeData.route) {
    const mode = macroDelayMode === 'dep' ? 'departure' : 'arrival';
    document.getElementById('tier5-sub').textContent = `Average ${mode} delay · ${routeData.route.from} to ${routeData.route.to}`;
  }
  drawMacroChart(null);
  renderRibbon(routeData.carriers, null);
  applyYearFilter(); // handles renderRouteKpi + renderDivergingBar
}


// ── Blank / route state ───────────────────────────────────────
function showNotFoundState(from, to) {
  const bp = document.getElementById('blank-prompt');
  bp.innerHTML = `
    <div style="font-size:36px;margin-bottom:14px;opacity:0.25">✈</div>
    <div style="font-size:16px;font-weight:600;color:var(--color-text-main);margin-bottom:6px">Route not found in dataset</div>
    <div style="font-size:13px;margin-top:4px">${from} → ${to} has no recorded flights. Try searching another route.</div>
  `;
  bp.style.display = '';
  document.getElementById('route-title').style.display = 'none';
  document.getElementById('route-scope').style.display = 'none';
  document.getElementById('route-legal').style.display = 'none';
  document.getElementById('route-kpi').style.display = 'none';
  document.getElementById('year-controller').style.display = 'none';
  document.querySelectorAll('section.section').forEach(el => el.style.display = 'none');
}

function showBlankState() {
  document.getElementById('blank-prompt').style.display = '';
  document.getElementById('route-title').style.display = 'none';
  document.getElementById('route-scope').style.display = 'none';
  document.getElementById('route-legal').style.display = 'none';
  document.getElementById('route-kpi').style.display = 'none';
  document.getElementById('year-controller').style.display = 'none';
  document.querySelectorAll('section.section').forEach(el => el.style.display = 'none');
}

function showRouteState() {
  document.getElementById('blank-prompt').style.display = 'none';
  document.getElementById('route-scope').style.display = '';
  document.getElementById('route-legal').style.display = '';
  document.getElementById('route-kpi').style.display = '';
  document.getElementById('year-controller').style.display = '';
  document.querySelectorAll('section.section').forEach(el => el.style.display = '');
}

// ── KPI cell scroll anchors ───────────────────────────────────
document.getElementById('kpi-cell-days').addEventListener('click', () =>
  document.getElementById('polar-main').scrollIntoView({ behavior: 'smooth', block: 'center' }));
document.getElementById('kpi-cell-carrier').addEventListener('click', () =>
  document.getElementById('carrier-card').scrollIntoView({ behavior: 'smooth', block: 'start' }));
['kpi-cell-depdelay', 'kpi-cell-arrdelay'].forEach(id =>
  document.getElementById(id)?.addEventListener('click', () =>
    document.getElementById('macro-svg').scrollIntoView({ behavior: 'smooth', block: 'center' })));

// ── Boot ──────────────────────────────────────────────────────
if (routeFrom.length === 3 && routeTo.length === 3) {
  applyRouteHeader(routeFrom, routeTo);
  showRouteState();
  loadRouteData(routeFrom, routeTo);
} else {
  showBlankState();
}

const macroObs = new ResizeObserver(() => drawMacroChart(selectedCarrier));
macroObs.observe(document.getElementById('macro-svg').parentElement);
