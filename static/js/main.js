/* ── Utility ──────────────────────────────────────────────────── */

function scoreClass(s) {
  if (s === null || s === undefined) return 'score-null';
  if (s >= 7) return 'score-green';
  if (s >= 5) return 'score-amber';
  return 'score-red';
}

function fmt(v) {
  if (v === null || v === undefined) return '—';
  return typeof v === 'number' ? v.toFixed(v % 1 === 0 ? 0 : 1) : v;
}

function show(id) {
  document.querySelectorAll('.screen').forEach(el => {
    el.classList.remove('active');
    el.style.display = 'none';
  });
  const el = document.getElementById(id);
  el.style.display = 'flex';
  el.classList.add('active');
}

/* ── Search ───────────────────────────────────────────────────── */

const input = document.getElementById('search-input');
const searchBtn = document.getElementById('search-btn');
const suggestions = document.getElementById('suggestions');
const hint = document.getElementById('search-hint');
let debounceTimer;
let currentMatches = [];   // holds latest typeahead results
let selectedIdx = -1;      // keyboard-highlighted row index

input.addEventListener('input', () => {
  clearTimeout(debounceTimer);
  const q = input.value.trim();
  hint.classList.add('hidden');
  if (q.length < 2) {
    hideSuggestions();
    setButtonReady(false);
    return;
  }
  debounceTimer = setTimeout(() => fetchSuggestions(q), 280);
});

input.addEventListener('keydown', e => {
  if (e.key === 'Escape') { hideSuggestions(); return; }

  if (e.key === 'ArrowDown') {
    e.preventDefault();
    moveSel(1); return;
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault();
    moveSel(-1); return;
  }

  if (e.key === 'Enter') {
    e.preventDefault();
    submitSelected();
  }
});

searchBtn.addEventListener('click', () => submitSelected());

document.addEventListener('click', e => {
  if (!e.target.closest('.search-box')) hideSuggestions();
});

function hideSuggestions() {
  suggestions.classList.add('hidden');
  suggestions.innerHTML = '';
  selectedIdx = -1;
}

function setButtonReady(ready) {
  searchBtn.disabled = !ready;
}

function moveSel(dir) {
  if (!currentMatches.length) return;
  selectedIdx = Math.max(0, Math.min(currentMatches.length - 1, selectedIdx + dir));
  highlightSel();
}

function highlightSel() {
  suggestions.querySelectorAll('.suggestion-item').forEach((el, i) => {
    el.classList.toggle('selected', i === selectedIdx);
  });
}

async function fetchSuggestions(q) {
  try {
    const res = await fetch(`/search?q=${encodeURIComponent(q)}`);
    const data = await res.json();
    currentMatches = data;
    renderSuggestions(data);
  } catch (e) {
    currentMatches = [];
    hideSuggestions();
    setButtonReady(false);
  }
}

function renderSuggestions(items) {
  if (!items.length) {
    hideSuggestions();
    hint.classList.remove('hidden');
    setButtonReady(false);
    return;
  }
  hint.classList.add('hidden');
  selectedIdx = 0;  // auto-highlight first result
  suggestions.innerHTML = items.map((c, i) => `
    <div class="suggestion-item${i === 0 ? ' selected' : ''}"
         data-ticker="${c.ticker}" data-slug="${c.slug}" data-name="${c.name}">
      <span class="suggestion-ticker">${c.ticker}</span>
      <span class="suggestion-name">${c.name}</span>
    </div>
  `).join('');
  suggestions.classList.remove('hidden');
  setButtonReady(true);

  suggestions.querySelectorAll('.suggestion-item').forEach((el, i) => {
    el.addEventListener('mouseenter', () => { selectedIdx = i; highlightSel(); });
    el.addEventListener('click', () => {
      const { ticker, slug, name } = el.dataset;
      pickCompany(ticker, slug, name);
    });
  });
}

function submitSelected() {
  if (!currentMatches.length) return;
  const idx = selectedIdx >= 0 ? selectedIdx : 0;
  const c = currentMatches[idx];
  if (!c) return;
  pickCompany(c.ticker, c.slug, c.name);
}

function pickCompany(ticker, slug, name) {
  hideSuggestions();
  input.value = name;
  setButtonReady(false);
  startAnalysis(ticker, slug, name);
}

/* ── Analysis ─────────────────────────────────────────────────── */

async function startAnalysis(ticker, slug, name) {
  show('loading-screen');
  document.getElementById('loading-msg').textContent = `Fetching data for ${name}…`;

  try {
    const res = await fetch('/analyse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticker, slug, name }),
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    renderResults(data);
    show('results-screen');
  } catch (e) {
    alert(`Error: ${e.message}`);
    show('search-screen');
    setButtonReady(currentMatches.length > 0);
  }
}

document.getElementById('back-btn').addEventListener('click', () => {
  show('search-screen');
  // don't reset input or matches — let user re-submit or refine
  setButtonReady(currentMatches.length > 0);
});

/* ── Render Results ───────────────────────────────────────────── */

function renderResults(data) {
  const { company, overall, hard_stops, pillars, years } = data;

  // Requirement 4: warn for any null pillar score before rendering.
  if (!data.unsupported_sector && pillars) {
    const label = (company && (company.name || company.ticker)) || '?';
    ['Financial Risk','Cash Generation','Business Quality','Growth Quality','Capital Efficiency']
      .forEach(p => {
        const s = pillars[p] && pillars[p].score;
        if (s == null) console.warn(`[EquityEngine] ${label}: pillar "${p}" score is null/missing`);
      });
    if (!overall || overall.score == null) {
      console.warn(`[EquityEngine] ${label}: overall score is null/missing`);
    }
  }

  // Company label
  document.getElementById('company-label').textContent =
    `${company.name} (${company.ticker})`;

  const overallCard = document.getElementById('overall-card');
  const stopsBanner = document.getElementById('hard-stops-banner');
  const grid = document.getElementById('pillars-grid');
  const sectorNotice = document.getElementById('sector-notice');

  // Unsupported sector — show notice, hide scoring sections
  if (data.unsupported_sector) {
    sectorNotice.classList.remove('hidden');
    document.getElementById('sector-notice-msg').textContent = data.sector_message || '';
    overallCard.classList.add('hidden');
    stopsBanner.classList.add('hidden');
    grid.innerHTML = '';
    return;
  }

  // Normal results — ensure scoring sections are visible
  sectorNotice.classList.add('hidden');
  overallCard.classList.remove('hidden');

  // Hard stops
  if (hard_stops && hard_stops.length) {
    stopsBanner.classList.remove('hidden');
    stopsBanner.innerHTML = `<h4>⚠ Hard Stop Rules Triggered</h4><ul>${hard_stops.map(s => `<li>${s}</li>`).join('')}</ul>`;
  } else {
    stopsBanner.classList.add('hidden');
  }

  // Overall score ring
  const score = overall.score;
  const pct = score ? (score / 10) : 0;
  const circumference = 327;
  const offset = circumference - pct * circumference;
  document.getElementById('overall-score-num').textContent = score !== null ? score.toFixed(2) : '—';
  const ring = document.getElementById('ring-fill');
  ring.style.stroke = score >= 7 ? 'var(--green)' : score >= 5 ? 'var(--amber)' : 'var(--red)';
  setTimeout(() => { ring.style.strokeDashoffset = offset; }, 100);

  // Recommendation
  const rec = overall.recommendation || '—';
  const badge = document.getElementById('recommendation-badge');
  badge.textContent = rec;
  badge.className = `rec-badge rec-${rec.replace(' ', '-')}`;

  // Years
  if (years && years.length) {
    document.getElementById('years-label').textContent =
      `Data years: ${[...years].reverse().join(', ')}`;
  }

  // Caps & penalties
  const cpEl = document.getElementById('caps-penalties');
  const cpItems = [
    ...(overall.caps || []).map(c => `<span class="cap-tag">↓ ${c}</span>`),
    ...(overall.penalties || []).map(p => `<span class="pen-tag">− ${p}</span>`),
  ];
  cpEl.innerHTML = cpItems.join('');

  // Pillar cards
  grid.innerHTML = '';
  const pillarOrder = ['Financial Risk','Cash Generation','Business Quality','Growth Quality','Capital Efficiency'];
  pillarOrder.forEach(name => {
    const pillar = pillars[name];
    if (!pillar) return;
    grid.appendChild(buildPillarCard(name, pillar));
  });
}

function buildPillarCard(pillarName, pillar) {
  const card = document.createElement('div');
  card.className = 'pillar-card';

  const s = pillar.score;
  const sc = scoreClass(s);

  // Penalties/caps for this pillar
  const penaltyLines = [
    ...(pillar.penalties || []),
    ...(pillar.caps || []),
  ];

  card.innerHTML = `
    <div class="pillar-header">
      <div class="pillar-header-left">
        <div class="pillar-score-badge ${sc}">${s !== null && s !== undefined ? s.toFixed(1) : '—'}</div>
        <div>
          <div class="pillar-name">${pillarName}</div>
          <div class="pillar-weight">${pillar.pillar_weight || ''}</div>
        </div>
      </div>
      <span class="pillar-chevron">▼</span>
    </div>

    <div class="pillar-body">
      ${pillar.error ? `<div class="pillar-error">⚠ ${pillar.error}</div>` : ''}
      ${buildComponents(pillar.components || {})}
      ${penaltyLines.length ? `<div class="pillar-penalties">${penaltyLines.map(p => `<span>− ${p}</span>`).join('')}</div>` : ''}
    </div>
  `;

  card.querySelector('.pillar-header').addEventListener('click', () => {
    card.classList.toggle('open');
  });

  return card;
}

function buildComponents(components) {
  return Object.entries(components).map(([name, comp]) => {
    const cs = comp.score;
    const cc = scoreClass(cs);
    const subs = comp.subs || {};

    return `
      <div class="component-section">
        <div class="component-header">
          <span class="component-name">${name}</span>
          <div class="component-score-weight">
            <div class="component-score ${cc}">${cs !== null && cs !== undefined ? cs.toFixed(1) : '—'}</div>
            <span class="component-weight">${comp.weight || ''}</span>
          </div>
        </div>
        ${comp.error ? `<div class="component-error">⚠ Calculation incomplete: ${comp.error}</div>` : ''}
        ${Object.entries(subs).map(([sname, sub]) => buildSubRow(sname, sub)).join('')}
      </div>
    `;
  }).join('');
}

function buildSubRow(name, sub) {
  const ss = sub.score;
  const sc = scoreClass(ss);
  const rawStr = sub.raw !== null && sub.raw !== undefined ? String(sub.raw) : '—';

  return `
    <div class="sub-row">
      <div class="sub-left">
        <div class="sub-name">${name}</div>
        <div class="sub-desc">${sub.desc || ''}</div>
      </div>
      <div class="sub-right">
        <span class="sub-raw">${rawStr}</span>
        <div class="sub-score-dot ${sc}">${ss !== null && ss !== undefined ? ss : '—'}</div>
      </div>
    </div>
  `;
}

/* ═══════════════════════════════════════════════════════
   COMPARE MODE
   ═══════════════════════════════════════════════════════ */

// ── State ────────────────────────────────────────────────
const MAX_SLOTS = 4;
const MIN_SLOTS = 2;
let compareSlots = [];
let compareResults = [];
let activeSig = 'ALL';

// ── Mode toggle ──────────────────────────────────────────
document.getElementById('mode-single').addEventListener('click', () => setMode('single'));
document.getElementById('mode-compare').addEventListener('click', () => setMode('compare'));

function setMode(m) {
  const isCmp = m === 'compare';
  document.getElementById('mode-single').classList.toggle('active', !isCmp);
  document.getElementById('mode-compare').classList.toggle('active', isCmp);
  document.getElementById('single-search').classList.toggle('hidden', isCmp);
  document.getElementById('compare-section').classList.toggle('hidden', !isCmp);
  if (isCmp) {
    if (compareSlots.length === 0) {
      addCompareSlot();
      addCompareSlot();
    } else {
      // Re-entering compare mode: re-sync visual state of existing slots
      refreshSlotsUI();
    }
  }
}

function refreshSlotsUI() {
  compareSlots.forEach(slot => {
    if (slot.match) {
      slot.input.value = `${slot.match.name} (${slot.match.ticker})`;
      slot.wrapper.classList.add('slot-selected');
    }
    // Don't clear unmatched slots — user may have partially typed something
  });
  updateSlotUI();
}

// ── Slot management ──────────────────────────────────────
function addCompareSlot() {
  if (compareSlots.length >= MAX_SLOTS) return;

  const idx = compareSlots.length;
  const wrapper = document.createElement('div');
  wrapper.className = 'compare-slot';

  const inputRow = document.createElement('div');
  inputRow.className = 'slot-input-row';

  const inp = document.createElement('input');
  inp.type = 'text';
  inp.className = 'slot-input';
  inp.placeholder = `Company ${idx + 1}…`;
  inp.autocomplete = 'off';

  const rmBtn = document.createElement('button');
  rmBtn.className = 'slot-rm-btn';
  rmBtn.textContent = '✕';

  const dd = document.createElement('div');
  dd.className = 'slot-dropdown suggestions hidden';

  inputRow.appendChild(inp);
  inputRow.appendChild(rmBtn);
  wrapper.appendChild(inputRow);
  wrapper.appendChild(dd);

  const slot = {
    idx, wrapper, input: inp, dropdown: dd,
    matches: [], selIdx: -1, match: null, debounce: null,
  };
  compareSlots.push(slot);
  document.getElementById('compare-slots').appendChild(wrapper);
  bindSlotEvents(slot);
  updateSlotUI();
}

function removeSlot(slot) {
  if (compareSlots.length <= MIN_SLOTS) {
    slot.input.value = '';
    slot.match = null;
    slot.wrapper.classList.remove('slot-selected');
    hideSlotDD(slot);
    updateCompareBtn();
    return;
  }
  slot.wrapper.remove();
  compareSlots.splice(compareSlots.indexOf(slot), 1);
  updateSlotUI();
}

function updateSlotUI() {
  compareSlots.forEach((s, i) => {
    s.idx = i;
    if (!s.match) s.input.placeholder = `Company ${i + 1}…`;
  });
  document.getElementById('compare-add-btn').classList.toggle('hidden', compareSlots.length >= MAX_SLOTS);
  updateCompareBtn();
}

function updateCompareBtn() {
  const ready = compareSlots.filter(s => s.match).length >= MIN_SLOTS;
  document.getElementById('compare-btn').disabled = !ready;
}

// ── Slot events ──────────────────────────────────────────
function bindSlotEvents(slot) {
  const { input, dropdown } = slot;

  input.addEventListener('input', () => {
    clearTimeout(slot.debounce);
    slot.match = null;
    slot.wrapper.classList.remove('slot-selected');
    updateCompareBtn();
    const q = input.value.trim();
    if (q.length < 2) { hideSlotDD(slot); return; }
    slot.debounce = setTimeout(() => fetchSlotSuggestions(slot, q), 280);
  });

  input.addEventListener('keydown', e => {
    if (e.key === 'Escape') { hideSlotDD(slot); return; }
    if (e.key === 'ArrowDown') { e.preventDefault(); moveSlotSel(slot, 1); return; }
    if (e.key === 'ArrowUp')   { e.preventDefault(); moveSlotSel(slot, -1); return; }
    if (e.key === 'Enter')     { e.preventDefault(); confirmSlotSel(slot); }
  });

  slot.wrapper.querySelector('.slot-rm-btn').addEventListener('click', () => removeSlot(slot));
}

async function fetchSlotSuggestions(slot, q) {
  try {
    const res = await fetch(`/search?q=${encodeURIComponent(q)}`);
    const items = await res.json();
    slot.matches = items;
    if (!items.length) { hideSlotDD(slot); return; }
    renderSlotDD(slot, items);
  } catch { hideSlotDD(slot); }
}

function renderSlotDD(slot, items) {
  slot.selIdx = 0;
  slot.dropdown.innerHTML = items.slice(0, 8).map((c, i) => `
    <div class="suggestion-item${i === 0 ? ' selected' : ''}" data-i="${i}">
      <span class="suggestion-ticker">${c.ticker}</span>
      <span class="suggestion-name">${c.name}</span>
    </div>
  `).join('');
  slot.dropdown.classList.remove('hidden');
  slot.dropdown.querySelectorAll('.suggestion-item').forEach(el => {
    el.addEventListener('mouseenter', () => { slot.selIdx = +el.dataset.i; highlightSlotDD(slot); });
    el.addEventListener('click', () => pickSlotCompany(slot, slot.matches[+el.dataset.i]));
  });
}

function moveSlotSel(slot, dir) {
  if (!slot.matches.length) return;
  slot.selIdx = Math.max(0, Math.min(slot.matches.length - 1, slot.selIdx + dir));
  highlightSlotDD(slot);
}

function highlightSlotDD(slot) {
  slot.dropdown.querySelectorAll('.suggestion-item').forEach((el, i) => {
    el.classList.toggle('selected', i === slot.selIdx);
  });
}

function confirmSlotSel(slot) {
  if (!slot.matches.length) return;
  const c = slot.matches[slot.selIdx >= 0 ? slot.selIdx : 0];
  if (c) pickSlotCompany(slot, c);
}

function pickSlotCompany(slot, company) {
  slot.match = company;
  slot.input.value = `${company.name} (${company.ticker})`;
  slot.wrapper.classList.add('slot-selected');
  hideSlotDD(slot);
  updateCompareBtn();
}

function hideSlotDD(slot) {
  slot.dropdown.classList.add('hidden');
  slot.dropdown.innerHTML = '';
}

// Close dropdowns when clicking outside compare slots
document.addEventListener('click', e => {
  if (!e.target.closest('.compare-slot')) compareSlots.forEach(hideSlotDD);
});

// ── Buttons ──────────────────────────────────────────────
document.getElementById('compare-add-btn').addEventListener('click', addCompareSlot);

document.getElementById('compare-btn').addEventListener('click', startComparison);

document.getElementById('cmp-back-btn').addEventListener('click', () => {
  show('search-screen');
  setMode('compare');
});

// ── Run comparison ───────────────────────────────────────
async function _fetchCompany(co) {
  const res = await fetch('/analyse', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(co),
  });
  const data = await res.json();
  if (data.error) throw new Error(data.error);
  data.company = data.company || co;
  return data;
}

async function startComparison() {
  const selected = compareSlots.filter(s => s.match).map(s => s.match);
  if (selected.length < 2) return;

  show('loading-screen');
  const total = selected.length;
  const results = [];
  const msgEl = document.getElementById('loading-msg');
  const subEl = document.getElementById('loading-sub');

  for (let i = 0; i < selected.length; i++) {
    const co = selected[i];

    // 9-second courtesy pause between companies so Macrotrends doesn't rate-limit
    if (i > 0) {
      msgEl.textContent = `Completed ${i} of ${total}. Pausing before next request…`;
      await new Promise(r => setTimeout(r, 9000));
    }

    msgEl.textContent = `Analysing company ${i + 1} of ${total}: ${co.name || co.ticker}…`;
    if (subEl) {
      subEl.textContent = `Fetching sequentially to avoid rate limits · ${total - i} of ${total} remaining`;
    }

    let data;
    try {
      data = await _fetchCompany(co);
    } catch (err) {
      // First attempt failed (network / server error) — wait 6s and retry once
      console.warn(`[EquityEngine] Attempt 1 failed for ${co.name || co.ticker}: ${err.message} — retrying…`);
      msgEl.textContent = `Request failed for ${co.name || co.ticker} — retrying in 6s…`;
      await new Promise(r => setTimeout(r, 6000));
      try {
        data = await _fetchCompany(co);
      } catch (err2) {
        console.warn(`[EquityEngine] Retry also failed for ${co.name || co.ticker}: ${err2.message}`);
        results.push({
          company: co,
          fetchError: err2.message,
          overall: { score: null, recommendation: 'ERROR' },
          pillars: {},
          unsupported_sector: false,
        });
        continue;
      }
    }

    // If data came back but overall score is null (rate-limited empty page), retry once
    if (!data.unsupported_sector && (!data.overall || data.overall.score === null)) {
      console.warn(`[EquityEngine] Null scores for ${co.name || co.ticker} — retrying in 6s…`);
      msgEl.textContent = `Incomplete data for ${co.name || co.ticker} — retrying in 6s…`;
      await new Promise(r => setTimeout(r, 6000));
      try {
        const retryData = await _fetchCompany(co);
        data = retryData;
      } catch (retryErr) {
        console.warn(`[EquityEngine] Retry failed for ${co.name || co.ticker}: ${retryErr.message}`);
        // Keep original (null-score) data — better than an error stub
      }
    }

    results.push(data);
  }

  // Restore sub-text for next solo search
  if (subEl) {
    subEl.textContent = 'Scraping 13 metrics from Macrotrends · This takes ~30 seconds';
  }

  // Console warnings for any null pillar scores
  results.forEach(r => {
    if (r.unsupported_sector || r.fetchError) return;
    const label = (r.company && (r.company.name || r.company.ticker)) || '?';
    PILLAR_DEFS.forEach(({ key }) => {
      const s = r.pillars && r.pillars[key] && r.pillars[key].score;
      if (s == null) {
        console.warn(`[EquityEngine] ${label}: pillar "${key}" score is null/missing`);
      }
    });
    if (r.overall == null || r.overall.score == null) {
      console.warn(`[EquityEngine] ${label}: overall score is null/missing`);
    }
  });

  compareResults = results.sort((a, b) => {
    const sa = (a.overall && a.overall.score !== null) ? a.overall.score : -1;
    const sb = (b.overall && b.overall.score !== null) ? b.overall.score : -1;
    return sb - sa;
  });
  renderComparison();
  show('compare-screen');
}

// ── Render comparison table ──────────────────────────────
const PILLAR_DEFS = [
  { key: 'Financial Risk',     abbr: 'FR', weight: '25%' },
  { key: 'Cash Generation',    abbr: 'CG', weight: '20%' },
  { key: 'Business Quality',   abbr: 'BQ', weight: '25%' },
  { key: 'Growth Quality',     abbr: 'GQ', weight: '15%' },
  { key: 'Capital Efficiency', abbr: 'CE', weight: '15%' },
];

function renderComparison() {
  const n = compareResults.length;
  document.getElementById('cmp-title').textContent =
    `Comparing ${n} compan${n === 1 ? 'y' : 'ies'}`;

  // Reset filter UI
  document.querySelectorAll('.sig-btn').forEach(b => b.classList.toggle('active', b.dataset.sig === 'ALL'));
  document.querySelectorAll('.pf-input').forEach(inp => { inp.value = ''; });
  activeSig = 'ALL';

  // Build company header cells
  const headerCells = compareResults.map((r, i) => {
    const co = r.company || {};
    const score = r.overall && r.overall.score !== null ? r.overall.score : null;
    const rec = (r.overall && r.overall.recommendation) || (r.fetchError ? 'ERROR' : '—');
    const sc = scoreClass(score);

    const recClass = r.unsupported_sector ? 'rec-NOT-RATED' :
                     r.fetchError ? 'rec-ERROR' :
                     `rec-${rec.replace(/\s+/g, '-')}`;
    const recLabel = r.unsupported_sector ? 'NOT RATED' :
                     r.fetchError ? 'FAILED' :
                     rec;
    const errorNote = r.fetchError
      ? `<div class="cmp-error-note" title="${r.fetchError}">Data unavailable — retry</div>`
      : '';

    return `
      <th data-colidx="${i}" class="co-th">
        <div class="cmp-co-hdr">
          <div class="cmp-co-rank">#${i + 1}</div>
          <div class="cmp-co-name" title="${co.name || co.ticker}">${co.name || co.ticker}</div>
          <div class="cmp-co-ticker">${co.ticker || ''}</div>
          <div class="cmp-overall ${sc}">${score !== null ? score.toFixed(2) : '—'}</div>
          <div class="rec-badge ${recClass} cmp-rec-badge">${recLabel}</div>
          ${errorNote}
        </div>
      </th>`;
  }).join('');

  // Build pillar rows
  const pillarRows = PILLAR_DEFS.map(({ key, weight }) => {
    const cells = compareResults.map((r, i) => {
      const pillar = r.pillars && r.pillars[key];
      const s = (pillar && pillar.score !== undefined) ? pillar.score : null;
      if (s === null) {
        return `<td data-colidx="${i}" class="cmp-td">
          <div class="cmp-cell-inner score-null"><div class="cmp-score-num">—</div></div>
        </td>`;
      }
      const sc = scoreClass(s);
      const barW = Math.round(s / 10 * 100);
      return `<td data-colidx="${i}" class="cmp-td">
        <div class="cmp-cell-inner ${sc}">
          <div class="cmp-score-num">${s.toFixed(1)}</div>
          <div class="cmp-bar-track"><div class="cmp-bar-fill" style="width:${barW}%"></div></div>
        </div>
      </td>`;
    }).join('');

    return `
      <tr>
        <td class="pillar-row-label">
          <span class="prl-name">${key}</span>
          <span class="prl-weight">${weight}</span>
        </td>
        ${cells}
      </tr>`;
  }).join('');

  document.getElementById('compare-table-wrap').innerHTML = `
    <table class="compare-table">
      <thead>
        <tr>
          <th class="pillar-row-label corner-th"></th>
          ${headerCells}
        </tr>
      </thead>
      <tbody>${pillarRows}</tbody>
    </table>`;

  applyFilters();
}

// ── Filters ──────────────────────────────────────────────
document.querySelectorAll('.sig-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.sig-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeSig = btn.dataset.sig;
    applyFilters();
  });
});

document.querySelectorAll('.pf-input').forEach(inp => {
  inp.addEventListener('input', applyFilters);
});

document.getElementById('cmp-reset').addEventListener('click', () => {
  document.querySelectorAll('.sig-btn').forEach(b => b.classList.toggle('active', b.dataset.sig === 'ALL'));
  document.querySelectorAll('.pf-input').forEach(inp => { inp.value = ''; });
  activeSig = 'ALL';
  applyFilters();
});

function applyFilters() {
  if (!compareResults.length) return;

  const pillarMins = {};
  document.querySelectorAll('.pf-input').forEach(inp => {
    const v = parseFloat(inp.value);
    if (!isNaN(v) && v > 0) pillarMins[inp.dataset.pillar] = v;
  });

  compareResults.forEach((r, i) => {
    const rec = (r.overall && r.overall.recommendation) || '';

    const sigOk = activeSig === 'ALL' || rec === activeSig;

    let pillarOk = true;
    for (const [pillar, minVal] of Object.entries(pillarMins)) {
      const pillarData = r.pillars && r.pillars[pillar];
      const s = pillarData && pillarData.score !== undefined ? pillarData.score : null;
      if (s === null || s < minVal) { pillarOk = false; break; }
    }

    const passes = sigOk && pillarOk;
    document.querySelectorAll(`[data-colidx="${i}"]`).forEach(el => {
      el.classList.toggle('col-out', !passes);
    });
  });
}
