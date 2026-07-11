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
    const lines = [
      'Gmail同期完了',
      `取得: ${result.fetched ?? 0}`,
      `新規: ${result.inserted ?? 0}`,
      `更新: ${result.updated ?? 0}`,
      `スキップ: ${result.skipped ?? 0}`,
      `エラー: ${result.errors ?? 0}`,
    ];
    const sourceResults = Array.isArray(result.sources) ? result.sources : [];
    if (sourceResults.length) {
      lines.push('', '[source別]');
      sourceResults.forEach((source) => {
        const sourceId = String(source.source_id || 'unknown');
        lines.push(
          `${sourceId}: 取得 ${source.fetched ?? 0} / 新規 ${source.inserted ?? 0} / 更新 ${source.updated ?? 0} / スキップ ${source.skipped ?? 0} / エラー ${source.errors ?? 0}`
        );
      });
    }
    alert(lines.join('\n'));
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
