(() => {
  const payload = JSON.parse(document.getElementById("mfblue-data").textContent);

  const state = {
    mainTab: "budget",
    mode: "month",
    month: payload.period_options?.latest_month || currentMonthLocal(),
    year: payload.period_options?.latest_year || String(new Date().getFullYear()),
    direction: "expense",
    showSubcategories: false,
    selectedAccount: "all",
    selected: null,
    filteredTransactions: null,
    categories: payload.categories || [],
    transactions: payload.transactions || [],
    editing: null,
    periodBounds: {
      min_month: payload.period_options?.min_month || payload.period_options?.latest_month || currentMonthLocal(),
      max_month: payload.period_options?.max_month || payload.period_options?.latest_month || currentMonthLocal(),
      min_year: payload.period_options?.min_year || payload.period_options?.latest_year || String(new Date().getFullYear()),
      max_year: payload.period_options?.max_year || payload.period_options?.latest_year || String(new Date().getFullYear()),
    },
    viewTab: "category",
    analysisCache: new Map(),
    asset: {
      viewMode: "month",
      periodMonth: payload.assets?.summary?.period_month || payload.assets?.bounds?.max_month || currentMonthLocal(),
      year: "",
      summary: payload.assets?.summary || null,
      bounds: payload.assets?.bounds || null,
      monthly: payload.assets?.monthly || [],
      axis: payload.assets?.axis || {},
      yearly: payload.assets?.yearly || [],
      products: payload.assets?.products || [],
      holdingsByMonth: payload.assets?.holdings_by_month || {},
      metric: "value",
      chartPointIndex: null,
    },
  };

  const colors = [
    "#1565c0", "#1e88e5", "#42a5f5", "#64b5f6", "#90caf9",
    "#0d47a1", "#1976d2", "#4fc3f7", "#29b6f6", "#0288d1",
    "#26c6da", "#00acc1", "#5c6bc0", "#7e57c2", "#3949ab", "#607d8b",
  ];

  state.asset.year = String((state.asset.yearly[0] && state.asset.yearly[0].year) || yearFromMonth(state.asset.periodMonth) || "");

  const categoryIcons = {
    food: "🍽",
    daily: "🧴",
    transport: "🚃",
    hobby: "🎮",
    beauty: "💄",
    communication: "📱",
    utilities: "💡",
    health: "🏥",
    education: "📚",
    social: "🎁",
    housing: "🏠",
    insurance: "🛡",
    tax: "📄",
    uncategorized: "❔",
    cash_card: "💳",
    special: "💠",
    car: "🚗",
    fund_movement: "🔁",
  };

  const accountLabels = {
    "paypay-card": "PayPayカード",
    amazon: "Amazon",
    "group:amazon": "Amazon",
    "amazon-order-history": "Amazon",
    "amazon-order": "Amazon",
  };

  const viewTabs = {
    category: "viewTabCategory",
    analysis: "viewTabAnalysis",
  };

  const FUND_MOVEMENT_CATEGORY_ID = "fund_movement";

  const fmt = new Intl.NumberFormat("ja-JP", {
    style: "currency",
    currency: "JPY",
    maximumFractionDigits: 0,
  });

  const readonlyMessages = {
    save: "読み取り専用デモのため、編集は保存されません。PC版アプリでカテゴリを編集してください。",
    sync: "読み取り専用デモのため、同期はできません。PC版でGmail同期を実行してください。",
    analysis: "読み取り専用デモのため、分析は実行できません。PC版でCodex App Server分析を実行してください。",
    assetPurchase: "読み取り専用デモのため、買い増しは保存されません。PC版で登録してください。",
    assetRefresh: "読み取り専用デモのため、基準価額更新は実行されません。PC版アプリで更新してください。",
  };

  function $(id) {
    return document.getElementById(id);
  }

  function isFundMovementCategoryId(categoryId) {
    return String(categoryId || "") === FUND_MOVEMENT_CATEGORY_ID;
  }

  function mascotImageHtml(assetName, altText, className = "") {
    const asset = (payload.mascots || {})[assetName];
    if (!asset) {
      return "";
    }
    return `<img src="${asset.webp}" data-fallback="${asset.png}" alt="${escapeHtml(altText)}" class="${className}" loading="lazy" decoding="async" />`;
  }

  function bindMascotFallback(root) {
    const scope = root || document;
    scope.querySelectorAll("img[data-fallback]").forEach((img) => {
      if (img.dataset.fallbackBound === "1") {
        return;
      }
      img.dataset.fallbackBound = "1";
      img.addEventListener("error", () => {
        const fallback = img.dataset.fallback || "";
        if (!fallback || img.dataset.fallbackTried === "1") {
          img.hidden = true;
          return;
        }
        img.dataset.fallbackTried = "1";
        img.src = fallback;
      });
    });
  }

  function currentMonthLocal() {
    const now = new Date();
    const y = now.getFullYear();
    const m = now.getMonth() + 1;
    return `${y.toString().padStart(4, "0")}-${m.toString().padStart(2, "0")}`;
  }

  function normalizeYear(value) {
    return String(Number(value || 0)).padStart(4, "0");
  }

  function shiftMonthValue(month, delta) {
    const [y, m] = month.split("-").map(Number);
    const total = y * 12 + (m - 1) + delta;
    const nextYear = Math.floor(total / 12);
    const nextMonth = (total % 12) + 1;
    return `${nextYear.toString().padStart(4, "0")}-${nextMonth.toString().padStart(2, "0")}`;
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
      return "--";
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
      return "--";
    }
    const sign = n > 0 ? "+" : n < 0 ? "-" : "±";
    return `${sign}${fmt.format(Math.abs(n))}`;
  }

  function formatSignedPercent(value) {
    if (value === null || value === undefined) {
      return "--";
    }
    const n = Number(value || 0);
    const sign = n > 0 ? "+" : n < 0 ? "-" : "±";
    return `${sign}${Math.abs(n).toFixed(2)}%`;
  }

  function valueToneClass(value) {
    if (value === null || value === undefined) return "";
    const n = Number(value);
    if (n > 0) return "tone-positive";
    if (n < 0) return "tone-negative";
    return "tone-neutral";
  }

  function formatPeriodLabel() {
    if (state.mode === "year") {
      return `${state.year}年`;
    }
    const [year, month] = state.month.split("-").map(Number);
    return `${year}年${month}月`;
  }

  function updateModeButtons() {
    const isMonth = state.mode === "month";
    $("modeMonth").classList.toggle("active", isMonth);
    $("modeYear").classList.toggle("active", !isMonth);
  }

  function updateDirectionButtons() {
    const expense = state.direction === "expense";
    $("expenseTab").classList.toggle("active", expense);
    $("incomeTab").classList.toggle("active", !expense);
    $("categoryHeader").textContent = expense ? "カテゴリ別支出" : "カテゴリ別収入";
  }

  function currentBounds() {
    return state.periodBounds;
  }

  function clampPeriodWithinBounds() {
    const bounds = currentBounds();
    if (!bounds) {
      return false;
    }

    if (state.mode === "month") {
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
    if (state.mode === "year") {
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
    if (state.mode === "year") {
      return compareYear(state.year, bounds.max_year) === 0;
    }
    return compareMonth(state.month, bounds.max_month) === 0;
  }

  function updatePeriodButtons() {
    $("prevPeriod").disabled = !canShift(-1);
    $("nextPeriod").disabled = !canShift(1);
    $("latestPeriod").disabled = isAtLatest();
  }

  function shiftPeriod(delta) {
    if (!canShift(delta)) {
      return;
    }
    if (state.mode === "year") {
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
    if (state.mode === "year") {
      state.year = bounds.max_year;
    } else {
      state.month = bounds.max_month;
      state.year = state.month.slice(0, 4);
    }
    state.selected = null;
    loadAll();
  }

  function accountFilterOptions() {
    return (payload.account_filters || []).slice();
  }

  function accountFilterDef() {
    return accountFilterOptions().find((opt) => opt.id === state.selectedAccount) || accountFilterOptions()[0] || { id: "all", label: "すべて", account_ids: null, analysis_account_ids: ["all"] };
  }

  function selectedAccountLabel() {
    if (state.selectedAccount === "all") {
      return "すべて";
    }
    return accountFilterDef().label || accountLabels[state.selectedAccount] || state.selectedAccount;
  }

  function accountMatches(tx) {
    const filterDef = accountFilterDef();
    if (!filterDef || !filterDef.account_ids) {
      return true;
    }
    return filterDef.account_ids.includes(tx.account_id);
  }

  function periodMatches(tx) {
    return state.mode === "year" ? tx.year === state.year : tx.month === state.month;
  }

  function resetCategorySelection() {
    state.selected = null;
    state.filteredTransactions = null;
    $("transactionTitle").textContent = "明細";
    $("clearFilter").hidden = true;
  }

  function scopedRows() {
    return (state.transactions || []).filter((tx) => periodMatches(tx) && accountMatches(tx));
  }

  function rowsForDirection(rows) {
    return rows.filter((tx) => tx.direction === state.direction);
  }

  function buildSummary(rows) {
    let incomeTotal = 0;
    let rawExpenseTotal = 0;
    let fundMovementTotal = 0;
    let fundMovementCount = 0;

    rows.forEach((tx) => {
      const amount = Number(tx.amount_yen || 0);
      if (tx.direction === "income") {
        incomeTotal += amount;
      } else {
        rawExpenseTotal += amount;
        if (tx.is_fund_movement || isFundMovementCategoryId(tx.category_id)) {
          fundMovementTotal += amount;
          fundMovementCount += 1;
        }
      }
    });

    const expenseTotal = Math.max(0, rawExpenseTotal - fundMovementTotal);
    const selectedTotal = state.direction === "expense" ? expenseTotal : incomeTotal;

    const categoriesRaw = rowsForDirection(rows).filter((tx) => !(state.direction === "expense" && (tx.is_fund_movement || isFundMovementCategoryId(tx.category_id))));

    const keyFor = (tx) => {
      if (state.showSubcategories) {
        return `${tx.category_id}::${tx.subcategory || "未分類"}`;
      }
      return `${tx.category_id}::`;
    };

    const grouped = new Map();
    categoriesRaw.forEach((tx) => {
      const key = keyFor(tx);
      const row = grouped.get(key) || {
        category_id: tx.category_id,
        category_name: tx.category_name,
        subcategory: state.showSubcategories ? (tx.subcategory || "未分類") : null,
        total: 0,
        count: 0,
      };
      row.total += Number(tx.amount_yen || 0);
      row.count += 1;
      grouped.set(key, row);
    });

    const categories = [...grouped.values()]
      .map((row) => ({
        ...row,
        percent: selectedTotal > 0 ? (row.total / selectedTotal) * 100 : 0,
      }))
      .sort((a, b) => (b.total - a.total) || String(a.category_name).localeCompare(String(b.category_name)));

    return {
      income_total: incomeTotal,
      expense_total: expenseTotal,
      expense_total_including_fund_movement: rawExpenseTotal,
      fund_movement_total: fundMovementTotal,
      fund_movement_count: fundMovementCount,
      balance: incomeTotal - expenseTotal,
      categories,
    };
  }

  function renderAccountFilters() {
    const el = $("accountFilters");
    if (!el) {
      return;
    }
    const options = accountFilterOptions();
    if (!options.find((opt) => opt.id === state.selectedAccount)) {
      state.selectedAccount = "all";
    }

    el.innerHTML = "";
    options.forEach((opt) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "filter-chip";
      button.classList.toggle("active", opt.id === state.selectedAccount);
      button.textContent = opt.label;
      button.addEventListener("click", () => {
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

  function renderSummary(summary) {
    $("incomeTotal").textContent = fmt.format(summary.income_total || 0);
    $("expenseTotal").textContent = fmt.format(summary.expense_total || 0);
    $("balanceTotal").textContent = fmt.format(summary.balance || 0);

    const sourceList = summary.categories || [];
    const list = state.direction === "expense"
      ? sourceList.filter((item) => !isFundMovementCategoryId(item.category_id))
      : sourceList;
    const targetTotal = list.reduce((acc, item) => acc + Number(item.total || 0), 0);
    const hasData = targetTotal > 0 && list.length > 0;
    $("emptyNotice").hidden = hasData;
    $("emptyNoticeText").textContent =
      state.direction === "expense" ? "表示する支出明細がありません。" : "表示する収入明細がありません。";

    renderDonut(list, targetTotal);
    renderDonutLegend(list, targetTotal);
    renderCategoryList(list, targetTotal);
    renderFundMovementHint(summary);
  }

  function renderFundMovementHint(summary) {
    const section = $("fundMovementHint");
    const total = Number(summary.fund_movement_total || 0);
    const count = Number(summary.fund_movement_count || 0);
    const shouldDisplay = state.direction === "expense" && total > 0;
    section.dataset.hasFundMovement = shouldDisplay ? "1" : "0";
    if (shouldDisplay) {
      $("fundMovementTotal").textContent = `${fmt.format(total)} / ${count}件`;
    }
    applyFundMovementVisibility();
  }

  function applyFundMovementVisibility() {
    const section = $("fundMovementHint");
    const hasFundMovement = section.dataset.hasFundMovement === "1";
    section.hidden = !(hasFundMovement && state.viewTab === "category" && state.direction === "expense");
  }

  function renderDonut(list, total) {
    const donut = $("donut");
    if (!total || list.length === 0) {
      donut.style.background = "conic-gradient(#e5e7eb 0deg 360deg)";
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
    donut.style.background = `conic-gradient(${stops.join(",")})`;
  }

  function renderDonutLegend(list, total) {
    const el = $("donutLegend");
    el.innerHTML = "";

    if (!total || list.length === 0) {
      el.hidden = true;
      return;
    }

    list.slice(0, 5).forEach((item, idx) => {
      const row = document.createElement("div");
      row.className = "donut-legend-item";
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
    const el = $("categoryList");
    el.innerHTML = "";
    if (!list.length) {
      return;
    }

    list.forEach((item, idx) => {
      const button = document.createElement("button");
      button.className = "category-item";
      const label = state.showSubcategories && item.subcategory
        ? `${item.category_name} / ${item.subcategory}`
        : item.category_name;
      const countText = `${item.count}件の明細`;
      const percent = item.percent ?? (total > 0 ? (item.total / total * 100) : 0);
      const icon = categoryIcons[item.category_id] || "🧾";
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
      button.addEventListener("click", () => selectCategory(item));
      el.appendChild(button);
    });
  }

  function queryTransactions({ direction = null, category_id = null, subcategory = null } = {}) {
    let rows = scopedRows();
    if (direction) {
      rows = rows.filter((tx) => tx.direction === direction);
    }
    if (category_id) {
      rows = rows.filter((tx) => tx.category_id === category_id);
    }
    if (subcategory) {
      rows = rows.filter((tx) => (tx.subcategory || "未分類") === subcategory);
    }
    return rows.slice().sort((a, b) => String(b.occurred_at).localeCompare(String(a.occurred_at)) || Number(b.id) - Number(a.id));
  }

  function selectCategory(item) {
    state.selected = item;
    const txs = queryTransactions({
      direction: state.direction,
      category_id: item.category_id,
      subcategory: state.showSubcategories && item.subcategory ? item.subcategory : null,
    });
    const baseLabel = isFundMovementCategoryId(item.category_id)
      ? "資金移動・チャージ"
      : item.category_name;
    const label = state.showSubcategories && item.subcategory
      ? `${baseLabel} / ${item.subcategory}`
      : baseLabel;
    $("transactionTitle").textContent = `${label}の明細`;
    $("clearFilter").hidden = false;
    state.filteredTransactions = txs;
    renderTransactions(txs);
    if (state.viewTab !== "category") {
      setViewTab("category");
    }
  }

  function renderTransactions(txs) {
    const el = $("transactions");
    el.innerHTML = "";
    if (!txs.length) {
      const msg = state.direction === "expense" ? "表示する支出明細がありません。" : "表示する収入明細がありません。";
      el.innerHTML = `<p class="notice">${escapeHtml(msg)}</p>`;
      return;
    }

    txs.forEach((tx) => {
      const day = Number(tx.occurred_at.slice(8, 10));
      const month = Number(tx.occurred_at.slice(5, 7));
      const item = document.createElement("article");
      item.className = "transaction";
      const sign = tx.direction === "expense" ? "-" : "+";
      const amountClass = tx.direction === "expense" ? "tx-amount expense" : "tx-amount income";
      const icon = categoryIcons[tx.category_id] || "🧾";
      const normalizedAccountName = accountLabel(tx.account_id, tx.account_name);
      const isFundMovement = Boolean(tx.is_fund_movement) || isFundMovementCategoryId(tx.category_id);
      const fundMovementBadge = isFundMovement
        ? '<span class="tx-badge transfer">資金移動</span>'
        : "";
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
      item.querySelector(".tx-edit").addEventListener("click", () => openEdit(tx));
      el.appendChild(item);
    });
  }

  function populateEditOptions() {
    const sel = $("editCategory");
    sel.innerHTML = "";
    state.categories.forEach((cat) => {
      const opt = document.createElement("option");
      opt.value = cat.id;
      opt.textContent = cat.name;
      sel.appendChild(opt);
    });
    updateSubcategoryList();
  }

  function updateSubcategoryList() {
    const cat = state.categories.find((c) => c.id === $("editCategory").value);
    const dl = $("subcategoryList");
    const chips = $("subcategoryChips");
    const current = $("editSubcategory").value || "未分類";
    const unique = new Set(["未分類", ...(cat?.subcategories || [])]);
    dl.innerHTML = "";
    chips.innerHTML = "";
    [...unique].forEach((sub) => {
      const opt = document.createElement("option");
      opt.value = sub;
      dl.appendChild(opt);

      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "subcategory-chip";
      chip.textContent = sub;
      chip.classList.toggle("active", sub === current);
      chip.addEventListener("click", () => {
        $("editSubcategory").value = sub;
        syncSubcategoryChipState();
      });
      chips.appendChild(chip);
    });
    syncSubcategoryChipState();
  }

  function syncSubcategoryChipState() {
    const selected = ($("editSubcategory").value || "").trim() || "未分類";
    document.querySelectorAll("#subcategoryChips .subcategory-chip").forEach((chip) => {
      chip.classList.toggle("active", chip.textContent === selected);
    });
  }

  function openEdit(tx) {
    state.editing = tx;
    const mascot = $("editDialogMascot");
    if (mascot) {
      mascot.innerHTML = mascotImageHtml("icon", "たぬきアイコン", "analysis-mascot analysis-mascot-dialog");
      bindMascotFallback(mascot);
    }
    $("editMerchant").textContent = `${tx.merchant} / ${fmt.format(tx.amount_yen)}`;
    $("editCategory").value = tx.category_id;
    $("editSubcategory").value = tx.subcategory || "未分類";
    $("learnRule").checked = true;
    $("applyPastMerchant").checked = false;
    updateSubcategoryList();
    syncSubcategoryChipState();
    $("editDialog").showModal();
  }

  function applyLocalCategoryChange() {
    if (!state.editing) {
      return;
    }
    const categoryId = $("editCategory").value;
    const subcategory = ($("editSubcategory").value || "未分類").trim() || "未分類";
    const categoryDef = state.categories.find((cat) => cat.id === categoryId);
    const categoryName = categoryDef?.name || categoryId;
    const applyPast = $("applyPastMerchant").checked;

    state.transactions = state.transactions.map((tx) => {
      const target = Number(tx.id) === Number(state.editing.id) || (applyPast && tx.merchant === state.editing.merchant);
      if (!target) {
        return tx;
      }
      const isFund = categoryId === FUND_MOVEMENT_CATEGORY_ID;
      return {
        ...tx,
        category_id: categoryId,
        category_name: categoryName,
        subcategory,
        is_fund_movement: isFund,
      };
    });
  }

  function saveEdit(ev) {
    ev.preventDefault();
    if (!state.editing) {
      return;
    }

    applyLocalCategoryChange();

    $("editDialog").close();
    state.editing = null;
    state.analysisCache.clear();
    alert(readonlyMessages.save);
    loadAll();
  }

  function analysisContextFromState() {
    if (state.mode === "year") {
      const year = state.year || state.month.slice(0, 4);
      return { periodType: "year", period: year, title: "年間分析" };
    }
    return { periodType: "month", period: state.month, title: "月次分析" };
  }

  function analysisKey(context) {
    return [context.periodType, context.period, state.selectedAccount, state.direction].join(":");
  }

  function analysisTabLabelForMode(mode = state.mode) {
    return mode === "year" ? "年間分析" : "月次分析";
  }

  function normalizeViewTab() {
    if (state.viewTab !== "category" && state.viewTab !== "analysis") {
      state.viewTab = "category";
    }
  }

  function renderViewTabs() {
    $("viewTabAnalysis").textContent = analysisTabLabelForMode();
    Object.entries(viewTabs).forEach(([name, id]) => {
      $(id).classList.toggle("active", state.viewTab === name);
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
    const showAnalysis = state.viewTab === "analysis";
    const txHeader = document.querySelector(".transactions-header");

    if (!showAnalysis) {
      $("categoryList").hidden = false;
      $("analysisPanel").hidden = true;
      $("transactions").hidden = false;
      applyFundMovementVisibility();
      if (txHeader) {
        txHeader.hidden = false;
      }
      $("transactionTitle").textContent = state.selected
        ? (state.showSubcategories && state.selected.subcategory
            ? `${state.selected.category_name} / ${state.selected.subcategory}の明細`
            : `${state.selected.category_name}の明細`)
        : "明細";
      $("clearFilter").hidden = !state.selected;
      const txs = state.selected && state.filteredTransactions ? state.filteredTransactions : queryTransactions({ direction: state.direction });
      renderTransactions(txs);
      return;
    }

    $("categoryList").hidden = true;
    applyFundMovementVisibility();
    if (txHeader) {
      txHeader.hidden = true;
    }
    $("transactions").hidden = true;
    $("analysisPanel").hidden = false;
    $("clearFilter").hidden = true;
    const context = analysisContextFromState();
    renderAnalysisPlaceholders(context);
    loadAnalysis(context);
  }

  function renderAnalysisPlaceholders(context) {
    const account = selectedAccountLabel();
    const directionLabel = state.direction === "expense" ? "表示する支出明細がありません。" : "表示する収入明細がありません。";
    const periodLabel = context.periodType === "month" ? context.period : `${context.period}年`;
    const heroIntro = context.periodType === "month"
      ? "今月の家計、ちょっと見てあげるね。"
      : "今年の家計、流れを見ていこう。";

    $("analysisHero").innerHTML = `
      <div class="analysis-character">
        ${mascotImageHtml("cheer", "たぬきマスコット", "analysis-mascot analysis-mascot-header")}
        <div class="analysis-character-copy">
          <p class="analysis-character-line">${heroIntro}</p>
          <p class="analysis-character-sub">数字だけじゃなく、見るべきところをしぼって出すよ。</p>
        </div>
      </div>
    `;
    $("analysisTarget").textContent = `対象: ${periodLabel} / ${account} / ${directionLabel}`;
    $("runAnalysisButton").textContent = context.periodType === "month" ? "分析する" : "年間分析する";
    $("rerunAnalysisButton").textContent = "再分析";
    bindMascotFallback($("analysisHero"));
  }

  function parseAnalysisSections(text) {
    const normalized = String(text || "").replace(/\r\n/g, "\n");
    const lines = normalized.split("\n");
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
    return [{ title: "コメント", lines: normalized.split("\n").map((line) => line.trim()).filter(Boolean) }];
  }

  function renderAnalysisSectionBody(lines) {
    const clean = lines.map((line) => line.trim()).filter(Boolean);
    if (!clean.length) {
      return '<p class="analysis-line">（コメントなし）</p>';
    }
    const bulletLines = clean.filter((line) => /^[-・●]\s*/.test(line));
    if (bulletLines.length >= Math.min(2, clean.length)) {
      const items = clean
        .map((line) => line.replace(/^[-・●]\s*/, "").trim())
        .filter(Boolean)
        .map((line) => `<li>${escapeHtml(line)}</li>`)
        .join("");
      return `<ul class="analysis-list">${items}</ul>`;
    }
    return clean.map((line) => `<p class="analysis-line">${escapeHtml(line)}</p>`).join("");
  }

  function renderAnalysisResultCard(text, stale = false) {
    const sections = parseAnalysisSections(text);
    const cards = sections.map((section, idx) => {
      const body = renderAnalysisSectionBody(section.lines);
      const classNames = ["analysis-section"];
      if (idx === 0 || section.title === "今月の結論") {
        classNames.push("hero");
      }
      if (section.title === "見るべき支出") {
        classNames.push("focus");
      }
      if (section.title === "次にやること") {
        classNames.push("next-action");
      }
      return `
        <section class="${classNames.join(" ")}">
          <h4>${escapeHtml(section.title)}</h4>
          ${body}
        </section>
      `;
    }).join("");
    const staleBadge = stale
      ? `
        <section class="analysis-stale-note">
          ${mascotImageHtml("stale", "前回分析のお知らせ", "analysis-mascot analysis-mascot-stale")}
          <p>前回の分析を表示中。分類や明細が変わってるから、必要なら再分析してね。</p>
        </section>
      `
      : "";

    $("analysisResult").innerHTML = `
      <div class="analysis-character">
        ${mascotImageHtml("cheer", "分析コメントのたぬき", "analysis-mascot")}
        <div class="analysis-character-copy">
          <p class="analysis-character-line">見どころだけ、ぎゅっとまとめたよ。</p>
        </div>
      </div>
      ${staleBadge}
      ${cards}
    `;
    bindMascotFallback($("analysisResult"));
  }

  function showAnalysisData(context, data) {
    const shortHash = data.input_hash ? String(data.input_hash).slice(0, 12) : "";
    if (data.has_analysis) {
      if (data.stale) {
        $("analysisStatus").textContent = "前回分析を表示中です。分類や明細が変更されています。必要なら再分析してください。";
      } else {
        $("analysisStatus").textContent = `分析済み${shortHash ? `（input_hash: ${shortHash}...）` : ""}`;
      }
      renderAnalysisResultCard(data.result_text || "分析結果テキストがありません。", Boolean(data.stale));
    } else {
      $("analysisStatus").textContent = "まだ分析されていません。";
      $("analysisResult").innerHTML = `
        <section class="analysis-empty">
          ${mascotImageHtml("thinking", "分析待ちのたぬき", "analysis-mascot analysis-mascot-empty")}
          <div>
            <p class="analysis-character-line">まだ分析してないよ。</p>
            <p class="analysis-empty-sub">PC版ならこの条件で分析できるよ。</p>
          </div>
        </section>
      `;
      bindMascotFallback($("analysisResult"));
    }
    $("runAnalysisButton").disabled = false;
    $("rerunAnalysisButton").disabled = false;
    renderAnalysisPlaceholders(context);
  }

  function loadAnalysis(context) {
    const key = analysisKey(context);
    if (state.analysisCache.has(key)) {
      showAnalysisData(context, state.analysisCache.get(key));
      return;
    }

    $("analysisStatus").textContent = "保存済み分析を確認中...";
    $("analysisResult").innerHTML = "";
    $("runAnalysisButton").disabled = true;
    $("rerunAnalysisButton").disabled = true;

    const accountIds = accountFilterDef().analysis_account_ids || ["all"];
    const row = (payload.analysis_runs || []).find((item) =>
      item.period_type === context.periodType
      && item.period === context.period
      && item.direction === state.direction
      && accountIds.includes(item.account_id)
    );

    const data = row
      ? {
          has_analysis: true,
          stale: Boolean(row.stale),
          result_text: row.result_text || (row.result_json ? JSON.stringify(row.result_json, null, 2) : ""),
          input_hash: row.input_hash || "",
        }
      : {
          has_analysis: false,
          stale: false,
          result_text: "",
          input_hash: "",
        };

    state.analysisCache.set(key, data);
    showAnalysisData(context, data);
  }

  function runAnalysis() {
    alert(readonlyMessages.analysis);
  }

  function accountLabel(accountId, fallbackName) {
    return accountLabels[accountId] || fallbackName || accountId;
  }

  function escapeHtml(value) {
    const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" };
    return String(value ?? "").replace(/[&<>\\"]/g, (c) => map[c]);
  }

  function syncNow() {
    alert(readonlyMessages.sync);
  }

  function changeMode(mode) {
    if (state.mode === mode) {
      return;
    }
    state.mode = mode;
    if (mode === "month") {
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
    const button = $("scrollTopButton");
    const shouldShow = window.scrollY > 460;
    button.classList.toggle("visible", shouldShow);
  }

  function scrollToTop() {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function loadAll() {
    $("periodLabel").textContent = formatPeriodLabel();
    clampPeriodWithinBounds();
    $("periodLabel").textContent = formatPeriodLabel();
    updatePeriodButtons();

    renderAccountFilters();

    const rows = scopedRows();
    const summary = buildSummary(rows);
    renderSummary(summary);

    populateEditOptions();
    updateViewContents();
  }

  function assetCurrentBounds() {
    return state.asset.bounds;
  }

  function assetYears() {
    return (state.asset.yearly || []).map((row) => String(row.year));
  }

  function latestMonthInYear(year) {
    const rows = (state.asset.monthly || []).filter((row) => yearFromMonth(row.period_month) === String(year || ""));
    return rows.length ? String(rows[rows.length - 1].period_month) : null;
  }

  function assetCanShift(delta) {
    if (state.asset.viewMode === "year") {
      const years = assetYears();
      const idx = years.findIndex((item) => item === String(state.asset.year || ""));
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
    if (state.asset.viewMode === "year") {
      const years = assetYears();
      if (!years.length) {
        return true;
      }
      return String(state.asset.year || "") === years[0];
    }
    const bounds = assetCurrentBounds();
    if (!bounds) {
      return false;
    }
    return compareMonth(state.asset.periodMonth, bounds.max_month) === 0;
  }

  function updateAssetPeriodLabel() {
    if (state.asset.viewMode === "year") {
      const year = String(state.asset.year || "");
      const row = (state.asset.yearly || []).find((r) => String(r.year) === year);
      if (row && row.is_ytd) {
        $("assetPeriodLabel").textContent = `${year}年（年初〜最新月）`;
      } else {
        $("assetPeriodLabel").textContent = `${year}年`;
      }
      return;
    }
    const [year, month] = state.asset.periodMonth.split("-").map(Number);
    $("assetPeriodLabel").textContent = `${year}年${month}月`;
  }

  function updateAssetPeriodButtons() {
    $("assetPrevPeriod").disabled = !assetCanShift(-1);
    $("assetNextPeriod").disabled = !assetCanShift(1);
    $("assetLatestPeriod").disabled = assetIsAtLatest();
  }

  function hasAssetData() {
    return Boolean(state.asset.summary && state.asset.summary.has_data);
  }

  function currentAssetSummary() {
    if (state.asset.viewMode === "year") {
      const row = (state.asset.yearly || []).find((r) => String(r.year) === String(state.asset.year || ""));
      if (!row) {
        return state.asset.summary || null;
      }
      return {
        period_month: row.end_period_month,
        current_value_yen: row.end_value_yen,
        previous_value_yen: row.start_value_yen,
        month_change_yen: row.total_change_yen,
        month_change_rate: row.total_change_rate,
        purchase_amount_yen: row.purchase_amount_yen,
        operation_change_yen: row.operation_change_yen,
        operation_change_rate: row.operation_change_rate,
        year: row.year,
        is_ytd: row.is_ytd,
      };
    }
    const periodMonth = state.asset.periodMonth;
    const found = (state.asset.monthly || []).find((row) => row.period_month === periodMonth);
    if (!found) {
      return state.asset.summary || null;
    }
    return found;
  }

  function assetMonthlyRowsForView() {
    const monthly = state.asset.monthly || [];
    if (state.asset.viewMode !== "year") {
      return monthly;
    }
    return monthly.filter((row) => yearFromMonth(row.period_month) === String(state.asset.year || ""));
  }

  function holdingsForCurrentMonth() {
    const month = state.asset.periodMonth;
    return (state.asset.holdingsByMonth || {})[month] || [];
  }

  function getAssetMetricValue(row, metric) {
    if (metric === "change") return Number(row.month_change_yen || 0);
    if (metric === "purchase") return Number(row.purchase_amount_yen || 0);
    if (metric === "operation") return Number(row.operation_change_yen || 0);
    return Number(row.current_value_yen || 0);
  }

  function renderAssetEmptyState() {
    const empty = $("assetEmptyState");
    if (!empty) {
      return;
    }
    empty.innerHTML = `
      <div class="asset-empty-card">
        <div class="asset-empty-copy">
          <p class="asset-empty-title">資産データを取り込むと表示されます</p>
          <p class="asset-empty-text">資産データがまだありません。SBI証券の保有資産CSVを取り込むと表示されます。</p>
        </div>
        <div class="asset-empty-image">${mascotImageHtml("thinking", "たぬきマスコット", "asset-empty-mascot")}</div>
      </div>
    `;
    bindMascotFallback(empty);
  }

  function renderAssetCards() {
    const el = $("assetCards");
    const summary = currentAssetSummary();
    if (!summary) {
      el.innerHTML = "";
      return;
    }
    const totalChange = summary.month_change_yen;
    const totalChangeRate = summary.month_change_rate;
    const operation = summary.operation_change_yen;
    const isYear = state.asset.viewMode === "year";
    const periodCaption = isYear
      ? (summary.is_ytd ? `${summary.year}年（年初〜最新月）` : `${summary.year}年`)
      : `評価日 ${escapeHtml(summary.valuation_date || "--")}`;

    el.innerHTML = `
      <article class="asset-card asset-card-total">
        <h3>${isYear ? "年次サマリー（評価額）" : "総資産（評価額）"}</h3>
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
        <div class="asset-mascot-wrap">${mascotImageHtml("cheer", "たぬきマスコット")}</div>
      </article>
    `;
    bindMascotFallback(el);
  }

  const ASSET_METRIC_LABELS = {
    value: "評価額",
    change: "総資産差（買い増し込み）",
    purchase: "買い増し額",
    operation: "運用増減（買い増し除外）",
  };

  function renderAssetChart() {
    const el = $("assetChart");
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
    
    let selectedIndex = state.asset.chartPointIndex !== null && state.asset.chartPointIndex >= 0 && state.asset.chartPointIndex < chartRows.length
      ? state.asset.chartPointIndex
      : chartRows.length - 1;
    
    if (selectedIndex >= chartRows.length) {
      selectedIndex = chartRows.length - 1;
      state.asset.chartPointIndex = selectedIndex;
    }
    
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
        ${points.map((point, idx) => `
          <circle cx="${point.x.toFixed(2)}" cy="${point.y.toFixed(2)}" r="${idx === selectedIndex ? '4.4' : '3.4'}" class="asset-chart-point${idx === selectedIndex ? ' active' : ''}" data-idx="${idx}"></circle>
          <circle cx="${point.x.toFixed(2)}" cy="${point.y.toFixed(2)}" r="14" class="asset-chart-hit-area" data-idx="${idx}" fill="transparent" style="cursor:pointer; pointer-events:all;"></circle>
        `).join('')}
        <g class="asset-chart-labels">${xLabels}</g>
        <g class="asset-chart-tooltip">
          <rect x="${(marker.x - 46).toFixed(2)}" y="${(marker.y - 36).toFixed(2)}" width="92" height="24" rx="10"></rect>
          <text x="${marker.x.toFixed(2)}" y="${(marker.y - 19).toFixed(2)}" text-anchor="middle">${escapeHtml(latestLabel)}</text>
        </g>
      </svg>
    `;
    el.querySelectorAll('.asset-chart-hit-area').forEach((node) => {
      node.addEventListener('click', () => {
        const next = Number(node.getAttribute('data-idx'));
        state.asset.chartPointIndex = Number.isFinite(next) ? next : chartRows.length - 1;
        renderAssetChart();
      });
    });
  }

  function renderAssetSummary() {
    const el = $("assetThisMonthSummary");
    const summary = currentAssetSummary();
    if (!summary) {
      el.innerHTML = "";
      return;
    }
    const isYear = state.asset.viewMode === "year";
    const rows = [
      [isYear ? "最新評価額" : "総資産", fmt.format(summary.current_value_yen || 0)],
      ["総資産差（買い増し込み）", summary.month_change_yen == null ? "--" : formatSignedYen(summary.month_change_yen)],
      [isYear ? "運用増減率" : "前月比", (isYear ? summary.operation_change_rate : summary.month_change_rate) == null ? "--" : formatSignedPercent(isYear ? summary.operation_change_rate : summary.month_change_rate)],
      ["買い増し額", fmt.format(summary.purchase_amount_yen || 0)],
      ["運用増減（買い増し除外）", summary.operation_change_yen == null ? "--" : formatSignedYen(summary.operation_change_yen)],
      [isYear ? '年初評価額' : '先月評価額', summary.previous_value_yen === null || summary.previous_value_yen === undefined ? '--' : fmt.format(summary.previous_value_yen)],
    ];
    el.innerHTML = rows.map(([k, v]) => `<div class="asset-summary-item"><dt>${escapeHtml(k)}</dt><dd>${escapeHtml(v)}</dd></div>`).join("");
  }

  function renderAssetYearly() {
    const el = $("assetYearlyCards");
    const list = state.asset.yearly || [];
    const title = $("assetPerformanceTitle");
    if (title) {
      title.textContent = "年次成績";
    }
    if (!list.length) {
      el.innerHTML = '<p class="notice">年次成績のデータがありません。</p>';
      return;
    }
    const rows = list.slice(0, 4);
    el.innerHTML = rows.map((row) => {
      const heading = row.is_ytd ? `${row.year}年（年初〜最新月）` : `${row.year}年`;
      return `
        <article class="asset-year-card">
          <h3>${escapeHtml(heading)}</h3>
          <p>年初評価額 ${fmt.format(row.start_value_yen || 0)}</p>
          <p>期末評価額 ${fmt.format(row.end_value_yen || 0)}</p>
          <p>総資産差（買い増し込み） ${formatSignedYen(row.total_change_yen || 0)}</p>
          <p>年間買い増し額 ${fmt.format(row.purchase_amount_yen || 0)}</p>
          <p>運用増減（買い増し除外） ${formatSignedYen(row.operation_change_yen || 0)}</p>
        </article>
      `;
    }).join("");
  }

  function renderAssetHoldings() {
    const el = $("assetHoldings");
    const rows = holdingsForCurrentMonth();
    if (!rows.length) {
      el.innerHTML = '<p class="notice">この月の保有商品はありません。</p>';
      return;
    }
    el.innerHTML = rows.map((row) => `
      <article class="asset-holding-card">
        <h3 class="asset-holding-title">${escapeHtml(row.name)}</h3>
        <div class="asset-holding-meta">${escapeHtml(row.account_type || "未分類")} / 評価日 ${escapeHtml(row.valuation_date || "--")}${row.source === "generated" ? " / 生成値" : ""}</div>
        <div class="asset-holding-grid">
          <p>評価額 <strong>${fmt.format(row.current_value_yen || 0)}</strong></p>
          <p>取得金額 <strong>${fmt.format(row.invested_amount_yen || 0)}</strong></p>
          <p>評価損益 <strong>${formatSignedYen(row.profit_loss_yen || 0)}</strong></p>
          <p>損益率 <strong>${row.profit_loss_rate == null ? "--" : formatSignedPercent(row.profit_loss_rate)}</strong></p>
        </div>
      </article>
    `).join("");
  }

  function populateAssetProductOptions() {
    const select = $("assetPurchaseProduct");
    const account = $("assetPurchaseAccountType");
    const products = state.asset.products || [];
    if (!products.length) {
      select.innerHTML = '<option value="">商品がありません</option>';
      account.value = "";
      return;
    }
    select.innerHTML = products.map((row) => `
      <option value="${row.id}" data-account="${escapeHtml(row.account_type || "")}">
        ${escapeHtml(row.name)} (${escapeHtml(row.account_type || "未分類")})
      </option>
    `).join("");
    const sync = () => {
      const selected = products.find((row) => String(row.id) === String(select.value));
      account.value = selected?.account_type || "";
    };
    select.onchange = sync;
    sync();
  }

  function renderAssetView() {
    updateAssetModeButtons();
    updateAssetPeriodLabel();
    updateAssetPeriodButtons();
    const hasData = hasAssetData();
    const empty = $("assetEmptyState");
    if (empty) {
      empty.hidden = hasData;
    }
    document.querySelectorAll("#assetTabView .asset-data-only").forEach((node) => {
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

  function shiftAssetPeriod(delta) {
    if (!assetCanShift(delta)) return;
    state.asset.chartPointIndex = null; // Reset selection when shifting period
    if (state.asset.viewMode === "year") {
      const years = assetYears();
      const idx = years.findIndex((item) => item === String(state.asset.year || ""));
      const next = years[idx - delta];
      if (!next) return;
      state.asset.year = next;
      const month = latestMonthInYear(next);
      if (month) {
        state.asset.periodMonth = month;
      }
      renderAssetView();
      return;
    }
    state.asset.periodMonth = shiftMonthValue(state.asset.periodMonth, delta);
    state.asset.chartPointIndex = null;
    renderAssetView();
  }

  function moveAssetLatest() {
    state.asset.chartPointIndex = null;
    if (state.asset.viewMode === "year") {
      const years = assetYears();
      if (!years.length) return;
      state.asset.year = years[0];
      const month = latestMonthInYear(years[0]);
      if (month) {
        state.asset.periodMonth = month;
      }
      renderAssetView();
      return;
    }
    const bounds = state.asset.bounds;
    if (!bounds) return;
    state.asset.periodMonth = bounds.max_month;
    renderAssetView();
  }

  function updateAssetModeButtons() {
    $("assetModeMonth").classList.toggle("active", state.asset.viewMode === "month");
    $("assetModeYear").classList.toggle("active", state.asset.viewMode === "year");
  }

  function changeAssetViewMode(mode) {
    state.asset.viewMode = mode;
    state.asset.chartPointIndex = null;
    if (mode === "year") {
      state.asset.year = yearFromMonth(state.asset.periodMonth) || assetYears()[0] || "";
      const month = latestMonthInYear(state.asset.year);
      if (month) {
        state.asset.periodMonth = month;
      }
    }
    updateAssetModeButtons();
    renderAssetView();
  }

  function openAssetPurchaseDialog() {
    const dialog = $("assetPurchaseDialog");
    const today = new Date().toISOString().slice(0, 10);
    $("assetPurchaseDate").value = today;
    $("assetPurchaseAmount").value = "";
    $("assetPurchaseQuantity").value = "";
    $("assetPurchaseUnitPrice").value = "";
    $("assetPurchaseSettlementDate").value = "";
    $("assetPurchaseMemo").value = "";
    populateAssetProductOptions();
    if (!(state.asset.products || []).length) {
      alert("買い増し対象の商品がありません。先に資産CSVを取り込んでください。");
      return;
    }
    dialog.showModal();
  }

  function saveAssetPurchase(ev) {
    ev.preventDefault();
    $("assetPurchaseDialog").close();
    alert(readonlyMessages.assetPurchase);
  }

  function updateMainTabView() {
    const isBudget = state.mainTab === "budget";
    const budgetView = $("budgetTabView");
    if (budgetView) {
      budgetView.hidden = !isBudget;
    }
    $("assetTabView").hidden = isBudget;
    $("appTitle").textContent = isBudget ? "家計簿" : "資産";
    const topActions = $("topActions");
    if (topActions) {
      topActions.hidden = !isBudget;
    }
    ["navHome", "navTransfer", "navBudget", "navAssets", "navSettings"].forEach((id) => {
      const button = $(id);
      if (button) {
        button.classList.remove("active");
      }
    });
    $("navBudget").classList.toggle("active", isBudget);
    $("navAssets").classList.toggle("active", !isBudget);
  }

  function setMainTab(tab) {
    state.mainTab = tab;
    updateMainTabView();
    if (tab === "assets") {
      renderAssetView();
    } else {
      loadAll();
    }
  }

  function setupReadonlyBadge() {
    const badge = $("readonlyDemoBadge");
    const exportedAt = payload.meta?.exported_at || "-";
    badge.textContent = `読み取り専用デモ / 書き出し: ${exportedAt}`;
  }

  $("prevPeriod").addEventListener("click", () => shiftPeriod(-1));
  $("nextPeriod").addEventListener("click", () => shiftPeriod(1));
  $("latestPeriod").addEventListener("click", moveToLatest);
  $("modeMonth").addEventListener("click", () => changeMode("month"));
  $("modeYear").addEventListener("click", () => changeMode("year"));
  $("expenseTab").addEventListener("click", () => changeDirection("expense"));
  $("incomeTab").addEventListener("click", () => changeDirection("income"));
  $("showSubcategories").addEventListener("change", (ev) => {
    state.showSubcategories = ev.target.checked;
    resetCategorySelection();
    state.analysisCache.clear();
    loadAll();
  });
  $("clearFilter").addEventListener("click", () => {
    resetCategorySelection();
    renderTransactions(queryTransactions({ direction: state.direction }));
  });
  $("syncButton").addEventListener("click", syncNow);
  $("editCategory").addEventListener("change", updateSubcategoryList);
  $("editSubcategory").addEventListener("input", syncSubcategoryChipState);
  $("saveEdit").addEventListener("click", saveEdit);
  document.querySelector("#editDialog .dialog-cancel").addEventListener("click", () => $("editDialog").close());
  $("viewTabCategory").addEventListener("click", () => setViewTab("category"));
  $("viewTabAnalysis").addEventListener("click", () => setViewTab("analysis"));
  $("viewFundMovement").addEventListener("click", () => {
    const item = {
      category_id: FUND_MOVEMENT_CATEGORY_ID,
      category_name: "資金移動・チャージ",
      subcategory: null,
    };
    selectCategory(item);
  });
  $("runAnalysisButton").addEventListener("click", runAnalysis);
  $("rerunAnalysisButton").addEventListener("click", runAnalysis);
  $("scrollTopButton").addEventListener("click", scrollToTop);
  $("assetPrevPeriod").addEventListener("click", () => shiftAssetPeriod(-1));
  $("assetNextPeriod").addEventListener("click", () => shiftAssetPeriod(1));
  $("assetLatestPeriod").addEventListener("click", moveAssetLatest);
  $("assetModeMonth").addEventListener("click", () => changeAssetViewMode("month"));
  $("assetModeYear").addEventListener("click", () => changeAssetViewMode("year"));
  $("assetRefreshPricesButton").addEventListener("click", () => alert(readonlyMessages.assetRefresh));
  $("openAssetPurchaseDialog").addEventListener("click", openAssetPurchaseDialog);
  $("saveAssetPurchase").addEventListener("click", saveAssetPurchase);
  document.querySelector("#assetPurchaseDialog .dialog-cancel").addEventListener("click", () => $("assetPurchaseDialog").close());
  document.querySelectorAll("#assetMetricTabs .asset-metric-tab").forEach((button) => {
    button.addEventListener("click", () => {
      state.asset.metric = button.dataset.metric || "value";
      document.querySelectorAll("#assetMetricTabs .asset-metric-tab").forEach((item) => {
        item.classList.toggle("active", item === button);
      });
      renderAssetChart();
    });
  });
  $("navBudget").addEventListener("click", () => setMainTab("budget"));
  $("navAssets").addEventListener("click", () => setMainTab("assets"));
  window.addEventListener("scroll", handleScrollTopVisibility, { passive: true });

  setupReadonlyBadge();
  updateModeButtons();
  updateDirectionButtons();
  renderViewTabs();
  updateMainTabView();
  handleScrollTopVisibility();
  loadAll();
})();
