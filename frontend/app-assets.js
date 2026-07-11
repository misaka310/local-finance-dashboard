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
    const row = (state.asset.yearly || []).find((r) => String(r.year) === year);
    if (row && row.is_ytd) {
      target.textContent = `${year}年（年初〜最新月）`;
    } else {
      target.textContent = `${year}年`;
    }
    return;
  }
  const [year, month] = state.asset.periodMonth.split('-').map(Number);
  target.textContent = `${year}年${month}月`;
}

function selectedAssetMonthly() {
  return (state.asset.monthly || []).find((row) => row.period_month === state.asset.periodMonth) || null;
}

function selectedAssetYear() {
  return (state.asset.yearly || []).find((row) => String(row.year) === String(state.asset.year || '')) || null;
}

function hasAssetData() {
  return Boolean(state.asset.summary && state.asset.summary.has_data);
}

function selectedAssetSummary() {
  if (state.asset.viewMode === 'year') {
    const row = selectedAssetYear();
    if (!row) {
      return null;
    }
    return {
      period_month: row.end_period_month,
      valuation_date: row.end_period_month ? `${row.end_period_month}-01` : '',
      current_value_yen: row.end_value_yen,
      previous_value_yen: row.start_value_yen,
      month_change_yen: row.total_change_yen,
      month_change_rate: row.total_change_rate,
      purchase_amount_yen: row.purchase_amount_yen,
      operation_change_yen: row.operation_change_yen,
      operation_change_rate: row.operation_change_rate,
      invested_amount_yen: null,
      profit_loss_yen: null,
      profit_loss_rate: null,
      holding_count: null,
      percent_available: row.percent_available,
      percent_unavailable_reason: row.percent_unavailable_reason,
      year: row.year,
      is_ytd: row.is_ytd,
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
  const isYear = state.asset.viewMode === 'year';
  const periodCaption = isYear ? (summary.is_ytd ? `${summary.year}年（年初〜最新月）` : `${summary.year}年`) : `評価日 ${escapeHtml(summary.valuation_date || '--')}`;
  const mascot = mascotImageHtml('cheer', 'たぬきマスコット', 'asset-total-mascot');
  el.innerHTML = `
    <article class="asset-card asset-card-total">
      <h3>${isYear ? '年次サマリー（評価額）' : '総資産（評価額）'}</h3>
      <div class="asset-card-main">${fmt.format(summary.current_value_yen || 0)}</div>

      <p class="asset-card-sub">
        総資産差（買い増し込み） ${totalChange === null || totalChange === undefined ? '--' : formatSignedYen(totalChange)}
        <span class="asset-card-sub-rate">前月比 ${totalChangeRate === null || totalChangeRate === undefined ? '--' : formatSignedPercent(totalChangeRate)}</span>
      </p>

      <p class="asset-card-note">${periodCaption}</p>
      <div class="asset-card-breakdown">
        <p><span>${isYear ? '年間買い増し額' : '買い増し額'}</span><strong>${fmt.format(summary.purchase_amount_yen || 0)}</strong></p>
        <p><span>運用増減（買い増し除外）</span><strong class="${valueToneClass(operation)}">${operation === null || operation === undefined ? '--' : formatSignedYen(operation)}</strong></p>
        <p><span>評価日</span><strong>${escapeHtml(summary.valuation_date || '--')}</strong></p>
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
  let compareSummary = '';
  if (metric === 'change') {
    compareSummary = `
      <div class="asset-chart-compare">
        <span class="${valueToneClass(changeValue)}">総資産差（買い増し込み）: ${escapeHtml(changeValue === null || changeValue === undefined ? '--' : formatSignedYen(changeValue))}</span>
        <span class="${valueToneClass(changeRate)}">前月比: ${escapeHtml(changeRate === null || changeRate === undefined ? '--' : formatSignedPercent(changeRate))}</span>
      </div>
    `;
  } else if (metric === 'purchase') {
    compareSummary = `
      <div class="asset-chart-compare">
        <span>買い増し額: ${escapeHtml(formatSignedYen(selectedRow.purchase_amount_yen || 0))}</span>
        <span class="${valueToneClass(changeValue)}">総資産差（買い増し込み）: ${escapeHtml(changeValue === null || changeValue === undefined ? '--' : formatSignedYen(changeValue))}</span>
        <span class="${valueToneClass(selectedRow.operation_change_yen)}">運用増減（買い増し除外）: ${escapeHtml(selectedRow.operation_change_yen === null || selectedRow.operation_change_yen === undefined ? '--' : formatSignedYen(selectedRow.operation_change_yen))}</span>
      </div>
    `;
  } else if (metric === 'operation') {
    compareSummary = `
      <div class="asset-chart-compare">
        <span class="${valueToneClass(selectedRow.operation_change_yen)}">運用増減（買い増し除外）: ${escapeHtml(selectedRow.operation_change_yen === null || selectedRow.operation_change_yen === undefined ? '--' : formatSignedYen(selectedRow.operation_change_yen))}</span>
        <span class="${valueToneClass(selectedRow.operation_change_rate)}">運用増減率: ${escapeHtml(selectedRow.operation_change_rate === null || selectedRow.operation_change_rate === undefined ? '--' : formatSignedPercent(selectedRow.operation_change_rate))}</span>
      </div>
    `;
  } else {
    compareSummary = `
      <div class="asset-chart-compare">
        <span>評価額: ${escapeHtml(fmt.format(selectedRow.current_value_yen || 0))}</span>
        <span>${previousLabel}: ${escapeHtml(previousValue === null || previousValue === undefined ? '--' : fmt.format(previousValue))}</span>
        <span class="${valueToneClass(changeValue)}">総資産差（買い増し込み）: ${escapeHtml(changeValue === null || changeValue === undefined ? '--' : formatSignedYen(changeValue))}</span>
        <span class="${valueToneClass(changeRate)}">前月比: ${escapeHtml(changeRate === null || changeRate === undefined ? '--' : formatSignedPercent(changeRate))}</span>
      </div>
    `;
  }

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
  const isYear = state.asset.viewMode === 'year';
  const rows = [
    [isYear ? '最新評価額' : '総資産', fmt.format(summary.current_value_yen || 0)],
    ['総資産差（買い増し込み）', summary.month_change_yen === null ? '--' : formatSignedYen(summary.month_change_yen)],
    [isYear ? '運用増減率' : '前月比', (isYear ? summary.operation_change_rate : summary.month_change_rate) === null ? '--' : formatSignedPercent(isYear ? summary.operation_change_rate : summary.month_change_rate)],
    ['買い増し額', fmt.format(summary.purchase_amount_yen || 0)],
    ['運用増減（買い増し除外）', summary.operation_change_yen === null ? '--' : formatSignedYen(summary.operation_change_yen)],
    [isYear ? '年初評価額' : '先月評価額', summary.previous_value_yen === null || summary.previous_value_yen === undefined ? '--' : fmt.format(summary.previous_value_yen)],
    ['評価損益', summary.profit_loss_yen === null || summary.profit_loss_yen === undefined ? '--' : formatSignedYen(summary.profit_loss_yen)],
    ['損益率', summary.profit_loss_rate === null || summary.profit_loss_rate === undefined ? '--' : formatSignedPercent(summary.profit_loss_rate)],
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
  const titleNode = $('assetPerformanceTitle');
  if (titleNode) {
    titleNode.textContent = '年次成績';
  }
  const list = state.asset.yearly || [];
  if (!list.length) {
    el.innerHTML = '<p class="notice">年次成績のデータがありません。</p>';
    return;
  }
  const rows = list.slice(0, 4);
  el.innerHTML = rows
    .map((row) => {
      const title = row.is_ytd ? `${row.year}年（年初〜最新月）` : `${row.year}年`;
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
          <p>年初評価額 ${fmt.format(row.start_value_yen || 0)}</p>
          <p>期末評価額 ${fmt.format(row.end_value_yen || 0)}</p>
          <p>総資産差（買い増し込み） ${formatSignedYen(row.total_change_yen || 0)}</p>
          <p>年間買い増し額 ${fmt.format(row.purchase_amount_yen || 0)}</p>
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
            <p class="${valueToneClass(monthChange)}">総資産差（買い増し込み） ${monthChange === null || monthChange === undefined ? '--' : formatSignedYen(monthChange)}</p>
            <p class="${valueToneClass(monthRate)}">先月比 ${monthRate === null || monthRate === undefined ? '--' : formatSignedPercent(monthRate)}</p>
            <p>買い増し額 ${fmt.format(purchase)}</p>
            <p class="${valueToneClass(operation)}">運用増減（買い増し除外） ${operation === null || operation === undefined ? '--' : formatSignedYen(operation)}</p>
          </div>
          <div class="asset-holding-grid">
            <p>先月評価額 <strong>${row.previous_value_yen === null || row.previous_value_yen === undefined ? '--' : fmt.format(row.previous_value_yen)}</strong></p>
            <p>取得金額 <strong>${fmt.format(row.invested_amount_yen || 0)}</strong></p>
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

function setAssetRefreshStatus(html, tone = 'neutral') {
  const node = $('assetRefreshStatus');
  if (!node) {
    return;
  }
  node.hidden = !html;
  node.innerHTML = html || '';
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
    const totalChecked = (nav.fetched || 0) + (nav.skipped || 0);
    const changed = (nav.inserted || 0) + (nav.updated || 0);
    const detailText = changed > 0 ? `${totalChecked}件確認 / ${changed}件変更` : `${totalChecked}件確認 / 変更なし`;
    const messageHtml = `基準価額を更新しました <span style="font-size: 0.85em; opacity: 0.8;">(${detailText})</span>`;
    setAssetRefreshStatus(messageHtml, nav.errors ? 'negative' : 'positive');
    await loadAssetAll();
    if (nav.errors) {
      const details = (nav.error_details || []).map((item) => `${item.fund_name}: ${item.error}`).join('\\n');
      alert(`一部失敗しました\\n${details || '詳細不明'}`);
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
  if (mode === 'year') {
    const currentYear = yearFromMonth(state.asset.periodMonth);
    state.asset.year = currentYear;
    const fallbackMonth = latestMonthInYear(currentYear);
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
