const state = {
  mainTab: 'budget',
  mode: 'month',
  month: currentMonthLocal(),
  year: String(new Date().getFullYear()),
  direction: 'expense',
  showSubcategories: false,
  selectedAccount: 'all',
  selected: null,
  filteredTransactions: null,
  categories: [],
  accounts: [],
  transactions: [],
  editing: null,
  periodBounds: null,
  requestSerial: 0,
  viewTab: 'category',
  analysisCache: new Map(),
  analysisRequestSerial: 0,
  asset: {
    viewMode: 'month',
    periodMonth: currentMonthLocal(),
    year: String(new Date().getFullYear()),
    summary: null,
    monthly: [],
    axis: {},
    yearly: [],
    holdings: [],
    products: [],
    metric: 'value',
    chartPointIndex: null,
    bounds: null,
    refreshBusy: false,
  },
};

const colors = [
  '#1565c0', '#1e88e5', '#42a5f5', '#64b5f6', '#90caf9',
  '#0d47a1', '#1976d2', '#4fc3f7', '#29b6f6', '#0288d1',
  '#26c6da', '#00acc1', '#5c6bc0', '#7e57c2', '#3949ab', '#607d8b',
];

const categoryIcons = {
  food: '🍽',
  daily: '🧴',
  transport: '🚃',
  hobby: '🎮',
  beauty: '💄',
  communication: '📱',
  utilities: '💡',
  health: '🏥',
  education: '📚',
  social: '🎁',
  housing: '🏠',
  insurance: '🛡',
  tax: '📄',
  uncategorized: '❔',
  cash_card: '💳',
  special: '💠',
  car: '🚗',
  fund_movement: '🔁',
};

const accountLabels = {
  'paypay-card': 'PayPayカード',
  amazon: 'Amazon',
  'group:amazon': 'Amazon',
  'amazon-order-history': 'Amazon',
  'amazon-order': 'Amazon',
};

const viewTabs = {
  category: 'viewTabCategory',
  analysis: 'viewTabAnalysis',
};

const accountChipOptions = [
  { id: 'all', name: 'すべて' },
  { id: 'paypay-card', name: 'PayPayカード' },
  { id: 'amazon', name: 'Amazon' },
];

const FUND_MOVEMENT_CATEGORY_ID = 'fund_movement';

const mascotAssets = {
  cheer: {
    webp: 'assets/mascot/tanuki/webp/tanuki_cheer.webp',
    png: 'assets/mascot/tanuki/png/tanuki_cheer.png',
  },
  happy: {
    webp: 'assets/mascot/tanuki/webp/tanuki_happy_pouch.webp',
    png: 'assets/mascot/tanuki/png/tanuki_happy_pouch.png',
  },
  thinking: {
    webp: 'assets/mascot/tanuki/webp/tanuki_thinking.webp',
    png: 'assets/mascot/tanuki/png/tanuki_thinking.png',
  },
  stale: {
    webp: 'assets/mascot/tanuki/webp/tanuki_mail_wink.webp',
    png: 'assets/mascot/tanuki/png/tanuki_mail_wink.png',
  },
  icon: {
    webp: 'assets/mascot/tanuki/png/tanuki_icon_128.png',
    png: 'assets/mascot/tanuki/png/tanuki_icon_128.png',
  },
};

const fmt = new Intl.NumberFormat('ja-JP', {
  style: 'currency',
  currency: 'JPY',
  maximumFractionDigits: 0,
});

const ASSET_EMPTY_MESSAGE = '資産データがまだありません。SBI証券の保有資産CSVを取り込むと表示されます。';
const ASSET_METRIC_LABELS = {
  value: '評価額',
  change: '増減額',
  purchase: '買い増し額',
  operation: '運用分',
};

function $(id) {
  return document.getElementById(id);
}

function isFundMovementCategoryId(categoryId) {
  return String(categoryId || '') === FUND_MOVEMENT_CATEGORY_ID;
}

function mascotImageHtml(assetName, altText, className = '') {
  const asset = mascotAssets[assetName];
  if (!asset) {
    return '';
  }
  return `<img src="${asset.webp}" data-fallback="${asset.png}" alt="${escapeHtml(altText)}" class="${className}" loading="lazy" decoding="async" />`;
}

function bindMascotFallback(root) {
  const scope = root || document;
  scope.querySelectorAll('img[data-fallback]').forEach((img) => {
    if (img.dataset.fallbackBound === '1') {
      return;
    }
    img.dataset.fallbackBound = '1';
    img.addEventListener('error', () => {
      const fallback = img.dataset.fallback || '';
      if (!fallback || img.dataset.fallbackTried === '1') {
        img.hidden = true;
        return;
      }
      img.dataset.fallbackTried = '1';
      img.src = fallback;
    });
  });
}

function currentMonthLocal() {
  const now = new Date();
  const y = now.getFullYear();
  const m = now.getMonth() + 1;
  return `${y.toString().padStart(4, '0')}-${m.toString().padStart(2, '0')}`;
}

function normalizeYear(value) {
  return String(Number(value || 0)).padStart(4, '0');
}

function shiftMonthValue(month, delta) {
  const [y, m] = month.split('-').map(Number);
  const total = y * 12 + (m - 1) + delta;
  const nextYear = Math.floor(total / 12);
  const nextMonth = (total % 12) + 1;
  return `${nextYear.toString().padStart(4, '0')}-${nextMonth.toString().padStart(2, '0')}`;
}

function compareMonth(a, b) {
  return a.localeCompare(b);
}

function compareYear(a, b) {
  return normalizeYear(a).localeCompare(normalizeYear(b));
}

function yearFromMonth(periodMonth) {
  return String(periodMonth || '').slice(0, 4);
}

function yearRangeLabel(year) {
  const y = Number(year || 0);
  if (!Number.isFinite(y) || y <= 0) {
    return '--';
  }
  return `${y}年`;
}

function formatPercent(value) {
  const n = Number(value || 0);
  return `${n.toFixed(1)}%`;
}

function formatSignedYen(value) {
  const n = Number(value || 0);
  if (!Number.isFinite(n)) {
    return '--';
  }
  const sign = n > 0 ? '+' : n < 0 ? '-' : '±';
  return `${sign}${fmt.format(Math.abs(n))}`;
}

function formatSignedPercent(value) {
  if (value === null || value === undefined) {
    return '--';
  }
  const n = Number(value || 0);
  const sign = n > 0 ? '+' : n < 0 ? '-' : '±';
  return `${sign}${Math.abs(n).toFixed(2)}%`;
}

function valueToneClass(value) {
  const n = Number(value || 0);
  if (!Number.isFinite(n) || n === 0) {
    return 'neutral';
  }
  return n > 0 ? 'positive' : 'negative';
}

function formatPeriodLabel() {
  if (state.mode === 'year') {
    return `${state.year}年`;
  }
  const [year, month] = state.month.split('-').map(Number);
  return `${year}年${month}月`;
}

function updateModeButtons() {
  const isMonth = state.mode === 'month';
  $('modeMonth').classList.toggle('active', isMonth);
  $('modeYear').classList.toggle('active', !isMonth);
}

function updateDirectionButtons() {
  const expense = state.direction === 'expense';
  $('expenseTab').classList.toggle('active', expense);
  $('incomeTab').classList.toggle('active', !expense);
  $('categoryHeader').textContent = expense ? 'カテゴリ別支出' : 'カテゴリ別収入';
}

function currentBounds() {
  return state.periodBounds;
}

function clampPeriodWithinBounds() {
  const bounds = currentBounds();
  if (!bounds) {
    return false;
  }

  if (state.mode === 'month') {
    let next = state.month;
    if (compareMonth(next, bounds.min_month) < 0) {
      next = bounds.min_month;
    }
    if (compareMonth(next, bounds.max_month) > 0) {
      next = bounds.max_month;
    }
    if (next !== state.month) {
      state.month = next;
      state.year = next.slice(0, 4);
      state.selected = null;
      return true;
    }
    state.year = state.month.slice(0, 4);
    return false;
  }

  let nextYear = normalizeYear(state.year);
  if (compareYear(nextYear, bounds.min_year) < 0) {
    nextYear = bounds.min_year;
  }
  if (compareYear(nextYear, bounds.max_year) > 0) {
    nextYear = bounds.max_year;
  }
  if (nextYear !== state.year) {
    state.year = nextYear;
    state.selected = null;
    return true;
  }
  return false;
}

function canShift(delta) {
  const bounds = currentBounds();
  if (!bounds) {
    return true;
  }
  if (state.mode === 'year') {
    const next = normalizeYear(Number(state.year) + delta);
    return compareYear(next, bounds.min_year) >= 0 && compareYear(next, bounds.max_year) <= 0;
  }
  const nextMonth = shiftMonthValue(state.month, delta);
  return compareMonth(nextMonth, bounds.min_month) >= 0 && compareMonth(nextMonth, bounds.max_month) <= 0;
}

function isAtLatest() {
  const bounds = currentBounds();
  if (!bounds) {
    return false;
  }
  if (state.mode === 'year') {
    return compareYear(state.year, bounds.max_year) === 0;
  }
  return compareMonth(state.month, bounds.max_month) === 0;
}

function updatePeriodButtons() {
  $('prevPeriod').disabled = !canShift(-1);
  $('nextPeriod').disabled = !canShift(1);
  $('latestPeriod').disabled = isAtLatest();
}

function shiftPeriod(delta) {
  if (!canShift(delta)) {
    return;
  }
  if (state.mode === 'year') {
    state.year = normalizeYear(Number(state.year) + delta);
  } else {
    state.month = shiftMonthValue(state.month, delta);
    state.year = state.month.slice(0, 4);
  }
  state.selected = null;
  loadAll();
}

function moveToLatest() {
  const bounds = currentBounds();
  if (!bounds || isAtLatest()) {
    return;
  }
  if (state.mode === 'year') {
    state.year = bounds.max_year;
  } else {
    state.month = bounds.max_month;
    state.year = state.month.slice(0, 4);
  }
  state.selected = null;
  loadAll();
}

function baseParams() {
  const params = new URLSearchParams({
    direction: state.direction,
    show_subcategories: String(state.showSubcategories),
  });
  if (state.mode === 'year') {
    params.set('year', state.year);
  } else {
    params.set('month', state.month);
  }
  applyAccountFilterParams(params);
  return params;
}

function applyAccountFilterParams(params) {
  if (state.selectedAccount === 'amazon') {
    params.set('account_group', 'amazon');
    return;
  }
  if (state.selectedAccount !== 'all') {
    params.set('account_id', state.selectedAccount);
  }
}

function accountLabel(accountId, fallbackName) {
  return accountLabels[accountId] || fallbackName || accountId;
}

function selectedAccountLabel() {
  if (state.selectedAccount === 'all') {
    return 'すべて';
  }
  if (state.selectedAccount === 'amazon') {
    return 'Amazon';
  }
  const found = (state.accounts || []).find((row) => row.id === state.selectedAccount);
  return accountLabel(state.selectedAccount, found?.name);
}

function resetCategorySelection() {
  state.selected = null;
  state.filteredTransactions = null;
  $('transactionTitle').textContent = '明細';
  $('clearFilter').hidden = true;
}

function accountFilterOptions() {
  return accountChipOptions.slice();
}

function renderAccountFilters() {
  const el = $('accountFilters');
  if (!el) {
    return;
  }
  const options = accountFilterOptions();
  if (!options.find((opt) => opt.id === state.selectedAccount)) {
    state.selectedAccount = 'all';
  }

  el.innerHTML = '';
  options.forEach((opt) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'filter-chip';
    button.classList.toggle('active', opt.id === state.selectedAccount);
    button.textContent = opt.name;
    button.addEventListener('click', () => {
      if (state.selectedAccount === opt.id) {
        return;
      }
      state.selectedAccount = opt.id;
      resetCategorySelection();
      state.analysisCache.clear();
      loadAll();
    });
    el.appendChild(button);
  });
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(mapApiErrorMessage(path, res.status, data));
  }
  return data;
}

async function apiWithErrorPayload(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(mapApiErrorMessage(path, res.status, data));
    err.payload = data;
    throw err;
  }
  return data;
}

function mapApiErrorMessage(path, status, data) {
  const serverMessage = data?.error || data?.error_message || '';
  const errorCode = String(data?.error_code || data?.errorCode || '');
  if (status === 404 && String(path || '').startsWith('/api/')) {
    return '家計簿サーバーが古い可能性があります。アプリを再起動してください。';
  }
  if (errorCode === 'dependency_missing' || serverMessage.includes('websocket-client が未インストール')) {
    return 'scripts\\01_setup.ps1 を再実行して依存関係を更新してください。';
  }
  if (errorCode === 'app_server_not_running' || serverMessage.includes('Codex App Serverが起動していません')) {
    return 'Codex App Serverが起動していません。分析込み起動スクリプトを使ってください。';
  }
  if (errorCode === 'websocket_connect_failed') {
    return 'Codex App Serverは起動していますが、WebSocket接続に失敗しました。起動し直してください。';
  }
  if (errorCode === 'protocol_failed') {
    return 'Codex App Serverとの通信手順で失敗しました。Codex CLIのバージョンまたはApp Server仕様が変わっている可能性があります。';
  }
  if (serverMessage.includes('接続形式が一致していません')) {
    return `${serverMessage}（分析込み起動スクリプトの利用を確認してください）`;
  }
  if (serverMessage) {
    return serverMessage;
  }
  return `通信に失敗しました (HTTP ${status})`;
}

function mapAnalysisFailureMessage(message, errorCode = '') {
  const text = String(message || '');
  if (errorCode === 'dependency_missing' || text.includes('websocket-client が未インストール')) {
    return 'scripts\\01_setup.ps1 を再実行して依存関係を更新してください。';
  }
  if (errorCode === 'app_server_not_running') {
    return 'Codex App Serverが起動していません。分析込み起動スクリプトを使ってください。';
  }
  if (errorCode === 'websocket_connect_failed') {
    return 'Codex App Serverは起動していますが、WebSocket接続に失敗しました。起動し直してください。';
  }
  if (errorCode === 'protocol_failed') {
    return 'Codex App Serverとの通信手順で失敗しました。Codex CLIのバージョンまたはApp Server仕様が変わっている可能性があります。';
  }
  if (text.includes('接続形式が一致していません')) {
    return `${text}（Codex App Serverの待ち受けURLを確認してください）`;
  }
  if (text.includes('Codex App Serverが起動していません') || text.includes('接続できません')) {
    return 'Codex App Serverが起動していません。分析込み起動スクリプトを使ってください。';
  }
  return text || '分析に失敗しました。';
}

async function loadAll() {
  const requestId = ++state.requestSerial;

  $('periodLabel').textContent = formatPeriodLabel();
  resetCategorySelection();

  const summaryParams = baseParams();
  const txParams = baseParams();
  const [summary, txs, cats, bounds, accounts] = await Promise.all([
    api(`/api/summary?${summaryParams.toString()}`),
    api(`/api/transactions?${txParams.toString()}`),
    api('/api/categories'),
    api('/api/period-bounds'),
    api('/api/accounts'),
  ]);

  if (requestId !== state.requestSerial) {
    return;
  }

  state.periodBounds = bounds;
  if (clampPeriodWithinBounds()) {
    $('periodLabel').textContent = formatPeriodLabel();
    updatePeriodButtons();
    await loadAll();
    return;
  }

  $('periodLabel').textContent = formatPeriodLabel();
  updatePeriodButtons();

  state.categories = cats.categories;
  state.accounts = accounts.accounts || [];
  state.transactions = txs.transactions;
  renderAccountFilters();

  renderSummary(summary);
  populateEditOptions();
  updateViewContents();
}
