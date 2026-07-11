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
    const rawDescription = String(tx.raw_description || '').trim();
    const isAmazonMail = tx.source_id === 'amazon-order';
    const descriptionHtml = isAmazonMail && rawDescription
      ? `<div class="tx-description">${escapeHtml(rawDescription)}</div>`
      : '';
    item.innerHTML = `
      <div class="tx-date"><small>${month}月</small>${day}</div>
      <div class="tx-main">
        <div class="tx-merchant">
          <span class="tx-icon" aria-hidden="true">${escapeHtml(icon)}</span>
          <span>${escapeHtml(tx.merchant)}</span>
        </div>
        ${descriptionHtml}
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
