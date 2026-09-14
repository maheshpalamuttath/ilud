function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str == null ? '' : String(str);
  return div.innerHTML;
}

function formatDateTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function statusPill(status) {
  const label = status === 'returned' ? 'Returned' : 'In use';
  return `<span class="status-pill status-pill--${status}">${label}</span>`;
}

// ---------------------------------------------------------------- tabs ----

const tabs = document.querySelectorAll('.tab');
const panels = document.querySelectorAll('.tab-panel');

tabs.forEach(tab => {
  tab.addEventListener('click', () => {
    tabs.forEach(t => t.classList.remove('tab--active'));
    panels.forEach(p => p.classList.remove('tab-panel--active'));
    tab.classList.add('tab--active');
    document.querySelector(`.tab-panel[data-panel="${tab.dataset.tab}"]`).classList.add('tab-panel--active');
  });
});

// ---------------------------------------------------------- by-date tab ----

const dateInput = document.getElementById('date-input');
const dateRunBtn = document.getElementById('date-run');
const dateSummary = document.getElementById('date-summary');
const dateTableBody = document.querySelector('#date-table tbody');
const dateEmpty = document.querySelector('.report-empty[data-for="date"]');

async function runDateReport() {
  const params = new URLSearchParams();
  if (dateInput.value) params.set('date', dateInput.value);

  const res = await fetch(`/api/reports/date?${params}`);
  const data = await res.json();
  if (!data.ok) {
    dateSummary.innerHTML = `<span class="chip">${escapeHtml(data.error || 'Could not load report.')}</span>`;
    dateTableBody.innerHTML = '';
    dateEmpty.hidden = true;
    return;
  }

  dateInput.value = data.date;
  dateSummary.innerHTML = `
    <span class="chip">Issued: <strong>${data.summary.issued}</strong></span>
    <span class="chip">Returned: <strong>${data.summary.returned}</strong></span>
    <span class="chip">Still in use: <strong>${data.summary.in_use}</strong></span>
  `;

  renderRows(dateTableBody, dateEmpty, data.rows, true);
}

dateRunBtn.addEventListener('click', runDateReport);

// -------------------------------------------------------------- range tab ----

const rangeStart = document.getElementById('range-start');
const rangeEnd = document.getElementById('range-end');
const rangeRunBtn = document.getElementById('range-run');
const rangeSummary = document.getElementById('range-summary');
const rangeTableBody = document.querySelector('#range-table tbody');
const rangeEmpty = document.querySelector('.report-empty[data-for="range"]');

async function runRangeReport() {
  const params = new URLSearchParams();
  if (rangeStart.value) params.set('start', rangeStart.value);
  if (rangeEnd.value) params.set('end', rangeEnd.value);

  const res = await fetch(`/api/reports/range?${params}`);
  const data = await res.json();
  if (!data.ok) {
    rangeSummary.innerHTML = `<span class="chip">${escapeHtml(data.error || 'Could not load report.')}</span>`;
    rangeTableBody.innerHTML = '';
    rangeEmpty.hidden = true;
    return;
  }

  rangeStart.value = data.start;
  rangeEnd.value = data.end;
  rangeSummary.innerHTML = `
    <span class="chip">Issued: <strong>${data.summary.issued}</strong></span>
    <span class="chip">Returned: <strong>${data.summary.returned}</strong></span>
    <span class="chip">Still in use: <strong>${data.summary.in_use}</strong></span>
  `;

  renderRows(rangeTableBody, rangeEmpty, data.rows, true);
}

rangeRunBtn.addEventListener('click', runRangeReport);

// -------------------------------------------------------------- patron tab ----

const patronCardInput = document.getElementById('patron-cardnumber');
const patronStart = document.getElementById('patron-start');
const patronEnd = document.getElementById('patron-end');
const patronRunBtn = document.getElementById('patron-run');
const patronSummary = document.getElementById('patron-summary');
const patronTableBody = document.querySelector('#patron-table tbody');
const patronEmpty = document.querySelector('.report-empty[data-for="patron"]');

async function runPatronReport() {
  const cardnumber = patronCardInput.value.trim();
  if (!cardnumber) {
    patronSummary.innerHTML = `<span class="chip">Enter a card number.</span>`;
    patronTableBody.innerHTML = '';
    patronEmpty.hidden = true;
    return;
  }

  const params = new URLSearchParams({ cardnumber });
  if (patronStart.value) params.set('start', patronStart.value);
  if (patronEnd.value) params.set('end', patronEnd.value);

  const res = await fetch(`/api/reports/patron?${params}`);
  const data = await res.json();
  if (!data.ok) {
    patronSummary.innerHTML = `<span class="chip">${escapeHtml(data.error || 'Could not load report.')}</span>`;
    patronTableBody.innerHTML = '';
    patronEmpty.hidden = true;
    return;
  }

  const nameChip = data.patron_name
    ? `<span class="chip">${escapeHtml(data.patron_name)} · Card #${escapeHtml(data.cardnumber)}</span>`
    : `<span class="chip">Card #${escapeHtml(data.cardnumber)}</span>`;

  patronSummary.innerHTML = `
    ${nameChip}
    <span class="chip">Issued: <strong>${data.summary.issued}</strong></span>
    <span class="chip">Returned: <strong>${data.summary.returned}</strong></span>
    <span class="chip">Still in use: <strong>${data.summary.in_use}</strong></span>
  `;

  renderRows(patronTableBody, patronEmpty, data.rows, false);
}

patronRunBtn.addEventListener('click', runPatronReport);
patronCardInput.addEventListener('keydown', e => { if (e.key === 'Enter') runPatronReport(); });

// ------------------------------------------------------------- shared ----

function renderRows(tbody, emptyEl, rows, withPatronColumns) {
  if (!rows || rows.length === 0) {
    tbody.innerHTML = '';
    emptyEl.hidden = false;
    return;
  }
  emptyEl.hidden = true;

  tbody.innerHTML = rows.map(r => {
    const cells = [
      `<td>${escapeHtml(r.barcode)}</td>`,
      `<td class="title-cell">${escapeHtml(r.title || 'Untitled')}</td>`,
      `<td>${escapeHtml(r.itemtype || '')}</td>`,
    ];
    if (withPatronColumns) {
      cells.push(`<td>${escapeHtml(r.patron_name)}</td>`);
      cells.push(`<td>${escapeHtml(r.cardnumber)}</td>`);
    }
    cells.push(`<td>${formatDateTime(r.issued_at)}</td>`);
    cells.push(`<td>${formatDateTime(r.returned_at)}</td>`);
    cells.push(`<td>${statusPill(r.status)}</td>`);
    return `<tr>${cells.join('')}</tr>`;
  }).join('');
}

const dateExportLink = document.getElementById('date-export');
const rangeExportLink = document.getElementById('range-export');
const patronExportLink = document.getElementById('patron-export');

dateExportLink.addEventListener('click', () => {
  const params = new URLSearchParams();
  if (dateInput.value) params.set('date', dateInput.value);
  dateExportLink.href = `/api/reports/date/export?${params}`;
});

rangeExportLink.addEventListener('click', () => {
  const params = new URLSearchParams();
  if (rangeStart.value) params.set('start', rangeStart.value);
  if (rangeEnd.value) params.set('end', rangeEnd.value);
  rangeExportLink.href = `/api/reports/range/export?${params}`;
});

patronExportLink.addEventListener('click', (e) => {
  const cardnumber = patronCardInput.value.trim();
  if (!cardnumber) {
    e.preventDefault();
    patronSummary.innerHTML = `<span class="chip">Enter a card number first.</span>`;
    return;
  }
  const params = new URLSearchParams({ cardnumber });
  if (patronStart.value) params.set('start', patronStart.value);
  if (patronEnd.value) params.set('end', patronEnd.value);
  patronExportLink.href = `/api/reports/patron/export?${params}`;
});

// ------------------------------------------------------------- init ----

const today = document.currentScript.dataset.today || new Date().toISOString().slice(0, 10);
dateInput.value = today;

const sevenDaysAgo = new Date();
sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 6);
rangeStart.value = sevenDaysAgo.toISOString().slice(0, 10);
rangeEnd.value = today;

runDateReport();
