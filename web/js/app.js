"use strict";

const API_URL =
  "https://axkd5z9qdd.execute-api.ap-northeast-1.amazonaws.com/screen";
const SAVED_FILTERS_KEY = "stock-compass.saved-filters.v1";
const SAVED_FILTERS_VERSION = 1;
const MAX_SAVED_FILTERS = 20;
const PAGE_SIZE = 50;

const form = document.querySelector("#screening-form");
const searchButton = document.querySelector("#search-button");
const resetButton = document.querySelector("#reset-button");
const formMessage = document.querySelector("#form-message");
const dataUpdatedAt = document.querySelector("#data-updated-at");
const resultSummary = document.querySelector("#result-summary");
const resultsBody = document.querySelector("#results-body");
const tableWrap = document.querySelector("#table-wrap");
const emptyState = document.querySelector("#empty-state");
const pagination = document.querySelector("#pagination");
const previousPage = document.querySelector("#previous-page");
const nextPage = document.querySelector("#next-page");
const pageStatus = document.querySelector("#page-status");
const filterPicker = document.querySelector("#filter-picker");
const addFilterButton = document.querySelector("#add-filter-button");
const activeFilterCount = document.querySelector("#active-filter-count");
const filterName = document.querySelector("#filter-name");
const saveFilterButton = document.querySelector("#save-filter-button");
const savedFilterList = document.querySelector("#saved-filter-list");
const savedMessage = document.querySelector("#saved-message");

let latestStocks = [];
let currentPage = 1;
let sortState = { key: "market_cap", type: "number", direction: "desc" };
let savedFilters = [];

const filterDefinitions = {
  market_cap: { label: "Market Cap" },
  per: { label: "P/E Ratio" },
  revenue_growth: { label: "Revenue Growth" },
  eps_growth: { label: "EPS Growth" },
  roe: { label: "ROE" },
  sector: { label: "Sector" },
  pbr: { label: "P/B Ratio" },
  dividend_yield: { label: "Dividend Yield" },
  roa: { label: "ROA" },
  eps_years: { label: "EPS Consecutive Growth" },
  fcf_yield: { label: "FCF Yield" },
  insider_hold: { label: "Insider Ownership" },
  rsi: { label: "RSI", technical: true },
  high_52w: { label: "52-week High Distance", technical: true },
  sma_20: { label: "SMA 20", technical: true },
  sma_50: { label: "SMA 50", technical: true },
  sma_200: { label: "SMA 200", technical: true },
  trend: { label: "Trend", technical: true },
};

const metricDescriptions = {
  ticker: "米国株を識別するための証券コードです。",
  name: "企業の名称です。",
  current_price: "データ取得時点の直近の終値です。",
  market_cap: "株価×発行済株式数で表す企業価値です。入力単位は10億米ドルです。",
  per: "株価収益率です。予想PERより実績PERを優先して使用します。",
  pbr: "株価純資産倍率です。株価が1株当たり純資産の何倍かを表します。",
  eps_growth: "取得できた年次EPSの最古値から最新値までの年平均成長率（CAGR）です。期間は銘柄により異なります。",
  eps_growth_rate: "取得できた年次EPSの最古値から最新値までの年平均成長率（CAGR）です。期間は銘柄により異なります。",
  eps_years: "直近から遡って、年次EPSが前年より増加した連続年数です。",
  revenue_growth: "Yahoo Financeから取得した売上高成長率です。複数年のCAGRではありません。",
  roe: "自己資本利益率です。株主資本に対してどれだけ利益を生んだかを表します。",
  roa: "総資産利益率です。企業の総資産に対してどれだけ利益を生んだかを表します。",
  dividend_yield: "年間配当額が株価に対して占める割合です。",
  fcf_yield: "フリーキャッシュフロー÷時価総額で計算する利回りです。",
  insider_hold: "役員などの内部関係者が保有する株式の割合です。",
  rsi: "直近14期間の値動きから計算する相対力指数です。0〜100で、一般に30未満は売られすぎ、70超は買われすぎの目安です。",
  high_52w: "現在価格が52週高値から何％離れているかを表します。高値と同水準なら0％、高値より下なら負数です。",
  sma_20: "現在価格が直近20期間の単純移動平均線より上か下かを指定します。",
  sma_50: "現在価格が直近50期間の単純移動平均線より上か下かを指定します。",
  sma_200: "現在価格が直近200期間の単純移動平均線より上か下かを指定します。",
  sector: "Yahoo Financeが分類した企業の事業セクターです。",
  trend: "RSI、MACD、20・50・200期間SMA、52週高値との位置を点数化した、このアプリ独自の総合判定です。",
  trend_signal: "RSI、MACD、20・50・200期間SMA、52週高値との位置を点数化した、このアプリ独自の総合判定です。",
};

const numericConditions = {
  "min-market-cap": {
    key: "min_market_cap",
    multiplier: 1_000_000_000,
    filterKey: "market_cap",
  },
  "max-market-cap": {
    key: "max_market_cap",
    multiplier: 1_000_000_000,
    filterKey: "market_cap",
  },
  "min-per": { key: "min_per", filterKey: "per" },
  "max-per": { key: "max_per", filterKey: "per" },
  "min-pbr": { key: "min_pbr", filterKey: "pbr" },
  "max-pbr": { key: "max_pbr", filterKey: "pbr" },
  "min-dividend-yield": {
    key: "min_dividend_yield",
    filterKey: "dividend_yield",
  },
  "max-dividend-yield": {
    key: "max_dividend_yield",
    filterKey: "dividend_yield",
  },
  "min-roe": { key: "min_roe", filterKey: "roe" },
  "min-roa": { key: "min_roa", filterKey: "roa" },
  "min-revenue-growth": {
    key: "min_revenue_growth",
    filterKey: "revenue_growth",
  },
  "min-eps-growth": { key: "min_eps_growth", filterKey: "eps_growth" },
  "min-eps-consecutive-years": {
    key: "min_eps_consecutive_years",
    filterKey: "eps_years",
  },
  "min-fcf-yield": { key: "min_fcf_yield", filterKey: "fcf_yield" },
  "min-insider-hold": {
    key: "min_insider_hold",
    filterKey: "insider_hold",
  },
  "max-insider-hold": {
    key: "max_insider_hold",
    filterKey: "insider_hold",
  },
  "min-rsi": { key: "min_rsi", filterKey: "rsi", technical: true },
  "max-rsi": { key: "max_rsi", filterKey: "rsi", technical: true },
  "min-pct-from-52w-high": {
    key: "min_pct_from_52w_high",
    filterKey: "high_52w",
    technical: true,
  },
  "max-pct-from-52w-high": {
    key: "max_pct_from_52w_high",
    filterKey: "high_52w",
    technical: true,
  },
};

const rangePairs = [
  ["min-market-cap", "max-market-cap", "時価総額", "market_cap"],
  ["min-per", "max-per", "PER", "per"],
  ["min-pbr", "max-pbr", "PBR", "pbr"],
  [
    "min-dividend-yield",
    "max-dividend-yield",
    "配当利回り",
    "dividend_yield",
  ],
  [
    "min-insider-hold",
    "max-insider-hold",
    "インサイダー保有率",
    "insider_hold",
  ],
  ["min-rsi", "max-rsi", "RSI", "rsi"],
  [
    "min-pct-from-52w-high",
    "max-pct-from-52w-high",
    "52週高値からの乖離",
    "high_52w",
  ],
];

function getFilterRow(filterKey) {
  return document.querySelector(`[data-filter-key="${filterKey}"]`);
}

function isFilterActive(filterKey) {
  const row = getFilterRow(filterKey);
  return Boolean(row && !row.hidden);
}

function clearFilterRow(row) {
  row.querySelectorAll("input, select").forEach((control) => {
    if (control.tagName === "SELECT") {
      control.selectedIndex = 0;
    } else {
      control.value = "";
    }
  });
}

function activateFilter(filterKey) {
  const row = getFilterRow(filterKey);
  if (!row) return;
  row.hidden = false;
  updateFilterControls();
}

function removeFilter(filterKey) {
  const row = getFilterRow(filterKey);
  if (!row || row.dataset.persistent === "true") return;
  clearFilterRow(row);
  row.hidden = true;
  updateFilterControls();
}

function updateFilterControls() {
  const activeRows = [...document.querySelectorAll(".filter-row:not([hidden])")];
  activeFilterCount.textContent = String(activeRows.length);

  const previousSelection = filterPicker.value;
  filterPicker.replaceChildren(new Option("Add filter…", ""));
  Object.entries(filterDefinitions).forEach(([key, definition]) => {
    if (!isFilterActive(key)) {
      const label = definition.technical
        ? `${definition.label}（テクニカル）`
        : definition.label;
      filterPicker.add(new Option(label, key));
    }
  });

  if ([...filterPicker.options].some((option) => option.value === previousSelection)) {
    filterPicker.value = previousSelection;
  }
  const hasAvailableFilters = filterPicker.options.length > 1;
  filterPicker.disabled = !hasAvailableFilters;
  addFilterButton.disabled = !hasAvailableFilters || !filterPicker.value;
}

function initializeMetricDescriptions() {
  document.querySelectorAll(".filter-row[data-filter-key]").forEach((row) => {
    const description = metricDescriptions[row.dataset.filterKey];
    const label = row.querySelector(".filter-label > label");
    if (!description || !label) return;
    label.classList.add("metric-help");
    label.title = description;
  });

  document.querySelectorAll("th button[data-sort-key]").forEach((button) => {
    const description = metricDescriptions[button.dataset.sortKey];
    if (!description) return;
    button.classList.add("metric-help");
    button.title = description;
  });
}

function readNumber(id) {
  const element = document.querySelector(`#${id}`);
  if (!element || element.value.trim() === "") return null;
  const value = Number(element.value);
  return Number.isFinite(value) ? value : null;
}

function buildConditions() {
  const conditions = {};

  Object.entries(numericConditions).forEach(([id, definition]) => {
    if (!isFilterActive(definition.filterKey)) return;
    const value = readNumber(id);
    if (value !== null) {
      conditions[definition.key] = value * (definition.multiplier ?? 1);
    }
  });

  if (isFilterActive("sector")) {
    const sector = document.querySelector("#sector").value;
    if (sector) conditions.sectors = [sector];
  }

  [20, 50, 200].forEach((period) => {
    const filterKey = `sma_${period}`;
    if (!isFilterActive(filterKey)) return;
    const value = document.querySelector(`#above-sma-${period}`).value;
    if (value) conditions[`above_sma_${period}`] = value === "true";
  });

  if (isFilterActive("trend")) {
    const trend = document.querySelector("#trend-signal").value;
    if (trend) conditions.trend_signals = [trend];
  }

  return conditions;
}

function validateConditions() {
  for (const [minimumId, maximumId, label, filterKey] of rangePairs) {
    if (!isFilterActive(filterKey)) continue;
    const minimum = readNumber(minimumId);
    const maximum = readNumber(maximumId);
    if (minimum !== null && maximum !== null && minimum > maximum) {
      return `${label}は、最小値を最大値以下にしてください。`;
    }
  }

  if (!form.checkValidity()) return "入力値の範囲を確認してください。";
  return "";
}

function resetFilters() {
  form.reset();
  document.querySelectorAll(".optional-filter").forEach((row) => {
    row.hidden = true;
  });
  filterName.value = "";
  formMessage.textContent = "";
  updateFilterControls();
}

function setLoading(isLoading) {
  searchButton.disabled = isLoading;
  resetButton.disabled = isLoading;
  searchButton.classList.toggle("is-loading", isLoading);
  searchButton.querySelector(".button-label").textContent = isLoading
    ? "Searching"
    : "Search stocks";
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function readSavedFilters() {
  try {
    const raw = window.localStorage.getItem(SAVED_FILTERS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (
      !isPlainObject(parsed) ||
      parsed.version !== SAVED_FILTERS_VERSION ||
      !Array.isArray(parsed.filters)
    ) {
      throw new Error("保存形式が不正です");
    }

    return parsed.filters.filter(
      (item) =>
        isPlainObject(item) &&
        typeof item.name === "string" &&
        item.name.trim() &&
        isPlainObject(item.conditions) &&
        typeof item.includeTechnicals === "boolean",
    );
  } catch {
    try {
      window.localStorage.removeItem(SAVED_FILTERS_KEY);
    } catch {
      // localStorage自体が利用できない場合も、画面の他機能は継続する。
    }
    savedMessage.classList.add("is-error");
    savedMessage.textContent = "保存データを読み込めなかったため初期化しました。";
    return [];
  }
}

function writeSavedFilters() {
  try {
    window.localStorage.setItem(
      SAVED_FILTERS_KEY,
      JSON.stringify({ version: SAVED_FILTERS_VERSION, filters: savedFilters }),
    );
    return true;
  } catch {
    savedMessage.classList.add("is-error");
    savedMessage.textContent = "このブラウザでは検索条件を保存できません。";
    return false;
  }
}

function renderSavedFilters() {
  savedFilterList.replaceChildren();
  if (savedFilters.length === 0) {
    const empty = document.createElement("p");
    empty.className = "saved-empty";
    empty.textContent = "保存済みの条件はありません。";
    savedFilterList.append(empty);
    return;
  }

  savedFilters.forEach((savedFilter) => {
    const item = document.createElement("div");
    item.className = "saved-filter-item";

    const loadButton = document.createElement("button");
    loadButton.type = "button";
    loadButton.className = "load-filter";
    loadButton.textContent = savedFilter.name;
    loadButton.title = `${savedFilter.name}を読み込む`;
    loadButton.addEventListener("click", () => applySavedFilter(savedFilter));

    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "delete-filter";
    deleteButton.textContent = "×";
    deleteButton.setAttribute("aria-label", `${savedFilter.name}を削除`);
    deleteButton.addEventListener("click", () => deleteSavedFilter(savedFilter.name));

    item.append(loadButton, deleteButton);
    savedFilterList.append(item);
  });
}

function saveCurrentFilter() {
  savedMessage.classList.remove("is-error");
  savedMessage.textContent = "";
  const name = filterName.value.trim();
  if (!name) {
    savedMessage.classList.add("is-error");
    savedMessage.textContent = "条件名を入力してください。";
    filterName.focus();
    return;
  }

  const validationError = validateConditions();
  if (validationError) {
    savedMessage.classList.add("is-error");
    savedMessage.textContent = validationError;
    return;
  }

  const existingIndex = savedFilters.findIndex(
    (item) => item.name.toLocaleLowerCase() === name.toLocaleLowerCase(),
  );
  const conditions = buildConditions();
  if (Object.keys(conditions).length === 0) {
    savedMessage.classList.add("is-error");
    savedMessage.textContent = "少なくとも1つの検索条件を指定してください。";
    return;
  }
  const savedFilter = {
    name,
    conditions,
    // v1の保存形式との互換性を維持する。
    includeTechnicals: true,
  };

  if (existingIndex >= 0) {
    if (!window.confirm(`「${savedFilters[existingIndex].name}」を上書きしますか？`)) {
      return;
    }
    savedFilters[existingIndex] = savedFilter;
  } else {
    if (savedFilters.length >= MAX_SAVED_FILTERS) {
      savedMessage.classList.add("is-error");
      savedMessage.textContent = `保存できる条件は最大${MAX_SAVED_FILTERS}件です。`;
      return;
    }
    savedFilters.push(savedFilter);
  }

  savedFilters.sort((left, right) => left.name.localeCompare(right.name, "ja"));
  if (!writeSavedFilters()) return;
  renderSavedFilters();
  filterName.value = "";
  savedMessage.textContent = existingIndex >= 0 ? "条件を上書きしました。" : "条件を保存しました。";
}

function deleteSavedFilter(name) {
  savedFilters = savedFilters.filter((item) => item.name !== name);
  if (!writeSavedFilters()) return;
  renderSavedFilters();
  savedMessage.classList.remove("is-error");
  savedMessage.textContent = `「${name}」を削除しました。`;
}

function applySavedFilter(savedFilter) {
  resetFilters();
  const conditions = savedFilter.conditions;

  Object.entries(numericConditions).forEach(([id, definition]) => {
    if (!Object.hasOwn(conditions, definition.key)) return;
    activateFilter(definition.filterKey);
    const value = Number(conditions[definition.key]);
    if (Number.isFinite(value)) {
      document.querySelector(`#${id}`).value = value / (definition.multiplier ?? 1);
    }
  });

  if (Array.isArray(conditions.sectors) && conditions.sectors.length > 0) {
    document.querySelector("#sector").value = conditions.sectors[0];
  }

  [20, 50, 200].forEach((period) => {
    const conditionKey = `above_sma_${period}`;
    if (!Object.hasOwn(conditions, conditionKey)) return;
    activateFilter(`sma_${period}`);
    document.querySelector(`#above-sma-${period}`).value = String(
      conditions[conditionKey],
    );
  });

  if (Array.isArray(conditions.trend_signals) && conditions.trend_signals.length > 0) {
    activateFilter("trend");
    document.querySelector("#trend-signal").value = conditions.trend_signals[0];
  }

  updateFilterControls();
  savedMessage.classList.remove("is-error");
  savedMessage.textContent = `「${savedFilter.name}」を読み込みました。`;
  formMessage.textContent = "";
}

function formatNumber(value, digits = 1) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) {
    return "—";
  }
  return new Intl.NumberFormat("ja-JP", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(Number(value));
}

function formatPercent(value, digits = 1) {
  const formatted = formatNumber(value, digits);
  return formatted === "—" ? formatted : `${formatted}%`;
}

function formatPrice(value) {
  const formatted = formatNumber(value, 2);
  return formatted === "—" ? formatted : `$${formatted}`;
}

function showDataUpdatedAt(value) {
  const date = new Date(value);
  if (!value || Number.isNaN(date.getTime())) {
    dataUpdatedAt.textContent = "取得日時の情報なし";
    dataUpdatedAt.removeAttribute("datetime");
    return;
  }

  dataUpdatedAt.dateTime = date.toISOString();
  dataUpdatedAt.textContent = `${new Intl.DateTimeFormat("ja-JP", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Tokyo",
  }).format(date)} JST`;
}

function formatMarketCap(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  if (number >= 1_000_000_000_000) {
    return `$${formatNumber(number / 1_000_000_000_000, 2)}T`;
  }
  if (number >= 1_000_000_000) {
    return `$${formatNumber(number / 1_000_000_000, 2)}B`;
  }
  if (number >= 1_000_000) {
    return `$${formatNumber(number / 1_000_000, 1)}M`;
  }
  return `$${formatNumber(number, 0)}`;
}

function createCell(text, className = "") {
  const cell = document.createElement("td");
  cell.textContent = text;
  if (className) cell.className = className;
  return cell;
}

function stockUrl(ticker) {
  return `https://finance.yahoo.com/quote/${encodeURIComponent(ticker ?? "")}`;
}

function createLinkedCell(stock, type) {
  const cell = document.createElement("td");
  const link = document.createElement("a");
  link.href = stockUrl(stock.ticker);
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.className = type === "ticker" ? "ticker-link" : "company-link";
  link.textContent = type === "ticker" ? stock.ticker || "—" : stock.name || "—";
  if (type === "company") link.title = stock.name || "";
  cell.append(link);
  return cell;
}

function createTrendCell(value) {
  const cell = document.createElement("td");
  if (!value) {
    cell.textContent = "—";
    return cell;
  }
  const trend = document.createElement("span");
  trend.className = `trend trend-${value.toLowerCase().replaceAll("_", "-")}`;
  trend.textContent = value.replaceAll("_", " ");
  cell.append(trend);
  return cell;
}

function sortedStocks() {
  return [...latestStocks].sort((left, right) => {
    const leftRaw = left[sortState.key];
    const rightRaw = right[sortState.key];
    const leftMissing =
      leftRaw === null ||
      leftRaw === undefined ||
      leftRaw === "" ||
      (sortState.type === "number" && !Number.isFinite(Number(leftRaw)));
    const rightMissing =
      rightRaw === null ||
      rightRaw === undefined ||
      rightRaw === "" ||
      (sortState.type === "number" && !Number.isFinite(Number(rightRaw)));
    if (leftMissing !== rightMissing) return leftMissing ? 1 : -1;
    if (leftMissing && rightMissing) return 0;

    let comparison;
    if (sortState.type === "number") {
      comparison = Number(leftRaw) - Number(rightRaw);
    } else {
      comparison = String(leftRaw).localeCompare(String(rightRaw), "en", {
        sensitivity: "base",
      });
    }
    return sortState.direction === "asc" ? comparison : -comparison;
  });
}

function updateSortHeaders() {
  document.querySelectorAll("th").forEach((heading) => {
    const button = heading.querySelector("button[data-sort-key]");
    if (!button) return;
    const active = button.dataset.sortKey === sortState.key;
    heading.removeAttribute("aria-sort");
    button.querySelector("span").textContent = active
      ? sortState.direction === "asc"
        ? "↑"
        : "↓"
      : "";
    if (active) {
      heading.setAttribute(
        "aria-sort",
        sortState.direction === "asc" ? "ascending" : "descending",
      );
    }
  });
}

function renderResults() {
  resultsBody.replaceChildren();
  const stocks = sortedStocks();
  const pageCount = Math.max(1, Math.ceil(stocks.length / PAGE_SIZE));
  currentPage = Math.min(currentPage, pageCount);
  const offset = (currentPage - 1) * PAGE_SIZE;
  const visibleStocks = stocks.slice(offset, offset + PAGE_SIZE);

  visibleStocks.forEach((stock) => {
    const row = document.createElement("tr");
    row.append(
      createLinkedCell(stock, "ticker"),
      createLinkedCell(stock, "company"),
      createCell(formatPrice(stock.current_price), "numeric"),
      createCell(formatMarketCap(stock.market_cap), "numeric"),
      createCell(formatNumber(stock.per, 2), "numeric"),
      createCell(formatNumber(stock.pbr, 2), "numeric"),
      createCell(formatPercent(stock.eps_growth_rate, 1), "numeric"),
      createCell(formatPercent(stock.revenue_growth, 1), "numeric"),
      createCell(formatPercent(stock.roe, 1), "numeric"),
      createCell(formatPercent(stock.dividend_yield, 2), "numeric"),
      createCell(formatNumber(stock.rsi, 1), "numeric"),
      createCell(stock.sector || "—"),
      createTrendCell(stock.trend_signal),
    );
    resultsBody.append(row);
  });

  const hasResults = latestStocks.length > 0;
  tableWrap.hidden = !hasResults;
  emptyState.hidden = hasResults;
  pagination.hidden = !hasResults;
  updateSortHeaders();

  if (hasResults) {
    const first = offset + 1;
    const last = offset + visibleStocks.length;
    resultSummary.textContent = `${latestStocks.length.toLocaleString("ja-JP")} companies found · ${first.toLocaleString("ja-JP")}–${last.toLocaleString("ja-JP")}件を表示`;
    pageStatus.textContent = `Page ${currentPage} of ${pageCount}`;
    previousPage.disabled = currentPage === 1;
    nextPage.disabled = currentPage === pageCount;
  } else {
    emptyState.querySelector("strong").textContent = "No matching companies";
    emptyState.querySelector("p").textContent = "条件を緩めて、もう一度検索してください。";
    resultSummary.textContent = "0 companies found";
  }
}

async function requestApi(payload, timeoutMilliseconds = 25_000) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMilliseconds);

  try {
    const response = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    let data;
    try {
      data = await response.json();
    } catch {
      throw new Error("APIから正しいJSONが返されませんでした。");
    }
    if (!response.ok) {
      throw new Error(data.error || `APIエラーが発生しました（${response.status}）。`);
    }
    return data;
  } finally {
    window.clearTimeout(timeout);
  }
}

async function requestScreening(payload) {
  const data = await requestApi(payload);
  if (!Array.isArray(data.stocks)) {
    throw new Error("APIレスポンスの形式が正しくありません。");
  }
  return data;
}

async function loadDataUpdatedAt() {
  try {
    const data = await requestApi({ metadata_only: true }, 10_000);
    showDataUpdatedAt(data.generated_at);
  } catch {
    dataUpdatedAt.textContent = "取得日時を確認できません";
    dataUpdatedAt.removeAttribute("datetime");
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  formMessage.textContent = "";
  const validationError = validateConditions();
  if (validationError) {
    formMessage.textContent = validationError;
    return;
  }

  const conditions = buildConditions();
  if (Object.keys(conditions).length === 0) {
    formMessage.textContent = "少なくとも1つの検索条件を指定してください。";
    return;
  }

  setLoading(true);
  resultSummary.textContent = "最新の保存データを検索しています…";
  try {
    const data = await requestScreening({
      conditions,
      include_technicals: true,
    });
    if (!dataUpdatedAt.hasAttribute("datetime")) {
      showDataUpdatedAt(data.generated_at);
    }
    latestStocks = data.stocks;
    currentPage = 1;
    renderResults();
    document.querySelector("#results-section").scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  } catch (error) {
    latestStocks = [];
    tableWrap.hidden = true;
    pagination.hidden = true;
    emptyState.hidden = false;
    emptyState.querySelector("strong").textContent = "Search failed";
    emptyState.querySelector("p").textContent =
      error.name === "AbortError"
        ? "応答がタイムアウトしました。しばらく待って再実行してください。"
        : error.message;
    resultSummary.textContent = "APIとの通信を確認してください。";
  } finally {
    setLoading(false);
  }
});

resetButton.addEventListener("click", resetFilters);

addFilterButton.addEventListener("click", () => {
  const filterKey = filterPicker.value;
  if (!filterKey) return;
  activateFilter(filterKey);
  const row = getFilterRow(filterKey);
  const firstControl = row.querySelector("input, select");
  if (firstControl && !firstControl.disabled) firstControl.focus();
});

filterPicker.addEventListener("change", () => {
  addFilterButton.disabled = !filterPicker.value;
});

document.querySelectorAll(".remove-filter").forEach((button) => {
  button.addEventListener("click", () => {
    removeFilter(button.closest(".filter-row").dataset.filterKey);
  });
});

saveFilterButton.addEventListener("click", saveCurrentFilter);
filterName.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    saveCurrentFilter();
  }
});

document.querySelectorAll("th button[data-sort-key]").forEach((button) => {
  button.addEventListener("click", () => {
    const key = button.dataset.sortKey;
    if (sortState.key === key) {
      sortState.direction = sortState.direction === "asc" ? "desc" : "asc";
    } else {
      sortState = {
        key,
        type: button.dataset.sortType,
        direction: button.dataset.sortType === "text" ? "asc" : "desc",
      };
    }
    currentPage = 1;
    renderResults();
  });
});

previousPage.addEventListener("click", () => {
  if (currentPage <= 1) return;
  currentPage -= 1;
  renderResults();
  tableWrap.scrollTop = 0;
});

nextPage.addEventListener("click", () => {
  const pageCount = Math.ceil(latestStocks.length / PAGE_SIZE);
  if (currentPage >= pageCount) return;
  currentPage += 1;
  renderResults();
  tableWrap.scrollTop = 0;
});

updateFilterControls();
initializeMetricDescriptions();
savedFilters = readSavedFilters();
renderSavedFilters();
updateSortHeaders();
loadDataUpdatedAt();
