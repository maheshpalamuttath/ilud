const cardnumberInput = document.getElementById('cardnumber');
const lookupBtn = document.getElementById('lookup-btn');
const patronCard = document.getElementById('patron-card');
const barcodesInput = document.getElementById('barcodes');
const issueBtn = document.getElementById('issue-btn');
const issueResults = document.getElementById('issue-results');

const returnBarcodesInput = document.getElementById('return-barcodes');
const returnBtn = document.getElementById('return-btn');
const returnResults = document.getElementById('return-results');

const inUseList = document.getElementById('in-use-list');
const inUseCount = document.getElementById('in-use-count');

// How long results/feedback stay on screen before auto-clearing, so the
// next patron at the kiosk doesn't see the previous one's info.
const ISSUE_RESULTS_TIMEOUT_MS = 8000;
const RETURN_FEEDBACK_TIMEOUT_MS = 5000;

let issueClearTimer = null;
let returnClearTimer = null;

let currentPatron = null; // { cardnumber, name }

function setPatronCard(state, payload) {
  if (state === 'empty') {
    patronCard.className = 'patron-card patron-card--empty';
    patronCard.innerHTML = '<p class="patron-card__hint">No patron looked up yet.</p>';
    barcodesInput.disabled = true;
    issueBtn.disabled = true;
    currentPatron = null;
    return;
  }
  if (state === 'error') {
    patronCard.className = 'patron-card patron-card--error';
    patronCard.textContent = payload;
    barcodesInput.disabled = true;
    issueBtn.disabled = true;
    currentPatron = null;
    return;
  }
  patronCard.className = 'patron-card patron-card--found';
  patronCard.innerHTML = `
    <div class="patron-card__name">${escapeHtml(payload.name || '(no name on file)')}</div>
    <div class="patron-card__card">Card #${escapeHtml(payload.cardnumber)}</div>
  `;
  barcodesInput.disabled = false;
  issueBtn.disabled = false;
  currentPatron = payload;
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str == null ? '' : String(str);
  return div.innerHTML;
}

async function lookupPatron() {
  const cardnumber = cardnumberInput.value.trim();
  issueResults.innerHTML = '';
  clearTimeout(issueClearTimer);
  if (!cardnumber) {
    setPatronCard('empty');
    return;
  }
  lookupBtn.disabled = true;
  lookupBtn.textContent = 'Looking up…';
  try {
    const res = await fetch(`/api/patron/${encodeURIComponent(cardnumber)}`);
    const data = await res.json();
    if (data.ok) {
      setPatronCard('found', { name: data.name, cardnumber: data.cardnumber });
      barcodesInput.focus();
    } else {
      setPatronCard('error', data.error || 'Patron not found.');
    }
  } catch (err) {
    setPatronCard('error', 'Could not reach the server.');
  } finally {
    lookupBtn.disabled = false;
    lookupBtn.textContent = 'Find';
  }
}

async function issueBooks() {
  if (!currentPatron) return;
  const barcodes = barcodesInput.value
    .split('\n')
    .map(s => s.trim())
    .filter(Boolean);

  if (barcodes.length === 0) {
    return;
  }

  clearTimeout(issueClearTimer);
  issueBtn.disabled = true;
  issueBtn.textContent = 'Issuing…';
  issueResults.innerHTML = '';

  try {
    const res = await fetch('/api/issue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cardnumber: currentPatron.cardnumber, barcodes }),
    });
    const data = await res.json();

    if (!data.ok) {
      const li = document.createElement('li');
      li.className = 'result-item--error';
      li.textContent = data.error || 'Issuing failed.';
      issueResults.appendChild(li);
    } else {
      data.results.forEach(r => {
        const li = document.createElement('li');
        li.className = r.ok ? 'result-item--ok' : 'result-item--error';
        const barcodeSpan = `<span class="result-item__barcode">${escapeHtml(r.barcode)}</span>`;
        const detail = r.ok
          ? `${escapeHtml(r.title || 'In use')} · ${escapeHtml(r.itemtype || '')}`
          : escapeHtml(r.error);
        li.innerHTML = `${barcodeSpan}<span>${detail}</span>`;
        issueResults.appendChild(li);
      });
      const anyOk = data.results.some(r => r.ok);
      if (anyOk) {
        barcodesInput.value = '';
        refreshInUse();
      }
    }
  } catch (err) {
    const li = document.createElement('li');
    li.className = 'result-item--error';
    li.textContent = 'Could not reach the server.';
    issueResults.appendChild(li);
  } finally {
    issueBtn.disabled = false;
    issueBtn.textContent = 'Issue for library use';
    issueClearTimer = setTimeout(resetIssuePanel, ISSUE_RESULTS_TIMEOUT_MS);
  }
}

function resetIssuePanel() {
  issueResults.innerHTML = '';
  cardnumberInput.value = '';
  setPatronCard('empty');
  cardnumberInput.focus();
}

async function returnBook() {
  const barcodes = returnBarcodesInput.value
    .split('\n')
    .map(s => s.trim())
    .filter(Boolean);

  if (barcodes.length === 0) return;

  clearTimeout(returnClearTimer);
  returnBtn.disabled = true;
  returnBtn.textContent = 'Returning…';
  returnResults.innerHTML = '';

  try {
    const res = await fetch('/api/return', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ barcodes }),
    });
    const data = await res.json();

    if (!data.ok) {
      const li = document.createElement('li');
      li.className = 'result-item--error';
      li.textContent = data.error || 'Returning failed.';
      returnResults.appendChild(li);
    } else {
      data.results.forEach(r => {
        const li = document.createElement('li');
        li.className = r.ok ? 'result-item--ok' : 'result-item--error';
        const barcodeSpan = `<span class="result-item__barcode">${escapeHtml(r.barcode)}</span>`;
        const detail = r.ok
          ? `Returned — ${escapeHtml(r.title || r.barcode)}`
          : escapeHtml(r.error);
        li.innerHTML = `${barcodeSpan}<span>${detail}</span>`;
        returnResults.appendChild(li);
      });
      const anyOk = data.results.some(r => r.ok);
      if (anyOk) {
        returnBarcodesInput.value = '';
        refreshInUse();
      }
    }
  } catch (err) {
    const li = document.createElement('li');
    li.className = 'result-item--error';
    li.textContent = 'Could not reach the server.';
    returnResults.appendChild(li);
  } finally {
    returnBtn.disabled = false;
    returnBtn.textContent = 'Return';
    returnBarcodesInput.focus();
    returnClearTimer = setTimeout(() => {
      returnResults.innerHTML = '';
      returnBarcodesInput.value = '';
    }, RETURN_FEEDBACK_TIMEOUT_MS);
  }
}

const IN_USE_DISPLAY_LIMIT = 3;

function renderInUse(items) {
  inUseCount.textContent = items.length;
  if (items.length === 0) {
    inUseList.innerHTML = '<li class="in-use-empty">Nothing checked out for in-library use right now.</li>';
    return;
  }

  const visible = items.slice(0, IN_USE_DISPLAY_LIMIT);
  const remaining = items.length - visible.length;

  inUseList.innerHTML = visible.map(item => `
    <li>
      <span class="in-use-item__barcode">${escapeHtml(item.barcode)}</span>
      <span class="in-use-item__meta">
        <span class="in-use-item__title">${escapeHtml(item.title || 'Untitled')}</span>
        <span class="in-use-item__sub">${escapeHtml(item.patron_name)} · since ${escapeHtml(formatTime(item.issued_at))}</span>
      </span>
    </li>
  `).join('');

  if (remaining > 0) {
    inUseList.innerHTML += `
      <li class="in-use-more">
        <a href="/reports">+${remaining} more currently in use — view in Reports &rarr;</a>
      </li>
    `;
  }
}

function formatTime(isoString) {
  if (!isoString) return '';
  const d = new Date(isoString);
  if (isNaN(d.getTime())) return isoString;
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

async function refreshInUse() {
  try {
    const res = await fetch('/api/in_use');
    const data = await res.json();
    if (data.ok) {
      renderInUse(data.items);
    }
  } catch (err) {
    // Silent fail on background refresh; keep last known state.
  }
}

lookupBtn.addEventListener('click', lookupPatron);
cardnumberInput.addEventListener('keydown', e => { if (e.key === 'Enter') lookupPatron(); });

issueBtn.addEventListener('click', issueBooks);

returnBtn.addEventListener('click', returnBook);

setPatronCard('empty');
refreshInUse();
setInterval(refreshInUse, 5000);
