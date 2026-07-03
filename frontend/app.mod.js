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
  return `${y}年4月〜${y + 1}年3月`;
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

function assetCurrentBounds() {
  return state.asset.bounds;
}

function assetCanShift(delta) {
  if (state.asset.viewMode === 'year') {
    const years = (state.asset.yearly || []).map((row) => String(row.year));
    if (!years.length) {
      return false;
    }
    const current = String(state.asset.year || '');
    const idx = years.findIndex((item) => item === current);
    if (idx < 0) {
      return false;
    }
    const nextIdx = idx - delta;
    return nextIdx >= 0 && nextIdx < years.length;
  }
  const bounds = assetCurrentBounds();
  if (!bounds) {
    return true;
  }
  const nextMonth = shiftMonthValue(state.asset.periodMonth, delta);
  return compareMonth(nextMonth, bounds.min_month) >= 0 && compareMonth(nextMonth, bounds.max_month) <= 0;
}

function assetIsAtLatest() {
  if (state.asset.viewMode === 'year') {
    if (!(state.asset.yearly || []).length) {
      return true;
    }
    const latest = String(state.asset.yearly[0].year || '');
    return String(state.asset.year || '') === latest;
  }
  const bounds = assetCurrentBounds();
  if (!bounds) {
    return false;
  }
  return compareMonth(state.asset.periodMonth, bounds.max_month) === 0;
}

function updateAssetPeriodButtons() {
  const prev = $('assetPrevPeriod');
  const next = $('assetNextPeriod');
  const latest = $('assetLatestPeriod');
  if (!prev || !next || !latest) {
    return;
  }
  prev.disabled = !assetCanShift(-1);
  next.disabled = !assetCanShift(1);
  latest.disabled = assetIsAtLatest();
}

function updateAssetPeriodLabel() {
  const target = $('assetPeriodLabel');
  if (!target) {
    return;
  }
  if (state.asset.viewMode === 'year') {
    const year = String(state.asset.year || '');
    target.textContent = `${year}年度 (${yearRangeLabel(year)})`;
    return;
  }
  const [year, month] = state.asset.periodMonth.split('-').map(Number);
  target.textContent = `${year}年${month}月`;
}

function selectedAssetMonthly() {
  return (state.asset.monthly || []).find((row) => row.period_month === state.asset.periodMonth) || null;
}

function selectedAssetFiscalYear() {
  return (state.asset.yearly || []).find((row) => String(row.year) === String(state.asset.year || '')) || null;
}

function hasAssetData() {
  return Boolean(state.asset.summary && state.asset.summary.has_data);
}

function selectedAssetSummary() {
  if (state.asset.viewMode === 'year') {
    const fiscal = selectedAssetFiscalYear();
    if (!fiscal) {
      return null;
    }
    return {
      period_month: fiscal.end_period_month,
      valuation_date: fiscal.end_period_month ? `${fiscal.end_period_month}-01` : '',
      current_value_yen: fiscal.end_value_yen,
      previous_value_yen: fiscal.start_value_yen,
      month_change_yen: fiscal.total_change_yen,
      month_change_rate: fiscal.total_change_rate,
      purchase_amount_yen: fiscal.purchase_amount_yen,
      operation_change_yen: fiscal.operation_change_yen,
      operation_change_rate: fiscal.operation_change_rate,
      invested_amount_yen: null,
      profit_loss_yen: null,
      profit_loss_rate: null,
      holding_count: null,
      percent_available: fiscal.percent_available,
      percent_unavailable_reason: fiscal.percent_unavailable_reason,
      fiscal_year: fiscal.year,
    };
  }
  const selected = selectedAssetMonthly();
  if (selected) {
    return selected;
  }
  return state.asset.summary || null;
}

function updateAssetModeButtons() {
  const month = $('assetModeMonth');
  const fiscal = $('assetModeYear');
  if (!month || !fiscal) {
    return;
  }
  const monthActive = state.asset.viewMode === 'month';
  month.classList.toggle('active', monthActive);
  fiscal.classList.toggle('active', !monthActive);
}

function getAssetMetricValue(row, metric) {
  if (metric === 'change') {
    return Number(row.month_change_yen || 0);
  }
  if (metric === 'purchase') {
    return Number(row.purchase_amount_yen || 0);
  }
  if (metric === 'operation') {
    return Number(row.operation_change_yen || 0);
  }
  return Number(row.current_value_yen || 0);
}

function assetMonthlyRowsForView() {
  const monthly = state.asset.monthly || [];
  if (state.asset.viewMode !== 'year') {
    return monthly;
  }
  const year = String(state.asset.year || '');
  return monthly.filter((row) => yearFromMonth(row.period_month) === year);
}

function assetYears() {
  return (state.asset.yearly || []).map((row) => String(row.year));
}

function latestMonthInYear(year) {
  const rows = (state.asset.monthly || []).filter((row) => yearFromMonth(row.period_month) === String(year || ''));
  return rows.length ? String(rows[rows.length - 1].period_month) : null;
}

function renderAssetEmptyState() {
  const empty = $('assetEmptyState');
  if (!empty) {
    return;
  }
  const mascot = mascotImageHtml('thinking', 'たぬきマスコット', 'asset-empty-mascot');
  empty.innerHTML = `
    <div class="asset-empty-card">
      <div class="asset-empty-copy">
        <p class="asset-empty-title">資産データを取り込むと表示されます</p>
        <p class="asset-empty-text">${escapeHtml(ASSET_EMPTY_MESSAGE)}</p>
      </div>
      <div class="asset-empty-image">${mascot}</div>
    </div>
  `;
  bindMascotFallback(empty);
}

function renderAssetCards() {
  const el = $('assetCards');
  if (!el) {
    return;
  }
  const summary = selectedAssetSummary();
  if (!summary) {
    el.innerHTML = '';
    return;
  }
  const totalChange = summary.month_change_yen;
  const totalChangeRate = summary.month_change_rate;
  const operation = summary.operation_change_yen;
  const profitLoss = summary.profit_loss_yen;
  const profitLossRate = summary.profit_loss_rate;
  const isFiscal = state.asset.viewMode === 'year';
  const periodCaption = isFiscal ? `${summary.fiscal_year}年度` : `評価日 ${escapeHtml(summary.valuation_date || '--')}`;
  const mascot = mascotImageHtml('cheer', 'たぬきマスコット', 'asset-total-mascot');
  el.innerHTML = `
    <article class="asset-card asset-card-total">
      <h3>${isFiscal ? '年次サマリー（評価額）' : '総資産（評価額）'}</h3>
      <div class="asset-card-main">${fmt.format(summary.current_value_yen || 0)}</div>
      <p class="asset-card-sub">
        総資産差 ${totalChange === null || totalChange === undefined ? '--' : formatSignedYen(totalChange)}
        <span class="asset-card-sub-rate">（買い増し込み${totalChangeRate === null || totalChangeRate === undefined ? '' : ` / ${formatSignedPercent(totalChangeRate)}` }）</span>
      </p>
      <p class="asset-card-note">${periodCaption}</p>
      <div class="asset-card-breakdown">
        <p><span>${isFiscal ? '年間買い増し額' : '買い増し額'}</span><strong>${fmt.format(summary.purchase_amount_yen || 0)}</strong></p>
        <p><span>運用増減</span><strong class="${valueToneClass(operation)}">${operation === null || operation === undefined ? '--' : formatSignedYen(operation)}</strong></p>
        <p><span>補足</span><strong>買い増し除外</strong></p>
        <p><span>${isFiscal ? '期首評価額' : '先月評価額'}</span><strong>${summary.previous_value_yen === null || summary.previous_value_yen === undefined ? '--' : fmt.format(summary.previous_value_yen)}</strong></p>
        <p><span>評価損益</span><strong class="${valueToneClass(profitLoss)}">${profitLoss === null || profitLoss === undefined ? '--' : formatSignedYen(profitLoss)}</strong></p>
        <p><span>損益率</span><strong class="${valueToneClass(profitLossRate)}">${profitLossRate === null || profitLossRate === undefined ? '--' : formatSignedPercent(profitLossRate)}</strong></p>
      </div>
      <div class="asset-mascot-wrap">${mascot}</div>
    </article>
  `;
  bindMascotFallback(el);
}

function renderAssetChart() {
  const el = $('assetChart');
  if (!el) {
    return;
  }
  const monthly = assetMonthlyRowsForView();
  if (!monthly.length) {
    el.innerHTML = `<p class="notice">${state.asset.viewMode === 'year' ? 'この年の月次データがありません。' : '月次スナップショットがありません。'}</p>`;
    return;
  }

  const metric = state.asset.metric;
  const label = ASSET_METRIC_LABELS[metric] || ASSET_METRIC_LABELS.value;
  const chartRows = monthly.slice(-12);
  const values = chartRows.map((row) => getAssetMetricValue(row, metric));
  const axisTicks = (state.asset.axis && state.asset.axis[metric]) || [];
  const minValue = axisTicks.length ? Math.min(...axisTicks) : Math.min(...values);
  const maxValue = axisTicks.length ? Math.max(...axisTicks) : Math.max(...values);
  const valueRange = Math.max(1, maxValue - minValue);

  const width = 360;
  const height = 216;
  const paddingLeft = 52;
  const paddingRight = 16;
  const paddingTop = 20;
  const paddingBottom = 44;
  const plotWidth = width - paddingLeft - paddingRight;
  const plotHeight = height - paddingTop - paddingBottom;
  const step = chartRows.length > 1 ? plotWidth / (chartRows.length - 1) : 0;
  const yFor = (value) => paddingTop + ((maxValue - value) / valueRange) * plotHeight;

  const points = chartRows.map((row, idx) => ({
    x: paddingLeft + idx * step,
    y: yFor(getAssetMetricValue(row, metric)),
  }));

  const linePath = points.map((point, idx) => `${idx === 0 ? 'M' : 'L'}${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(' ');
  const areaPath = `${linePath} L ${(paddingLeft + plotWidth).toFixed(2)} ${(paddingTop + plotHeight).toFixed(2)} L ${paddingLeft.toFixed(2)} ${(paddingTop + plotHeight).toFixed(2)} Z`;
  const selectedIndex = state.asset.chartPointIndex !== null && state.asset.chartPointIndex >= 0 && state.asset.chartPointIndex < chartRows.length
    ? state.asset.chartPointIndex
    : chartRows.length - 1;
  const selectedValue = values[selectedIndex];
  const selectedRow = chartRows[selectedIndex];
  const marker = points[selectedIndex];
  const latestLabel = metric === 'value' ? fmt.format(selectedValue) : formatSignedYen(selectedValue);
  const zeroLineY = minValue < 0 && maxValue > 0 ? yFor(0) : null;
  const yTicks = axisTicks.length ? axisTicks : [minValue, minValue + valueRange / 2, maxValue];
  const yGuides = yTicks.map((tick) => {
    const y = yFor(tick);
    const text = metric === 'value' ? fmt.format(tick) : formatSignedYen(tick);
    return `
      <line x1="${paddingLeft}" y1="${y.toFixed(2)}" x2="${(paddingLeft + plotWidth).toFixed(2)}" y2="${y.toFixed(2)}" class="asset-chart-y-guide"></line>
      <text class="asset-chart-y-label" x="${(paddingLeft - 6).toFixed(2)}" y="${(y + 4).toFixed(2)}" text-anchor="end">${escapeHtml(text)}</text>
    `;
  }).join('');
  const xLabels = chartRows.map((row, idx) => {
    const year = Number((row.period_month || '').slice(0, 4) || 0);
    const month = Number((row.period_month || '').slice(5, 7) || 0);
    const prevYear = idx > 0 ? Number((chartRows[idx - 1].period_month || '').slice(0, 4) || 0) : year;
    const labelText = idx === 0 || prevYear !== year || month === 1 ? `${year % 100}/${month}` : `${month}`;
    return `<text class="asset-chart-x-label" x="${(paddingLeft + idx * step).toFixed(2)}" y="${(height - 10).toFixed(2)}" text-anchor="middle">${labelText}</text>`;
  }).join('');
  const previousValue = selectedRow.previous_value_yen;
  const changeValue = selectedRow.month_change_yen;
  const changeRate = selectedRow.month_change_rate;
  const currentLabel = state.asset.viewMode === 'year' ? '対象月' : '今月';
  const previousLabel = state.asset.viewMode === 'year' ? '前月' : '先月';
  const compareSummary = `
    <div class="asset-chart-compare">
      <span>${currentLabel}: ${escapeHtml(fmt.format(selectedRow.current_value_yen || 0))}</span>
      <span>${previousLabel}: ${escapeHtml(previousValue === null || previousValue === undefined ? '--' : fmt.format(previousValue))}</span>
      <span class="${valueToneClass(changeValue)}">総資産差: ${escapeHtml(changeValue === null || changeValue === undefined ? '--' : formatSignedYen(changeValue))}</span>
      <span class="${valueToneClass(selectedRow.operation_change_yen)}">運用増減: ${escapeHtml(selectedRow.operation_change_yen === null || selectedRow.operation_change_yen === undefined ? '--' : formatSignedYen(selectedRow.operation_change_yen))}</span>
      <span class="${valueToneClass(changeRate)}">前月比: ${escapeHtml(changeRate === null || changeRate === undefined ? '--' : formatSignedPercent(changeRate))}</span>
      <span>買い増し額: ${escapeHtml(fmt.format(selectedRow.purchase_amount_yen || 0))}</span>
    </div>
  `;

  el.innerHTML = `
    <div class="asset-chart-head">
      <p class="asset-chart-metric">${escapeHtml(label)}</p>
      <p class="asset-chart-latest">${escapeHtml(latestLabel)}</p>
    </div>
    ${compareSummary}
    <svg class="asset-line-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(label)}の推移">
      <rect x="${paddingLeft}" y="${paddingTop}" width="${plotWidth}" height="${plotHeight}" class="asset-chart-plot-bg"></rect>
      ${yGuides}
      ${zeroLineY === null ? '' : `<line x1="${paddingLeft}" y1="${zeroLineY.toFixed(2)}" x2="${(paddingLeft + plotWidth).toFixed(2)}" y2="${zeroLineY.toFixed(2)}" class="asset-chart-zero-line"></line>`}
      <path d="${areaPath}" class="asset-chart-area"></path>
      <path d="${linePath}" class="asset-chart-line"></path>
      ${points.map((point, idx) => `<circle cx="${point.x.toFixed(2)}" cy="${point.y.toFixed(2)}" r="${idx === selectedIndex ? '4.4' : '3.4'}" class="asset-chart-point${idx === selectedIndex ? ' active' : ''}" data-idx="${idx}"></circle>`).join('')}
      <g class="asset-chart-labels">${xLabels}</g>
      <g class="asset-chart-tooltip">
        <rect x="${(marker.x - 46).toFixed(2)}" y="${(marker.y - 36).toFixed(2)}" width="92" height="24" rx="10"></rect>
        <text x="${marker.x.toFixed(2)}" y="${(marker.y - 19).toFixed(2)}" text-anchor="middle">${escapeHtml(latestLabel)}</text>
      </g>
    </svg>
  `;
  el.querySelectorAll('.asset-chart-point').forEach((node) => {
    node.addEventListener('click', () => {
      const next = Number(node.getAttribute('data-idx'));
      state.asset.chartPointIndex = Number.isFinite(next) ? next : chartRows.length - 1;
      renderAssetChart();
    });
  });
}

function renderAssetSummary() {
  const el = $('assetThisMonthSummary');
  if (!el) {
    return;
  }
  const summary = selectedAssetSummary();
  if (!summary) {
    el.innerHTML = '';
    return;
  }
  const isFiscal = state.asset.viewMode === 'year';
  const rows = [
    [isFiscal ? '最新評価額' : '総資産', fmt.format(summary.current_value_yen || 0)],
    ['総資産差（買い増し込み）', summary.month_change_yen === null ? '--' : formatSignedYen(summary.month_change_yen)],
    ['買い増し額', fmt.format(summary.purchase_amount_yen || 0)],
    ['運用増減（買い増し除外）', summary.operation_change_yen === null ? '--' : formatSignedYen(summary.operation_change_yen)],
    [isFiscal ? '運用増減率' : '前月比', (isFiscal ? summary.operation_change_rate : summary.month_change_rate) === null ? '--' : formatSignedPercent(isFiscal ? summary.operation_change_rate : summary.month_change_rate)],
    ['保有銘柄数', String(summary.holding_count || 0)],
  ];
  el.innerHTML = rows
    .map(([k, v], idx) => `<div class="asset-summary-item${idx < 3 ? ' primary' : ''}"><dt>${escapeHtml(k)}</dt><dd>${escapeHtml(v)}</dd></div>`)
    .join('');
}

function renderAssetYearly() {
  const el = $('assetYearlyCards');
  if (!el) {
    return;
  }
  const mode = state.asset.viewMode;
  const rows = mode === 'fiscal' ? (state.asset.yearly || []) : (state.asset.yearly || []);
  const titleNode = $('assetPerformanceTitle');
  if (titleNode) {
    titleNode.textContent = mode === 'fiscal' ? '年次成績' : '年別成績（暦年）';
  }
  if (!rows.length) {
    el.innerHTML = `<p class="notice">${mode === 'fiscal' ? '年次成績のデータがありません。' : '年別成績のデータがありません。'}</p>`;
    return;
  }
  const list = mode === 'fiscal' ? rows.slice(0, 1) : rows.slice(0, 4);
  el.innerHTML = list
    .map((row) => {
      const title = mode === 'fiscal'
        ? `${row.year}年度（${yearRangeLabel(row.year)}）`
        : (row.is_ytd ? `${row.year}年（年初〜最新月）` : `${row.year}年`);
      const percentBlocked = !row.percent_available;
      const reason = row.percent_unavailable_reason === 'base_too_small'
        ? `年初評価額が${fmt.format(100000)}未満のため％は参考外`
        : 'データ開始月が期間先頭ではないため％は参考外';
      return `
        <article class="asset-year-card">
          <h3>${escapeHtml(title)}</h3>
          ${percentBlocked ? `<p class="asset-year-note">${escapeHtml(reason)}</p>` : `
          <p>買い増し込み ${row.total_change_rate === null ? '--' : formatSignedPercent(row.total_change_rate)}</p>
          <p>運用分 ${row.operation_change_rate === null ? '--' : formatSignedPercent(row.operation_change_rate)}</p>`}
          <p>${mode === 'fiscal' ? '期首評価額' : '年初評価額'} ${fmt.format(row.start_value_yen || 0)}</p>
          <p>${mode === 'fiscal' ? '最新評価額' : '期末評価額'} ${fmt.format(row.end_value_yen || 0)}</p>
          <p>総資産差（買い増し込み） ${formatSignedYen(row.total_change_yen || 0)}</p>
          <p>${mode === 'fiscal' ? '年間買い増し額' : '年間買い増し額'} ${fmt.format(row.purchase_amount_yen || 0)}</p>
          <p>運用増減（買い増し除外） ${formatSignedYen(row.operation_change_yen || 0)}</p>
        </article>
      `;
    })
    .join('');
}

function renderAssetHoldings() {
  const el = $('assetHoldings');
  if (!el) {
    return;
  }
  const list = state.asset.holdings || [];
  if (!list.length) {
    el.innerHTML = '<p class="notice">この月の保有商品はありません。</p>';
    return;
  }
  el.innerHTML = list
    .map((row) => {
      const profitRate = row.profit_loss_rate === null ? '--' : formatSignedPercent(row.profit_loss_rate);
      const monthChange = row.month_change_yen;
      const monthRate = row.month_change_rate;
      const operation = row.operation_change_yen;
      const purchase = row.purchase_amount_yen || 0;
      return `
        <article class="asset-holding-card">
          <div class="asset-holding-head">
            <h3 class="asset-holding-title">${escapeHtml(row.name)}</h3>
            <p class="asset-holding-value">${fmt.format(row.current_value_yen || 0)}</p>
          </div>
          <div class="asset-holding-meta">
            <span>${escapeHtml(row.account_type || '未分類')}</span>
            <span>評価日 ${escapeHtml(row.valuation_date || '--')}</span>
            <span class="asset-source-chip">${escapeHtml(row.source_label || (row.source === 'generated' ? '生成' : '実測'))}</span>
          </div>
          <div class="asset-holding-pnl">
            <p class="${valueToneClass(row.profit_loss_yen)}">評価損益 ${formatSignedYen(row.profit_loss_yen || 0)}</p>
            <p class="${valueToneClass(row.profit_loss_rate)}">損益率 ${profitRate}</p>
            <p class="${valueToneClass(monthChange)}">総資産差 ${monthChange === null || monthChange === undefined ? '--' : formatSignedYen(monthChange)}</p>
            <p class="${valueToneClass(monthRate)}">先月比 ${monthRate === null || monthRate === undefined ? '--' : formatSignedPercent(monthRate)}</p>
            <p>買い増し額 ${fmt.format(purchase)}</p>
            <p class="${valueToneClass(operation)}">運用増減 ${operation === null || operation === undefined ? '--' : formatSignedYen(operation)}</p>
          </div>
          <div class="asset-holding-grid">
            <p>先月評価額 <strong>${row.previous_value_yen === null || row.previous_value_yen === undefined ? '--' : fmt.format(row.previous_value_yen)}</strong></p>
            <p>取得金額 <strong>${fmt.format(row.invested_amount_yen || 0)}</strong></p>
            <p>保有口数 <strong>${row.quantity ?? '--'}</strong></p>
            <p>基準価額 <strong>${row.base_price ? fmt.format(row.base_price) : '--'}</strong></p>
            <p>取得単価 <strong>${row.acquisition_price ? fmt.format(row.acquisition_price) : '--'}</strong></p>
          </div>
        </article>
      `;
    })
    .join('');
}

function populateAssetProductOptions() {
  const select = $('assetPurchaseProduct');
  const account = $('assetPurchaseAccountType');
  if (!select || !account) {
    return;
  }
  const products = state.asset.products || [];
  if (!products.length) {
    select.innerHTML = '<option value="">商品がありません</option>';
    account.value = '';
    return;
  }
  select.innerHTML = products
    .map((row) => `<option value="${row.id}" data-account="${escapeHtml(row.account_type || '')}">${escapeHtml(row.name)} (${escapeHtml(row.account_type || '未分類')})</option>`)
    .join('');
  const syncAccountType = () => {
    const selected = products.find((row) => String(row.id) === String(select.value));
    account.value = selected?.account_type || '';
  };
  select.onchange = syncAccountType;
  syncAccountType();
}

function renderAssetAll() {
  updateAssetModeButtons();
  updateAssetPeriodLabel();
  updateAssetPeriodButtons();

  const hasData = hasAssetData();
  const empty = $('assetEmptyState');
  if (empty) {
    empty.hidden = hasData;
  }
  document.querySelectorAll('#assetTabView .asset-data-only').forEach((node) => {
    node.hidden = !hasData;
  });

  if (!hasData) {
    renderAssetEmptyState();
    return;
  }

  renderAssetCards();
  renderAssetChart();
  renderAssetSummary();
  renderAssetYearly();
  renderAssetHoldings();
  populateAssetProductOptions();
}

async function loadAssetAll() {
  const periodMonth = state.asset.periodMonth;
  const params = new URLSearchParams({ period_month: periodMonth });
  const [summary, monthly, yearly, holdings, products] = await Promise.all([
    api(`/api/assets/summary?${params.toString()}`),
    api('/api/assets/monthly'),
    api('/api/assets/yearly'),
    api(`/api/assets/holdings?${params.toString()}`),
    api('/api/assets/products'),
  ]);
  state.asset.summary = summary;
  state.asset.monthly = monthly.monthly || [];
  state.asset.axis = monthly.axis || {};
  state.asset.yearly = yearly.yearly || [];
  state.asset.yearly = yearly.fiscal_yearly || [];
  state.asset.holdings = holdings.holdings || [];
  state.asset.products = products.products || [];
  state.asset.bounds = summary.bounds || null;
  state.asset.chartPointIndex = null;
  if (summary.period_month) {
    state.asset.periodMonth = summary.period_month;
  }
  if (state.asset.viewMode === 'year') {
    const years = assetYears();
    if (!years.includes(String(state.asset.year || ''))) {
      state.asset.year = years[0] || yearFromMonth(state.asset.periodMonth);
    }
  }
  renderAssetAll();
}

function shiftAssetPeriod(delta) {
  if (!assetCanShift(delta)) {
    return;
  }
  if (state.asset.viewMode === 'year') {
    const years = assetYears();
    const idx = years.findIndex((item) => item === String(state.asset.year || ''));
    const next = years[idx - delta];
    if (!next) {
      return;
    }
    state.asset.year = next;
    const month = latestMonthInYear(next);
    if (month) {
      state.asset.periodMonth = month;
    }
    loadAssetAll().catch((err) => alert(`資産データの表示に失敗しました: ${err.message}`));
    return;
  }
  state.asset.periodMonth = shiftMonthValue(state.asset.periodMonth, delta);
  loadAssetAll().catch((err) => alert(`資産データの表示に失敗しました: ${err.message}`));
}

function moveAssetLatest() {
  if (state.asset.viewMode === 'year') {
    const years = assetYears();
    if (!years.length) {
      return;
    }
    state.asset.year = years[0];
    const month = latestMonthInYear(years[0]);
    if (month) {
      state.asset.periodMonth = month;
    }
    loadAssetAll().catch((err) => alert(`資産データの表示に失敗しました: ${err.message}`));
    return;
  }
  if (!state.asset.bounds) {
    return;
  }
  state.asset.periodMonth = state.asset.bounds.max_month;
  loadAssetAll().catch((err) => alert(`資産データの表示に失敗しました: ${err.message}`));
}

function setAssetRefreshStatus(text, tone = 'neutral') {
  const node = $('assetRefreshStatus');
  if (!node) {
    return;
  }
  node.hidden = !text;
  node.textContent = text || '';
  node.classList.remove('positive', 'negative', 'neutral');
  node.classList.add(tone);
}

async function refreshAssetPrices() {
  const button = $('assetRefreshPricesButton');
  if (!button || state.asset.refreshBusy) {
    return;
  }
  state.asset.refreshBusy = true;
  button.disabled = true;
  button.textContent = '更新中…';
  setAssetRefreshStatus('基準価額を更新中です…', 'neutral');
  try {
    const result = await api('/api/assets/refresh-prices', {
      method: 'POST',
      body: JSON.stringify({ period_month: state.asset.periodMonth }),
    });
    const nav = result.nav_fetch || {};
    const message = `基準価額を更新しました（fetched ${nav.fetched || 0} / inserted ${nav.inserted || 0} / updated ${nav.updated || 0} / skipped ${nav.skipped || 0}）`;
    setAssetRefreshStatus(message, nav.errors ? 'negative' : 'positive');
    await loadAssetAll();
    if (nav.errors) {
      const details = (nav.error_details || []).map((item) => `${item.fund_name}: ${item.error}`).join('\n');
      alert(`一部失敗しました\n${details || '詳細不明'}`);
    }
  } catch (err) {
    setAssetRefreshStatus(`基準価額更新に失敗しました: ${err.message}`, 'negative');
  } finally {
    state.asset.refreshBusy = false;
    button.disabled = false;
    button.textContent = '基準価額更新';
  }
}

function changeAssetViewMode(mode) {
  if (state.asset.viewMode === mode) {
    return;
  }
  state.asset.viewMode = mode;
  if (mode === 'fiscal') {
    const currentFiscal = yearFromMonth(state.asset.periodMonth);
    state.asset.year = currentFiscal;
    const fallbackMonth = latestMonthInYear(currentFiscal);
    if (fallbackMonth) {
      state.asset.periodMonth = fallbackMonth;
    }
  }
  updateAssetModeButtons();
  loadAssetAll().catch((err) => alert(`資産データの表示に失敗しました: ${err.message}`));
}

function updateMainTabView() {
  const isBudget = state.mainTab === 'budget';
  const budgetView = $('budgetTabView');
  if (budgetView) {
    budgetView.hidden = !isBudget;
  }
  $('assetTabView').hidden = isBudget;
  $('appTitle').textContent = isBudget ? '家計簿' : '資産';
  const topActions = $('topActions');
  if (topActions) {
    topActions.hidden = !isBudget;
  }
  ['navHome', 'navTransfer', 'navBudget', 'navAssets', 'navSettings'].forEach((id) => {
    const button = $(id);
    if (button) {
      button.classList.remove('active');
    }
  });
  $('navBudget').classList.toggle('active', isBudget);
  $('navAssets').classList.toggle('active', !isBudget);
}

function setMainTab(tab) {
  if (state.mainTab === tab) {
    return;
  }
  state.mainTab = tab;
  updateMainTabView();
  if (tab === 'assets') {
    loadAssetAll().catch((err) => alert(`資産データの表示に失敗しました: ${err.message}`));
  } else {
    loadAll().catch((err) => alert(`表示に失敗しました: ${err.message}`));
  }
}

function renderSummary(summary) {
  $('incomeTotal').textContent = fmt.format(summary.income_total || 0);
  $('expenseTotal').textContent = fmt.format(summary.expense_total || 0);
  $('balanceTotal').textContent = fmt.format(summary.balance || 0);

  const sourceList = summary.categories || [];
  const list = state.direction === 'expense'
    ? sourceList.filter((item) => !isFundMovementCategoryId(item.category_id))
    : sourceList;
  const targetTotal = list.reduce((acc, item) => acc + Number(item.total || 0), 0);
  const hasData = targetTotal > 0 && list.length > 0;
  $('emptyNotice').hidden = hasData;
  $('emptyNoticeText').textContent =
    state.direction === 'expense' ? '表示する支出明細がありません。' : '表示する収入明細がありません。';

  renderDonut(list, targetTotal);
  renderDonutLegend(list, targetTotal);
  renderCategoryList(list, targetTotal);
  renderFundMovementHint(summary);
}

function renderFundMovementHint(summary) {
  const section = $('fundMovementHint');
  const total = Number(summary.fund_movement_total || 0);
  const count = Number(summary.fund_movement_count || 0);
  const shouldDisplay = state.direction === 'expense' && total > 0;
  section.dataset.hasFundMovement = shouldDisplay ? '1' : '0';
  if (shouldDisplay) {
    $('fundMovementTotal').textContent = `${fmt.format(total)} / ${count}件`;
  }
  applyFundMovementVisibility();
}

function applyFundMovementVisibility() {
  const section = $('fundMovementHint');
  const hasFundMovement = section.dataset.hasFundMovement === '1';
  section.hidden = !(hasFundMovement && state.viewTab === 'category' && state.direction === 'expense');
}

function renderDonut(list, total) {
  const donut = $('donut');
  if (!total || list.length === 0) {
    donut.style.background = 'conic-gradient(#e5e7eb 0deg 360deg)';
    return;
  }
  let start = 0;
  const lastIndex = list.length - 1;
  const stops = list.map((item, idx) => {
    const raw = (item.total / total) * 360;
    let end = idx === lastIndex ? 360 : start + raw;
    if (idx !== lastIndex) {
      end = Math.max(start + 1, end);
    }
    const part = `${colors[idx % colors.length]} ${start}deg ${end}deg`;
    start = end;
    return part;
  });
  donut.style.background = `conic-gradient(${stops.join(',')})`;
}

function renderDonutLegend(list, total) {
  const el = $('donutLegend');
  el.innerHTML = '';

  if (!total || list.length === 0) {
    el.hidden = true;
    return;
  }

  list.slice(0, 5).forEach((item, idx) => {
    const row = document.createElement('div');
    row.className = 'donut-legend-item';
    const label = state.showSubcategories && item.subcategory
      ? `${item.category_name} / ${item.subcategory}`
      : item.category_name;
    const percent = item.percent ?? (total > 0 ? (item.total / total * 100) : 0);
    row.innerHTML = `
      <span class="donut-legend-left">
        <span class="donut-swatch" style="background:${colors[idx % colors.length]}"></span>
        <span class="donut-legend-label">${escapeHtml(label)}</span>
      </span>
      <span class="donut-legend-percent">${formatPercent(percent)}</span>
    `;
    el.appendChild(row);
  });

  el.hidden = false;
}

function renderCategoryList(list, total) {
  const el = $('categoryList');
  el.innerHTML = '';
  if (!list.length) {
    return;
  }

  list.forEach((item, idx) => {
    const button = document.createElement('button');
    button.className = 'category-item';
    const label = state.showSubcategories && item.subcategory
      ? `${item.category_name} / ${item.subcategory}`
      : item.category_name;
    const countText = `${item.count}件の明細`;
    const percent = item.percent ?? (total > 0 ? (item.total / total * 100) : 0);
    const icon = categoryIcons[item.category_id] || '🧾';
    button.innerHTML = `
      <span class="category-icon-wrap" style="background:${colors[idx % colors.length]}">
        <span class="category-icon" aria-hidden="true">${escapeHtml(icon)}</span>
      </span>
      <span class="category-main">
        <span class="category-name">${escapeHtml(label)}</span>
        <span class="category-sub">${escapeHtml(countText)}</span>
      </span>
      <span class="category-right">
        <span class="category-amount">${fmt.format(item.total)}</span>
        <span class="category-percent">${formatPercent(percent)}</span>
      </span>
    `;
    button.addEventListener('click', () => selectCategory(item));
    el.appendChild(button);
  });
}

async function selectCategory(item) {
  state.selected = item;
  const params = baseParams();
  params.set('category_id', item.category_id);
  if (state.showSubcategories && item.subcategory) {
    params.set('subcategory', item.subcategory);
  }
  const data = await api(`/api/transactions?${params.toString()}`);
  const baseLabel = isFundMovementCategoryId(item.category_id)
    ? '資金移動・チャージ'
    : item.category_name;
  const label = state.showSubcategories && item.subcategory
    ? `${baseLabel} / ${item.subcategory}`
    : baseLabel;
  $('transactionTitle').textContent = `${label}の明細`;
  $('clearFilter').hidden = false;
  state.filteredTransactions = data.transactions;
  renderTransactions(data.transactions);
  if (state.viewTab !== 'category') {
    setViewTab('category');
  }
}

function renderTransactions(txs) {
  const el = $('transactions');
  el.innerHTML = '';
  if (!txs.length) {
    const msg = state.direction === 'expense' ? '表示する支出明細がありません。' : '表示する収入明細がありません。';
    el.innerHTML = `<p class="notice">${escapeHtml(msg)}</p>`;
    return;
  }

  txs.forEach((tx) => {
    const day = Number(tx.occurred_at.slice(8, 10));
    const month = Number(tx.occurred_at.slice(5, 7));
    const item = document.createElement('article');
    item.className = 'transaction';
    const sign = tx.direction === 'expense' ? '-' : '+';
    const amountClass = tx.direction === 'expense' ? 'tx-amount expense' : 'tx-amount income';
    const icon = categoryIcons[tx.category_id] || '🧾';
    const normalizedAccountName = accountLabel(tx.account_id, tx.account_name);
    const isFundMovement = Boolean(tx.is_fund_movement) || isFundMovementCategoryId(tx.category_id);
    const fundMovementBadge = isFundMovement
      ? '<span class="tx-badge transfer">資金移動</span>'
      : '';
    item.innerHTML = `
      <div class="tx-date"><small>${month}月</small>${day}</div>
      <div class="tx-main">
        <div class="tx-merchant">
          <span class="tx-icon" aria-hidden="true">${escapeHtml(icon)}</span>
          <span>${escapeHtml(tx.merchant)}</span>
        </div>
        <div class="tx-meta">${escapeHtml(tx.category_name)} / ${escapeHtml(tx.subcategory)} ・ ${escapeHtml(normalizedAccountName)} ${fundMovementBadge}</div>
        <button class="tx-edit" type="button">カテゴリを変更</button>
      </div>
      <div class="${amountClass}">${sign}${fmt.format(tx.amount_yen)}</div>
    `;
    item.querySelector('.tx-edit').addEventListener('click', () => openEdit(tx));
    el.appendChild(item);
  });
}

function populateEditOptions() {
  const sel = $('editCategory');
  sel.innerHTML = '';
  state.categories.forEach((cat) => {
    const opt = document.createElement('option');
    opt.value = cat.id;
    opt.textContent = cat.name;
    sel.appendChild(opt);
  });
  updateSubcategoryList();
}

function updateSubcategoryList() {
  const cat = state.categories.find((c) => c.id === $('editCategory').value);
  const dl = $('subcategoryList');
  const chips = $('subcategoryChips');
  const current = $('editSubcategory').value || '未分類';
  const unique = new Set(['未分類', ...(cat?.subcategories || [])]);
  dl.innerHTML = '';
  chips.innerHTML = '';
  [...unique].forEach((sub) => {
    const opt = document.createElement('option');
    opt.value = sub;
    dl.appendChild(opt);

    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'subcategory-chip';
    chip.textContent = sub;
    chip.classList.toggle('active', sub === current);
    chip.addEventListener('click', () => {
      $('editSubcategory').value = sub;
      syncSubcategoryChipState();
    });
    chips.appendChild(chip);
  });
  syncSubcategoryChipState();
}

function syncSubcategoryChipState() {
  const selected = ($('editSubcategory').value || '').trim() || '未分類';
  document.querySelectorAll('#subcategoryChips .subcategory-chip').forEach((chip) => {
    chip.classList.toggle('active', chip.textContent === selected);
  });
}

function openEdit(tx) {
  state.editing = tx;
  const mascot = $('editDialogMascot');
  if (mascot) {
    mascot.innerHTML = mascotImageHtml('icon', 'たぬきアイコン', 'analysis-mascot analysis-mascot-dialog');
    bindMascotFallback(mascot);
  }
  $('editMerchant').textContent = `${tx.merchant} / ${fmt.format(tx.amount_yen)}`;
  $('editCategory').value = tx.category_id;
  $('editSubcategory').value = tx.subcategory || '未分類';
  $('learnRule').checked = true;
  $('applyPastMerchant').checked = false;
  updateSubcategoryList();
  syncSubcategoryChipState();
  $('editDialog').showModal();
}

async function saveEdit(ev) {
  ev.preventDefault();
  if (!state.editing) {
    return;
  }
  const result = await api(`/api/transactions/${state.editing.id}`, {
    method: 'PATCH',
    body: JSON.stringify({
      category_id: $('editCategory').value,
      subcategory: $('editSubcategory').value || '未分類',
      learn_rule: $('learnRule').checked,
      apply_to_existing: $('applyPastMerchant').checked,
    }),
  });
  $('editDialog').close();
  if ($('applyPastMerchant').checked) {
    alert(`過去の同じ店舗にも反映しました（${result.applied_count || 1}件）`);
  }
  state.editing = null;
  state.analysisCache.clear();
  await loadAll();
}

function openAssetPurchaseDialog() {
  const dialog = $('assetPurchaseDialog');
  if (!dialog) {
    return;
  }
  const today = new Date().toISOString().slice(0, 10);
  $('assetPurchaseDate').value = today;
  $('assetPurchaseAmount').value = '';
  $('assetPurchaseQuantity').value = '';
  $('assetPurchaseUnitPrice').value = '';
  $('assetPurchaseSettlementDate').value = '';
  $('assetPurchaseMemo').value = '';
  populateAssetProductOptions();
  if (!(state.asset.products || []).length) {
    alert('買い増し対象の商品がありません。先に資産CSVを取り込んでください。');
    return;
  }
  dialog.showModal();
}

async function saveAssetPurchase(ev) {
  ev.preventDefault();
  const assetId = Number($('assetPurchaseProduct').value || 0);
  const purchaseDate = $('assetPurchaseDate').value;
  const amountYen = Number($('assetPurchaseAmount').value || 0);
  if (!assetId || !purchaseDate || amountYen <= 0) {
    alert('日付・商品・購入金額を入力してください。');
    return;
  }
  await api('/api/assets/purchases', {
    method: 'POST',
    body: JSON.stringify({
      asset_id: assetId,
      purchase_date: purchaseDate,
      amount_yen: amountYen,
      quantity: $('assetPurchaseQuantity').value || null,
      unit_price: $('assetPurchaseUnitPrice').value || null,
      settlement_date: $('assetPurchaseSettlementDate').value || null,
      memo: $('assetPurchaseMemo').value || null,
      source: 'manual',
    }),
  });
  $('assetPurchaseDialog').close();
  await loadAssetAll();
}

function analysisContextFromState() {
  if (state.mode === 'year') {
    const year = state.year || state.month.slice(0, 4);
    return { periodType: 'year', period: year, title: '年間分析' };
  }
  return { periodType: 'month', period: state.month, title: '月次分析' };
}

function analysisKey(context) {
  return [context.periodType, context.period, state.selectedAccount, state.direction].join(':');
}

function analysisTabLabelForMode(mode = state.mode) {
  return mode === 'year' ? '年間分析' : '月次分析';
}

function normalizeViewTab() {
  if (state.viewTab !== 'category' && state.viewTab !== 'analysis') {
    state.viewTab = 'category';
  }
}

function renderViewTabs() {
  $('viewTabAnalysis').textContent = analysisTabLabelForMode();
  Object.entries(viewTabs).forEach(([name, id]) => {
    $(id).classList.toggle('active', state.viewTab === name);
  });
}

function setViewTab(tab) {
  if (state.viewTab === tab) {
    return;
  }
  state.viewTab = tab;
  updateViewContents();
}

function updateViewContents() {
  normalizeViewTab();
  renderViewTabs();
  const showAnalysis = state.viewTab === 'analysis';
  const txHeader = document.querySelector('.transactions-header');

  if (!showAnalysis) {
    $('categoryList').hidden = false;
    $('analysisPanel').hidden = true;
    $('transactions').hidden = false;
    applyFundMovementVisibility();
    if (txHeader) {
      txHeader.hidden = false;
    }
    $('transactionTitle').textContent = state.selected
      ? (state.showSubcategories && state.selected.subcategory
          ? `${state.selected.category_name} / ${state.selected.subcategory}の明細`
          : `${state.selected.category_name}の明細`)
      : '明細';
    $('clearFilter').hidden = !state.selected;
    const txs = state.selected && state.filteredTransactions ? state.filteredTransactions : state.transactions;
    renderTransactions(txs);
    return;
  }

  $('categoryList').hidden = true;
  applyFundMovementVisibility();
  if (txHeader) {
    txHeader.hidden = true;
  }
  $('transactions').hidden = true;
  $('analysisPanel').hidden = false;
  $('clearFilter').hidden = true;
  const context = analysisContextFromState();
  renderAnalysisPlaceholders(context);
  loadAnalysis(context).catch((err) => {
    $('analysisStatus').textContent = err.message || '分析情報の取得に失敗しました。';
    $('analysisResult').innerHTML = '';
  });
}

function renderAnalysisPlaceholders(context) {
  const account = selectedAccountLabel();
  const directionLabel = state.direction === 'expense' ? '表示する支出明細がありません。' : '表示する収入明細がありません。';
  const periodLabel = context.periodType === 'month' ? context.period : `${context.period}年`;
  const heroIntro = context.periodType === 'month'
    ? '今月の家計、ちょっと見てあげるね。'
    : '今年の家計、流れを見ていこう。';

  $('analysisHero').innerHTML = `
    <div class="analysis-character">
      ${mascotImageHtml('cheer', 'たぬきマスコット', 'analysis-mascot analysis-mascot-header')}
      <div class="analysis-character-copy">
        <p class="analysis-character-line">${heroIntro}</p>
        <p class="analysis-character-sub">数字だけじゃなく、見るべきところをしぼって出すよ。</p>
      </div>
    </div>
  `;
  $('analysisTarget').textContent = `対象: ${periodLabel} / ${account} / ${directionLabel}`;
  $('runAnalysisButton').textContent = context.periodType === 'month' ? '分析する' : '年間分析する';
  $('rerunAnalysisButton').textContent = '再分析';
  bindMascotFallback($('analysisHero'));
}

function parseAnalysisSections(text) {
  const normalized = String(text || '').replace(/\r\n/g, '\n');
  const lines = normalized.split('\n');
  const sections = [];
  let current = null;

  lines.forEach((rawLine) => {
    const line = rawLine.trim();
    const heading = line.match(/^(?:\d+\.\s*)?(今月の結論|見るべき支出|次にやること|今月は気にしなくていいこと)\s*[:：]?\s*$/);
    if (heading) {
      if (current) {
        sections.push(current);
      }
      current = { title: heading[1], lines: [] };
      return;
    }
    if (!current) {
      return;
    }
    if (line) {
      current.lines.push(line);
    }
  });

  if (current) {
    sections.push(current);
  }
  if (sections.length > 0) {
    return sections;
  }
  return [{ title: 'コメント', lines: normalized.split('\n').map((line) => line.trim()).filter(Boolean) }];
}

function renderAnalysisSectionBody(lines) {
  const clean = lines.map((line) => line.trim()).filter(Boolean);
  if (!clean.length) {
    return '<p class="analysis-line">（コメントなし）</p>';
  }
  const bulletLines = clean.filter((line) => /^[-・●]\s*/.test(line));
  if (bulletLines.length >= Math.min(2, clean.length)) {
    const items = clean
      .map((line) => line.replace(/^[-・●]\s*/, '').trim())
      .filter(Boolean)
      .map((line) => `<li>${escapeHtml(line)}</li>`)
      .join('');
    return `<ul class="analysis-list">${items}</ul>`;
  }
  return clean.map((line) => `<p class="analysis-line">${escapeHtml(line)}</p>`).join('');
}

function renderAnalysisResultCard(text, stale = false) {
  const sections = parseAnalysisSections(text);
  const cards = sections.map((section, idx) => {
    const body = renderAnalysisSectionBody(section.lines);
    const classNames = ['analysis-section'];
    if (idx === 0 || section.title === '今月の結論') {
      classNames.push('hero');
    }
    if (section.title === '見るべき支出') {
      classNames.push('focus');
    }
    if (section.title === '次にやること') {
      classNames.push('next-action');
    }
    return `
      <section class="${classNames.join(' ')}">
        <h4>${escapeHtml(section.title)}</h4>
        ${body}
      </section>
    `;
  }).join('');
  const staleBadge = stale
    ? `
      <section class="analysis-stale-note">
        ${mascotImageHtml('stale', '前回分析のお知らせ', 'analysis-mascot analysis-mascot-stale')}
        <p>前回の分析を表示中。分類や明細が変わってるから、必要なら再分析してね。</p>
      </section>
    `
    : '';

  $('analysisResult').innerHTML = `
    <div class="analysis-character">
      ${mascotImageHtml('cheer', '分析コメントのたぬき', 'analysis-mascot')}
      <div class="analysis-character-copy">
        <p class="analysis-character-line">見どころだけ、ぎゅっとまとめたよ。</p>
      </div>
    </div>
    ${staleBadge}
    ${cards}
  `;
  bindMascotFallback($('analysisResult'));
}

function showAnalysisData(context, data) {
  const shortHash = data.input_hash ? String(data.input_hash).slice(0, 12) : '';
  if (data.has_analysis) {
    if (data.stale) {
      $('analysisStatus').textContent = '前回分析を表示中です。分類や明細が変更されています。必要なら再分析してください。';
    } else {
      $('analysisStatus').textContent = `分析済み${shortHash ? `（input_hash: ${shortHash}...）` : ''}`;
    }
    renderAnalysisResultCard(data.result_text || '分析結果テキストがありません。', Boolean(data.stale));
  } else {
    $('analysisStatus').textContent = 'まだ分析されていません。';
    $('analysisResult').innerHTML = `
      <section class="analysis-empty">
        ${mascotImageHtml('thinking', '分析待ちのたぬき', 'analysis-mascot analysis-mascot-empty')}
        <div>
          <p class="analysis-character-line">まだ分析してないよ。</p>
          <p class="analysis-empty-sub">ボタンを押すと、この条件でチェックするよ。</p>
        </div>
      </section>
    `;
    bindMascotFallback($('analysisResult'));
  }
  $('runAnalysisButton').disabled = false;
  $('rerunAnalysisButton').disabled = false;
  renderAnalysisPlaceholders(context);
}

async function loadAnalysis(context) {
  const requestId = ++state.analysisRequestSerial;
  const key = analysisKey(context);
  if (state.analysisCache.has(key)) {
    showAnalysisData(context, state.analysisCache.get(key));
    return;
  }

  $('analysisStatus').textContent = '分析情報を確認中...';
  $('analysisResult').innerHTML = '';
  $('runAnalysisButton').disabled = true;
  $('rerunAnalysisButton').disabled = true;

  const params = new URLSearchParams({
    period_type: context.periodType,
    direction: state.direction,
  });
  applyAccountFilterParams(params);
  if (context.periodType === 'month') {
    params.set('month', context.period);
  } else {
    params.set('year', context.period);
  }
  const data = await api(`/api/analysis?${params.toString()}`);
  if (requestId !== state.analysisRequestSerial) {
    return;
  }
  if (data.has_analysis) {
    state.analysisCache.set(key, data);
  }
  showAnalysisData(context, data);
}

async function runAnalysis(force) {
  const context = analysisContextFromState();
  const button = force ? $('rerunAnalysisButton') : $('runAnalysisButton');
  const originalLabel = button.textContent;
  button.textContent = force ? '再分析中…' : '分析中…';
  button.disabled = true;
  $('runAnalysisButton').disabled = true;
  $('rerunAnalysisButton').disabled = true;

  try {
    const key = analysisKey(context);
    state.analysisCache.delete(key);

    const body = {
      period_type: context.periodType,
      direction: state.direction,
      force,
    };
    if (state.selectedAccount === 'amazon') {
      body.account_group = 'amazon';
    } else {
      body.account_id = state.selectedAccount;
    }
    if (context.periodType === 'month') {
      body.month = context.period;
    } else {
      body.year = context.period;
    }

    let data;
    try {
      data = await apiWithErrorPayload('/api/analysis/run', {
        method: 'POST',
        body: JSON.stringify(body),
      });
    } catch (err) {
      data = err.payload || null;
      if (!data) {
        throw err;
      }
    }

    if (data.status === 'failed') {
      const msg = mapAnalysisFailureMessage(
        data.error_message || '分析に失敗しました。',
        data.error_code || ''
      );
      renderAnalysisPlaceholders(context);
      $('analysisStatus').textContent = msg;
      $('analysisResult').innerHTML = '<p class="analysis-empty">再分析の実行に失敗しました。</p>';
      return;
    }

    const normalized = {
      ...data,
      has_analysis: true,
    };
    state.analysisCache.set(key, normalized);
    showAnalysisData(context, normalized);
  } catch (err) {
    const code = err?.payload?.error_code || '';
    $('analysisStatus').textContent = `分析に失敗しました: ${mapAnalysisFailureMessage(err.message || err, code)}`;
    $('analysisResult').innerHTML = '<p class="analysis-empty">分析結果を表示できませんでした。</p>';
  } finally {
    button.textContent = originalLabel;
    button.disabled = false;
    $('runAnalysisButton').disabled = false;
    $('rerunAnalysisButton').disabled = false;
  }
}

function escapeHtml(value) {
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' };
  return String(value ?? '').replace(/[&<>\"]/g, (c) => map[c]);
}

async function syncNow() {
  const btn = $('syncButton');
  btn.textContent = 'Gmail同期中…';
  btn.disabled = true;
  try {
    const result = await api('/api/sync', { method: 'POST', body: '{}' });
    alert(`Gmail同期完了\n取得: ${result.fetched}\n新規: ${result.inserted}\n更新: ${result.updated}\nエラー: ${result.errors}`);
    state.analysisCache.clear();
    await loadAll();
  } catch (e) {
    alert(`Gmail同期に失敗しました: ${e.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Gmail同期';
  }
}

function changeMode(mode) {
  if (state.mode === mode) {
    return;
  }
  state.mode = mode;
  if (mode === 'month') {
    state.month = state.month || currentMonthLocal();
    state.year = state.month.slice(0, 4);
  } else {
    state.year = state.month.slice(0, 4);
  }
  normalizeViewTab();
  resetCategorySelection();
  state.analysisCache.clear();
  updateModeButtons();
  loadAll();
}

function changeDirection(direction) {
  state.direction = direction;
  resetCategorySelection();
  state.analysisCache.clear();
  updateDirectionButtons();
  loadAll();
}

function handleScrollTopVisibility() {
  const button = $('scrollTopButton');
  const shouldShow = window.scrollY > 460;
  button.classList.toggle('visible', shouldShow);
}

function scrollToTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

$('prevPeriod').addEventListener('click', () => shiftPeriod(-1));
$('nextPeriod').addEventListener('click', () => shiftPeriod(1));
$('latestPeriod').addEventListener('click', moveToLatest);
$('modeMonth').addEventListener('click', () => changeMode('month'));
$('modeYear').addEventListener('click', () => changeMode('year'));
$('expenseTab').addEventListener('click', () => changeDirection('expense'));
$('incomeTab').addEventListener('click', () => changeDirection('income'));
$('showSubcategories').addEventListener('change', (ev) => {
  state.showSubcategories = ev.target.checked;
  resetCategorySelection();
  state.analysisCache.clear();
  loadAll();
});
$('clearFilter').addEventListener('click', () => {
  resetCategorySelection();
  renderTransactions(state.transactions);
});
$('syncButton').addEventListener('click', syncNow);
$('editCategory').addEventListener('change', updateSubcategoryList);
$('editSubcategory').addEventListener('input', syncSubcategoryChipState);
$('saveEdit').addEventListener('click', saveEdit);
document.querySelector('#editDialog .dialog-cancel').addEventListener('click', () => $('editDialog').close());
$('viewTabCategory').addEventListener('click', () => setViewTab('category'));
$('viewTabAnalysis').addEventListener('click', () => setViewTab('analysis'));
$('viewFundMovement').addEventListener('click', async () => {
  const item = {
    category_id: FUND_MOVEMENT_CATEGORY_ID,
    category_name: '資金移動・チャージ',
    subcategory: null,
  };
  await selectCategory(item);
});
$('runAnalysisButton').addEventListener('click', () => runAnalysis(false));
$('rerunAnalysisButton').addEventListener('click', () => runAnalysis(true));
$('scrollTopButton').addEventListener('click', scrollToTop);
$('assetPrevPeriod').addEventListener('click', () => shiftAssetPeriod(-1));
$('assetNextPeriod').addEventListener('click', () => shiftAssetPeriod(1));
$('assetLatestPeriod').addEventListener('click', moveAssetLatest);
$('assetModeMonth').addEventListener('click', () => changeAssetViewMode('month'));
$('assetModeYear').addEventListener('click', () => changeAssetViewMode('year'));
$('assetRefreshPricesButton').addEventListener('click', refreshAssetPrices);
$('openAssetPurchaseDialog').addEventListener('click', openAssetPurchaseDialog);
$('saveAssetPurchase').addEventListener('click', saveAssetPurchase);
document.querySelector('#assetPurchaseDialog .dialog-cancel').addEventListener('click', () => $('assetPurchaseDialog').close());
document.querySelectorAll('#assetMetricTabs .asset-metric-tab').forEach((button) => {
  button.addEventListener('click', () => {
    state.asset.metric = button.dataset.metric || 'value';
    state.asset.chartPointIndex = null;
    document.querySelectorAll('#assetMetricTabs .asset-metric-tab').forEach((item) => {
      item.classList.toggle('active', item === button);
    });
    renderAssetChart();
  });
});
$('navBudget').addEventListener('click', () => setMainTab('budget'));
$('navAssets').addEventListener('click', () => setMainTab('assets'));
window.addEventListener('scroll', handleScrollTopVisibility, { passive: true });

updateModeButtons();
updateDirectionButtons();
renderViewTabs();
updateMainTabView();
handleScrollTopVisibility();
loadAll().catch((err) => {
  console.error(err);
  alert(`表示に失敗しました: ${err.message}`);
});

