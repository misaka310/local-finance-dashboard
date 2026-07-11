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
